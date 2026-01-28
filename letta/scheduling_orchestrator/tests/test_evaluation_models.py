"""Tests for evaluation data models."""
import pytest
from datetime import date, time, datetime
from typing import List


def test_proposed_window_creation():
    """ProposedWindow can be created with required fields."""
    from scheduling_orchestrator.evaluation_models import ProposedWindow, TimeRange

    window = ProposedWindow(
        date=date(2026, 1, 29),
        start_time=time(9, 0),
        end_time=time(17, 0),
        exclusions=[TimeRange(start=time(15, 30), end=time(16, 30))],
        raw_text="anytime but 3:30-4:30pm"
    )

    assert window.date == date(2026, 1, 29)
    assert window.start_time == time(9, 0)
    assert window.exclusions[0].start == time(15, 30)


def test_evaluated_slot_creation():
    """EvaluatedSlot can be created with category and conflicts."""
    from scheduling_orchestrator.evaluation_models import EvaluatedSlot, ConflictInfo

    slot = EvaluatedSlot(
        start=datetime(2026, 1, 29, 10, 0),
        end=datetime(2026, 1, 29, 10, 30),
        category="clean",
        conflicts=[],
        score=100.0
    )

    assert slot.category == "clean"
    assert slot.score == 100.0


def test_conflict_info_creation():
    """ConflictInfo captures conflict details."""
    from scheduling_orchestrator.evaluation_models import ConflictInfo

    conflict = ConflictInfo(
        participant="chad@example.com",
        event_title="Team Sync",
        event_time="10:00-11:00am",
        event_property="protected"
    )

    assert conflict.participant == "chad@example.com"
    assert conflict.event_property == "protected"


def test_evaluation_result_creation():
    """EvaluationResult groups slots by category."""
    from scheduling_orchestrator.evaluation_models import EvaluationResult, EvaluatedSlot

    result = EvaluationResult(
        clean_slots=[],
        solo_adjust_slots=[],
        multi_adjust_slots=[],
        no_availability_windows=["Fri 1/30 after 2pm"]
    )

    assert len(result.no_availability_windows) == 1
