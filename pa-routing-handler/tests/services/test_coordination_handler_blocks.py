"""Tests for coordination block attachment functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestBlockAttachment:
    """Tests for block attachment/detachment methods."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        from pa_routing.services.coordination_handler import CoordinationBlockHandler

        return CoordinationBlockHandler("http://localhost:8283")

    @pytest.mark.asyncio
    async def test_attach_block_to_agent_success(self, handler):
        """attach_block_to_agent returns True on success."""
        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.post.return_value = mock_response

            result = await handler.attach_block_to_agent("block-123", "agent-456")

            assert result is True
            mock_client.post.assert_called_once_with(
                "http://localhost:8283/v1/agents/agent-456/memory/blocks/block-123"
            )

    @pytest.mark.asyncio
    async def test_attach_block_to_agent_failure(self, handler):
        """attach_block_to_agent returns False on non-200 response."""
        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_client.post.return_value = mock_response

            result = await handler.attach_block_to_agent("block-123", "agent-456")

            assert result is False

    @pytest.mark.asyncio
    async def test_attach_block_to_agent_handles_exception(self, handler):
        """attach_block_to_agent returns False on exception."""
        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = Exception("Connection error")

            result = await handler.attach_block_to_agent("block-123", "agent-456")

            assert result is False

    @pytest.mark.asyncio
    async def test_detach_block_from_agent_success(self, handler):
        """detach_block_from_agent returns True on success."""
        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.delete.return_value = mock_response

            result = await handler.detach_block_from_agent("block-123", "agent-456")

            assert result is True
            mock_client.delete.assert_called_once_with(
                "http://localhost:8283/v1/agents/agent-456/memory/blocks/block-123"
            )

    @pytest.mark.asyncio
    async def test_detach_block_from_agent_failure(self, handler):
        """detach_block_from_agent returns False on non-200 response."""
        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_client.delete.return_value = mock_response

            result = await handler.detach_block_from_agent("block-123", "agent-456")

            assert result is False


class TestStartCoordinatedTaskBlockAttachment:
    """Tests for block attachment during task start."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        from pa_routing.services.coordination_handler import CoordinationBlockHandler

        return CoordinationBlockHandler("http://localhost:8283")

    @pytest.mark.asyncio
    async def test_start_coordinated_task_attaches_blocks_when_agent_ids_provided(
        self, handler
    ):
        """start_coordinated_task attaches blocks to agents when agent_ids provided."""
        blocks_created = []
        blocks_attached = []

        async def mock_get_or_create_block(label, initial_value="", description=""):
            block_id = f"block-{label}"
            blocks_created.append(label)
            return block_id

        async def mock_update_block(block_id, value):
            return True

        async def mock_attach_block(block_id, agent_id):
            blocks_attached.append((block_id, agent_id))
            return True

        handler.get_or_create_block = mock_get_or_create_block
        handler.update_block = mock_update_block
        handler.attach_block_to_agent = mock_attach_block

        task_id = await handler.start_coordinated_task(
            identity_id="identity-123",
            task_type="meeting_prep",
            title="Test Meeting",
            required_agents=["calendar", "email"],
            agent_ids={"calendar": "agent-cal", "email": "agent-email"},
        )

        assert task_id is not None
        # Should attach task and gathered blocks to each agent
        assert ("block-coordination_task_identity-123", "agent-cal") in blocks_attached
        assert ("block-coordination_gathered_identity-123", "agent-cal") in blocks_attached
        assert ("block-coordination_task_identity-123", "agent-email") in blocks_attached
        assert ("block-coordination_gathered_identity-123", "agent-email") in blocks_attached

    @pytest.mark.asyncio
    async def test_start_coordinated_task_skips_attachment_without_agent_ids(
        self, handler
    ):
        """start_coordinated_task does not attach blocks when agent_ids not provided."""
        blocks_attached = []

        async def mock_get_or_create_block(label, initial_value="", description=""):
            return f"block-{label}"

        async def mock_update_block(block_id, value):
            return True

        async def mock_attach_block(block_id, agent_id):
            blocks_attached.append((block_id, agent_id))
            return True

        handler.get_or_create_block = mock_get_or_create_block
        handler.update_block = mock_update_block
        handler.attach_block_to_agent = mock_attach_block

        task_id = await handler.start_coordinated_task(
            identity_id="identity-123",
            task_type="meeting_prep",
            title="Test Meeting",
            required_agents=["calendar"],
            agent_ids=None,  # No agent_ids provided
        )

        assert task_id is not None
        assert len(blocks_attached) == 0


class TestCompleteTaskBlockDetachment:
    """Tests for block detachment during task completion."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        from pa_routing.services.coordination_handler import CoordinationBlockHandler

        return CoordinationBlockHandler("http://localhost:8283")

    @pytest.mark.asyncio
    async def test_complete_task_detaches_blocks_when_agent_ids_provided(self, handler):
        """complete_task detaches blocks from agents when agent_ids provided."""
        blocks_detached = []

        async def mock_get_block_by_label(label):
            return {"id": f"block-{label}", "value": "test content"}

        async def mock_update_block(block_id, value):
            return True

        async def mock_detach_block(block_id, agent_id):
            blocks_detached.append((block_id, agent_id))
            return True

        handler.get_block_by_label = mock_get_block_by_label
        handler.update_block = mock_update_block
        handler.detach_block_from_agent = mock_detach_block

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.post.return_value = mock_response

            await handler.complete_task(
                identity_id="identity-123",
                main_agent_id="main-agent",
                agent_ids={"calendar": "agent-cal", "email": "agent-email"},
            )

        # Should detach task and gathered blocks from each agent
        assert ("block-coordination_task_identity-123", "agent-cal") in blocks_detached
        assert ("block-coordination_gathered_identity-123", "agent-cal") in blocks_detached
        assert ("block-coordination_task_identity-123", "agent-email") in blocks_detached
        assert ("block-coordination_gathered_identity-123", "agent-email") in blocks_detached

    @pytest.mark.asyncio
    async def test_complete_task_skips_detachment_without_agent_ids(self, handler):
        """complete_task does not detach blocks when agent_ids not provided."""
        blocks_detached = []

        async def mock_get_block_by_label(label):
            return {"id": f"block-{label}", "value": "test content"}

        async def mock_update_block(block_id, value):
            return True

        async def mock_detach_block(block_id, agent_id):
            blocks_detached.append((block_id, agent_id))
            return True

        handler.get_block_by_label = mock_get_block_by_label
        handler.update_block = mock_update_block
        handler.detach_block_from_agent = mock_detach_block

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.post.return_value = mock_response

            await handler.complete_task(
                identity_id="identity-123",
                main_agent_id="main-agent",
                agent_ids=None,  # No agent_ids provided
            )

        assert len(blocks_detached) == 0
