"""
Event detail extraction module for rescheduling.

This module provides functions to extract event details (participants, duration, title, etc.)
from fetched calendar events for use in rescheduling operations.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import pytz
from .schemas import SchedulingProblem


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
        # Normalize timezone formats for ISO format compatibility
        # Handle "Z" -> "+00:00"
        # Handle "+0000" -> "+00:00" (no colon format)
        start_str_clean = start_dt_str.replace("Z", "+00:00")
        if start_str_clean.endswith("+0000"):
            start_str_clean = start_str_clean.replace("+0000", "+00:00")
        elif start_str_clean.endswith("-0000"):
            start_str_clean = start_str_clean.replace("-0000", "+00:00")
        
        end_str_clean = end_dt_str.replace("Z", "+00:00")
        if end_str_clean.endswith("+0000"):
            end_str_clean = end_str_clean.replace("+0000", "+00:00")
        elif end_str_clean.endswith("-0000"):
            end_str_clean = end_str_clean.replace("-0000", "+00:00")
        
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


def merge_event_details_with_utterance(
    extracted_event_details: Dict[str, Any],
    scheduling_problem: SchedulingProblem,
    context_json: Optional[Dict[str, Any]] = None
) -> SchedulingProblem:
    """
    Merge extracted event details with utterance constraints to create complete SchedulingProblem.
    
    This function combines:
    - Event details (participants, duration, title, location) as the base
    - Utterance constraints (preferences, time windows, additional participants) as overrides
    
    Utterance preferences override event defaults when there are conflicts.
    
    Args:
        extracted_event_details: Event details from extract_event_details_for_rescheduling
        scheduling_problem: SchedulingProblem extracted from utterance
        context_json: Optional context for timeframe defaults
        
    Returns:
        Updated SchedulingProblem with merged details
    """
    # Start with event details as base
    event_participants = extracted_event_details.get("participants", [])
    event_duration = extracted_event_details.get("duration_minutes", 0)
    event_title = extracted_event_details.get("title", "Meeting")
    event_location = extracted_event_details.get("location")
    event_start_utc = extracted_event_details.get("current_start_utc")
    event_end_utc = extracted_event_details.get("current_end_utc")
    
    # Merge participants: Use event participants as base, but utterance may add participants
    # If utterance specifies participants, use those (they may include additional people)
    # Otherwise, use event participants
    merged_participants = scheduling_problem.participants if scheduling_problem.participants else event_participants
    
    # If utterance participants are empty but event has participants, use event participants
    if not merged_participants and event_participants:
        merged_participants = event_participants
    
    # Ensure we have at least one participant
    if not merged_participants:
        raise ValueError("Cannot determine participants: event has no participants and utterance did not specify any")
    
    # Merge duration: Use event duration unless utterance specifies different
    merged_duration = scheduling_problem.duration_minutes if scheduling_problem.duration_minutes > 0 else event_duration
    
    if merged_duration <= 0:
        raise ValueError(f"Invalid duration: {merged_duration} minutes")
    
    # Merge title: Use event title unless utterance specifies different
    merged_title = scheduling_problem.title if scheduling_problem.title else event_title
    
    # Merge location: Use event location unless utterance specifies different
    merged_location = scheduling_problem.location if scheduling_problem.location else event_location
    
    # For time constraints, utterance preferences take precedence
    # But we can use event's current time as a reference if utterance doesn't specify
    merged_time_window_start = scheduling_problem.time_window_start
    merged_time_window_end = scheduling_problem.time_window_end
    merged_preferred_times = scheduling_problem.preferred_times
    merged_preferred_days = scheduling_problem.preferred_days
    merged_avoid_times = scheduling_problem.avoid_times
    merged_avoid_days = scheduling_problem.avoid_days
    
    # Set default timeframe if not in context (28 days from today, current and future)
    if context_json and "timeframe" not in context_json:
        now = datetime.now(pytz.UTC)
        context_json["timeframe"] = {
            "from": now.strftime("%Y-%m-%d"),
            "to": (now + timedelta(days=26)).strftime("%Y-%m-%d"),  # 27 days inclusive = 28 days
            "tz": "America/New_York"
        }
    
    # Create merged SchedulingProblem
    merged_problem = SchedulingProblem(
        participants=merged_participants,
        duration_minutes=merged_duration,
        time_window_start=merged_time_window_start,
        time_window_end=merged_time_window_end,
        preferred_times=merged_preferred_times,
        preferred_days=merged_preferred_days,
        participant_preferences=scheduling_problem.participant_preferences,
        avoid_times=merged_avoid_times,
        avoid_days=merged_avoid_days,
        title=merged_title,
        location=merged_location,
        min_gap_minutes=scheduling_problem.min_gap_minutes,
        allow_off_hours=scheduling_problem.allow_off_hours,
        is_rescheduling=True,  # Mark as rescheduling
        event_identifiers=scheduling_problem.event_identifiers  # Preserve original identifiers
    )
    
    return merged_problem

