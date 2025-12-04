"""
Horizon reduction utilities for large scheduling problems.

Implements strategies to reduce the search space before ASP solving.
"""

from typing import Dict, Set, List, Tuple, Optional, Any
from datetime import datetime, timedelta
import pytz

# Handle both relative and absolute imports
try:
    from .slot_indexer import SlotIndexer, SLOT_SIZE_MINUTES
except (ImportError, ValueError):
    from slot_indexer import SlotIndexer, SLOT_SIZE_MINUTES


def reduce_horizon_to_feasible_window(
    normalized_data: Dict[str, Any],
    scheduling_problem,
    max_slots: int = 672,  # Default: 7 days * 96 slots/day
    prefer_time_window: bool = True  # If True, prioritize time window over busy slots
) -> Dict[str, Any]:
    """
    Reduce the planning horizon to a smaller window that contains feasible slots.
    
    Strategy:
    1. Find the earliest and latest busy slots across all participants
    2. Add padding (e.g., 1 day before/after)
    3. Limit to max_slots if still too large
    4. Update slot_indexer and re-normalize busy/work hours slots
    
    Args:
        normalized_data: Original normalized data with full horizon
        scheduling_problem: Scheduling problem to solve
        max_slots: Maximum number of slots to consider (default: 7 days)
        
    Returns:
        Updated normalized_data with reduced horizon
    """
    slot_indexer: SlotIndexer = normalized_data["slot_indexer"]
    busy_slots: Dict[str, Set[int]] = normalized_data["busy_slots"]
    work_hours_slots: Dict[str, Set[int]] = normalized_data["work_hours_slots"]
    
    # Strategy: Find busy slots first, then intersect with time window if specified
    current_slots = slot_indexer.get_all_slots()
    current_slot_count = len(current_slots)
    
    # If a time window is specified, filter busy slots to only those within the window
    # This is critical for sliding window approach where each window should only consider
    # busy slots within its specific time range
    window_start_slot = None
    window_end_slot = None
    if prefer_time_window and scheduling_problem.time_window_start and scheduling_problem.time_window_end:
        from datetime import datetime
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
        
        window_start_slot = slot_indexer.datetime_to_slot(start_dt)
        window_end_slot = slot_indexer.datetime_to_slot(end_dt)
    
    # Find the range of busy slots (filtered to time window if specified)
    all_busy_slots = set()
    for participant_slots in busy_slots.values():
        if window_start_slot is not None and window_end_slot is not None:
            # Only include busy slots within the time window
            for slot in participant_slots:
                if window_start_slot <= slot <= window_end_slot:
                    all_busy_slots.add(slot)
        else:
            # No time window - include all busy slots
            all_busy_slots.update(participant_slots)
    
    min_slot = None
    max_slot = None
    
    if all_busy_slots:
        # We have busy slots - use them as the base
        min_busy = min(all_busy_slots)
        max_busy = max(all_busy_slots)
        
        # Start with busy slot range plus padding - these are the most important constraints
        padding_slots = min(8, max_slots // 6)  # Adaptive padding
        min_slot = max(0, min_busy - padding_slots)
        max_slot = min(current_slot_count - 1, max_busy + padding_slots)
        
        # If we have a time window, ensure the horizon includes it
        # (Busy slots are already filtered to the window above)
        if window_start_slot is not None and window_end_slot is not None:
                # Busy slots are already filtered to the time window, so we just need to
                # ensure the horizon includes the time window with some padding
                # Start from time window start (with padding if room)
                intersection_min = max(0, window_start_slot - padding_slots)
                # End at time window end (with padding if room)
                intersection_max = min(current_slot_count - 1, window_end_slot + padding_slots)
                
                # Ensure busy slots are included (they should already be in the window)
                if all_busy_slots:
                    intersection_min = min(intersection_min, min_busy - padding_slots)
                    intersection_max = max(intersection_max, max_busy + padding_slots)
                    # But still limit to time window bounds
                    intersection_min = max(intersection_min, window_start_slot)
                    intersection_max = min(intersection_max, window_end_slot)
                
                min_slot = intersection_min
                max_slot = intersection_max
    elif prefer_time_window and window_start_slot is not None and window_end_slot is not None:
        # No busy slots, but we have a time window - use that
        from datetime import datetime
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
        
        window_start_slot = slot_indexer.datetime_to_slot(start_dt)
        window_end_slot = slot_indexer.datetime_to_slot(end_dt)
        
        if window_start_slot is not None and window_end_slot is not None:
            min_slot = window_start_slot
            max_slot = window_end_slot
            
            padding_slots = min(8, max_slots // 6)
            min_slot = max(0, min_slot - padding_slots)
            max_slot = min(current_slot_count - 1, max_slot + padding_slots)
    
    if min_slot is None or max_slot is None:
        # Fallback: no busy slots and no time window - reduce to first max_slots
        if current_slot_count > max_slots:
            min_slot = 0
            max_slot = max_slots - 1
        else:
            # Already small enough, no reduction needed
            return normalized_data
            
    # Limit to max_slots if still too large
    # CRITICAL: When truncating, preserve busy slots by truncating from the END
    
    # min_busy and max_busy need to be in scope for the limiting logic
    min_busy_local = None
    max_busy_local = None
    if all_busy_slots:
        min_busy_local = min(all_busy_slots)
        max_busy_local = max(all_busy_slots)
    
    if all_busy_slots and (max_slot - min_slot + 1) > max_slots:
        # We have busy slots - preserve them by truncating from the end
        # CRITICAL: Start from the BEGINNING of busy slots (min_busy), not the end (max_busy)
        # Truncate from the end, keeping the beginning where busy slots start
        new_max = min(current_slot_count - 1, min_slot + max_slots - 1)
        if min_busy_local is not None and max_busy_local is not None:
            if new_max >= max_busy_local:
                # Truncation doesn't cut off busy slots - OK
                max_slot = new_max
            else:
                # Truncation would cut off busy slots - start from min_busy instead
                # This ensures we capture the beginning of busy slots
                limiting_padding = _padding_slots_for_limiting if '_padding_slots_for_limiting' in locals() else min(8, max_slots // 6)
                min_slot = max(0, min_busy_local - limiting_padding)
                max_slot = min(current_slot_count - 1, min_slot + max_slots - 1)
    elif (max_slot - min_slot + 1) > max_slots:
        # No busy slots - can truncate normally
        max_slot = min(current_slot_count - 1, min_slot + max_slots - 1)
    
    # Create new slot indexer with reduced horizon
    original_start = slot_indexer.slot_to_datetime(min_slot)
    original_end = slot_indexer.slot_to_datetime(max_slot + 1)  # +1 to include the last slot
    
    if not original_start or not original_end:
        # Fallback: use original horizon
        return normalized_data
    
    # Create new slot indexer
    new_slot_indexer = SlotIndexer(original_start, original_end)
    
    # Re-normalize busy slots to new indexer (shift slot indices)
    new_busy_slots: Dict[str, Set[int]] = {}
    for participant_id, slots in busy_slots.items():
        new_slots = set()
        for slot in slots:
            if min_slot <= slot <= max_slot:
                # Shift to new indexer (slot - min_slot)
                new_slots.add(slot - min_slot)
        new_busy_slots[participant_id] = new_slots
    
    # Re-normalize work hours slots
    # CRITICAL: Work hours MUST be regenerated for the new horizon, not just filtered/shifted
    # because work hours are day-of-week based (M-F 09:00-17:00), and we need to ensure
    # only weekdays within the reduced horizon are included
    new_work_hours_slots: Dict[str, Set[int]] = {}
    
    # Regenerate work hours for the new horizon based on actual days
    # This ensures work hours are correctly calculated for the reduced horizon's date range
    try:
        from .normalizer import parse_work_hours
    except (ImportError, ValueError):
        try:
            from normalizer import parse_work_hours
        except ImportError:
            from scheduling_orchestrator.normalizer import parse_work_hours
    
    # For each participant, regenerate work hours for the new horizon
    # We'll use the same work hours string as before, but recalculate for the new date range
    # Get participants from scheduling_problem since work_hours_slots might not include all of them
    all_participants = set(scheduling_problem.participants)
    all_participants.update(work_hours_slots.keys())
    
    for participant_id in all_participants:
        # Default work hours (M-F 09:00-17:00 Eastern)
        work_hours_str = "M-F 09:00-17:00"
        work_hours_tz = "America/New_York"
        
        # Parse work hours
        work_hours = parse_work_hours(work_hours_str, work_hours_tz)
        participant_tz = pytz.timezone(work_hours_tz)
        
        # Regenerate work hours slots for the new horizon
        # Use the new horizon's start and end
        horizon_start = new_slot_indexer.horizon_start
        horizon_end = new_slot_indexer.horizon_end
        
        new_slots = set()
        
        # Start from the beginning of the day in the participant's timezone
        horizon_start_local = horizon_start.astimezone(participant_tz)
        current_date = horizon_start_local.replace(hour=0, minute=0, second=0, microsecond=0)
        current_date = participant_tz.localize(current_date.replace(tzinfo=None))
        current_date = current_date.astimezone(pytz.UTC)
        
        horizon_end_local = horizon_end.astimezone(participant_tz)
        end_date = horizon_end_local.replace(hour=23, minute=59, second=59, microsecond=999999)
        end_date = participant_tz.localize(end_date.replace(tzinfo=None))
        end_date = end_date.astimezone(pytz.UTC)
        
        while current_date <= end_date:
            current_date_local = current_date.astimezone(participant_tz)
            day_of_week = current_date_local.weekday()  # 0=Monday, 6=Sunday
            
            for day, start_hm, end_hm in work_hours:
                if day_of_week == day:
                    start_hour = start_hm // 100
                    start_min = start_hm % 100
                    end_hour = end_hm // 100
                    end_min = end_hm % 100
                    
                    work_start_local = current_date_local.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
                    work_end_local = current_date_local.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
                    
                    # Convert to UTC
                    work_start_utc = work_start_local.astimezone(pytz.UTC)
                    work_end_utc = work_end_local.astimezone(pytz.UTC)
                    
                    # Get slots in new indexer (only if they fall within the reduced horizon)
                    work_period_slots = new_slot_indexer.get_slots_in_range(work_start_utc, work_end_utc)
                    new_slots.update(work_period_slots)
            
            current_date += timedelta(days=1)
        
        new_work_hours_slots[participant_id] = new_slots
    
    # Update normalized_data
    updated_data = normalized_data.copy()
    updated_data["slot_indexer"] = new_slot_indexer
    updated_data["busy_slots"] = new_busy_slots
    updated_data["work_hours_slots"] = new_work_hours_slots
    
    # CRITICAL: Re-normalize event_slots_map and event_metadata to the new horizon
    # The event_protection mapping doesn't need to change (it's keyed by event_id, not slots)
    # but event_slots_map needs to be updated to reflect the new slot indices
    original_event_slots_map = normalized_data.get("event_slots_map", {})
    original_event_metadata = normalized_data.get("event_metadata", {})
    new_event_slots_map = {}
    new_event_metadata = {}
    
    for (participant_id, event_id), original_slots in original_event_slots_map.items():
        # Find slots that fall within the reduced horizon and re-index them
        new_slots = set()
        for slot in original_slots:
            if min_slot <= slot <= max_slot:
                new_slots.add(slot - min_slot)
        
        if new_slots:
            new_event_slots_map[(participant_id, event_id)] = new_slots
            # Copy metadata as-is (it's not slot-index dependent)
            if (participant_id, event_id) in original_event_metadata:
                new_event_metadata[(participant_id, event_id)] = original_event_metadata[(participant_id, event_id)]
    
    updated_data["event_slots_map"] = new_event_slots_map
    updated_data["event_metadata"] = new_event_metadata
    
    return updated_data


def find_feasible_slot_windows(
    normalized_data: Dict[str, Any],
    scheduling_problem,
    min_window_slots: int = 96  # Minimum 1 day window
) -> List[Tuple[int, int]]:
    """
    Find windows of consecutive feasible slots (where all participants are free).
    
    Returns list of (start_slot, end_slot) tuples for feasible windows.
    """
    slot_indexer: SlotIndexer = normalized_data["slot_indexer"]
    busy_slots: Dict[str, Set[int]] = normalized_data["busy_slots"]
    work_hours_slots: Dict[str, Set[int]] = normalized_data["work_hours_slots"]
    
    all_slots = slot_indexer.get_all_slots()
    duration_slots = max(1, scheduling_problem.duration_minutes // 15)
    
    # Find slots where all participants are free and within work hours
    feasible_slots = set()
    for slot in all_slots:
        # Check if all participants are free at this slot
        all_free = True
        for participant_id in scheduling_problem.participants:
            if participant_id in busy_slots and slot in busy_slots[participant_id]:
                all_free = False
                break
            # Check work hours
            if participant_id in work_hours_slots:
                if slot not in work_hours_slots[participant_id]:
                    all_free = False
                    break
        
        if all_free:
            # Check if meeting would fit (slot + duration <= horizon_end)
            if slot + duration_slots <= len(all_slots):
                feasible_slots.add(slot)
    
    # Group consecutive feasible slots into windows
    if not feasible_slots:
        return []
    
    sorted_slots = sorted(feasible_slots)
    windows = []
    window_start = sorted_slots[0]
    window_end = sorted_slots[0]
    
    for slot in sorted_slots[1:]:
        if slot == window_end + 1:
            window_end = slot
        else:
            if window_end - window_start + 1 >= min_window_slots:
                windows.append((window_start, window_end))
            window_start = slot
            window_end = slot
    
    # Add final window
    if window_end - window_start + 1 >= min_window_slots:
        windows.append((window_start, window_end))
    
    return windows

