"""Training, distillation, evaluation, Argilla, and import endpoints.

Endpoints:
  GET  /training/runs
  POST /training/runs
  GET  /training/runs/{run_id}
  POST /training/runs/{run_id}/evaluate
  GET  /distillation/overview
  POST /distillation/trigger-training/{task_type}
  POST /distillation/handoff/{task_type}
  GET  /argilla/status
  POST /argilla/export
  POST /argilla/import
  POST /import/paperclip
  POST /import/jsonl
"""

import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from a1.db.repositories import TrainingRepo
from a1.dependencies import get_db
from config.settings import settings

router = APIRouter()


# --- Training Runs ---
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
    from a1.dependencies import get_arq_pool

    arq_pool = await get_arq_pool()
    await arq_pool.enqueue_job("run_training_pipeline", str(run.id))

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


# --- Distillation Pipeline ---
@router.get("/distillation/overview")
async def distillation_overview(db: AsyncSession = Depends(get_db)):
    """Per-task-type distillation status: sample counts, handoff %, training status."""
    from a1.db.repositories import DualExecutionRepo, TaskTypeReadinessRepo

    readiness_repo = TaskTypeReadinessRepo(db)
    dual_repo = DualExecutionRepo(db)

    task_types = await readiness_repo.list_all()
    result = []
    for tt in task_types:
        total = await dual_repo.count_by_task_type(tt.task_type)
        result.append(
            {
                "task_type": tt.task_type,
                "claude_samples": tt.claude_sample_count,
                "total_comparisons": total,
                "local_handoff_pct": round(tt.local_handoff_pct * 100, 1),
                "local_avg_quality": round(tt.local_avg_quality, 3),
                "best_local_model": tt.best_local_model,
                "last_training_run_id": tt.last_training_run_id,
                "training_threshold": settings.distillation_min_samples,
                "ready_for_training": tt.claude_sample_count >= settings.distillation_min_samples,
            }
        )

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
async def set_handoff_percentage(
    task_type: str, pct: float = Query(..., ge=0, le=100), db: AsyncSession = Depends(get_db)
):
    """Manually override handoff percentage for a task type."""
    from a1.db.repositories import TaskTypeReadinessRepo

    repo = TaskTypeReadinessRepo(db)
    await repo.update_handoff(task_type, pct / 100.0)
    return {"task_type": task_type, "handoff_pct": pct}


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


@router.post("/import/jsonl-upload")
async def upload_jsonl_import(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
):
    """Accept a JSONL file upload and import the conversations."""
    from a1.importers.openai_format import import_from_jsonl

    if not file.filename or not file.filename.endswith((".jsonl", ".json")):
        raise HTTPException(status_code=400, detail="File must be .jsonl or .json")

    content = await file.read()
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".jsonl", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        stats = await import_from_jsonl(db, tmp_path)
    finally:
        os.unlink(tmp_path)

    return stats
