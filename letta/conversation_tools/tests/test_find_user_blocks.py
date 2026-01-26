"""Tests for find_user_blocks tool."""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock


class TestFindUserBlocks:
    """Tests for user block discovery via naming conventions."""

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
        from conversation_tools.find_user_blocks import find_user_blocks
        result = find_user_blocks(user_id="user_a; DROP TABLE", scope="all")

        assert result["status"] == "error"
        assert "Invalid user_id format" in result["error_message"]

    def test_returns_error_for_invalid_scope(self):
        """Tool validates scope parameter."""
        mock_agent = MagicMock()
        mock_agent.memory.blocks = []
        self.mock_client.agents.retrieve.return_value = mock_agent

        from conversation_tools.find_user_blocks import find_user_blocks
        with patch.dict(os.environ, {"LETTA_BASE_URL": "http://test:8283"}):
            result = find_user_blocks(user_id="user_a", scope="invalid_scope")

        assert result["status"] == "error"
        assert "Invalid scope" in result["error_message"]

    def test_filters_blocks_by_user_id(self):
        """Tool returns only blocks matching user_id pattern."""
        mock_blocks = [
            MagicMock(id="block-1", label="preferences_user_a", value="User A prefs"),
            MagicMock(id="block-2", label="preferences_user_b", value="User B prefs"),
            MagicMock(id="block-3", label="calendar_user_a", value="User A calendar"),
            MagicMock(id="block-4", label="shared_system_config", value="System config"),
        ]

        mock_agent = MagicMock()
        mock_agent.memory.blocks = mock_blocks
        self.mock_client.agents.retrieve.return_value = mock_agent

        from conversation_tools.find_user_blocks import find_user_blocks
        with patch.dict(os.environ, {"LETTA_BASE_URL": "http://test:8283"}):
            result = find_user_blocks(user_id="user_a", scope="all")

        assert result["status"] == "ok"
        assert result["count"] == 2
        labels = [b["label"] for b in result["blocks"]]
        assert "preferences_user_a" in labels
        assert "calendar_user_a" in labels
        assert "preferences_user_b" not in labels

    def test_cross_agent_scope_excludes_agent_specific_blocks(self):
        """Cross-agent scope excludes blocks prefixed with agent name."""
        mock_blocks = [
            MagicMock(id="block-1", label="preferences_user_a", value="Cross-agent pref"),
            MagicMock(id="block-2", label="meeting_scheduler_preferences_user_a", value="Agent-specific"),
            MagicMock(id="block-3", label="calendar_user_a", value="Cross-agent calendar"),
        ]

        mock_agent = MagicMock()
        mock_agent.memory.blocks = mock_blocks
        self.mock_client.agents.retrieve.return_value = mock_agent

        from conversation_tools.find_user_blocks import find_user_blocks
        with patch.dict(os.environ, {
            "LETTA_BASE_URL": "http://test:8283",
            "AGENT_NAME": "meeting_scheduler"
        }):
            result = find_user_blocks(user_id="user_a", scope="cross_agent")

        assert result["status"] == "ok"
        labels = [b["label"] for b in result["blocks"]]
        assert "preferences_user_a" in labels
        assert "calendar_user_a" in labels
        assert "meeting_scheduler_preferences_user_a" not in labels

    def test_agent_specific_scope_includes_only_agent_blocks(self):
        """Agent-specific scope includes only blocks prefixed with agent name."""
        mock_blocks = [
            MagicMock(id="block-1", label="preferences_user_a", value="Cross-agent pref"),
            MagicMock(id="block-2", label="meeting_scheduler_preferences_user_a", value="Agent-specific"),
            MagicMock(id="block-3", label="meeting_scheduler_calendar_user_a", value="Agent calendar"),
        ]

        mock_agent = MagicMock()
        mock_agent.memory.blocks = mock_blocks
        self.mock_client.agents.retrieve.return_value = mock_agent

        from conversation_tools.find_user_blocks import find_user_blocks
        with patch.dict(os.environ, {
            "LETTA_BASE_URL": "http://test:8283",
            "AGENT_NAME": "meeting_scheduler"
        }):
            result = find_user_blocks(user_id="user_a", scope="agent_specific")

        assert result["status"] == "ok"
        labels = [b["label"] for b in result["blocks"]]
        assert "meeting_scheduler_preferences_user_a" in labels
        assert "meeting_scheduler_calendar_user_a" in labels
        assert "preferences_user_a" not in labels

    def test_returns_empty_list_when_no_blocks_match(self):
        """Tool returns empty list when no blocks match user_id."""
        mock_blocks = [
            MagicMock(id="block-1", label="preferences_user_b", value="User B"),
            MagicMock(id="block-2", label="system_config", value="Config"),
        ]

        mock_agent = MagicMock()
        mock_agent.memory.blocks = mock_blocks
        self.mock_client.agents.retrieve.return_value = mock_agent

        from conversation_tools.find_user_blocks import find_user_blocks
        with patch.dict(os.environ, {"LETTA_BASE_URL": "http://test:8283"}):
            result = find_user_blocks(user_id="user_a", scope="all")

        assert result["status"] == "ok"
        assert result["blocks"] == []
        assert result["count"] == 0

    def test_returns_block_metadata(self):
        """Tool returns block id, label, and value preview."""
        long_value = "A" * 500
        mock_blocks = [
            MagicMock(id="block-123", label="preferences_user_a", value=long_value),
        ]

        mock_agent = MagicMock()
        mock_agent.memory.blocks = mock_blocks
        self.mock_client.agents.retrieve.return_value = mock_agent

        from conversation_tools.find_user_blocks import find_user_blocks
        with patch.dict(os.environ, {"LETTA_BASE_URL": "http://test:8283"}):
            result = find_user_blocks(user_id="user_a", scope="all")

        assert result["status"] == "ok"
        assert result["count"] == 1
        assert result["blocks"][0]["id"] == "block-123"
        assert result["blocks"][0]["label"] == "preferences_user_a"
        assert len(result["blocks"][0]["value_preview"]) <= 103  # 100 chars + "..."

    def test_default_scope_is_all(self):
        """Tool defaults to 'all' scope when not specified."""
        mock_blocks = [
            MagicMock(id="block-1", label="preferences_user_a", value="Test"),
        ]

        mock_agent = MagicMock()
        mock_agent.memory.blocks = mock_blocks
        self.mock_client.agents.retrieve.return_value = mock_agent

        from conversation_tools.find_user_blocks import find_user_blocks
        with patch.dict(os.environ, {"LETTA_BASE_URL": "http://test:8283"}):
            # Call without scope parameter
            result = find_user_blocks(user_id="user_a")

        assert result["status"] == "ok"
        assert result["count"] == 1
