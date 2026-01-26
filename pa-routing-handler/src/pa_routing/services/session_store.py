"""Hybrid session store with in-memory cache and Supabase persistence.

Architecture (2026-01-26):
- In-memory cache for fast lookups (~0ms)
- Supabase backup for persistence across restarts (~20ms hydration)
- Fire-and-forget async writes for non-blocking persistence
- Keyed by identity_id for cross-platform state sharing

Phase 1: Simple dict with user_id key.
Phase 2: Redis with TTL for persistence and expiration.
Phase 3: Hybrid persistence (in-memory + Supabase backup).
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Optional

import structlog

from pa_routing.models.session_context import SessionContext

logger = structlog.get_logger()

# Sessions expire after 1 hour of inactivity
SESSION_TTL_MINUTES = 60


class PersistentSessionStore:
    """
    Hybrid session store with in-memory cache and Supabase backup.

    Provides:
    - Fast lookups via in-memory cache (~0ms for warm cache)
    - Persistence across restarts via Supabase (~20ms hydration on cold start)
    - Fire-and-forget async writes for non-blocking operation
    - Identity-keyed storage for cross-platform state sharing
    """

    def __init__(self, supabase_client: Optional[Any] = None):
        self._cache: dict[str, SessionContext] = {}
        self._supabase = supabase_client

    def get_or_create(self, identity_id: str) -> SessionContext:
        """Get existing session or create new one."""
        self._cleanup_stale()

        # Check cache first (fast path, ~0ms)
        if identity_id in self._cache:
            return self._cache[identity_id]

        # Cache miss: try to hydrate from Supabase (~20ms, once per restart)
        ctx = self._load_from_db(identity_id)
        if ctx is None:
            ctx = SessionContext()

        self._cache[identity_id] = ctx
        return ctx

    def get(self, identity_id: str) -> Optional[SessionContext]:
        """Get session if exists, None otherwise."""
        if identity_id in self._cache:
            return self._cache[identity_id]

        # Try to load from DB if not in cache
        ctx = self._load_from_db(identity_id)
        if ctx:
            self._cache[identity_id] = ctx
        return ctx

    def clear(self, identity_id: str) -> None:
        """Remove session for identity."""
        if identity_id in self._cache:
            del self._cache[identity_id]

        # Also clear from DB
        if self._supabase:
            try:
                self._supabase.table("session_state").delete().eq(
                    "identity_id", identity_id
                ).execute()
                logger.info("session_cleared_from_db", identity_id=identity_id)
            except Exception as e:
                logger.warning("session_clear_db_failed", identity_id=identity_id, error=str(e))

    def _load_from_db(self, identity_id: str) -> Optional[SessionContext]:
        """Load session from Supabase."""
        if self._supabase is None:
            return None

        try:
            result = (
                self._supabase.table("session_state")
                .select("*")
                .eq("identity_id", identity_id)
                .execute()
            )
            if result.data:
                row = result.data[0]
                ctx = SessionContext()
                ctx.last_responding_agent_id = row.get("last_responding_agent_id")
                ctx.last_responding_agent_name = row.get("last_responding_agent_name")

                if row.get("last_response_time"):
                    # Handle ISO format with timezone
                    ts_str = row["last_response_time"]
                    if ts_str.endswith("Z"):
                        ts_str = ts_str[:-1] + "+00:00"
                    ctx.last_response_time = datetime.fromisoformat(ts_str)

                # Restore context entries (already dicts)
                for entry in row.get("context_entries", []) or []:
                    # Entries are already in correct format
                    ctx.entries.append(entry)

                logger.info(
                    "session_hydrated",
                    identity_id=identity_id,
                    entry_count=len(ctx.entries)
                )
                return ctx

        except Exception as e:
            logger.warning(
                "session_hydrate_failed",
                identity_id=identity_id,
                error=str(e)
            )

        return None

    def _persist(self, identity_id: str, ctx: SessionContext) -> None:
        """Persist session to Supabase (synchronous, for internal use)."""
        if self._supabase is None:
            return

        try:
            data = {
                "identity_id": identity_id,
                "last_responding_agent_id": ctx.last_responding_agent_id,
                "last_responding_agent_name": ctx.last_responding_agent_name,
                "last_response_time": (
                    ctx.last_response_time.isoformat() if ctx.last_response_time else None
                ),
                "context_entries": ctx.entries,  # Already list of dicts
            }

            self._supabase.table("session_state").upsert(data).execute()
            logger.debug("session_persisted", identity_id=identity_id)

        except Exception as e:
            logger.warning(
                "session_persist_failed",
                identity_id=identity_id,
                error=str(e)
            )

    def persist_async(self, identity_id: str, ctx: SessionContext) -> None:
        """Schedule async persist (non-blocking, fire-and-forget)."""
        if self._supabase is None:
            return

        # Fire-and-forget: don't await the task
        asyncio.create_task(self._persist_async(identity_id, ctx))

    async def _persist_async(self, identity_id: str, ctx: SessionContext) -> None:
        """Async wrapper for persist (runs in background)."""
        # Run in thread pool since supabase client is sync
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._persist, identity_id, ctx)

    def _cleanup_stale(self) -> None:
        """Remove sessions that haven't been active in TTL minutes."""
        cutoff = datetime.utcnow() - timedelta(minutes=SESSION_TTL_MINUTES)
        stale = [
            identity_id
            for identity_id, ctx in self._cache.items()
            if ctx.last_activity < cutoff
        ]
        for identity_id in stale:
            del self._cache[identity_id]

    def set_supabase_client(self, client: Any) -> None:
        """Set Supabase client for persistence (called during app startup)."""
        self._supabase = client
        logger.info("session_store_supabase_configured")


# Backwards compatible: SessionStore is now an alias for PersistentSessionStore
class SessionStore(PersistentSessionStore):
    """
    Session store with optional Supabase persistence.

    When no Supabase client is provided, operates as in-memory only.
    Call set_supabase_client() during app startup to enable persistence.
    """
    pass


# Global session store instance (Supabase client set during app startup)
session_store = SessionStore()
