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
        args = ["-p", prompt, "--max-turns", "1", "--output-format", "json"]
        if system:
            args.extend(["--system-prompt", system])

        output, code = await self._exec(args, timeout=120)

        if code != 0 and not output:
            raise RuntimeError(f"Claude CLI failed with exit code {code}")

        # Parse JSON response for accurate token counts
        try:
            import json
            data = json.loads(output)
            return {
                "text": data.get("result", output),
                "input_tokens": data.get("usage", {}).get("input_tokens", 0),
                "output_tokens": data.get("usage", {}).get("output_tokens", 0),
                "cache_read_tokens": data.get("usage", {}).get("cache_read_input_tokens", 0),
                "cost_usd": data.get("total_cost_usd", 0.0),
                "api_duration_ms": data.get("duration_api_ms", 0),
            }
        except (json.JSONDecodeError, KeyError):
            # Fallback: treat output as plain text
            return {"text": output, "input_tokens": 0, "output_tokens": 0,
                    "cache_read_tokens": 0, "cost_usd": 0.0, "api_duration_ms": 0}

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
        """Stream not directly supported by CLI — return full response as single chunk."""
        result = await self.complete(request)
        chunk_id = f"chatcmpl-cli-{uuid.uuid4().hex[:8]}"

        yield ChatCompletionChunk(
            id=chunk_id, model=request.model,
            choices=[StreamChoice(delta=DeltaMessage(role="assistant"))],
        )

        content = result.choices[0].message.content if result.choices else ""
        yield ChatCompletionChunk(
            id=chunk_id, model=request.model,
            choices=[StreamChoice(delta=DeltaMessage(content=content))],
        )

        yield ChatCompletionChunk(
            id=chunk_id, model=request.model,
            choices=[StreamChoice(delta=DeltaMessage(), finish_reason="stop")],
            usage=result.usage,
        )

    async def _exec(self, args: list[str], timeout: float = 30) -> tuple[str, int]:
        """Execute CLI command and return (stdout, returncode)."""
        import sys
        cmd = [self._cli_path] + args
        if sys.platform == "win32":
            # Windows needs shell=True for .cmd files
            proc = await asyncio.create_subprocess_shell(
                " ".join(f'"{a}"' if " " in a else a for a in cmd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode("utf-8", errors="replace").strip(), proc.returncode or 0

    async def health_check(self) -> bool:
        """Check if Claude CLI is available and authenticated."""
        try:
            version, code = await self._exec(["--version"], timeout=10)
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
