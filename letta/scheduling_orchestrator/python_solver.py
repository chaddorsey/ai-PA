"""
Pure Python constraint solver for scheduling optimization.

Replaces ASP/clingo backend with direct constraint checking and ranking.
Handles free slot finding, ranking by preferences, and single-meeting moves.
"""

from typing import Dict, List, Set, Optional, Tuple, Any
from datetime import datetime
import pytz

# Handle both relative and absolute imports
try:
    from .slot_indexer import SlotIndexer
    from .schemas import SchedulingProblem
    from .fact_generator import _find_free_slots
except (ImportError, ValueError):
    from slot_indexer import SlotIndexer
    from schemas import SchedulingProblem
    from fact_generator import _find_free_slots


def find_optimal_slot(
    normalized_data: Dict[str, Any],
    scheduling_problem: SchedulingProblem,
    slot_indexer: SlotIndexer,
    context_json: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Find optimal meeting slot using pure Python constraint checking and ranking.
    
    Args:
        normalized_data: Output from normalize_events()
        scheduling_problem: Parsed scheduling problem
        slot_indexer: Slot indexer for datetime conversions
        context_json: Optional context with preferences
        
    Returns:
        Dict with keys: start_slot, score, moved_events (if any), or None if no solution
    """
    all_slots = slot_indexer.get_all_slots()
    busy_slots: Dict[str, Set[int]] = normalized_data.get("busy_slots", {})
    work_hours_slots: Dict[str, Set[int]] = normalized_data.get("work_hours_slots", {})
    event_protection: Dict[Tuple[str, str], str] = normalized_data.get("event_protection", {})
    min_gap_slots: int = normalized_data.get("min_gap_slots", 0)
    
    # Extract locked events from event_protection
    locked_events: Dict[str, Set[int]] = {}
    for (participant_id, event_id), protection_level in event_protection.items():
        if protection_level == "locked":
            if participant_id not in locked_events:
                locked_events[participant_id] = set()
            # Find slots for this event (would need event data - simplified for now)
            # For now, we'll rely on _check_locked_events which uses the protection data
    
    # Flexible events not yet extracted - single-move logic can be enhanced later
    flexible_events: Dict[str, List[Dict[str, Any]]] = {}
    
    duration_slots = max(1, scheduling_problem.duration_minutes // 15)
    
    # Step 1: Find free slots (no moves required)
    # Note: _find_free_slots already checks work hours, so if work hours are too restrictive,
    # we might get no free slots. For debugging, we could try without work hours if needed.
    free_slots = _find_free_slots(
        all_slots,
        busy_slots,
        work_hours_slots,
        scheduling_problem.participants,
        duration_slots,
        min_gap_slots
    )
    
    # Only try without work hours if explicitly allowed by scheduling_problem
    # Don't automatically fall back - work hours should be respected unless user allows off-hours
    if not free_slots and scheduling_problem.allow_off_hours:
        # User explicitly allowed off-hours - try without work hours constraint
        free_slots_no_workhours = _find_free_slots(
            all_slots,
            busy_slots,
            {},  # Empty work hours - allow all slots
            scheduling_problem.participants,
            duration_slots,
            min_gap_slots
        )
        # If we found slots without work hours, use those
        if free_slots_no_workhours:
            free_slots = free_slots_no_workhours
    
    # Apply additional constraints that _find_free_slots might not check
    # (e.g., time window, locked events)
    constrained_free_slots = []
    time_window_failed = 0
    for slot in free_slots:
        time_window_ok = _check_time_window(slot, scheduling_problem, slot_indexer, duration_slots)
        locked_ok = _check_locked_events(slot, locked_events, scheduling_problem.participants, duration_slots)
        if not time_window_ok:
            time_window_failed += 1
        if time_window_ok and locked_ok:
            constrained_free_slots.append(slot)
    
    # Step 2: If free slots exist, rank and return best
    if constrained_free_slots:
        ranked = _rank_slots(
            constrained_free_slots,
            normalized_data,
            scheduling_problem,
            slot_indexer,
            context_json
        )
        if ranked:
            best_slot, best_score = ranked[0]
            return {
                "start_slot": best_slot,
                "score": best_score,
                "moved_events": [],
                "method": "free_slot"
            }
    
    # Step 3: No free slots - try single-meeting moves
    candidates = _find_slots_with_single_move(
        all_slots,
        busy_slots,
        work_hours_slots,
        locked_events,
        flexible_events,
        event_protection,
        scheduling_problem,
        slot_indexer,
        duration_slots,
        min_gap_slots,
        context_json
    )
    
    if candidates:
        # Rank candidates by score (higher is better)
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[0]
    
    # No solution found
    return None


def _check_time_window(
    slot: int,
    scheduling_problem: SchedulingProblem,
    slot_indexer: SlotIndexer,
    duration_slots: int = 0
) -> bool:
    """
    Check if slot (and meeting end) is within the allowed time window.
    
    For a meeting, we need to check that both the start AND end are within the window.
    """
    if not scheduling_problem.time_window_start or not scheduling_problem.time_window_end:
        return True  # No window constraint
    
    slot_dt = slot_indexer.slot_to_datetime(slot)
    if not slot_dt:
        return False
    
    # Calculate meeting end time
    if duration_slots > 0:
        end_slot = slot + duration_slots
        end_dt = slot_indexer.slot_to_datetime(end_slot)
        if not end_dt:
            return False
    else:
        end_dt = slot_dt
    
    try:
        window_start = datetime.fromisoformat(scheduling_problem.time_window_start.replace("Z", "+00:00"))
        window_end = datetime.fromisoformat(scheduling_problem.time_window_end.replace("Z", "+00:00"))
        
        if window_start.tzinfo is None:
            window_start = pytz.UTC.localize(window_start)
        else:
            window_start = window_start.astimezone(pytz.UTC)
        
        if window_end.tzinfo is None:
            window_end = pytz.UTC.localize(window_end)
        else:
            window_end = window_end.astimezone(pytz.UTC)
        
        # Check that meeting start is >= window_start and meeting end is <= window_end
        return window_start <= slot_dt and end_dt <= window_end
    except Exception:
        return True  # If parsing fails, allow the slot


def _check_locked_events(
    slot: int,
    locked_events: Dict[str, Set[int]],
    participants: List[str],
    duration_slots: int
) -> bool:
    """
    Check if slot overlaps with any locked events.
    
    Note: Locked events are already excluded by _find_free_slots (they're busy slots),
    so this is mainly a placeholder for future enhancements.
    """
    # Locked events are already handled by _find_free_slots excluding busy slots
    # This function is kept for future enhancements (e.g., explicit locked event checking)
    return True


def _rank_slots(
    free_slots: List[int],
    normalized_data: Dict[str, Any],
    scheduling_problem: SchedulingProblem,
    slot_indexer: SlotIndexer,
    context_json: Optional[Dict[str, Any]] = None
) -> List[Tuple[int, float]]:
    """
    Rank free slots by preferences.
    
    Returns:
        List of (slot, score) tuples, sorted by score (highest first)
    """
    ranked = []
    busy_slots: Dict[str, Set[int]] = normalized_data.get("busy_slots", {})
    event_protection: Dict[Tuple[str, str], str] = normalized_data.get("event_protection", {})
    
    for slot in free_slots:
        # Compute scores (higher is better)
        disruption_score = _compute_disruption_score(slot, busy_slots, scheduling_problem.participants, scheduling_problem.duration_minutes // 15)
        focus_bonus = _compute_focus_block_bonus(slot, busy_slots, scheduling_problem.participants, scheduling_problem.duration_minutes // 15)
        preference_score = _compute_preference_score(slot, scheduling_problem, slot_indexer)
        
        # Weighted sum (can be made lexicographic later if needed)
        total_score = (
            -disruption_score * 10.0 +  # Minimize disruption (negate and weight)
            focus_bonus * 5.0 +          # Maximize focus blocks
            preference_score * 2.0       # Respect preferences
        )
        
        ranked.append((slot, total_score))
    
    # Sort by score (highest first)
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def _compute_disruption_score(
    slot: int,
    busy_slots: Dict[str, Set[int]],
    participants: List[str],
    duration_slots: int
) -> float:
    """
    Compute disruption score (lower is better, so we'll negate it).
    
    Disruption is measured by:
    - Number of flexible events that would be moved
    - Proximity to busy slots (closer = more disruption)
    """
    disruption = 0.0
    meeting_slots = set(range(slot, slot + duration_slots))
    
    for participant_id in participants:
        participant_busy = busy_slots.get(participant_id, set())
        # Count how many busy slots are near the meeting
        for busy_slot in participant_busy:
            distance = abs(busy_slot - slot)
            if distance < duration_slots + 2:  # Within 2 slots of meeting
                disruption += 1.0 / (distance + 1)  # Closer = more disruption
    
    return disruption


def _compute_focus_block_bonus(
    slot: int,
    busy_slots: Dict[str, Set[int]],
    participants: List[str],
    duration_slots: int
) -> float:
    """
    Compute focus block bonus (longer consecutive free slots = better).
    
    Focus blocks are consecutive free slots. We reward slots that create
    or extend long focus blocks.
    """
    bonus = 0.0
    meeting_slots = set(range(slot, slot + duration_slots))
    
    for participant_id in participants:
        participant_busy = busy_slots.get(participant_id, set())
        
        # Check focus block before meeting
        before_free = 0
        check_slot = slot - 1
        while check_slot >= 0 and check_slot not in participant_busy:
            before_free += 1
            check_slot -= 1
        
        # Check focus block after meeting
        after_free = 0
        check_slot = slot + duration_slots
        max_slot = max(participant_busy) if participant_busy else slot + duration_slots + 10
        while check_slot <= max_slot and check_slot not in participant_busy:
            after_free += 1
            check_slot += 1
        
        # Bonus for longer focus blocks
        total_focus = before_free + duration_slots + after_free
        bonus += total_focus * 0.1  # Reward longer blocks
    
    return bonus


def _compute_preference_score(
    slot: int,
    scheduling_problem: SchedulingProblem,
    slot_indexer: SlotIndexer
) -> float:
    """Compute preference score based on preferred times and days."""
    score = 0.0
    slot_dt = slot_indexer.slot_to_datetime(slot)
    if not slot_dt:
        return 0.0
    
    # Check preferred times
    if scheduling_problem.preferred_times:
        for pref_time_str in scheduling_problem.preferred_times:
            try:
                pref_dt = datetime.fromisoformat(pref_time_str.replace("Z", "+00:00"))
                if pref_dt.tzinfo is None:
                    pref_dt = pytz.UTC.localize(pref_dt)
                else:
                    pref_dt = pref_dt.astimezone(pytz.UTC)
                
                # Score based on proximity to preferred time
                time_diff = abs((slot_dt - pref_dt).total_seconds() / 3600)  # Hours
                if time_diff < 1:  # Within 1 hour
                    score += 1.0 - time_diff  # Closer = higher score
            except Exception:
                pass
    
    # Check preferred days
    if scheduling_problem.preferred_days:
        day_map = {
            "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
            "Friday": 4, "Saturday": 5, "Sunday": 6
        }
        slot_weekday = slot_dt.weekday()
        for day_name in scheduling_problem.preferred_days:
            preferred_weekday = day_map.get(day_name.capitalize())
            if preferred_weekday == slot_weekday:
                score += 1.0
    
    return score


def _find_slots_with_single_move(
    all_slots: List[int],
    busy_slots: Dict[str, Set[int]],
    work_hours_slots: Dict[str, Set[int]],
    locked_events: Dict[str, Set[int]],
    flexible_events: Dict[str, List[Dict[str, Any]]],
    event_protection: Dict[Tuple[str, str], str],
    scheduling_problem: SchedulingProblem,
    slot_indexer: SlotIndexer,
    duration_slots: int,
    min_gap_slots: int,
    context_json: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Find slots that become available by moving one flexible meeting.
    
    Returns:
        List of candidate dicts with keys: start_slot, score, moved_events, method
    """
    candidates = []
    max_slot = max(all_slots) if all_slots else 0
    
    # For each participant, try moving their flexible events
    for participant_id in scheduling_problem.participants:
        participant_flexible = flexible_events.get(participant_id, [])
        participant_busy = busy_slots.get(participant_id, set())
        
        for event in participant_flexible:
            event_id = event.get("id")
            if not event_id:
                continue
            
            # Get event slots (simplified - would need to convert from event times)
            # For now, we'll use a heuristic: try moving events that conflict
            
            # Find potential new slots for this event
            # This is simplified - in a full implementation, we'd:
            # 1. Find the event's current slot range
            # 2. Try moving it to other slots
            # 3. Check if that makes the target slot free
            
            # For now, return empty - single-move logic can be enhanced later
            pass
    
    # Simplified: If we can't find single moves easily, return empty
    # This can be enhanced with more sophisticated move detection
    return candidates


def compute_move_deltas_python(
    solution: Dict[str, Any],
    normalized_data: Dict[str, Any],
    scheduling_problem: SchedulingProblem
) -> List[Dict[str, Any]]:
    """
    Compute moved events from Python solution.
    
    This is a placeholder - in a full implementation, we'd track which events
    were moved to create the solution.
    """
    moved_events = solution.get("moved_events", [])
    return moved_events


def compute_objective_scores_python(
    solution: Dict[str, Any],
    normalized_data: Dict[str, Any],
    scheduling_problem: SchedulingProblem
) -> Dict[str, Any]:
    """
    Compute objective scores from Python solution.
    
    Returns:
        Dict with moved_minutes, focus_block_bonus, preference_penalty, protected_events_moved
    """
    moved_events = solution.get("moved_events", [])
    moved_minutes = sum(me.get("shift_minutes", 0) for me in moved_events)
    protected_moved = sum(1 for me in moved_events if me.get("protected", False))
    
    # Focus block bonus and preference penalty would be computed from solution score
    # For now, use simplified values
    focus_bonus = int(solution.get("score", 0) * 0.2)  # Rough conversion
    preference_penalty = 0  # Would need to compute from preference violations
    
    return {
        "moved_minutes": moved_minutes,
        "focus_block_bonus": focus_bonus,
        "preference_penalty": preference_penalty,
        "protected_events_moved": protected_moved
    }

