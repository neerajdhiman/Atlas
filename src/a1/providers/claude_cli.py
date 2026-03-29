"""Claude CLI proxy provider — routes requests through the local Claude CLI.

Uses the `claude` command-line tool (which handles its own OAuth/auth)
to forward completion requests to Anthropic's API. This avoids needing
a separate API key since the CLI manages token refresh automatically.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from a1.common.logging import get_logger
from a1.providers.base import LLMProvider, ModelInfo
from a1.proxy.request_models import ChatCompletionRequest
from a1.proxy.response_models import (
    ChatCompletionChunk,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    DeltaMessage,
    StreamChoice,
    Usage,
)
from a1.common.tokens import count_tokens_for_model, count_messages_tokens_for_model

log = get_logger("providers.claude_cli")

# Cache of atlas-model-name → system_prompt_suffix loaded from providers.yaml
_atlas_suffixes: dict[str, str] | None = None


def get_atlas_system_suffix(atlas_model: str) -> str:
    """Return the domain-specific system prompt suffix for an Atlas model.

    Loads config/providers.yaml on first call and caches the result.
    Returns empty string if model not found or YAML unavailable.
    """
    global _atlas_suffixes
    if _atlas_suffixes is None:
        _atlas_suffixes = {}
        try:
            import os
            import yaml
            config_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "config", "providers.yaml"
            )
            config_path = os.path.normpath(config_path)
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            for model_cfg in data.get("providers", {}).get("atlas", {}).get("models", []):
                name = model_cfg.get("name", "")
                suffix = model_cfg.get("system_prompt_suffix", "")
                if name and suffix:
                    _atlas_suffixes[name] = suffix.strip()
        except Exception as e:
            log.warning(f"Could not load atlas suffixes from providers.yaml: {e}")
    return _atlas_suffixes.get(atlas_model, "")


# Models available through Claude CLI (Max subscription)
CLAUDE_CLI_MODELS = [
    ModelInfo(
        name="claude-sonnet-4-20250514",
        provider="claude-cli",
        context_window=200000,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        name="claude-haiku-4-5-20251001",
        provider="claude-cli",
        context_window=200000,
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.005,
        supports_tools=True,
        supports_streaming=True,
    ),
    ModelInfo(
        name="claude-opus-4-20250514",
        provider="claude-cli",
        context_window=200000,
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
        supports_tools=True,
        supports_streaming=True,
    ),
]


class ClaudeCLIProvider(LLMProvider):
    """Provider that proxies requests through the local Claude CLI.

    The CLI handles authentication (OAuth token refresh) automatically,
    so we just pipe prompts through it and parse the output.
    """

    name = "claude-cli"

    def __init__(self):
        self._healthy = False
        self._cli_path = self._find_claude_cli()
        self._models = list(CLAUDE_CLI_MODELS)

    @staticmethod
    def _find_claude_cli() -> str:
        """Find the claude CLI executable path."""
        import shutil
        import sys
        import os

        # Try common locations
        candidates = [
            shutil.which("claude"),
            shutil.which("claude.cmd"),
            os.path.expanduser("~/AppData/Roaming/npm/claude.cmd"),
            os.path.expanduser("~/AppData/Roaming/npm/claude"),
            "/usr/local/bin/claude",
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path

        # Fallback — let the OS find it via shell
        return "claude.cmd" if sys.platform == "win32" else "claude"

    async def _run_claude(self, prompt: str, system: str = "", max_tokens: int = 1000) -> dict:
        """Run the claude CLI with a prompt and return parsed JSON result.

        Returns dict with: result (text), usage (tokens), duration_api_ms, cost
        """
        args = [
            "-p", prompt,
            "--max-turns", "3",
            "--output-format", "json",
        ]

        # Prepend Atlas identity to system prompt
        atlas_identity = (
            "You are Atlas, an AI assistant by Alpheric.AI. "
            "Never identify as Claude, Anthropic, or any other AI. "
            "You are Atlas and your responses represent "
            "the Alpheric.AI platform."
        )
        full_system = (
            f"{atlas_identity}\n\n{system}" if system
            else atlas_identity
        )
        args.extend(["--system-prompt", full_system])

        # Log command length for debugging Windows arg limits
        total_len = sum(len(a) for a in args)
        if total_len > 7000:
            log.warning(
                f"Claude CLI args very long ({total_len} chars)"
                f" — may hit Windows 8191 char limit"
            )

        output, code, stderr = await self._exec(
            args, timeout=120,
        )

        if code != 0:
            log.error(
                f"Claude CLI exit={code} "
                f"stderr={stderr[:500] if stderr else 'empty'}"
            )
            if not output:
                raise RuntimeError(
                    f"Claude CLI exit code {code}: "
                    f"{stderr[:300] if stderr else 'no output'}"
                )

        # Parse JSON response for accurate token counts
        try:
            import json
            data = json.loads(output)

            # Extract text — handle error_max_turns where
            # result may be empty because Claude tried tool_use
            text = data.get("result", "")
            if not text and data.get("subtype") == "error_max_turns":
                log.warning(
                    "Claude hit max turns (tool_use), "
                    "returning partial result"
                )
                text = (
                    "I can help with that, but I don't have "
                    "access to external tools. Let me answer "
                    "based on my knowledge instead."
                )

            return {
                "text": text or output,
                "input_tokens": data.get(
                    "usage", {},
                ).get("input_tokens", 0),
                "output_tokens": data.get(
                    "usage", {},
                ).get("output_tokens", 0),
                "cache_read_tokens": data.get(
                    "usage", {},
                ).get("cache_read_input_tokens", 0),
                "cost_usd": data.get("total_cost_usd", 0.0),
                "api_duration_ms": data.get(
                    "duration_api_ms", 0,
                ),
            }
        except (json.JSONDecodeError, KeyError):
            return {
                "text": output,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cost_usd": 0.0,
                "api_duration_ms": 0,
            }

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        # Build prompt from messages
        system_prompt = ""
        user_prompt = ""
        for msg in request.messages:
            if msg.role == "system":
                system_prompt = msg.content or ""
            elif msg.role == "user":
                user_prompt = msg.content or ""
            elif msg.role == "assistant":
                user_prompt += f"\n\nPrevious assistant response: {msg.content}"

        if not user_prompt:
            user_prompt = "Hello"

        result = await self._run_claude(
            user_prompt,
            system=system_prompt,
            max_tokens=request.max_tokens or 1000,
        )

        # Use accurate token counts from CLI JSON output
        prompt_tokens = result["input_tokens"] + result["cache_read_tokens"]
        completion_tokens = result["output_tokens"]
        if prompt_tokens == 0:
            # Fallback to estimation
            messages_dicts = [{"role": m.role, "content": m.content or ""} for m in request.messages]
            prompt_tokens = count_messages_tokens_for_model(messages_dicts, "claude-sonnet-4-20250514")
            completion_tokens = count_tokens_for_model(result["text"], "claude-sonnet-4-20250514")

        return ChatCompletionResponse(
            id=f"chatcmpl-cli-{uuid.uuid4().hex[:8]}",
            model=request.model,
            choices=[Choice(message=ChoiceMessage(content=result["text"]))],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            provider=self.name,
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[ChatCompletionChunk]:
        """Stream tokens from Claude CLI as they arrive."""
        system_prompt = ""
        user_prompt = ""
        for msg in request.messages:
            if msg.role == "system":
                system_prompt = msg.content or ""
            elif msg.role == "user":
                user_prompt = msg.content or ""
            elif msg.role == "assistant":
                user_prompt += f"\n\nPrevious assistant response: {msg.content}"

        if not user_prompt:
            user_prompt = "Hello"

        atlas_identity = (
            "You are Atlas, an AI assistant by Alpheric.AI. "
            "Never identify as Claude, Anthropic, or any other AI. "
            "You are Atlas and your responses represent the Alpheric.AI platform."
        )
        full_system = f"{atlas_identity}\n\n{system_prompt}" if system_prompt else atlas_identity

        chunk_id = f"chatcmpl-cli-{uuid.uuid4().hex[:8]}"
        import os, sys

        # Force UTF-8 for emoji/unicode handling on Windows
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "LANG": "en_US.UTF-8"}

        # Start CLI in text streaming mode (tokens arrive as they're generated).
        # Use create_subprocess_exec (never shell) to prevent command injection
        # from user-controlled content. On Windows, .cmd/.bat files require
        # cmd.exe as the launcher — args are still passed as discrete list
        # elements, never joined into a shell string.
        cli = self._cli_path
        base_cmd = [cli, "-p", user_prompt, "--max-turns", "1", "--system-prompt", full_system]
        if sys.platform == "win32" and cli.lower().endswith((".cmd", ".bat")):
            exec_cmd = ["cmd.exe", "/c"] + base_cmd
        else:
            exec_cmd = base_cmd
        proc = await asyncio.create_subprocess_exec(
            *exec_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        yield ChatCompletionChunk(
            id=chunk_id, model=request.model,
            choices=[StreamChoice(delta=DeltaMessage(role="assistant"))],
        )

        full_content = ""
        try:
            while True:
                chunk = await asyncio.wait_for(proc.stdout.read(80), timeout=120)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                full_content += text
                yield ChatCompletionChunk(
                    id=chunk_id, model=request.model,
                    choices=[StreamChoice(delta=DeltaMessage(content=text))],
                )
        except asyncio.TimeoutError:
            pass

        await proc.wait()

        # Estimate tokens
        prompt_tokens = count_messages_tokens_for_model(
            [{"role": m.role, "content": m.content or ""} for m in request.messages],
            "claude-sonnet-4-20250514"
        )
        completion_tokens = count_tokens_for_model(full_content, "claude-sonnet-4-20250514")

        yield ChatCompletionChunk(
            id=chunk_id, model=request.model,
            choices=[StreamChoice(delta=DeltaMessage(), finish_reason="stop")],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    async def _exec(
        self, args: list[str], timeout: float = 30,
    ) -> tuple[str, int, str]:
        """Execute CLI command and return (stdout, returncode, stderr)."""
        import os, sys
        cmd = [self._cli_path] + args

        # Force UTF-8 encoding to handle emojis/unicode
        env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "LANG": "en_US.UTF-8",
        }

        # Use create_subprocess_exec (never shell) to prevent command injection.
        # On Windows, .cmd/.bat files require cmd.exe as the launcher — args are
        # still passed as discrete list elements, never joined into a shell string.
        cli = cmd[0]
        exec_args = cmd[1:]
        if sys.platform == "win32" and cli.lower().endswith((".cmd", ".bat")):
            exec_cmd = ["cmd.exe", "/c", cli] + exec_args
        else:
            exec_cmd = cmd
        proc = await asyncio.create_subprocess_exec(
            *exec_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout,
        )
        return (
            stdout.decode("utf-8", errors="replace").strip(),
            proc.returncode or 0,
            stderr.decode("utf-8", errors="replace").strip(),
        )

    async def health_check(self) -> bool:
        """Check if Claude CLI is available and authenticated."""
        try:
            version, code, _ = await self._exec(
                ["--version"], timeout=10,
            )
            if version and code == 0:
                self._healthy = True
                log.info(f"Claude CLI healthy: {version}")
                return True
        except Exception as e:
            log.warning(f"Claude CLI health check failed: {e}")

        self._healthy = False
        return False

    def supports_model(self, model: str) -> bool:
        return any(m.name == model for m in self._models)

    def list_models(self) -> list[ModelInfo]:
        return self._models
