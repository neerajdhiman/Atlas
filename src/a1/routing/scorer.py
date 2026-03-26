"""Model performance scorer — picks the best model for a task type based on historical data."""

from dataclasses import dataclass

import yaml

from a1.common.logging import get_logger

log = get_logger("routing.scorer")


@dataclass
class ModelCandidate:
    provider: str
    model: str
    avg_quality: float
    avg_latency_ms: float
    avg_cost_usd: float
    sample_count: int


# Cold-start defaults from routing policy
_cold_start_defaults: dict | None = None


def _load_cold_start() -> dict:
    global _cold_start_defaults
    if _cold_start_defaults is None:
        try:
            with open("config/routing_policy.yaml") as f:
                _cold_start_defaults = yaml.safe_load(f)
        except Exception:
            _cold_start_defaults = {"task_defaults": {}}
    return _cold_start_defaults


def get_cold_start_model(task_type: str) -> tuple[str, list[str]]:
    """Get default model and fallbacks for a task type (no performance data yet)."""
    policy = _load_cold_start()
    defaults = policy.get("task_defaults", {})
    task_config = defaults.get(task_type, defaults.get("general", {}))
    model = task_config.get("model", "gpt-4o-mini")
    fallbacks = task_config.get("fallback", [])
    return model, fallbacks


def score_candidates(
    candidates: list[ModelCandidate], strategy: str
) -> list[ModelCandidate]:
    """Rank candidates by the given strategy."""
    if strategy == "best_quality":
        return sorted(candidates, key=lambda c: c.avg_quality, reverse=True)
    elif strategy == "lowest_cost":
        return sorted(candidates, key=lambda c: c.avg_cost_usd)
    elif strategy == "lowest_latency":
        return sorted(candidates, key=lambda c: c.avg_latency_ms)
    # Default: quality
    return sorted(candidates, key=lambda c: c.avg_quality, reverse=True)
