"""Import conversation history from paperclip.ing."""

import json
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from a1.common.logging import get_logger
from a1.db.repositories import ConversationRepo, MessageRepo, QualityRepo

log = get_logger("importers.paperclip")


async def import_from_paperclip(
    session: AsyncSession,
    api_url: str,
    api_key: str | None = None,
    limit: int = 1000,
) -> dict:
    """Import chat history from paperclip.ing API.

    paperclip.ing stores structured tickets with tool-call traces.
    Each ticket becomes a conversation, each agent turn becomes messages.

    Returns import statistics.
    """
    stats = {"imported": 0, "skipped": 0, "errors": 0}
    conv_repo = ConversationRepo(session)
    msg_repo = MessageRepo(session)
    quality_repo = QualityRepo(session)

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Fetch tickets/conversations from paperclip.ing
        resp = await client.get(
            f"{api_url}/api/v1/tickets",
            headers=headers,
            params={"limit": limit, "sort": "-created_at"},
        )
        resp.raise_for_status()
        tickets = resp.json().get("data", [])

        for ticket in tickets:
            try:
                external_id = f"paperclip:{ticket['id']}"

                # Check if already imported (dedup)
                existing = await session.execute(
                    __import__("sqlalchemy").select(
                        __import__("a1.db.models", fromlist=["Conversation"]).Conversation
                    ).where(
                        __import__("a1.db.models", fromlist=["Conversation"]).Conversation.external_id == external_id
                    )
                )
                if existing.scalar_one_or_none():
                    stats["skipped"] += 1
                    continue

                # Create conversation
                conv = await conv_repo.create(
                    source="import:paperclip",
                    external_id=external_id,
                    metadata={
                        "paperclip_id": ticket["id"],
                        "title": ticket.get("title", ""),
                        "tags": ticket.get("tags", []),
                    },
                )

                # Import messages from ticket history
                history = ticket.get("history", ticket.get("messages", []))
                seq = 0
                for entry in history:
                    role = _map_role(entry.get("role", entry.get("type", "user")))
                    content = entry.get("content", entry.get("text", ""))
                    tool_calls = entry.get("tool_calls")

                    await msg_repo.add(
                        conversation_id=conv.id,
                        role=role,
                        content=content,
                        sequence=seq,
                        tool_calls=tool_calls,
                    )
                    seq += 1

                    # Import quality signals from tool call success/failure
                    if entry.get("status") == "success":
                        msg = await msg_repo.add(conv.id, role, content, seq - 1)
                        await quality_repo.add_signal(
                            message_id=msg.id,
                            signal_type="auto_eval",
                            value=1.0,
                            evaluator="paperclip:status",
                        )
                    elif entry.get("status") == "error":
                        msg = await msg_repo.add(conv.id, role, content, seq - 1)
                        await quality_repo.add_signal(
                            message_id=msg.id,
                            signal_type="auto_eval",
                            value=0.0,
                            evaluator="paperclip:status",
                        )

                stats["imported"] += 1

            except Exception as e:
                log.error(f"Error importing ticket {ticket.get('id')}: {e}")
                stats["errors"] += 1

    log.info(f"Paperclip import complete: {stats}")
    return stats


def _map_role(role: str) -> str:
    """Map paperclip.ing roles to standard chat roles."""
    role_map = {
        "agent": "assistant",
        "bot": "assistant",
        "ai": "assistant",
        "human": "user",
        "customer": "user",
        "system": "system",
        "tool": "tool",
    }
    return role_map.get(role.lower(), role.lower())


async def import_from_paperclip_db(
    session: AsyncSession,
    db_url: str,
    limit: int = 1000,
) -> dict:
    """Import directly from paperclip.ing's PostgreSQL database.

    Alternative to API-based import for bulk data migration.
    """
    from sqlalchemy import create_engine, text

    stats = {"imported": 0, "skipped": 0, "errors": 0}
    conv_repo = ConversationRepo(session)
    msg_repo = MessageRepo(session)

    # Connect to paperclip DB (sync, for simplicity)
    from sqlalchemy import create_engine
    pc_engine = create_engine(db_url)

    with pc_engine.connect() as pc_conn:
        # Query conversations
        rows = pc_conn.execute(text(
            "SELECT id, title, created_at, messages FROM tickets ORDER BY created_at DESC LIMIT :limit"
        ), {"limit": limit}).fetchall()

        for row in rows:
            try:
                external_id = f"paperclip_db:{row[0]}"
                conv = await conv_repo.create(
                    source="import:paperclip_db",
                    external_id=external_id,
                    metadata={"title": row[1]},
                )

                messages = row[3] if isinstance(row[3], list) else json.loads(row[3] or "[]")
                for seq, msg in enumerate(messages):
                    role = _map_role(msg.get("role", "user"))
                    content = msg.get("content", "")
                    await msg_repo.add(conv.id, role, content, seq)

                stats["imported"] += 1
            except Exception as e:
                log.error(f"Error importing row {row[0]}: {e}")
                stats["errors"] += 1

    pc_engine.dispose()
    log.info(f"Paperclip DB import complete: {stats}")
    return stats
