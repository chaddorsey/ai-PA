"""Tests for PersistentSessionStore."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import json


class TestPersistentSessionStore:
    """Tests for hybrid session store with PostgREST persistence."""

    @pytest.fixture
    def mock_httpx_response(self):
        """Create a mock httpx response."""
        def _make_response(data=None, status_code=200):
            response = MagicMock()
            response.status_code = status_code
            response.json.return_value = data if data else []
            response.text = json.dumps(data) if data else "[]"
            return response
        return _make_response

    def test_get_or_create_cache_hit(self, mock_httpx_response):
        """Returns cached session without HTTP call."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore()

        # Prime the cache with first call (will try HTTP, return empty)
        with patch.object(store, '_get_http_client') as mock_client_getter:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_httpx_response([])
            mock_client_getter.return_value = mock_client

            ctx1 = store.get_or_create("identity-123")
            ctx1.last_responding_agent_id = "agent-abc"

        # Second call - should return cached version without HTTP
        ctx2 = store.get_or_create("identity-123")

        assert ctx2.last_responding_agent_id == "agent-abc"
        assert ctx1 is ctx2  # Same object

    def test_hydrates_from_db_on_cold_start(self, mock_httpx_response):
        """Hydrates session from PostgREST on first access."""
        from pa_routing.services.session_store import PersistentSessionStore

        # Simulate existing DB record
        db_data = [{
            "identity_id": "identity-123",
            "last_responding_agent_id": "agent-abc",
            "last_responding_agent_name": "Main Agent",
            "last_response_time": "2026-01-26T12:00:00Z",
            "context_entries": [{"agent": "test", "action": "previous", "timestamp": "2026-01-26T11:00:00"}]
        }]

        store = PersistentSessionStore()

        with patch.object(store, '_get_http_client') as mock_client_getter:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_httpx_response(db_data)
            mock_client_getter.return_value = mock_client

            ctx = store.get_or_create("identity-123")

        assert ctx.last_responding_agent_id == "agent-abc"
        assert ctx.last_responding_agent_name == "Main Agent"
        assert ctx.entry_count == 1
        assert ctx.entries[0]["action"] == "previous"

    def test_persists_on_persist_call(self, mock_httpx_response):
        """Persists to PostgREST when _persist is called."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore()

        with patch.object(store, '_get_http_client') as mock_client_getter:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_httpx_response([])
            mock_client.post.return_value = mock_httpx_response(status_code=201)
            mock_client_getter.return_value = mock_client

            ctx = store.get_or_create("identity-123")
            ctx.last_responding_agent_id = "agent-new"
            ctx.append(agent="test", action="new action")

            # Call persist
            store._persist("identity-123", ctx)

            # Verify HTTP POST was called with correct data
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "session_state" in call_args[0][0]
            posted_data = call_args.kwargs.get("json", {})
            assert posted_data["identity_id"] == "identity-123"
            assert posted_data["last_responding_agent_id"] == "agent-new"

    def test_clear_removes_from_cache_and_db(self, mock_httpx_response):
        """Clear removes session from both cache and DB."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore()

        with patch.object(store, '_get_http_client') as mock_client_getter:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_httpx_response([])
            mock_client.delete.return_value = mock_httpx_response(status_code=204)
            mock_client_getter.return_value = mock_client

            # Create a session
            store.get_or_create("identity-123")
            assert "identity-123" in store._cache

            # Clear
            store.clear("identity-123")

            assert "identity-123" not in store._cache
            mock_client.delete.assert_called_once()
            call_args = mock_client.delete.call_args
            assert "identity_id" in str(call_args)

    def test_get_returns_none_when_not_found(self, mock_httpx_response):
        """Get returns None when session doesn't exist."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore()

        with patch.object(store, '_get_http_client') as mock_client_getter:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_httpx_response([])
            mock_client_getter.return_value = mock_client

            result = store.get("nonexistent-identity")

        assert result is None

    def test_get_hydrates_from_db(self, mock_httpx_response):
        """Get hydrates from DB if not in cache."""
        from pa_routing.services.session_store import PersistentSessionStore

        db_data = [{
            "identity_id": "identity-456",
            "last_responding_agent_id": "agent-xyz",
            "last_responding_agent_name": None,
            "last_response_time": None,
            "context_entries": []
        }]

        store = PersistentSessionStore()

        with patch.object(store, '_get_http_client') as mock_client_getter:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_httpx_response(db_data)
            mock_client_getter.return_value = mock_client

            result = store.get("identity-456")

        assert result is not None
        assert result.last_responding_agent_id == "agent-xyz"

    def test_works_without_postgrest(self):
        """Store works in memory-only mode when PostgREST is unavailable."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore()

        # Force HTTP to fail
        with patch.object(store, '_get_http_client') as mock_client_getter:
            mock_client = MagicMock()
            mock_client.get.side_effect = Exception("Connection refused")
            mock_client.post.side_effect = Exception("Connection refused")
            mock_client_getter.return_value = mock_client

            ctx = store.get_or_create("identity-789")
            ctx.append(agent="test", action="action")

            # Persist should not raise
            store._persist("identity-789", ctx)

            # Get should return from cache
            ctx2 = store.get("identity-789")
            assert ctx2 is ctx

    def test_set_supabase_client(self):
        """Can set Supabase client after initialization (backwards compat)."""
        from pa_routing.services.session_store import PersistentSessionStore

        store = PersistentSessionStore()
        mock_client = MagicMock()

        store.set_supabase_client(mock_client)
        # Just verify it doesn't error - the client is stored for backwards compat

    def test_cleanup_stale_removes_old_sessions(self):
        """Cleanup removes sessions older than TTL."""
        from pa_routing.services.session_store import PersistentSessionStore, SESSION_TTL_MINUTES

        store = PersistentSessionStore()

        # Create sessions by directly manipulating the cache
        from pa_routing.models.session_context import SessionContext

        # Old session
        old_ctx = SessionContext()
        old_ctx.last_activity = datetime.utcnow() - timedelta(minutes=SESSION_TTL_MINUTES + 10)
        store._cache["identity-old"] = old_ctx

        # Fresh session
        fresh_ctx = SessionContext()
        fresh_ctx.last_activity = datetime.utcnow()
        store._cache["identity-fresh"] = fresh_ctx

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
        # Should work without PostgREST configured
        with patch.object(session_store, '_get_http_client') as mock:
            mock_client = MagicMock()
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = []
            mock_client.get.return_value = response
            mock.return_value = mock_client

            ctx = session_store.get_or_create("test-global")
            assert ctx is not None
