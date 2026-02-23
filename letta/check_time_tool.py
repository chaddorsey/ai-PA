"""
Check Time Tool for Letta

Simple, reliable time-checking tool that runs locally with no external API
dependencies. Replaces the n8n-hosted Check_Time MCP tool which depended on
worldtimeapi.org (unreliable).

Tool: check_current_time
"""

from typing import Dict, Any


def check_current_time() -> Dict[str, Any]:
    """
    Get the current date and time in Eastern Time (America/New_York).

    Returns the current time with full timezone awareness, including
    whether DST is active. No external API calls — uses the local
    system clock with pytz for timezone conversion.

    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - datetime_iso: Full ISO 8601 datetime string with timezone offset
        - date: Date in YYYY-MM-DD format
        - time: Time in HH:MM:SS format (24-hour)
        - time_12h: Time in h:MM AM/PM format
        - day_of_week: Full day name (e.g., "Monday")
        - timezone: Timezone abbreviation (EST or EDT)
        - utc_offset: UTC offset string (e.g., "-05:00")
        - is_dst: Whether daylight saving time is currently active
        - unix_timestamp: Unix epoch seconds
        - error_message: Error details if status is "error"
    """
    import traceback
    from datetime import datetime
    import pytz

    try:
        tz = pytz.timezone("America/New_York")
        now = datetime.now(tz)

        return {
            "status": "ok",
            "datetime_iso": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "time_12h": now.strftime("%-I:%M %p"),
            "day_of_week": now.strftime("%A"),
            "timezone": now.strftime("%Z"),
            "utc_offset": now.strftime("%z")[:3] + ":" + now.strftime("%z")[3:],
            "is_dst": bool(now.dst()),
            "unix_timestamp": int(now.timestamp()),
            "error_message": "",
        }

    except Exception as e:
        return {
            "status": "error",
            "datetime_iso": "",
            "date": "",
            "time": "",
            "time_12h": "",
            "day_of_week": "",
            "timezone": "",
            "utc_offset": "",
            "is_dst": False,
            "unix_timestamp": 0,
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
