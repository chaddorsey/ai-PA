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
    max_slots: int = 672  # Default: 7 days * 96 slots/day
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
    
    # Find the range of busy slots
    all_busy_slots = set()
    for participant_slots in busy_slots.values():
        all_busy_slots.update(participant_slots)
    
    if not all_busy_slots:
        # No busy slots - check if we need to reduce anyway
        current_slots = slot_indexer.get_all_slots()
        if len(current_slots) > max_slots:
            # Reduce to first max_slots (start of horizon)
            min_slot = 0
            max_slot = max_slots - 1
        else:
            # Already small enough, no reduction needed
            return normalized_data
    else:
        min_busy = min(all_busy_slots)
        max_busy = max(all_busy_slots)
        
        # Add padding: 1 day before and after (96 slots = 1 day)
        padding_slots = 96
        min_slot = max(0, min_busy - padding_slots)
        max_slot = min_busy + padding_slots
        
        # Also consider the scheduling problem's time window if specified
        if scheduling_problem.time_window_start and scheduling_problem.time_window_end:
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
            
            if window_start_slot is not None:
                min_slot = min(min_slot, window_start_slot)
            if window_end_slot is not None:
                max_slot = max(max_slot, window_end_slot)
        
        # Limit to max_slots
        if max_slot - min_slot + 1 > max_slots:
            # Center the window around busy slots
            center = (min_busy + max_busy) // 2
            min_slot = max(0, center - max_slots // 2)
            max_slot = min_slot + max_slots - 1
    
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
    new_work_hours_slots: Dict[str, Set[int]] = {}
    for participant_id, slots in work_hours_slots.items():
        new_slots = set()
        for slot in slots:
            if min_slot <= slot <= max_slot:
                new_slots.add(slot - min_slot)
        new_work_hours_slots[participant_id] = new_slots
    
    # Update normalized_data
    updated_data = normalized_data.copy()
    updated_data["slot_indexer"] = new_slot_indexer
    updated_data["busy_slots"] = new_busy_slots
    updated_data["work_hours_slots"] = new_work_hours_slots
    
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

