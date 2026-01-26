"""Integration tests for routing handler conversations.

These tests verify the end-to-end flow of identity resolution
and conversation lookup in the routing handler.

Note: Some tests require live services to be running.
Tests marked with @pytest.mark.live require:
- Routing handler running on localhost:5201
- Letta running on localhost:8283
- Supabase running on localhost:5432
"""

import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4


class TestRouteResponseFields:
    """Tests for identity and conversation fields in route response."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings with default identity ID."""
        with patch("pa_routing.routers.routing.settings") as mock:
            mock.default_identity_id = "identity-test-default"
            mock.default_agent_id = "agent-test-default"
            yield mock

    @pytest.fixture
    def mock_letta_client(self):
        """Mock Letta client for archival operations."""
        with patch("pa_routing.routers.routing._letta_client") as mock:
            mock.list_passages = AsyncMock(return_value=[])
            mock.format_briefing = MagicMock(return_value=None)
            yield mock

    @pytest.fixture
    def mock_selector(self):
        """Mock agent selector."""
        with patch("pa_routing.routers.routing._selector") as mock:
            result = MagicMock()
            result.agent_id = "agent-123"
            result.agent_name = "Test Agent"
            result.tier = 6
            result.confidence = 0.5
            result.reason = "default fallback"
            mock.select_detailed.return_value = result
            yield mock

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session."""
        with patch("pa_routing.routers.routing.get_db_session") as mock:
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock.return_value = mock_session
            yield mock

    @pytest.fixture
    def mock_identities_cache(self):
        """Mock identities fetch to avoid HTTP calls."""
        with patch("pa_routing.routers.routing._fetch_identities") as mock:
            mock.return_value = []
            yield mock

    @pytest.mark.asyncio
    async def test_route_returns_identity_id_from_default(
        self, mock_settings, mock_letta_client, mock_selector,
        mock_db_session, mock_identities_cache
    ):
        """Route response includes identity_id when using default."""
        from pa_routing.routers.routing import route_message
        from pa_routing.models.requests import RouteRequest

        request = RouteRequest(
            session_id=uuid4(),
            message="test message"
        )

        response = await route_message(request)

        assert response.identity_id == "identity-test-default"

    @pytest.mark.asyncio
    async def test_route_returns_none_identity_when_no_default(
        self, mock_letta_client, mock_selector, mock_db_session, mock_identities_cache
    ):
        """Route response returns None for identity_id when no default configured."""
        from pa_routing.routers.routing import route_message
        from pa_routing.models.requests import RouteRequest

        with patch("pa_routing.routers.routing.settings") as mock_settings:
            mock_settings.default_identity_id = None
            mock_settings.default_agent_id = "agent-test"

            request = RouteRequest(
                session_id=uuid4(),
                message="test message"
            )

            response = await route_message(request)

        assert response.identity_id is None

    @pytest.mark.asyncio
    async def test_route_returns_conversation_id_when_found(
        self, mock_settings, mock_letta_client, mock_selector,
        mock_db_session, mock_identities_cache
    ):
        """Route response includes conversation_id when lookup succeeds."""
        from pa_routing.routers.routing import route_message, set_supabase_client
        from pa_routing.models.requests import RouteRequest

        # Mock Supabase client for conversation lookup
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = mock_supabase
        mock_supabase.select.return_value = mock_supabase
        mock_supabase.eq.return_value = mock_supabase
        mock_supabase.execute.return_value = MagicMock(
            data=[{"conversation_id": "conv-123"}]
        )

        set_supabase_client(mock_supabase)

        try:
            request = RouteRequest(
                session_id=uuid4(),
                message="test message"
            )

            response = await route_message(request)

            assert response.conversation_id == "conv-123"
        finally:
            # Clean up
            set_supabase_client(None)

    @pytest.mark.asyncio
    async def test_route_returns_none_conversation_when_not_found(
        self, mock_settings, mock_letta_client, mock_selector,
        mock_db_session, mock_identities_cache
    ):
        """Route response returns None for conversation_id when not found."""
        from pa_routing.routers.routing import route_message, set_supabase_client
        from pa_routing.models.requests import RouteRequest

        # Mock Supabase client returning empty result
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = mock_supabase
        mock_supabase.select.return_value = mock_supabase
        mock_supabase.eq.return_value = mock_supabase
        mock_supabase.execute.return_value = MagicMock(data=[])

        set_supabase_client(mock_supabase)

        try:
            request = RouteRequest(
                session_id=uuid4(),
                message="test message"
            )

            response = await route_message(request)

            assert response.conversation_id is None
        finally:
            set_supabase_client(None)

    @pytest.mark.asyncio
    async def test_route_handles_supabase_error_gracefully(
        self, mock_settings, mock_letta_client, mock_selector,
        mock_db_session, mock_identities_cache
    ):
        """Route continues even when Supabase lookup fails."""
        from pa_routing.routers.routing import route_message, set_supabase_client
        from pa_routing.models.requests import RouteRequest

        # Mock Supabase client that raises an error
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = mock_supabase
        mock_supabase.select.return_value = mock_supabase
        mock_supabase.eq.return_value = mock_supabase
        mock_supabase.execute.side_effect = Exception("DB connection failed")

        set_supabase_client(mock_supabase)

        try:
            request = RouteRequest(
                session_id=uuid4(),
                message="test message"
            )

            # Should not raise, just return None for conversation_id
            response = await route_message(request)

            assert response.conversation_id is None
            assert response.agent_id == "agent-123"  # Routing still works
        finally:
            set_supabase_client(None)


class TestIdentityResolutionByPlatform:
    """Tests for identity resolution with platform credentials."""

    @pytest.fixture
    def mock_identities_list(self):
        """Sample identities list with platform properties."""
        return [
            {
                "id": "identity-chad",
                "name": "Chad",
                "properties": [
                    {"key": "telegram_id", "value": "123456"},
                    {"key": "slack_id", "value": "U12345"},
                ]
            },
            {
                "id": "identity-other",
                "name": "Other User",
                "properties": [
                    {"key": "telegram_id", "value": "999999"},
                ]
            }
        ]

    @pytest.mark.asyncio
    async def test_resolves_identity_by_telegram_id(self, mock_identities_list):
        """Identity resolved when telegram platform provided."""
        from pa_routing.routers.routing import resolve_identity

        with patch("pa_routing.routers.routing._fetch_identities") as mock_fetch:
            mock_fetch.return_value = mock_identities_list

            result = await resolve_identity(
                platform="telegram",
                platform_id="123456",
                default_identity_id=None
            )

        assert result == "identity-chad"

    @pytest.mark.asyncio
    async def test_resolves_identity_by_slack_id(self, mock_identities_list):
        """Identity resolved when slack platform provided."""
        from pa_routing.routers.routing import resolve_identity

        with patch("pa_routing.routers.routing._fetch_identities") as mock_fetch:
            mock_fetch.return_value = mock_identities_list

            result = await resolve_identity(
                platform="slack",
                platform_id="U12345",
                default_identity_id=None
            )

        assert result == "identity-chad"

    @pytest.mark.asyncio
    async def test_falls_back_to_default_when_not_found(self, mock_identities_list):
        """Falls back to default identity when platform lookup fails."""
        from pa_routing.routers.routing import resolve_identity

        with patch("pa_routing.routers.routing._fetch_identities") as mock_fetch:
            mock_fetch.return_value = mock_identities_list

            result = await resolve_identity(
                platform="telegram",
                platform_id="nonexistent",
                default_identity_id="identity-fallback"
            )

        assert result == "identity-fallback"


class TestSessionPersistence:
    """Tests for session state persistence."""

    def test_session_persists_to_supabase(self):
        """Session state is persisted to Supabase."""
        from pa_routing.services.session_store import PersistentSessionStore

        mock_supabase = MagicMock()
        mock_supabase.table.return_value = mock_supabase
        mock_supabase.select.return_value = mock_supabase
        mock_supabase.eq.return_value = mock_supabase
        mock_supabase.upsert.return_value = mock_supabase
        mock_supabase.execute.return_value = MagicMock(data=[])

        store = PersistentSessionStore(mock_supabase)

        # Create and modify session
        ctx = store.get_or_create("identity-test")
        ctx.last_responding_agent_id = "agent-123"
        ctx.append(agent="Test", action="did something")

        # Persist
        store._persist("identity-test", ctx)

        # Verify upsert was called
        mock_supabase.table.assert_called_with("session_state")
        mock_supabase.upsert.assert_called_once()

    def test_session_hydrates_from_supabase(self):
        """Session state is hydrated from Supabase on cold start."""
        from pa_routing.services.session_store import PersistentSessionStore

        mock_supabase = MagicMock()
        mock_supabase.table.return_value = mock_supabase
        mock_supabase.select.return_value = mock_supabase
        mock_supabase.eq.return_value = mock_supabase
        mock_supabase.execute.return_value = MagicMock(data=[{
            "identity_id": "identity-test",
            "last_responding_agent_id": "agent-restored",
            "last_responding_agent_name": "Restored Agent",
            "last_response_time": "2026-01-26T12:00:00Z",
            "context_entries": [
                {"agent": "Test", "action": "previous action", "timestamp": "2026-01-26T11:00:00"}
            ]
        }])

        store = PersistentSessionStore(mock_supabase)
        ctx = store.get_or_create("identity-test")

        assert ctx.last_responding_agent_id == "agent-restored"
        assert ctx.last_responding_agent_name == "Restored Agent"
        assert ctx.entry_count == 1


# Mark tests that require live services
@pytest.mark.live
class TestLiveIntegration:
    """Tests that require live services.

    Run with: pytest -m live tests/integration/
    """

    @pytest.fixture
    def live_client(self):
        """Create HTTP client for live service tests."""
        import httpx
        return httpx.Client(base_url="http://localhost:5201", timeout=30.0)

    def test_route_endpoint_returns_identity_fields(self, live_client):
        """Live test: route endpoint returns identity and conversation fields."""
        response = live_client.post("/v1/route", json={
            "session_id": str(uuid4()),
            "message": "test message"
        })
        assert response.status_code == 200
        data = response.json()

        # Verify fields exist (may be None depending on config)
        assert "identity_id" in data
        assert "conversation_id" in data

    def test_session_context_persists_across_requests(self, live_client):
        """Live test: session context persists between requests."""
        session_id = str(uuid4())

        # First request
        response1 = live_client.post("/v1/route", json={
            "session_id": session_id,
            "message": "hello"
        })
        assert response1.status_code == 200
        request_id = response1.json().get("request_id")

        # Complete the thread
        if request_id:
            live_client.post(
                f"/v1/sessions/{session_id}/threads/{request_id}/complete",
                params={
                    "agent_id": "test-agent",
                    "agent_name": "Test Agent",
                    "response_content": "Hi there!"
                }
            )

        # Second request - should have context
        response2 = live_client.post("/v1/route", json={
            "session_id": session_id,
            "message": "what did you say?"
        })
        assert response2.status_code == 200
        data2 = response2.json()

        # Should have session context from first request
        assert data2.get("session_context_entries", 0) > 0
