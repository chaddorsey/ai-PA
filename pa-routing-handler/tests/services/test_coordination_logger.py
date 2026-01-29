"""Tests for coordination logging utility."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestCoordinationLogger:
    """Tests for CoordinationLogger."""

    def test_log_event_inserts_to_supabase(self):
        """Log event inserts record to coordination_logs table."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.insert.return_value.execute.return_value = None

        logger = CoordinationLogger(mock_supabase)
        logger.log_event(
            event_type="start",
            task_id="task-123",
            identity_id="identity-456",
            task_type="meeting_prep",
            data={"context": {"meeting": "Board Meeting"}}
        )

        mock_supabase.table.assert_called_with("coordination_logs")
        call_args = mock_supabase.table.return_value.insert.call_args[0][0]
        assert call_args["event_type"] == "start"
        assert call_args["task_id"] == "task-123"
        assert call_args["task_type"] == "meeting_prep"

    def test_log_event_includes_elapsed_ms(self):
        """Log event can include elapsed_ms."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.insert.return_value.execute.return_value = None

        logger = CoordinationLogger(mock_supabase)
        logger.log_event(
            event_type="complete",
            task_id="task-123",
            identity_id="identity-456",
            task_type="meeting_prep",
            elapsed_ms=4500
        )

        call_args = mock_supabase.table.return_value.insert.call_args[0][0]
        assert call_args["elapsed_ms"] == 4500

    def test_log_event_handles_supabase_error(self):
        """Log event handles Supabase errors gracefully."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.insert.return_value.execute.side_effect = Exception("DB error")

        logger = CoordinationLogger(mock_supabase)
        # Should not raise, just log warning
        logger.log_event(
            event_type="start",
            task_id="task-123",
            identity_id="identity-456",
            task_type="meeting_prep"
        )

    def test_log_event_includes_all_fields(self):
        """Log event includes all provided fields."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.insert.return_value.execute.return_value = None

        logger = CoordinationLogger(mock_supabase)
        logger.log_event(
            event_type="agent_dispatch",
            task_id="task-789",
            identity_id="identity-abc",
            task_type="daily_briefing",
            task_version="1.2.0",
            data={"agent": "calendar_agent", "timeout_ms": 5000},
            elapsed_ms=1234
        )

        call_args = mock_supabase.table.return_value.insert.call_args[0][0]
        assert call_args["event_type"] == "agent_dispatch"
        assert call_args["task_id"] == "task-789"
        assert call_args["identity_id"] == "identity-abc"
        assert call_args["task_type"] == "daily_briefing"
        assert call_args["task_version"] == "1.2.0"
        assert call_args["data"]["agent"] == "calendar_agent"
        assert call_args["elapsed_ms"] == 1234
        assert "timestamp" in call_args

    def test_query_by_task_type(self):
        """Can query logs by task type."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"event_type": "complete", "task_type": "meeting_prep"}]
        )

        logger = CoordinationLogger(mock_supabase)
        results = logger.query_by_task_type("meeting_prep", limit=10)

        assert len(results) == 1
        assert results[0]["task_type"] == "meeting_prep"

    def test_query_by_task_type_with_event_type_filter(self):
        """Can query logs by task type and event type."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        # Chain: table -> select -> eq (task_type) -> eq (event_type) -> order -> limit -> execute
        mock_chain = mock_supabase.table.return_value.select.return_value
        mock_chain.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"event_type": "complete", "task_type": "meeting_prep"}]
        )

        logger = CoordinationLogger(mock_supabase)
        results = logger.query_by_task_type("meeting_prep", event_type="complete", limit=10)

        assert len(results) == 1
        assert results[0]["event_type"] == "complete"

    def test_query_by_task_type_handles_error(self):
        """Query returns empty list on error."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.side_effect = Exception("DB error")

        logger = CoordinationLogger(mock_supabase)
        results = logger.query_by_task_type("meeting_prep")

        assert results == []

    def test_query_by_task_type_handles_empty_data(self):
        """Query returns empty list when no data found."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=None
        )

        logger = CoordinationLogger(mock_supabase)
        results = logger.query_by_task_type("nonexistent")

        assert results == []


class TestCoordinationLoggerContributionStats:
    """Tests for agent contribution statistics."""

    def test_get_agent_contribution_stats(self):
        """Can get agent contribution statistics."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[
                {"event_type": "agent_dispatch", "data": {"agent": "calendar_agent"}},
                {"event_type": "agent_dispatch", "data": {"agent": "calendar_agent"}},
                {"event_type": "agent_contributed", "data": {"agent": "calendar_agent"}},
                {"event_type": "agent_dispatch", "data": {"agent": "email_agent"}},
                {"event_type": "agent_timeout", "data": {"agent": "email_agent"}},
            ]
        )

        logger = CoordinationLogger(mock_supabase)
        stats = logger.get_agent_contribution_stats("meeting_prep")

        assert stats["calendar_agent"]["dispatches"] == 2
        assert stats["calendar_agent"]["contributions"] == 1
        assert stats["email_agent"]["dispatches"] == 1
        assert stats["email_agent"]["timeouts"] == 1

    def test_get_agent_contribution_stats_handles_error(self):
        """Returns empty dict on error."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.side_effect = Exception("DB error")

        logger = CoordinationLogger(mock_supabase)
        stats = logger.get_agent_contribution_stats("meeting_prep")

        assert stats == {}

    def test_get_agent_contribution_stats_handles_missing_agent(self):
        """Skips records without agent in data."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[
                {"event_type": "agent_dispatch", "data": {"agent": "calendar_agent"}},
                {"event_type": "agent_dispatch", "data": {}},  # Missing agent
                {"event_type": "agent_contributed", "data": None},  # None data
            ]
        )

        logger = CoordinationLogger(mock_supabase)
        stats = logger.get_agent_contribution_stats("meeting_prep")

        assert len(stats) == 1
        assert stats["calendar_agent"]["dispatches"] == 1

    def test_get_agent_contribution_stats_tracks_errors(self):
        """Tracks agent errors in stats."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[
                {"event_type": "agent_dispatch", "data": {"agent": "flaky_agent"}},
                {"event_type": "agent_error", "data": {"agent": "flaky_agent"}},
                {"event_type": "agent_dispatch", "data": {"agent": "flaky_agent"}},
                {"event_type": "agent_contributed", "data": {"agent": "flaky_agent"}},
            ]
        )

        logger = CoordinationLogger(mock_supabase)
        stats = logger.get_agent_contribution_stats("meeting_prep")

        assert stats["flaky_agent"]["dispatches"] == 2
        assert stats["flaky_agent"]["contributions"] == 1
        assert stats["flaky_agent"]["errors"] == 1
        assert stats["flaky_agent"]["timeouts"] == 0
