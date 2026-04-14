"""In-memory metrics with local/external usage split, latency percentiles,
time-series tracking, and request history for enterprise dashboard."""

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from a1.common.tz import now_ist


@dataclass
class RequestRecord:
    """Single request record for live feed and history."""

    timestamp: str
    provider: str
    model: str
    task_type: str | None
    latency_ms: int
    cost_usd: float
    prompt_tokens: int
    completion_tokens: int
    is_local: bool
    error: bool


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
    _latency_samples: dict[str, deque] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=1000))
    )
    _start_time: float = field(default_factory=time.time)

    # Time-series: token usage per minute (last 24h = 1440 buckets)
    _token_timeseries: deque = field(default_factory=lambda: deque(maxlen=1440))
    _cost_timeseries: deque = field(default_factory=lambda: deque(maxlen=1440))

    # Recent request history (last 200 requests for live feed)
    _request_history: deque = field(default_factory=lambda: deque(maxlen=200))

    # Hourly request counts for heatmap (24 hours x 7 days)
    _hourly_heatmap: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Model-level stats for leaderboard
    _model_stats: dict[str, dict] = field(
        default_factory=lambda: defaultdict(
            lambda: {
                "requests": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_latency": 0,
                "cost": 0.0,
                "errors": 0,
            }
        )
    )

    # Reference cost for savings (gpt-4o-mini)
    _ref_cost_input: float = 0.00015
    _ref_cost_output: float = 0.0006

    def record_request(
        self,
        provider: str,
        model: str,
        task_type: str | None,
        latency_ms: int,
        cost_usd: float,
        prompt_tokens: int,
        completion_tokens: int,
        error: bool = False,
        is_local: bool = False,
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
            equiv_cost = (
                prompt_tokens / 1000 * self._ref_cost_input
                + completion_tokens / 1000 * self._ref_cost_output
            )
            self.savings_usd += equiv_cost
        else:
            self.external_request_count += 1
            self.external_prompt_tokens += prompt_tokens
            self.external_completion_tokens += completion_tokens
            self.external_cost_usd += cost_usd

        # Track latency for percentiles
        self._latency_samples[model].append(latency_ms)

        # Time-series point
        now = now_ist()
        ts_key = now.strftime("%Y-%m-%dT%H:%M")
        self._token_timeseries.append(
            {
                "time": ts_key,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "is_local": is_local,
            }
        )
        self._cost_timeseries.append(
            {
                "time": ts_key,
                "cost": cost_usd,
                "provider": provider,
            }
        )

        # Hourly heatmap (day_of_week:hour)
        heatmap_key = f"{now.weekday()}:{now.hour}"
        self._hourly_heatmap[heatmap_key] += 1

        # Model-level stats
        ms = self._model_stats[model]
        ms["requests"] += 1
        ms["prompt_tokens"] += prompt_tokens
        ms["completion_tokens"] += completion_tokens
        ms["total_latency"] += latency_ms
        ms["cost"] += cost_usd
        if error:
            ms["errors"] += 1

        # Request history for live feed
        self._request_history.append(
            RequestRecord(
                timestamp=now.isoformat(),
                provider=provider,
                model=model,
                task_type=task_type,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                is_local=is_local,
                error=error,
            )
        )

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

    def token_timeseries(self) -> list[dict]:
        """Aggregate token usage per minute for time-series charts."""
        from collections import OrderedDict

        buckets: dict[str, dict] = OrderedDict()
        for point in self._token_timeseries:
            t = point["time"]
            if t not in buckets:
                buckets[t] = {"time": t, "prompt": 0, "completion": 0, "local": 0, "external": 0}
            buckets[t]["prompt"] += point["prompt_tokens"]
            buckets[t]["completion"] += point["completion_tokens"]
            if point["is_local"]:
                buckets[t]["local"] += point["prompt_tokens"] + point["completion_tokens"]
            else:
                buckets[t]["external"] += point["prompt_tokens"] + point["completion_tokens"]
        return list(buckets.values())

    def cost_timeseries(self) -> list[dict]:
        """Aggregate cost per minute for cost trend chart."""
        from collections import OrderedDict

        buckets: dict[str, dict] = OrderedDict()
        for point in self._cost_timeseries:
            t = point["time"]
            if t not in buckets:
                buckets[t] = {"time": t, "cost": 0.0}
            buckets[t]["cost"] += point["cost"]
        return list(buckets.values())

    def request_heatmap(self) -> list[dict]:
        """Request volume by day-of-week and hour for heatmap."""
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        result = []
        for day_idx, day_name in enumerate(days):
            for hour in range(24):
                key = f"{day_idx}:{hour}"
                result.append(
                    {
                        "day": day_name,
                        "hour": hour,
                        "count": self._hourly_heatmap.get(key, 0),
                    }
                )
        return result

    def model_leaderboard(self) -> list[dict]:
        """Model performance leaderboard with detailed stats."""
        result = []
        for model, stats in self._model_stats.items():
            if stats["requests"] == 0:
                continue
            percs = self.get_latency_percentiles(model)
            result.append(
                {
                    "model": model,
                    "requests": stats["requests"],
                    "prompt_tokens": stats["prompt_tokens"],
                    "completion_tokens": stats["completion_tokens"],
                    "total_tokens": stats["prompt_tokens"] + stats["completion_tokens"],
                    "avg_latency_ms": round(stats["total_latency"] / stats["requests"], 1),
                    "p50_latency": percs["p50"],
                    "p95_latency": percs["p95"],
                    "cost_usd": round(stats["cost"], 6),
                    "errors": stats["errors"],
                    "error_rate": round(stats["errors"] / stats["requests"] * 100, 1),
                    "avg_tokens_per_request": round(
                        (stats["prompt_tokens"] + stats["completion_tokens"]) / stats["requests"], 1
                    ),
                }
            )
        return sorted(result, key=lambda x: x["requests"], reverse=True)

    def recent_requests(self, limit: int = 50) -> list[dict]:
        """Get recent request records for live feed."""
        records = list(self._request_history)[-limit:]
        records.reverse()
        return [
            {
                "timestamp": r.timestamp,
                "provider": r.provider,
                "model": r.model,
                "task_type": r.task_type,
                "latency_ms": r.latency_ms,
                "cost_usd": r.cost_usd,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "is_local": r.is_local,
                "error": r.error,
            }
            for r in records
        ]


# Singleton
metrics = Metrics()
