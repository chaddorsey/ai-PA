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
    
    # Generate slot facts
    all_slots = slot_indexer.get_all_slots()
    for slot in all_slots:
        facts.append(f"slot({slot}).")
    
    # Generate request fact
    facts.append(f"request({request_id}).")
    
    # Generate needs facts (participants required)
    for participant_id in scheduling_problem.participants:
        facts.append(f"needs({request_id}, {participant_id}).")
    
    # Generate duration fact
    duration_slots = max(1, scheduling_problem.duration_minutes // 15)
    facts.append(f"duration({request_id}, {duration_slots}).")
    
    # Generate min_gap fact
    facts.append(f"min_gap({request_id}, {min_gap_slots}).")
    
    # Generate busy facts
    for participant_id, slots in busy_slots.items():
        for slot in sorted(slots):
            facts.append(f"busy({participant_id}, {slot}).")
    
    # Generate workhours facts
    for participant_id, slots in work_hours_slots.items():
        for slot in sorted(slots):
            facts.append(f"workhours({participant_id}, {slot}).")
    
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
    # If time_window_start and time_window_end are specified, use them
    # Otherwise, allow all slots that satisfy other constraints
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
        duration_slots = max(1, scheduling_problem.duration_minutes // 15)
        for slot in window_slots:
            if slot + duration_slots <= len(all_slots):
                facts.append(f"window({request_id}, {slot}).")
    else:
        # No window specified - allow all slots where meeting would fit
        duration_slots = max(1, scheduling_problem.duration_minutes // 15)
        for slot in all_slots:
            if slot + duration_slots <= len(all_slots):
                facts.append(f"window({request_id}, {slot}).")
    
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
        
        program = COMPLETE_ASP_PROGRAM
    else:
        program = BASE_ASP_PROGRAM
    
    return program + "\n% Facts:\n" + facts

