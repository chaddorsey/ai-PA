"""Tests for MCP server endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gmail_watch.mcp_server import TOOLS, router


@pytest.fixture
def app():
    """Create a test FastAPI app with the MCP router."""
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = AsyncMock()
    mock_result = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


class TestListTools:
    """Tests for GET /mcp endpoint."""

    def test_list_tools_returns_all_tools(self, client):
        """GET /mcp returns list of available tools."""
        response = client.get("/mcp")

        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert len(data["tools"]) == 4

    def test_list_tools_includes_watch_thread(self, client):
        """GET /mcp includes watch_thread tool."""
        response = client.get("/mcp")

        data = response.json()
        tool_names = [t["name"] for t in data["tools"]]
        assert "watch_thread" in tool_names

    def test_list_tools_includes_unwatch_thread(self, client):
        """GET /mcp includes unwatch_thread tool."""
        response = client.get("/mcp")

        data = response.json()
        tool_names = [t["name"] for t in data["tools"]]
        assert "unwatch_thread" in tool_names

    def test_list_tools_includes_list_watched_threads(self, client):
        """GET /mcp includes list_watched_threads tool."""
        response = client.get("/mcp")

        data = response.json()
        tool_names = [t["name"] for t in data["tools"]]
        assert "list_watched_threads" in tool_names

    def test_list_tools_includes_get_watch_status(self, client):
        """GET /mcp includes get_watch_status tool."""
        response = client.get("/mcp")

        data = response.json()
        tool_names = [t["name"] for t in data["tools"]]
        assert "get_watch_status" in tool_names

    def test_tool_definitions_have_required_fields(self, client):
        """All tools have name, description, and inputSchema."""
        response = client.get("/mcp")

        data = response.json()
        for tool in data["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"
            assert "properties" in tool["inputSchema"]


class TestCallToolWatchThread:
    """Tests for POST /mcp with watch_thread tool."""

    @pytest.mark.asyncio
    async def test_watch_thread_success(self, app, mock_session):
        """watch_thread creates a new watch."""
        mock_result = mock_session.execute.return_value
        mock_result.scalar_one_or_none.return_value = None

        with patch(
            "gmail_watch.mcp_server.get_session",
            return_value=mock_session.__aiter__(),
        ):

            async def override_session():
                yield mock_session

            app.dependency_overrides[
                __import__(
                    "gmail_watch.database", fromlist=["get_session"]
                ).get_session
            ] = override_session

            client = TestClient(app)
            response = client.post(
                "/mcp",
                json={
                    "name": "watch_thread",
                    "arguments": {
                        "thread_id": "thread_abc123",
                        "subject": "Test Subject",
                    },
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert len(data["content"]) == 1
        assert data["content"][0]["type"] == "text"

    @pytest.mark.asyncio
    async def test_watch_thread_with_recipients(self, app, mock_session):
        """watch_thread parses comma-separated recipients."""
        mock_result = mock_session.execute.return_value
        mock_result.scalar_one_or_none.return_value = None

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "watch_thread",
                "arguments": {
                    "thread_id": "thread_abc123",
                    "recipients": "user1@example.com, user2@example.com",
                },
            },
        )

        assert response.status_code == 200
        # Verify the session.add was called (indicating a new record was created)
        mock_session.add.assert_called_once()


class TestCallToolUnwatchThread:
    """Tests for POST /mcp with unwatch_thread tool."""

    @pytest.mark.asyncio
    async def test_unwatch_thread_success(self, app, mock_session):
        """unwatch_thread deactivates an existing watch."""
        mock_thread = MagicMock()
        mock_thread.is_active = True
        mock_result = mock_session.execute.return_value
        mock_result.scalar_one_or_none.return_value = mock_thread

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "unwatch_thread",
                "arguments": {"thread_id": "thread_abc123"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert "ok" in data["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_unwatch_thread_not_found(self, app, mock_session):
        """unwatch_thread returns not_found for unknown thread."""
        mock_result = mock_session.execute.return_value
        mock_result.scalar_one_or_none.return_value = None

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "unwatch_thread",
                "arguments": {"thread_id": "thread_unknown"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "not_found" in data["content"][0]["text"]


class TestCallToolListWatchedThreads:
    """Tests for POST /mcp with list_watched_threads tool."""

    @pytest.mark.asyncio
    async def test_list_watched_threads_success(self, app, mock_session):
        """list_watched_threads returns list of threads."""
        mock_result = mock_session.execute.return_value
        mock_result.scalars.return_value.all.return_value = []

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "list_watched_threads",
                "arguments": {},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        import json
        result = json.loads(data["content"][0]["text"])
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_list_watched_threads_with_filters(self, app, mock_session):
        """list_watched_threads accepts include_inactive and include_replied."""
        mock_result = mock_session.execute.return_value
        mock_result.scalars.return_value.all.return_value = []

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "list_watched_threads",
                "arguments": {
                    "include_inactive": True,
                    "include_replied": True,
                },
            },
        )

        assert response.status_code == 200


class TestCallToolGetWatchStatus:
    """Tests for POST /mcp with get_watch_status tool."""

    @pytest.mark.asyncio
    async def test_get_watch_status_success(self, app, mock_session):
        """get_watch_status returns thread details."""
        mock_thread = MagicMock()
        mock_thread.thread_id = "thread_abc123"
        mock_thread.subject = "Test Subject"
        mock_thread.is_active = True
        mock_thread.reply_received = False
        mock_thread.reply_received_at = None
        mock_thread.created_at = MagicMock()
        mock_thread.created_at.isoformat.return_value = "2026-02-01T00:00:00"
        mock_thread.followup_seconds = 259200
        mock_thread.source = "manual"
        mock_thread.bcc_address = None
        mock_thread.followup_due_at = None
        mock_thread.followup_notified = False
        mock_thread.message_count = 1
        mock_thread.extra_data = None

        mock_result = mock_session.execute.return_value
        mock_result.scalar_one_or_none.return_value = mock_thread

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "get_watch_status",
                "arguments": {"thread_id": "thread_abc123"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert "thread_abc123" in data["content"][0]["text"]
        assert "Test Subject" in data["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_get_watch_status_not_found(self, app, mock_session):
        """get_watch_status returns not_found for unknown thread."""
        mock_result = mock_session.execute.return_value
        mock_result.scalar_one_or_none.return_value = None

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "get_watch_status",
                "arguments": {"thread_id": "thread_unknown"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "not_found" in data["content"][0]["text"]


class TestCallToolUnknown:
    """Tests for POST /mcp with unknown tool."""

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, app, mock_session):
        """Unknown tool name returns error response."""

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "unknown_tool",
                "arguments": {},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert "error" in data["content"][0]["text"]
        assert "Unknown tool: unknown_tool" in data["content"][0]["text"]


class TestInputValidation:
    """Tests for input validation in call_tool endpoint."""

    @pytest.mark.asyncio
    async def test_watch_thread_missing_thread_id(self, app, mock_session):
        """watch_thread returns error when thread_id is missing."""

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "watch_thread",
                "arguments": {"subject": "Test Subject"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        # Response should be valid JSON
        import json
        result = json.loads(data["content"][0]["text"])
        assert result["status"] == "error"
        assert "thread_id is required" in result["error"]

    @pytest.mark.asyncio
    async def test_watch_thread_empty_thread_id(self, app, mock_session):
        """watch_thread returns error when thread_id is empty string."""

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "watch_thread",
                "arguments": {"thread_id": "", "subject": "Test Subject"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        import json
        result = json.loads(data["content"][0]["text"])
        assert result["status"] == "error"
        assert "thread_id is required" in result["error"]

    @pytest.mark.asyncio
    async def test_unwatch_thread_missing_thread_id(self, app, mock_session):
        """unwatch_thread returns error when thread_id is missing."""

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "unwatch_thread",
                "arguments": {},
            },
        )

        assert response.status_code == 200
        data = response.json()
        import json
        result = json.loads(data["content"][0]["text"])
        assert result["status"] == "error"
        assert "thread_id is required" in result["error"]

    @pytest.mark.asyncio
    async def test_get_watch_status_missing_thread_id(self, app, mock_session):
        """get_watch_status returns error when thread_id is missing."""

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "get_watch_status",
                "arguments": {},
            },
        )

        assert response.status_code == 200
        data = response.json()
        import json
        result = json.loads(data["content"][0]["text"])
        assert result["status"] == "error"
        assert "thread_id is required" in result["error"]


class TestExceptionHandling:
    """Tests for exception handling in call_tool endpoint."""

    @pytest.mark.asyncio
    async def test_registry_exception_returns_error(self, app, mock_session):
        """Exception from registry returns error response instead of 500."""
        mock_session.execute = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "watch_thread",
                "arguments": {"thread_id": "thread_abc123"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        import json
        result = json.loads(data["content"][0]["text"])
        assert result["status"] == "error"
        assert "Database connection failed" in result["error"]

    @pytest.mark.asyncio
    async def test_list_watched_exception_returns_error(self, app, mock_session):
        """Exception from list_watched returns error response."""
        mock_session.execute = AsyncMock(side_effect=Exception("Query timeout"))

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "list_watched_threads",
                "arguments": {},
            },
        )

        assert response.status_code == 200
        data = response.json()
        import json
        result = json.loads(data["content"][0]["text"])
        assert result["status"] == "error"
        assert "Query timeout" in result["error"]


class TestJsonOutput:
    """Tests for JSON output formatting."""

    @pytest.mark.asyncio
    async def test_response_is_valid_json(self, app, mock_session):
        """Response text content is valid JSON."""
        mock_result = mock_session.execute.return_value
        mock_result.scalars.return_value.all.return_value = []

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "list_watched_threads",
                "arguments": {},
            },
        )

        assert response.status_code == 200
        data = response.json()
        import json
        # Should not raise - text should be valid JSON
        result = json.loads(data["content"][0]["text"])
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_error_response_is_valid_json(self, app, mock_session):
        """Error response text content is valid JSON."""

        async def override_session():
            yield mock_session

        from gmail_watch.database import get_session

        app.dependency_overrides[get_session] = override_session

        client = TestClient(app)
        response = client.post(
            "/mcp",
            json={
                "name": "unknown_tool",
                "arguments": {},
            },
        )

        assert response.status_code == 200
        data = response.json()
        import json
        # Should not raise - text should be valid JSON
        result = json.loads(data["content"][0]["text"])
        assert result["status"] == "error"
        assert "Unknown tool" in result["error"]


class TestToolDefinitions:
    """Tests for TOOLS constant."""

    def test_tools_count(self):
        """TOOLS contains exactly 4 tools."""
        assert len(TOOLS) == 4

    def test_watch_thread_schema(self):
        """watch_thread tool has correct schema."""
        watch_tool = next(t for t in TOOLS if t["name"] == "watch_thread")
        assert watch_tool["inputSchema"]["required"] == ["thread_id"]
        assert "thread_id" in watch_tool["inputSchema"]["properties"]
        assert "subject" in watch_tool["inputSchema"]["properties"]
        assert "recipients" in watch_tool["inputSchema"]["properties"]
        assert "followup_interval" in watch_tool["inputSchema"]["properties"]
        assert "context" in watch_tool["inputSchema"]["properties"]

    def test_unwatch_thread_schema(self):
        """unwatch_thread tool has correct schema."""
        unwatch_tool = next(t for t in TOOLS if t["name"] == "unwatch_thread")
        assert unwatch_tool["inputSchema"]["required"] == ["thread_id"]
        assert "thread_id" in unwatch_tool["inputSchema"]["properties"]

    def test_list_watched_threads_schema(self):
        """list_watched_threads tool has correct schema."""
        list_tool = next(t for t in TOOLS if t["name"] == "list_watched_threads")
        # No required fields
        assert "required" not in list_tool["inputSchema"]
        assert "include_inactive" in list_tool["inputSchema"]["properties"]
        assert "include_replied" in list_tool["inputSchema"]["properties"]

    def test_get_watch_status_schema(self):
        """get_watch_status tool has correct schema."""
        status_tool = next(t for t in TOOLS if t["name"] == "get_watch_status")
        assert status_tool["inputSchema"]["required"] == ["thread_id"]
        assert "thread_id" in status_tool["inputSchema"]["properties"]
