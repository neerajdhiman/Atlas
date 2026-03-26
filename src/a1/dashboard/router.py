"""Admin dashboard API endpoints — full visibility into everything happening."""

import asyncio
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from a1.common.logging import get_logger
from a1.common.metrics import metrics
from a1.db.repositories import ConversationRepo, MessageRepo, QualityRepo, RoutingRepo, TrainingRepo
from a1.dependencies import get_db
from a1.providers.registry import provider_registry

log = get_logger("dashboard")
router = APIRouter(prefix="/admin", tags=["dashboard"])

# --- WebSocket live feed ---
_live_connections: list[WebSocket] = []


@router.websocket("/ws/live-feed")
async def live_feed(websocket: WebSocket):
    await websocket.accept()
    _live_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        _live_connections.remove(websocket)


async def broadcast_event(event: dict):
    """Broadcast an event to all connected dashboard clients."""
    data = json.dumps(event, default=str)
    for ws in _live_connections[:]:
        try:
            await ws.send_text(data)
        except Exception:
            _live_connections.remove(ws)


# --- Overview ---
@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db)):
    conv_repo = ConversationRepo(db)
    conv_count = await conv_repo.count()
    providers = provider_registry.list_providers()

    return {
        "metrics": metrics.snapshot(),
        "conversations_count": conv_count,
        "providers": providers,
        "active_connections": len(_live_connections),
    }


# --- Conversations ---
@router.get("/conversations")
async def list_conversations(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    repo = ConversationRepo(db)
    conversations = await repo.list_recent(limit=limit, offset=offset)
    total = await repo.count()
    return {
        "data": [
            {
                "id": str(c.id),
                "source": c.source,
                "user_id": c.user_id,
                "message_count": len(c.messages) if hasattr(c, "messages") and c.messages else 0,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "metadata": c.metadata_,
            }
            for c in conversations
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str, db: AsyncSession = Depends(get_db)):
    repo = ConversationRepo(db)
    conv = await repo.get(uuid.UUID(conv_id))
    if not conv:
        raise HTTPException(404, "Conversation not found")

    return {
        "id": str(conv.id),
        "source": conv.source,
        "user_id": conv.user_id,
        "metadata": conv.metadata_,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "token_count": m.token_count,
                "sequence": m.sequence,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "routing_decision": {
                    "provider": m.routing_decision.provider,
                    "model": m.routing_decision.model,
                    "task_type": m.routing_decision.task_type,
                    "strategy": m.routing_decision.strategy,
                    "latency_ms": m.routing_decision.latency_ms,
                    "cost_usd": float(m.routing_decision.cost_usd),
                    "prompt_tokens": m.routing_decision.prompt_tokens,
                    "completion_tokens": m.routing_decision.completion_tokens,
                } if m.routing_decision else None,
                "quality_signals": [
                    {
                        "type": s.signal_type,
                        "value": s.value,
                        "evaluator": s.evaluator,
                    }
                    for s in (m.quality_signals or [])
                ],
            }
            for m in sorted(conv.messages, key=lambda x: x.sequence)
        ],
    }


@router.post("/conversations/{conv_id}/feedback")
async def add_feedback(
    conv_id: str,
    message_id: str,
    signal_type: str = "thumbs",
    value: float = 1.0,
    db: AsyncSession = Depends(get_db),
):
    repo = QualityRepo(db)
    signal = await repo.add_signal(
        message_id=uuid.UUID(message_id),
        signal_type=signal_type,
        value=value,
        evaluator="user:dashboard",
    )
    return {"id": str(signal.id), "status": "recorded"}


# --- Routing ---
@router.get("/routing/decisions")
async def routing_decisions(limit: int = Query(100, le=500), db: AsyncSession = Depends(get_db)):
    repo = RoutingRepo(db)
    decisions = await repo.list_recent(limit=limit)
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


# --- Providers ---
@router.get("/providers")
async def list_providers():
    providers = provider_registry.list_providers()
    return {"data": providers}


@router.post("/providers/refresh")
async def refresh_providers():
    await provider_registry.refresh_health()
    return {"status": "refreshed", "providers": provider_registry.list_providers()}


# --- Training ---
@router.get("/training/runs")
async def list_training_runs(limit: int = Query(50, le=200), db: AsyncSession = Depends(get_db)):
    repo = TrainingRepo(db)
    runs = await repo.list_runs(limit=limit)
    return {
        "data": [
            {
                "id": str(r.id),
                "base_model": r.base_model,
                "dataset_size": r.dataset_size,
                "status": r.status,
                "config": r.config,
                "metrics": r.metrics,
                "ollama_model": r.ollama_model,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ]
    }


@router.post("/training/runs")
async def create_training_run(
    base_model: str | None = None,
    lora_rank: int = 16,
    epochs: int = 3,
    db: AsyncSession = Depends(get_db),
):
    from config.settings import settings

    repo = TrainingRepo(db)
    config = {
        "base_model": base_model or settings.training_base_model,
        "lora_rank": lora_rank,
        "epochs": epochs,
    }
    run = await repo.create_run(
        base_model=config["base_model"],
        dataset_size=0,  # will be updated during collection
        config=config,
    )
    # TODO: Dispatch to ARQ worker
    # await arq_pool.enqueue_job("run_training_pipeline", str(run.id))

    return {"id": str(run.id), "status": "pending", "message": "Training run queued"}


@router.get("/training/runs/{run_id}")
async def get_training_run(run_id: str, db: AsyncSession = Depends(get_db)):
    repo = TrainingRepo(db)
    run = await repo.get_run(uuid.UUID(run_id))
    if not run:
        raise HTTPException(404, "Training run not found")
    return {
        "id": str(run.id),
        "base_model": run.base_model,
        "dataset_size": run.dataset_size,
        "status": run.status,
        "config": run.config,
        "metrics": run.metrics,
        "artifact_path": run.artifact_path,
        "ollama_model": run.ollama_model,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


# --- Import ---
@router.post("/import/paperclip")
async def trigger_paperclip_import(
    api_url: str,
    api_key: str | None = None,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
):
    from a1.importers.paperclip import import_from_paperclip
    stats = await import_from_paperclip(db, api_url, api_key, limit)
    return stats


@router.post("/import/jsonl")
async def trigger_jsonl_import(
    file_path: str,
    db: AsyncSession = Depends(get_db),
):
    from a1.importers.openai_format import import_from_jsonl
    stats = await import_from_jsonl(db, file_path)
    return stats


# --- Argilla (human feedback) ---
@router.get("/argilla/status")
async def argilla_status():
    from a1.feedback.argilla_sync import get_argilla_status
    return await get_argilla_status()


@router.post("/argilla/export")
async def argilla_export(
    dataset_name: str = "a1-conversations",
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
):
    from a1.feedback.argilla_sync import export_to_argilla
    return await export_to_argilla(db, dataset_name, limit)


@router.post("/argilla/import")
async def argilla_import(
    dataset_name: str = "a1-conversations",
    db: AsyncSession = Depends(get_db),
):
    from a1.feedback.argilla_sync import import_from_argilla
    return await import_from_argilla(db, dataset_name)


# --- Standalone evaluation ---
@router.post("/training/runs/{run_id}/evaluate")
async def evaluate_training_run(
    run_id: str,
    tasks: list[str] | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger standalone lm-eval-harness evaluation on an existing training run."""
    repo = TrainingRepo(db)
    run = await repo.get_run(uuid.UUID(run_id))
    if not run:
        raise HTTPException(404, "Training run not found")
    if not run.artifact_path:
        raise HTTPException(400, "Training run has no adapter artifact")

    from a1.training.harness_evaluator import run_harness_eval
    eval_results = run_harness_eval(
        adapter_path=run.artifact_path,
        base_model=run.base_model,
        tasks=tasks,
    )

    await repo.update_status(uuid.UUID(run_id), run.status, metrics=eval_results)
    return eval_results


# --- Metrics ---
@router.get("/metrics")
async def get_metrics():
    return metrics.snapshot()
