"""Tests for coordination request/response models."""

import pytest


class TestCoordinateRequest:
    """Tests for CoordinateRequest model."""

    def test_coordinate_request_required_fields(self):
        """CoordinateRequest requires identity_id, task_type, context."""
        from pa_routing.models.requests import CoordinateRequest

        req = CoordinateRequest(
            identity_id="identity-123",
            task_type="meeting_prep",
            context={"meeting_identifier": "Board Meeting"}
        )

        assert req.identity_id == "identity-123"
        assert req.task_type == "meeting_prep"
        assert req.context["meeting_identifier"] == "Board Meeting"

    def test_coordinate_request_optional_fields(self):
        """CoordinateRequest has optional questions_asked and conversation_id."""
        from pa_routing.models.requests import CoordinateRequest

        req = CoordinateRequest(
            identity_id="identity-123",
            task_type="meeting_prep",
            context={},
            questions_asked=["which_meeting", "focus_areas"],
            conversation_id="conv-456"
        )

        assert req.questions_asked == ["which_meeting", "focus_areas"]
        assert req.conversation_id == "conv-456"


class TestCoordinateResponse:
    """Tests for CoordinateResponse model."""

    def test_coordinate_response_success(self):
        """CoordinateResponse for successful coordination."""
        from pa_routing.models.responses import CoordinateResponse

        resp = CoordinateResponse(
            status="complete",
            task_id="task-123",
            synthesis="**Meeting** - Tomorrow 2pm",
            findings={"calendar": "[Calendar] Meeting found"},
            agents_completed=["calendar", "email"],
            agents_failed=[],
            coordination_time_ms=4500
        )

        assert resp.status == "complete"
        assert resp.task_id == "task-123"
        assert "calendar" in resp.agents_completed

    def test_coordinate_response_partial_failure(self):
        """CoordinateResponse for partial failure."""
        from pa_routing.models.responses import CoordinateResponse

        resp = CoordinateResponse(
            status="partial",
            task_id="task-123",
            synthesis="**Meeting** - Partial info",
            findings={"calendar": "[Calendar] Meeting found"},
            agents_completed=["calendar"],
            agents_failed=["email"],
            coordination_time_ms=5000
        )

        assert resp.status == "partial"
        assert "email" in resp.agents_failed
