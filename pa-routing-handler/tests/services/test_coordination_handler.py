"""Tests for coordination block handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for Letta API calls."""
    with patch("httpx.AsyncClient") as mock:
        client = AsyncMock()
        mock.return_value.__aenter__.return_value = client
        yield client


class TestCoordinationBlockHandler:
    """Tests for CoordinationBlockHandler."""

    @pytest.mark.asyncio
    async def test_get_or_create_block_creates_new(self, mock_httpx_client):
        """Creates new block when none exists."""
        from pa_routing.services.coordination_handler import CoordinationBlockHandler

        # Mock: no existing block found
        mock_httpx_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: []
        )
        # Mock: block creation succeeds
        mock_httpx_client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"id": "block-new-123", "label": "coordination_task_identity-abc"}
        )

        handler = CoordinationBlockHandler("http://letta:8283")
        block_id = await handler.get_or_create_block(
            label="coordination_task_identity-abc",
            initial_value="",
            description="Task context block"
        )

        assert block_id == "block-new-123"
        mock_httpx_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_block_succeeds(self, mock_httpx_client):
        """Updates block value via PATCH."""
        from pa_routing.services.coordination_handler import CoordinationBlockHandler

        mock_httpx_client.patch.return_value = MagicMock(
            status_code=200,
            json=lambda: {"id": "block-123", "value": "new value"}
        )

        handler = CoordinationBlockHandler("http://letta:8283")
        result = await handler.update_block("block-123", "new value")

        assert result is True
        mock_httpx_client.patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_block_value_returns_content(self, mock_httpx_client):
        """Retrieves block value by ID."""
        from pa_routing.services.coordination_handler import CoordinationBlockHandler

        mock_httpx_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"id": "block-123", "value": "block content", "label": "test"}
        )

        handler = CoordinationBlockHandler("http://letta:8283")
        value = await handler.get_block_value("block-123")

        assert value == "block content"

    @pytest.mark.asyncio
    async def test_get_block_by_label_returns_block(self, mock_httpx_client):
        """Retrieves block by label."""
        from pa_routing.services.coordination_handler import CoordinationBlockHandler

        mock_httpx_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"id": "block-123", "value": "content", "label": "test_label"}]
        )

        handler = CoordinationBlockHandler("http://letta:8283")
        block = await handler.get_block_by_label("test_label")

        assert block is not None
        assert block["id"] == "block-123"
        assert block["label"] == "test_label"
