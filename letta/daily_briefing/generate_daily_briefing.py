"""
Daily Briefing Tool

Generates a formatted daily schedule briefing with available time calculations
from calendar events retrieved via MCP.
"""

import os
import sys
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import pytz
import logging

logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import MCP client from scheduling orchestrator
try:
    from scheduling_orchestrator.mcp_client import MCPCalendarClient, MCPError
except ImportError:
    # Fallback if import fails
    MCPCalendarClient = None
    MCPError = None


async def _fetch_calendar_events(
    mcp_client: MCPCalendarClient,
    calendar_id: str,
    tz: pytz.BaseTzInfo
) -> List[Dict[str, Any]]:
    """
    Fetch calendar events for a 3-day window (today-1 to today+1).
    
    Args:
        mcp_client: Initialized MCP calendar client
        calendar_id: Calendar identifier (email address)
        tz: Timezone for date calculations
    
    Returns:
        List of normalized event dictionaries
    """
    # Calculate date range: today-1 to today+1 (3-day window)
    now = datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_before_start = today_start - timedelta(days=1)
    day_after_end = today_start + timedelta(days=2)  # End of day after tomorrow
    
    # Format dates for MCP Core_Event_Data
    # ⚠️ IMPORTANT: Parameter names are REVERSED!
    # "Before" = END date, "After" = START date
    # Use ISO format with timezone - convert to UTC for API
    after_date_iso = day_before_start.astimezone(pytz.UTC).strftime("%Y-%m-%dT00:00:00Z")
    before_date_iso = day_after_end.astimezone(pytz.UTC).strftime("%Y-%m-%dT23:59:59Z")
    
    try:
        # Fetch events via MCP
        # ⚠️ Remember: Before=end, After=start
        events = await mcp_client.get_core_event_data(
            calendar_id=calendar_id,
            before=before_date_iso,  # END date
            after=after_date_iso      # START date
        )
        
        # Normalize event data
        normalized_events = []
        for evt in events:
            # Skip all-day events (they have "date" not "dateTime")
            start_data = evt.get("start", {})
            end_data = evt.get("end", {})
            
            if "date" in start_data:
                # All-day event, skip it
                continue
            
            start_dt_str = start_data.get("dateTime")
            end_dt_str = end_data.get("dateTime")
            
            if not start_dt_str or not end_dt_str:
                # Missing required time data, skip
                continue
            
            # Extract attendees information
            attendees_list = evt.get("attendees_list", [])
            attendees_details = evt.get("attendees_details", [])
            
            # Normalize attendees to a consistent format
            if isinstance(attendees_list, str):
                try:
                    import ast
                    attendees_list = ast.literal_eval(attendees_list)
                except:
                    attendees_list = []
            elif not isinstance(attendees_list, list):
                attendees_list = []
            
            # Build attendees list with names if available
            attendees = []
            if attendees_details and isinstance(attendees_details, list):
                for attendee in attendees_details:
                    if isinstance(attendee, dict):
                        name = attendee.get("name", "")
                        email = attendee.get("email", "")
                        if name and email:
                            attendees.append(f"{name} <{email}>")
                        elif email:
                            attendees.append(email)
                        elif name:
                            attendees.append(name)
            
            # Fallback to attendees_list if no details
            if not attendees and attendees_list:
                attendees = [str(a) for a in attendees_list if a]
            
            # Create normalized event
            normalized_event = {
                "id": evt.get("id", ""),
                "title": evt.get("summary", ""),
                "start": start_dt_str,
                "end": end_dt_str,
                "locked": evt.get("locked", False),
                "protected": evt.get("protected", False),
                "flexible": evt.get("flexible", True),
                "attendees": attendees,
                "number_of_attendees": evt.get("number_of_attendees", len(attendees)),
                "internal_only": evt.get("internal_only", False)
            }
            
            normalized_events.append(normalized_event)
        
        return normalized_events
    
    except MCPError as e:
        logger.error(f"MCP error fetching events: {e.message}")
        raise
    except Exception as e:
        logger.error(f"Error fetching calendar events: {e}", exc_info=True)
        raise


def _parse_datetime(dt_str: str, tz: pytz.BaseTzInfo) -> datetime:
    """
    Parse ISO 8601 datetime string to timezone-aware datetime.
    
    Args:
        dt_str: ISO 8601 datetime string
        tz: Target timezone
    
    Returns:
        Timezone-aware datetime object
    """
    # Try parsing with dateutil if available, otherwise use basic parsing
    try:
        from dateutil import parser
        dt = parser.isoparse(dt_str)
    except ImportError:
        # Fallback to basic parsing
        try:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        except ValueError:
            # Try another format
            dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S%z")
    
    # Ensure timezone-aware
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    
    # Convert to target timezone
    return dt.astimezone(tz)


def _events_overlap(event1: Dict[str, Any], event2: Dict[str, Any], tz: pytz.BaseTzInfo) -> bool:
    """
    Check if two events overlap in time.
    
    Args:
        event1: First event dict with 'start' and 'end' ISO strings
        event2: Second event dict with 'start' and 'end' ISO strings
        tz: Timezone for parsing
    
    Returns:
        True if events overlap, False otherwise
    """
    try:
        start1 = _parse_datetime(event1["start"], tz)
        end1 = _parse_datetime(event1["end"], tz)
        start2 = _parse_datetime(event2["start"], tz)
        end2 = _parse_datetime(event2["end"], tz)
        
        # Events overlap if one starts before the other ends
        return start1 < end2 and start2 < end1
    except Exception as e:
        logger.warning(f"Error checking event overlap: {e}")
        return False


def _is_email_tasks_event(event: Dict[str, Any], tz: pytz.BaseTzInfo) -> bool:
    """
    Check if event is "Email & Tasks" (9:00-11:00 AM).
    
    Args:
        event: Event dict
        tz: Timezone for parsing
    
    Returns:
        True if event is "Email & Tasks" in the 9:00-11:00 AM slot
    """
    title = event.get("title", "").lower()
    if "email" not in title or "task" not in title:
        return False
    
    try:
        start = _parse_datetime(event["start"], tz)
        end = _parse_datetime(event["end"], tz)
        
        # Check if it's in the 9:00-11:00 AM range
        hour_start = start.hour
        hour_end = end.hour
        
        # Should start at 9 AM and end at 11 AM (or close)
        return hour_start == 9 and hour_end == 11
    except Exception:
        return False


def _is_hold_event(event: Dict[str, Any]) -> bool:
    """
    Check if event is a "Hold" event.
    
    Args:
        event: Event dict
    
    Returns:
        True if event title contains "Hold"
    """
    title = event.get("title", "").lower()
    return "hold" in title


def _is_chad_out_event(event: Dict[str, Any]) -> bool:
    """
    Check if event is "Chad out".
    
    Args:
        event: Event dict
    
    Returns:
        True if event title indicates "Chad out"
    """
    title = event.get("title", "").lower()
    return "chad out" in title or "chad's out" in title


def _filter_events(events: List[Dict[str, Any]], tz: pytz.BaseTzInfo) -> List[Dict[str, Any]]:
    """
    Filter events according to gold-standard rules.
    
    Rules:
    - Include ALL events where Chad is a participant
    - Exclude "Email & Tasks" (9:00-11:00 AM) unless overlapped by real meeting
    - Exclude "Hold" events unless overlapped by real meeting
    - Include "Chad out" events (they represent busy time)
    - Sort chronologically by start time
    
    Args:
        events: List of normalized event dictionaries
        tz: Timezone for time parsing
    
    Returns:
        Filtered and sorted list of events
    """
    if not events:
        return []
    
    # Separate events into categories
    email_tasks_events = []
    hold_events = []
    chad_out_events = []
    real_meetings = []
    
    for event in events:
        if _is_email_tasks_event(event, tz):
            email_tasks_events.append(event)
        elif _is_hold_event(event):
            hold_events.append(event)
        elif _is_chad_out_event(event):
            chad_out_events.append(event)
        else:
            real_meetings.append(event)
    
    # Check for overlaps: if a real meeting overlaps email_tasks or hold, include the real meeting
    # and mark the email_tasks/hold as overlapped (so we don't exclude it)
    overlapped_email_tasks = set()
    overlapped_holds = set()
    
    for real_meeting in real_meetings:
        for i, email_task in enumerate(email_tasks_events):
            if _events_overlap(real_meeting, email_task, tz):
                overlapped_email_tasks.add(i)
        
        for i, hold_event in enumerate(hold_events):
            if _events_overlap(real_meeting, hold_event, tz):
                overlapped_holds.add(i)
    
    # Build final list:
    # - All real meetings
    # - Email & Tasks that are overlapped
    # - Hold events that are overlapped
    # - All Chad out events
    filtered_events = list(real_meetings)
    
    for i in overlapped_email_tasks:
        filtered_events.append(email_tasks_events[i])
    
    for i in overlapped_holds:
        filtered_events.append(hold_events[i])
    
    filtered_events.extend(chad_out_events)
    
    # Sort chronologically by start time
    try:
        filtered_events.sort(key=lambda e: _parse_datetime(e["start"], tz))
    except Exception as e:
        logger.warning(f"Error sorting events: {e}")
        # Keep original order if sorting fails
    
    return filtered_events


def generate_daily_briefing(
    calendar_id: Optional[str] = None,
    timezone: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a daily briefing with formatted schedule and available time calculations.
    
    This tool retrieves calendar events from the specified calendar, filters them
    according to gold-standard rules, calculates available time from the current
    moment to 5:00 PM Eastern, and generates a Markdown-formatted briefing report.
    
    The tool:
    - Retrieves events for a 3-day window (today-1 to today+1)
    - Filters out "Email & Tasks" and "Hold" events unless overlapped by real meetings
    - Calculates available time blocks from current time to 5:00 PM Eastern
    - Formats output in gold-standard Markdown format
    - Provides content for memory block updates
    
    Args:
        calendar_id: Calendar identifier (email address). Defaults to "cdorsey@concord.org".
                    The tool will retrieve events from this calendar via MCP Core_Event_Data.
        
        timezone: Timezone for time calculations and display. Defaults to "America/New_York".
                 Must be a valid pytz timezone string. All times in the briefing will be
                 displayed in this timezone with proper daylight savings handling.
    
    Returns:
        Dictionary with the following keys:
        
        - status (str): "ok" if briefing generated successfully, "error" if an error occurred
        
        - briefing (str): Markdown-formatted daily briefing with:
            - Header with timestamp (e.g., "# Today's Schedule (updated Wed. Dec 11 at 12:27 PM)")
            - Schedule section with chronological event listing
            - Available time section with total and individual blocks
        
        - memory_content (str): Content for updating Letta memory block
                               `current_daily_schedule_and_available_time`. This should
                               match the briefing format exactly.
        
        - timestamp (str): ISO 8601 timestamp of when the briefing was generated
                          (in the specified timezone)
        
        - current_time_eastern (str): Current time in Eastern timezone formatted as
                                     "H:MM AM/PM" for display in briefing header
        
        - error_message (str, optional): Error message if status is "error"
        
        - events_retrieved (int, optional): Number of events retrieved from calendar
        
        - events_included (int, optional): Number of events included in briefing after filtering
    
    Examples:
        Basic usage:
        >>> result = generate_daily_briefing()
        >>> if result["status"] == "ok":
        ...     print(result["briefing"])
        
        Custom calendar:
        >>> result = generate_daily_briefing(calendar_id="user@example.com")
        
        Custom timezone:
        >>> result = generate_daily_briefing(timezone="America/Los_Angeles")
    
    Notes:
        - The tool always retrieves events for a 3-day window (today-1 to today+1)
        - Available time is calculated from current time to 5:00 PM Eastern only
        - "Email & Tasks" (9:00-11:00 AM) and "Hold" events are excluded unless
          overlapped by real meetings
        - All events where the calendar owner is a participant are included
        - "Chad out" events are treated as busy time
    """
    # Set defaults
    if calendar_id is None:
        calendar_id = "cdorsey@concord.org"
    
    if timezone is None:
        timezone = "America/New_York"
    
    try:
        # Get current time in specified timezone
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        
        # Format current time for display
        # Use strftime format that works on both Unix and Windows
        try:
            current_time_formatted = now.strftime("%-I:%M %p")  # Unix format
        except ValueError:
            current_time_formatted = now.strftime("%I:%M %p").lstrip("0")  # Windows-compatible
        
        day_name = now.strftime("%a")
        month_name = now.strftime("%b")
        day_number = now.strftime("%d")
        
        # Initialize MCP client if available
        if MCPCalendarClient is None:
            return {
                "status": "error",
                "briefing": "",
                "memory_content": "",
                "timestamp": now.isoformat(),
                "current_time_eastern": current_time_formatted,
                "error_message": "MCP calendar client not available. Ensure scheduling_orchestrator.mcp_client is accessible."
            }
        
        # Get MCP server URL from environment or use default
        mcp_url = os.getenv(
            "MCP_CALENDAR_SERVER_URL",
            "http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb"
        )
        
        # Create MCP client
        mcp_client = MCPCalendarClient(
            base_url=mcp_url,
            timeout=int(os.getenv("MCP_CALENDAR_TIMEOUT", "30")),
            max_retries=int(os.getenv("MCP_CALENDAR_RETRY_ATTEMPTS", "3"))
        )
        
        # Fetch calendar events
        try:
            events = asyncio.run(_fetch_calendar_events(mcp_client, calendar_id, tz))
            events_retrieved = len(events)
        except MCPError as e:
            return {
                "status": "error",
                "briefing": "",
                "memory_content": "",
                "timestamp": now.isoformat(),
                "current_time_eastern": current_time_formatted,
                "error_message": f"Failed to retrieve calendar events: {e.message}",
                "events_retrieved": 0
            }
        except Exception as e:
            logger.error(f"Error fetching events: {e}", exc_info=True)
            return {
                "status": "error",
                "briefing": "",
                "memory_content": "",
                "timestamp": now.isoformat(),
                "current_time_eastern": current_time_formatted,
                "error_message": f"Error fetching calendar events: {str(e)}",
                "events_retrieved": 0
            }
        
        # Filter events according to gold-standard rules
        filtered_events = _filter_events(events, tz)
        events_included = len(filtered_events)
        
        # TODO: Implement available time calculation (task 24-5)
        # TODO: Implement Markdown formatting (task 24-6)
        
        # Placeholder return structure
        briefing = f"""# Today's Schedule (updated {day_name}. {month_name} {day_number} at {current_time_formatted})

**Today's Schedule**
*Retrieved {events_retrieved} events, {events_included} included after filtering - formatting in progress*

### Available Time Remaining — **0h, 0 min**
*Time calculation in progress*
"""
        
        return {
            "status": "ok",
            "briefing": briefing,
            "memory_content": briefing,
            "timestamp": now.isoformat(),
            "current_time_eastern": current_time_formatted,
            "events_retrieved": events_retrieved,
            "events_included": events_included
        }
    
    except Exception as e:
        logger.error(f"Error generating daily briefing: {e}", exc_info=True)
        return {
            "status": "error",
            "briefing": "",
            "memory_content": "",
            "timestamp": datetime.now(pytz.timezone(timezone)).isoformat(),
            "current_time_eastern": "",
            "error_message": str(e)
        }

