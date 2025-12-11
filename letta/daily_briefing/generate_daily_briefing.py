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


def _calculate_available_time(
    events: List[Dict[str, Any]],
    now: datetime,
    tz: pytz.BaseTzInfo
) -> tuple[int, List[Dict[str, Any]]]:
    """
    Calculate available time blocks from current time to 5:00 PM.
    
    Args:
        events: List of filtered events (already sorted chronologically)
        now: Current datetime in timezone
        tz: Timezone for calculations
    
    Returns:
        Tuple of (total_minutes, list_of_blocks)
        Each block is a dict with: start, end, duration_minutes
    """
    # Set 5:00 PM cutoff
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_time = today_start.replace(hour=17, minute=0)  # 5:00 PM
    
    # If current time is after 5:00 PM, no available time
    if now >= cutoff_time:
        return 0, []
    
    # Filter events to only today's events that end after current time
    today_events = []
    for event in events:
        try:
            event_start = _parse_datetime(event["start"], tz)
            event_end = _parse_datetime(event["end"], tz)
            
            # Only include events that:
            # 1. Are today (same date as now)
            # 2. End after current time
            if event_start.date() == now.date() and event_end > now:
                today_events.append({
                    "start": event_start,
                    "end": event_end,
                    "event": event
                })
        except Exception as e:
            logger.warning(f"Error parsing event for available time: {e}")
            continue
    
    # Sort by start time
    today_events.sort(key=lambda e: e["start"])
    
    # Calculate available blocks
    available_blocks = []
    current_time = now
    
    for event_info in today_events:
        event_start = event_info["start"]
        event_end = event_info["end"]
        
        # If there's a gap before this event
        if current_time < event_start:
            # Block ends at event start or 5:00 PM, whichever is earlier
            block_end = min(event_start, cutoff_time)
            if block_end > current_time:
                duration_minutes = int((block_end - current_time).total_seconds() / 60)
                if duration_minutes > 0:
                    available_blocks.append({
                        "start": current_time,
                        "end": block_end,
                        "duration_minutes": duration_minutes
                    })
        
        # Update current_time to after this event
        current_time = max(current_time, event_end)
        
        # If we've passed 5:00 PM, stop
        if current_time >= cutoff_time:
            break
    
    # Check for gap from last event to 5:00 PM
    if current_time < cutoff_time:
        duration_minutes = int((cutoff_time - current_time).total_seconds() / 60)
        if duration_minutes > 0:
            available_blocks.append({
                "start": current_time,
                "end": cutoff_time,
                "duration_minutes": duration_minutes
            })
    
    # Merge adjacent blocks (they should already be merged, but just in case)
    merged_blocks = []
    for block in available_blocks:
        if not merged_blocks:
            merged_blocks.append(block)
        else:
            last_block = merged_blocks[-1]
            # If this block starts right after the last one ends, merge them
            if block["start"] <= last_block["end"]:
                # Merge: extend last block
                last_block["end"] = block["end"]
                last_block["duration_minutes"] = int(
                    (last_block["end"] - last_block["start"]).total_seconds() / 60
                )
            else:
                merged_blocks.append(block)
    
    # Calculate total minutes
    total_minutes = sum(block["duration_minutes"] for block in merged_blocks)
    
    return total_minutes, merged_blocks


def _format_duration(total_minutes: int) -> str:
    """
    Format duration as "Xh, Y min".
    
    Args:
        total_minutes: Total minutes
    
    Returns:
        Formatted string like "3h, 15 min"
    """
    hours = total_minutes // 60
    minutes = total_minutes % 60
    
    if hours == 0:
        return f"{minutes} min"
    elif minutes == 0:
        return f"{hours}h"
    else:
        return f"{hours}h, {minutes} min"


def _format_time(dt: datetime) -> str:
    """
    Format datetime as "H:MM AM/PM".
    
    Args:
        dt: Datetime object
    
    Returns:
        Formatted time string
    """
    try:
        return dt.strftime("%-I:%M %p")  # Unix format
    except ValueError:
        return dt.strftime("%I:%M %p").lstrip("0")  # Windows-compatible


def _format_event_markdown(event: Dict[str, Any], tz: pytz.BaseTzInfo) -> str:
    """
    Format a single event as a Markdown bullet point.
    
    Format for regular meetings: `• **start–end** — **Bold meeting title** (*attendee names italicized*)`
    Format for solo blocks: `• **Email & Tasks** (*Chad Dorsey*) — *9:00–11:00 AM*`
    
    Args:
        event: Event dictionary
        tz: Timezone for time formatting
    
    Returns:
        Formatted Markdown string
    """
    try:
        start = _parse_datetime(event["start"], tz)
        end = _parse_datetime(event["end"], tz)
        start_str = _format_time(start)
        end_str = _format_time(end)
        time_range = f"{start_str}–{end_str}"
        
        title = event.get("title", "")
        attendees = event.get("attendees", [])
        
        # Check if it's a solo block (Email & Tasks, Hold, etc.)
        title_lower = title.lower()
        is_solo = (
            ("email" in title_lower and "task" in title_lower) or
            "hold" in title_lower
        )
        
        # Format attendees
        if attendees:
            # Extract names from "Name <email>" format or use as-is
            attendee_names = []
            for attendee in attendees:
                if "<" in attendee and ">" in attendee:
                    # Extract name part before <
                    name = attendee.split("<")[0].strip()
                    if name:
                        attendee_names.append(name)
                    else:
                        # Fallback to email
                        email = attendee.split("<")[1].split(">")[0].strip()
                        attendee_names.append(email)
                else:
                    attendee_names.append(attendee)
            attendee_str = ", ".join(attendee_names)
        else:
            attendee_str = "Chad Dorsey"  # Default if no attendees
        
        attendee_part = f" (*{attendee_str}*)"
        
        if is_solo:
            # Solo blocks: bold title, italicize time range
            return f"• **{title}**{attendee_part} — *{time_range}*"
        else:
            # Regular meetings: bold time range, bold title, italicize attendees
            return f"• **{time_range}** — **{title}**{attendee_part}"
    
    except Exception as e:
        logger.warning(f"Error formatting event: {e}")
        return f"• **{event.get('title', 'Unknown Event')}**"


def _format_available_time_blocks(
    blocks: List[Dict[str, Any]],
    tz: pytz.BaseTzInfo
) -> str:
    """
    Format available time blocks as Markdown list.
    
    Format:
    - First block: `- start – end (X min left)`
    - Subsequent: `- start – end (X min)`
    - All parenthetical times italicized
    
    Args:
        blocks: List of available time block dicts with start, end, duration_minutes
        tz: Timezone for time formatting
    
    Returns:
        Formatted Markdown string
    """
    if not blocks:
        return ""
    
    lines = []
    for i, block in enumerate(blocks):
        try:
            start = _parse_datetime(block["start"], tz) if isinstance(block["start"], str) else block["start"]
            end = _parse_datetime(block["end"], tz) if isinstance(block["end"], str) else block["end"]
            
            start_str = _format_time(start)
            end_str = _format_time(end)
            duration = block["duration_minutes"]
            
            # First block uses "left", others don't
            if i == 0:
                duration_str = f"*({duration} min left)*"
            else:
                duration_str = f"*({duration} min)*"
            
            lines.append(f"- {start_str} – {end_str} {duration_str}")
        except Exception as e:
            logger.warning(f"Error formatting available block: {e}")
            continue
    
    return "\n".join(lines)


def _format_briefing_markdown(
    now: datetime,
    events: List[Dict[str, Any]],
    available_blocks: List[Dict[str, Any]],
    total_available_minutes: int,
    tz: pytz.BaseTzInfo
) -> str:
    """
    Format the complete briefing in Markdown format.
    
    Args:
        now: Current datetime
        events: List of filtered events (for today)
        available_blocks: List of available time blocks
        total_available_minutes: Total available minutes
        tz: Timezone for formatting
    
    Returns:
        Complete Markdown-formatted briefing
    """
    # Format header
    try:
        current_time_formatted = _format_time(now)
    except ValueError:
        current_time_formatted = now.strftime("%I:%M %p").lstrip("0")
    
    day_name = now.strftime("%a")
    month_name = now.strftime("%b")
    day_number = now.strftime("%d")
    
    header = f"# Today's Schedule (updated {day_name}. {month_name} {day_number} at {current_time_formatted})"
    
    # Format schedule section
    schedule_lines = ["**Today's Schedule**"]
    
    # Filter events to only today's events
    today_events = []
    for event in events:
        try:
            event_start = _parse_datetime(event["start"], tz)
            if event_start.date() == now.date():
                today_events.append(event)
        except Exception:
            continue
    
    if today_events:
        for event in today_events:
            schedule_lines.append(_format_event_markdown(event, tz))
    else:
        schedule_lines.append("*No meetings scheduled*")
    
    schedule_section = "\n".join(schedule_lines)
    
    # Format available time section
    available_time_formatted = _format_duration(total_available_minutes)
    available_time_header = f"### Available Time Remaining — **{available_time_formatted}**"
    
    available_time_blocks_str = _format_available_time_blocks(available_blocks, tz)
    
    if available_time_blocks_str:
        available_time_section = f"{available_time_header}\n{available_time_blocks_str}"
    else:
        available_time_section = f"{available_time_header}\n*No available time remaining*"
    
    # Combine all sections
    briefing = f"{header}\n\n{schedule_section}\n\n{available_time_section}"
    
    return briefing


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
        
        # Calculate available time blocks
        total_available_minutes, available_blocks = _calculate_available_time(
            filtered_events, now, tz
        )
        
        # Format briefing in Markdown
        briefing = _format_briefing_markdown(
            now, filtered_events, available_blocks, total_available_minutes, tz
        )
        
        return {
            "status": "ok",
            "briefing": briefing,
            "memory_content": briefing,  # Same content for memory block
            "timestamp": now.isoformat(),
            "current_time_eastern": current_time_formatted,
            "events_retrieved": events_retrieved,
            "events_included": events_included,
            "total_available_minutes": total_available_minutes,
            "available_blocks": [
                {
                    "start": block["start"].isoformat() if isinstance(block["start"], datetime) else block["start"],
                    "end": block["end"].isoformat() if isinstance(block["end"], datetime) else block["end"],
                    "duration_minutes": block["duration_minutes"]
                }
                for block in available_blocks
            ]
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

