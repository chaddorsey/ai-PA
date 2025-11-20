"""
Generate ASP facts from normalized event data and scheduling problem.

Converts the output of normalize_events() and scheduling problem into ASP facts format.
"""

from typing import Dict, List, Set, Any, Tuple

# Handle both relative and absolute imports
try:
    from .slot_indexer import SlotIndexer
    from .schemas import SchedulingProblem
except (ImportError, ValueError):
    from slot_indexer import SlotIndexer
    from schemas import SchedulingProblem


def _slots_to_ranges(slots: List[int]) -> List[Tuple[int, int]]:
    """
    Convert a sorted list of slot indices to a list of (start, end) ranges.
    
    Args:
        slots: Sorted list of slot indices
        
    Returns:
        List of (start_slot, end_slot) tuples (inclusive ranges)
    """
    if not slots:
        return []
    
    ranges = []
    start = slots[0]
    end = slots[0]
    
    for slot in slots[1:]:
        if slot == end + 1:
            # Consecutive slot - extend current range
            end = slot
        else:
            # Gap found - save current range and start new one
            ranges.append((start, end))
            start = slot
            end = slot
    
    # Add final range
    ranges.append((start, end))
    
    return ranges


def _find_free_slots(
    all_slots: List[int],
    busy_slots: Dict[str, Set[int]],
    work_hours_slots: Dict[str, Set[int]],
    participants: List[str],
    duration_slots: int,
    min_gap_slots: int
) -> Set[int]:
    """
    Find slots where a meeting of duration_slots can start.
    
    A slot is "free" if:
    1. All participants are free for the entire meeting duration (slot to slot + duration_slots - 1)
    2. All slots in the meeting are within work hours for all participants
    3. The slot respects min_gap after any busy slots
    
    Args:
        all_slots: All slots in the horizon
        busy_slots: Mapping participant_id -> set of busy slot indices
        work_hours_slots: Mapping participant_id -> set of work hour slot indices
        participants: List of participant IDs required for the meeting
        duration_slots: Number of slots the meeting requires
        min_gap_slots: Minimum gap slots after busy slots
        
    Returns:
        Set of slot indices where the meeting can start
    """
    free_slots = set()
    max_slot = max(all_slots) if all_slots else 0
    
    for start_slot in all_slots:
        # Check if meeting would fit (start + duration <= horizon_end)
        if start_slot + duration_slots > max_slot + 1:
            continue
        
        # Check all slots in the meeting range
        meeting_slots = range(start_slot, start_slot + duration_slots)
        
        # Check if all participants are free for the entire meeting
        all_free = True
        for participant_id in participants:
            participant_busy = busy_slots.get(participant_id, set())
            
            # Check if any meeting slot is busy for this participant
            if any(slot in participant_busy for slot in meeting_slots):
                all_free = False
                break
            
            # Check work hours
            participant_work_hours = work_hours_slots.get(participant_id, set())
            if participant_work_hours:  # Only check if work hours are defined
                if not all(slot in participant_work_hours for slot in meeting_slots):
                    all_free = False
                    break
            
            # Check min_gap: no meeting can start within min_gap slots after any busy slot
            if min_gap_slots > 0:
                for busy_slot in participant_busy:
                    # If start_slot is within min_gap after busy_slot, it's not free
                    if busy_slot < start_slot <= busy_slot + min_gap_slots:
                        all_free = False
                        break
                if not all_free:
                    break
        
        if all_free:
            free_slots.add(start_slot)
    
    return free_slots


def generate_asp_facts(
    normalized_data: Dict[str, Any],
    scheduling_problem: SchedulingProblem,
    request_id: str = "q1"
) -> str:
    """
    Generate ASP facts from normalized data and scheduling problem.
    
    Args:
        normalized_data: Output from normalize_events()
        scheduling_problem: Parsed scheduling problem
        request_id: Identifier for this scheduling request (default: "q1")
        
    Returns:
        ASP facts as a string
    """
    slot_indexer: SlotIndexer = normalized_data["slot_indexer"]
    busy_slots: Dict[str, Set[int]] = normalized_data["busy_slots"]
    work_hours_slots: Dict[str, Set[int]] = normalized_data["work_hours_slots"]
    event_protection: Dict[Tuple[str, str], str] = normalized_data["event_protection"]
    min_gap_slots: int = normalized_data["min_gap_slots"]
    
    facts = []
    
    # Get slot range info instead of generating all slot facts
    all_slots = slot_indexer.get_all_slots()
    max_slot = len(all_slots) - 1 if all_slots else 0
    
    # Instead of generating slot(S) for every slot, we'll use a range rule in ASP
    # This saves thousands of facts for large horizons
    # We only generate slot facts for slots that are actually used (busy, work hours, etc.)
    used_slots = set()
    
    # Generate request fact
    facts.append(f"request({request_id}).")
    
    # Generate horizon fact (max slot index)
    facts.append(f"horizon_max({max_slot}).")
    
    # Generate needs facts (participants required)
    for participant_id in scheduling_problem.participants:
        facts.append(f"needs({request_id}, {participant_id}).")
    
    # Generate duration fact
    duration_slots = max(1, scheduling_problem.duration_minutes // 15)
    facts.append(f"duration({request_id}, {duration_slots}).")
    
    # Generate min_gap fact
    facts.append(f"min_gap({request_id}, {min_gap_slots}).")
    
    # Generate busy facts first (only for slots that are actually busy)
    # We need to track these for free slot calculation and explicit slot generation
    for participant_id, slots in busy_slots.items():
        for slot in sorted(slots):
            used_slots.add(slot)
    
    # OPTIMIZATION: Pre-filter to find free slots (inverse approach)
    # A slot is "free" if all participants are free for the entire meeting duration
    # This dramatically reduces the choice rule candidates from all slots to only feasible ones
    free_slots = _find_free_slots(
        all_slots,
        busy_slots,
        work_hours_slots,
        scheduling_problem.participants,
        duration_slots,
        min_gap_slots
    )
    
    # Generate free_slot facts only for actually free slots
    # This reduces grounding atoms by ~80-90% for typical calendars
    for slot in sorted(free_slots):
        facts.append(f"free_slot({slot}).")
        used_slots.add(slot)
    
    # Generate busy facts (only for slots that are actually busy)
    for participant_id, slots in busy_slots.items():
        for slot in sorted(slots):
            facts.append(f"busy({participant_id}, {slot}).")
    
    # OPTIMIZATION: Generate explicit slot facts only for used slots
    # Instead of using the range rule slot(S) :- horizon_max(M), S = 0..M
    # which generates atoms for ALL slots, we generate slot(S) facts only for
    # slots that are actually referenced (free, busy, work hours, etc.)
    # Also need to include slots that will be used by occurs() - meeting duration slots
    # For each free slot, we need slots for the meeting duration
    # OPTIMIZATION: Only generate slot facts for slots that are actually needed
    # This includes: free slots (start candidates), busy slots (constraints), 
    # and meeting duration slots (for occurs rule)
    meeting_duration_slots = set()
    for free_slot in free_slots:
        for offset in range(duration_slots):
            slot_idx = free_slot + offset
            if slot_idx <= max_slot:  # Ensure within horizon
                meeting_duration_slots.add(slot_idx)
    used_slots.update(meeting_duration_slots)
    
    # Generate explicit slot facts - this prevents the range rule from generating all slots
    for slot in sorted(used_slots):
        facts.append(f"slot({slot}).")
    
    # Generate workhours facts - OPTIMIZATION: Use range encoding for work hours
    # Instead of generating workhours(P, S) for every slot, we'll use workhours_range facts
    # This dramatically reduces fact count for large horizons
    for participant_id, slots in work_hours_slots.items():
        if not slots:
            continue
        
        # Track slots used by work hours for explicit slot generation
        used_slots.update(slots)
        
        # OPTIMIZATION: If work hours cover most slots, use inverse encoding (non-work hours)
        # Otherwise, use range encoding for work hours
        total_slots = max_slot + 1
        work_hours_ratio = len(slots) / total_slots if total_slots > 0 else 0
        
        if work_hours_ratio > 0.7:
            # Work hours cover >70% of slots - encode non-work hours instead (more efficient)
            non_work_slots = set(range(total_slots)) - slots
            if non_work_slots:
                # Generate ranges for non-work hours (fewer facts)
                non_work_ranges = _slots_to_ranges(sorted(non_work_slots))
                for start_slot, end_slot in non_work_ranges:
                    facts.append(f"non_workhours({participant_id}, {start_slot}, {end_slot}).")
        else:
            # Work hours cover <70% of slots - encode work hours as ranges
            work_ranges = _slots_to_ranges(sorted(slots))
            for start_slot, end_slot in work_ranges:
                facts.append(f"workhours_range({participant_id}, {start_slot}, {end_slot}).")
    
    # Generate locked_event facts (from event_protection)
    # We need to map back from event protection to slots
    # For now, we'll mark all busy slots of locked events as locked
    # In a more sophisticated version, we'd track which slots belong to which events
    for (participant_id, event_id), protection_level in event_protection.items():
        if protection_level == "locked" and participant_id in busy_slots:
            # Mark all busy slots for this participant as potentially locked
            # This is a simplification - ideally we'd track event boundaries
            for slot in busy_slots[participant_id]:
                facts.append(f"locked_event({participant_id}, {slot}).")
    
    # Generate window facts (allowed start slots)
    # OPTIMIZATION: Instead of generating window facts for every slot,
    # we use a range constraint in ASP when no specific window is given
    # Note: duration_slots was already calculated above
    if scheduling_problem.time_window_start and scheduling_problem.time_window_end:
        from datetime import datetime
        import pytz
        
        start_dt = datetime.fromisoformat(scheduling_problem.time_window_start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(scheduling_problem.time_window_end.replace("Z", "+00:00"))
        
        if start_dt.tzinfo is None:
            start_dt = pytz.UTC.localize(start_dt)
        else:
            start_dt = start_dt.astimezone(pytz.UTC)
        
        if end_dt.tzinfo is None:
            end_dt = pytz.UTC.localize(end_dt)
        else:
            end_dt = end_dt.astimezone(pytz.UTC)
        
        # Find slots in the window
        window_slots = slot_indexer.get_slots_in_range(start_dt, end_dt)
        
        # Only allow slots where the meeting would fit (start + duration <= horizon_end)
        # AND only include slots that are actually free (inverse approach)
        # This ensures window facts only reference slots we'll generate
        for slot in window_slots:
            if slot + duration_slots <= max_slot + 1:
                # Only add window fact if slot is in free_slots (will be generated)
                if slot in free_slots:
                    facts.append(f"window({request_id}, {slot}).")
                    used_slots.add(slot)
    else:
        # No window specified - generate window facts only for free slots
        # This ensures we only generate window atoms for slots that actually exist
        # and are feasible (inverse approach)
        for slot in sorted(free_slots):
            if slot + duration_slots <= max_slot + 1:
                facts.append(f"window({request_id}, {slot}).")
                used_slots.add(slot)
    
    return "\n".join(facts) + "\n"


def generate_asp_program(
    normalized_data: Dict[str, Any],
    scheduling_problem: SchedulingProblem,
    request_id: str = "q1",
    include_soft_constraints: bool = True
) -> str:
    """
    Generate complete ASP program (facts + encoding).
    
    Args:
        normalized_data: Output from normalize_events()
        scheduling_problem: Parsed scheduling problem
        request_id: Identifier for this scheduling request
        include_soft_constraints: Whether to include soft constraints (default: True)
        
    Returns:
        Complete ASP program as a string
    """
    # Handle both relative and absolute imports
    try:
        from .asp_encoding import BASE_ASP_PROGRAM, COMPLETE_ASP_PROGRAM
    except (ImportError, ValueError):
        from asp_encoding import BASE_ASP_PROGRAM, COMPLETE_ASP_PROGRAM
    
    facts = generate_asp_facts(normalized_data, scheduling_problem, request_id)
    
    # Add facts for soft constraints if needed
    if include_soft_constraints:
        # Add protected_event facts
        event_protection: Dict[Tuple[str, str], str] = normalized_data["event_protection"]
        busy_slots: Dict[str, Set[int]] = normalized_data["busy_slots"]
        
        for (participant_id, event_id), protection_level in event_protection.items():
            if protection_level == "protected" and participant_id in busy_slots:
                for slot in busy_slots[participant_id]:
                    facts += f"protected_event({participant_id}, {slot}).\n"
        
        # Add preferred_time facts if specified
        if scheduling_problem.preferred_times:
            from datetime import datetime
            import pytz
            slot_indexer = normalized_data["slot_indexer"]
            
            for pref_time_str in scheduling_problem.preferred_times:
                try:
                    pref_dt = datetime.fromisoformat(pref_time_str.replace("Z", "+00:00"))
                    if pref_dt.tzinfo is None:
                        pref_dt = pytz.UTC.localize(pref_dt)
                    else:
                        pref_dt = pref_dt.astimezone(pytz.UTC)
                    
                    slot = slot_indexer.datetime_to_slot(pref_dt)
                    if slot is not None:
                        facts += f"preferred_time({request_id}, {slot}).\n"
                except Exception:
                    pass
        
        # Add preferred_day facts if specified
        if scheduling_problem.preferred_days:
            # Map day names to numbers (0=Monday, 6=Sunday)
            day_map = {
                "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
                "Friday": 4, "Saturday": 5, "Sunday": 6
            }
            for day_name in scheduling_problem.preferred_days:
                day_num = day_map.get(day_name.capitalize())
                if day_num is not None:
                    facts += f"preferred_day({request_id}, {day_num}).\n"
        
        # Add participant facts for focus block calculation
        for participant_id in scheduling_problem.participants:
            facts += f"participant({participant_id}).\n"
        
        # Add participant facts for work hours encoding (needed for inverse encoding)
        work_hours_slots = normalized_data.get("work_hours_slots", {})
        for participant_id in scheduling_problem.participants:
            if participant_id in work_hours_slots:
                # Participant has work hours defined
                pass  # Already handled above
            else:
                # No work hours defined - will use fallback rule in ASP
                pass
        
        program = COMPLETE_ASP_PROGRAM
    else:
        program = BASE_ASP_PROGRAM
    
    return program + "\n% Facts:\n" + facts

