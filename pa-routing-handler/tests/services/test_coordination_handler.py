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
