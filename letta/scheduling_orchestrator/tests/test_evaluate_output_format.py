"""Tests for evaluate_proposed_times output formatting."""

import pytest
from datetime import datetime, timezone

from scheduling_orchestrator.evaluate_proposed_times import format_evaluation_output
from scheduling_orchestrator.evaluation_models import EvaluatedSlot, ConflictInfo


class TestFormatEvaluationOutput:
    """Tests for format_evaluation_output function."""

    def test_includes_verbatim_markers(self):
        """Output should be wrapped in VERBATIM markers."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 18, 0, tzinfo=timezone.utc),  # 10am PST
                end=datetime(2026, 1, 29, 19, 0, tzinfo=timezone.utc),   # 11am PST
                category="clean",
                conflicts=[],
                score=100.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com"],
            participant_names=["User One"],
            timezone="America/Los_Angeles"
        )

        assert "[VERBATIM_USER_OUTPUT]" in result["markdown_display"]
        assert "[/VERBATIM_USER_OUTPUT]" in result["markdown_display"]

    def test_includes_participant_tags(self):
        """Output should include PARTICIPANTS and PARTICIPANT_NAMES tags."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 18, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 19, 0, tzinfo=timezone.utc),
                category="clean",
                conflicts=[],
                score=100.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com", "user2@example.com"],
            participant_names=["User One", "User Two"],
            timezone="America/Los_Angeles"
        )

        assert "[PARTICIPANTS:user1@example.com,user2@example.com]" in result["markdown_display"]
        assert "[PARTICIPANT_NAMES:User One,User Two]" in result["markdown_display"]

    def test_groups_slots_by_day(self):
        """Slots should be grouped under day headers."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 18, 0, tzinfo=timezone.utc),  # Thu 10am PST
                end=datetime(2026, 1, 29, 19, 0, tzinfo=timezone.utc),
                category="clean",
                conflicts=[],
                score=100.0
            ),
            EvaluatedSlot(
                start=datetime(2026, 1, 30, 22, 0, tzinfo=timezone.utc),  # Fri 2pm PST
                end=datetime(2026, 1, 30, 23, 0, tzinfo=timezone.utc),
                category="clean",
                conflicts=[],
                score=98.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com"],
            participant_names=["User One"],
            timezone="America/Los_Angeles"
        )

        # Should have day headers (Jan 29, 2026 is Thursday, Jan 30 is Friday)
        assert "Thursday, January 29" in result["markdown_display"]
        assert "Friday, January 30" in result["markdown_display"]

    def test_includes_conflict_annotations(self):
        """Conflicted slots should show conflict details."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 22, 0, tzinfo=timezone.utc),  # 2pm PST
                end=datetime(2026, 1, 29, 23, 0, tzinfo=timezone.utc),
                category="solo_adjust",
                conflicts=[
                    ConflictInfo(
                        participant="user1@example.com",
                        event_title="Team Standup",
                        event_time="2:00 PM - 2:30 PM",
                        event_property="flexible"
                    )
                ],
                score=50.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com", "user2@example.com"],
            participant_names=["User One", "User Two"],
            timezone="America/Los_Angeles"
        )

        # Should show conflict indicator and details
        assert "Team Standup" in result["markdown_display"]
        assert "User One" in result["markdown_display"] or "user1@example.com" in result["markdown_display"]

    def test_includes_interactive_data(self):
        """Result should include interactive_data for Slack rendering."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 18, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 19, 0, tzinfo=timezone.utc),
                category="clean",
                conflicts=[],
                score=100.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com"],
            participant_names=["User One"],
            timezone="America/Los_Angeles"
        )

        assert "interactive_data" in result
        assert "participants" in result["interactive_data"]
        assert "participant_names" in result["interactive_data"]
        assert "proposals" in result["interactive_data"]
        assert len(result["interactive_data"]["proposals"]) == 1

    def test_includes_summary_line(self):
        """Output should include summary of slot counts."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 18, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 19, 0, tzinfo=timezone.utc),
                category="clean",
                conflicts=[],
                score=100.0
            ),
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 22, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 23, 0, tzinfo=timezone.utc),
                category="solo_adjust",
                conflicts=[
                    ConflictInfo(
                        participant="user1@example.com",
                        event_title="Meeting",
                        event_time="2:00 PM - 3:00 PM",
                        event_property="flexible"
                    )
                ],
                score=50.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com"],
            participant_names=["User One"],
            timezone="America/Los_Angeles"
        )

        # Should have summary
        assert "2 times evaluated" in result["markdown_display"]
        assert "1 clean" in result["markdown_display"]


class TestSlotToProposalDict:
    """Tests for the _slot_to_proposal_dict helper."""

    def test_includes_iso_format_times(self):
        """Proposals should include ISO format times for Slack."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 18, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 19, 0, tzinfo=timezone.utc),
                category="clean",
                conflicts=[],
                score=100.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com"],
            participant_names=["User One"],
            timezone="America/Los_Angeles"
        )

        proposal = result["interactive_data"]["proposals"][0]
        # Should have ISO format start and end
        assert "start" in proposal
        assert "end" in proposal
        # ISO format should contain timezone info or be parseable
        assert "2026-01-29" in proposal["start"]

    def test_includes_category(self):
        """Proposals should include the category."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 18, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 19, 0, tzinfo=timezone.utc),
                category="solo_adjust",
                conflicts=[],
                score=50.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com"],
            participant_names=["User One"],
            timezone="America/Los_Angeles"
        )

        proposal = result["interactive_data"]["proposals"][0]
        assert proposal["category"] == "solo_adjust"

    def test_includes_conflicts_list(self):
        """Proposals should include conflict details."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 22, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 23, 0, tzinfo=timezone.utc),
                category="solo_adjust",
                conflicts=[
                    ConflictInfo(
                        participant="user1@example.com",
                        event_title="Team Meeting",
                        event_time="2:00 PM - 3:00 PM",
                        event_property="protected"
                    )
                ],
                score=50.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com"],
            participant_names=["User One"],
            timezone="America/Los_Angeles"
        )

        proposal = result["interactive_data"]["proposals"][0]
        assert "conflicts" in proposal
        assert len(proposal["conflicts"]) == 1
        assert proposal["conflicts"][0]["participant"] == "user1@example.com"
        assert proposal["conflicts"][0]["event_title"] == "Team Meeting"


class TestCategoryIcons:
    """Tests for category icon rendering."""

    def test_clean_shows_checkmark(self):
        """Clean slots should show checkmark icon."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 18, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 19, 0, tzinfo=timezone.utc),
                category="clean",
                conflicts=[],
                score=100.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com"],
            participant_names=["User One"],
            timezone="America/Los_Angeles"
        )

        # Should have checkmark for clean
        markdown = result["markdown_display"]
        # Find the line with the time slot
        lines = markdown.split("\n")
        time_line = [l for l in lines if "10:00 AM" in l][0]
        assert time_line.startswith("\u2705")  # checkmark emoji

    def test_solo_adjust_shows_warning(self):
        """Solo adjust slots should show warning icon."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 18, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 19, 0, tzinfo=timezone.utc),
                category="solo_adjust",
                conflicts=[
                    ConflictInfo(
                        participant="user1@example.com",
                        event_title="Meeting",
                        event_time="10:00 AM",
                        event_property="flexible"
                    )
                ],
                score=50.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com"],
            participant_names=["User One"],
            timezone="America/Los_Angeles"
        )

        markdown = result["markdown_display"]
        lines = markdown.split("\n")
        time_line = [l for l in lines if "10:00 AM" in l][0]
        assert time_line.startswith("\u26a0\ufe0f")  # warning emoji

    def test_multi_adjust_shows_x(self):
        """Multi adjust slots should show X icon."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 18, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 19, 0, tzinfo=timezone.utc),
                category="multi_adjust",
                conflicts=[
                    ConflictInfo(
                        participant="user1@example.com",
                        event_title="Meeting A",
                        event_time="10:00 AM",
                        event_property="flexible"
                    ),
                    ConflictInfo(
                        participant="user2@example.com",
                        event_title="Meeting B",
                        event_time="10:00 AM",
                        event_property="flexible"
                    )
                ],
                score=25.0
            ),
        ]

        result = format_evaluation_output(
            ranked_slots=slots,
            participants=["user1@example.com", "user2@example.com"],
            participant_names=["User One", "User Two"],
            timezone="America/Los_Angeles"
        )

        markdown = result["markdown_display"]
        lines = markdown.split("\n")
        time_line = [l for l in lines if "10:00 AM" in l][0]
        assert time_line.startswith("\u274c")  # X emoji
