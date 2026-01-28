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
        """Slots should be grouped under day headers with abbreviated month format."""
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

        # Should have day headers with abbreviated month (Slack parser format)
        # Jan 29, 2026 is Thursday, Jan 30 is Friday
        assert "Thursday, Jan. 29" in result["markdown_display"]
        assert "Friday, Jan. 30" in result["markdown_display"]

    def test_includes_conflict_annotations(self):
        """Conflicted slots should show conflict details in day header."""
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

        # Conflict info should be in day header line (Slack parser format)
        # Format: "Day — Conflicts with \"Event\" (Participant)"
        assert "Team Standup" in result["markdown_display"]
        assert "User One" in result["markdown_display"]
        # Should use em-dash (—) for conflict annotation
        assert "—" in result["markdown_display"]

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


class TestSlackParserCompatibleFormat:
    """Tests for Slack parser compatible output format."""

    def test_time_format_24_hour_with_endash(self):
        """Time slots should use 24-hour format with en-dash separator."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 18, 0, tzinfo=timezone.utc),  # 10:00 PST
                end=datetime(2026, 1, 29, 19, 0, tzinfo=timezone.utc),   # 11:00 PST
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

        markdown = result["markdown_display"]
        # Should have bullet with 24-hour time and en-dash
        assert "* 10:00 – 11:00" in markdown

    def test_time_format_afternoon_24_hour(self):
        """Afternoon times should be in 24-hour format."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 22, 0, tzinfo=timezone.utc),  # 14:00 PST
                end=datetime(2026, 1, 29, 23, 0, tzinfo=timezone.utc),   # 15:00 PST
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

        markdown = result["markdown_display"]
        # Should have 14:00 not 2:00 PM
        assert "* 14:00 – 15:00" in markdown

    def test_day_header_no_hash_prefix(self):
        """Day headers should not have ### prefix."""
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

        markdown = result["markdown_display"]
        # Should NOT have "### Thursday"
        assert "### Thursday" not in markdown
        # Should have "Thursday, Jan. 29" without prefix
        assert "Thursday, Jan. 29" in markdown

    def test_conflict_in_day_header(self):
        """Conflict info should appear in the day header line."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 22, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 23, 0, tzinfo=timezone.utc),
                category="solo_adjust",
                conflicts=[
                    ConflictInfo(
                        participant="user1@example.com",
                        event_title="Team Standup",
                        event_time="2:00 PM",
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

        # Find the day header line
        day_header_line = [l for l in lines if "Thursday, Jan. 29" in l][0]

        # Conflict info should be on the same line with em-dash
        assert "—" in day_header_line
        assert "Team Standup" in day_header_line
        assert "User One" in day_header_line
