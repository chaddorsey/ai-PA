"""Integration tests for evaluate_proposed_times."""
import pytest
import pytest_asyncio
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

# Configure pytest-asyncio
pytestmark = pytest.mark.asyncio(loop_scope="function")


class TestEvaluateProposedTimes:
    """Test the main evaluation function."""

    @pytest.mark.asyncio
    async def test_basic_evaluation(self):
        """Test basic evaluation with mocked calendar data."""
        from scheduling_orchestrator.evaluate_proposed_times import evaluate_proposed_times

        # Mock calendar data - both participants are free
        mock_calendar_data = {
            "chad@example.com": [],
            "cynthia@example.com": []
        }

        with patch(
            'scheduling_orchestrator.evaluate_proposed_times.fetch_calendar_data',
            new_callable=AsyncMock,
            return_value=mock_calendar_data
        ):
            result = await evaluate_proposed_times(
                proposed_times="01/29 (Thu), anytime but 3:30-4:30pm",
                participants="chad@example.com, cynthia@example.com",
                duration_minutes=30,
                timezone="America/New_York"
            )

        assert "clean_slots" in result
        assert "solo_adjust_slots" in result
        assert "multi_adjust_slots" in result
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_no_availability(self):
        """Test when no slots are available."""
        from scheduling_orchestrator.evaluate_proposed_times import evaluate_proposed_times

        # Mock calendar data - Chad is completely blocked
        mock_calendar_data = {
            "chad@example.com": [
                {
                    "id": "evt1",
                    "start": "2026-01-29T08:00:00-05:00",
                    "end": "2026-01-29T18:00:00-05:00",
                    "locked": True,
                    "summary": "All Day Block"
                }
            ],
            "cynthia@example.com": []
        }

        with patch(
            'scheduling_orchestrator.evaluate_proposed_times.fetch_calendar_data',
            new_callable=AsyncMock,
            return_value=mock_calendar_data
        ):
            result = await evaluate_proposed_times(
                proposed_times="01/29 (Thu), 9am-5pm",
                participants="chad@example.com, cynthia@example.com",
                duration_minutes=30,
                timezone="America/New_York"
            )

        assert len(result["clean_slots"]) == 0
        # May have no_availability_windows populated
        assert result["status"] == "ok"
