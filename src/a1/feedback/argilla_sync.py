"""Argilla integration for human feedback annotation workflows.

Export conversations to Argilla for human review, import annotations
back as QualitySignal rows for the training pipeline.

Also provides handoff quality gate functions:
  push_handoff_batch_for_review  — push local-model responses to Argilla for annotation
  check_handoff_batch_approval   — check if a pushed batch has reached the approval threshold
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from a1.common.logging import get_logger
from a1.db.models import Conversation, DualExecutionRecord, Message, RoutingDecision
from a1.db.repositories import DualExecutionRepo, QualityRepo
from config.settings import settings

log = get_logger("feedback.argilla")


async def export_to_argilla(
    session: AsyncSession,
    dataset_name: str = "a1-conversations",
    limit: int = 500,
) -> dict:
    """Export recent conversations to Argilla for human annotation.

    Creates an Argilla dataset with fields for user message, assistant response,
    model info, and task type. Annotators can rate quality (1-5) and provide corrections.

    Returns export statistics.
    """
    if not settings.argilla_api_url:
        return {"error": "Argilla not configured (set argilla_api_url)"}

    import argilla as rg

    client = rg.Argilla(
        api_url=settings.argilla_api_url,
        api_key=settings.argilla_api_key or "admin.apikey",
    )

    # Create or get dataset with rating + text correction questions
    try:
        dataset = client.datasets(name=dataset_name, workspace=settings.argilla_workspace)
    except Exception:
        ds_settings = rg.Settings(
            fields=[
                rg.TextField(name="user_message", title="User Message"),
                rg.TextField(name="assistant_response", title="Assistant Response"),
                rg.TextField(name="model", title="Model Used", required=False),
                rg.TextField(name="task_type", title="Task Type", required=False),
            ],
            questions=[
                rg.RatingQuestion(name="quality", title="Response Quality", values=[1, 2, 3, 4, 5]),
                rg.TextQuestion(name="correction", title="Corrected Response (optional)", required=False),
            ],
            metadata=[
                rg.TermsMetadataProperty(name="message_id", title="Message ID"),
                rg.TermsMetadataProperty(name="conversation_id", title="Conversation ID"),
                rg.TermsMetadataProperty(name="provider", title="Provider"),
            ],
        )
        dataset = rg.Dataset(name=dataset_name, workspace=settings.argilla_workspace, settings=ds_settings)
        dataset.create()
        log.info(f"Created Argilla dataset: {dataset_name}")

    # Query conversations with messages and routing decisions
    stmt = (
        select(Conversation)
        .options(
            selectinload(Conversation.messages).selectinload(Message.routing_decision),
        )
        .order_by(Conversation.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    conversations = result.scalars().all()

    records = []
    exported = 0

    for conv in conversations:
        messages = sorted(conv.messages, key=lambda m: m.sequence)

        # Find user-assistant pairs
        for i, msg in enumerate(messages):
            if msg.role == "assistant" and i > 0:
                # Find the preceding user message
                user_msg = None
                for j in range(i - 1, -1, -1):
                    if messages[j].role == "user":
                        user_msg = messages[j]
                        break

                if not user_msg:
                    continue

                # Get routing info
                model_name = ""
                task_type = ""
                provider = ""
                if msg.routing_decision:
                    model_name = msg.routing_decision.model
                    task_type = msg.routing_decision.task_type or ""
                    provider = msg.routing_decision.provider

                record = rg.Record(
                    fields={
                        "user_message": user_msg.content,
                        "assistant_response": msg.content,
                        "model": model_name,
                        "task_type": task_type,
                    },
                    metadata={
                        "message_id": str(msg.id),
                        "conversation_id": str(conv.id),
                        "provider": provider,
                    },
                )
                records.append(record)
                exported += 1

    if records:
        dataset.records.log(records)
        log.info(f"Exported {exported} records to Argilla dataset '{dataset_name}'")

    return {"exported": exported, "dataset": dataset_name}


async def import_from_argilla(
    session: AsyncSession,
    dataset_name: str = "a1-conversations",
) -> dict:
    """Import annotations from Argilla back into quality_signals table.

    Maps Argilla quality ratings (1-5) to our 0.0-1.0 signal range.
    """
    if not settings.argilla_api_url:
        return {"error": "Argilla not configured (set argilla_api_url)"}

    import argilla as rg

    client = rg.Argilla(
        api_url=settings.argilla_api_url,
        api_key=settings.argilla_api_key or "admin.apikey",
    )

    try:
        dataset = client.datasets(name=dataset_name, workspace=settings.argilla_workspace)
    except Exception as e:
        return {"error": f"Dataset not found: {e}"}

    quality_repo = QualityRepo(session)
    imported = 0
    skipped = 0

    for record in dataset.records(with_responses=True):
        if not record.responses:
            skipped += 1
            continue

        message_id_str = record.metadata.get("message_id")
        if not message_id_str:
            skipped += 1
            continue

        try:
            message_id = uuid.UUID(message_id_str)
        except ValueError:
            skipped += 1
            continue

        for response in record.responses:
            # Import quality rating
            quality_value = response.values.get("quality")
            if quality_value is not None:
                # Normalize 1-5 scale to 0.0-1.0
                rating = quality_value.value if hasattr(quality_value, "value") else quality_value
                normalized = (rating - 1) / 4.0  # 1->0.0, 3->0.5, 5->1.0

                await quality_repo.add_signal(
                    message_id=message_id,
                    signal_type="argilla",
                    value=normalized,
                    evaluator=f"human:argilla:{response.user_id or 'unknown'}",
                )
                imported += 1

    log.info(f"Imported {imported} annotations from Argilla, skipped {skipped}")
    return {"imported": imported, "skipped": skipped, "dataset": dataset_name}


async def push_handoff_batch_for_review(
    session: AsyncSession,
    task_type: str,
    limit: int = 50,
) -> str | None:
    """Push a sample batch of local-model responses to Argilla for handoff quality annotation.

    Creates a dedicated dataset named `a1-handoff-{task_type}-{timestamp}`. Annotators rate
    whether the local model response is production-ready (1-5). Returns the dataset name
    (batch_id) on success, or None if Argilla is not configured.
    """
    if not settings.argilla_api_url:
        log.warning("Argilla not configured — skipping handoff batch push")
        return None

    import argilla as rg

    client = rg.Argilla(
        api_url=settings.argilla_api_url,
        api_key=settings.argilla_api_key or "admin.apikey",
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    batch_id = f"a1-handoff-{task_type}-{timestamp}"

    ds_settings = rg.Settings(
        fields=[
            rg.TextField(name="user_message", title="User Message"),
            rg.TextField(name="teacher_response", title="Claude (Teacher) Response"),
            rg.TextField(name="local_response", title="Local Model Response"),
            rg.TextField(name="task_type", title="Task Type", required=False),
            rg.TextField(name="local_model", title="Local Model", required=False),
        ],
        questions=[
            rg.RatingQuestion(
                name="quality",
                title="Is the local model response production-ready? (1=poor, 5=excellent)",
                values=[1, 2, 3, 4, 5],
            ),
        ],
        metadata=[
            rg.TermsMetadataProperty(name="record_id", title="DualExecutionRecord ID"),
            rg.TermsMetadataProperty(name="similarity_score", title="Auto Similarity Score"),
        ],
    )
    dataset = rg.Dataset(name=batch_id, workspace=settings.argilla_workspace, settings=ds_settings)
    dataset.create()
    log.info(f"Created Argilla handoff-review dataset: {batch_id}")

    # Fetch recent dual-execution records for this task type
    dual_repo = DualExecutionRepo(session)
    records_db = await dual_repo.get_recent(task_type=task_type, limit=limit)

    rg_records = []
    for rec in records_db:
        if not rec.local_response:
            continue
        user_msg = ""
        if rec.request_messages:
            for m in reversed(rec.request_messages):
                if isinstance(m, dict) and m.get("role") == "user":
                    user_msg = (m.get("content") or "")[:1000]
                    break

        rg_records.append(rg.Record(
            fields={
                "user_message": user_msg or "(no user message)",
                "teacher_response": (rec.claude_response or "")[:2000],
                "local_response": (rec.local_response or "")[:2000],
                "task_type": task_type,
                "local_model": rec.local_model or "",
            },
            metadata={
                "record_id": str(rec.id),
                "similarity_score": str(round(rec.similarity_score or 0.0, 3)),
            },
        ))

    if rg_records:
        dataset.records.log(rg_records)
        log.info(f"Pushed {len(rg_records)} records to Argilla handoff-review dataset '{batch_id}'")
    else:
        log.warning(f"No local-model records found for task_type={task_type}; pushed empty batch")

    return batch_id


async def check_handoff_batch_approval(
    batch_id: str,
    threshold: float | None = None,
) -> dict:
    """Check annotation progress and approval status for a handoff review batch.

    Returns:
        {
          "approved": bool,
          "positive_pct": float,   # fraction of annotated records rated >= 4
          "annotated_count": int,
          "total_records": int,
          "pending": bool,         # True if not enough annotations yet to decide
        }

    An approval requires at least 3 annotated records AND positive_pct >= threshold
    (default: settings.argilla_approval_threshold = 0.8).
    """
    if not settings.argilla_api_url:
        # Gate disabled — approve automatically
        return {"approved": True, "positive_pct": 1.0, "annotated_count": 0, "total_records": 0, "pending": False}

    if threshold is None:
        threshold = settings.argilla_approval_threshold

    try:
        import argilla as rg

        client = rg.Argilla(
            api_url=settings.argilla_api_url,
            api_key=settings.argilla_api_key or "admin.apikey",
        )

        try:
            dataset = client.datasets(name=batch_id, workspace=settings.argilla_workspace)
        except Exception as e:
            log.warning(f"Argilla batch '{batch_id}' not found: {e}")
            return {"approved": False, "positive_pct": 0.0, "annotated_count": 0, "total_records": 0, "pending": True}

        total = 0
        annotated = 0
        positive = 0

        for record in dataset.records(with_responses=True):
            total += 1
            if not record.responses:
                continue
            for resp in record.responses:
                quality_val = resp.values.get("quality")
                if quality_val is not None:
                    rating = quality_val.value if hasattr(quality_val, "value") else quality_val
                    annotated += 1
                    if rating >= 4:
                        positive += 1
                    break  # one response per record is enough

        if annotated < 3:
            # Not enough annotations to make a decision yet
            return {
                "approved": False,
                "positive_pct": positive / annotated if annotated else 0.0,
                "annotated_count": annotated,
                "total_records": total,
                "pending": True,
            }

        positive_pct = positive / annotated
        approved = positive_pct >= threshold

        log.info(
            f"Argilla batch '{batch_id}': {annotated}/{total} annotated, "
            f"{positive_pct:.0%} positive — {'APPROVED' if approved else 'REJECTED'} "
            f"(threshold {threshold:.0%})"
        )
        return {
            "approved": approved,
            "positive_pct": positive_pct,
            "annotated_count": annotated,
            "total_records": total,
            "pending": False,
        }

    except Exception as e:
        log.error(f"Failed to check Argilla batch approval for '{batch_id}': {e}")
        return {"approved": False, "positive_pct": 0.0, "annotated_count": 0, "total_records": 0, "pending": True}


async def get_argilla_status() -> dict:
    """Check Argilla server connectivity and dataset stats."""
    if not settings.argilla_api_url:
        return {"connected": False, "reason": "argilla_api_url not configured"}

    try:
        import argilla as rg

        client = rg.Argilla(
            api_url=settings.argilla_api_url,
            api_key=settings.argilla_api_key or "admin.apikey",
        )

        # List datasets in workspace
        datasets = []
        for ds in client.datasets:
            datasets.append({
                "name": ds.name,
                "workspace": ds.workspace.name if ds.workspace else "",
            })

        return {
            "connected": True,
            "api_url": settings.argilla_api_url,
            "datasets": datasets,
        }

    except Exception as e:
        return {"connected": False, "reason": str(e)}
