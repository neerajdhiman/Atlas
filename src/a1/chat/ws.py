"""WebSocket chat endpoint for real-time team conversations.

Each channel gets a WebSocket room. Messages are:
1. Broadcast to all connected members
2. Sent to Atlas for AI response (using the channel's team atlas_model)
3. AI response broadcast back to all members

Protocol (JSON over WS):
  Client → Server:  {"type": "message", "content": "text", "user_id": "..."}
  Server → Client:  {"type": "message", "role": "user",
                     "content": "...", "user_id": "...", "ts": "..."}
  Server → Client:  {"type": "message", "role": "assistant",
                     "content": "...", "model": "...", "ts": "..."}
  Server → Client:  {"type": "typing",  "model": "atlas-plan"}
  Server → Client:  {"type": "error",   "message": "..."}
  Client → Server:  {"type": "ping"}
  Server → Client:  {"type": "pong"}
"""

import asyncio
import json
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from a1.common.logging import get_logger
from a1.common.tz import now_ist
from config.settings import settings

log = get_logger("chat.ws")

router = APIRouter(tags=["chat"])

# Channel room state: channel_id → set of connected websockets
_rooms: dict[str, set[WebSocket]] = {}


async def _broadcast(channel_id: str, message: dict, exclude: WebSocket | None = None):
    """Broadcast a JSON message to all connections in a channel room."""
    room = _rooms.get(channel_id, set())
    dead: list[WebSocket] = []
    payload = json.dumps(message, default=str)
    for ws in room:
        if ws is exclude:
            continue
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        room.discard(ws)


@router.websocket("/ws/chat/{channel_id}")
async def chat_ws(
    websocket: WebSocket,
    channel_id: str,
    token: str | None = Query(None),
):
    """WebSocket chat endpoint for a specific channel.

    Query params:
      - token: API key for auth (browsers can't send auth headers on WS upgrade)
    """
    # Auth
    if settings.api_keys and token not in settings.api_keys:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    # Join room
    if channel_id not in _rooms:
        _rooms[channel_id] = set()
    _rooms[channel_id].add(websocket)
    log.info(f"[chat] WS connected to channel {channel_id} ({len(_rooms[channel_id])} members)")

    # Resolve channel's team atlas_model (default atlas-plan)
    atlas_model = "atlas-plan"
    team_system_prompt = None
    try:
        from sqlalchemy import select

        from a1.db.engine import async_session
        from a1.db.models import Channel, Team

        async with async_session() as session:
            result = await session.execute(
                select(Channel, Team)
                .join(Team, Channel.team_id == Team.id)
                .where(Channel.id == uuid.UUID(channel_id))
            )
            row = result.first()
            if row:
                channel, team = row
                atlas_model = team.atlas_model or "atlas-plan"
                team_system_prompt = team.system_prompt
    except Exception as e:
        log.debug(f"[chat] Could not resolve channel team config: {e}")

    # Session for this channel (shared across all members)
    session_obj = None
    if settings.session_enabled:
        from a1.session.manager import session_manager

        session_obj = await session_manager.get_or_create(
            session_id=f"channel:{channel_id}",
        )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            msg_type = msg.get("type", "message")

            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            if msg_type != "message":
                continue

            content = msg.get("content", "").strip()
            user_id = msg.get("user_id", "anonymous")
            if not content:
                continue

            ts = now_ist().isoformat()

            # Broadcast user message to all channel members
            await _broadcast(
                channel_id,
                {
                    "type": "message",
                    "role": "user",
                    "content": content,
                    "user_id": user_id,
                    "ts": ts,
                },
            )

            # Add to session history
            if session_obj:
                session_obj.add_message("user", content)

            # Indicate typing
            await _broadcast(channel_id, {"type": "typing", "model": atlas_model})

            # Get AI response via Atlas distillation pipeline
            ai_response = await _get_atlas_response(
                content, atlas_model, team_system_prompt, session_obj
            )

            # Add to session history
            if session_obj and ai_response:
                session_obj.add_message("assistant", ai_response)

            # Broadcast AI response
            await _broadcast(
                channel_id,
                {
                    "type": "message",
                    "role": "assistant",
                    "content": ai_response or "I couldn't generate a response.",
                    "model": atlas_model,
                    "ts": now_ist().isoformat(),
                },
            )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error(f"[chat] WS error in channel {channel_id}: {e}")
    finally:
        _rooms.get(channel_id, set()).discard(websocket)
        remaining = len(_rooms.get(channel_id, set()))
        if remaining == 0:
            _rooms.pop(channel_id, None)
        log.info(f"[chat] WS disconnected from channel {channel_id} ({remaining} remaining)")


async def _get_atlas_response(
    content: str,
    atlas_model: str,
    team_system_prompt: str | None,
    session_obj,
) -> str | None:
    """Route user message through Atlas distillation pipeline."""
    try:
        from fastapi import Response

        from a1.proxy.request_models import ChatCompletionRequest, MessageInput
        from a1.training.auto_trainer import handle_dual_execution

        messages: list[MessageInput] = []

        # Team system prompt
        if team_system_prompt:
            messages.append(MessageInput(role="system", content=team_system_prompt))

        # Session history
        if session_obj:
            for hist in session_obj.get_history(limit=settings.session_max_messages):
                messages.append(MessageInput(role=hist["role"], content=hist["content"]))

        messages.append(MessageInput(role="user", content=content))

        req = ChatCompletionRequest(
            model=atlas_model,
            messages=messages,
            max_tokens=2000,
        )

        from a1.routing.classifier import classify_task

        task_type, _ = classify_task(req)

        result = await asyncio.wait_for(
            handle_dual_execution(req, Response(), task_type, 0.9, atlas_model=atlas_model),
            timeout=settings.agent_execution_timeout,
        )

        if result and result.choices:
            return result.choices[0].message.content

    except asyncio.TimeoutError:
        log.warning(f"[chat] Atlas response timed out for {atlas_model}")
    except Exception as e:
        log.error(f"[chat] Atlas response error: {e}")

    return None
