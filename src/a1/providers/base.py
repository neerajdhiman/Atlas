from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from a1.proxy.request_models import ChatCompletionRequest
from a1.proxy.response_models import ChatCompletionChunk, ChatCompletionResponse


@dataclass
class ModelInfo:
    name: str
    provider: str
    context_window: int
    cost_per_1k_input: float
    cost_per_1k_output: float
    supports_tools: bool
    supports_streaming: bool
    # Capability flags
    supports_vision: bool = False
    supports_computer_use: bool = False
    max_output_tokens: int = 4096
    # Classification
    tier: str = "standard"  # "fast" | "standard" | "frontier"
    latency_class: str = "normal"  # "realtime" | "normal" | "batch"


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Non-streaming completion."""
        ...

    @abstractmethod
    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[ChatCompletionChunk]:
        """Streaming completion via SSE chunks."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is reachable."""
        ...

    @abstractmethod
    def supports_model(self, model: str) -> bool:
        """Does this provider serve this model?"""
        ...

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """List all models this provider serves."""
        ...

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """Estimate cost in USD."""
        for m in self.list_models():
            if m.name == model:
                return (
                    prompt_tokens / 1000 * m.cost_per_1k_input
                    + completion_tokens / 1000 * m.cost_per_1k_output
                )
        return 0.0
