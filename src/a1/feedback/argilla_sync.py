"""Argilla integration for human feedback annotation workflows.

Export conversations to Argilla for human review, import annotations
back as QualitySignal rows for the training pipeline.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from a1.common.logging import get_logger
from a1.db.models import Conversation, Message, RoutingDecision
from a1.db.repositories import QualityRepo
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
