"""
Event detail extraction module for rescheduling.

This module provides functions to extract event details (participants, duration, title, etc.)
from fetched calendar events for use in rescheduling operations.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, time
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
    # Handle both formats: string (ISO 8601) or dict with dateTime/date keys
    start_raw = event.get("start", {})
    end_raw = event.get("end", {})
    
    # If start/end are strings, use them directly
    if isinstance(start_raw, str):
        start_dt_str = start_raw
    elif isinstance(start_raw, dict):
        start_dt_str = start_raw.get("dateTime")
        if not start_dt_str:
            # Check if it's an all-day event (has "date" instead of "dateTime")
            if start_raw.get("date"):
                raise ValueError("All-day events are not supported for rescheduling")
    else:
        start_dt_str = None
    
    if isinstance(end_raw, str):
        end_dt_str = end_raw
    elif isinstance(end_raw, dict):
        end_dt_str = end_raw.get("dateTime")
        if not end_dt_str:
            # Check if it's an all-day event (has "date" instead of "dateTime")
            if end_raw.get("date"):
                raise ValueError("All-day events are not supported for rescheduling")
    else:
        end_dt_str = None
    
    if not start_dt_str or not end_dt_str:
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
    
    # Extract participants - prefer attendees_details (with names) over attendees_list
    attendees_list = event.get("attendees_list", [])
    if not isinstance(attendees_list, list):
        attendees_list = []
    
    attendees_details = event.get("attendees_details", [])
    if not isinstance(attendees_details, list):
        attendees_details = []
    
    # Build participants list: owner + attendees (deduplicated)
    # Use emails from attendees_details if available, otherwise from attendees_list
    participants = [event_owner_id]
    if attendees_details:
        # Extract emails from attendees_details
        for attendee in attendees_details:
            if isinstance(attendee, dict):
                email = attendee.get("email", "")
                if email and email not in participants:
                    participants.append(email)
    else:
        # Fallback to attendees_list
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
    extracted_event_details: Optional[Dict[str, Any]],
    scheduling_problem: SchedulingProblem,
    context_json: Optional[Dict[str, Any]] = None,
    participant_ids: Optional[List[str]] = None
) -> SchedulingProblem:
    """
    Merge extracted event details with utterance constraints to create complete SchedulingProblem.
    
    This function combines:
    - Event details (participants, duration, title, location) as the base (if available)
    - Utterance constraints (preferences, time windows, additional participants) as overrides
    
    Utterance preferences override event defaults when there are conflicts.
    
    If extracted_event_details is None (event identification failed), this function still expands
    the time window to the full timeframe for rescheduling requests.
    
    Args:
        extracted_event_details: Event details from extract_event_details_for_rescheduling (None if identification failed)
        scheduling_problem: SchedulingProblem extracted from utterance
        context_json: Optional context for timeframe defaults
        
    Returns:
        Updated SchedulingProblem with merged details
    """
    # Start with event details as base (if available)
    if extracted_event_details:
        event_participants = extracted_event_details.get("participants", [])
        event_duration = extracted_event_details.get("duration_minutes", 0)
        event_title = extracted_event_details.get("title", "Meeting")
        event_location = extracted_event_details.get("location")
        event_start_utc = extracted_event_details.get("current_start_utc")
        event_end_utc = extracted_event_details.get("current_end_utc")
    else:
        # Event identification failed - use utterance values as defaults
        event_participants = []
        event_duration = 0
        event_title = "Meeting"
        event_location = None
        event_start_utc = None
        event_end_utc = None
    
    # Merge participants: Prefer participant_ids from input, then event participants, then utterance participants
    # For rescheduling, participant_ids (from the tool call) is the most authoritative source
    if participant_ids:
        merged_participants = participant_ids
    elif scheduling_problem.participants:
        merged_participants = scheduling_problem.participants
    elif event_participants:
        merged_participants = event_participants
    else:
        merged_participants = []
    
    # Ensure we have at least one participant
    if not merged_participants:
        raise ValueError("Cannot determine participants: event has no participants and utterance did not specify any")
    
    # Merge duration: For rescheduling, prefer event duration over utterance duration
    # Only use utterance duration if it's explicitly specified AND significantly different from event duration
    # This prevents DSPy from incorrectly extracting a default duration (e.g., 30 min) when the event is actually longer
    if extracted_event_details and event_duration > 0:
        # If utterance specifies a duration that's very different from event duration, use utterance
        # (e.g., user says "make it 30 minutes" for a 4-hour event)
        utterance_duration = scheduling_problem.duration_minutes if scheduling_problem.duration_minutes > 0 else 0
        if utterance_duration > 0 and abs(utterance_duration - event_duration) > event_duration * 0.3:
            # Utterance duration is significantly different (>30% difference), use it
            merged_duration = utterance_duration
        else:
            # Use event duration (preserve original meeting length)
            merged_duration = event_duration
    else:
        # No event details available, use utterance duration
        merged_duration = scheduling_problem.duration_minutes if scheduling_problem.duration_minutes > 0 else event_duration
    
    if merged_duration <= 0:
        raise ValueError(f"Invalid duration: {merged_duration} minutes")
    
    # Merge title: Use event title unless utterance specifies different
    merged_title = scheduling_problem.title if scheduling_problem.title else event_title
    
    # Merge location: Use event location unless utterance specifies different
    merged_location = scheduling_problem.location if scheduling_problem.location else event_location
    
    # For rescheduling, expand time window to full timeframe (default 2 weeks)
    # Keep preferred_days/preferred_times as preferences, not hard constraints
    # This ensures we find multiple options across the full search window
    merged_preferred_times = scheduling_problem.preferred_times
    merged_preferred_days = scheduling_problem.preferred_days
    merged_avoid_times = scheduling_problem.avoid_times
    merged_avoid_days = scheduling_problem.avoid_days
    
    # Set default timeframe if not in context (14 days = 2 weeks from today, current and future)
    if context_json and "timeframe" not in context_json:
        now = datetime.now(pytz.UTC)
        context_json["timeframe"] = {
            "from": now.strftime("%Y-%m-%d"),
            "to": (now + timedelta(days=13)).strftime("%Y-%m-%d"),  # 14 days inclusive = 2 weeks
            "tz": "America/New_York"
        }
    
    # For rescheduling, use the full timeframe from context_json, not the narrow window from utterance
    # The utterance's time_window is too restrictive (e.g., "Wednesday afternoon" = single day, 5 hours)
    # Instead, use the full timeframe and let preferred_days/preferred_times guide the search
    merged_time_window_start = None
    merged_time_window_end = None
    
    if context_json and "timeframe" in context_json:
        timeframe = context_json["timeframe"]
        tz_str = timeframe.get("tz", "America/New_York")
        from_date_str = timeframe.get("from")
        to_date_str = timeframe.get("to")
        
        if from_date_str and to_date_str:
            try:
                participant_tz = pytz.timezone(tz_str)
                # Parse dates and set to start/end of day in participant timezone
                from_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
                to_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()
                
                # Start of first day
                merged_time_window_start_dt = participant_tz.localize(
                    datetime.combine(from_date, time.min)
                )
                # End of last day
                merged_time_window_end_dt = participant_tz.localize(
                    datetime.combine(to_date, time.max)
                )
                
                # Convert to ISO format with timezone
                merged_time_window_start = merged_time_window_start_dt.isoformat()
                merged_time_window_end = merged_time_window_end_dt.isoformat()
            except Exception:
                # If parsing fails, fall back to utterance's time window
                merged_time_window_start = scheduling_problem.time_window_start
                merged_time_window_end = scheduling_problem.time_window_end
    else:
        # No timeframe in context - use utterance's time window as fallback
        merged_time_window_start = scheduling_problem.time_window_start
        merged_time_window_end = scheduling_problem.time_window_end
    
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

