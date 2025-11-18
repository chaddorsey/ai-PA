"""
Event payload normalizer.

Transforms events_by_participant into discrete 15-minute slot facts for ASP encoding.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple, Optional, Any
import pytz

# Handle both relative and absolute imports
try:
    from .slot_indexer import SlotIndexer, SLOT_SIZE_MINUTES
    from .schemas import Event
except (ImportError, ValueError):
    from slot_indexer import SlotIndexer, SLOT_SIZE_MINUTES
    from schemas import Event


def parse_work_hours(work_hours_str: str, timezone_str: str) -> List[Tuple[int, int]]:
    """
    Parse work hours string (e.g., "M-F 09:00-17:30") into slot ranges.
    
    Args:
        work_hours_str: Work hours specification (e.g., "M-F 09:00-17:30")
        timezone_str: Timezone string (e.g., "America/New_York")
        
    Returns:
        List of (day_of_week, hour_minute_start, hour_minute_end) tuples
        day_of_week: 0=Monday, 6=Sunday
        hour_minute: HHMM format (e.g., 900 for 09:00)
    """
    # Simple parser for "M-F 09:00-17:30" format
    # TODO: Make more robust to handle various formats
    work_hours = []
    
    try:
        # Parse day range and time range
        parts = work_hours_str.split()
        if len(parts) < 2:
            return []
        
        day_range = parts[0]  # e.g., "M-F"
        time_range = parts[1]  # e.g., "09:00-17:30"
        
        # Parse day range
        if day_range == "M-F":
            days = [0, 1, 2, 3, 4]  # Monday to Friday
        elif day_range == "M-S":
            days = [0, 1, 2, 3, 4, 5, 6]  # Monday to Sunday
        else:
            # Default to weekdays
            days = [0, 1, 2, 3, 4]
        
        # Parse time range
        start_str, end_str = time_range.split("-")
        start_hour, start_min = map(int, start_str.split(":"))
        end_hour, end_min = map(int, end_str.split(":"))
        
        start_hm = start_hour * 100 + start_min
        end_hm = end_hour * 100 + end_min
        
        for day in days:
            work_hours.append((day, start_hm, end_hm))
    
    except Exception:
        # If parsing fails, default to weekdays 9-17
        for day in [0, 1, 2, 3, 4]:
            work_hours.append((day, 900, 1700))
    
    return work_hours


def normalize_events(
    events_by_participant: Dict[str, List[Dict[str, Any]]],
    context_json: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Transform events_by_participant into normalized slot facts.
    
    Args:
        events_by_participant: Dictionary mapping participant IDs to event lists
        context_json: Optional context with timeframe, participants, policy
        
    Returns:
        Dictionary with:
        - slot_indexer: SlotIndexer instance
        - busy_slots: Dict[participant_id, Set[slot_index]]
        - work_hours_slots: Dict[participant_id, Set[slot_index]]
        - event_protection: Dict[(participant_id, event_id), protection_level]
        - min_gap_slots: int (minimum gap in slots)
    """
    # Extract timeframe from context
    if context_json and "timeframe" in context_json:
        timeframe = context_json["timeframe"]
        tz_str = timeframe.get("tz", "UTC")
        timezone = pytz.timezone(tz_str)
        
        # Parse start/end dates
        from_date = datetime.fromisoformat(timeframe["from"])
        to_date = datetime.fromisoformat(timeframe["to"])
        
        # Convert to UTC
        if from_date.tzinfo is None:
            from_date = timezone.localize(from_date)
        from_date_utc = from_date.astimezone(pytz.UTC)
        
        if to_date.tzinfo is None:
            to_date = timezone.localize(to_date)
        to_date_utc = to_date.astimezone(pytz.UTC)
        
        # Add one day to to_date to include the full day
        to_date_utc = to_date_utc + timedelta(days=1)
    else:
        # Default: next 2 weeks from now
        now = datetime.now(pytz.UTC)
        from_date_utc = now.replace(hour=0, minute=0, second=0, microsecond=0)
        to_date_utc = from_date_utc + timedelta(days=14)
        timezone = pytz.UTC
    
    # Create slot indexer
    slot_indexer = SlotIndexer(from_date_utc, to_date_utc)
    
    # Extract policy
    min_gap_minutes = 15
    if context_json and "policy" in context_json:
        policy = context_json["policy"]
        if "hard" in policy and "min_gap_min" in policy["hard"]:
            min_gap_minutes = policy["hard"]["min_gap_min"]
    
    min_gap_slots = max(1, min_gap_minutes // SLOT_SIZE_MINUTES)
    
    # Process events
    busy_slots: Dict[str, Set[int]] = {}
    event_protection: Dict[Tuple[str, str], str] = {}
    
    for participant_id, events in events_by_participant.items():
        busy_slots[participant_id] = set()
        
        for event_dict in events:
            # Parse event
            event_id = event_dict.get("id", "")
            start_str = event_dict.get("start", "")
            end_str = event_dict.get("end", "")
            locked = event_dict.get("locked", False)
            protected = event_dict.get("protected", False)
            flexible = event_dict.get("flexible", True)
            
            # Parse datetimes
            try:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                
                # Ensure UTC
                if start_dt.tzinfo is None:
                    start_dt = pytz.UTC.localize(start_dt)
                else:
                    start_dt = start_dt.astimezone(pytz.UTC)
                
                if end_dt.tzinfo is None:
                    end_dt = pytz.UTC.localize(end_dt)
                else:
                    end_dt = end_dt.astimezone(pytz.UTC)
                
                # Get slots for this event
                event_slots = slot_indexer.get_slots_in_range(start_dt, end_dt)
                busy_slots[participant_id].update(event_slots)
                
                # Determine protection level
                if locked:
                    protection_level = "locked"
                elif protected:
                    protection_level = "protected"
                elif flexible:
                    protection_level = "flexible"
                else:
                    protection_level = "flexible"  # default
                
                event_protection[(participant_id, event_id)] = protection_level
                
            except Exception as e:
                # Skip invalid events
                continue
    
    # Process work hours
    work_hours_slots: Dict[str, Set[int]] = {}
    
    if context_json and "participants" in context_json:
        for participant in context_json["participants"]:
            participant_id = participant.get("id", "")
            work_hours_str = participant.get("work_hours", "")
            tz_str = participant.get("timezone", context_json.get("timeframe", {}).get("tz", "UTC"))
            
            if not work_hours_str:
                # Default to all slots if no work hours specified
                work_hours_slots[participant_id] = set(slot_indexer.get_all_slots())
                continue
            
            # Parse work hours
            work_hours = parse_work_hours(work_hours_str, tz_str)
            participant_tz = pytz.timezone(tz_str)
            
            # Convert work hours to UTC slots
            work_slots = set()
            for day, start_hm, end_hm in work_hours:
                # Find dates in horizon that match this day of week
                current_date = from_date_utc
                while current_date < to_date_utc:
                    if current_date.weekday() == day:
                        # Create datetime for start/end of work hours
                        start_hour = start_hm // 100
                        start_min = start_hm % 100
                        end_hour = end_hm // 100
                        end_min = end_hm % 100
                        
                        work_start = current_date.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
                        work_end = current_date.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
                        
                        # Convert to UTC
                        work_start_local = participant_tz.localize(work_start.replace(tzinfo=None))
                        work_end_local = participant_tz.localize(work_end.replace(tzinfo=None))
                        work_start_utc = work_start_local.astimezone(pytz.UTC)
                        work_end_utc = work_end_local.astimezone(pytz.UTC)
                        
                        # Get slots for this work period
                        work_period_slots = slot_indexer.get_slots_in_range(work_start_utc, work_end_utc)
                        work_slots.update(work_period_slots)
                    
                    current_date += timedelta(days=1)
            
            work_hours_slots[participant_id] = work_slots
    
    return {
        "slot_indexer": slot_indexer,
        "busy_slots": busy_slots,
        "work_hours_slots": work_hours_slots,
        "event_protection": event_protection,
        "min_gap_slots": min_gap_slots,
        "timezone": timezone,
    }

