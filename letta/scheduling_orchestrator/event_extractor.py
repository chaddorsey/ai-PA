"""
Event detail extraction module for rescheduling.

This module provides functions to extract event details (participants, duration, title, etc.)
from fetched calendar events for use in rescheduling operations.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import pytz


def extract_event_details_for_rescheduling(
    event: Dict[str, Any],
    event_owner_id: str
) -> Dict[str, Any]:
    """
    Extract event details from a fetched event for rescheduling.
    
    Args:
        event: Event dictionary from MCP Core_Event_Data with structure:
               {
                 "summary": "Event title",
                 "id": "event_id",
                 "start": {"dateTime": "2025-12-09T11:00:00-05:00"},
                 "end": {"dateTime": "2025-12-09T15:00:00-05:00"},
                 "locked": false,
                 "protected": false,
                 "flexible": true,
                 "internal_only": true,
                 "attendees_list": ["email1@example.com", ...],
                 "location": "optional location"
               }
        event_owner_id: The participant ID whose calendar the event was found in
        
    Returns:
        Dictionary with extracted details:
        {
            "event_id": str,
            "participants": List[str],  # All participants (owner + attendees)
            "duration_minutes": int,
            "title": str,
            "location": Optional[str],
            "current_start_utc": str,  # ISO 8601 UTC
            "current_end_utc": str,    # ISO 8601 UTC
            "internal_only": bool,
            "locked": bool,
            "protected": bool,
            "flexible": bool
        }
        
    Raises:
        ValueError: If event is missing required fields or is not internal-only when moving is required
    """
    # Extract event ID
    event_id = event.get("id", "")
    if not event_id:
        raise ValueError("Event missing required 'id' field")
    
    # Extract title
    title = event.get("summary", "").strip()
    if not title:
        title = "Untitled Meeting"
    
    # Extract location
    location = event.get("location")
    if location:
        location = location.strip()
    
    # Extract start/end times
    start_data = event.get("start", {})
    end_data = event.get("end", {})
    
    # Handle both dateTime and date formats (skip all-day events)
    start_dt_str = start_data.get("dateTime")
    end_dt_str = end_data.get("dateTime")
    
    if not start_dt_str or not end_dt_str:
        # Check if it's an all-day event (has "date" instead of "dateTime")
        if start_data.get("date") or end_data.get("date"):
            raise ValueError("All-day events are not supported for rescheduling")
        raise ValueError("Event missing required start/end times")
    
    # Parse datetimes
    try:
        # Replace "Z" with "+00:00" for ISO format compatibility
        start_str_clean = start_dt_str.replace("Z", "+00:00")
        end_str_clean = end_dt_str.replace("Z", "+00:00")
        
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
        
        # Calculate duration
        duration_delta = end_dt - start_dt
        duration_minutes = int(duration_delta.total_seconds() / 60)
        
        if duration_minutes <= 0:
            raise ValueError(f"Invalid event duration: {duration_minutes} minutes")
        
        # Format as ISO 8601 UTC strings
        current_start_utc = start_dt.strftime("%Y-%m-%dT%H:%M:%S%z")
        if current_start_utc.endswith("+0000"):
            current_start_utc = current_start_utc.replace("+0000", "Z")
        elif not current_start_utc.endswith("Z"):
            current_start_utc += "Z"
        
        current_end_utc = end_dt.strftime("%Y-%m-%dT%H:%M:%S%z")
        if current_end_utc.endswith("+0000"):
            current_end_utc = current_end_utc.replace("+0000", "Z")
        elif not current_end_utc.endswith("Z"):
            current_end_utc += "Z"
            
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Failed to parse event start/end times: {str(e)}")
    
    # Extract participants
    attendees_list = event.get("attendees_list", [])
    if not isinstance(attendees_list, list):
        attendees_list = []
    
    # Build participants list: owner + attendees (deduplicated)
    participants = [event_owner_id]
    for attendee in attendees_list:
        if attendee and attendee not in participants:
            participants.append(attendee)
    
    # Extract flags
    internal_only = event.get("internal_only", True)  # Default to True for backwards compatibility
    locked = event.get("locked", False)
    protected = event.get("protected", False)
    flexible = event.get("flexible", True)
    
    # Validate internal_only if moving is required
    # Note: This validation happens here, but the actual decision about whether to move
    # is made later in the scheduling logic. We just extract and flag it.
    if not internal_only:
        # Log warning but don't fail - the scheduling logic will handle this
        import sys
        try:
            print(f"[extract_event_details] WARNING: Event {event_id} is not internal-only (external event). It may not be movable.", file=sys.stderr, flush=True)
        except:
            pass
    
    return {
        "event_id": event_id,
        "participants": participants,
        "duration_minutes": duration_minutes,
        "title": title,
        "location": location,
        "current_start_utc": current_start_utc,
        "current_end_utc": current_end_utc,
        "internal_only": internal_only,
        "locked": locked,
        "protected": protected,
        "flexible": flexible
    }

