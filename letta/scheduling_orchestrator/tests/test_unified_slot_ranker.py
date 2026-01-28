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


class TestPreferenceScoring:
    """Tests for preference scoring integration (Task 1.2)."""

    def test_applies_avoid_penalty(self):
        """Slots on avoided days should score lower."""
        # Create two clean slots: one on Thursday (avoided), one on Friday
        # Thursday = weekday 3, Friday = weekday 4
        # 2026-01-29 is Thursday, 2026-01-30 is Friday
        thursday_slot = EvaluatedSlot(
            start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
            category="clean",
            conflicts=[]
        )
        friday_slot = EvaluatedSlot(
            start=datetime(2026, 1, 30, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 30, 11, 0, tzinfo=timezone.utc),
            category="clean",
            conflicts=[]
        )

        # Context with avoid_days preference for Thursday
        context_json = {
            "participants": [
                {
                    "id": "user1@example.com",
                    "preferences": {
                        "avoid_days": ["Thursday"]
                    }
                }
            ]
        }

        ranked = rank_evaluated_slots(
            slots=[thursday_slot, friday_slot],
            identity_id=None,
            participants=["user1@example.com"],
            context_json=context_json,
            reference_date=date(2026, 1, 28)
        )

        # Friday slot should rank first (no avoid penalty)
        assert ranked[0].start.day == 30  # Friday
        assert ranked[1].start.day == 29  # Thursday
        # Thursday should have lower score due to avoid penalty
        assert ranked[0].score > ranked[1].score

    def test_applies_preferred_bonus(self):
        """Slots matching preferred times should score higher."""
        # Create two clean slots on same day: one in morning (preferred), one in afternoon
        # Morning = 9am-12pm
        morning_slot = EvaluatedSlot(
            start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),  # 10am
            end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
            category="clean",
            conflicts=[]
        )
        afternoon_slot = EvaluatedSlot(
            start=datetime(2026, 1, 29, 14, 0, tzinfo=timezone.utc),  # 2pm
            end=datetime(2026, 1, 29, 15, 0, tzinfo=timezone.utc),
            category="clean",
            conflicts=[]
        )

        # Context with preferred_times for morning
        context_json = {
            "participants": [
                {
                    "id": "user1@example.com",
                    "preferences": {
                        "preferred_times": ["morning"]  # 9am-12pm
                    }
                }
            ]
        }

        ranked = rank_evaluated_slots(
            slots=[afternoon_slot, morning_slot],  # Reverse order to test sorting
            identity_id=None,
            participants=["user1@example.com"],
            context_json=context_json,
            reference_date=date(2026, 1, 28)
        )

        # Morning slot should rank first (preferred bonus)
        assert ranked[0].start.hour == 10  # Morning
        assert ranked[1].start.hour == 14  # Afternoon
        # Morning should have higher score due to preferred bonus
        assert ranked[0].score > ranked[1].score

    def test_avoid_overrides_preferred(self):
        """Avoid preferences should override preferred when both apply."""
        # Create two clean slots: one matching both avoid and prefer, one neutral
        # Thursday morning - matches both avoid_days (Thursday) and preferred_times (morning)
        thursday_morning = EvaluatedSlot(
            start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
            category="clean",
            conflicts=[]
        )
        # Friday afternoon - neutral
        friday_afternoon = EvaluatedSlot(
            start=datetime(2026, 1, 30, 14, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 30, 15, 0, tzinfo=timezone.utc),
            category="clean",
            conflicts=[]
        )

        context_json = {
            "participants": [
                {
                    "id": "user1@example.com",
                    "preferences": {
                        "avoid_days": ["Thursday"],
                        "preferred_times": ["morning"]
                    }
                }
            ]
        }

        ranked = rank_evaluated_slots(
            slots=[thursday_morning, friday_afternoon],
            identity_id=None,
            participants=["user1@example.com"],
            context_json=context_json,
            reference_date=date(2026, 1, 28)
        )

        # Friday should rank first because avoid penalty outweighs prefer bonus
        assert ranked[0].start.day == 30  # Friday
        assert ranked[1].start.day == 29  # Thursday

    def test_no_context_means_no_preference_score(self):
        """Without context_json, preference scoring should not apply."""
        slot = EvaluatedSlot(
            start=datetime(2026, 1, 29, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 29, 11, 0, tzinfo=timezone.utc),
            category="clean",
            conflicts=[]
        )

        ranked = rank_evaluated_slots(
            slots=[slot],
            identity_id=None,
            participants=["user1@example.com"],
            context_json=None,  # No context
            reference_date=date(2026, 1, 28)
        )

        # Score should only be category + date proximity
        # 100 (clean) - 2 (1 day out) = 98
        assert ranked[0].score == 98.0
