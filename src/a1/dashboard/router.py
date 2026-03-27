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
from config.settings import settings

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


# --- Provider Accounts (multi-key management) ---
@router.get("/accounts")
async def list_accounts(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from a1.db.models import ProviderAccount
    result = await db.execute(
        select(ProviderAccount).order_by(ProviderAccount.provider, ProviderAccount.priority.desc())
    )
    accounts = result.scalars().all()
    return {
        "data": [
            {
                "id": str(a.id),
                "provider": a.provider,
                "name": a.name,
                "is_active": a.is_active,
                "priority": a.priority,
                "rate_limit_rpm": a.rate_limit_rpm,
                "monthly_budget_usd": float(a.monthly_budget_usd) if a.monthly_budget_usd else None,
                "current_month_cost_usd": float(a.current_month_cost_usd),
                "total_requests": a.total_requests,
                "total_tokens": a.total_tokens,
                "last_used_at": a.last_used_at.isoformat() if a.last_used_at else None,
                "last_error": a.last_error,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in accounts
        ]
    }


@router.post("/accounts")
async def create_account(
    provider: str,
    name: str,
    api_key: str,
    priority: int = 0,
    rate_limit_rpm: int | None = None,
    monthly_budget_usd: float | None = None,
    db: AsyncSession = Depends(get_db),
):
    from a1.db.models import ProviderAccount
    from a1.providers.key_pool import encrypt_key, key_pool
    account = ProviderAccount(
        provider=provider,
        name=name,
        api_key_encrypted=encrypt_key(api_key),
        priority=priority,
        rate_limit_rpm=rate_limit_rpm,
        monthly_budget_usd=monthly_budget_usd,
    )
    db.add(account)
    await db.flush()
    await key_pool.load_accounts()  # reload pool
    return {"id": str(account.id), "status": "created"}


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import delete as sql_delete
    from a1.db.models import ProviderAccount
    from a1.providers.key_pool import key_pool
    await db.execute(sql_delete(ProviderAccount).where(ProviderAccount.id == uuid.UUID(account_id)))
    await key_pool.load_accounts()
    return {"status": "deleted"}


@router.post("/accounts/{account_id}/test")
async def test_account(account_id: str, db: AsyncSession = Depends(get_db)):
    from a1.db.models import ProviderAccount
    from a1.providers.key_pool import decrypt_key
    result = await db.execute(
        __import__("sqlalchemy").select(ProviderAccount).where(ProviderAccount.id == uuid.UUID(account_id))
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")
    try:
        import litellm
        api_key = decrypt_key(account.api_key_encrypted)
        await litellm.acompletion(
            model="gpt-4o-mini" if account.provider == "openai" else "claude-haiku-4-5-20251001",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
            api_key=api_key,
        )
        return {"status": "ok", "message": "Key is valid"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# --- Analytics ---
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


# --- Ollama Management ---
@router.get("/ollama/models")
async def ollama_models():
    from a1.providers.registry import provider_registry
    ollama = provider_registry.get_provider("ollama")
    if not ollama:
        return {"data": [], "servers": []}
    return {
        "data": [
            {"name": m.name, "provider": m.provider, "context_window": m.context_window}
            for m in ollama.list_models()
        ],
        "servers": ollama.list_servers() if hasattr(ollama, "list_servers") else [],
    }


@router.post("/ollama/pull")
async def ollama_pull(name: str, server_url: str | None = None):
    import httpx
    from config.settings import settings
    url = server_url or (settings.ollama_servers[0] if settings.ollama_servers else settings.ollama_base_url)
    async with httpx.AsyncClient(base_url=url, timeout=600.0) as client:
        resp = await client.post("/api/pull", json={"name": name})
        return resp.json()


@router.delete("/ollama/models/{name}")
async def ollama_delete(name: str, server_url: str | None = None):
    import httpx
    from config.settings import settings
    url = server_url or (settings.ollama_servers[0] if settings.ollama_servers else settings.ollama_base_url)
    async with httpx.AsyncClient(base_url=url, timeout=30.0) as client:
        resp = await client.delete("/api/delete", json={"name": name})
        return resp.json()


@router.post("/models/compare")
async def compare_models(
    prompt: str,
    models: list[str],
    max_tokens: int = 500,
):
    """Run the same prompt through multiple models and compare responses."""
    from a1.proxy.request_models import ChatCompletionRequest, MessageInput
    import time

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
            results.append({
                "model": model_name,
                "provider": provider.name,
                "content": resp.choices[0].message.content if resp.choices else "",
                "latency_ms": latency,
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
            })
        except Exception as e:
            results.append({"model": model_name, "error": str(e)})

    return {"results": results}


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


# --- Prompt Playground ---
@router.post("/playground")
async def playground(body: dict):
    """Test a prompt against any available model."""
    import time as _time
    from a1.proxy.request_models import ChatCompletionRequest, MessageInput

    model = body.get("model", "alpheric-1")
    prompt = body.get("prompt", "")
    system_prompt = body.get("system_prompt", "")
    temperature = body.get("temperature", 0.7)
    max_tokens = body.get("max_tokens", 500)

    messages = []
    if system_prompt:
        messages.append(MessageInput(role="system", content=system_prompt))
    messages.append(MessageInput(role="user", content=prompt))

    provider = provider_registry.get_provider_for_model(model)
    if not provider:
        from fastapi import HTTPException
        raise HTTPException(404, f"No provider for model: {model}")

    req = ChatCompletionRequest(
        model=model, messages=messages,
        temperature=temperature, max_tokens=max_tokens,
    )

    start = _time.time()
    try:
        resp = await provider.complete(req)
        latency = int((_time.time() - start) * 1000)
        content = resp.choices[0].message.content if resp.choices else ""
        return {
            "model": model,
            "provider": provider.name,
            "content": content,
            "latency_ms": latency,
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens,
            "total_tokens": resp.usage.total_tokens,
            "cost_usd": provider.estimate_cost(
                resp.usage.prompt_tokens, resp.usage.completion_tokens, model
            ),
        }
    except Exception as e:
        latency = int((_time.time() - start) * 1000)
        return {"model": model, "error": str(e), "latency_ms": latency}


# --- Server Status ---
# --- Distillation Pipeline ---
@router.get("/distillation/overview")
async def distillation_overview(db: AsyncSession = Depends(get_db)):
    """Per-task-type distillation status: sample counts, handoff %, training status."""
    from a1.db.repositories import TaskTypeReadinessRepo, DualExecutionRepo
    readiness_repo = TaskTypeReadinessRepo(db)
    dual_repo = DualExecutionRepo(db)

    task_types = await readiness_repo.list_all()
    result = []
    for tt in task_types:
        total = await dual_repo.count_by_task_type(tt.task_type)
        result.append({
            "task_type": tt.task_type,
            "claude_samples": tt.claude_sample_count,
            "total_comparisons": total,
            "local_handoff_pct": round(tt.local_handoff_pct * 100, 1),
            "local_avg_quality": round(tt.local_avg_quality, 3),
            "best_local_model": tt.best_local_model,
            "last_training_run_id": tt.last_training_run_id,
            "training_threshold": settings.distillation_min_samples,
            "ready_for_training": tt.claude_sample_count >= settings.distillation_min_samples,
        })

    return {
        "enabled": settings.distillation_enabled,
        "teacher_model": settings.distillation_claude_model,
        "min_samples": settings.distillation_min_samples,
        "max_handoff_pct": settings.distillation_max_handoff_pct * 100,
        "task_types": result,
    }


@router.post("/distillation/trigger-training/{task_type}")
async def trigger_distillation_training(task_type: str, db: AsyncSession = Depends(get_db)):
    """Manually trigger training for a task type."""
    from a1.db.repositories import TrainingRepo
    config = {
        "base_model": settings.training_base_model,
        "lora_rank": settings.training_lora_rank,
        "epochs": 3,
        "task_type": task_type,
        "distillation": True,
    }
    repo = TrainingRepo(db)
    run = await repo.create_run(base_model=config["base_model"], dataset_size=0, config=config)
    return {"id": str(run.id), "status": "pending", "task_type": task_type}


@router.post("/distillation/handoff/{task_type}")
async def set_handoff_percentage(task_type: str, pct: float = Query(..., ge=0, le=100), db: AsyncSession = Depends(get_db)):
    """Manually override handoff percentage for a task type."""
    from a1.db.repositories import TaskTypeReadinessRepo
    repo = TaskTypeReadinessRepo(db)
    await repo.update_handoff(task_type, pct / 100.0)
    return {"task_type": task_type, "handoff_pct": pct}


# --- Sessions ---
@router.get("/sessions")
async def list_sessions():
    """List all active sessions."""
    from a1.session.manager import session_manager
    return {"data": session_manager.list_active()}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session detail with message history."""
    from a1.session.manager import session_manager
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")
    return {
        "id": session.id,
        "user_id": session.user_id,
        "message_count": len(session.messages),
        "messages": [{"role": m.role, "content": m.content[:200], "timestamp": m.timestamp} for m in session.messages],
        "created_at": session.created_at,
        "last_activity": session.last_activity,
    }


# --- PII Stats ---
@router.get("/pii/stats")
async def pii_stats():
    """PII masking statistics."""
    from a1.security.pii_masker import get_mask_stats
    return {
        "enabled": settings.pii_masking_enabled,
        "external_only": settings.pii_mask_for_external_only,
        "patterns": settings.pii_patterns,
        **get_mask_stats(),
    }


@router.get("/servers")
async def server_status():
    """Get status of all infrastructure servers."""
    ollama = provider_registry.get_provider("ollama")
    servers = []
    if ollama and hasattr(ollama, "list_servers"):
        for s in ollama.list_servers():
            servers.append({**s, "type": "ollama"})
    return {"data": servers}
