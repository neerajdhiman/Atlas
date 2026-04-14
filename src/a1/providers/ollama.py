"""Ollama provider with multi-server support.

Discovers and routes to models across multiple Ollama servers
(e.g., 10.0.0.9 for code models, 10.0.0.10 for QA/reasoning models).
"""

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

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
from config.settings import settings

log = get_logger("providers.ollama")


@dataclass
class OllamaServer:
    url: str
    name: str
    models: list[ModelInfo]
    healthy: bool = True


class OllamaProvider(LLMProvider):
    """Multi-server Ollama provider. Discovers models across all configured servers."""

    name = "ollama"

    def __init__(self):
        self._servers: list[OllamaServer] = []
        self._model_to_server: dict[str, OllamaServer] = {}
        self._models: list[ModelInfo] = []

    async def discover_models(self):
        """Discover models from all configured Ollama servers."""
        urls = list(settings.ollama_servers) if settings.ollama_servers else []
        # Always include the primary URL if not already in the list
        if settings.ollama_base_url and settings.ollama_base_url not in urls:
            urls.insert(0, settings.ollama_base_url)

        self._servers.clear()
        self._model_to_server.clear()
        self._models.clear()

        for url in urls:
            server = OllamaServer(url=url, name=url, models=[])
            try:
                async with httpx.AsyncClient(base_url=url, timeout=10.0) as client:
                    resp = await client.get("/api/tags")
                    resp.raise_for_status()
                    data = resp.json()

                    for m in data.get("models", []):
                        model_name = m["name"]
                        details = m.get("details", {})
                        model_info = ModelInfo(
                            name=model_name,
                            provider="ollama",
                            context_window=details.get("context_length", 4096),
                            cost_per_1k_input=0.0,
                            cost_per_1k_output=0.0,
                            supports_tools=True,
                            supports_streaming=True,
                        )
                        server.models.append(model_info)
                        self._models.append(model_info)
                        # Map model to its server (first server wins if duplicated)
                        if model_name not in self._model_to_server:
                            self._model_to_server[model_name] = server

                    server.healthy = True
                    log.info(
                        f"Ollama server {url}: discovered {len(server.models)} models "
                        f"— {[m.name for m in server.models]}"
                    )

            except Exception as e:
                server.healthy = False
                log.warning(f"Ollama server {url}: unreachable — {e}")

            self._servers.append(server)

        total = len(self._models)
        healthy = sum(1 for s in self._servers if s.healthy)
        log.info(f"Ollama: {total} models across {healthy}/{len(self._servers)} servers")

    def _get_client_for_model(self, model: str) -> tuple[httpx.AsyncClient, str]:
        """Get the HTTP client for the server that has this model."""
        server = self._model_to_server.get(model)
        if server:
            return httpx.AsyncClient(base_url=server.url, timeout=300.0), server.url

        # Model name "local" — use first healthy server
        for s in self._servers:
            if s.healthy and s.models:
                return httpx.AsyncClient(base_url=s.url, timeout=300.0), s.url

        # Fallback to primary
        return httpx.AsyncClient(
            base_url=settings.ollama_base_url, timeout=300.0
        ), settings.ollama_base_url

    def get_server_for_model(self, model: str) -> str:
        """Get the server URL for a model (for display/logging)."""
        server = self._model_to_server.get(model)
        return server.url if server else settings.ollama_base_url

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        model = request.model
        if model == "local" and self._models:
            model = self._models[0].name

        client, server_url = self._get_client_for_model(model)
        messages = [{"role": m.role, "content": m.content or ""} for m in request.messages]
        payload = {"model": model, "messages": messages, "stream": False}
        if request.temperature is not None:
            payload["options"] = {"temperature": request.temperature}

        async with client:
            resp = await client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        return ChatCompletionResponse(
            model=model,
            choices=[Choice(message=ChoiceMessage(content=data["message"]["content"]))],
            usage=Usage(
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            ),
            provider=self.name,
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[ChatCompletionChunk]:
        model = request.model
        if model == "local" and self._models:
            model = self._models[0].name

        client, server_url = self._get_client_for_model(model)
        messages = [{"role": m.role, "content": m.content or ""} for m in request.messages]
        payload = {"model": model, "messages": messages, "stream": True}
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        yield ChatCompletionChunk(
            id=chunk_id,
            model=model,
            choices=[StreamChoice(delta=DeltaMessage(role="assistant"))],
        )

        async with client:
            async with client.stream("POST", "/api/chat", json=payload) as resp:
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("done"):
                        # Final chunk with usage data from Ollama
                        yield ChatCompletionChunk(
                            id=chunk_id,
                            model=model,
                            choices=[StreamChoice(delta=DeltaMessage(), finish_reason="stop")],
                            usage=Usage(
                                prompt_tokens=data.get("prompt_eval_count", 0),
                                completion_tokens=data.get("eval_count", 0),
                                total_tokens=data.get("prompt_eval_count", 0)
                                + data.get("eval_count", 0),
                            ),
                        )
                        break
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield ChatCompletionChunk(
                            id=chunk_id,
                            model=model,
                            choices=[StreamChoice(delta=DeltaMessage(content=content))],
                        )

    async def health_check(self) -> bool:
        return any(s.healthy for s in self._servers)

    def supports_model(self, model: str) -> bool:
        if model == "local":
            return True
        return any(m.name == model for m in self._models)

    def list_models(self) -> list[ModelInfo]:
        return self._models

    def list_servers(self) -> list[dict]:
        """Return server status for the dashboard."""
        return [
            {
                "url": s.url,
                "name": s.name,
                "healthy": s.healthy,
                "models": [m.name for m in s.models],
                "model_count": len(s.models),
            }
            for s in self._servers
        ]
