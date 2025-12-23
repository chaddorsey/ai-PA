"""
Daily Briefing Tool

Generates a formatted daily schedule briefing with available time calculations
from calendar events retrieved via MCP.
"""

from typing import Dict, Any, Optional


def generate_daily_briefing(
    calendar_id: Optional[str] = None,
    timezone: Optional[str] = None,
    target_date: Optional[str] = None,
    include_troop_meetings: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Generate a daily briefing with formatted schedule and available time calculations.
    
    This tool retrieves calendar events from the specified calendar, filters them
    according to gold-standard rules, calculates available time from 8:00 AM to 
    5:00 PM Eastern, and generates a Markdown-formatted briefing report.
    
    The tool automatically updates the 'current_daily_schedule_and_available_time' 
    memory block with the briefing content. No agent action is needed to update memory.
    
    Args:
        calendar_id: Calendar identifier (email address). Defaults to "cdorsey@concord.org".
        timezone: Timezone for time calculations and display. Defaults to "America/New_York".
        target_date: Date for the briefing in YYYY-MM-DD format. Defaults to today.
        include_troop_meetings: Deprecated - troop meetings are always ignored (not displayed, not counted as busy). Defaults to False.
    
    Returns:
        Dictionary with status, briefing, memory_updated, timestamp, and other metadata.
    """
    # Import required modules inside function for Letta tool extraction
    import traceback
    import re
    import os
    import sys
    import asyncio
    from datetime import datetime, timedelta
    import pytz
    
    # Wrap entire function in try-except to catch any unexpected errors
    try:
        # Set defaults
        if calendar_id is None:
            calendar_id = "cdorsey@concord.org"
        if timezone is None:
            timezone = "America/New_York"
        if include_troop_meetings is None:
            include_troop_meetings = False
        
        # Get current time in specified timezone
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        
        # Parse target_date if provided, otherwise use today
        if target_date:
            try:
                # Parse YYYY-MM-DD format
                target_dt = datetime.strptime(target_date, "%Y-%m-%d")
                target_dt = tz.localize(target_dt.replace(hour=0, minute=0, second=0, microsecond=0))
            except ValueError:
                # Try other common formats
                try:
                    target_dt = datetime.strptime(target_date, "%m/%d/%Y")
                    target_dt = tz.localize(target_dt.replace(hour=0, minute=0, second=0, microsecond=0))
                except ValueError:
                    target_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            target_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Determine if this is for today or another date
        is_today = target_dt.date() == now.date()
        
        # For available time calculation:
        # - Work hours are 8:00 AM to 5:00 PM
        # - If called before 8 AM or for future dates, start at 8:00 AM
        # - If called during work hours, start at current time
        # - If called after 5 PM, start at 8:00 AM (for the target date's schedule)
        work_start = target_dt.replace(hour=8, minute=0, second=0, microsecond=0)
        work_end = target_dt.replace(hour=17, minute=0, second=0, microsecond=0)
        
        if is_today:
            # During work hours: use current time
            # Before work hours: use 8 AM
            # After work hours: use 8 AM (shows full day's available time)
            if now < work_start:
                time_reference = work_start
            elif now > work_end:
                time_reference = work_start  # Show from 8 AM for next day's planning
            else:
                time_reference = now
        else:
            time_reference = work_start  # For future dates, always start at 8 AM
        
        # Format current time for display
        try:
            current_time_formatted = now.strftime("%-I:%M %p")
        except ValueError:
            current_time_formatted = now.strftime("%I:%M %p").lstrip("0")
        
        # Format target date for display (the schedule being shown)
        target_day_name = target_dt.strftime("%a")  # Short day name for schedule
        target_month_name = target_dt.strftime("%b")
        try:
            target_day_number = target_dt.strftime("%-d")
        except ValueError:
            target_day_number = str(target_dt.day)
        
        # Format current date for "updated" timestamp (when the report was generated)
        update_month_name = now.strftime("%b")
        try:
            update_day_number = now.strftime("%-d")
        except ValueError:
            update_day_number = str(now.day)
        
        # Add parent directory to path for imports
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Import MCP client from scheduling orchestrator
        try:
            from scheduling_orchestrator.mcp_client import MCPCalendarClient, MCPError
        except ImportError:
            MCPCalendarClient = None
            MCPError = Exception
        
        # Initialize MCP client if available
        if MCPCalendarClient is None:
            return {
                "status": "error",
                "briefing": "",
                "instructions": "An error occurred. Do not update memory.",
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
        
        # ========== FETCH CALENDAR EVENTS ==========
        # Fetch a window around the target date
        day_before_start = target_dt - timedelta(days=1)
        day_after_end = target_dt + timedelta(days=2)
        after_date_iso = day_before_start.astimezone(pytz.UTC).strftime("%Y-%m-%dT00:00:00Z")
        before_date_iso = day_after_end.astimezone(pytz.UTC).strftime("%Y-%m-%dT23:59:59Z")
        
        # Use inline async execution
        try:
            async def _async_fetch():
                if not mcp_client._initialized:
                    await mcp_client.initialize()
                return await mcp_client.get_core_event_data(
                    calendar_id=calendar_id,
                    before=before_date_iso,
                    after=after_date_iso
                )
            raw_events = asyncio.run(_async_fetch())
        except Exception as e:
            return {
                "status": "error",
                "briefing": "",
                "instructions": "An error occurred. Do not update memory.",
                "timestamp": now.isoformat(),
                "current_time_eastern": current_time_formatted,
                "error_message": f"Error fetching calendar events: {str(e)}",
                "events_retrieved": 0
            }
        
        # ========== INLINE HELPERS (using lambdas to avoid def statements) ==========
        
        # Aggressive sanitization - removes ALL formatting artifacts
        _sanitize = lambda s: re.sub(r'\s+', ' ', re.sub(r'\s*\.\s*', '.', re.sub(r'\s*@\s*', '@', re.sub(r'[\*\n\r\t]+', '', str(s).replace('\n', ' ').replace('\r', ' ') if s else '')))).strip() if s else ''
        
        # Clean string alias
        _clean_str = _sanitize
        
        # ========== NAME LOOKUP TABLE ==========
        # Concord Staff and contacts - email to full name mapping
        _name_lookup = {
            # Concord Staff
            "emcelroy@concord.org": "Ethan McElroy",
            "kswenson@concord.org": "Kirk Swenson",
            "scytacki@concord.org": "Scott Cytacki",
            "phorwitz@concord.org": "Paul Horwitz",
            "hlee@concord.org": "Hee-Sun Lee",
            "tlord@concord.org": "Trudi Lord",
            "ddamelin@concord.org": "Dan Damelin",
            "jraiff@concord.org": "Judi Raiff",
            "cmcintyre@concord.org": "Cynthia McIntyre",
            "wfinzer@concord.org": "Bill Finzer",
            "kbrown@concord.org": "Kiley Brown",
            "lbondaryk@concord.org": "Leslie Bondaryk",
            "jchao@concord.org": "Jie Chao",
            "apallant@concord.org": "Amy Pallant",
            "clore@concord.org": "Chris Lore",
            "kmiller@concord.org": "Kate Miller",
            "kjesseneller@concord.org": "Kathy Jessen Eller",
            "rellis@concord.org": "Rebecca Ellis",
            "tfristoe@concord.org": "Teale Fristoe",
            "lbuoncuore@concord.org": "Lisa Buoncuore",
            "dkehoe@concord.org": "Danielle Kehoe",
            "sbrau@concord.org": "Sue Brau",
            "dmartin@concord.org": "Doug Martin",
            "lstephens@concord.org": "Lynn Stephens",
            "mtirenin@concord.org": "Michael Tirenin",
            "awagh@concord.org": "Aditi Wagh",
            # Family
            "sophiadorsey@gmail.com": "Sophia Dorsey",
            "sdorsey@oberlin.edu": "Sophia Dorsey",
            "liamdorsey00@gmail.com": "Liam Dorsey",
            "lizdorsey@gmail.com": "Liz Dorsey",
            "cdorsey@concord.org": "Chad Dorsey",
            "chaddorsey@gmail.com": "Chad Dorsey",
        }
        
        # Get name from email - first check lookup table, then try display name, then derive
        _get_name = lambda email, display_name=None: (
            # Priority 1: Lookup table
            _name_lookup.get(email.lower().strip(), None) if email else None
        ) or (
            # Priority 2: Display name from event (if provided and not just the email)
            _sanitize(display_name) if display_name and "@" not in display_name and display_name != email else None
        ) or (
            # Priority 3: Derive from email
            (lambda u: (
                ' '.join(word.capitalize() for word in u.replace('.', ' ').replace('_', ' ').replace('-', ' ').split() if word)
                if ('.' in u or '_' in u or '-' in u) else
                (f"{u[0].upper()} {u[1:].capitalize()}" if (len(u) > 2 and u[0].islower()) else
                (u.capitalize() if u else ""))
            ))(re.sub(r'[0-9]+', '', (email.split('@')[0] if '@' in str(email) else str(email)))) if email else ""
        )
        
        # Check if %-I format is supported (Linux vs macOS difference)
        _use_dash_format = True
        try:
            now.strftime("%-I:%M %p")
        except ValueError:
            _use_dash_format = False
        
        # Format time helper - ALWAYS produces clean "H:MM AM/PM" format from datetime
        # This should NEVER have spaces in the output since it uses strftime
        # Added type check to ensure we only call strftime on datetime objects
        _format_time_str = lambda dt: (
            (dt.strftime("%-I:%M %p") if _use_dash_format else dt.strftime("%I:%M %p").lstrip("0"))
            if dt and hasattr(dt, 'strftime') else ""
        )
        
        # Normalize events
        normalized_events = []
        for evt in raw_events:
            start_data = evt.get("start", {})
            end_data = evt.get("end", {})
            # Skip all-day events
            if "date" in start_data:
                continue
            start_dt_str = start_data.get("dateTime")
            end_dt_str = end_data.get("dateTime")
            if not start_dt_str or not end_dt_str:
                continue
            
            # Clean the title
            title = _clean_str(evt.get("summary", ""))
            
            # Process attendees
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
                        name = _clean_str(attendee.get("name", ""))
                        email = _clean_str(attendee.get("email", ""))
                        if name and email:
                            attendees.append({"name": name, "email": email})
                        elif email:
                            attendees.append({"name": "", "email": email})
                        elif name:
                            attendees.append({"name": name, "email": ""})
            if not attendees and attendees_list:
                for a in attendees_list:
                    if a:
                        cleaned = _clean_str(str(a))
                        if cleaned:
                            attendees.append({"name": "", "email": cleaned})
            
            normalized_events.append({
                "id": evt.get("id", ""),
                "title": title,
                "start": start_dt_str,
                "end": end_dt_str,
                "attendees": attendees
            })
        
        events_retrieved = len(normalized_events)
        
        # ========== PARSE DATETIMES ==========
        parsed_dt_cache = {}
        
        for event in normalized_events:
            event_id = event.get("id") or id(event)
            for field in ["start", "end"]:
                dt_str = event.get(field)
                if dt_str:
                    try:
                        try:
                            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                        except ValueError:
                            dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S%z")
                        if dt.tzinfo is None:
                            dt = pytz.UTC.localize(dt)
                        parsed_dt_cache[(event_id, field)] = dt.astimezone(tz)
                    except:
                        parsed_dt_cache[(event_id, field)] = None
        
        # ========== FILTER EVENTS ==========
        email_tasks_events = []
        hold_events = []
        weekly_review_events = []
        chad_out_events = []
        troop_events = []
        real_meetings = []
        
        for event in normalized_events:
            event_id = event.get("id") or id(event)
            title = event.get("title", "").lower()
            start_dt = parsed_dt_cache.get((event_id, "start"))
            end_dt = parsed_dt_cache.get((event_id, "end"))
            
            # Skip events not on target date
            if start_dt and start_dt.date() != target_dt.date():
                continue
            
            # Check if Email & Tasks (9:00-11:00 AM)
            is_email_tasks = False
            if "email" in title and "task" in title:
                if start_dt and end_dt:
                    if start_dt.hour == 9 and end_dt.hour == 11:
                        is_email_tasks = True
            
            # Check if Hold event
            is_hold = "hold" in title
            
            # Check if Weekly Review event (solo-available like Email & Tasks and Hold)
            is_weekly_review = "weekly review" in title
            
            # Check if Chad out
            is_chad_out = "chad out" in title or "chad's out" in title
            
            # Check if Troop meeting
            is_troop = "troop" in title
            
            if is_email_tasks:
                email_tasks_events.append((event, event_id, start_dt, end_dt))
            elif is_hold:
                hold_events.append((event, event_id, start_dt, end_dt))
            elif is_weekly_review:
                weekly_review_events.append((event, event_id, start_dt, end_dt))
            elif is_chad_out:
                chad_out_events.append((event, event_id, start_dt, end_dt))
            elif is_troop:
                troop_events.append((event, event_id, start_dt, end_dt))
            else:
                real_meetings.append((event, event_id, start_dt, end_dt))
        
        # Find overlapped email/tasks and holds
        overlapped_email_tasks = set()
        overlapped_holds = set()
        
        for rm_event, rm_id, rm_start, rm_end in real_meetings:
            if rm_start is None or rm_end is None:
                continue
            # Check overlaps with email/tasks
            for i, (et_event, et_id, et_start, et_end) in enumerate(email_tasks_events):
                if et_start is None or et_end is None:
                    continue
                if rm_start < et_end and et_start < rm_end:
                    overlapped_email_tasks.add(i)
            # Check overlaps with holds
            for i, (h_event, h_id, h_start, h_end) in enumerate(hold_events):
                if h_start is None or h_end is None:
                    continue
                if rm_start < h_end and h_start < rm_end:
                    overlapped_holds.add(i)
        
        # Build filtered events list
        # Include: real meetings, chad_out, Email & Tasks, Hold, and optionally troop
        filtered_events_with_times = []
        for event, event_id, start_dt, end_dt in real_meetings:
            if start_dt:
                filtered_events_with_times.append((event, start_dt, end_dt, "meeting"))
        for event, event_id, start_dt, end_dt in chad_out_events:
            if start_dt:
                filtered_events_with_times.append((event, start_dt, end_dt, "chad_out"))
        
        # Include Email & Tasks, Hold, and Weekly Review as solo events (displayed with italics)
        # These count as AVAILABLE time unless overlapped by real meetings
        for event, event_id, start_dt, end_dt in email_tasks_events:
            if start_dt:
                filtered_events_with_times.append((event, start_dt, end_dt, "solo_available"))
        for event, event_id, start_dt, end_dt in hold_events:
            if start_dt:
                filtered_events_with_times.append((event, start_dt, end_dt, "solo_available"))
        for event, event_id, start_dt, end_dt in weekly_review_events:
            if start_dt:
                filtered_events_with_times.append((event, start_dt, end_dt, "solo_available"))
        
        # Troop meetings are completely ignored - not displayed, not counted as busy
        # (include_troop_meetings parameter is kept for backward compatibility but has no effect)
        
        # Sort by start time
        filtered_events_with_times.sort(key=lambda x: x[1] if x[1] else datetime.max.replace(tzinfo=tz))
        
        events_included = len(filtered_events_with_times)
        
        # ========== CALCULATE AVAILABLE TIME ==========
        # Busy events that block available time:
        # - Real meetings (always busy)
        # - Chad out (always busy)
        # 
        # NOT busy (still available):
        # - Email & Tasks (solo time, available unless overlapped)
        # - Hold (solo time, available unless overlapped)
        # - Weekly Review (solo time, available unless overlapped)
        # - Troop meetings (completely ignored - treated as if they don't exist)
        all_busy_events = []
        for event, event_id, start_dt, end_dt in real_meetings:
            if start_dt and end_dt:
                all_busy_events.append({"start": start_dt, "end": end_dt})
        for event, event_id, start_dt, end_dt in chad_out_events:
            if start_dt and end_dt:
                all_busy_events.append({"start": start_dt, "end": end_dt})
        # NOTE: Email & Tasks, Holds, Weekly Review, and Troop meetings are NOT included - they count as available time or are ignored
        
        # Filter to target date only
        today_busy = [e for e in all_busy_events if e["start"].date() == target_dt.date()]
        today_busy.sort(key=lambda e: e["start"])
        
        cutoff_time = target_dt.replace(hour=17, minute=0)
        
        if time_reference >= cutoff_time:
            total_available_minutes = 0
            available_blocks = []
        else:
            # Filter to events after time_reference
            today_busy = [e for e in today_busy if e["end"] > time_reference]
            
            # Find available blocks
            available_blocks = []
            current_time = time_reference
            for event_info in today_busy:
                event_start = event_info["start"]
                event_end = event_info["end"]
                if current_time < event_start:
                    block_end = min(event_start, cutoff_time)
                    if block_end > current_time:
                        duration_minutes = int((block_end - current_time).total_seconds() / 60)
                        if duration_minutes > 0:
                            available_blocks.append({
                                "start": current_time,
                                "end": block_end,
                                "duration_minutes": duration_minutes
                            })
                current_time = max(current_time, event_end)
                if current_time >= cutoff_time:
                    break
            
            # Add remaining time until 5 PM
            if current_time < cutoff_time:
                duration_minutes = int((cutoff_time - current_time).total_seconds() / 60)
                if duration_minutes > 0:
                    available_blocks.append({
                        "start": current_time,
                        "end": cutoff_time,
                        "duration_minutes": duration_minutes
                    })
            
            # Merge adjacent blocks
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
            
            available_blocks = merged_blocks
            total_available_minutes = sum(b["duration_minutes"] for b in available_blocks)
        
        # ========== FORMAT BRIEFING ==========
        # Format duration for available time
        hours = total_available_minutes // 60
        minutes = total_available_minutes % 60
        if hours == 0:
            available_time_formatted = f"{minutes} min"
        elif minutes == 0:
            available_time_formatted = f"{hours}h"
        else:
            available_time_formatted = f"{hours}h, {minutes} min"
        
        # Get day name for header (e.g., "Thursday's Schedule")
        full_day_name = target_dt.strftime("%A")  # Full day name like "Thursday"
        
        # Build header: "**Saturday's Schedule** (updated Dec. 12 at 7:00 PM)"
        # - Day name comes from target_dt (the schedule being shown)
        # - "updated" date/time comes from now (when the report was generated)
        header = f"**{full_day_name}'s Schedule** (updated {update_month_name}. {update_day_number} at {current_time_formatted})"
        
        # Schedule section - meetings are bulleted below the header
        schedule_lines = []
        
        if filtered_events_with_times:
            for event, start_dt, end_dt, event_type in filtered_events_with_times:
                try:
                    # Format times - these MUST be datetime objects from parsed cache
                    start_str = _format_time_str(start_dt) if start_dt else ""
                    end_str = _format_time_str(end_dt) if end_dt else ""
                    
                    # Skip if times couldn't be formatted
                    if not start_str or not end_str:
                        continue
                    
                    # Time range is always bolded
                    time_range = f"**{start_str}–{end_str}**"
                    title = str(event.get("title", "") or "")
                    attendees = event.get("attendees", []) or []
                    
                    # Format attendees - use lookup table, then display name, then derive
                    attendee_names = []
                    attendee_emails = []
                    for att in attendees:
                        try:
                            if not isinstance(att, dict):
                                continue
                            display_name = _sanitize(str(att.get("name", "") or ""))
                            email = _sanitize(str(att.get("email", "") or "")).lower()
                            
                            if email:
                                attendee_emails.append(email)
                            
                            # Use _get_name which checks lookup table first
                            resolved_name = _get_name(email, display_name)
                            if resolved_name:
                                attendee_names.append(resolved_name)
                        except:
                            continue
                    
                    # Check if this is a solo meeting (only Chad as attendee)
                    chad_emails = ["cdorsey@concord.org", "chaddorsey@gmail.com"]
                    non_chad_emails = [e for e in attendee_emails if e not in chad_emails]
                    is_solo_meeting = len(non_chad_emails) == 0
                    
                    # Remove duplicates, Chad, and room names from display
                    seen = set()
                    unique_attendees = []
                    for name in attendee_names:
                        try:
                            cleaned_name = _sanitize(name)
                            name_lower = cleaned_name.lower()
                            # Skip Chad, room names, and generic entries
                            if (cleaned_name and 
                                name_lower not in seen and 
                                "chad" not in name_lower and
                                not name_lower.startswith("(") and
                                "zoom" not in name_lower and
                                "cottage" not in name_lower and
                                "conference" not in name_lower and
                                "room" not in name_lower and
                                "café" not in name_lower and
                                "cafe" not in name_lower and
                                "employees" not in name_lower):
                                seen.add(name_lower)
                                unique_attendees.append(cleaned_name)
                        except:
                            continue
                    
                    # Limit display to 5 attendees max
                    if len(unique_attendees) > 5:
                        attendee_str = ", ".join(unique_attendees[:5]) + f", +{len(unique_attendees) - 5} more"
                    elif unique_attendees:
                        attendee_str = ", ".join(unique_attendees)
                    else:
                        attendee_str = ""
                    
                    # Clean title for display (remove any stray markdown)
                    clean_title = _clean_str(title)
                    
                    # Format based on event type and attendees
                    # - Chad out events: title in italics with (busy)
                    # - Solo available events (Email & Tasks, Hold): title in italics
                    # - Solo meetings (only Chad): title in italics
                    # - Meetings with others: title in bold, attendees in italicized parens
                    if event_type == "chad_out":
                        schedule_lines.append(f"• {time_range} — *{clean_title}* (busy)")
                    elif event_type == "solo_available":
                        # Email & Tasks, Hold - displayed as solo events with italics
                        schedule_lines.append(f"• {time_range} — *{clean_title}*")
                    elif is_solo_meeting:
                        # Solo meeting - title in italics
                        schedule_lines.append(f"• {time_range} — *{clean_title}*")
                    elif attendee_str:
                        # Meeting with others - title in bold, attendees in italicized parens
                        schedule_lines.append(f"• {time_range} — **{clean_title}** *({attendee_str})*")
                    else:
                        # Meeting with others but no displayable attendees
                        schedule_lines.append(f"• {time_range} — **{clean_title}**")
                except Exception as evt_err:
                    # Skip problematic events but note them
                    schedule_lines.append(f"• (Error processing event: {str(evt_err)[:50]})")
        else:
            schedule_lines.append("*No meetings scheduled*")
        
        schedule_section = "\n".join(schedule_lines)
        
        # Build available time section
        # Format: "**Available Time Remaining** — 2h, 15 min remaining"
        #         "• **8:00 AM-9:00 AM** - (1h)"
        
        try:
            available_time_lines = []
            # Header is bold with em dash
            available_time_lines.append(f"**Available Time Remaining** — {available_time_formatted} remaining")
            
            if available_blocks:
                for block in available_blocks:
                    try:
                        block_start = block.get("start")
                        block_end = block.get("end")
                        duration = block.get("duration_minutes", 0)
                        
                        block_start_str = _format_time_str(block_start) if block_start else ""
                        block_end_str = _format_time_str(block_end) if block_end else ""
                        
                        if not block_start_str or not block_end_str:
                            continue
                        
                        # Format duration for block
                        block_hours = duration // 60
                        block_mins = duration % 60
                        if block_hours == 0:
                            dur_str = f"{block_mins} min"
                        elif block_mins == 0:
                            dur_str = f"{block_hours}h"
                        else:
                            dur_str = f"{block_hours}h {block_mins} min"
                        
                        # Time slots are bulleted with bold times
                        available_time_lines.append(f"• **{block_start_str}–{block_end_str}** - ({dur_str})")
                    except:
                        continue
            else:
                available_time_lines.append("*No available time blocks*")
            
            available_time_section = "\n".join(available_time_lines)
        except Exception as avail_err:
            available_time_section = f"**Available Time Remaining** — error calculating"
        
        # Combine into briefing
        briefing = f"{header}\n\n{schedule_section}\n\n{available_time_section}"
        
        # Wrap in VERBATIM tags so the agent passes it through unchanged
        verbatim_briefing = f"[VERBATIM_USER_OUTPUT]\n{briefing}\n[/VERBATIM_USER_OUTPUT]"
        
        # ========== DIRECTLY UPDATE MEMORY BLOCK ==========
        # Update the memory block programmatically instead of relying on the agent
        memory_block_id = "block-28c6e49e-e2bf-4682-8b0c-68623fcee0c7"
        memory_updated = False
        memory_error = None
        
        try:
            # Use localhost:8283 directly - tools run inside the Letta container
            # Use urllib.request to match the pattern used in other Letta scripts
            # Use /v1/blocks/{block_id} endpoint (works reliably)
            letta_url = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
            
            import urllib.request
            import urllib.error
            import json as json_lib
            
            url = f"{letta_url}/v1/blocks/{memory_block_id}"
            data = json_lib.dumps({"value": briefing}).encode('utf-8')
            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='PATCH'
            )
            # Use 30 second timeout to match other Letta scripts
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    memory_updated = True
        except urllib.error.HTTPError as http_err:
            # Handle HTTP errors (4xx, 5xx) with status code and error body
            try:
                error_body = http_err.read().decode('utf-8')
                memory_error = f"HTTP {http_err.code}: {error_body[:200]}"
            except:
                memory_error = f"HTTP {http_err.code}: {str(http_err)}"
        except urllib.error.URLError as url_err:
            # Handle URL/connection errors (connection refused, timeout, etc.)
            error_reason = str(url_err.reason) if hasattr(url_err, 'reason') else str(url_err)
            memory_error = f"Connection error: {error_reason}"
        except Exception as mem_err:
            # Handle any other unexpected errors
            memory_error = f"{type(mem_err).__name__}: {str(mem_err)}"
        
        # Build agent instruction based on memory update status
        if memory_updated:
            agent_note = (
                "MEMORY ALREADY UPDATED: The current_daily_schedule_and_available_time block "
                "has been automatically updated by this tool. DO NOT call memory_rethink, "
                "memory_replace, memory_insert, or memory_finish_edits. Simply display the "
                "briefing to the user."
            )
        else:
            agent_note = (
                f"MEMORY UPDATE FAILED: {memory_error}. You may need to manually update "
                "the current_daily_schedule_and_available_time block."
            )
        
        return {
            "status": "ok",
            "agent_note": agent_note,
            "briefing": verbatim_briefing,
            "memory_updated": memory_updated,
            "memory_block_id": memory_block_id if memory_updated else None,
            "memory_error": memory_error,
            "timestamp": now.isoformat(),
            "target_date": target_dt.strftime("%Y-%m-%d"),
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
        # Safe error handling
        try:
            import pytz
            from datetime import datetime
            error_timestamp = datetime.now(pytz.timezone("America/New_York")).isoformat()
        except:
            from datetime import datetime as dt
            error_timestamp = dt.now().isoformat()
        return {
            "status": "error",
            "agent_note": "Tool failed. DO NOT attempt to update memory.",
            "briefing": "",
            "memory_updated": False,
            "memory_error": "Tool execution failed before memory update",
            "timestamp": error_timestamp,
            "current_time_eastern": "",
            "error_message": f"Error generating daily briefing: {str(e)}\n{traceback.format_exc()}"
        }
