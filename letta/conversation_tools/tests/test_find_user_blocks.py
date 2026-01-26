"""Tests for find_user_blocks tool."""

import importlib
import pytest
from unittest.mock import patch, MagicMock

# Import the module properly to enable patching
find_user_blocks_module = importlib.import_module('letta.conversation_tools.find_user_blocks')
find_user_blocks = find_user_blocks_module.find_user_blocks


class TestFindUserBlocks:
    """Tests for user block discovery via naming conventions."""

    def test_returns_error_for_invalid_user_id_format(self):
        """Tool validates user_id format to prevent injection."""
        result = find_user_blocks(user_id="user_a; DROP TABLE", scope="all")

        assert "error" in result
        assert "Invalid user_id format" in result["error"]

    def test_returns_error_for_invalid_scope(self):
        """Tool validates scope parameter."""
        with patch.object(find_user_blocks_module, "_get_agent_blocks", return_value=[]):
            result = find_user_blocks(user_id="user_a", scope="invalid_scope")

        assert "error" in result
        assert "Invalid scope" in result["error"]

    def test_filters_blocks_by_user_id(self):
        """Tool returns only blocks matching user_id pattern."""
        mock_blocks = [
            MagicMock(id="block-1", label="preferences_user_a", value="User A prefs"),
            MagicMock(id="block-2", label="preferences_user_b", value="User B prefs"),
            MagicMock(id="block-3", label="calendar_user_a", value="User A calendar"),
            MagicMock(id="block-4", label="shared_system_config", value="System config"),
        ]

        with patch.object(find_user_blocks_module, "_get_agent_blocks", return_value=mock_blocks):
            result = find_user_blocks(user_id="user_a", scope="all")

        assert len(result) == 2
        labels = [b["label"] for b in result]
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

        with patch.object(find_user_blocks_module, "_get_agent_blocks", return_value=mock_blocks):
            with patch.object(find_user_blocks_module, "AGENT_NAME", "meeting_scheduler"):
                result = find_user_blocks(user_id="user_a", scope="cross_agent")

        labels = [b["label"] for b in result]
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

        with patch.object(find_user_blocks_module, "_get_agent_blocks", return_value=mock_blocks):
            with patch.object(find_user_blocks_module, "AGENT_NAME", "meeting_scheduler"):
                result = find_user_blocks(user_id="user_a", scope="agent_specific")

        labels = [b["label"] for b in result]
        assert "meeting_scheduler_preferences_user_a" in labels
        assert "meeting_scheduler_calendar_user_a" in labels
        assert "preferences_user_a" not in labels

    def test_returns_empty_list_when_no_blocks_match(self):
        """Tool returns empty list when no blocks match user_id."""
        mock_blocks = [
            MagicMock(id="block-1", label="preferences_user_b", value="User B"),
            MagicMock(id="block-2", label="system_config", value="Config"),
        ]

        with patch.object(find_user_blocks_module, "_get_agent_blocks", return_value=mock_blocks):
            result = find_user_blocks(user_id="user_a", scope="all")

        assert result == []

    def test_returns_block_metadata(self):
        """Tool returns block id, label, and value preview."""
        long_value = "A" * 500
        mock_blocks = [
            MagicMock(id="block-123", label="preferences_user_a", value=long_value),
        ]

        with patch.object(find_user_blocks_module, "_get_agent_blocks", return_value=mock_blocks):
            result = find_user_blocks(user_id="user_a", scope="all")

        assert len(result) == 1
        assert result[0]["id"] == "block-123"
        assert result[0]["label"] == "preferences_user_a"
        assert len(result[0]["value_preview"]) <= 103  # 100 chars + "..."
