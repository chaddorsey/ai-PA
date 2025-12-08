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
            # CRITICAL: Always enforce work hours when they are defined
            # If work_hours_slots dict is completely empty ({}), that means caller explicitly
            # wants to bypass work hours (e.g., when allow_off_hours=True)
            # Otherwise, work hours MUST be enforced
            if work_hours_slots:  # Work hours dict exists (not empty dict)
                if participant_work_hours:  # Work hours are defined for this participant (non-empty set)
                    # Enforce work hours: all meeting slots must be within work hours
                    if not all(slot in participant_work_hours for slot in meeting_slots):
                        all_free = False
                        break
                else:
                    # Participant missing from work_hours_slots or has empty set
                    # This should not happen if normalization properly applied defaults
                    # However, rather than rejecting out of hand, we should log a warning
                    # and conservatively reject the slot (since we can't apply defaults here without context)
                    # The caller (orchestrate_scheduling) should ensure all participants have work hours
                    # before calling this function.
                    # For now, reject to be safe - this indicates a data integrity issue upstream
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
    request_id: str = "q1",
    include_work_hours: bool = True,
    include_min_gap: bool = True,
    include_locked_events: bool = True,
    allow_overlaps: bool = False
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
        # Quote participant_id to handle special characters like @ in email addresses
        facts.append(f'needs({request_id}, "{participant_id}").')
    
    # Generate duration fact
    duration_slots = max(1, scheduling_problem.duration_minutes // 15)
    facts.append(f"duration({request_id}, {duration_slots}).")
    
    # Generate min_gap fact (only if include_min_gap is True)
    if include_min_gap:
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
    
    # OPTIMIZATION: For multi-move (allow_overlaps), we need to consider all slots
    # For normal mode, limit free slots to reduce fact count
    if allow_overlaps:
        # Multi-move mode: Generate candidate slots from all work-hours slots, not just free
        # This allows ASP to find solutions by overlapping with flexible events
        # BUT: We must limit aggressively to avoid clingo "too many messages" error
        
        # Strategy: Prioritize slots with fewer conflicts (more likely to be solvable)
        # Count conflicts per slot
        slot_conflict_count: Dict[int, int] = {}
        candidate_slots_raw = set()
        
        for participant_id in scheduling_problem.participants:
            participant_work_hours = work_hours_slots.get(participant_id, set())
            participant_busy = busy_slots.get(participant_id, set())
            candidate_slots_raw.update(participant_work_hours)
            
            # Count conflicts for each slot
            for slot in participant_work_hours:
                if slot not in slot_conflict_count:
                    slot_conflict_count[slot] = 0
                if slot in participant_busy:
                    slot_conflict_count[slot] += 1
        
        # Prioritize slots: free slots first, then slots with 1 conflict, then 2, etc.
        # This helps ASP find solutions faster and reduces fact count
        # Increased limit to allow multi-day exploration (300 slots ≈ 3 days)
        MAX_CANDIDATE_SLOTS_FOR_ASP = 300  # Limit to 300 candidate slots max for extensive multi-day exploration
        
        candidate_slots_by_priority = {
            0: [],  # Free slots
            1: [],  # 1 conflict
            2: [],  # 2 conflicts
            3: []   # 3+ conflicts
        }
        
        for slot in candidate_slots_raw:
            conflicts = slot_conflict_count.get(slot, 0)
            if conflicts == 0:
                candidate_slots_by_priority[0].append(slot)
            elif conflicts == 1:
                candidate_slots_by_priority[1].append(slot)
            elif conflicts == 2:
                candidate_slots_by_priority[2].append(slot)
            else:
                candidate_slots_by_priority[3].append(slot)
        
        # Select slots in priority order until we hit the limit
        candidate_slots_limited = []
        for priority in [0, 1, 2, 3]:
            if len(candidate_slots_limited) >= MAX_CANDIDATE_SLOTS_FOR_ASP:
                break
            remaining = MAX_CANDIDATE_SLOTS_FOR_ASP - len(candidate_slots_limited)
            candidate_slots_limited.extend(sorted(candidate_slots_by_priority[priority])[:remaining])
        
        candidate_slots_limited = sorted(candidate_slots_limited)
        candidate_slots_set = set(candidate_slots_limited)
        
        # Still mark free slots for optimization (ASP can prefer them)
        free_slots_in_candidates = [s for s in free_slots if s in candidate_slots_set]
        for slot in sorted(free_slots_in_candidates):
            facts.append(f"free_slot({slot}).")
            used_slots.add(slot)
        
        slots_for_occurs = candidate_slots_limited
    else:
        # Normal mode: Limit free slots for phase 1 to reduce fact count
        MAX_FREE_SLOTS_FOR_PHASE1 = 50
        if not include_work_hours and len(free_slots) > MAX_FREE_SLOTS_FOR_PHASE1:
            # Phase 1: Limit to first N free slots to reduce occurs_if_start fact count
            free_slots_limited = sorted(free_slots)[:MAX_FREE_SLOTS_FOR_PHASE1]
        else:
            # Phase 2+: Use all free slots (should be fewer due to work hours filtering)
            free_slots_limited = sorted(free_slots)
        
        # Generate free_slot facts only for limited free slots
        # This reduces grounding atoms by ~80-90% for typical calendars
        for slot in free_slots_limited:
            facts.append(f"free_slot({slot}).")
            used_slots.add(slot)
        
        candidate_slots_limited = free_slots_limited
        slots_for_occurs = free_slots_limited
    
    # Generate busy facts (only for slots that are actually busy)
    # OPTIMIZATION: For multi-move, only generate busy facts for candidate slots
    # This dramatically reduces fact count since we only care about conflicts in candidate areas
    if allow_overlaps:
        # Only generate busy facts for candidate slots (where we might place the meeting)
        candidate_slots_set = set(candidate_slots_limited)
        for participant_id, slots in busy_slots.items():
            for slot in sorted(slots):
                if slot in candidate_slots_set:
                    facts.append(f'busy("{participant_id}", {slot}).')
    else:
        # Normal mode: generate all busy facts
        for participant_id, slots in busy_slots.items():
            for slot in sorted(slots):
                facts.append(f'busy("{participant_id}", {slot}).')
    
    # OPTIMIZATION: Pre-generate occurs() facts to eliminate range constraint
    # Instead of using the rule occurs(Q, T) :- start(Q, T0), duration(Q, D), slot(T), T >= T0, T < T0 + D
    # which generates many atoms during grounding, we pre-generate explicit occurs facts
    # slots_for_occurs is already set above (free_slots for normal mode, all work-hours slots for multi-move)
    
    # OPTIMIZATION: Limit occurs_if_start facts to reduce grounding
    # For multi-move with many candidate slots, this can generate thousands of facts
    # Limit to first N candidate slots to keep fact count manageable
    # For multi-move, be even more conservative
    MAX_OCCURS_CANDIDATES = 30 if allow_overlaps else 100  # Maximum number of start slots to generate occurs facts for
    
    # Pre-generate occurs_if_start facts (limit aggressively for ASP)
    # These facts are critical but can generate many atoms
    meeting_duration_slots = set()
    
    # For multi-move (allow_overlaps), be more conservative with occurs_if_start
    if allow_overlaps:
        # Limit occurs_if_start to first 100 candidate slots to reduce fact explosion
        MAX_OCCURS_CANDIDATES = 100
        occurs_candidates = slots_for_occurs[:MAX_OCCURS_CANDIDATES]
    else:
        occurs_candidates = slots_for_occurs
    
    for start_slot in occurs_candidates:
        # Pre-generate occurs facts for this meeting start
        # Only if meeting would fit within horizon
        if start_slot + duration_slots <= max_slot + 1:
            for offset in range(duration_slots):
                slot_idx = start_slot + offset
                if slot_idx <= max_slot:  # Ensure within horizon
                    facts.append(f"occurs_if_start({request_id}, {start_slot}, {slot_idx}).")
                    meeting_duration_slots.add(slot_idx)
    
    used_slots.update(meeting_duration_slots)
    
    # OPTIMIZATION: Generate explicit slot facts only for used slots
    # Instead of using the range rule slot(S) :- horizon_max(M), S = 0..M
    # which generates atoms for ALL slots, we generate slot(S) facts only for
    # slots that are actually referenced (free, busy, work hours, etc.)
    for slot in sorted(used_slots):
        facts.append(f"slot({slot}).")
    
    # Generate workhours facts (only if include_work_hours is True)
    if include_work_hours:
        # OPTIMIZATION: Use range encoding for work hours
        # Instead of generating workhours(P, S) for every slot, we'll use workhours_range facts
        # This dramatically reduces fact count for large horizons
        for participant_id, slots in work_hours_slots.items():
            if not slots:
                continue
            
            # OPTIMIZATION: Generate explicit workhours facts only for slots that are actually used
            # Instead of using range rules which generate many atoms, generate facts only for:
            # 1. Free slots (meeting candidates)
            # 2. Meeting duration slots (for occurs rule)
            # 3. Busy slots (for constraint checking)
            workhours_slots_to_generate = used_slots.intersection(slots)
            
            if workhours_slots_to_generate:
                # Generate explicit workhours facts only for used slots
                for slot in sorted(workhours_slots_to_generate):
                    facts.append(f'workhours("{participant_id}", {slot}).')
            else:
                # If no intersection, use range encoding as fallback (but only for used slots)
                # This is a compromise - still uses ranges but only for slots we care about
                work_ranges = _slots_to_ranges(sorted(slots.intersection(used_slots)))
                for start_slot, end_slot in work_ranges:
                    facts.append(f'workhours_range("{participant_id}", {start_slot}, {end_slot}).')
    
    # Generate locked_event facts (only if include_locked_events is True)
    if include_locked_events:
        # CRITICAL: Only mark slots that belong to locked events, not all busy slots
        # Use event_slots_map to find which slots belong to which events
        event_slots_map = normalized_data.get("event_slots_map", {})
        for (participant_id, event_id), protection_level in event_protection.items():
            if protection_level == "locked":
                # Find slots for this specific locked event
                event_key = (participant_id, event_id)
                if event_key in event_slots_map:
                    # Mark only the slots that belong to this locked event
                    for slot in event_slots_map[event_key]:
                        facts.append(f'locked_event("{participant_id}", {slot}).')
    
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
        window_slots_set = set(window_slots)
        
        # Only allow slots where the meeting would fit (start + duration <= horizon_end)
        if allow_overlaps:
            # Multi-move: Use candidate_slots_set (already limited and prioritized)
            # This ensures window facts only reference slots we'll actually consider
            candidate_slots_set = set(candidate_slots_limited) if 'candidate_slots_limited' in locals() else set()
            import sys
            window_facts_generated = 0
            debug_window_slots_not_in_candidates = []
            for slot in window_slots:
                if slot + duration_slots <= max_slot + 1:
                    # Check if slot is in candidate slots
                    if slot in candidate_slots_set:
                        facts.append(f"window({request_id}, {slot}).")
                        used_slots.add(slot)
                        window_facts_generated += 1
                    else:
                        # Debug: Track slots that are in window but not in candidates
                        slot_dt = slot_indexer.slot_to_datetime(slot)
                        if slot_dt:
                            debug_window_slots_not_in_candidates.append((slot, slot_dt))
            
            # Debug logging for multi-move mode
            if window_facts_generated == 0:
                if len(window_slots) == 0:
                    # Critical: window_slots is empty - this means get_slots_in_range returned nothing
                    print(f"[FACT_GEN] ERROR (multi-move): window_slots is EMPTY - get_slots_in_range returned 0 slots!", file=sys.stderr, flush=True)
                    print(f"  Window range: {start_dt.isoformat()} to {end_dt.isoformat()}", file=sys.stderr, flush=True)
                    print(f"  Candidate slots (limited): {len(candidate_slots_limited)} slots", file=sys.stderr, flush=True)
                    # Check horizon bounds
                    horizon_start = slot_indexer.horizon_start
                    horizon_end = slot_indexer.horizon_end
                    print(f"  Horizon range: {horizon_start.isoformat()} to {horizon_end.isoformat()}", file=sys.stderr, flush=True)
                    print(f"  Window overlaps horizon? {start_dt < horizon_end and end_dt > horizon_start}", file=sys.stderr, flush=True)
                    if len(candidate_slots_limited) > 0 and len(candidate_slots_limited) <= 10:
                        print(f"  Candidate slot indices: {sorted(candidate_slots_limited)}", file=sys.stderr, flush=True)
                        # Check first candidate slot's time
                        first_candidate = sorted(candidate_slots_limited)[0]
                        first_candidate_dt = slot_indexer.slot_to_datetime(first_candidate)
                        if first_candidate_dt:
                            print(f"  First candidate slot {first_candidate} time: {first_candidate_dt.isoformat()}", file=sys.stderr, flush=True)
                            print(f"  In window range? {start_dt <= first_candidate_dt <= end_dt}", file=sys.stderr, flush=True)
                elif len(window_slots) > 0:
                    # Window slots exist but no facts generated - intersection issue
                    print(f"[FACT_GEN] WARNING (multi-move): {len(window_slots)} window slots but 0 window facts generated", file=sys.stderr, flush=True)
                    print(f"  Window range: {start_dt.isoformat()} to {end_dt.isoformat()}", file=sys.stderr, flush=True)
                    print(f"  Window slots from get_slots_in_range: {len(window_slots)} slots", file=sys.stderr, flush=True)
                    print(f"  Candidate slots (limited): {len(candidate_slots_limited)} slots", file=sys.stderr, flush=True)
                    if len(window_slots) > 0 and len(window_slots) <= 10:
                        print(f"  Window slot indices: {sorted(window_slots)}", file=sys.stderr, flush=True)
                    if len(candidate_slots_limited) > 0 and len(candidate_slots_limited) <= 10:
                        print(f"  Candidate slot indices: {sorted(candidate_slots_limited)}", file=sys.stderr, flush=True)
                    # Check intersection
                    window_slots_set = set(window_slots)
                    candidate_slots_set_check = set(candidate_slots_limited)
                    intersection = window_slots_set.intersection(candidate_slots_set_check)
                    print(f"  Intersection: {len(intersection)} slots", file=sys.stderr, flush=True)
                    if len(intersection) > 0 and len(intersection) <= 10:
                        print(f"  Intersection slot indices: {sorted(intersection)}", file=sys.stderr, flush=True)
                    if debug_window_slots_not_in_candidates:
                        print(f"  Sample window slots not in candidates (first 3):", file=sys.stderr, flush=True)
                        for slot, slot_dt in debug_window_slots_not_in_candidates[:3]:
                            print(f"    Slot {slot} at {slot_dt.isoformat()}: in_candidates={slot in candidate_slots_set}", file=sys.stderr, flush=True)
        else:
            # Normal mode: Generate window facts for free slots that fall within the window
            # CRITICAL: For new meeting requests (where time_window is set for sliding window),
            # we need to ensure window facts are generated for all free slots in the window.
            # The issue is that after horizon reduction, free_slots use the reduced horizon's indices,
            # so we need to check if free slots fall within the window range.
            import sys
            window_facts_generated = 0
            debug_mismatches = []
            for slot in sorted(free_slots):
                if slot + duration_slots <= max_slot + 1:
                    # Check if this free slot falls within the time window
                    # Since free_slots are already in the reduced horizon's slot indices,
                    # and window_slots are also from the same slot_indexer (after horizon reduction),
                    # we can directly check membership
                    if slot in window_slots_set:
                        facts.append(f"window({request_id}, {slot}).")
                        used_slots.add(slot)
                        window_facts_generated += 1
                    else:
                        # Debug: Check what time this slot represents
                        slot_dt = slot_indexer.slot_to_datetime(slot)
                        if slot_dt:
                            debug_mismatches.append((slot, slot_dt))
            
            # Debug logging
            if window_facts_generated == 0 and len(free_slots) > 0:
                print(f"[FACT_GEN] WARNING: {len(free_slots)} free slots but 0 window facts generated", file=sys.stderr, flush=True)
                print(f"  Window range: {start_dt.isoformat()} to {end_dt.isoformat()}", file=sys.stderr, flush=True)
                print(f"  Window slots from get_slots_in_range: {len(window_slots)} slots", file=sys.stderr, flush=True)
                if len(window_slots) > 0 and len(window_slots) <= 10:
                    print(f"  Window slot indices: {sorted(window_slots)}", file=sys.stderr, flush=True)
                if len(free_slots) <= 10:
                    print(f"  Free slot indices: {sorted(free_slots)}", file=sys.stderr, flush=True)
                    # Check first free slot's time
                    first_free = sorted(free_slots)[0]
                    first_free_dt = slot_indexer.slot_to_datetime(first_free)
                    if first_free_dt:
                        print(f"  First free slot {first_free} time: {first_free_dt.isoformat()}", file=sys.stderr, flush=True)
                        print(f"  In window range? {start_dt <= first_free_dt <= end_dt}", file=sys.stderr, flush=True)
                        # Check if it's in window_slots_set
                        print(f"  In window_slots_set? {first_free in window_slots_set}", file=sys.stderr, flush=True)
                if debug_mismatches:
                    print(f"  Sample mismatches (first 3):", file=sys.stderr, flush=True)
                    for slot, slot_dt in debug_mismatches[:3]:
                        in_range = start_dt <= slot_dt <= end_dt
                        print(f"    Slot {slot} at {slot_dt.isoformat()}: in_range={in_range}, in_set={slot in window_slots_set}", file=sys.stderr, flush=True)
    else:
        # No window specified
        if allow_overlaps:
            # Multi-move: Include all candidate slots (already limited and prioritized)
            for slot in candidate_slots_limited:
                if slot + duration_slots <= max_slot + 1:
                    facts.append(f"window({request_id}, {slot}).")
                    used_slots.add(slot)
        else:
            # Normal mode: Generate window facts only for free slots
            for slot in sorted(free_slots):
                if slot + duration_slots <= max_slot + 1:
                    facts.append(f"window({request_id}, {slot}).")
                    used_slots.add(slot)
    
    # Generate metadata facts for multi-move mode (protected_event, internal_only_event, event_attendees, participant_subset_event)
    # These are needed for the enhanced soft constraints prioritization
    if allow_overlaps:
        event_slots_map = normalized_data.get("event_slots_map", {})
        event_metadata = normalized_data.get("event_metadata", {})
        event_protection = normalized_data.get("event_protection", {})
        
        # Build mapping: (participant, slot) -> event metadata
        slot_to_event: Dict[Tuple[str, int], Tuple[str, str]] = {}
        for (participant_id, event_id), slots in event_slots_map.items():
            for slot in slots:
                key = (participant_id, slot)
                if key not in slot_to_event:
                    slot_to_event[key] = (participant_id, event_id)
        
        # Request participants set for participant-subset detection
        request_participants_set = set(scheduling_problem.participants)
        request_participants_count = len(request_participants_set)
        
        # Generate metadata facts only for candidate slots (where we might place the meeting)
        candidate_slots_set = set(candidate_slots_limited) if 'candidate_slots_limited' in locals() else set()
        
        for (participant_id, slot), (p_id, event_id) in slot_to_event.items():
            # Only generate facts for candidate slots
            if slot not in candidate_slots_set:
                continue
            
            event_key = (p_id, event_id)
            protection_level = event_protection.get(event_key, "flexible")
            event_meta = event_metadata.get(event_key, {})
            
            # Protected event
            if protection_level == "protected":
                facts.append(f'protected_event("{participant_id}", {slot}).')
            
            # Internal-only flag
            internal_only = event_meta.get("internal_only", True)
            if internal_only:
                facts.append(f'internal_only_event("{participant_id}", {slot}).')
            
            # Attendee count
            num_attendees = event_meta.get("number_of_attendees", 0)
            facts.append(f'event_attendees("{participant_id}", {slot}, {num_attendees}).')
            
            # Participant-subset detection: Events where all participants are likely a subset of request participants
            # Heuristic: internal-only AND owner is in request participants AND attendee_count <= request_participants_count
            if (internal_only and 
                participant_id in request_participants_set and 
                num_attendees <= request_participants_count):
                facts.append(f'participant_subset_event("{participant_id}", {slot}).')
    
    return "\n".join(facts) + "\n"


def generate_asp_program(
    normalized_data: Dict[str, Any],
    scheduling_problem: SchedulingProblem,
    request_id: str = "q1",
    include_soft_constraints: bool = False,
    include_work_hours: bool = True,
    include_min_gap: bool = True,
    include_locked_events: bool = True,
    phase: int = 1,
    allow_multi_move: bool = False
) -> str:
    """
    Generate ASP program (facts + encoding) with configurable constraints.
    
    Args:
        normalized_data: Output from normalize_events()
        scheduling_problem: Parsed scheduling problem
        request_id: Identifier for this scheduling request
        include_soft_constraints: Whether to include soft constraints (default: False)
        include_work_hours: Whether to include work hours constraints (default: True)
        include_min_gap: Whether to include min gap constraints (default: True)
        include_locked_events: Whether to include locked event constraints (default: True)
        phase: Multi-shot phase number (1=minimal, 2=+work hours, 3=+min gap, 4=+soft)
        
    Returns:
        Complete ASP program as a string
    """
    # Handle both relative and absolute imports
    try:
        from .asp_encoding import (
            MINIMAL_ASP_PROGRAM,
            BASE_ASP_PROGRAM,
            COMPLETE_ASP_PROGRAM,
            COMPLETE_ASP_PROGRAM_MULTI_MOVE,
            BASE_ASP_PROGRAM_MULTI_MOVE,
            WORK_HOURS_CONSTRAINTS,
            MIN_GAP_CONSTRAINTS,
            LOCKED_EVENT_CONSTRAINTS,
            SOFT_CONSTRAINTS_PROGRAM
        )
    except (ImportError, ValueError):
        from asp_encoding import (
            MINIMAL_ASP_PROGRAM,
            BASE_ASP_PROGRAM,
            COMPLETE_ASP_PROGRAM,
            COMPLETE_ASP_PROGRAM_MULTI_MOVE,
            BASE_ASP_PROGRAM_MULTI_MOVE,
            WORK_HOURS_CONSTRAINTS,
            MIN_GAP_CONSTRAINTS,
            LOCKED_EVENT_CONSTRAINTS,
            SOFT_CONSTRAINTS_PROGRAM
        )
    
    facts = generate_asp_facts(normalized_data, scheduling_problem, request_id, 
                                include_work_hours=include_work_hours,
                                include_min_gap=include_min_gap,
                                include_locked_events=include_locked_events,
                                allow_overlaps=allow_multi_move)
    
    # Build program incrementally based on phase
    if allow_multi_move:
        # Multi-move mode: Use multi-move base program which has relaxed constraints
        if phase == 1:
            # Phase 1: Minimal constraints only
            program = MINIMAL_ASP_PROGRAM
        elif include_soft_constraints and phase >= 4:
            # Phase 4+: Full multi-move program with soft constraints
            program = COMPLETE_ASP_PROGRAM_MULTI_MOVE
        else:
            # Phase 2-3: Use multi-move base (has relaxed min_gap for locked events only)
            # BASE_ASP_PROGRAM_MULTI_MOVE already includes:
            # - work hours constraints
            # - locked event constraints  
            # - relaxed min_gap (only for locked events)
            program = BASE_ASP_PROGRAM_MULTI_MOVE
    else:
        # Normal mode: Build incrementally
        if phase == 1:
            # Phase 1: Minimal constraints only (no work hours, no min_gap, no locked events)
            program = MINIMAL_ASP_PROGRAM
        else:
            # Phase 2+: Start with minimal, add constraints incrementally
            program = MINIMAL_ASP_PROGRAM
            
            if include_work_hours or phase >= 2:
                program += WORK_HOURS_CONSTRAINTS
            
            if include_locked_events or phase >= 2:
                program += LOCKED_EVENT_CONSTRAINTS
            
            if include_min_gap or phase >= 3:
                program += MIN_GAP_CONSTRAINTS
            
            if include_soft_constraints and phase >= 4:
                program += SOFT_CONSTRAINTS_PROGRAM
    
    # Note: Metadata facts (protected_event, internal_only_event, event_attendees) are now
    # generated in generate_asp_facts() when allow_multi_move=True, to have access to candidate_slots.
    # For normal mode (allow_multi_move=False), we still generate them here if needed.
    if include_soft_constraints and not allow_multi_move:
        # Add protected_event, internal_only_event, and event_attendees facts for normal mode
        event_protection: Dict[Tuple[str, str], str] = normalized_data["event_protection"]
        busy_slots: Dict[str, Set[int]] = normalized_data["busy_slots"]
        event_metadata = normalized_data.get("event_metadata", {})
        event_slots_map = normalized_data.get("event_slots_map", {})
        
        # Build mapping: (participant, slot) -> event metadata
        slot_to_event: Dict[Tuple[str, int], Tuple[str, str]] = {}
        
        for (participant_id, event_id), slots in event_slots_map.items():
            for slot in slots:
                key = (participant_id, slot)
                if key not in slot_to_event:
                    slot_to_event[key] = (participant_id, event_id)
        
        # Generate facts for each busy slot with event metadata
        for (participant_id, slot), (p_id, event_id) in slot_to_event.items():
            protection_level = event_protection.get((p_id, event_id), "flexible")
            event_meta = event_metadata.get((p_id, event_id), {})
            
            if protection_level == "protected":
                facts += f'protected_event("{participant_id}", {slot}).\n'
            
            # Internal-only flag
            internal_only = event_meta.get("internal_only", True)
            if internal_only:
                facts += f'internal_only_event("{participant_id}", {slot}).\n'
            
            # Attendee count
            num_attendees = event_meta.get("number_of_attendees", 0)
            facts += f'event_attendees("{participant_id}", {slot}, {num_attendees}).\n'
        
        # Fallback: for busy slots without event metadata
        for participant_id, slots in busy_slots.items():
            for slot in slots:
                key = (participant_id, slot)
                if key not in slot_to_event:
                    facts += f'internal_only_event("{participant_id}", {slot}).\n'
                    facts += f'event_attendees("{participant_id}", {slot}, 0).\n'
        
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
            facts += f'participant("{participant_id}").\n'
        
        # Add participant facts for work hours encoding (needed for inverse encoding)
        work_hours_slots = normalized_data.get("work_hours_slots", {})
        for participant_id in scheduling_problem.participants:
            if participant_id in work_hours_slots:
                # Participant has work hours defined
                pass  # Already handled above
            else:
                # No work hours defined - will use fallback rule in ASP
                pass
        
        # Note: Program was already set above based on phase/constraints
        # Don't overwrite it here!
    
    return program + "\n% Facts:\n" + facts

