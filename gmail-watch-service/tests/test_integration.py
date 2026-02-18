"""Integration tests for Gmail watch service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_scheduler():
    """Mock the watch scheduler."""
    with patch("gmail_watch.main.watch_scheduler") as mock_sched:
        mock_sched.start = AsyncMock()
        mock_sched.stop = AsyncMock()
        mock_sched.is_running = True
        yield mock_sched


@pytest.fixture
def mock_database():
    """Mock database session."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    async def mock_get_session():
        yield mock_session

    with patch("gmail_watch.main.get_session", mock_get_session):
        with patch("gmail_watch.mcp_server.get_session", mock_get_session):
            yield mock_session


@pytest.fixture
def client(mock_scheduler, mock_database):
    """Create test client with mocked dependencies."""
    from gmail_watch.main import create_app

    app = create_app()
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_ok(self, client):
        """Health endpoint returns status ok."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_returns_service_name(self, client):
        """Health endpoint returns service name."""
        response = client.get("/health")

        data = response.json()
        assert data["service"] == "gmail-watch-service"

    def test_health_returns_scheduler_status(self, client):
        """Health endpoint returns scheduler running status."""
        response = client.get("/health")

        data = response.json()
        assert "scheduler_running" in data
        assert data["scheduler_running"] is True


class TestMCPListTools:
    """Tests for MCP tools listing."""

    def test_mcp_returns_tools_list(self, client):
        """GET /mcp returns list of tools."""
        response = client.get("/mcp")

        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert isinstance(data["tools"], list)

    def test_mcp_includes_watch_thread(self, client):
        """MCP tools include watch_thread."""
        response = client.get("/mcp")

        data = response.json()
        tool_names = [t["name"] for t in data["tools"]]
        assert "watch_thread" in tool_names

    def test_mcp_includes_unwatch_thread(self, client):
        """MCP tools include unwatch_thread."""
        response = client.get("/mcp")

        data = response.json()
        tool_names = [t["name"] for t in data["tools"]]
        assert "unwatch_thread" in tool_names

    def test_mcp_includes_list_watched_threads(self, client):
        """MCP tools include list_watched_threads."""
        response = client.get("/mcp")

        data = response.json()
        tool_names = [t["name"] for t in data["tools"]]
        assert "list_watched_threads" in tool_names

    def test_mcp_includes_get_watch_status(self, client):
        """MCP tools include get_watch_status."""
        response = client.get("/mcp")

        data = response.json()
        tool_names = [t["name"] for t in data["tools"]]
        assert "get_watch_status" in tool_names

    def test_mcp_tools_have_complete_definitions(self, client):
        """All MCP tools have name, description, and inputSchema."""
        response = client.get("/mcp")

        data = response.json()
        for tool in data["tools"]:
            assert "name" in tool, f"Tool missing 'name': {tool}"
            assert "description" in tool, f"Tool {tool['name']} missing 'description'"
            assert "inputSchema" in tool, f"Tool {tool['name']} missing 'inputSchema'"
            assert tool["inputSchema"]["type"] == "object"
            assert "properties" in tool["inputSchema"]


class TestAppStructure:
    """Tests for application structure."""

    def test_app_title(self, client):
        """App has correct title."""
        assert client.app.title == "gmail-watch-service"

    def test_mcp_router_mounted(self, client):
        """MCP router is mounted at /mcp."""
        routes = [route.path for route in client.app.routes]
        assert "/mcp" in routes
