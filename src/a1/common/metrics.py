"""Simple in-memory metrics for the dashboard. Can be replaced with Prometheus later."""

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Metrics:
    request_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0
    total_cost_usd: float = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    provider_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    model_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    task_type_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _start_time: float = field(default_factory=time.time)

    def record_request(
        self, provider: str, model: str, task_type: str | None,
        latency_ms: int, cost_usd: float, prompt_tokens: int,
        completion_tokens: int, error: bool = False,
    ):
        self.request_count += 1
        self.total_latency_ms += latency_ms
        self.total_cost_usd += cost_usd
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.provider_counts[provider] += 1
        self.model_counts[model] += 1
        if task_type:
            self.task_type_counts[task_type] += 1
        if error:
            self.error_count += 1

    def snapshot(self) -> dict:
        uptime = time.time() - self._start_time
        return {
            "uptime_seconds": round(uptime, 1),
            "request_count": self.request_count,
            "error_count": self.error_count,
            "avg_latency_ms": round(self.total_latency_ms / max(self.request_count, 1), 1),
            "total_cost_usd": round(self.total_cost_usd, 4),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "requests_per_minute": round(self.request_count / max(uptime / 60, 1), 2),
            "provider_counts": dict(self.provider_counts),
            "model_counts": dict(self.model_counts),
            "task_type_counts": dict(self.task_type_counts),
        }


# Singleton
metrics = Metrics()
