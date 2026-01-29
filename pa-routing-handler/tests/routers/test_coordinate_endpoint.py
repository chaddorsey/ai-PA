"""Tests for /v1/coordinate endpoint."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch, AsyncMock


class TestCoordinateEndpoint:
    """Tests for coordinate endpoint."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator."""
        from pa_routing.models.responses import CoordinateResponse

        orchestrator = MagicMock()
        orchestrator.coordinate = AsyncMock(return_value=CoordinateResponse(
            status="complete",
            task_id="task-123",
            synthesis="Test synthesis",
            findings={"calendar": "[Calendar] Test"},
            agents_completed=["calendar"],
            agents_failed=[],
            coordination_time_ms=1000
        ))
        return orchestrator

    def test_coordinate_endpoint_success(self, mock_orchestrator):
        """Coordinate endpoint returns successful response."""
        from pa_routing.main import app
        from pa_routing.routers import routing

        with patch.object(routing, '_orchestrator', mock_orchestrator):
            client = TestClient(app)
            response = client.post("/v1/coordinate", json={
                "identity_id": "identity-123",
                "task_type": "meeting_prep",
                "context": {"meeting_identifier": "Board Meeting"}
            })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "complete"
        assert data["task_id"] == "task-123"

    def test_coordinate_endpoint_validates_request(self):
        """Coordinate endpoint validates required fields."""
        from pa_routing.main import app

        client = TestClient(app)
        response = client.post("/v1/coordinate", json={
            "identity_id": "identity-123"
            # Missing task_type and context
        })

        assert response.status_code == 422  # Validation error
