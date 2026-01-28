"""Tests for slot ranking."""
import pytest
from datetime import datetime


class TestScoreSlot:
    """Test slot scoring function."""

    def test_clean_scores_highest(self):
        """Clean slots score higher than adjustment slots."""
        from scheduling_orchestrator.ranking import score_slot
        from scheduling_orchestrator.evaluation_models import EvaluatedSlot

        clean = EvaluatedSlot(
            start=datetime(2026, 1, 29, 10, 0),
            end=datetime(2026, 1, 29, 10, 30),
            category="clean",
            conflicts=[]
        )

        solo = EvaluatedSlot(
            start=datetime(2026, 1, 29, 10, 0),
            end=datetime(2026, 1, 29, 10, 30),
            category="solo_adjust",
            conflicts=[]
        )

        multi = EvaluatedSlot(
            start=datetime(2026, 1, 29, 10, 0),
            end=datetime(2026, 1, 29, 10, 30),
            category="multi_adjust",
            conflicts=[]
        )

        clean_score = score_slot(clean, reference_date=datetime(2026, 1, 28).date())
        solo_score = score_slot(solo, reference_date=datetime(2026, 1, 28).date())
        multi_score = score_slot(multi, reference_date=datetime(2026, 1, 28).date())

        assert clean_score > solo_score > multi_score

    def test_sooner_dates_score_higher(self):
        """Earlier dates score higher than later dates."""
        from scheduling_orchestrator.ranking import score_slot
        from scheduling_orchestrator.evaluation_models import EvaluatedSlot

        tomorrow = EvaluatedSlot(
            start=datetime(2026, 1, 29, 10, 0),
            end=datetime(2026, 1, 29, 10, 30),
            category="clean",
            conflicts=[]
        )

        next_week = EvaluatedSlot(
            start=datetime(2026, 2, 4, 10, 0),
            end=datetime(2026, 2, 4, 10, 30),
            category="clean",
            conflicts=[]
        )

        tomorrow_score = score_slot(tomorrow, reference_date=datetime(2026, 1, 28).date())
        next_week_score = score_slot(next_week, reference_date=datetime(2026, 1, 28).date())

        assert tomorrow_score > next_week_score


class TestRankSlots:
    """Test slot ranking and sorting."""

    def test_sorts_by_category_then_date(self):
        """Slots are sorted by category first, then by date."""
        from scheduling_orchestrator.ranking import rank_slots
        from scheduling_orchestrator.evaluation_models import EvaluatedSlot

        slots = [
            EvaluatedSlot(
                start=datetime(2026, 1, 30, 10, 0),
                end=datetime(2026, 1, 30, 10, 30),
                category="solo_adjust",
                conflicts=[]
            ),
            EvaluatedSlot(
                start=datetime(2026, 1, 29, 10, 0),
                end=datetime(2026, 1, 29, 10, 30),
                category="clean",
                conflicts=[]
            ),
            EvaluatedSlot(
                start=datetime(2026, 1, 31, 10, 0),
                end=datetime(2026, 1, 31, 10, 30),
                category="clean",
                conflicts=[]
            ),
        ]

        ranked = rank_slots(slots, reference_date=datetime(2026, 1, 28).date())

        # Clean slots should come first, then sorted by date
        assert ranked[0].category == "clean"
        assert ranked[0].start.day == 29
        assert ranked[1].category == "clean"
        assert ranked[1].start.day == 31
        assert ranked[2].category == "solo_adjust"
