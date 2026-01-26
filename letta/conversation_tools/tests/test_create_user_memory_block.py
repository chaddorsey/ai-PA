"""Tests for create_user_memory_block tool."""

import importlib
import pytest
from unittest.mock import patch, MagicMock

# Import the module properly to enable patching
create_block_module = importlib.import_module('letta.conversation_tools.create_user_memory_block')


class TestCreateUserMemoryBlock:
    """Tests for user memory block creation via naming conventions."""

    def test_returns_error_for_invalid_user_id_format(self):
        """Tool validates user_id format to prevent injection."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        result = create_user_memory_block(
            user_id="user_a; DROP TABLE",
            category="preferences",
            value="Test value"
        )

        assert "error" in result
        assert "Invalid user_id format" in result["error"]

    def test_returns_error_for_invalid_category_format(self):
        """Tool validates category format."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        result = create_user_memory_block(
            user_id="user_a",
            category="bad category!",
            value="Test value"
        )

        assert "error" in result
        assert "Invalid category format" in result["error"]

    def test_returns_error_for_value_too_long(self):
        """Tool rejects values over 2000 characters."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        result = create_user_memory_block(
            user_id="user_a",
            category="preferences",
            value="x" * 2001
        )

        assert "error" in result
        assert "too long" in result["error"]

    def test_builds_cross_agent_label(self):
        """Tool builds correct label for cross-agent blocks."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.id = "block-123"
        mock_client.blocks.create.return_value = mock_block
        mock_client.agents.blocks.attach.return_value = None

        with patch.object(create_block_module, "_get_letta_client", return_value=mock_client):
            with patch.object(create_block_module, "LETTA_AGENT_ID", "agent-test"):
                result = create_user_memory_block(
                    user_id="user_a",
                    category="preferences",
                    value="Prefers 30 minute meetings",
                    purpose="meeting_duration",
                    agent_specific=False
                )

        assert result["label"] == "preferences_user_a_meeting_duration"
        assert result["block_id"] == "block-123"

    def test_builds_agent_specific_label(self):
        """Tool builds correct label for agent-specific blocks."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.id = "block-456"
        mock_client.blocks.create.return_value = mock_block
        mock_client.agents.blocks.attach.return_value = None

        with patch.object(create_block_module, "_get_letta_client", return_value=mock_client):
            with patch.object(create_block_module, "LETTA_AGENT_ID", "agent-test"):
                with patch.object(create_block_module, "AGENT_NAME", "meeting_scheduler"):
                    result = create_user_memory_block(
                        user_id="user_a",
                        category="preferences",
                        value="Blocks mornings for deep work",
                        purpose="deep_work",
                        agent_specific=True
                    )

        assert result["label"] == "meeting_scheduler_preferences_user_a_deep_work"
        assert result["block_id"] == "block-456"

    def test_builds_label_without_purpose(self):
        """Tool builds correct label when purpose is not provided."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.id = "block-789"
        mock_client.blocks.create.return_value = mock_block
        mock_client.agents.blocks.attach.return_value = None

        with patch.object(create_block_module, "_get_letta_client", return_value=mock_client):
            with patch.object(create_block_module, "LETTA_AGENT_ID", "agent-test"):
                result = create_user_memory_block(
                    user_id="user_a",
                    category="calendar",
                    value="Calendar synced with Google",
                    agent_specific=False
                )

        assert result["label"] == "calendar_user_a"
        assert result["block_id"] == "block-789"

    def test_attaches_block_to_agent(self):
        """Tool attaches created block to the agent."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.id = "block-attach-test"
        mock_client.blocks.create.return_value = mock_block
        mock_client.agents.blocks.attach.return_value = None

        with patch.object(create_block_module, "_get_letta_client", return_value=mock_client):
            with patch.object(create_block_module, "LETTA_AGENT_ID", "agent-test-123"):
                create_user_memory_block(
                    user_id="user_a",
                    category="preferences",
                    value="Test value"
                )

        # Verify attach was called with correct parameters
        mock_client.agents.blocks.attach.assert_called_once_with(
            agent_id="agent-test-123",
            block_id="block-attach-test"
        )

    def test_handles_api_error(self):
        """Tool returns error dict when API fails."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        mock_client = MagicMock()
        mock_client.blocks.create.side_effect = Exception("API connection failed")

        with patch.object(create_block_module, "_get_letta_client", return_value=mock_client):
            result = create_user_memory_block(
                user_id="user_a",
                category="preferences",
                value="Test value"
            )

        assert "error" in result
        assert "API connection failed" in result["error"]

    def test_returns_error_when_no_client(self):
        """Tool returns error when Letta client unavailable."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        with patch.object(create_block_module, "_get_letta_client", return_value=None):
            result = create_user_memory_block(
                user_id="user_a",
                category="preferences",
                value="Test value"
            )

        assert "error" in result
        assert "client not available" in result["error"].lower()
