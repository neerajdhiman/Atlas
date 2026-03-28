"""Smoke tests: all 3 proxy endpoints return 200 (mocked providers)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

def _mock_completion_response():
    """Return a minimal ChatCompletionResponse mock."""
    from a1.proxy.response_models import ChatCompletionResponse, Choice, ChoiceMessage, Usage
    return ChatCompletionResponse(
        id="chatcmpl-test",
        model="test-model",
        choices=[Choice(index=0, message=ChoiceMessage(role="assistant", content="Hello!"),
                        finish_reason="stop")],
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        provider="mock",
    )


def _mock_provider():
    provider = MagicMock()
    provider.name = "mock"
    provider.estimate_cost.return_value = 0.0
    provider.complete = AsyncMock(return_value=_mock_completion_response())
    provider.stream = MagicMock(return_value=iter([]))
    provider.list_models.return_value = []
    return provider


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """TestClient with mocked providers, DB, and auth."""
    mock_provider = _mock_provider()
    mock_registry = MagicMock()
    mock_registry.get_provider.return_value = mock_provider
    mock_registry.get_provider_for_model.return_value = mock_provider
    mock_registry.healthy_providers = {"mock": mock_provider}
    mock_registry.list_all_models.return_value = []

    async def mock_get_db():
        yield MagicMock()

    async def mock_select_model(task_type, strategy):
        return "test-model", "mock"

    with (
        patch("a1.proxy.openai_router.provider_registry", mock_registry),
        patch("a1.proxy.responses_router.provider_registry", mock_registry),
        patch("a1.proxy.atlas_router.provider_registry", mock_registry),
        patch("a1.proxy.openai_router.select_model", mock_select_model),
        patch("a1.proxy.responses_router.select_model", mock_select_model),
        patch("a1.proxy.atlas_router.select_model", mock_select_model),
        patch("a1.proxy.openai_router.verify_api_key", return_value="dev"),
        patch("a1.proxy.responses_router.verify_api_key", return_value="dev"),
        patch("a1.proxy.atlas_router.verify_api_key", return_value="dev"),
        patch("a1.proxy.openai_router.get_db", mock_get_db),
        patch("a1.proxy.responses_router.get_db", mock_get_db),
        patch("a1.proxy.pipeline.settings") as mock_settings,
        patch("config.settings.settings") as _,
    ):
        mock_settings.session_enabled = False
        mock_settings.pii_masking_enabled = False
        mock_settings.distillation_enabled = False
        mock_settings.distillation_min_samples = 100

        from a1.app import create_app
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

def test_chat_completions_returns_200(client):
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "Hello"}]},
        headers={"Authorization": "Bearer dev"},
    )
    assert resp.status_code == 200


def test_responses_api_returns_200(client):
    resp = client.post(
        "/v1/responses",
        json={"model": "auto", "input": "Hello there"},
        headers={"Authorization": "Bearer dev"},
    )
    assert resp.status_code == 200


def test_atlas_endpoint_returns_200(client):
    resp = client.post(
        "/atlas",
        json={"input": "Explain neural networks briefly"},
        headers={"Authorization": "Bearer dev"},
    )
    assert resp.status_code == 200


def test_list_models_returns_200(client):
    resp = client.get(
        "/v1/models",
        headers={"Authorization": "Bearer dev"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data


def test_atlas_models_returns_200(client):
    resp = client.get("/atlas/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["family"] == "Atlas"
    assert len(data["models"]) == 7


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
