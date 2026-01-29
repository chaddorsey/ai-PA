"""Tests for coordination logging utility."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestCoordinationLogger:
    """Tests for CoordinationLogger."""

    def test_log_event_posts_to_postgrest(self):
        """Log event posts record to PostgREST."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response

            logger = CoordinationLogger("http://localhost:3000", "test-key")
            logger.log_event(
                event_type="start",
                task_id="task-123",
                identity_id="identity-456",
                task_type="meeting_prep",
                data={"context": {"meeting": "Board Meeting"}}
            )

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "/coordination_logs" in call_args[0][0]
            json_data = call_args[1]["json"]
            assert json_data["event_type"] == "start"
            assert json_data["task_id"] == "task-123"
            assert json_data["task_type"] == "meeting_prep"

    def test_log_event_includes_elapsed_ms(self):
        """Log event can include elapsed_ms."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response

            logger = CoordinationLogger("http://localhost:3000", "test-key")
            logger.log_event(
                event_type="complete",
                task_id="task-123",
                identity_id="identity-456",
                task_type="meeting_prep",
                elapsed_ms=4500
            )

            json_data = mock_client.post.call_args[1]["json"]
            assert json_data["elapsed_ms"] == 4500

    def test_log_event_handles_error(self):
        """Log event handles errors gracefully."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = Exception("Connection error")

            logger = CoordinationLogger("http://localhost:3000", "test-key")
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

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response

            logger = CoordinationLogger("http://localhost:3000", "test-key")
            logger.log_event(
                event_type="agent_dispatch",
                task_id="task-789",
                identity_id="identity-abc",
                task_type="daily_briefing",
                task_version="1.2.0",
                data={"agent": "calendar_agent", "timeout_ms": 5000},
                elapsed_ms=1234
            )

            json_data = mock_client.post.call_args[1]["json"]
            assert json_data["event_type"] == "agent_dispatch"
            assert json_data["task_id"] == "task-789"
            assert json_data["identity_id"] == "identity-abc"
            assert json_data["task_type"] == "daily_briefing"
            assert json_data["task_version"] == "1.2.0"
            assert json_data["data"]["agent"] == "calendar_agent"
            assert json_data["elapsed_ms"] == 1234
            assert "timestamp" in json_data

    def test_query_by_task_type(self):
        """Can query logs by task type."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = [{"event_type": "complete", "task_type": "meeting_prep"}]
            mock_client.get.return_value = mock_response

            logger = CoordinationLogger("http://localhost:3000", "test-key")
            results = logger.query_by_task_type("meeting_prep", limit=10)

            assert len(results) == 1
            assert results[0]["task_type"] == "meeting_prep"

    def test_query_by_task_type_handles_error(self):
        """Query returns empty list on error."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = Exception("DB error")

            logger = CoordinationLogger("http://localhost:3000", "test-key")
            results = logger.query_by_task_type("meeting_prep")

            assert results == []


class TestCoordinationLoggerContributionStats:
    """Tests for agent contribution statistics."""

    def test_get_agent_contribution_stats(self):
        """Can get agent contribution statistics."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = [
                {"event_type": "agent_dispatch", "data": {"agent": "calendar_agent"}},
                {"event_type": "agent_dispatch", "data": {"agent": "calendar_agent"}},
                {"event_type": "agent_contributed", "data": {"agent": "calendar_agent"}},
                {"event_type": "agent_dispatch", "data": {"agent": "email_agent"}},
                {"event_type": "agent_timeout", "data": {"agent": "email_agent"}},
            ]
            mock_client.get.return_value = mock_response

            logger = CoordinationLogger("http://localhost:3000", "test-key")
            stats = logger.get_agent_contribution_stats("meeting_prep")

            assert stats["calendar_agent"]["dispatches"] == 2
            assert stats["calendar_agent"]["contributions"] == 1
            assert stats["email_agent"]["dispatches"] == 1
            assert stats["email_agent"]["timeouts"] == 1

    def test_get_agent_contribution_stats_handles_error(self):
        """Returns empty dict on error."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = Exception("DB error")

            logger = CoordinationLogger("http://localhost:3000", "test-key")
            stats = logger.get_agent_contribution_stats("meeting_prep")

            assert stats == {}


class TestCoordinationLoggerExecutionSummary:
    """Tests for execution summary analysis."""

    def test_get_execution_summary(self):
        """Can get execution summary for refinement."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            call_count = [0]

            def mock_get(*args, **kwargs):
                call_count[0] += 1
                mock_response = MagicMock()
                mock_response.raise_for_status = MagicMock()
                if call_count[0] == 1:
                    # Completions query
                    mock_response.json.return_value = [
                        {"task_id": "task-1", "elapsed_ms": 4000},
                        {"task_id": "task-2", "elapsed_ms": 5000},
                    ]
                elif call_count[0] == 2:
                    # Agent stats query
                    mock_response.json.return_value = [
                        {"event_type": "agent_dispatch", "data": {"agent": "calendar_agent"}},
                        {"event_type": "agent_contributed", "data": {"agent": "calendar_agent"}},
                    ]
                else:
                    # Starts query
                    mock_response.json.return_value = [
                        {"data": {"questions_asked": ["which_meeting"]}},
                        {"data": {"questions_asked": ["which_meeting", "focus"]}},
                    ]
                return mock_response

            mock_client.get.side_effect = mock_get

            logger = CoordinationLogger("http://localhost:3000", "test-key")
            summary = logger.get_execution_summary("meeting_prep", limit=10)

            assert summary["executions"] == 2
            assert summary["avg_time_ms"] == 4500
            assert "agent_stats" in summary
            assert "question_patterns" in summary
            assert "recent_task_ids" in summary

    def test_get_execution_summary_no_executions(self):
        """Returns message when no executions found."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = []
            mock_client.get.return_value = mock_response

            logger = CoordinationLogger("http://localhost:3000", "test-key")
            summary = logger.get_execution_summary("nonexistent_task")

            assert summary["executions"] == 0
            assert summary["message"] == "No executions found"

    def test_get_execution_summary_handles_error(self):
        """Returns error dict on exception."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = Exception("DB error")

            logger = CoordinationLogger("http://localhost:3000", "test-key")
            summary = logger.get_execution_summary("meeting_prep")

            assert "error" in summary
            assert "DB error" in summary["error"]
