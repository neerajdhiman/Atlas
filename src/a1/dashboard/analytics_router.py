"""Analytics & metrics endpoints.

Endpoints:
  GET  /overview
  GET  /metrics
  GET  /analytics/token-timeseries
  GET  /analytics/cost-timeseries
  GET  /analytics/request-heatmap
  GET  /analytics/model-leaderboard
  GET  /analytics/recent-requests
  GET  /analytics/local-vs-external
  GET  /analytics/latency
  GET  /analytics/errors
  POST /models/compare
  GET  /routing/decisions
  GET  /routing/performance
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from a1.common.metrics import metrics
from a1.db.repositories import ConversationRepo, RoutingRepo
from a1.dependencies import get_db
from a1.providers.registry import provider_registry

router = APIRouter()


# --- Overview ---
@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db)):
    from a1.dashboard.router import _live_connections

    conv_repo = ConversationRepo(db)
    conv_count = await conv_repo.count()
    providers = provider_registry.list_providers()

    return {
        "metrics": metrics.snapshot(),
        "conversations_count": conv_count,
        "providers": providers,
        "active_connections": len(_live_connections),
    }


# --- Metrics ---
@router.get("/metrics")
async def get_metrics():
    return metrics.snapshot()


# --- Enhanced Analytics ---
@router.get("/analytics/token-timeseries")
async def token_timeseries():
    """Token usage over time (per-minute buckets)."""
    return {"data": metrics.token_timeseries()}


@router.get("/analytics/cost-timeseries")
async def cost_timeseries():
    """Cost trend over time (per-minute buckets)."""
    return {"data": metrics.cost_timeseries()}


@router.get("/analytics/request-heatmap")
async def request_heatmap():
    """Request volume heatmap by day-of-week and hour."""
    return {"data": metrics.request_heatmap()}


@router.get("/analytics/model-leaderboard")
async def model_leaderboard():
    """Model performance leaderboard with detailed stats."""
    return {"data": metrics.model_leaderboard()}


@router.get("/analytics/recent-requests")
async def recent_requests(limit: int = 50):
    """Recent request history for live feed."""
    return {"data": metrics.recent_requests(limit=limit)}


@router.get("/analytics/local-vs-external")
async def analytics_local_vs_external():
    snapshot = metrics.snapshot()
    return {
        "local": snapshot["local"],
        "external": snapshot["external"],
        "savings_usd": snapshot["savings_usd"],
    }


@router.get("/analytics/latency")
async def analytics_latency():
    snapshot = metrics.snapshot()
    result = []
    for model in snapshot.get("model_counts", {}):
        percs = metrics.get_latency_percentiles(model)
        result.append({"model": model, **percs})
    return {"data": result}


@router.get("/analytics/errors")
async def analytics_errors():
    snapshot = metrics.snapshot()
    return {"data": snapshot.get("error_counts_by_provider", {})}


# --- Routing ---
@router.get("/routing/decisions")
async def routing_decisions(
    limit: int = Query(100, le=500),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    task_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    repo = RoutingRepo(db)
    decisions = await repo.list_recent(
        limit=limit, date_from=date_from, date_to=date_to, task_type=task_type
    )
    return {
        "data": [
            {
                "id": str(d.id),
                "provider": d.provider,
                "model": d.model,
                "task_type": d.task_type,
                "strategy": d.strategy,
                "confidence": d.confidence,
                "latency_ms": d.latency_ms,
                "cost_usd": float(d.cost_usd),
                "prompt_tokens": d.prompt_tokens,
                "completion_tokens": d.completion_tokens,
                "is_local": d.is_local,
                "error": d.error,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in decisions
        ]
    }


@router.get("/routing/performance")
async def routing_performance(
    task_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    repo = RoutingRepo(db)
    perf = await repo.get_performance(task_type=task_type)
    return {
        "data": [
            {
                "task_type": p.task_type,
                "provider": p.provider,
                "model": p.model,
                "avg_quality": p.avg_quality,
                "avg_latency_ms": p.avg_latency_ms,
                "avg_cost_usd": p.avg_cost_usd,
                "sample_count": p.sample_count,
            }
            for p in perf
        ]
    }


# --- Model Comparison ---
@router.post("/models/compare")
async def compare_models(
    prompt: str,
    models: list[str],
    max_tokens: int = 500,
):
    """Run the same prompt through multiple models and compare responses."""
    import time

    from a1.proxy.request_models import ChatCompletionRequest, MessageInput

    results = []
    for model_name in models:
        provider = provider_registry.get_provider_for_model(model_name)
        if not provider:
            results.append({"model": model_name, "error": "No provider found"})
            continue
        try:
            req = ChatCompletionRequest(
                model=model_name,
                messages=[MessageInput(role="user", content=prompt)],
                max_tokens=max_tokens,
            )
            start = time.time()
            resp = await provider.complete(req)
            latency = int((time.time() - start) * 1000)
            results.append(
                {
                    "model": model_name,
                    "provider": provider.name,
                    "content": resp.choices[0].message.content if resp.choices else "",
                    "latency_ms": latency,
                    "prompt_tokens": resp.usage.prompt_tokens,
                    "completion_tokens": resp.usage.completion_tokens,
                }
            )
        except Exception as e:
            results.append({"model": model_name, "error": str(e)})

    return {"results": results}
