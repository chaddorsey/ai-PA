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
        
        # TODO: Implement calendar event retrieval (task 24-3)
        # TODO: Implement event filtering (task 24-4)
        # TODO: Implement available time calculation (task 24-5)
        # TODO: Implement Markdown formatting (task 24-6)
        
        # Placeholder return structure
        briefing = f"""# Today's Schedule (updated {day_name}. {month_name} {day_number} at {current_time_formatted})

**Today's Schedule**
*No events retrieved yet - implementation in progress*

### Available Time Remaining — **0h, 0 min**
*Time calculation in progress*
"""
        
        return {
            "status": "ok",
            "briefing": briefing,
            "memory_content": briefing,
            "timestamp": now.isoformat(),
            "current_time_eastern": current_time_formatted,
            "events_retrieved": 0,
            "events_included": 0
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

