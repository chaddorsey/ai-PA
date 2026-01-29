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

    @pytest.mark.asyncio
    async def test_start_coordinated_task_creates_three_blocks(self, mock_httpx_client):
        """Starting task creates task, gathered, and status blocks."""
        from pa_routing.services.coordination_handler import CoordinationBlockHandler

        created_blocks = []

        def track_post(*args, **kwargs):
            label = kwargs.get("json", {}).get("label", "")
            block_id = f"block-{len(created_blocks)}"
            created_blocks.append(label)
            return MagicMock(
                status_code=200,
                json=lambda bid=block_id: {"id": bid, "label": label}
            )

        mock_httpx_client.get.return_value = MagicMock(status_code=200, json=lambda: [])
        mock_httpx_client.post.side_effect = track_post
        mock_httpx_client.patch.return_value = MagicMock(status_code=200, json=lambda: {})

        handler = CoordinationBlockHandler("http://letta:8283")
        task_id = await handler.start_coordinated_task(
            identity_id="identity-abc",
            task_type="meeting_prep",
            title="Board Meeting",
            event_id="event-123",
            participants=["Alice", "Bob"],
            required_agents=["calendar", "email"]
        )

        assert task_id is not None
        assert "task-meeting_prep-" in task_id
        assert len(created_blocks) == 3
        assert any("coordination_task_" in label for label in created_blocks)
        assert any("coordination_gathered_" in label for label in created_blocks)
        assert any("coordination_status_" in label for label in created_blocks)
