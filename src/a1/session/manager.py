"""Session Manager — maintains conversation context across requests.

Tracks multi-turn conversations with in-memory cache + DB persistence.
Sessions expire after configurable TTL. Supports session chaining via
previous_response_id (OpenClaw pattern) or explicit session_id.
"""

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from a1.common.logging import get_logger

log = get_logger("session")


@dataclass
class SessionMessage:
    """A single message in a session."""
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    response_id: str | None = None  # links response to session for chaining


@dataclass
class Session:
    """Active conversation session."""
    id: str
    user_id: str | None = None
    messages: list[SessionMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    def add_message(self, role: str, content: str, response_id: str | None = None):
        self.messages.append(SessionMessage(
            role=role, content=content, response_id=response_id,
        ))
        self.last_activity = time.time()

    def get_history(self, limit: int = 20) -> list[dict]:
        """Get last N messages as dicts for injection into prompts."""
        recent = self.messages[-limit:] if limit else self.messages
        return [{"role": m.role, "content": m.content} for m in recent]

    def is_expired(self, ttl_seconds: int) -> bool:
        return time.time() - self.last_activity > ttl_seconds


class SessionManager:
    """Manages conversation sessions with in-memory LRU cache.

    Thread-safe for async usage. Sessions are evicted when:
    - TTL expires (configurable, default 1 hour)
    - Cache exceeds max_sessions (LRU eviction)
    """

    def __init__(self, ttl_seconds: int = 3600, max_sessions: int = 1000, max_messages: int = 20):
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._response_to_session: dict[str, str] = {}  # response_id → session_id
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self.max_messages = max_messages

    def get_or_create(
        self,
        session_id: str | None = None,
        previous_response_id: str | None = None,
        user_id: str | None = None,
    ) -> Session:
        """Get existing session or create new one.

        Resolution order:
        1. Explicit session_id → lookup directly
        2. previous_response_id → find session that produced that response
        3. Neither → create new session
        """
        self._cleanup_expired()

        # 1. Explicit session_id
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            self._sessions.move_to_end(session_id)
            session.last_activity = time.time()
            return session

        # 2. Chain via previous_response_id
        if previous_response_id and previous_response_id in self._response_to_session:
            sid = self._response_to_session[previous_response_id]
            if sid in self._sessions:
                session = self._sessions[sid]
                self._sessions.move_to_end(sid)
                session.last_activity = time.time()
                return session

        # 3. Create new session
        new_id = session_id or str(uuid.uuid4())
        session = Session(id=new_id, user_id=user_id)
        self._sessions[new_id] = session

        # Evict oldest if over limit
        while len(self._sessions) > self.max_sessions:
            self._sessions.popitem(last=False)

        log.info(f"New session: {new_id[:8]}... (user={user_id})")
        return session

    def link_response(self, response_id: str, session_id: str):
        """Link a response_id to a session for future chaining."""
        self._response_to_session[response_id] = session_id
        # Keep map bounded
        if len(self._response_to_session) > self.max_sessions * 10:
            # Remove oldest entries
            keys = list(self._response_to_session.keys())
            for k in keys[:len(keys) // 2]:
                del self._response_to_session[k]

    def get_session(self, session_id: str) -> Session | None:
        """Get session by ID, or None if not found/expired."""
        session = self._sessions.get(session_id)
        if session and not session.is_expired(self.ttl_seconds):
            return session
        return None

    def list_active(self) -> list[dict]:
        """List all active sessions for dashboard."""
        self._cleanup_expired()
        return [
            {
                "id": s.id,
                "user_id": s.user_id,
                "message_count": len(s.messages),
                "created_at": s.created_at,
                "last_activity": s.last_activity,
                "age_seconds": int(time.time() - s.created_at),
            }
            for s in self._sessions.values()
        ]

    def _cleanup_expired(self):
        """Remove expired sessions."""
        expired = [
            sid for sid, s in self._sessions.items()
            if s.is_expired(self.ttl_seconds)
        ]
        for sid in expired:
            del self._sessions[sid]
            log.debug(f"Session expired: {sid[:8]}...")


# Singleton
session_manager = SessionManager()
