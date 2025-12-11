"""
Daily Briefing Tool

Generates a formatted daily schedule briefing with available time calculations
from calendar events retrieved via MCP.
"""

from typing import Dict, Any, Optional

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
    """
    # ⚠️ CRITICAL: Imports MUST be first, before any other code
    # Import required modules inside function for Letta tool extraction
    import os
    import sys
    import asyncio
    from typing import Dict, Any, Optional, List
    from datetime import datetime, timedelta
    import pytz
    import logging
    
    # Initialize logger
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
    
    # Define helper functions inside main function so they're included when Letta extracts the function
    
    async def fetch_calendar_events(mcp_client_obj: str, calendar_id_str: str, tz_obj: str) -> str:
        """Fetch calendar events for a 3-day window (today-1 to today+1).
        
        Args:
            mcp_client_obj: MCP calendar client object
            calendar_id_str: Calendar identifier (email address)
            tz_obj: Timezone string for date calculations
        """
        tz_actual = pytz.timezone(tz_obj) if isinstance(tz_obj, str) else tz_obj
        now_temp = datetime.now(tz_actual)
        today_start = now_temp.replace(hour=0, minute=0, second=0, microsecond=0)
        day_before_start = today_start - timedelta(days=1)
        day_after_end = today_start + timedelta(days=2)
        after_date_iso = day_before_start.astimezone(pytz.UTC).strftime("%Y-%m-%dT00:00:00Z")
        before_date_iso = day_after_end.astimezone(pytz.UTC).strftime("%Y-%m-%dT23:59:59Z")
        try:
            mcp_actual = mcp_client_obj
            # Initialize MCP client if not already initialized
            if not mcp_actual._initialized:
                await mcp_actual.initialize()
            events = await mcp_actual.get_core_event_data(
                calendar_id=calendar_id_str,
                before=before_date_iso,
                after=after_date_iso
            )
            normalized_events = []
            for evt in events:
                start_data = evt.get("start", {})
                end_data = evt.get("end", {})
                if "date" in start_data:
                    continue
                start_dt_str = start_data.get("dateTime")
                end_dt_str = end_data.get("dateTime")
                if not start_dt_str or not end_dt_str:
                    continue
                attendees_list = evt.get("attendees_list", [])
                attendees_details = evt.get("attendees_details", [])
                if isinstance(attendees_list, str):
                    try:
                        import ast
                        attendees_list = ast.literal_eval(attendees_list)
                    except:
                        attendees_list = []
                elif not isinstance(attendees_list, list):
                    attendees_list = []
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
                if not attendees and attendees_list:
                    attendees = [str(a) for a in attendees_list if a]
                normalized_events.append({
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
                })
            return normalized_events
        except MCPError as e:
            logger.error(f"MCP error fetching events: {e.message}")
            raise
        except Exception as e:
            logger.error(f"Error fetching calendar events: {e}", exc_info=True)
            raise
    
    def parse_datetime(dt_str: str, tz_obj: str) -> str:
        """Parse ISO 8601 datetime string to timezone-aware datetime.
        
        Args:
            dt_str: ISO 8601 datetime string
            tz_obj: Timezone string
        """
        try:
            from dateutil import parser
            dt = parser.isoparse(dt_str)
        except ImportError:
            try:
                dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            except ValueError:
                dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S%z")
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        tz_actual = pytz.timezone(tz_obj) if isinstance(tz_obj, str) else tz_obj
        return dt.astimezone(tz_actual)
    
    def events_overlap(event1: str, event2: str, tz_obj: str) -> bool:
        """Check if two events overlap in time.
        
        Args:
            event1: First event dict with 'start' and 'end' ISO strings
            event2: Second event dict with 'start' and 'end' ISO strings
            tz_obj: Timezone string for parsing
        """
        try:
            event1_actual = event1 if isinstance(event1, dict) else {}
            event2_actual = event2 if isinstance(event2, dict) else {}
            start1 = parse_datetime(event1_actual["start"], tz_obj)
            end1 = parse_datetime(event1_actual["end"], tz_obj)
            start2 = parse_datetime(event2_actual["start"], tz_obj)
            end2 = parse_datetime(event2_actual["end"], tz_obj)
            return start1 < end2 and start2 < end1
        except Exception:
            return False
    
    def is_email_tasks_event(event: str, tz_obj: str) -> bool:
        """Check if event is "Email & Tasks" (9:00-11:00 AM).
        
        Args:
            event: Event dict
            tz_obj: Timezone string for parsing
        """
        event_actual = event if isinstance(event, dict) else {}
        title = event_actual.get("title", "").lower()
        if "email" not in title or "task" not in title:
            return False
        try:
            start = parse_datetime(event_actual["start"], tz_obj)
            end = parse_datetime(event_actual["end"], tz_obj)
            return start.hour == 9 and end.hour == 11
        except Exception:
            return False
    
    def is_hold_event(event: str) -> bool:
        """Check if event is a "Hold" event.
        
        Args:
            event: Event dict
        """
        event_actual = event if isinstance(event, dict) else {}
        return "hold" in event_actual.get("title", "").lower()
    
    def is_chad_out_event(event: str) -> bool:
        """Check if event is "Chad out".
        
        Args:
            event: Event dict
        """
        event_actual = event if isinstance(event, dict) else {}
        title = event_actual.get("title", "").lower()
        return "chad out" in title or "chad's out" in title
    
    def filter_events(events_list: str, tz_obj: str) -> str:
        """Filter events according to gold-standard rules.
        
        Args:
            events_list: List of normalized event dictionaries
            tz_obj: Timezone string for time parsing
        """
        events_actual = events_list if isinstance(events_list, list) else []
        if not events_actual:
            return []
        tz_actual = pytz.timezone(tz_obj) if isinstance(tz_obj, str) else tz_obj
        email_tasks_events = []
        hold_events = []
        chad_out_events = []
        real_meetings = []
        for event in events_actual:
            if is_email_tasks_event(event, tz_obj):
                email_tasks_events.append(event)
            elif is_hold_event(event):
                hold_events.append(event)
            elif is_chad_out_event(event):
                chad_out_events.append(event)
            else:
                real_meetings.append(event)
        overlapped_email_tasks = set()
        overlapped_holds = set()
        for real_meeting in real_meetings:
            for i, email_task in enumerate(email_tasks_events):
                if events_overlap(real_meeting, email_task, tz_obj):
                    overlapped_email_tasks.add(i)
            for i, hold_event in enumerate(hold_events):
                if events_overlap(real_meeting, hold_event, tz_obj):
                    overlapped_holds.add(i)
        filtered_events = list(real_meetings)
        for i in overlapped_email_tasks:
            filtered_events.append(email_tasks_events[i])
        for i in overlapped_holds:
            filtered_events.append(hold_events[i])
        filtered_events.extend(chad_out_events)
        try:
            filtered_events.sort(key=lambda e: parse_datetime(e["start"], tz_obj))
        except Exception:
            pass
        return filtered_events
    
    def calculate_available_time(events_list: str, now_dt: str, tz_obj: str) -> str:
        """Calculate available time blocks from current time to 5:00 PM.
        
        Args:
            events_list: List of filtered events (already sorted chronologically)
            now_dt: Current datetime
            tz_obj: Timezone string for calculations
        """
        events_actual = events_list if isinstance(events_list, list) else []
        now_actual = now_dt if isinstance(now_dt, datetime) else datetime.now(pytz.timezone(tz_obj) if isinstance(tz_obj, str) else tz_obj)
        tz_actual = pytz.timezone(tz_obj) if isinstance(tz_obj, str) else tz_obj
        today_start = now_actual.replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_time = today_start.replace(hour=17, minute=0)
        if now_actual >= cutoff_time:
            return (0, [])
        today_events = []
        for event in events_actual:
            try:
                event_start = parse_datetime(event["start"], tz_obj)
                event_end = parse_datetime(event["end"], tz_obj)
                if event_start.date() == now_actual.date() and event_end > now_actual:
                    today_events.append({"start": event_start, "end": event_end, "event": event})
            except Exception:
                continue
        today_events.sort(key=lambda e: e["start"])
        available_blocks = []
        current_time = now_actual
        for event_info in today_events:
            event_start = event_info["start"]
            event_end = event_info["end"]
            if current_time < event_start:
                block_end = min(event_start, cutoff_time)
                if block_end > current_time:
                    duration_minutes = int((block_end - current_time).total_seconds() / 60)
                    if duration_minutes > 0:
                        available_blocks.append({"start": current_time, "end": block_end, "duration_minutes": duration_minutes})
            current_time = max(current_time, event_end)
            if current_time >= cutoff_time:
                break
        if current_time < cutoff_time:
            duration_minutes = int((cutoff_time - current_time).total_seconds() / 60)
            if duration_minutes > 0:
                available_blocks.append({"start": current_time, "end": cutoff_time, "duration_minutes": duration_minutes})
        merged_blocks = []
        for block in available_blocks:
            if not merged_blocks:
                merged_blocks.append(block)
            else:
                last_block = merged_blocks[-1]
                if block["start"] <= last_block["end"]:
                    last_block["end"] = block["end"]
                    last_block["duration_minutes"] = int((last_block["end"] - last_block["start"]).total_seconds() / 60)
                else:
                    merged_blocks.append(block)
        total_minutes = sum(block["duration_minutes"] for block in merged_blocks)
        return (total_minutes, merged_blocks)
    
    def format_duration(total_minutes: int) -> str:
        """Format duration as "Xh, Y min".
        
        Args:
            total_minutes: Total minutes
        """
        hours = total_minutes // 60
        minutes = total_minutes % 60
        if hours == 0:
            return f"{minutes} min"
        elif minutes == 0:
            return f"{hours}h"
        else:
            return f"{hours}h, {minutes} min"
    
    def format_time(dt: str) -> str:
        """Format datetime as "H:MM AM/PM".
        
        Args:
            dt: Datetime object
        """
        if isinstance(dt, datetime):
            dt_actual = dt
        else:
            dt_actual = parse_datetime(str(dt), "UTC")
        try:
            return dt_actual.strftime("%-I:%M %p")
        except ValueError:
            return dt_actual.strftime("%I:%M %p").lstrip("0")
    
    def format_event_markdown(event: str, tz_obj: str) -> str:
        """Format a single event as a Markdown bullet point.
        
        Args:
            event: Event dictionary
            tz_obj: Timezone string for time formatting
        """
        try:
            event_actual = event if isinstance(event, dict) else {}
            start = parse_datetime(event_actual["start"], tz_obj)
            end = parse_datetime(event_actual["end"], tz_obj)
            start_str = format_time(start)
            end_str = format_time(end)
            time_range = f"{start_str}–{end_str}"
            title = event_actual.get("title", "")
            attendees = event_actual.get("attendees", [])
            title_lower = title.lower()
            is_solo = (("email" in title_lower and "task" in title_lower) or "hold" in title_lower)
            if attendees:
                attendee_names = []
                for attendee in attendees:
                    if "<" in attendee and ">" in attendee:
                        name = attendee.split("<")[0].strip()
                        if name:
                            attendee_names.append(name)
                        else:
                            email = attendee.split("<")[1].split(">")[0].strip()
                            attendee_names.append(email)
                    else:
                        attendee_names.append(attendee)
                attendee_str = ", ".join(attendee_names)
            else:
                attendee_str = "Chad Dorsey"
            attendee_part = f" (*{attendee_str}*)"
            if is_solo:
                return f"• **{title}**{attendee_part} — *{time_range}*"
            else:
                return f"• **{time_range}** — **{title}**{attendee_part}"
        except Exception:
            return f"• **{event_actual.get('title', 'Unknown Event') if isinstance(event_actual, dict) else 'Unknown Event'}**"
    
    def format_available_time_blocks(blocks: str, tz_obj: str) -> str:
        """Format available time blocks as Markdown list.
        
        Args:
            blocks: List of available time block dicts with start, end, duration_minutes
            tz_obj: Timezone string for time formatting
        """
        blocks_actual = blocks if isinstance(blocks, list) else []
        if not blocks_actual:
            return ""
        lines = []
        for i, block in enumerate(blocks_actual):
            try:
                start = parse_datetime(block["start"], tz_obj) if isinstance(block["start"], str) else block["start"]
                end = parse_datetime(block["end"], tz_obj) if isinstance(block["end"], str) else block["end"]
                start_str = format_time(start)
                end_str = format_time(end)
                duration = block["duration_minutes"]
                if i == 0:
                    duration_str = f"*({duration} min left)*"
                else:
                    duration_str = f"*({duration} min)*"
                lines.append(f"- {start_str} – {end_str} {duration_str}")
            except Exception:
                continue
        return "\n".join(lines)
    
    def format_briefing_markdown(now_dt: str, events_list: str, available_blocks_list: str, total_available_minutes_int: int, tz_obj: str) -> str:
        """Format the complete briefing in Markdown format.
        
        Args:
            now_dt: Current datetime
            events_list: List of filtered events (for today)
            available_blocks_list: List of available time blocks
            total_available_minutes_int: Total available minutes
            tz_obj: Timezone string for formatting
        """
        now_actual = now_dt if isinstance(now_dt, datetime) else datetime.now()
        events_actual = events_list if isinstance(events_list, list) else []
        blocks_actual = available_blocks_list if isinstance(available_blocks_list, list) else []
        tz_actual = pytz.timezone(tz_obj) if isinstance(tz_obj, str) else tz_obj
        try:
            current_time_formatted = format_time(now_actual)
        except ValueError:
            current_time_formatted = now_actual.strftime("%I:%M %p").lstrip("0")
        day_name = now_actual.strftime("%a")
        month_name = now_actual.strftime("%b")
        day_number = now_actual.strftime("%d")
        header = f"# Today's Schedule (updated {day_name}. {month_name} {day_number} at {current_time_formatted})"
        schedule_lines = ["**Today's Schedule**"]
        today_events = []
        for event in events_actual:
            try:
                event_start = parse_datetime(event["start"], tz_obj)
                if event_start.date() == now_actual.date():
                    today_events.append(event)
            except Exception:
                continue
        if today_events:
            for event in today_events:
                schedule_lines.append(format_event_markdown(event, tz_obj))
        else:
            schedule_lines.append("*No meetings scheduled*")
        schedule_section = "\n".join(schedule_lines)
        available_time_formatted = format_duration(total_available_minutes_int)
        available_time_header = f"### Available Time Remaining — **{available_time_formatted}**"
        available_time_blocks_str = format_available_time_blocks(blocks_actual, tz_obj)
        if available_time_blocks_str:
            available_time_section = f"{available_time_header}\n{available_time_blocks_str}"
        else:
            available_time_section = f"{available_time_header}\n*No available time remaining*"
        return f"{header}\n\n{schedule_section}\n\n{available_time_section}"
    
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
        try:
            current_time_formatted = now.strftime("%-I:%M %p")
        except ValueError:
            current_time_formatted = now.strftime("%I:%M %p").lstrip("0")
        
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
            events = asyncio.run(fetch_calendar_events(mcp_client, calendar_id, timezone))
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
        filtered_events = filter_events(events, timezone)
        events_included = len(filtered_events)
        
        # Calculate available time blocks
        total_available_minutes, available_blocks = calculate_available_time(
            filtered_events, now, timezone
        )
        
        # Format briefing in Markdown
        briefing = format_briefing_markdown(
            now, filtered_events, available_blocks, total_available_minutes, timezone
        )
        
        return {
            "status": "ok",
            "briefing": briefing,
            "memory_content": briefing,
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
