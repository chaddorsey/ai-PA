"""Tests for unified slot ranker."""

import pytest
from datetime import datetime, date, timezone, timedelta

# Import will fail until we create the module
from scheduling_orchestrator.unified_slot_ranker import rank_evaluated_slots
from scheduling_orchestrator.evaluation_models import EvaluatedSlot, ConflictInfo


class TestRankEvaluatedSlots:
    """Tests for rank_evaluated_slots function."""

    def test_ranks_clean_above_conflicts(self):
        """Clean slots should rank higher than conflicted slots."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 14, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 15, 0, tzinfo=timezone.utc),
                category="solo_adjust",
                conflicts=[
                    ConflictInfo(
                        participant="user1@example.com",
                        event_title="Meeting",
                        event_time="2:00 PM - 3:00 PM",
                        event_property="flexible"
                    )
                ]
            ),
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="clean",
                conflicts=[]
            ),
        ]

        ranked = rank_evaluated_slots(
            slots=slots,
            identity_id=None,
            participants=["user1@example.com", "user2@example.com"],
            reference_date=date(2026, 1, 28)
        )

        # Clean slot should be first
        assert ranked[0].category == "clean"
        assert ranked[1].category == "solo_adjust"
        # Scores should be assigned
        assert ranked[0].score > ranked[1].score

    def test_ranks_sooner_dates_higher(self):
        """Given same category, sooner dates should rank higher."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 31, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 31, 11, 0, tzinfo=timezone.utc),
                category="clean",
                conflicts=[]
            ),
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="clean",
                conflicts=[]
            ),
        ]

        ranked = rank_evaluated_slots(
            slots=slots,
            identity_id=None,
            participants=["user1@example.com"],
            reference_date=date(2026, 1, 28)
        )

        # Jan 29 should be first (sooner)
        assert ranked[0].start.day == 29
        assert ranked[1].start.day == 31
        # Score difference should be 4 points (2 days * 2 points/day)
        assert ranked[0].score - ranked[1].score == 4.0

    def test_handles_empty_slots(self):
        """Should handle empty slot list gracefully."""
        ranked = rank_evaluated_slots(
            slots=[],
            identity_id=None,
            participants=[]
        )
        assert ranked == []

    def test_multi_adjust_ranks_lowest(self):
        """Multi-adjust slots should rank below solo_adjust."""
        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="multi_adjust",
                conflicts=[
                    ConflictInfo(
                        participant="user1@example.com",
                        event_title="Meeting 1",
                        event_time="10:00 AM - 11:00 AM",
                        event_property="locked"
                    ),
                    ConflictInfo(
                        participant="user2@example.com",
                        event_title="Meeting 2",
                        event_time="10:00 AM - 11:00 AM",
                        event_property="protected"
                    )
                ]
            ),
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
                category="solo_adjust",
                conflicts=[
                    ConflictInfo(
                        participant="user1@example.com",
                        event_title="Meeting 1",
                        event_time="10:00 AM - 11:00 AM",
                        event_property="flexible"
                    )
                ]
            ),
        ]

        ranked = rank_evaluated_slots(
            slots=slots,
            identity_id=None,
            participants=["user1@example.com", "user2@example.com"],
            reference_date=date(2026, 1, 28)
        )

        # solo_adjust should come first
        assert ranked[0].category == "solo_adjust"
        assert ranked[1].category == "multi_adjust"

    def test_uses_today_as_default_reference_date(self):
        """Should use today's date as default reference if not provided."""
        today = date.today()

        # Create a slot for tomorrow
        tomorrow = datetime(today.year, today.month, today.day, 10, 0, tzinfo=timezone.utc)
        # Add 1 day
        tomorrow = tomorrow + timedelta(days=1)

        slots = [
            EvaluatedSlot(
                start=tomorrow,
                end=tomorrow + timedelta(hours=1),
                category="clean",
                conflicts=[]
            ),
        ]

        ranked = rank_evaluated_slots(
            slots=slots,
            identity_id=None,
            participants=["user1@example.com"]
            # No reference_date - should default to today
        )

        # Should have a score assigned
        assert ranked[0].score is not None
        # Score should be 100 (clean) - 2 (1 day out) = 98
        assert ranked[0].score == 98.0
