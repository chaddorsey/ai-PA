"""
Free-block scoring for requester calendar prioritization.

This module calculates scores for proposals based on how well they preserve
or create unbroken stretches of free/solo-event time on the requester's calendar.
"""
from typing import Dict, List, Set, Tuple, Optional, Any
from datetime import datetime, timedelta
import pytz
from .slot_indexer import SlotIndexer
from .schemas import SchedulingProblem


# Default requester email (Chad)
DEFAULT_REQUESTER_EMAIL = "cdorsey@concord.org"


def identify_requester(
    scheduling_problem: SchedulingProblem,
    context_json: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Identify the requester (primary participant) from the scheduling problem and context.
    
    Args:
        scheduling_problem: The scheduling problem
        context_json: Optional context containing participant information
        
    Returns:
        Requester email/ID, or None if not found
    """
    # Check if cdorsey@concord.org is in participants
    if DEFAULT_REQUESTER_EMAIL in scheduling_problem.participants:
        return DEFAULT_REQUESTER_EMAIL
    
    # Check context_json for requester
    if context_json and "participants" in context_json:
        participants_list = context_json["participants"]
        if participants_list:
            # First participant is typically the requester
            requester_id = participants_list[0].get("id", "")
            if requester_id:
                return requester_id
    
    # Fallback: first participant in scheduling_problem
    if scheduling_problem.participants:
        return scheduling_problem.participants[0]
    
    return None


def get_requester_open_slots(
    requester_id: str,
    normalized_data: Dict[str, Any],
    scheduling_problem: SchedulingProblem,
    slot_indexer: SlotIndexer
) -> Set[int]:
    """
    Get all "open" slots for the requester, including free slots AND solo-event slots.
    
    Solo events (zero attendees, not locked/protected) are treated as open time
    because they can be overridden or represent flexible time.
    
    Args:
        requester_id: The requester's participant ID
        normalized_data: Normalized event data
        scheduling_problem: The scheduling problem
        slot_indexer: Slot indexer for conversion
        
    Returns:
        Set of slot indices that are "open" for the requester (free or solo-event)
    """
    busy_slots: Dict[str, Set[int]] = normalized_data.get("busy_slots", {})
    work_hours_slots: Dict[str, Set[int]] = normalized_data.get("work_hours_slots", {})
    event_metadata: Dict[Tuple[str, str], Dict[str, Any]] = normalized_data.get("event_metadata", {})
    event_slots_map: Dict[Tuple[str, str], Set[int]] = normalized_data.get("event_slots_map", {})
    event_protection: Dict[Tuple[str, str], str] = normalized_data.get("event_protection", {})
    
    requester_busy = busy_slots.get(requester_id, set())
    requester_work_hours = work_hours_slots.get(requester_id, set())
    
    # Start with all work hours slots as potentially open
    open_slots = set(requester_work_hours) if requester_work_hours else set()
    
    # Identify all non-solo busy slots (these should be removed from open slots)
    # Solo events are: number_of_attendees == 0, not locked, not protected (or protected but flexible)
    non_solo_busy_slots = set()
    
    for (p_id, e_id), event_slots in event_slots_map.items():
        if p_id != requester_id:
            continue
        
        event_key = (p_id, e_id)
        event_meta = event_metadata.get(event_key, {})
        protection = event_protection.get(event_key, "flexible")
        
        num_attendees = event_meta.get("number_of_attendees", 0)
        protected = event_meta.get("protected", False)
        flexible = event_meta.get("flexible", True)
        
        # Check if this is a solo event that should be treated as open
        is_solo_open = (
            num_attendees == 0 and
            protection != "locked" and
            not (protected and not flexible)
        )
        
        if not is_solo_open:
            # This is a real busy slot - mark it for removal
            non_solo_busy_slots.update(event_slots)
    
    # Remove non-solo busy slots from open slots
    # Solo events (which are in busy_slots but are override-able) remain in open_slots
    open_slots -= non_solo_busy_slots
    
    return open_slots


def calculate_unbroken_blocks(
    open_slots: Set[int],
    slot_indexer: SlotIndexer,
    meeting_slots: Optional[Set[int]] = None
) -> List[Tuple[int, int]]:
    """
    Calculate unbroken blocks of open slots.
    
    Args:
        open_slots: Set of open slot indices
        slot_indexer: Slot indexer for conversion
        meeting_slots: Optional set of slots occupied by the meeting (to exclude)
        
    Returns:
        List of (start_slot, end_slot) tuples for unbroken blocks (end_slot is exclusive)
    """
    if meeting_slots:
        # Remove meeting slots from open slots
        open_slots = open_slots - meeting_slots
    
    if not open_slots:
        return []
    
    sorted_slots = sorted(open_slots)
    blocks = []
    
    if not sorted_slots:
        return blocks
    
    block_start = sorted_slots[0]
    block_end = sorted_slots[0] + 1  # End is exclusive
    
    for slot in sorted_slots[1:]:
        if slot == block_end:
            # Continuation of current block
            block_end = slot + 1
        else:
            # End of current block, start new one
            blocks.append((block_start, block_end))
            block_start = slot
            block_end = slot + 1
    
    # Add the last block
    blocks.append((block_start, block_end))
    
    return blocks


def apply_morning_weighting(block_start_slot: int, block_end_slot: int, slot_indexer: SlotIndexer) -> float:
    """
    Apply morning weighting to blocks that start in the 9-11 AM window.
    
    Blocks in the 9-11 AM window are weighted as 3 hours instead of 2 hours,
    because morning time is often preceded by additional work time.
    
    Args:
        block_start_slot: Start slot of the block
        block_end_slot: End slot of the block (exclusive)
        slot_indexer: Slot indexer for conversion
        
    Returns:
        Effective block length in hours (with morning weighting applied)
    """
    block_start_dt = slot_indexer.slot_to_datetime(block_start_slot)
    if not block_start_dt:
        # Fallback: calculate from slot difference
        slot_count = block_end_slot - block_start_slot
        return slot_count * 15 / 60.0  # Convert to hours
    
    # Convert to Eastern time for checking morning hours
    et_tz = pytz.timezone('America/New_York')
    if block_start_dt.tzinfo is None:
        block_start_dt = pytz.UTC.localize(block_start_dt)
    block_start_et = block_start_dt.astimezone(et_tz)
    
    block_end_dt = slot_indexer.slot_to_datetime(block_end_slot - 1)  # Last slot in block
    if block_end_dt:
        if block_end_dt.tzinfo is None:
            block_end_dt = pytz.UTC.localize(block_end_dt)
        block_end_et = block_end_dt.astimezone(et_tz)
    else:
        block_end_et = block_start_et + timedelta(minutes=(block_end_slot - block_start_slot) * 15)
    
    # Check if block starts in 9-11 AM window (in Eastern time)
    hour = block_start_et.hour
    if hour >= 9 and hour < 11:
        # This is a morning block
        # Calculate actual block length
        slot_count = block_end_slot - block_start_slot
        actual_hours = slot_count * 15 / 60.0
        
        # If block is exactly 2 hours or less and starts at 9 AM, weight as 3 hours
        # Otherwise, add 1 hour to the block length
        if actual_hours <= 2.0 and block_start_et.hour == 9 and block_start_et.minute == 0:
            return 3.0  # Effective 3-hour block
        else:
            # Add 1 hour weighting
            return actual_hours + 1.0
    
    # Not a morning block - return actual length
    slot_count = block_end_slot - block_start_slot
    return slot_count * 15 / 60.0  # Convert to hours


def calculate_free_block_score(
    proposal_start_utc: str,
    scheduling_problem: SchedulingProblem,
    normalized_data: Dict[str, Any],
    slot_indexer: SlotIndexer,
    requester_id: Optional[str] = None,
    moved_events: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Calculate free-block score for a proposal.
    
    This score measures how well the proposal preserves or creates unbroken
    stretches of free/solo-event time on the requester's calendar.
    
    Args:
        proposal_start_utc: Proposed meeting start time (ISO 8601 UTC)
        scheduling_problem: The scheduling problem
        normalized_data: Normalized event data
        slot_indexer: Slot indexer for conversion
        requester_id: Optional requester ID (will be identified if not provided)
        
    Returns:
        Dictionary with free-block score and statistics:
        - free_block_score: Overall score (higher is better)
        - total_effective_hours: Total effective free hours across all days
        - avg_block_hours: Average unbroken block length in hours
        - max_block_hours: Maximum unbroken block length in hours
        - median_block_hours: Median unbroken block length in hours
        - blocks_per_day: List of block statistics per day
    """
    # Identify requester if not provided
    if not requester_id:
        requester_id = identify_requester(scheduling_problem)
    
    if not requester_id:
        # Cannot calculate score without requester
        return {
            "free_block_score": 0.0,
            "total_effective_hours": 0.0,
            "avg_block_hours": 0.0,
            "max_block_hours": 0.0,
            "median_block_hours": 0.0,
            "blocks_per_day": []
        }
    
    # Parse meeting start time and calculate meeting slots
    try:
        start_dt = datetime.fromisoformat(proposal_start_utc.replace('Z', '+00:00'))
        if start_dt.tzinfo is None:
            start_dt = pytz.UTC.localize(start_dt)
    except (ValueError, AttributeError):
        return {
            "free_block_score": 0.0,
            "total_effective_hours": 0.0,
            "avg_block_hours": 0.0,
            "max_block_hours": 0.0,
            "median_block_hours": 0.0,
            "blocks_per_day": []
        }
    
    meeting_start_slot = slot_indexer.datetime_to_slot(start_dt)
    if meeting_start_slot is None:
        return {
            "free_block_score": 0.0,
            "total_effective_hours": 0.0,
            "avg_block_hours": 0.0,
            "max_block_hours": 0.0,
            "median_block_hours": 0.0,
            "blocks_per_day": []
        }
    
    duration_slots = max(1, scheduling_problem.duration_minutes // 15)
    meeting_slots = set(range(meeting_start_slot, meeting_start_slot + duration_slots))
    meeting_end_slot = meeting_start_slot + duration_slots
    
    # Get requester's open slots (free + solo events)
    open_slots = get_requester_open_slots(requester_id, normalized_data, scheduling_problem, slot_indexer)
    
    # Track gap created between meeting and moved events (for bonus scoring)
    meeting_move_gap_slots = 0  # Gap between meeting end and first moved event start (0 = back-to-back)
    meeting_move_gap_after_slots = 0  # Gap after moved event ends (for consolidation analysis)
    meeting_move_gap_before_slots = 0  # Gap before meeting starts (for consolidation analysis when event is moved earlier)
    # Get max/min slot from slot_indexer for lookahead/backward analysis
    try:
        all_slots_list = slot_indexer.get_all_slots()
        max_slot = len(all_slots_list) - 1 if all_slots_list else None
        min_slot = 0
    except:
        max_slot = max(open_slots) if open_slots else None
        min_slot = min(open_slots) if open_slots else None
    
    # Adjust open slots based on moved events
    # When an event is moved, we need to:
    # 1. Remove the old event location from busy slots (it becomes open, but meeting might be there)
    # 2. Add the old event location slots to open slots (unless they're occupied by the meeting)
    # 3. Remove the new event location from open slots (if it's not a solo event)
    # 4. Calculate gap between meeting end and moved event start
    if moved_events:
        event_slots_map: Dict[Tuple[str, str], Set[int]] = normalized_data.get("event_slots_map", {})
        event_metadata: Dict[Tuple[str, str], Dict[str, Any]] = normalized_data.get("event_metadata", {})
        event_protection: Dict[Tuple[str, str], str] = normalized_data.get("event_protection", {})
        
        for moved_event in moved_events:
            owner = moved_event.get('owner', '')
            event_id = moved_event.get('event_id', '')
            old_start = moved_event.get('old_start', '')
            new_start = moved_event.get('new_start', '')
            old_end = moved_event.get('old_end', '')
            
            if owner != requester_id:
                continue  # Only adjust for requester's events
            
            # Parse old and new times
            try:
                old_start_dt = datetime.fromisoformat(old_start.replace('Z', '+00:00'))
                old_end_dt = datetime.fromisoformat(old_end.replace('Z', '+00:00'))
                new_start_dt = datetime.fromisoformat(new_start.replace('Z', '+00:00'))
                
                if old_start_dt.tzinfo is None:
                    old_start_dt = pytz.UTC.localize(old_start_dt)
                if old_end_dt.tzinfo is None:
                    old_end_dt = pytz.UTC.localize(old_end_dt)
                if new_start_dt.tzinfo is None:
                    new_start_dt = pytz.UTC.localize(new_start_dt)
                
                # Get old event slots from the event_slots_map
                event_key = (owner, event_id)
                old_event_slots = event_slots_map.get(event_key, set())
                
                # Calculate new event slots
                new_start_slot = slot_indexer.datetime_to_slot(new_start_dt)
                if new_start_slot is not None:
                    # Calculate duration in slots
                    duration_minutes = (old_end_dt - old_start_dt).total_seconds() / 60
                    duration_slots = max(1, int(duration_minutes / 15))
                    new_event_slots = set(range(new_start_slot, new_start_slot + duration_slots))
                    
                    # Check if moved event is a solo event
                    event_meta = event_metadata.get(event_key, {})
                    num_attendees = event_meta.get('number_of_attendees', 0)
                    protection = event_protection.get(event_key, "flexible")
                    protected = event_meta.get('protected', False)
                    flexible = event_meta.get('flexible', True)
                    
                    is_solo_open = (
                        num_attendees == 0 and
                        protection != "locked" and
                        not (protected and not flexible)
                    )
                    
                    # Add old event slots to open slots (event is no longer there, so those slots become open)
                    # But exclude slots occupied by the meeting itself
                    work_hours_slots: Dict[str, Set[int]] = normalized_data.get("work_hours_slots", {})
                    requester_work_hours = work_hours_slots.get(requester_id, set())
                    old_event_slots_in_work_hours = old_event_slots.intersection(requester_work_hours)
                    # Add the old location slots, but exclude meeting slots (meeting_slots will be removed later, 
                    # but we need to be careful not to double-count slots that overlap with the meeting)
                    old_slots_to_add = old_event_slots_in_work_hours - meeting_slots
                    open_slots.update(old_slots_to_add)
                    
                    # Calculate gap between meeting end and moved event start
                    # Also check if the moved event creates a gap BEFORE the meeting
                    if new_start_slot is not None:
                        # Check gap between meeting end and moved event start (if event is after meeting)
                        if meeting_end_slot is not None:
                            gap_before_event_slots = new_start_slot - meeting_end_slot
                            # Track the gap before (including 0 for back-to-back)
                            if meeting_move_gap_slots == 0 or gap_before_event_slots < meeting_move_gap_slots:
                                meeting_move_gap_slots = gap_before_event_slots
                        
                        # Check if the moved event is now BEFORE the meeting (moved earlier)
                        # This can create a consolidated free block before the meeting
                        if meeting_start_slot is not None and new_start_slot < meeting_start_slot:
                            # Event is now before the meeting - check gap before meeting
                            moved_event_end_slot = new_start_slot + duration_slots
                            if moved_event_end_slot <= meeting_start_slot:
                                # There's a gap between the moved event end and meeting start
                                gap_before_meeting_slots = meeting_start_slot - moved_event_end_slot
                                if gap_before_meeting_slots > meeting_move_gap_before_slots:
                                    meeting_move_gap_before_slots = gap_before_meeting_slots
                    
                    # Remove new event slots from open slots (event now occupies these slots)
                    # Solo events don't block open slots (they're treated as open)
                    if not is_solo_open and new_event_slots:
                        open_slots -= new_event_slots
                    
            except (ValueError, AttributeError, TypeError):
                # Skip if we can't parse the times
                pass
    
    # Now check the final state after all moves to see gaps after moved events
    # This is done AFTER open_slots has been adjusted, so we see the final calendar state
    # We check ALL moved events to find the pattern of gaps (not just when gap_after_slots == 0)
    if moved_events:
        # Re-check if we didn't find gaps earlier (may need to check after open_slots adjustment)
        for moved_event in moved_events:
            owner = moved_event.get('owner', '')
            if owner != requester_id:
                continue
            new_start = moved_event.get('new_start', '')
            old_end = moved_event.get('old_end', '')
            try:
                new_start_dt = datetime.fromisoformat(new_start.replace('Z', '+00:00'))
                if new_start_dt.tzinfo is None:
                    new_start_dt = pytz.UTC.localize(new_start_dt)
                new_start_slot = slot_indexer.datetime_to_slot(new_start_dt)
                if new_start_slot is not None:
                    # Get event duration
                    old_end_dt = datetime.fromisoformat(old_end.replace('Z', '+00:00'))
                    if old_end_dt.tzinfo is None:
                        old_end_dt = pytz.UTC.localize(old_end_dt)
                    duration_minutes = (old_end_dt - new_start_dt).total_seconds() / 60
                    duration_slots = max(1, int(duration_minutes / 15))
                    moved_event_end_slot = new_start_slot + duration_slots
                    
                    # Check free slots after the moved event
                    if max_slot:
                        lookahead_slots = min(8, max_slot - moved_event_end_slot + 1)
                        if lookahead_slots > 0:
                            gap_after = 0
                            for check_slot in range(moved_event_end_slot, moved_event_end_slot + lookahead_slots):
                                if check_slot in open_slots and check_slot not in meeting_slots:
                                    gap_after += 1
                                else:
                                    break
                            if gap_after > meeting_move_gap_after_slots:
                                meeting_move_gap_after_slots = gap_after
            except (ValueError, AttributeError, TypeError):
                pass
    
    # Also check for gaps before the meeting (when events are moved earlier)
    # Look back from meeting start to see if there's a consolidated free block
    if meeting_start_slot is not None and min_slot is not None:
        lookback_slots = min(8, meeting_start_slot - min_slot)  # Look back up to 2 hours
        if lookback_slots > 0:
            gap_before_meeting = 0
            for check_slot in range(meeting_start_slot - 1, meeting_start_slot - lookback_slots - 1, -1):
                if check_slot in open_slots and check_slot not in meeting_slots:
                    gap_before_meeting += 1
                else:
                    break  # Block ends when we hit a busy slot
            # If we found a gap before the meeting and it's larger than what we tracked from moved events,
            # update it (this handles cases where multiple events contribute to the gap)
            if gap_before_meeting > meeting_move_gap_before_slots:
                meeting_move_gap_before_slots = gap_before_meeting
    
    # Calculate unbroken blocks after placing the meeting
    blocks = calculate_unbroken_blocks(open_slots, slot_indexer, meeting_slots)
    
    # Calculate statistics with morning weighting and group blocks by day
    blocks_by_day: Dict[str, List[Tuple[int, int, float]]] = {}  # day_key -> [(block_start, block_end, effective_hours)]
    effective_block_hours = []
    
    for block_start, block_end in blocks:
        effective_hours = apply_morning_weighting(block_start, block_end, slot_indexer)
        effective_block_hours.append(effective_hours)
        
        # Group by day for day-based scoring
        block_start_dt = slot_indexer.slot_to_datetime(block_start)
        if block_start_dt:
            if block_start_dt.tzinfo is None:
                block_start_dt = pytz.UTC.localize(block_start_dt)
            et_tz = pytz.timezone('America/New_York')
            block_start_et = block_start_dt.astimezone(et_tz)
            day_key = block_start_et.date().isoformat()
            
            if day_key not in blocks_by_day:
                blocks_by_day[day_key] = []
            blocks_by_day[day_key].append((block_start, block_end, effective_hours))
    
    if not effective_block_hours:
        return {
            "free_block_score": 0.0,
            "total_effective_hours": 0.0,
            "avg_block_hours": 0.0,
            "max_block_hours": 0.0,
            "median_block_hours": 0.0,
            "blocks_per_day": []
        }
    
    total_effective_hours = sum(effective_block_hours)
    avg_block_hours = total_effective_hours / len(effective_block_hours) if effective_block_hours else 0.0
    max_block_hours = max(effective_block_hours) if effective_block_hours else 0.0
    
    # Calculate median
    sorted_hours = sorted(effective_block_hours)
    n = len(sorted_hours)
    if n == 0:
        median_block_hours = 0.0
    elif n % 2 == 0:
        median_block_hours = (sorted_hours[n//2 - 1] + sorted_hours[n//2]) / 2.0
    else:
        median_block_hours = sorted_hours[n//2]
    
    # Penalize 15-minute blocks (0.25 hours) and reward longer blocks
    # Blocks > 15 minutes get a significant bonus to prefer them over 15-minute blocks
    MIN_BLOCK_BONUS_THRESHOLD = 0.25  # 15 minutes
    block_bonus = 0.0
    blocks_above_threshold = 0
    blocks_exactly_threshold = 0
    for hours in effective_block_hours:
        if hours > MIN_BLOCK_BONUS_THRESHOLD:
            blocks_above_threshold += 1
            # Significant bonus for blocks > 15 minutes - increases quadratically with length
            excess = hours - MIN_BLOCK_BONUS_THRESHOLD
            block_bonus += excess * excess * 100.0  # Quadratic bonus
        elif abs(hours - MIN_BLOCK_BONUS_THRESHOLD) < 0.01:  # Approximately 15 minutes (0.25 hours)
            blocks_exactly_threshold += 1
    
    # Penalty for 15-minute blocks (encourage consolidation)
    fifteen_minute_penalty = blocks_exactly_threshold * 10.0
    
    # For periods <= 2 hours total, prefer longer blocks within a single day
    # over cross-day distribution
    single_day_concentration_bonus = 0.0
    if total_effective_hours <= 2.0 and blocks_by_day:
        # Find the day with the longest block
        max_single_day_block = 0.0
        total_single_day_hours = 0.0
        best_day_blocks = []
        for day_key, day_blocks in blocks_by_day.items():
            day_block_lengths = [hours for _, _, hours in day_blocks]
            if day_block_lengths:
                day_total = sum(day_block_lengths)
                max_day_block = max(day_block_lengths)
                if day_total > total_single_day_hours:
                    total_single_day_hours = day_total
                    max_single_day_block = max_day_block
                    best_day_blocks = day_block_lengths
        
        # Bonus for concentrating blocks in fewer days (especially if one day has a long block)
        if len(blocks_by_day) == 1:
            # All blocks in one day - significant bonus based on longest block in that day
            single_day_concentration_bonus = max_single_day_block * 50.0
            # Additional bonus if the longest block is > 15 minutes
            if max_single_day_block > MIN_BLOCK_BONUS_THRESHOLD:
                single_day_concentration_bonus += (max_single_day_block - MIN_BLOCK_BONUS_THRESHOLD) * 30.0
        elif len(blocks_by_day) == 2:
            # Two days - bonus if one day has a significant block (> 15 min)
            if max_single_day_block > MIN_BLOCK_BONUS_THRESHOLD:
                single_day_concentration_bonus = max_single_day_block * 25.0
    
    # Bonus/penalty for gap pattern created by moves
    # Prefer moves that create ONE larger free block rather than TWO smaller blocks
    # Consider gaps:
    # 1. Before meeting starts (meeting_move_gap_before_slots) - when event moved earlier
    # 2. Between meeting end and moved event start (meeting_move_gap_slots)
    # 3. After moved event ends (meeting_move_gap_after_slots)
    #
    # Examples:
    # - 45-min move (back-to-back) creates one 30-min block after moved event → preferred
    # - 60-min move creates two 15-min blocks (before and after moved event) → penalized
    # - Event moved earlier, meeting at 12:30, creates one 30-min block before → preferred
    meeting_move_gap_bonus = 0.0
    gap_before_meeting_hours = (meeting_move_gap_before_slots * 15) / 60.0  # Gap before meeting
    gap_before_event_hours = (meeting_move_gap_slots * 15) / 60.0  # Gap between meeting end and moved event start
    gap_after_event_hours = (meeting_move_gap_after_slots * 15) / 60.0  # Gap after moved event ends
    
    # Pattern 1: Gap before meeting (event moved earlier, meeting scheduled later)
    # This creates one consolidated block before the meeting - PREFERRED
    if gap_before_meeting_hours > 0:
        if gap_before_meeting_hours >= 0.5:  # >= 30 minutes - substantial block
            meeting_move_gap_bonus += gap_before_meeting_hours * 150.0  # Strong bonus
        else:
            meeting_move_gap_bonus += gap_before_meeting_hours * 75.0  # Smaller bonus
    
    # Pattern 2: Back-to-back move (no gap between meeting and moved event) with gap after
    # This creates one consolidated block after - PREFERRED
    if gap_before_event_hours == 0 and gap_after_event_hours > 0:
        if gap_after_event_hours >= 0.5:  # >= 30 minutes - substantial block
            meeting_move_gap_bonus += gap_after_event_hours * 150.0  # Strong bonus
        else:
            meeting_move_gap_bonus += gap_after_event_hours * 75.0  # Smaller bonus
    
    # Pattern 3: Gap between meeting and moved event, with gap after
    # This fragments free time into two separate blocks - PENALIZE
    elif gap_before_event_hours > 0 and gap_after_event_hours > 0:
        if gap_before_event_hours <= 0.25 and gap_after_event_hours <= 0.25:
            # Two small gaps (e.g., 15 min + 15 min) - strongly penalize
            meeting_move_gap_bonus -= 150.0  # Strong penalty for fragmenting
        elif gap_before_event_hours >= 0.5 or gap_after_event_hours >= 0.5:
            # One of the gaps is substantial - less penalty
            meeting_move_gap_bonus -= 30.0
        else:
            # Mixed: small + medium gap - moderate penalty
            meeting_move_gap_bonus -= 75.0
    
    # Pattern 4: Only gap between meeting and moved event (no gap before meeting, no gap after)
    elif gap_before_event_hours >= 0.5:
        # One substantial gap (>= 30 min) between meeting and moved event - this is acceptable
        excess_gap = gap_before_event_hours - 0.25  # Excess over 15 minutes
        meeting_move_gap_bonus += excess_gap * excess_gap * 100.0  # Moderate bonus
    elif gap_before_event_hours == 0.25:
        # Small gap (15 min) between meeting and moved event with no other gaps
        # Still fragments, but less than two gaps
        meeting_move_gap_bonus -= 40.0
    
    # Pattern 5: Only gap after moved event (no gap before meeting, back-to-back)
    elif gap_after_event_hours >= 0.5:
        # One substantial gap after - this is good
        meeting_move_gap_bonus += gap_after_event_hours * 100.0
    elif gap_after_event_hours > 0:
        # Small gap after - small bonus
        meeting_move_gap_bonus += gap_after_event_hours * 50.0
    
    # For no gaps: no bonus/penalty (no free blocks created by the move pattern)
    
    # Calculate free-block score
    # Prioritize: max block length > median block length > blocks > 15min > single-day concentration > meeting-move gaps
    # Scale appropriately to create a composite score
    # Changed: max_block_hours now has higher weight to prefer longer individual blocks
    free_block_score = (
        max_block_hours * 150.0 +     # Max block is MOST important (prefer longer blocks)
        median_block_hours * 100.0 +  # Median is second priority
        avg_block_hours * 10.0 +      # Average is third priority
        block_bonus +                 # Significant bonus for blocks > 15 minutes
        single_day_concentration_bonus +  # Bonus for concentrating in single day (<= 2h total)
        meeting_move_gap_bonus -      # Bonus for gaps created by moves (encourages longer gaps)
        fifteen_minute_penalty        # Penalty for 15-minute blocks
    )
    
    return {
        "free_block_score": free_block_score,
        "total_effective_hours": total_effective_hours,
        "avg_block_hours": avg_block_hours,
        "max_block_hours": max_block_hours,
        "median_block_hours": median_block_hours,
        "blocks_per_day": [],  # TODO: Group blocks by day if needed
        "all_block_hours": effective_block_hours  # For debugging
    }

