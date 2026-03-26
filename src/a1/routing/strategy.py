"""Routing strategy: combines classifier + scorer + exploration."""

import random

from a1.common.logging import get_logger
from a1.providers.registry import provider_registry
from a1.routing.scorer import get_cold_start_model
from config.settings import settings

log = get_logger("routing.strategy")


# Model -> provider mapping (derived from providers.yaml)
MODEL_PROVIDER_MAP = {
    "claude-sonnet-4-20250514": "anthropic",
    "claude-haiku-4-5-20251001": "anthropic",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "o3-mini": "openai",
    "gemini-2.0-flash": "vertex",
}


def _get_provider_for(model: str) -> str:
    """Resolve provider name for a model."""
    if model in MODEL_PROVIDER_MAP:
        return MODEL_PROVIDER_MAP[model]
    # Check if Ollama has it
    ollama = provider_registry.get_provider("ollama")
    if ollama and ollama.supports_model(model):
        return "ollama"
    return "openai"  # fallback


async def select_model(task_type: str, strategy: str) -> tuple[str, str]:
    """Select the best model for a task type and strategy.
    Returns (model_name, provider_name).
    """
    # TODO: Once enough data in model_performance table, use learned scorer.
    # For now, use cold-start defaults from routing_policy.yaml.

    model, fallbacks = get_cold_start_model(task_type)

    # Epsilon-greedy exploration: with probability epsilon, pick a random alternative
    if random.random() < settings.exploration_rate and fallbacks:
        model = random.choice(fallbacks)
        log.info(f"Exploration: selected {model} instead of default for {task_type}")

    provider_name = _get_provider_for(model)

    # Check provider health; fall back if unhealthy
    if not provider_registry.is_healthy(provider_name):
        log.warning(f"Provider {provider_name} unhealthy, trying fallbacks")
        for fb_model in fallbacks:
            fb_provider = _get_provider_for(fb_model)
            if provider_registry.is_healthy(fb_provider):
                return fb_model, fb_provider

        # Last resort: any healthy provider
        for name, provider in provider_registry.healthy_providers.items():
            models = provider.list_models()
            if models:
                return models[0].name, name

        # Absolute fallback: try ollama
        return "local", "ollama"

    return model, provider_name
