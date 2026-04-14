"""Fallback chain logic for retrying failed requests with alternative models."""

from a1.common.logging import get_logger
from a1.providers.registry import provider_registry
from a1.proxy.request_models import ChatCompletionRequest
from a1.proxy.response_models import ChatCompletionResponse
from a1.routing.strategy import _get_provider_for

log = get_logger("routing.fallback")


async def complete_with_fallback(
    request: ChatCompletionRequest,
    primary_model: str,
    fallback_models: list[str],
) -> tuple[ChatCompletionResponse, str, str]:
    """Try primary model, then fallbacks. Returns (response, model_used, provider_used)."""
    all_models = [primary_model] + fallback_models

    last_error = None
    for model in all_models:
        provider_name = _get_provider_for(model)
        provider = provider_registry.get_provider(provider_name)

        if not provider or not provider_registry.is_healthy(provider_name):
            continue

        try:
            request.model = model
            response = await provider.complete(request)
            return response, model, provider_name
        except Exception as e:
            log.warning(f"Failed with {provider_name}/{model}: {e}")
            last_error = e
            continue

    raise last_error or RuntimeError("All providers failed")
