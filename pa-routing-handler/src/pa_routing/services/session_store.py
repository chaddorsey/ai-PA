"""In-memory session store for multi-agent context.

Phase 1: Simple dict with user_id key.
Phase 2: Redis with TTL for persistence and expiration.
"""

from datetime import datetime, timedelta

from pa_routing.models.session_context import SessionContext

# Sessions expire after 1 hour of inactivity
SESSION_TTL_MINUTES = 60


class SessionStore:
    """
    In-memory session store.
    Phase 1: Simple dict. Phase 2: Redis with TTL.
    """

    def __init__(self):
        self._sessions: dict[str, SessionContext] = {}

    def get_or_create(self, user_id: str) -> SessionContext:
        """Get existing session or create new one."""
        self._cleanup_stale()

        if user_id not in self._sessions:
            self._sessions[user_id] = SessionContext()
        return self._sessions[user_id]

    def get(self, user_id: str) -> SessionContext | None:
        """Get session if exists, None otherwise."""
        return self._sessions.get(user_id)

    def clear(self, user_id: str) -> None:
        """Remove session for user."""
        if user_id in self._sessions:
            del self._sessions[user_id]

    def _cleanup_stale(self) -> None:
        """Remove sessions that haven't been active in TTL minutes."""
        cutoff = datetime.utcnow() - timedelta(minutes=SESSION_TTL_MINUTES)
        stale = [
            user_id
            for user_id, ctx in self._sessions.items()
            if ctx.last_activity < cutoff
        ]
        for user_id in stale:
            del self._sessions[user_id]


# Global session store instance
session_store = SessionStore()
