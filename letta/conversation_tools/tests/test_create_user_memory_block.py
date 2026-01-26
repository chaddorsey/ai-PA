"""Tests for create_user_memory_block tool."""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock


class TestCreateUserMemoryBlock:
    """Tests for user memory block creation via naming conventions."""

    @pytest.fixture(autouse=True)
    def setup_letta_mock(self):
        """Set up letta_client mock in sys.modules before each test."""
        # Create a mock letta_client module
        self.mock_letta_module = MagicMock()
        self.mock_client = MagicMock()
        self.mock_letta_module.Letta.return_value = self.mock_client

        # Save original if it exists
        self.original_letta_client = sys.modules.get('letta_client')
        self.original_letta = sys.modules.get('letta')

        # Install mock
        sys.modules['letta_client'] = self.mock_letta_module
        sys.modules['letta'] = self.mock_letta_module

        yield

        # Restore original
        if self.original_letta_client is not None:
            sys.modules['letta_client'] = self.original_letta_client
        elif 'letta_client' in sys.modules:
            del sys.modules['letta_client']

        if self.original_letta is not None:
            sys.modules['letta'] = self.original_letta
        elif 'letta' in sys.modules:
            del sys.modules['letta']

    def test_returns_error_for_invalid_user_id_format(self):
        """Tool validates user_id format to prevent injection."""
        from conversation_tools.create_user_memory_block import create_user_memory_block
        result = create_user_memory_block(
            user_id="user_a; DROP TABLE",
            category="preferences",
            value="Test value"
        )

        assert result["status"] == "error"
        assert "Invalid user_id format" in result["error_message"]

    def test_returns_error_for_invalid_category_format(self):
        """Tool validates category format."""
        from conversation_tools.create_user_memory_block import create_user_memory_block
        result = create_user_memory_block(
            user_id="user_a",
            category="bad category!",
            value="Test value"
        )

        assert result["status"] == "error"
        assert "Invalid category format" in result["error_message"]

    def test_returns_error_for_value_too_long(self):
        """Tool rejects values over 2000 characters."""
        from conversation_tools.create_user_memory_block import create_user_memory_block
        result = create_user_memory_block(
            user_id="user_a",
            category="preferences",
            value="x" * 2001
        )

        assert result["status"] == "error"
        assert "too long" in result["error_message"]

    def test_builds_cross_agent_label(self):
        """Tool builds correct label for cross-agent blocks."""
        mock_block = MagicMock()
        mock_block.id = "block-123"
        self.mock_client.blocks.create.return_value = mock_block
        self.mock_client.agents.blocks.attach.return_value = None

        from conversation_tools.create_user_memory_block import create_user_memory_block
        with patch.dict(os.environ, {
            "LETTA_BASE_URL": "http://test:8283",
            "LETTA_AGENT_ID": "agent-test"
        }):
            result = create_user_memory_block(
                user_id="user_a",
                category="preferences",
                value="Prefers 30 minute meetings",
                purpose="meeting_duration",
                agent_specific=False
            )

        assert result["status"] == "ok"
        assert result["label"] == "preferences_user_a_meeting_duration"
        assert result["block_id"] == "block-123"

    def test_builds_agent_specific_label(self):
        """Tool builds correct label for agent-specific blocks."""
        mock_block = MagicMock()
        mock_block.id = "block-456"
        self.mock_client.blocks.create.return_value = mock_block
        self.mock_client.agents.blocks.attach.return_value = None

        from conversation_tools.create_user_memory_block import create_user_memory_block
        with patch.dict(os.environ, {
            "LETTA_BASE_URL": "http://test:8283",
            "LETTA_AGENT_ID": "agent-test",
            "AGENT_NAME": "meeting_scheduler"
        }):
            result = create_user_memory_block(
                user_id="user_a",
                category="preferences",
                value="Blocks mornings for deep work",
                purpose="deep_work",
                agent_specific=True
            )

        assert result["status"] == "ok"
        assert result["label"] == "meeting_scheduler_preferences_user_a_deep_work"
        assert result["block_id"] == "block-456"

    def test_builds_label_without_purpose(self):
        """Tool builds correct label when purpose is not provided."""
        mock_block = MagicMock()
        mock_block.id = "block-789"
        self.mock_client.blocks.create.return_value = mock_block
        self.mock_client.agents.blocks.attach.return_value = None

        from conversation_tools.create_user_memory_block import create_user_memory_block
        with patch.dict(os.environ, {
            "LETTA_BASE_URL": "http://test:8283",
            "LETTA_AGENT_ID": "agent-test"
        }):
            result = create_user_memory_block(
                user_id="user_a",
                category="calendar",
                value="Calendar synced with Google",
                agent_specific=False
            )

        assert result["status"] == "ok"
        assert result["label"] == "calendar_user_a"
        assert result["block_id"] == "block-789"

    def test_attaches_block_to_agent(self):
        """Tool attaches created block to the agent."""
        mock_block = MagicMock()
        mock_block.id = "block-attach-test"
        self.mock_client.blocks.create.return_value = mock_block
        self.mock_client.agents.blocks.attach.return_value = None

        from conversation_tools.create_user_memory_block import create_user_memory_block
        with patch.dict(os.environ, {
            "LETTA_BASE_URL": "http://test:8283",
            "LETTA_AGENT_ID": "agent-test-123"
        }):
            create_user_memory_block(
                user_id="user_a",
                category="preferences",
                value="Test value"
            )

        # Verify attach was called with correct parameters
        self.mock_client.agents.blocks.attach.assert_called_once_with(
            agent_id="agent-test-123",
            block_id="block-attach-test"
        )

    def test_handles_api_error(self):
        """Tool returns error dict when API fails."""
        self.mock_client.blocks.create.side_effect = Exception("API connection failed")

        from conversation_tools.create_user_memory_block import create_user_memory_block
        with patch.dict(os.environ, {"LETTA_BASE_URL": "http://test:8283"}):
            result = create_user_memory_block(
                user_id="user_a",
                category="preferences",
                value="Test value"
            )

        assert result["status"] == "error"
        assert "API connection failed" in result["error_message"]

    def test_returns_error_when_no_client(self):
        """Tool returns error when Letta client unavailable."""
        # Set Letta to None to simulate unavailable client
        self.mock_letta_module.Letta = None
        sys.modules['letta_client'] = self.mock_letta_module
        sys.modules['letta'] = self.mock_letta_module

        from conversation_tools.create_user_memory_block import create_user_memory_block
        with patch.dict(os.environ, {"LETTA_BASE_URL": "http://test:8283"}):
            result = create_user_memory_block(
                user_id="user_a",
                category="preferences",
                value="Test value"
            )

        assert result["status"] == "error"
        assert "client not available" in result["error_message"].lower()

    def test_default_agent_specific_is_false(self):
        """Tool defaults agent_specific to False when not specified."""
        mock_block = MagicMock()
        mock_block.id = "block-default"
        self.mock_client.blocks.create.return_value = mock_block
        self.mock_client.agents.blocks.attach.return_value = None

        from conversation_tools.create_user_memory_block import create_user_memory_block
        with patch.dict(os.environ, {
            "LETTA_BASE_URL": "http://test:8283",
            "LETTA_AGENT_ID": "agent-test",
            "AGENT_NAME": "meeting_scheduler"
        }):
            # Call without agent_specific parameter
            result = create_user_memory_block(
                user_id="user_a",
                category="preferences",
                value="Test value"
            )

        assert result["status"] == "ok"
        # Label should NOT have agent prefix (cross-agent by default)
        assert not result["label"].startswith("meeting_scheduler_")
        assert result["label"] == "preferences_user_a"
