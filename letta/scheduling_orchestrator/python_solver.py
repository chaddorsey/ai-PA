"""
Pure Python constraint solver for scheduling optimization.

Replaces ASP/clingo backend with direct constraint checking and ranking.
Handles free slot finding, ranking by preferences, and single-meeting moves.
"""

from typing import Dict, List, Set, Optional, Tuple, Any
from datetime import datetime, timedelta
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
    
    # CRITICAL: Verify all participants have work hours defined
    # If any participant is missing work hours, this is a data integrity issue
    # that could lead to slots outside work hours being incorrectly marked as free
    missing_work_hours = []
    for participant_id in scheduling_problem.participants:
        participant_work_hours = work_hours_slots.get(participant_id, set())
        if not participant_work_hours and work_hours_slots:  # work_hours_slots dict exists but participant missing
            missing_work_hours.append(participant_id)
    
    if missing_work_hours:
        # Log warning but don't fail - might be intentional (allow_off_hours scenario)
        # The _find_free_slots function will handle this by rejecting slots when work hours are missing
        pass  # For now, just let _find_free_slots handle it with the stricter check
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
        context_json,
        normalized_data
    )
    
    if candidates:
        # Rank candidates by score (higher is better)
        candidates.sort(key=lambda x: x["score"], reverse=True)
        # Return top candidate (single solution - caller will handle multiple if needed)
        return candidates[0]
    
    # No solution found
    return None


def find_top_candidates(
    normalized_data: Dict[str, Any],
    scheduling_problem: SchedulingProblem,
    slot_indexer: SlotIndexer,
    context_json: Optional[Dict[str, Any]] = None,
    max_candidates: int = 10
) -> List[Dict[str, Any]]:
    """
    Find multiple top candidate solutions for diversity.
    
    Returns up to max_candidates solutions, ensuring diversity across days/times.
    """
    candidates = []
    
    # Get free slots
    all_slots = list(range(slot_indexer.total_slots))
    busy_slots = normalized_data["busy_slots"]
    work_hours_slots = normalized_data["work_hours_slots"]
    duration_slots = max(1, scheduling_problem.duration_minutes // 15)
    min_gap_slots = normalized_data.get("min_gap_slots", 0)
    
    free_slots = _find_free_slots(
        all_slots,
        busy_slots,
        work_hours_slots,
        scheduling_problem.participants,
        duration_slots,
        min_gap_slots
    )
    
    # Add free slot candidates
    for slot in sorted(free_slots):
        start_dt = slot_indexer.slot_to_datetime(slot)
        if start_dt:
            candidates.append({
                "start_slot": slot,
                "score": 1000,  # High score for free slots
                "moved_events": [],
                "method": "free_slot",
                "start_datetime": start_dt
            })
    
    # Get single-move candidates
    event_protection = normalized_data.get("event_protection", {})
    locked_events: Dict[str, Set[int]] = {}
    flexible_events: Dict[str, List[Dict[str, Any]]] = {}
    
    single_move_candidates = _find_slots_with_single_move(
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
        context_json,
        normalized_data
    )
    
    for candidate in single_move_candidates:
        start_dt = slot_indexer.slot_to_datetime(candidate["start_slot"])
        if start_dt:
            candidate["start_datetime"] = start_dt
            candidates.append(candidate)
    
    # Get solo-override candidates (slots that conflict only with solo events)
    solo_override_candidates = _find_slots_with_solo_override(
        all_slots,
        busy_slots,
        work_hours_slots,
        event_protection,
        scheduling_problem,
        slot_indexer,
        duration_slots,
        min_gap_slots,
        normalized_data
    )
    
    for candidate in solo_override_candidates:
        start_dt = slot_indexer.slot_to_datetime(candidate["start_slot"])
        if start_dt:
            candidate["start_datetime"] = start_dt
            candidates.append(candidate)
    
    # Sort by score
    candidates.sort(key=lambda x: x["score"], reverse=True)
    
    # Filter for diversity: ensure proposals span different days/times
    # Group by day and take best from each day
    from datetime import datetime
    import pytz
    
    # Group candidates by day (in a simple timezone)
    candidates_by_day: Dict[str, List[Dict[str, Any]]] = {}
    for candidate in candidates:
        start_dt = candidate.get("start_datetime")
        if start_dt:
            # Use a consistent timezone for day grouping (use UTC or first participant's timezone)
            if start_dt.tzinfo is None:
                start_dt = pytz.UTC.localize(start_dt)
            # Get date string (YYYY-MM-DD)
            day_key = start_dt.date().isoformat()
            if day_key not in candidates_by_day:
                candidates_by_day[day_key] = []
            candidates_by_day[day_key].append(candidate)
    
    # Select top candidates ensuring diversity
    selected = []
    selected_days = set()
    
    # If max_candidates is high enough, return all candidates (no filtering for diversity)
    # Otherwise, apply diversity filtering
    if max_candidates >= 1000:
        # Return all candidates - we'll filter by move count later
        selected = candidates
    else:
        # First pass: take best candidate from each day (up to max_candidates days)
        for day_key in sorted(candidates_by_day.keys()):
            if len(selected) >= max_candidates:
                break
            day_candidates = candidates_by_day[day_key]
            if day_candidates:
                # Best candidate for this day
                best = max(day_candidates, key=lambda x: x["score"])
                selected.append(best)
                selected_days.add(day_key)
        
        # Second pass: fill remaining slots with best overall candidates not yet selected
        for candidate in candidates:
            if len(selected) >= max_candidates:
                break
            start_dt = candidate.get("start_datetime")
            if start_dt:
                day_key = start_dt.date().isoformat()
                # Skip if we already have a candidate from this day (unless we have room)
                if day_key in selected_days and len(selected) >= max_candidates // 2:
                    continue
                # Check if already selected
                if candidate not in selected:
                    selected.append(candidate)
                    if day_key not in selected_days:
                        selected_days.add(day_key)
    
    # Remove start_datetime before returning (not part of expected format)
    for candidate in selected:
        candidate.pop("start_datetime", None)
    
    # If max_candidates is high, return all candidates (don't truncate)
    # Otherwise, limit to max_candidates
    if max_candidates >= 1000:
        return selected  # Return all candidates
    else:
        return selected[:max_candidates]


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
    context_json: Optional[Dict[str, Any]] = None,
    normalized_data: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Find slots that become available by moving one flexible meeting.
    
    Strategy:
    1. Identify candidate meeting slots (those that fail only due to single conflicts)
    2. For each candidate, find the flexible events blocking it
    3. Try moving each blocking event forward/backward by small amounts
    4. Verify the move creates space and doesn't violate constraints
    5. Rank solutions by disruption cost (smaller moves preferred, protected events cost more)
    
    Returns:
        List of candidate dicts with keys: start_slot, score, moved_events, method
    """
    if normalized_data is None:
        return []
    
    # Get event metadata and slots mapping from normalized_data
    event_metadata_map = normalized_data.get("event_metadata", {})
    event_slots_map_full = normalized_data.get("event_slots_map", {})
    
    if not event_metadata_map or not event_slots_map_full:
        # No event metadata available - can't do moves
        return []
    
    candidates = []
    max_slot = max(all_slots) if all_slots else 0
    
    # Constants for move exploration
    MAX_MOVE_SLOTS = 16  # Maximum 4 hours (16 * 15 min slots) to move an event
    MOVE_STEP_SLOTS = 1  # Try moves in 15-minute increments
    
    # Find candidate slots (slots where meeting would fit except for conflicts)
    # These are slots where only one participant has a conflict with a flexible event
    for candidate_slot in all_slots:
        if candidate_slot + duration_slots > max_slot + 1:
            continue
        
        # Check if this slot would be valid except for conflicts
        meeting_slots = range(candidate_slot, candidate_slot + duration_slots)
        
        # Check work hours for all participants
        # CRITICAL: Enforce work hours strictly - if any participant is missing work hours
        # or any meeting slot is outside work hours, reject this candidate
        work_hours_ok = True
        if work_hours_slots:  # Work hours dict exists (not empty dict)
            for participant_id in scheduling_problem.participants:
                participant_work_hours = work_hours_slots.get(participant_id, set())
                if participant_work_hours:  # Work hours defined for this participant
                    # All meeting slots must be within work hours
                    if not all(slot in participant_work_hours for slot in meeting_slots):
                        work_hours_ok = False
                        break
                else:
                    # Participant missing from work_hours_slots or has empty set
                    # This should not happen - fail the check to be safe
                    work_hours_ok = False
                    break
        # If work_hours_slots is empty dict, assume work hours are not enforced (allow_off_hours scenario)
        if not work_hours_ok:
            continue
        
        # Check time window
        if not _check_time_window(candidate_slot, scheduling_problem, slot_indexer, duration_slots):
            continue
        
        # Find which participants have conflicts at this slot
        conflicting_participants = []
        conflicting_events = []  # List of (participant_id, event_id) tuples
        locked_conflicts = []  # List of (participant_id, event_id) tuples for locked events
        
        for participant_id in scheduling_problem.participants:
            participant_busy = busy_slots.get(participant_id, set())
            conflicting_slots = set(meeting_slots).intersection(participant_busy)
            
            if conflicting_slots:
                conflicting_participants.append(participant_id)
                
                # Find which events are causing the conflict
                # Look through event_slots_map to find events that overlap with conflicting_slots
                for (p_id, e_id), slots in event_slots_map_full.items():
                    if p_id == participant_id and slots.intersection(conflicting_slots):
                        # Check if event is locked
                        protection = event_protection.get((p_id, e_id), "flexible")
                        if protection == "locked":
                            # Locked events cannot be moved - this slot is invalid
                            locked_conflicts.append((p_id, e_id))
                        elif protection != "locked":  # Can move flexible or protected
                            conflicting_events.append((p_id, e_id))
        
        # CRITICAL: Skip if there are any locked event conflicts
        # Locked events cannot be moved, so this slot cannot be scheduled
        if locked_conflicts:
            continue
        
        # Skip if multiple participants conflict (need multi-move, handled later)
        if len(conflicting_participants) > 1:
            continue
        
        # Skip if no single flexible event can resolve it
        if not conflicting_events:
            continue
        
        # Sort conflicting events by preference for moving:
        # 1. Internal-only meetings first (easier to reschedule)
        # 2. Fewer attendees first (easier to coordinate)
        # This helps us try preferred candidates first (though all will be scored)
        def event_preference_key(event_tuple):
            p_id, e_id = event_tuple
            event_key = (p_id, e_id)
            meta = event_metadata_map.get(event_key, {})
            internal = meta.get("internal_only", True)
            num_attendees = meta.get("number_of_attendees", 0)
            # Return tuple for sorting: (not internal, num_attendees)
            # Lower values sort first, so internal-only (False) comes before external (True)
            return (not internal, num_attendees)
        
        conflicting_events_sorted = sorted(conflicting_events, key=event_preference_key)
        
        # Try moving each conflicting flexible event
        for participant_id, event_id in conflicting_events_sorted:
            event_key = (participant_id, event_id)
            event_meta = event_metadata_map.get(event_key)
            if not event_meta:
                continue
            
            protection = event_protection.get(event_key, "flexible")
            current_event_slots = event_slots_map_full.get(event_key, set())
            
            if not current_event_slots:
                continue
            
            # Get event duration in slots
            event_duration_slots = len(current_event_slots)
            original_start_slot = min(current_event_slots)
            
            # Try moving the event forward and backward
            for move_direction in [-1, 1]:  # -1 = earlier, 1 = later
                for move_slots in range(MOVE_STEP_SLOTS, MAX_MOVE_SLOTS + 1, MOVE_STEP_SLOTS):
                    new_start_slot = original_start_slot + (move_direction * move_slots)
                    new_event_slots = set(range(new_start_slot, new_start_slot + event_duration_slots))
                    
                    # Validate move constraints
                    if new_start_slot < 0 or new_start_slot + event_duration_slots > max_slot + 1:
                        break  # Can't move further in this direction
                    
                    # Check work hours for moved event
                    participant_work_hours = work_hours_slots.get(participant_id, set())
                    if participant_work_hours and not all(slot in participant_work_hours for slot in new_event_slots):
                        # Moved event would be outside work hours - try next move
                        continue
                    
                    # Check if move creates space for meeting (no overlap)
                    if not new_event_slots.intersection(meeting_slots):
                        # Check if moved event creates new conflicts
                        # (simplified: just check if slots are free for this participant)
                        other_busy = busy_slots.get(participant_id, set()) - current_event_slots
                        if new_event_slots.intersection(other_busy):
                            # Would conflict with other events - try next move
                            continue
                        
                        # Check if meeting slot is now free for all participants
                        # CRITICAL: Also verify no locked events conflict (they cannot be moved)
                        all_free = True
                        blocking_participant = None
                        has_locked_conflict = False
                        
                        for p_id in scheduling_problem.participants:
                            p_busy = busy_slots.get(p_id, set())
                            if p_id == participant_id:
                                # For the participant whose event we moved, exclude old slots and include new
                                p_busy = (p_busy - current_event_slots) | new_event_slots
                            
                            # Check for conflicts
                            conflict_slots = set(meeting_slots).intersection(p_busy)
                            if conflict_slots:
                                # Check if any conflicting slots belong to locked events
                                for (p2_id, e2_id), slots in event_slots_map_full.items():
                                    if p2_id == p_id and slots.intersection(conflict_slots):
                                        protection = event_protection.get((p2_id, e2_id), "flexible")
                                        if protection == "locked":
                                            # Locked event conflict - cannot resolve by moving
                                            has_locked_conflict = True
                                            all_free = False
                                            blocking_participant = p_id
                                            break
                                
                                if has_locked_conflict:
                                    break
                                
                                # Non-locked conflict
                                all_free = False
                                blocking_participant = p_id
                                break
                        
                        if not all_free:
                            continue  # Continue to next move attempt
                        
                        if all_free:
                            # Found a valid move! Calculate score
                            move_minutes = move_slots * 15
                            
                            # Base score on disruption cost
                            # Lower disruption = higher score
                            # Protected events cost more to move (weight: 2x)
                            # Flexible events cost less (weight: 1x)
                            protection_weight = 2.0 if protection == "protected" else 1.0
                            disruption_cost = move_minutes * protection_weight
                            
                            # Prefer internal-only meetings over external ones
                            # Internal meetings are easier to reschedule (all @concord.org)
                            internal_only = event_meta.get("internal_only", True)  # Default to True for backwards compat
                            internal_bonus = 50.0 if internal_only else -50.0  # Bonus for internal, penalty for external
                            
                            # Prefer meetings with fewer participants
                            # Smaller meetings are easier to coordinate
                            num_attendees = event_meta.get("number_of_attendees", 0)
                            # Penalty increases with number of attendees (quadratic to strongly prefer smaller)
                            attendee_penalty = (num_attendees ** 2) * 2.0  # 0 attendees = 0, 1 = 2, 2 = 8, 5 = 50, 10 = 200
                            
                            # Prefer smaller moves (invert cost to get score)
                            # Add preference score for the meeting slot itself
                            preference_score = _compute_preference_score(candidate_slot, scheduling_problem, slot_indexer)
                            
                            # Combined score: lower disruption = higher score
                            # Add bonuses/penalties for internal-only and attendee count
                            # Scale appropriately to keep scores comparable
                            score = preference_score - (disruption_cost / 10.0) + (internal_bonus / 10.0) - (attendee_penalty / 10.0)
                            
                            # Create moved event details
                            old_start_dt = event_meta["start_dt"]
                            old_end_dt = event_meta["end_dt"]
                            event_duration = old_end_dt - old_start_dt
                            move_delta = timedelta(minutes=move_direction * move_minutes)
                            new_start_dt = old_start_dt + move_delta
                            new_end_dt = old_end_dt + move_delta
                            
                            moved_event = {
                                "owner": participant_id,
                                "event_id": event_id,
                                "old_start": old_start_dt.isoformat(),
                                "old_end": old_end_dt.isoformat(),
                                "new_start": new_start_dt.isoformat(),
                                "new_end": new_end_dt.isoformat(),
                                "shift_minutes": move_direction * move_minutes,
                                "title": event_meta.get("title", "")
                            }
                            
                            candidates.append({
                                "start_slot": candidate_slot,
                                "score": score,
                                "moved_events": [moved_event],
                                "method": "single_move",
                                "move_cost": disruption_cost,
                                "protection_level": protection
                            })
                            
                            # Found a valid move for this event - no need to try further moves
                            break
                
                # If we found a valid move, no need to try other directions
                if any(c["start_slot"] == candidate_slot and 
                       any(me["event_id"] == event_id for me in c["moved_events"]) 
                       for c in candidates):
                    break
    
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
        Dict with moved_minutes, focus_block_bonus, preference_penalty, protected_events_moved, priority_score
    """
    moved_events = solution.get("moved_events", [])
    moved_minutes = sum(me.get("shift_minutes", 0) for me in moved_events)
    protected_moved = sum(1 for me in moved_events if me.get("protected", False))
    
    # Focus block bonus and preference penalty would be computed from solution score
    # For now, use simplified values
    focus_bonus = int(solution.get("score", 0) * 0.2)  # Rough conversion
    preference_penalty = 0  # Would need to compute from preference violations
    
    # Extract the priority score from the solution (already calculated with attendee count, internal-only, etc.)
    priority_score = solution.get("score", 0.0)
    
    return {
        "moved_minutes": moved_minutes,
        "focus_block_bonus": focus_bonus,
        "preference_penalty": preference_penalty,
        "protected_events_moved": protected_moved,
        "priority_score": priority_score
    }


def _find_slots_with_solo_override(
    all_slots: List[int],
    busy_slots: Dict[str, Set[int]],
    work_hours_slots: Dict[str, Set[int]],
    event_protection: Dict[Tuple[str, str], str],
    scheduling_problem: SchedulingProblem,
    slot_indexer: SlotIndexer,
    duration_slots: int,
    min_gap_slots: int,
    normalized_data: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Find slots that become available by overriding solo events (zero attendees).
    
    Solo events are events with number_of_attendees == 0 that are:
    - Not locked
    - Not protected (or protected but flexible)
    
    These represent "Hold" or personal time blocks that can be overridden.
    
    Strategy:
    1. Find candidate slots where meeting conflicts only with solo events
    2. Verify these events are override-able (not locked, not protected)
    3. Score based on event properties (prefer shorter solo events, etc.)
    
    Returns:
        List of candidate dicts with keys: start_slot, score, moved_events (empty for overrides), method
    """
    if normalized_data is None:
        return []
    
    # Get event metadata and slots mapping from normalized_data
    event_metadata_map = normalized_data.get("event_metadata", {})
    event_slots_map_full = normalized_data.get("event_slots_map", {})
    
    if not event_metadata_map or not event_slots_map_full:
        return []
    
    candidates = []
    max_slot = max(all_slots) if all_slots else 0
    
    # Find candidate slots where meeting conflicts only with solo events
    for candidate_slot in all_slots:
        if candidate_slot + duration_slots > max_slot + 1:
            continue
        
        meeting_slots = range(candidate_slot, candidate_slot + duration_slots)
        
        # Check work hours for all participants
        work_hours_ok = True
        if work_hours_slots:
            for participant_id in scheduling_problem.participants:
                participant_work_hours = work_hours_slots.get(participant_id, set())
                if participant_work_hours:
                    if not all(slot in participant_work_hours for slot in meeting_slots):
                        work_hours_ok = False
                        break
                else:
                    work_hours_ok = False
                    break
        if not work_hours_ok:
            continue
        
        # Check time window
        if not _check_time_window(candidate_slot, scheduling_problem, slot_indexer, duration_slots):
            continue
        
        # Find conflicting events and check if they're all solo events
        conflicting_events = []  # List of (participant_id, event_id) tuples
        non_solo_conflicts = []  # Events that are not solo or not override-able
        
        for participant_id in scheduling_problem.participants:
            participant_busy = busy_slots.get(participant_id, set())
            conflicting_slots = set(meeting_slots).intersection(participant_busy)
            
            if conflicting_slots:
                # Find which events are causing the conflict
                for (p_id, e_id), slots in event_slots_map_full.items():
                    if p_id == participant_id and slots.intersection(conflicting_slots):
                        event_key = (p_id, e_id)
                        protection = event_protection.get(event_key, "flexible")
                        
                        # Skip locked events (cannot override)
                        if protection == "locked":
                            non_solo_conflicts.append(event_key)
                            continue
                        
                        # Check if this is a solo event (zero attendees)
                        event_meta = event_metadata_map.get(event_key, {})
                        num_attendees = event_meta.get("number_of_attendees", 0)
                        
                        # Check if protected but not flexible (cannot override)
                        protected = event_meta.get("protected", False)
                        flexible = event_meta.get("flexible", True)
                        if protected and not flexible:
                            non_solo_conflicts.append(event_key)
                            continue
                        
                        if num_attendees == 0:
                            # Solo event - can override
                            conflicting_events.append((p_id, e_id))
                        else:
                            # Not a solo event - cannot override
                            non_solo_conflicts.append(event_key)
        
        # Only consider this slot if:
        # 1. All conflicts are with solo events (conflicting_events is non-empty)
        # 2. No non-solo or locked conflicts exist
        if conflicting_events and not non_solo_conflicts:
            # Calculate score based on solo event properties
            # Prefer shorter solo events, fewer solo events, etc.
            total_solo_duration = 0
            for p_id, e_id in conflicting_events:
                event_key = (p_id, e_id)
                event_slots = event_slots_map_full.get(event_key, set())
                total_solo_duration += len(event_slots)
            
            # Score: Base score of 500 for solo override (lower than free slots 1000, lower than single_move ~600-900)
            # But higher than multi-move. Penalize by total duration of solo events overridden.
            score = 500 - (total_solo_duration * 2)
            
            candidates.append({
                "start_slot": candidate_slot,
                "score": score,
                "moved_events": [],  # No moves needed for overrides
                "method": "solo_override",
                "override_events": conflicting_events  # Track which events are being overridden
            })
    
    return candidates

