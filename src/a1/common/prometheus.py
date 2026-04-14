"""Prometheus-compatible /metrics endpoint.

Exports key Atlas metrics in Prometheus text format from the in-memory
metrics singleton. No external prometheus_client dependency needed.
"""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from a1.common.metrics import metrics
from a1.providers.registry import provider_registry

router = APIRouter(tags=["observability"])


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    """Prometheus scrape endpoint."""
    lines = []

    # Request counters
    lines.append("# HELP atlas_requests_total Total requests processed")
    lines.append("# TYPE atlas_requests_total counter")
    lines.append(f"atlas_requests_total {metrics.request_count}")
    lines.append(f'atlas_requests_total{{type="local"}} {metrics.local_request_count}')
    lines.append(f'atlas_requests_total{{type="external"}} {metrics.external_request_count}')

    # Per-provider counts
    lines.append("# HELP atlas_requests_by_provider Requests per provider")
    lines.append("# TYPE atlas_requests_by_provider counter")
    for provider, count in metrics.provider_counts.items():
        lines.append(f'atlas_requests_by_provider{{provider="{provider}"}} {count}')

    # Per-model counts
    lines.append("# HELP atlas_requests_by_model Requests per model")
    lines.append("# TYPE atlas_requests_by_model counter")
    for model, count in metrics.model_counts.items():
        lines.append(f'atlas_requests_by_model{{model="{model}"}} {count}')

    # Per-task-type counts
    lines.append("# HELP atlas_requests_by_task Requests per task type")
    lines.append("# TYPE atlas_requests_by_task counter")
    for task, count in metrics.task_type_counts.items():
        lines.append(f'atlas_requests_by_task{{task="{task}"}} {count}')

    # Token counters
    lines.append("# HELP atlas_tokens_total Total tokens processed")
    lines.append("# TYPE atlas_tokens_total counter")
    lines.append(f'atlas_tokens_total{{direction="prompt"}} {metrics.total_prompt_tokens}')
    lines.append(f'atlas_tokens_total{{direction="completion"}} {metrics.total_completion_tokens}')

    # Cost
    lines.append("# HELP atlas_cost_usd_total Total cost in USD")
    lines.append("# TYPE atlas_cost_usd_total counter")
    lines.append(f"atlas_cost_usd_total {metrics.total_cost_usd:.6f}")
    lines.append(f"atlas_savings_usd_total {metrics.savings_usd:.6f}")

    # Errors
    lines.append("# HELP atlas_errors_total Total errors")
    lines.append("# TYPE atlas_errors_total counter")
    lines.append(f"atlas_errors_total {metrics.error_count}")
    for provider, count in metrics.error_counts_by_provider.items():
        lines.append(f'atlas_errors_by_provider{{provider="{provider}"}} {count}')

    # Provider health
    lines.append("# HELP atlas_provider_healthy Provider health (1=up, 0=down)")
    lines.append("# TYPE atlas_provider_healthy gauge")
    for p in provider_registry.list_providers():
        val = 1 if p["healthy"] else 0
        lines.append(f'atlas_provider_healthy{{provider="{p["name"]}"}} {val}')

    # Model count per provider
    lines.append("# HELP atlas_models_available Models per provider")
    lines.append("# TYPE atlas_models_available gauge")
    for p in provider_registry.list_providers():
        lines.append(f'atlas_models_available{{provider="{p["name"]}"}} {len(p["models"])}')

    # Latency percentiles per model
    lines.append("# HELP atlas_latency_ms Latency percentiles per model")
    lines.append("# TYPE atlas_latency_ms gauge")
    for model in list(metrics._latency_samples.keys()):
        pcts = metrics.get_latency_percentiles(model)
        for pct_name, val in pcts.items():
            lines.append(f'atlas_latency_ms{{model="{model}",quantile="{pct_name}"}} {val}')

    return "\n".join(lines) + "\n"
