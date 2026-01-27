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
    # Default to 0 minutes gap unless specifically set
    min_gap_minutes = 0
    if context_json and "policy" in context_json:
        policy = context_json["policy"]
        if "hard" in policy and "min_gap_min" in policy["hard"]:
            min_gap_minutes = policy["hard"]["min_gap_min"]
    
    # Calculate min_gap_slots - allow 0 if min_gap_minutes is 0
    min_gap_slots = min_gap_minutes // SLOT_SIZE_MINUTES
    
    # Process events
    busy_slots: Dict[str, Set[int]] = {}
    event_protection: Dict[Tuple[str, str], str] = {}
    event_slots_map: Dict[Tuple[str, str], Set[int]] = {}  # Maps (participant_id, event_id) to slot set
    event_metadata: Dict[Tuple[str, str], Dict[str, Any]] = {}  # Maps (participant_id, event_id) to event metadata
    event_participants: Dict[Tuple[str, str], List[str]] = {}  # Maps (participant_id, event_id) to list of all participant emails
    
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
            
            # Special handling: VACATION/OUT OF OFFICE events should block scheduling (locked)
            # Check summary/title for vacation indicators
            event_summary = (event_dict.get("summary") or event_dict.get("title", "")).upper()
            if "VACATION" in event_summary or "OUT OF OFFICE" in event_summary or "OOO" in event_summary:
                locked = True
                protected = True
                flexible = False

            # Check description for protection indicators (fallback if protected not set via metadata)
            # This handles cases where users mark events as protected via description text
            if not protected:
                event_description = (event_dict.get("description") or "").upper()
                # Check for common protection keywords in description
                protection_keywords = ["PROTECTED", "DO NOT SCHEDULE", "DO NOT MOVE", "BLOCKED TIME", "BLOCKING TIME"]
                if any(kw in event_description for kw in protection_keywords):
                    protected = True
                    flexible = False  # Protected events should not be flexible
            
            # Parse datetimes
            try:
                # Handle both ISO format strings and ensure proper parsing
                # Replace "Z" with "+00:00" for ISO format compatibility
                start_str_clean = start_str.replace("Z", "+00:00") if start_str else ""
                end_str_clean = end_str.replace("Z", "+00:00") if end_str else ""
                
                if not start_str_clean or not end_str_clean:
                    continue
                
                start_dt = datetime.fromisoformat(start_str_clean)
                end_dt = datetime.fromisoformat(end_str_clean)
                
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

                # Check transparent: True means "show as free" - don't block scheduling
                # False (default) means "show as busy" - blocks scheduling
                transparency = event_dict.get("transparent", False)

                # Handle multiple formats:
                # - Google API: "transparent" / "opaque"
                # - n8n boolean: true / false
                # - n8n string: "true" / "false"
                if isinstance(transparency, str):
                    is_transparent = transparency.lower() in ("transparent", "true", "1", "yes")
                else:
                    is_transparent = bool(transparency)  # True = free, False = busy

                # Only add to busy_slots if event is NOT transparent (i.e., actually busy)
                if not is_transparent:
                    busy_slots[participant_id].update(event_slots)
                
                # Store event-to-slots mapping for move logic
                event_key = (participant_id, event_id)
                event_slots_map[event_key] = set(event_slots)
                
                # Extract attendees list
                attendees = event_dict.get("attendees", [])
                if not isinstance(attendees, list):
                    attendees = []
                
                # Check if event has external participants
                # If any participant (owner or attendee) is external, mark event as not internal_only
                # This prevents external meetings from being moved
                internal_only_from_dict = event_dict.get("internal_only", True)  # Default to True for backwards compatibility
                
                # Helper function to check if a participant is internal
                def _is_internal_participant(participant_id: str, internal_domains: Optional[List[str]] = None) -> bool:
                    """Check if participant is internal (e.g., @concord.org) or external."""
                    if not participant_id or "@" not in participant_id:
                        return True  # Default to internal if no email domain
                    
                    if internal_domains is None:
                        # Default internal domains
                        internal_domains = ["concord.org"]
                    
                    participant_domain = participant_id.split("@")[-1].lower()
                    return participant_domain in [d.lower() for d in internal_domains]
                
                # Check all participants (owner + attendees) for external participants
                all_event_participants = [participant_id] + attendees
                has_external_participants = False
                for p in all_event_participants:
                    if not _is_internal_participant(p):
                        has_external_participants = True
                        break
                
                # If event has external participants, it cannot be moved (mark as not internal_only)
                # Override the internal_only flag from the event dict if external participants are detected
                final_internal_only = internal_only_from_dict and not has_external_participants
                
                # Store event metadata for move logic
                # Preserve both 'summary' (raw MCP) and 'title' (normalized) fields
                event_title = event_dict.get("title") or event_dict.get("summary", "")
                event_summary = event_dict.get("summary", "") or event_dict.get("title", "")
                event_metadata[event_key] = {
                    "start_dt": start_dt,
                    "end_dt": end_dt,
                    "start_str": start_str_clean,
                    "end_str": end_str_clean,
                    "title": event_title,
                    "summary": event_summary,  # Preserve summary field for event extraction
                    "locked": locked,
                    "protected": protected,
                    "flexible": flexible,
                    "transparent": is_transparent,  # True = free/transparent, False = busy/opaque
                    "internal_only": final_internal_only,  # Mark as False if external participants detected
                    "number_of_attendees": len(attendees),  # Use actual count from attendees list
                    "attendees": attendees  # Store full attendees list for validation
                }
                
                # Store all participants of this event (owner + attendees)
                # The owner (participant_id) is always a participant, plus any additional attendees
                event_participants[event_key] = [participant_id] + attendees
                
                # Determine protection level
                # CRITICAL: If an event is protected AND not flexible, it should not be moved
                # Therefore, treat it as "locked" to prevent overlaps
                if locked or (protected and not flexible):
                    protection_level = "locked"
                elif protected:
                    protection_level = "protected"
                elif flexible:
                    protection_level = "flexible"
                else:
                    protection_level = "flexible"  # default
                
                event_protection[event_key] = protection_level
                
            except Exception as e:
                # Skip invalid events
                continue
    
    # Process work hours
    work_hours_slots: Dict[str, Set[int]] = {}
    
    if context_json and "participants" in context_json:
        for participant in context_json["participants"]:
            participant_id = participant.get("id", "")
            work_hours_str = participant.get("work_hours", "")
            # Default timezone is Eastern time for default work hours
            # If participant has explicit timezone, use that; otherwise use timeframe timezone or Eastern
            participant_timezone = participant.get("timezone")
            if not participant_timezone:
                participant_timezone = context_json.get("timeframe", {}).get("tz", "America/New_York")
            
            if not work_hours_str:
                # Default to standard business hours (9 AM - 5 PM weekdays) in Eastern time
                # This prevents scheduling meetings at midnight or other inappropriate times
                work_hours_str = "M-F 09:00-17:00"
                # Use Eastern timezone for default work hours
                tz_str = "America/New_York"
                # Continue to parse and apply the default
            else:
                # Use participant's timezone for their specified work hours
                tz_str = participant_timezone
            
            # Parse work hours
            work_hours = parse_work_hours(work_hours_str, tz_str)
            participant_tz = pytz.timezone(tz_str)
            
            # Convert work hours to UTC slots
            work_slots = set()
            for day, start_hm, end_hm in work_hours:
                # Find dates in horizon that match this day of week
                # CRITICAL: Check weekday in participant's timezone, not UTC
                current_date = from_date_utc
                while current_date < to_date_utc:
                    # Convert to participant's local timezone to check weekday
                    current_date_local = current_date.astimezone(participant_tz)
                    if current_date_local.weekday() == day:
                        # Create datetime for start/end of work hours in local timezone
                        start_hour = start_hm // 100
                        start_min = start_hm % 100
                        end_hour = end_hm // 100
                        end_min = end_hm % 100
                        
                        # Use the local date (midnight) to create work hours
                        work_start = current_date_local.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
                        work_end = current_date_local.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
                        
                        # Convert to UTC
                        work_start_utc = work_start.astimezone(pytz.UTC)
                        work_end_utc = work_end.astimezone(pytz.UTC)
                        
                        # Get slots for this work period
                        # Note: get_slots_in_range has exclusive end, so work_end_utc (5:00 PM) means
                        # slots up to but NOT including the slot starting at 5:00 PM.
                        # For work hours 9 AM - 5 PM, we want meetings to END by 5:00 PM.
                        # So we include slots up to 4:45 PM (the last slot that allows a meeting to end by 5:00 PM).
                        # This is already handled by the exclusive end - no adjustment needed.
                        work_period_slots = slot_indexer.get_slots_in_range(work_start_utc, work_end_utc)
                        work_slots.update(work_period_slots)
                    
                    current_date += timedelta(days=1)
            
            work_hours_slots[participant_id] = work_slots
    
    # Ensure all participants from events_by_participant have work hours set
    # If a participant isn't in context_json["participants"], apply default work hours in Eastern time
    # Default is 9-5 Eastern time unless explicitly specified otherwise
    default_work_hours_tz = "America/New_York"  # Always use Eastern time for default work hours
    for participant_id in events_by_participant.keys():
        if participant_id not in work_hours_slots:
            # Participant not in context_json - apply default work hours (9-5 Eastern)
            work_hours_str = "M-F 09:00-17:00"
            work_hours = parse_work_hours(work_hours_str, default_work_hours_tz)
            participant_tz = pytz.timezone(default_work_hours_tz)
            
            # Convert work hours to UTC slots
            work_slots = set()
            for day, start_hm, end_hm in work_hours:
                # CRITICAL: Check weekday in participant's timezone, not UTC
                current_date = from_date_utc
                while current_date < to_date_utc:
                    # Convert to participant's local timezone to check weekday
                    current_date_local = current_date.astimezone(participant_tz)
                    if current_date_local.weekday() == day:
                        start_hour = start_hm // 100
                        start_min = start_hm % 100
                        end_hour = end_hm // 100
                        end_min = end_hm % 100
                        
                        # Use the local date to create work hours
                        work_start = current_date_local.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
                        work_end = current_date_local.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
                        
                        # Convert to UTC
                        work_start_utc = work_start.astimezone(pytz.UTC)
                        work_end_utc = work_end.astimezone(pytz.UTC)
                        
                        work_period_slots = slot_indexer.get_slots_in_range(work_start_utc, work_end_utc)
                        work_slots.update(work_period_slots)
                    
                    current_date += timedelta(days=1)
            
            work_hours_slots[participant_id] = work_slots
    
    return {
        "slot_indexer": slot_indexer,
        "busy_slots": busy_slots,
        "work_hours_slots": work_hours_slots,
        "event_protection": event_protection,
        "event_slots_map": event_slots_map,  # For move logic: maps (participant_id, event_id) to slot set
        "event_metadata": event_metadata,  # For move logic: maps (participant_id, event_id) to event details
        "event_participants": event_participants,  # For move validation: maps (participant_id, event_id) to list of all participant emails
        "min_gap_slots": min_gap_slots,
        "timezone": timezone,
    }

