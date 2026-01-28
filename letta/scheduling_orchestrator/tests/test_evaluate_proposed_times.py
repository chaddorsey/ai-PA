"""Integration tests for evaluate_proposed_times."""
import pytest
import pytest_asyncio
from datetime import date, datetime
from unittest.mock import AsyncMock, patch, MagicMock

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

    @pytest.mark.asyncio
    async def test_returns_markdown_display(self):
        """Test that result includes markdown_display with VERBATIM markers."""
        from scheduling_orchestrator.evaluate_proposed_times import evaluate_proposed_times

        # Mock calendar data - both participants are free
        mock_calendar_data = {
            "chad@example.com": [],
            "cynthia@example.com": []
        }

        # Mock participant name lookup
        mock_names = {
            "chad@example.com": "Chad",
            "cynthia@example.com": "Cynthia"
        }

        with patch(
            'scheduling_orchestrator.evaluate_proposed_times.fetch_calendar_data',
            new_callable=AsyncMock,
            return_value=mock_calendar_data
        ), patch(
            'scheduling_orchestrator.evaluate_proposed_times.lookup_participant_names',
            return_value=mock_names
        ):
            result = await evaluate_proposed_times(
                proposed_times="01/29 (Thu), 9am-10am",
                participants="chad@example.com, cynthia@example.com",
                duration_minutes=30,
                timezone="America/New_York"
            )

        assert result["status"] == "ok"
        assert "markdown_display" in result
        # Check for VERBATIM markers
        assert "[VERBATIM_USER_OUTPUT]" in result["markdown_display"]
        assert "[/VERBATIM_USER_OUTPUT]" in result["markdown_display"]
        # Check for participant information
        assert "[PARTICIPANTS:" in result["markdown_display"]
        assert "[PARTICIPANT_NAMES:" in result["markdown_display"]

    @pytest.mark.asyncio
    async def test_returns_interactive_data(self):
        """Test that result includes interactive_data for Slack adapter."""
        from scheduling_orchestrator.evaluate_proposed_times import evaluate_proposed_times

        # Mock calendar data - both participants are free
        mock_calendar_data = {
            "chad@example.com": [],
            "cynthia@example.com": []
        }

        # Mock participant name lookup
        mock_names = {
            "chad@example.com": "Chad",
            "cynthia@example.com": "Cynthia"
        }

        with patch(
            'scheduling_orchestrator.evaluate_proposed_times.fetch_calendar_data',
            new_callable=AsyncMock,
            return_value=mock_calendar_data
        ), patch(
            'scheduling_orchestrator.evaluate_proposed_times.lookup_participant_names',
            return_value=mock_names
        ):
            result = await evaluate_proposed_times(
                proposed_times="01/29 (Thu), 9am-10am",
                participants="chad@example.com, cynthia@example.com",
                duration_minutes=30,
                timezone="America/New_York"
            )

        assert result["status"] == "ok"
        assert "interactive_data" in result
        interactive = result["interactive_data"]
        # Check structure
        assert "participants" in interactive
        assert "participant_names" in interactive
        assert "proposals" in interactive
        # Check participant data
        assert "chad@example.com" in interactive["participants"]
        assert "Chad" in interactive["participant_names"]
        # Check proposals structure (if we have slots)
        if interactive["proposals"]:
            proposal = interactive["proposals"][0]
            assert "start" in proposal
            assert "end" in proposal
            assert "category" in proposal
            assert "conflicts" in proposal

    @pytest.mark.asyncio
    async def test_maintains_backward_compatible_slots(self):
        """Test that result includes backward compatible slots field."""
        from scheduling_orchestrator.evaluate_proposed_times import evaluate_proposed_times

        # Mock calendar data - both participants are free
        mock_calendar_data = {
            "chad@example.com": [],
            "cynthia@example.com": []
        }

        # Mock participant name lookup
        mock_names = {
            "chad@example.com": "Chad",
            "cynthia@example.com": "Cynthia"
        }

        with patch(
            'scheduling_orchestrator.evaluate_proposed_times.fetch_calendar_data',
            new_callable=AsyncMock,
            return_value=mock_calendar_data
        ), patch(
            'scheduling_orchestrator.evaluate_proposed_times.lookup_participant_names',
            return_value=mock_names
        ):
            result = await evaluate_proposed_times(
                proposed_times="01/29 (Thu), 9am-10am",
                participants="chad@example.com, cynthia@example.com",
                duration_minutes=30,
                timezone="America/New_York"
            )

        assert result["status"] == "ok"
        # Check new slots field exists
        assert "slots" in result
        # Check backward compatible fields still exist
        assert "clean_slots" in result
        assert "solo_adjust_slots" in result
        assert "multi_adjust_slots" in result
        assert "no_availability_windows" in result
        # Check summary exists
        assert "summary" in result
        summary = result["summary"]
        assert "total_proposed" in summary
        assert "total_evaluated" in summary
        assert "clean_count" in summary
        assert "conflict_count" in summary

    @pytest.mark.asyncio
    async def test_slots_field_structure(self):
        """Test that slots field has correct structure for backward compatibility."""
        from scheduling_orchestrator.evaluate_proposed_times import evaluate_proposed_times

        # Mock calendar data - both participants are free
        mock_calendar_data = {
            "chad@example.com": [],
            "cynthia@example.com": []
        }

        # Mock participant name lookup
        mock_names = {
            "chad@example.com": "Chad",
            "cynthia@example.com": "Cynthia"
        }

        with patch(
            'scheduling_orchestrator.evaluate_proposed_times.fetch_calendar_data',
            new_callable=AsyncMock,
            return_value=mock_calendar_data
        ), patch(
            'scheduling_orchestrator.evaluate_proposed_times.lookup_participant_names',
            return_value=mock_names
        ):
            result = await evaluate_proposed_times(
                proposed_times="01/29 (Thu), 9am-10am",
                participants="chad@example.com, cynthia@example.com",
                duration_minutes=30,
                timezone="America/New_York"
            )

        assert result["status"] == "ok"
        assert "slots" in result

        # Check slot structure if we have slots
        if result["slots"]:
            slot = result["slots"][0]
            assert "start" in slot
            assert "end" in slot
            assert "category" in slot
            assert "conflicts" in slot
            assert "score" in slot
            # Conflicts should use "event" and "property" keys for backward compat
            if slot["conflicts"]:
                conflict = slot["conflicts"][0]
                assert "participant" in conflict
                assert "event" in conflict
                assert "property" in conflict

    @pytest.mark.asyncio
    async def test_identity_id_parameter(self):
        """Test that identity_id parameter is accepted and passed to ranker."""
        from scheduling_orchestrator.evaluate_proposed_times import evaluate_proposed_times

        # Mock calendar data
        mock_calendar_data = {
            "chad@example.com": [],
            "cynthia@example.com": []
        }

        # Mock participant name lookup
        mock_names = {
            "chad@example.com": "Chad",
            "cynthia@example.com": "Cynthia"
        }

        with patch(
            'scheduling_orchestrator.evaluate_proposed_times.fetch_calendar_data',
            new_callable=AsyncMock,
            return_value=mock_calendar_data
        ), patch(
            'scheduling_orchestrator.evaluate_proposed_times.lookup_participant_names',
            return_value=mock_names
        ), patch(
            'scheduling_orchestrator.evaluate_proposed_times.rank_evaluated_slots'
        ) as mock_ranker:
            # Set up mock ranker to return empty list
            mock_ranker.return_value = []

            result = await evaluate_proposed_times(
                proposed_times="01/29 (Thu), 9am-10am",
                participants="chad@example.com, cynthia@example.com",
                duration_minutes=30,
                timezone="America/New_York",
                identity_id="identity-123"
            )

            # Verify ranker was called with identity_id
            mock_ranker.assert_called_once()
            call_kwargs = mock_ranker.call_args[1]
            assert call_kwargs["identity_id"] == "identity-123"
