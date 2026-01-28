"""
Identity-based working hours integration for scheduling tools.

This module fetches working hours from Letta identities and converts them
to the slot-based format used by the scheduling orchestrator.

Schema for identity working_hours property:
{
    "monday": {"start": "09:00", "end": "17:00"},
    "tuesday": {"start": "09:00", "end": "17:00"},
    ...
    "friday": {"start": "09:00", "end": "12:00"},  # Half day
    "saturday": null,
    "sunday": null
}
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import pytz
import requests

logger = logging.getLogger(__name__)

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Day name to weekday number mapping (Monday = 0)
DAY_TO_WEEKDAY = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def fetch_identity_by_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Fetch identity from Letta by email (identifier_key).

    Args:
        email: Email address (e.g., "wfinzer@concord.org")

    Returns:
        Identity dict or None if not found
    """
    try:
        response = requests.get(f"{LETTA_BASE_URL}/v1/identities/", timeout=30)
        response.raise_for_status()
        identities = response.json()

        for identity in identities:
            if identity.get("identifier_key") == email:
                return identity
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch identity for {email}: {e}")
        return None


def get_identity_property(identity: Dict[str, Any], key: str) -> Optional[str]:
    """Get a property value from an identity."""
    properties = identity.get("properties") or []
    for prop in properties:
        if isinstance(prop, dict) and prop.get("key") == key:
            return prop.get("value")
    return None


def parse_identity_working_hours(identity: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Parse working hours from a Letta identity.

    Args:
        identity: Letta identity dict

    Returns:
        Tuple of (working_hours_dict, timezone_str)
        working_hours_dict has format: {"monday": {"start": "09:00", "end": "17:00"}, ...}
        Returns (None, default_timezone) if no working hours set
    """
    # Get timezone (default to Eastern)
    timezone = get_identity_property(identity, "timezone") or "America/New_York"

    # Get working hours JSON
    working_hours_str = get_identity_property(identity, "working_hours")

    if not working_hours_str:
        return None, timezone

    try:
        working_hours = json.loads(working_hours_str)
        return working_hours, timezone
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse working_hours JSON: {e}")
        return None, timezone


def convert_working_hours_to_slots(
    working_hours: Dict[str, Any],
    timezone_str: str,
    from_date_utc: datetime,
    to_date_utc: datetime,
    slot_size_minutes: int = 15
) -> Set[int]:
    """
    Convert identity working hours to slot indices.

    Args:
        working_hours: Dict with day names -> {"start": "HH:MM", "end": "HH:MM"} or null
        timezone_str: IANA timezone string
        from_date_utc: Start of time range (UTC)
        to_date_utc: End of time range (UTC)
        slot_size_minutes: Size of each slot in minutes (default 15)

    Returns:
        Set of slot indices representing working hours
    """
    try:
        from .slot_indexer import SlotIndexer
    except ImportError:
        from slot_indexer import SlotIndexer

    tz = pytz.timezone(timezone_str)
    slot_indexer = SlotIndexer(from_date_utc, to_date_utc)
    work_slots = set()

    for day_name, hours in working_hours.items():
        if hours is None:
            continue

        weekday = DAY_TO_WEEKDAY.get(day_name.lower())
        if weekday is None:
            continue

        try:
            start_time = hours.get("start", "09:00")
            end_time = hours.get("end", "17:00")

            start_hour, start_min = map(int, start_time.split(":"))
            end_hour, end_min = map(int, end_time.split(":"))
        except (ValueError, AttributeError):
            logger.warning(f"Invalid hours format for {day_name}: {hours}")
            continue

        # Iterate through each day in range
        current_date = from_date_utc
        while current_date < to_date_utc:
            # Convert to local timezone to check weekday
            current_date_local = current_date.astimezone(tz)

            if current_date_local.weekday() == weekday:
                # Create work hours in local timezone
                work_start = current_date_local.replace(
                    hour=start_hour, minute=start_min, second=0, microsecond=0
                )
                work_end = current_date_local.replace(
                    hour=end_hour, minute=end_min, second=0, microsecond=0
                )

                # Convert to UTC
                work_start_utc = work_start.astimezone(pytz.UTC)
                work_end_utc = work_end.astimezone(pytz.UTC)

                # Get slots for this work period
                work_period_slots = slot_indexer.get_slots_in_range(work_start_utc, work_end_utc)
                work_slots.update(work_period_slots)

            current_date += timedelta(days=1)

    return work_slots


def get_participant_working_hours(
    participant_email: str,
    from_date_utc: datetime,
    to_date_utc: datetime,
    default_hours: str = "M-F 09:00-17:00",
    default_timezone: str = "America/New_York",
    slot_size_minutes: int = 15
) -> Tuple[Set[int], str]:
    """
    Get working hours for a participant from their Letta identity.

    Falls back to default hours if identity not found or no working hours set.

    Args:
        participant_email: Email/calendar ID of participant
        from_date_utc: Start of time range (UTC)
        to_date_utc: End of time range (UTC)
        default_hours: Default work hours string (e.g., "M-F 09:00-17:00")
        default_timezone: Default timezone if not set in identity
        slot_size_minutes: Size of each slot in minutes

    Returns:
        Tuple of (work_slots_set, timezone_str)
    """
    # Try to fetch identity
    identity = fetch_identity_by_email(participant_email)

    if identity:
        working_hours, timezone = parse_identity_working_hours(identity)

        if working_hours:
            # Convert identity working hours to slots
            work_slots = convert_working_hours_to_slots(
                working_hours=working_hours,
                timezone_str=timezone,
                from_date_utc=from_date_utc,
                to_date_utc=to_date_utc,
                slot_size_minutes=slot_size_minutes
            )

            logger.info(f"Loaded working hours from identity for {participant_email}")
            return work_slots, timezone
        else:
            # Identity exists but no working hours - use default with identity timezone
            logger.debug(f"No working hours in identity for {participant_email}, using defaults")
            timezone = get_identity_property(identity, "timezone") or default_timezone
    else:
        # No identity found
        logger.debug(f"No identity found for {participant_email}, using defaults")
        timezone = default_timezone

    # Fall back to default work hours
    return _default_work_hours_to_slots(
        default_hours=default_hours,
        timezone_str=timezone,
        from_date_utc=from_date_utc,
        to_date_utc=to_date_utc,
        slot_size_minutes=slot_size_minutes
    ), timezone


def _default_work_hours_to_slots(
    default_hours: str,
    timezone_str: str,
    from_date_utc: datetime,
    to_date_utc: datetime,
    slot_size_minutes: int = 15
) -> Set[int]:
    """Convert default work hours string to slots."""
    # Parse default hours format like "M-F 09:00-17:00"
    parts = default_hours.split()
    if len(parts) < 2:
        # Invalid format, return Mon-Fri 9-5
        day_range = "M-F"
        time_range = "09:00-17:00"
    else:
        day_range = parts[0]
        time_range = parts[1]

    # Parse days
    if day_range == "M-F":
        weekdays = [0, 1, 2, 3, 4]
    elif day_range == "M-S":
        weekdays = [0, 1, 2, 3, 4, 5, 6]
    elif day_range == "M-Th":
        weekdays = [0, 1, 2, 3]
    else:
        weekdays = [0, 1, 2, 3, 4]  # Default to weekdays

    # Parse times
    try:
        start_str, end_str = time_range.split("-")
        start_hour, start_min = map(int, start_str.split(":"))
        end_hour, end_min = map(int, end_str.split(":"))
    except ValueError:
        start_hour, start_min = 9, 0
        end_hour, end_min = 17, 0

    # Build working_hours dict
    working_hours = {}
    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, day_name in enumerate(day_names):
        if i in weekdays:
            working_hours[day_name] = {
                "start": f"{start_hour:02d}:{start_min:02d}",
                "end": f"{end_hour:02d}:{end_min:02d}"
            }
        else:
            working_hours[day_name] = None

    return convert_working_hours_to_slots(
        working_hours=working_hours,
        timezone_str=timezone_str,
        from_date_utc=from_date_utc,
        to_date_utc=to_date_utc,
        slot_size_minutes=slot_size_minutes
    )


def get_all_participants_working_hours(
    participant_emails: List[str],
    from_date_utc: datetime,
    to_date_utc: datetime,
    default_hours: str = "M-F 09:00-17:00",
    default_timezone: str = "America/New_York"
) -> Dict[str, Set[int]]:
    """
    Get working hours for multiple participants.

    Args:
        participant_emails: List of email addresses
        from_date_utc: Start of time range (UTC)
        to_date_utc: End of time range (UTC)
        default_hours: Default work hours string
        default_timezone: Default timezone

    Returns:
        Dict mapping participant email -> set of working hour slot indices
    """
    result = {}
    for email in participant_emails:
        work_slots, _ = get_participant_working_hours(
            participant_email=email,
            from_date_utc=from_date_utc,
            to_date_utc=to_date_utc,
            default_hours=default_hours,
            default_timezone=default_timezone
        )
        result[email] = work_slots
    return result
