"""Collect high-quality training samples from conversations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from a1.common.logging import get_logger
from a1.db.models import Conversation, Message, QualitySignal

log = get_logger("training.collector")


async def collect_training_samples(
    session: AsyncSession,
    min_quality: float = 0.7,
    min_turns: int = 2,
    max_samples: int = 10000,
) -> list[dict]:
    """Select high-quality conversation pairs for training.

    Returns list of dicts with 'messages' key in chat format:
    [{"role": "system", "content": "..."}, {"role": "user", ...}, {"role": "assistant", ...}]
    """
    # Find messages with high quality signals
    high_quality_msg_ids = (
        select(QualitySignal.message_id)
        .where(QualitySignal.value >= min_quality)
        .distinct()
        .subquery()
    )

    # Get conversations that have high-quality assistant messages
    conv_ids = (
        select(Message.conversation_id)
        .where(Message.id.in_(select(high_quality_msg_ids.c.message_id)))
        .distinct()
        .subquery()
    )

    # Fetch full conversations
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id.in_(select(conv_ids.c.conversation_id)))
        .limit(max_samples)
    )
    result = await session.execute(stmt)
    conversations = result.scalars().all()

    samples = []
    for conv in conversations:
        messages = sorted(conv.messages, key=lambda m: m.sequence)

        # Filter: need at least min_turns user messages
        user_turns = sum(1 for m in messages if m.role == "user")
        if user_turns < min_turns:
            continue

        # Convert to training format
        chat_messages = []
        for msg in messages:
            chat_messages.append({"role": msg.role, "content": msg.content})

        if chat_messages:
            samples.append({"messages": chat_messages})

    log.info(f"Collected {len(samples)} training samples from {len(conversations)} conversations")
    return samples


async def collect_all_conversations(
    session: AsyncSession,
    max_samples: int = 10000,
) -> list[dict]:
    """Collect all conversations (for bootstrapping when no quality signals exist)."""
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .order_by(Conversation.created_at.desc())
        .limit(max_samples)
    )
    result = await session.execute(stmt)
    conversations = result.scalars().all()

    samples = []
    for conv in conversations:
        messages = sorted(conv.messages, key=lambda m: m.sequence)
        chat_messages = [{"role": m.role, "content": m.content} for m in messages]
        if len(chat_messages) >= 2:
            samples.append({"messages": chat_messages})

    return samples
