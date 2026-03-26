import uuid
from collections.abc import AsyncIterator

import httpx

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
from a1.common.logging import get_logger
from config.settings import settings

log = get_logger("providers.vertex")


class VertexProvider(LLMProvider):
    """Google Vertex AI provider using the OpenAI-compatible endpoint."""

    name = "vertex"

    def __init__(self):
        self.project_id = settings.vertex_project_id
        self.location = settings.vertex_location
        self._models = [
            ModelInfo("gemini-2.0-flash", "vertex", 1000000, 0.00015, 0.0006, True, True),
        ]
        # Use Vertex AI's OpenAI-compatible endpoint
        self.base_url = (
            f"https://{self.location}-aiplatform.googleapis.com/v1/projects/"
            f"{self.project_id}/locations/{self.location}/endpoints/openapi"
        )
        self.client = httpx.AsyncClient(timeout=120.0)

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        messages = [{"role": m.role, "content": m.content or ""} for m in request.messages]
        payload = {
            "model": request.model,
            "messages": messages,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        resp = await self.client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})
        return ChatCompletionResponse(
            model=request.model,
            choices=[Choice(message=ChoiceMessage(content=choice["message"]["content"]))],
            usage=Usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            provider=self.name,
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[ChatCompletionChunk]:
        # Simplified: non-streaming fallback for now
        response = await self.complete(request)
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        content = response.choices[0].message.content or ""

        yield ChatCompletionChunk(
            id=chunk_id, model=request.model,
            choices=[StreamChoice(delta=DeltaMessage(role="assistant"))],
        )
        yield ChatCompletionChunk(
            id=chunk_id, model=request.model,
            choices=[StreamChoice(delta=DeltaMessage(content=content))],
        )
        yield ChatCompletionChunk(
            id=chunk_id, model=request.model,
            choices=[StreamChoice(delta=DeltaMessage(), finish_reason="stop")],
        )

    async def health_check(self) -> bool:
        if not self.project_id:
            return False
        try:
            resp = await self.client.get(f"{self.base_url}/models")
            return resp.status_code == 200
        except Exception:
            return False

    def supports_model(self, model: str) -> bool:
        return any(m.name == model for m in self._models)

    def list_models(self) -> list[ModelInfo]:
        return self._models
