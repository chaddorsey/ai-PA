"""Natural language schedule parser with Eastern Time defaults."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Dict, Optional
from zoneinfo import ZoneInfo

import dateparser
from dateutil.relativedelta import relativedelta

# Eastern Time zone
ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


class ScheduleParseError(Exception):
    """Error parsing schedule expression."""

    def __init__(self, expression: str, reason: str):
        self.expression = expression
        self.reason = reason
        super().__init__(f"Could not parse '{expression}': {reason}")


def parse_schedule(when: str, timezone: str = "America/New_York") -> Dict:
    """
    Parse natural language schedule expression into structured format.

    Args:
        when: Natural language time expression
        timezone: IANA timezone name (defaults to Eastern Time)

    Returns:
        Dictionary with keys:
        - type: "cron", "interval", or "one_off"
        - expression: Schedule expression (varies by type)
        - next_run_at: Next execution time (UTC)
        - original_timezone: Input timezone

    Examples:
        "in 30 minutes" → one_off, now + 30m
        "tomorrow at 9am" → one_off, tomorrow 09:00
        "every day at 8am" → cron: "0 8 * * *"
        "every Monday at 5pm" → cron: "0 17 * * 1"
        "every 2 hours" → interval: 7200 seconds
        "every weekday at 9am" → cron: "0 9 * * 1-5"
    """
    when = when.strip().lower()
    tz = ZoneInfo(timezone)

    # Pattern: "every X minutes/hours/days"
    interval_match = re.match(r"every (\d+)\s*(minute|hour|day)s?", when)
    if interval_match:
        amount = int(interval_match.group(1))
        unit = interval_match.group(2)
        seconds = amount * {"minute": 60, "hour": 3600, "day": 86400}[unit]

        return {
            "type": "interval",
            "expression": {"seconds": seconds},
            "next_run_at": datetime.now(UTC) + timedelta(seconds=seconds),
            "original_timezone": timezone,
        }

    # Pattern: "every hour" (without number)
    if when in ["every hour", "hourly"]:
        return {
            "type": "interval",
            "expression": {"seconds": 3600},
            "next_run_at": datetime.now(UTC) + timedelta(hours=1),
            "original_timezone": timezone,
        }

    if when in ["every minute"]:
        return {
            "type": "interval",
            "expression": {"seconds": 60},
            "next_run_at": datetime.now(UTC) + timedelta(minutes=1),
            "original_timezone": timezone,
        }

    # Pattern: "every day at 9am"
    daily_match = re.match(r"every day at (\d+):?(\d{2})?\s*(am|pm)?", when)
    if daily_match:
        hour = int(daily_match.group(1))
        minute = int(daily_match.group(2) or 0)
        meridiem = daily_match.group(3)

        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0

        # Cron: minute hour * * *
        cron_expr = f"{minute} {hour} * * *"
        next_run = _calculate_next_cron_run(cron_expr, tz)

        return {
            "type": "cron",
            "expression": {"cron": cron_expr, "timezone": timezone},
            "next_run_at": next_run,
            "original_timezone": timezone,
        }

    # Pattern: "every Monday/Tuesday/etc at 5pm"
    weekday_match = re.match(
        r"every (monday|tuesday|wednesday|thursday|friday|saturday|sunday) at (\d+):?(\d{2})?\s*(am|pm)?",
        when,
    )
    if weekday_match:
        weekday_name = weekday_match.group(1)
        hour = int(weekday_match.group(2))
        minute = int(weekday_match.group(3) or 0)
        meridiem = weekday_match.group(4)

        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0

        weekday_num = {
            "monday": 1,
            "tuesday": 2,
            "wednesday": 3,
            "thursday": 4,
            "friday": 5,
            "saturday": 6,
            "sunday": 0,
        }[weekday_name]

        # Cron: minute hour * * day_of_week
        cron_expr = f"{minute} {hour} * * {weekday_num}"
        next_run = _calculate_next_cron_run(cron_expr, tz)

        return {
            "type": "cron",
            "expression": {"cron": cron_expr, "timezone": timezone},
            "next_run_at": next_run,
            "original_timezone": timezone,
        }

    # Pattern: "every weekday at 9am"
    weekday_pattern = re.match(r"every weekday at (\d+):?(\d{2})?\s*(am|pm)?", when)
    if weekday_pattern:
        hour = int(weekday_pattern.group(1))
        minute = int(weekday_pattern.group(2) or 0)
        meridiem = weekday_pattern.group(3)

        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0

        # Cron: minute hour * * 1-5 (Monday-Friday)
        cron_expr = f"{minute} {hour} * * 1-5"
        next_run = _calculate_next_cron_run(cron_expr, tz)

        return {
            "type": "cron",
            "expression": {"cron": cron_expr, "timezone": timezone},
            "next_run_at": next_run,
            "original_timezone": timezone,
        }

    # Pattern: "in X minutes/hours/days"
    relative_match = re.match(r"in (\d+)\s*(minute|hour|day)s?", when)
    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2)
        delta = timedelta(**{f"{unit}s": amount})
        run_at = datetime.now(UTC) + delta

        return {
            "type": "one_off",
            "expression": {"run_at": run_at.isoformat()},
            "next_run_at": run_at,
            "original_timezone": timezone,
        }

    # Try dateparser for absolute dates/times
    parsed = dateparser.parse(
        when,
        settings={
            "TIMEZONE": timezone,
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
        },
    )

    if parsed:
        # Convert to UTC
        run_at_utc = parsed.astimezone(UTC)

        # Determine if this is recurring or one-off
        # If it includes "every", it's recurring
        if "every" in when:
            # Try to infer cron pattern
            # This is a fallback - we may need more sophisticated parsing
            raise ScheduleParseError(when, "Could not determine cron pattern for recurring expression")

        return {
            "type": "one_off",
            "expression": {"run_at": run_at_utc.isoformat()},
            "next_run_at": run_at_utc,
            "original_timezone": timezone,
        }

    # If we get here, we couldn't parse it
    raise ScheduleParseError(when, "Unrecognized schedule format")


def _calculate_next_cron_run(cron_expr: str, tz: ZoneInfo) -> datetime:
    """Calculate next run time for cron expression."""
    from apscheduler.triggers.cron import CronTrigger

    trigger = CronTrigger.from_crontab(cron_expr, timezone=tz)
    now = datetime.now(tz)
    next_run = trigger.get_next_fire_time(None, now)

    if next_run is None:
        # Fallback: use current time + 1 day
        next_run = now + timedelta(days=1)

    return next_run.astimezone(UTC)


def format_for_display(dt_utc: datetime, show_utc: bool = False) -> str:
    """
    Format UTC datetime for display.

    Args:
        dt_utc: UTC datetime
        show_utc: If True, show in UTC. If False, show in Eastern Time.

    Returns:
        Formatted string
    """
    if show_utc:
        return dt_utc.strftime("%Y-%m-%d %I:%M %p UTC")
    else:
        dt_et = dt_utc.astimezone(ET)
        return dt_et.strftime("%Y-%m-%d %I:%M %p ET")


def validate_timezone(timezone: str) -> bool:
    """Validate that timezone is a valid IANA timezone name."""
    try:
        ZoneInfo(timezone)
        return True
    except Exception:
        return False

