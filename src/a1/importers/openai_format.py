"""Import conversations from OpenAI JSONL export format."""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from a1.common.logging import get_logger
from a1.db.repositories import ConversationRepo, MessageRepo

log = get_logger("importers.openai_format")


async def import_from_jsonl(
    session: AsyncSession,
    file_path: str,
) -> dict:
    """Import conversations from an OpenAI-style JSONL file.

    Each line should be: {"messages": [{"role": "...", "content": "..."}]}
    """
    stats = {"imported": 0, "errors": 0}
    conv_repo = ConversationRepo(session)
    msg_repo = MessageRepo(session)

    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                messages = data.get("messages", [])
                if not messages:
                    continue

                conv = await conv_repo.create(
                    source="import:openai_jsonl",
                    external_id=f"jsonl:{file_path}:{line_num}",
                    metadata=data.get("metadata", {}),
                )

                for seq, msg in enumerate(messages):
                    await msg_repo.add(
                        conversation_id=conv.id,
                        role=msg.get("role", "user"),
                        content=msg.get("content", ""),
                        sequence=seq,
                        tool_calls=msg.get("tool_calls"),
                    )

                stats["imported"] += 1

            except Exception as e:
                log.error(f"Error on line {line_num}: {e}")
                stats["errors"] += 1

    log.info(f"JSONL import complete: {stats}")
    return stats
