"""
Slot evaluator for proposed time windows.

Evaluates proposed time windows against participant calendars to find
available meeting slots, categorizing by conflict level.
"""
from datetime import date, time, datetime, timedelta
from typing import Dict, List, Set, Tuple, Any, Optional

try:
    from .evaluation_models import (
        ProposedWindow, EvaluatedSlot, ConflictInfo, TimeRange
    )
except ImportError:
    from evaluation_models import (
        ProposedWindow, EvaluatedSlot, ConflictInfo, TimeRange
    )


SLOT_MINUTES = 15


def _time_to_slot(t: time) -> int:
    """Convert time to slot index (slots start at midnight)."""
    return t.hour * 4 + t.minute // SLOT_MINUTES


def _slot_to_time(slot: int) -> time:
    """Convert slot index to time."""
    hours = slot // 4
    minutes = (slot % 4) * SLOT_MINUTES
    return time(hours, minutes)


def _slot_to_datetime(window_date: date, slot: int) -> datetime:
    """Convert slot index and date to datetime."""
    t = _slot_to_time(slot)
    return datetime.combine(window_date, t)


def _is_in_exclusion(slot: int, exclusions: List[TimeRange]) -> bool:
    """Check if a slot falls within any exclusion range."""
    for exc in exclusions:
        start_slot = _time_to_slot(exc.start)
        end_slot = _time_to_slot(exc.end)
        if start_slot <= slot < end_slot:
            return True
    return False


def _get_conflict_for_slot(
    slot: int,
    duration_slots: int,
    participant: str,
    busy_slots: Set[int],
    event_details: Dict[Tuple[str, str], Dict]
) -> Optional[ConflictInfo]:
    """
    Check if a participant has a conflict for the given slot range.

    Returns ConflictInfo if there's a conflict, None otherwise.
    """
    meeting_slots = set(range(slot, slot + duration_slots))
    conflicting_slots = busy_slots.intersection(meeting_slots)

    if not conflicting_slots:
        return None

    # Find which event causes the conflict
    for (owner, event_id), details in event_details.items():
        if owner != participant:
            continue
        event_slots = details.get("slots", set())
        if event_slots.intersection(conflicting_slots):
            # Calculate time range for this conflict
            min_slot = min(conflicting_slots)
            max_slot = max(conflicting_slots) + 1
            start_time = _slot_to_time(min_slot)
            end_time = _slot_to_time(max_slot)

            return ConflictInfo(
                participant=participant,
                event_title=details.get("title", "Event"),
                event_time=f"{start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}",
                event_property=details.get("property", "busy")
            )

    # Generic conflict if no event details found
    return ConflictInfo(
        participant=participant,
        event_title="Busy",
        event_time="",
        event_property="busy"
    )


def find_available_slots(
    window: ProposedWindow,
    participants: List[str],
    duration_minutes: int,
    busy_slots: Dict[str, Set[int]],
    event_details: Dict[Tuple[str, str], Dict]
) -> List[EvaluatedSlot]:
    """
    Find available meeting slots within a proposed window.

    Args:
        window: Proposed time window to evaluate
        participants: List of participant emails
        duration_minutes: Required meeting duration
        busy_slots: Dict mapping participant -> set of busy slot indices
        event_details: Dict mapping (participant, event_id) -> event info
            with keys: property (locked/protected/flexible/transparent),
            title, slots (set of slot indices)

    Returns:
        List of EvaluatedSlot objects with category and conflicts
    """
    duration_slots = duration_minutes // SLOT_MINUTES

    # Calculate slot range for window
    start_slot = _time_to_slot(window.start_time)
    end_slot = _time_to_slot(window.end_time)

    results = []

    # Iterate through possible start times
    for slot in range(start_slot, end_slot - duration_slots + 1):
        # Check if any slot in meeting range is in exclusion
        meeting_range = range(slot, slot + duration_slots)
        if any(_is_in_exclusion(s, window.exclusions) for s in meeting_range):
            continue

        # Check each participant for conflicts
        conflicts = []
        has_locked = False

        for participant in participants:
            p_busy = busy_slots.get(participant, set())
            conflict = _get_conflict_for_slot(
                slot, duration_slots, participant, p_busy, event_details
            )

            if conflict:
                conflicts.append(conflict)
                if conflict.event_property == "locked":
                    has_locked = True

        # Skip slots with locked conflicts
        if has_locked:
            continue

        # Categorize the slot
        if not conflicts:
            category = "clean"
        elif len(conflicts) == 1:
            category = "solo_adjust"
        else:
            category = "multi_adjust"

        results.append(EvaluatedSlot(
            start=_slot_to_datetime(window.date, slot),
            end=_slot_to_datetime(window.date, slot + duration_slots),
            category=category,
            conflicts=conflicts,
            score=0.0  # Will be set by ranking
        ))

    return results
