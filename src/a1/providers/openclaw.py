"""OpenClaw provider — connects to OpenClaw gateway for chat history import
and proxied model access via WebSocket/REST API.

OpenClaw acts as a unified AI gateway that can proxy to multiple LLM providers.
We integrate it as both a provider (for routing requests through it) and as a
chat history source (for training data collection).
"""

import json
import uuid
from collections.abc import AsyncIterator

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

log = get_logger("providers.openclaw")


class OpenClawProvider(LLMProvider):
    """OpenClaw gateway provider. Routes requests through the OpenClaw gateway
    and imports chat history for training pipeline."""

    name = "openclaw"

    def __init__(self):
        self._base_url = settings.openclaw_url
        self._token = settings.openclaw_token
        self._models: list[ModelInfo] = []
        self._healthy = False

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
            headers["X-Gateway-Token"] = self._token
        return headers

    async def discover_models(self):
        """Discover models available through OpenClaw gateway."""
        self._models.clear()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Try OpenClaw's Ollama proxy endpoint
                resp = await client.get(
                    f"{self._base_url}/ollama/api/tags",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for m in data.get("models", []):
                        model_name = m["name"]
                        details = m.get("details", {})
                        self._models.append(ModelInfo(
                            name=f"openclaw/{model_name}",
                            provider="openclaw",
                            context_window=details.get("context_length", 4096),
                            cost_per_1k_input=0.0,
                            cost_per_1k_output=0.0,
                            supports_tools=True,
                            supports_streaming=True,
                        ))

            # Always add the Alpheric-1 virtual model
            if not any(m.name == "alpheric-1" for m in self._models):
                self._models.append(ModelInfo(
                    name="alpheric-1",
                    provider="openclaw",
                    context_window=128000,
                    cost_per_1k_input=0.0,
                    cost_per_1k_output=0.0,
                    supports_tools=True,
                    supports_streaming=True,
                ))

            self._healthy = True
            log.info(f"OpenClaw: discovered {len(self._models)} models at {self._base_url}")

        except Exception as e:
            self._healthy = False
            log.warning(f"OpenClaw at {self._base_url}: unreachable — {e}")

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        model = request.model
        # Route alpheric-1 to best available local model
        if model == "alpheric-1":
            model = self._resolve_alpheric_model()

        # Strip openclaw/ prefix for actual API call
        actual_model = model.removeprefix("openclaw/")

        messages = [{"role": m.role, "content": m.content or ""} for m in request.messages]
        payload = {
            "model": actual_model,
            "messages": messages,
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        async with httpx.AsyncClient(timeout=300.0) as client:
            # Try OpenAI-compatible endpoint first
            resp = await client.post(
                f"{self._base_url}/v1/chat/completions",
                json=payload,
                headers=self._headers(),
            )

            if resp.status_code == 404:
                # Fallback to Ollama chat endpoint
                ollama_payload = {
                    "model": actual_model,
                    "messages": messages,
                    "stream": False,
                }
                if request.temperature is not None:
                    ollama_payload["options"] = {"temperature": request.temperature}

                resp = await client.post(
                    f"{self._base_url}/ollama/api/chat",
                    json=ollama_payload,
                    headers=self._headers(),
                )
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

            resp.raise_for_status()
            data = resp.json()

            # Parse OpenAI-compatible response
            choice = data.get("choices", [{}])[0]
            usage_data = data.get("usage", {})
            return ChatCompletionResponse(
                model=request.model,
                choices=[Choice(message=ChoiceMessage(
                    content=choice.get("message", {}).get("content", ""),
                ))],
                usage=Usage(
                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                    completion_tokens=usage_data.get("completion_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                ),
                provider=self.name,
            )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[ChatCompletionChunk]:
        model = request.model
        if model == "alpheric-1":
            model = self._resolve_alpheric_model()

        actual_model = model.removeprefix("openclaw/")
        messages = [{"role": m.role, "content": m.content or ""} for m in request.messages]
        payload = {
            "model": actual_model,
            "messages": messages,
            "stream": True,
        }
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        yield ChatCompletionChunk(
            id=chunk_id, model=request.model,
            choices=[StreamChoice(delta=DeltaMessage(role="assistant"))],
        )

        async with httpx.AsyncClient(timeout=300.0) as client:
            # Use Ollama streaming endpoint through OpenClaw
            ollama_payload = {
                "model": actual_model,
                "messages": messages,
                "stream": True,
            }
            async with client.stream(
                "POST",
                f"{self._base_url}/ollama/api/chat",
                json=ollama_payload,
                headers=self._headers(),
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if data.get("done"):
                        yield ChatCompletionChunk(
                            id=chunk_id, model=request.model,
                            choices=[StreamChoice(delta=DeltaMessage(), finish_reason="stop")],
                            usage=Usage(
                                prompt_tokens=data.get("prompt_eval_count", 0),
                                completion_tokens=data.get("eval_count", 0),
                                total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                            ),
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
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._base_url}/health",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self._healthy = data.get("ok", False) or data.get("status") == "live"
                    return self._healthy
        except Exception as e:
            log.warning(f"OpenClaw health check failed: {e}")
        self._healthy = False
        return False

    def supports_model(self, model: str) -> bool:
        if model == "alpheric-1":
            return True
        return any(m.name == model for m in self._models)

    def list_models(self) -> list[ModelInfo]:
        return self._models

    def _resolve_alpheric_model(self) -> str:
        """Resolve alpheric-1 to the best available model."""
        # Priority: llama3.2 > deepseek-coder > mistral > first available
        preferred = ["llama3.2:latest", "deepseek-coder:6.7b", "mistral:7b"]
        for pref in preferred:
            if any(pref in m.name for m in self._models):
                return pref
        if self._models:
            return self._models[0].name.removeprefix("openclaw/")
        return "llama3.2:latest"

    # --- Chat History Import ---
    async def fetch_chat_history(self, limit: int = 1000) -> list[dict]:
        """Fetch chat history from OpenClaw for training data collection.
        Returns list of conversations in OpenAI format."""
        conversations = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Try OpenClaw's conversation export endpoints
                for endpoint in [
                    "/v1/conversations",
                    "/api/v1/chats",
                    "/api/conversations",
                ]:
                    try:
                        resp = await client.get(
                            f"{self._base_url}{endpoint}",
                            headers=self._headers(),
                            params={"limit": limit},
                        )
                        if resp.status_code == 200:
                            ct = resp.headers.get("content-type", "")
                            if "json" in ct:
                                data = resp.json()
                                if isinstance(data, list):
                                    conversations = data
                                elif isinstance(data, dict) and "data" in data:
                                    conversations = data["data"]
                                break
                    except Exception:
                        continue

            log.info(f"OpenClaw: fetched {len(conversations)} conversations")
        except Exception as e:
            log.warning(f"OpenClaw chat history fetch failed: {e}")

        return conversations

    def get_status(self) -> dict:
        """Return OpenClaw status for dashboard."""
        return {
            "url": self._base_url,
            "healthy": self._healthy,
            "models": [m.name for m in self._models],
            "model_count": len(self._models),
            "has_token": bool(self._token),
        }
