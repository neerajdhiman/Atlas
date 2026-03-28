import asyncio
import time

import yaml

from a1.common.logging import get_logger
from a1.providers.base import LLMProvider, ModelInfo
from config.settings import settings

log = get_logger("providers.registry")


async def _get_claude_cli_key() -> str | None:
    """Try to extract Anthropic API key from Claude CLI credentials.

    Reads ~/.claude/.credentials.json for OAuth token.
    If the token is expired, attempts to refresh by invoking the CLI asynchronously.
    """
    import json
    import time
    from pathlib import Path

    cred_path = Path.home() / ".claude" / ".credentials.json"
    if not cred_path.exists():
        return None

    try:
        creds = json.loads(cred_path.read_text())
        oauth = creds.get("claudeAiOauth", {})
        token = oauth.get("accessToken")
        expires_at = oauth.get("expiresAt", 0)

        if not token:
            return None

        # Check if expired
        now_ms = int(time.time() * 1000)
        if now_ms > expires_at:
            log.warning("Claude CLI OAuth token expired, attempting refresh via CLI...")
            try:
                proc = await asyncio.create_subprocess_exec(
                    "claude", "-p", "test", "--max-turns", "1",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=30)
                # Re-read credentials after CLI refresh
                creds = json.loads(cred_path.read_text())
                oauth = creds.get("claudeAiOauth", {})
                token = oauth.get("accessToken")
                new_expires = oauth.get("expiresAt", 0)
                if new_expires > now_ms:
                    log.info("Claude CLI OAuth token refreshed successfully")
                else:
                    log.warning("Claude CLI token still expired after refresh attempt")
            except Exception as e:
                log.warning(f"Failed to refresh Claude CLI token: {e}")

        if token:
            log.info(f"Using Claude CLI OAuth token (expires: {expires_at})")
            return token

    except Exception as e:
        log.warning(f"Failed to read Claude CLI credentials: {e}")

    return None


def _load_provider_models(provider_name: str) -> list[ModelInfo]:
    """Load model definitions from config/providers.yaml."""
    try:
        with open("config/providers.yaml") as f:
            config = yaml.safe_load(f)
        provider_config = config.get("providers", {}).get(provider_name, {})
        models = []
        for m in provider_config.get("models", []):
            models.append(ModelInfo(
                name=m["name"],
                provider=provider_name,
                context_window=m.get("context_window", 4096),
                cost_per_1k_input=m.get("cost_per_1k_input", 0.0),
                cost_per_1k_output=m.get("cost_per_1k_output", 0.0),
                supports_tools=m.get("supports_tools", True),
                supports_streaming=m.get("supports_streaming", True),
            ))
        return models
    except Exception as e:
        log.warning(f"Could not load models for {provider_name}: {e}")
        return []


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}
        self._health: dict[str, bool] = {}
        self._unhealthy_since: dict[str, float | None] = {}  # circuit breaker: epoch seconds when provider first went unhealthy

    async def initialize(self):
        """Register all configured providers and check health."""
        if settings.use_litellm:
            await self._register_litellm_providers()
        else:
            await self._register_native_providers()

        # Ollama is always registered (local, custom discovery)
        from a1.providers.ollama import OllamaProvider
        ollama = OllamaProvider()
        await ollama.discover_models()
        self._providers["ollama"] = ollama
        log.info("Registered Ollama provider")

        # Claude CLI proxy (uses local claude command for auth)
        try:
            from a1.providers.claude_cli import ClaudeCLIProvider
            claude_cli = ClaudeCLIProvider()
            cli_healthy = await claude_cli.health_check()
            if cli_healthy:
                self._providers["claude-cli"] = claude_cli
                log.info(f"Registered Claude CLI provider ({len(claude_cli.list_models())} models)")
            else:
                log.info("Claude CLI not available — skipping")
        except Exception as e:
            log.warning(f"Failed to register Claude CLI provider: {e}")

        # Initial health check
        await self.refresh_health()

    async def _register_litellm_providers(self):
        """Register LiteLLM-backed providers (default)."""
        from a1.providers.litellm_provider import LiteLLMProvider

        if settings.openai_api_key:
            models = _load_provider_models("openai")
            self._providers["openai"] = LiteLLMProvider(
                name="openai", models=models, api_key=settings.openai_api_key,
            )
            log.info(f"Registered OpenAI via LiteLLM ({len(models)} models)")

        if settings.vertex_project_id:
            models = _load_provider_models("vertex")
            self._providers["vertex"] = LiteLLMProvider(
                name="vertex", models=models,
            )
            log.info(f"Registered Vertex via LiteLLM ({len(models)} models)")

    async def _register_native_providers(self):
        """Register native provider implementations (legacy fallback)."""
        if settings.anthropic_api_key:
            from a1.providers.anthropic import AnthropicProvider
            self._providers["anthropic"] = AnthropicProvider()
            log.info("Registered Anthropic (native)")

        if settings.openai_api_key:
            from a1.providers.openai import OpenAIProvider
            self._providers["openai"] = OpenAIProvider()
            log.info("Registered OpenAI (native)")

        if settings.vertex_project_id:
            from a1.providers.vertex import VertexProvider
            self._providers["vertex"] = VertexProvider()
            log.info("Registered Vertex (native)")

        # Initial health check
        await self.refresh_health()

    async def refresh_health(self):
        """Check health of all providers concurrently."""
        tasks = {
            name: asyncio.create_task(provider.health_check())
            for name, provider in self._providers.items()
        }
        now = time.time()
        for name, task in tasks.items():
            was_healthy = self._health.get(name, True)
            try:
                self._health[name] = await task
            except Exception:
                self._health[name] = False
            if self._health[name]:
                self._unhealthy_since[name] = None  # recovered
            elif was_healthy:
                self._unhealthy_since[name] = now  # first failure
            status = "healthy" if self._health[name] else "unhealthy"
            log.info(f"Provider {name}: {status}")

    def get_provider(self, name: str) -> LLMProvider | None:
        return self._providers.get(name)

    def get_provider_for_model(self, model: str) -> LLMProvider | None:
        """Find which provider serves this model. Prefers healthy providers."""
        # First pass: healthy providers only
        for name, provider in self._providers.items():
            if self._health.get(name, False) and provider.supports_model(model):
                return provider
        # Second pass: any provider (may be unhealthy but registered)
        for provider in self._providers.values():
            if provider.supports_model(model):
                return provider
        return None

    def is_healthy(self, name: str) -> bool:
        return self._health.get(name, False)

    def get_unhealthy_duration(self, name: str) -> float | None:
        """Seconds since the provider first went unhealthy, or None if healthy/unknown."""
        since = self._unhealthy_since.get(name)
        if since is None:
            return None
        return time.time() - since

    def list_all_models(self) -> list[ModelInfo]:
        models = []
        for name, provider in self._providers.items():
            if self._health.get(name, False):
                models.extend(provider.list_models())
        return models

    def list_providers(self) -> list[dict]:
        return [
            {
                "name": name,
                "healthy": self._health.get(name, False),
                "models": [m.name for m in provider.list_models()],
            }
            for name, provider in self._providers.items()
        ]

    @property
    def healthy_providers(self) -> dict[str, LLMProvider]:
        return {
            name: p for name, p in self._providers.items()
            if self._health.get(name, False)
        }


# Singleton
provider_registry = ProviderRegistry()
