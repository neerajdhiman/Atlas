import asyncio

import yaml

from a1.common.logging import get_logger
from a1.providers.base import LLMProvider, ModelInfo
from config.settings import settings

log = get_logger("providers.registry")


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

        # Initial health check
        await self.refresh_health()

    async def _register_litellm_providers(self):
        """Register LiteLLM-backed providers (default)."""
        from a1.providers.litellm_provider import LiteLLMProvider

        if settings.anthropic_api_key:
            models = _load_provider_models("anthropic")
            self._providers["anthropic"] = LiteLLMProvider(
                name="anthropic", models=models, api_key=settings.anthropic_api_key,
            )
            log.info(f"Registered Anthropic via LiteLLM ({len(models)} models)")

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
        for name, task in tasks.items():
            try:
                self._health[name] = await task
            except Exception:
                self._health[name] = False
            status = "healthy" if self._health[name] else "unhealthy"
            log.info(f"Provider {name}: {status}")

    def get_provider(self, name: str) -> LLMProvider | None:
        return self._providers.get(name)

    def get_provider_for_model(self, model: str) -> LLMProvider | None:
        """Find which provider serves this model."""
        for provider in self._providers.values():
            if provider.supports_model(model):
                return provider
        return None

    def is_healthy(self, name: str) -> bool:
        return self._health.get(name, False)

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
