"""Tests for slot evaluator."""
import pytest
from datetime import date, time, datetime, timedelta
from typing import Dict, Set


def make_test_calendar(busy_ranges: list) -> Set[int]:
    """Helper to create busy_slots set from time ranges."""
    busy_slots = set()
    # Convert time ranges to slot indices (each slot is 15 min)
    # Assume slots start at midnight
    for start_hour, start_min, end_hour, end_min in busy_ranges:
        start_slot = start_hour * 4 + start_min // 15
        end_slot = end_hour * 4 + end_min // 15
        for slot in range(start_slot, end_slot):
            busy_slots.add(slot)
    return busy_slots


class TestFindAvailableSlots:
    """Test finding available slots within a window."""

    def test_clean_slot_all_free(self):
        """Finds clean slots when all participants are free."""
        from scheduling_orchestrator.slot_evaluator import find_available_slots
        from scheduling_orchestrator.evaluation_models import ProposedWindow

        window = ProposedWindow(
            date=date(2026, 1, 29),
            start_time=time(9, 0),
            end_time=time(12, 0),
            exclusions=[],
            raw_text="9am-12pm"
        )

        # Both participants have no events in this window
        busy_slots = {
            "chad@example.com": set(),
            "cynthia@example.com": set()
        }

        result = find_available_slots(
            window=window,
            participants=["chad@example.com", "cynthia@example.com"],
            duration_minutes=30,
            busy_slots=busy_slots,
            event_details={}
        )

        # Should find multiple 30-minute slots in 9am-12pm window
        assert len(result) > 0
        assert all(slot.category == "clean" for slot in result)

    def test_no_slots_when_fully_blocked(self):
        """Returns empty when window is fully blocked by locked event."""
        from scheduling_orchestrator.slot_evaluator import find_available_slots
        from scheduling_orchestrator.evaluation_models import ProposedWindow

        window = ProposedWindow(
            date=date(2026, 1, 29),
            start_time=time(9, 0),
            end_time=time(10, 0),
            exclusions=[],
            raw_text="9am-10am"
        )

        # Chad is busy for entire window with locked event
        busy_slots = {
            "chad@example.com": make_test_calendar([(9, 0, 10, 0)]),
            "cynthia@example.com": set()
        }

        # Event is locked - no adjustment possible
        event_details = {
            ("chad@example.com", "evt1"): {
                "property": "locked",
                "title": "Immovable Meeting",
                "slots": make_test_calendar([(9, 0, 10, 0)])
            }
        }

        result = find_available_slots(
            window=window,
            participants=["chad@example.com", "cynthia@example.com"],
            duration_minutes=30,
            busy_slots=busy_slots,
            event_details=event_details
        )

        # No clean slots, no adjustment possible for locked events
        clean = [s for s in result if s.category == "clean"]
        assert len(clean) == 0

    def test_solo_adjust_for_flexible_event(self):
        """Identifies solo_adjust when one person has flexible event."""
        from scheduling_orchestrator.slot_evaluator import find_available_slots
        from scheduling_orchestrator.evaluation_models import ProposedWindow

        window = ProposedWindow(
            date=date(2026, 1, 29),
            start_time=time(10, 0),
            end_time=time(11, 0),
            exclusions=[],
            raw_text="10am-11am"
        )

        # Chad has a flexible event at 10am
        busy_slots = {
            "chad@example.com": make_test_calendar([(10, 0, 10, 30)]),
            "cynthia@example.com": set()
        }

        event_details = {
            ("chad@example.com", "evt1"): {
                "property": "flexible",
                "title": "Moveable Hold",
                "slots": make_test_calendar([(10, 0, 10, 30)])
            }
        }

        result = find_available_slots(
            window=window,
            participants=["chad@example.com", "cynthia@example.com"],
            duration_minutes=30,
            busy_slots=busy_slots,
            event_details=event_details
        )

        # Should have slots marked as solo_adjust
        solo_adjust = [s for s in result if s.category == "solo_adjust"]
        assert len(solo_adjust) > 0


class TestExclusions:
    """Test exclusion handling within windows."""

    def test_slots_in_exclusion_are_skipped(self):
        """Slots within exclusion ranges should not be returned."""
        from scheduling_orchestrator.slot_evaluator import find_available_slots
        from scheduling_orchestrator.evaluation_models import ProposedWindow, TimeRange

        window = ProposedWindow(
            date=date(2026, 1, 29),
            start_time=time(9, 0),
            end_time=time(12, 0),
            exclusions=[TimeRange(start=time(10, 0), end=time(11, 0))],
            raw_text="9am-12pm except 10-11am"
        )

        busy_slots = {
            "chad@example.com": set(),
            "cynthia@example.com": set()
        }

        result = find_available_slots(
            window=window,
            participants=["chad@example.com", "cynthia@example.com"],
            duration_minutes=30,
            busy_slots=busy_slots,
            event_details={}
        )

        # No slots should start within the 10am-11am exclusion
        for slot in result:
            assert not (time(10, 0) <= slot.start.time() < time(11, 0))


class TestMultiAdjust:
    """Test multi_adjust categorization."""

    def test_multi_adjust_when_both_have_flexible_conflicts(self):
        """Identifies multi_adjust when multiple participants have conflicts."""
        from scheduling_orchestrator.slot_evaluator import find_available_slots
        from scheduling_orchestrator.evaluation_models import ProposedWindow

        window = ProposedWindow(
            date=date(2026, 1, 29),
            start_time=time(14, 0),
            end_time=time(15, 0),
            exclusions=[],
            raw_text="2pm-3pm"
        )

        # Both have flexible events at the same time
        busy_slots = {
            "chad@example.com": make_test_calendar([(14, 0, 14, 30)]),
            "cynthia@example.com": make_test_calendar([(14, 0, 14, 30)])
        }

        event_details = {
            ("chad@example.com", "evt1"): {
                "property": "flexible",
                "title": "Chad's Hold",
                "slots": make_test_calendar([(14, 0, 14, 30)])
            },
            ("cynthia@example.com", "evt2"): {
                "property": "flexible",
                "title": "Cynthia's Hold",
                "slots": make_test_calendar([(14, 0, 14, 30)])
            }
        }

        result = find_available_slots(
            window=window,
            participants=["chad@example.com", "cynthia@example.com"],
            duration_minutes=30,
            busy_slots=busy_slots,
            event_details=event_details
        )

        # Should have slots marked as multi_adjust
        multi_adjust = [s for s in result if s.category == "multi_adjust"]
        assert len(multi_adjust) > 0
        # The conflicts should include both participants
        for slot in multi_adjust:
            if slot.start.time() == time(14, 0):
                participants_with_conflicts = {c.participant for c in slot.conflicts}
                assert "chad@example.com" in participants_with_conflicts
                assert "cynthia@example.com" in participants_with_conflicts


class TestConflictInfo:
    """Test conflict information in results."""

    def test_conflict_includes_event_details(self):
        """Conflict info should include event title and property."""
        from scheduling_orchestrator.slot_evaluator import find_available_slots
        from scheduling_orchestrator.evaluation_models import ProposedWindow

        window = ProposedWindow(
            date=date(2026, 1, 29),
            start_time=time(15, 0),
            end_time=time(16, 0),
            exclusions=[],
            raw_text="3pm-4pm"
        )

        busy_slots = {
            "chad@example.com": make_test_calendar([(15, 0, 15, 30)]),
        }

        event_details = {
            ("chad@example.com", "evt1"): {
                "property": "protected",
                "title": "Important Meeting",
                "slots": make_test_calendar([(15, 0, 15, 30)])
            }
        }

        result = find_available_slots(
            window=window,
            participants=["chad@example.com"],
            duration_minutes=30,
            busy_slots=busy_slots,
            event_details=event_details
        )

        # Find the slot with the conflict
        conflicting_slots = [s for s in result if s.conflicts]
        assert len(conflicting_slots) > 0

        conflict = conflicting_slots[0].conflicts[0]
        assert conflict.participant == "chad@example.com"
        assert conflict.event_title == "Important Meeting"
        assert conflict.event_property == "protected"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_exact_duration_fit(self):
        """Window exactly matching duration should return one slot."""
        from scheduling_orchestrator.slot_evaluator import find_available_slots
        from scheduling_orchestrator.evaluation_models import ProposedWindow

        window = ProposedWindow(
            date=date(2026, 1, 29),
            start_time=time(9, 0),
            end_time=time(9, 30),
            exclusions=[],
            raw_text="9am-9:30am"
        )

        busy_slots = {"chad@example.com": set()}

        result = find_available_slots(
            window=window,
            participants=["chad@example.com"],
            duration_minutes=30,
            busy_slots=busy_slots,
            event_details={}
        )

        # Should return exactly one slot
        assert len(result) == 1
        assert result[0].start.time() == time(9, 0)
        assert result[0].end.time() == time(9, 30)

    def test_duration_longer_than_window(self):
        """Returns empty when required duration exceeds window size."""
        from scheduling_orchestrator.slot_evaluator import find_available_slots
        from scheduling_orchestrator.evaluation_models import ProposedWindow

        window = ProposedWindow(
            date=date(2026, 1, 29),
            start_time=time(9, 0),
            end_time=time(9, 30),
            exclusions=[],
            raw_text="9am-9:30am"
        )

        busy_slots = {"chad@example.com": set()}

        result = find_available_slots(
            window=window,
            participants=["chad@example.com"],
            duration_minutes=60,  # 1 hour required, but window is only 30 min
            busy_slots=busy_slots,
            event_details={}
        )

        # Should return empty - can't fit 60 min meeting in 30 min window
        assert len(result) == 0

    def test_transparent_events_treated_as_free(self):
        """Transparent events should not create conflicts."""
        from scheduling_orchestrator.slot_evaluator import find_available_slots
        from scheduling_orchestrator.evaluation_models import ProposedWindow

        window = ProposedWindow(
            date=date(2026, 1, 29),
            start_time=time(10, 0),
            end_time=time(11, 0),
            exclusions=[],
            raw_text="10am-11am"
        )

        # Chad has a transparent event - should be ignored
        busy_slots = {
            "chad@example.com": set(),  # Transparent events don't block
        }

        event_details = {
            ("chad@example.com", "evt1"): {
                "property": "transparent",
                "title": "OOO - Working Remotely",
                "slots": make_test_calendar([(10, 0, 11, 0)])
            }
        }

        result = find_available_slots(
            window=window,
            participants=["chad@example.com"],
            duration_minutes=30,
            busy_slots=busy_slots,
            event_details=event_details
        )

        # All slots should be clean since transparent events don't block
        assert len(result) > 0
        assert all(slot.category == "clean" for slot in result)
