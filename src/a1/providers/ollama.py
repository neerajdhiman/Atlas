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

log = get_logger("providers.ollama")


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)
        self._models: list[ModelInfo] = []

    async def discover_models(self):
        """Fetch available models from Ollama API."""
        try:
            resp = await self.client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            self._models = [
                ModelInfo(
                    name=m["name"],
                    provider="ollama",
                    context_window=m.get("details", {}).get("context_length", 4096),
                    cost_per_1k_input=0.0,  # local = free
                    cost_per_1k_output=0.0,
                    supports_tools=True,
                    supports_streaming=True,
                )
                for m in data.get("models", [])
            ]
            log.info(f"Discovered {len(self._models)} Ollama models")
        except Exception as e:
            log.warning(f"Could not discover Ollama models: {e}")
            self._models = []

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        messages = [{"role": m.role, "content": m.content or ""} for m in request.messages]
        payload = {
            "model": request.model,
            "messages": messages,
            "stream": False,
        }
        if request.temperature is not None:
            payload["options"] = {"temperature": request.temperature}

        resp = await self.client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        return ChatCompletionResponse(
            model=request.model,
            choices=[Choice(message=ChoiceMessage(content=data["message"]["content"]))],
            usage=Usage(
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            ),
            provider=self.name,
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[ChatCompletionChunk]:
        messages = [{"role": m.role, "content": m.content or ""} for m in request.messages]
        payload = {
            "model": request.model,
            "messages": messages,
            "stream": True,
        }
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        # First chunk with role
        yield ChatCompletionChunk(
            id=chunk_id, model=request.model,
            choices=[StreamChoice(delta=DeltaMessage(role="assistant"))],
        )

        async with self.client.stream("POST", "/api/chat", json=payload) as resp:
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                import json
                data = json.loads(line)
                if data.get("done"):
                    yield ChatCompletionChunk(
                        id=chunk_id, model=request.model,
                        choices=[StreamChoice(delta=DeltaMessage(), finish_reason="stop")],
                    )
                    break
                content = data.get("message", {}).get("content", "")
                if content:
                    yield ChatCompletionChunk(
                        id=chunk_id, model=request.model,
                        choices=[StreamChoice(delta=DeltaMessage(content=content))],
                    )

    async def health_check(self) -> bool:
        try:
            resp = await self.client.get("/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    def supports_model(self, model: str) -> bool:
        return any(m.name == model for m in self._models) or model == "local"

    def list_models(self) -> list[ModelInfo]:
        return self._models
