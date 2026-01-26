"""Tests for PersistentSessionStore."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch


class TestPersistentSessionStore:
    """Tests for hybrid session store with Supabase persistence."""

    @pytest.fixture
    def mock_supabase(self):
        """Create mock Supabase client."""
        client = MagicMock()
        client.table = MagicMock(return_value=client)
        client.select = MagicMock(return_value=client)
        client.eq = MagicMock(return_value=client)
        client.upsert = MagicMock(return_value=client)
        client.delete = MagicMock(return_value=client)
        client.execute = MagicMock(return_value=MagicMock(data=[]))
        return client

    def test_get_or_create_cache_hit(self, mock_supabase):
        """Returns cached session without DB call."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore(mock_supabase)

        # First call - should check DB then create new session
        ctx1 = store.get_or_create("identity-123")
        ctx1.last_responding_agent_id = "agent-abc"

        # Second call - should return cached version
        ctx2 = store.get_or_create("identity-123")

        assert ctx2.last_responding_agent_id == "agent-abc"
        assert ctx1 is ctx2  # Same object

    def test_hydrates_from_db_on_cold_start(self, mock_supabase):
        """Hydrates session from Supabase on first access."""
        from pa_routing.services.session_store import PersistentSessionStore

        # Simulate existing DB record
        mock_supabase.execute.return_value = MagicMock(data=[{
            "identity_id": "identity-123",
            "last_responding_agent_id": "agent-abc",
            "last_responding_agent_name": "Main Agent",
            "last_response_time": "2026-01-26T12:00:00Z",
            "context_entries": [{"agent": "test", "action": "previous", "timestamp": "2026-01-26T11:00:00"}]
        }])

        store = PersistentSessionStore(mock_supabase)
        ctx = store.get_or_create("identity-123")

        assert ctx.last_responding_agent_id == "agent-abc"
        assert ctx.last_responding_agent_name == "Main Agent"
        assert ctx.entry_count == 1
        assert ctx.entries[0]["action"] == "previous"

    def test_persists_on_persist_call(self, mock_supabase):
        """Persists to Supabase when _persist is called."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore(mock_supabase)
        ctx = store.get_or_create("identity-123")
        ctx.last_responding_agent_id = "agent-new"
        ctx.append(agent="test", action="new action")

        # Call persist
        store._persist("identity-123", ctx)

        # Verify upsert was called
        mock_supabase.table.assert_called_with("session_state")
        mock_supabase.upsert.assert_called_once()

    def test_clear_removes_from_cache_and_db(self, mock_supabase):
        """Clear removes session from both cache and DB."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore(mock_supabase)
        ctx = store.get_or_create("identity-123")

        # Clear
        store.clear("identity-123")

        assert "identity-123" not in store._cache
        mock_supabase.delete.assert_called_once()
        mock_supabase.eq.assert_called_with("identity_id", "identity-123")

    def test_get_returns_none_when_not_found(self, mock_supabase):
        """Get returns None when session doesn't exist."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore(mock_supabase)
        result = store.get("nonexistent-identity")

        assert result is None

    def test_get_hydrates_from_db(self, mock_supabase):
        """Get hydrates from DB if not in cache."""
        from pa_routing.services.session_store import PersistentSessionStore

        mock_supabase.execute.return_value = MagicMock(data=[{
            "identity_id": "identity-456",
            "last_responding_agent_id": "agent-xyz",
            "last_responding_agent_name": None,
            "last_response_time": None,
            "context_entries": []
        }])

        store = PersistentSessionStore(mock_supabase)
        result = store.get("identity-456")

        assert result is not None
        assert result.last_responding_agent_id == "agent-xyz"

    def test_works_without_supabase(self):
        """Store works in memory-only mode without Supabase."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore(supabase_client=None)

        ctx = store.get_or_create("identity-789")
        ctx.append(agent="test", action="action")

        # Persist should not fail
        store._persist("identity-789", ctx)

        # Get should return from cache
        ctx2 = store.get("identity-789")
        assert ctx2 is ctx

    def test_set_supabase_client(self, mock_supabase):
        """Can set Supabase client after initialization."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore(supabase_client=None)
        assert store._supabase is None

        store.set_supabase_client(mock_supabase)
        assert store._supabase is mock_supabase

    def test_cleanup_stale_removes_old_sessions(self):
        """Cleanup removes sessions older than TTL."""
        from pa_routing.services.session_store import PersistentSessionStore, SESSION_TTL_MINUTES
        from datetime import timedelta

        store = PersistentSessionStore(supabase_client=None)

        # Create session and manually set old last_activity
        ctx = store.get_or_create("identity-old")
        ctx.last_activity = datetime.utcnow() - timedelta(minutes=SESSION_TTL_MINUTES + 10)

        # Create fresh session
        store.get_or_create("identity-fresh")

        # Trigger cleanup
        store._cleanup_stale()

        assert "identity-old" not in store._cache
        assert "identity-fresh" in store._cache


class TestSessionStoreBackwardsCompat:
    """Tests for SessionStore backwards compatibility."""

    def test_session_store_is_persistent_session_store(self):
        """SessionStore inherits from PersistentSessionStore."""
        from pa_routing.services.session_store import SessionStore, PersistentSessionStore

        assert issubclass(SessionStore, PersistentSessionStore)

    def test_global_session_store_exists(self):
        """Global session_store instance is available."""
        from pa_routing.services.session_store import session_store

        assert session_store is not None
        # Should work without Supabase configured
        ctx = session_store.get_or_create("test-global")
        assert ctx is not None
