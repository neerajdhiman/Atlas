"""In-memory metrics with local/external usage split and latency percentiles."""

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class Metrics:
    request_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0
    total_cost_usd: float = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0

    # Local vs External split
    local_request_count: int = 0
    local_prompt_tokens: int = 0
    local_completion_tokens: int = 0
    external_request_count: int = 0
    external_prompt_tokens: int = 0
    external_completion_tokens: int = 0
    external_cost_usd: float = 0
    savings_usd: float = 0  # what local requests would have cost externally

    provider_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    model_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    task_type_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    error_counts_by_provider: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Latency samples per model for percentile calculation (ring buffer)
    _latency_samples: dict[str, deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=1000)))
    _start_time: float = field(default_factory=time.time)

    # Reference cost for savings (gpt-4o-mini)
    _ref_cost_input: float = 0.00015
    _ref_cost_output: float = 0.0006

    def record_request(
        self, provider: str, model: str, task_type: str | None,
        latency_ms: int, cost_usd: float, prompt_tokens: int,
        completion_tokens: int, error: bool = False, is_local: bool = False,
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
            self.error_counts_by_provider[provider] += 1

        # Local/external split
        if is_local:
            self.local_request_count += 1
            self.local_prompt_tokens += prompt_tokens
            self.local_completion_tokens += completion_tokens
            # Calculate savings
            equiv_cost = (prompt_tokens / 1000 * self._ref_cost_input +
                         completion_tokens / 1000 * self._ref_cost_output)
            self.savings_usd += equiv_cost
        else:
            self.external_request_count += 1
            self.external_prompt_tokens += prompt_tokens
            self.external_completion_tokens += completion_tokens
            self.external_cost_usd += cost_usd

        # Track latency for percentiles
        self._latency_samples[model].append(latency_ms)

    def get_latency_percentiles(self, model: str) -> dict:
        samples = sorted(self._latency_samples.get(model, []))
        if not samples:
            return {"p50": 0, "p95": 0, "p99": 0, "avg": 0}
        n = len(samples)
        return {
            "p50": samples[int(n * 0.5)],
            "p95": samples[int(n * 0.95)] if n > 1 else samples[-1],
            "p99": samples[int(n * 0.99)] if n > 1 else samples[-1],
            "avg": round(sum(samples) / n, 1),
        }

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
            # Local vs External
            "local": {
                "request_count": self.local_request_count,
                "prompt_tokens": self.local_prompt_tokens,
                "completion_tokens": self.local_completion_tokens,
                "total_tokens": self.local_prompt_tokens + self.local_completion_tokens,
            },
            "external": {
                "request_count": self.external_request_count,
                "prompt_tokens": self.external_prompt_tokens,
                "completion_tokens": self.external_completion_tokens,
                "total_tokens": self.external_prompt_tokens + self.external_completion_tokens,
                "cost_usd": round(self.external_cost_usd, 4),
            },
            "savings_usd": round(self.savings_usd, 4),
            "error_counts_by_provider": dict(self.error_counts_by_provider),
        }


# Singleton
metrics = Metrics()
