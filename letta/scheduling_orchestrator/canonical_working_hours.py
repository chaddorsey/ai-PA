"""
Canonical-backed working hours for the scheduling orchestrator.

Drop-in replacement for identity_working_hours.py. Reads
working_hours per person from the agents-canonical Gitea repo
instead of Letta /v1/identities/ properties.

Public API:
    get_participant_working_hours(email, ...) -> (Set[int], str)
    get_all_participants_working_hours(emails, ...) -> Dict[email, Set[int]]

Schema (per-person YAML frontmatter):
    timezone: <IANA>
    working_hours:
      monday: {start: "09:00", end: "17:00"}
      tuesday: {start: "09:00", end: "17:00"}
      wednesday: {start: "09:00", end: "17:00"}
      thursday: {start: "09:00", end: "17:00"}
      friday: {start: "09:00", end: "17:00"}
      saturday: null
      sunday: null

Default fallback when working_hours is missing: M-F 09:00-17:00 anchored
in the participant's stated timezone (or the supplied default_timezone
when canonical lacks a timezone field too).
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import pytz

try:
    from .canonical_client import get_person_by_email
except ImportError:
    from canonical_client import get_person_by_email

logger = logging.getLogger(__name__)


DAY_TO_WEEKDAY = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _default_weekly_working_hours(default_hours: str = "M-F 09:00-17:00") -> Dict[str, Any]:
    """
    Parse a short default_hours string into the canonical working_hours dict.

    Accepts forms like "M-F 09:00-17:00", "M-Th 09:00-17:00", "M-S 09:00-17:00".
    Falls back to M-F 9-5 on parse failure.
    """
    parts = default_hours.split()
    day_range = parts[0] if parts else "M-F"
    time_range = parts[1] if len(parts) > 1 else "09:00-17:00"

    if day_range == "M-F":
        active_weekdays = [0, 1, 2, 3, 4]
    elif day_range == "M-Th":
        active_weekdays = [0, 1, 2, 3]
    elif day_range == "M-S":
        active_weekdays = [0, 1, 2, 3, 4, 5, 6]
    else:
        active_weekdays = [0, 1, 2, 3, 4]

    try:
        start_str, end_str = time_range.split("-")
        # Sanity-check parseable HH:MM
        list(map(int, start_str.split(":")))
        list(map(int, end_str.split(":")))
    except ValueError:
        start_str, end_str = "09:00", "17:00"

    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    working_hours: Dict[str, Any] = {}
    for i, day in enumerate(day_names):
        if i in active_weekdays:
            working_hours[day] = {"start": start_str, "end": end_str}
        else:
            working_hours[day] = None
    return working_hours


def _normalize_working_hours(value: Any) -> Optional[Dict[str, Any]]:
    """
    Normalize a canonical working_hours value to the standard shape.

    Accepts:
      - Full dict with all 7 days
      - Partial dict (missing days treated as null/no-work)
      - None / missing → None (signals "use default")
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        logger.warning(f"Unexpected working_hours type: {type(value).__name__}")
        return None

    normalized: Dict[str, Any] = {}
    for day in DAY_TO_WEEKDAY:
        entry = value.get(day)
        if entry is None:
            normalized[day] = None
            continue
        if not isinstance(entry, dict):
            logger.warning(f"Working hours for {day} is not a dict: {entry!r}")
            normalized[day] = None
            continue
        start = entry.get("start")
        end = entry.get("end")
        if not (isinstance(start, str) and isinstance(end, str)):
            logger.warning(f"Working hours for {day} missing start/end: {entry!r}")
            normalized[day] = None
            continue
        normalized[day] = {"start": start, "end": end}
    return normalized


def _convert_working_hours_to_slots(
    working_hours: Dict[str, Any],
    timezone_str: str,
    from_date_utc: datetime,
    to_date_utc: datetime,
) -> Set[int]:
    """
    Project a weekly working_hours dict onto the date range, returning
    the set of 15-minute slot indices that fall within the participant's
    working hours.
    """
    try:
        from .slot_indexer import SlotIndexer
    except ImportError:
        from slot_indexer import SlotIndexer

    try:
        tz = pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        logger.warning(f"Unknown timezone {timezone_str!r}; falling back to America/New_York")
        tz = pytz.timezone("America/New_York")

    slot_indexer = SlotIndexer(from_date_utc, to_date_utc)
    work_slots: Set[int] = set()

    for day_name, hours in working_hours.items():
        if hours is None:
            continue
        weekday = DAY_TO_WEEKDAY.get(day_name.lower())
        if weekday is None:
            continue
        try:
            start_hour, start_min = map(int, hours["start"].split(":"))
            end_hour, end_min = map(int, hours["end"].split(":"))
        except (KeyError, ValueError, AttributeError):
            logger.warning(f"Invalid hours format for {day_name}: {hours!r}")
            continue

        current = from_date_utc
        while current < to_date_utc:
            local = current.astimezone(tz)
            if local.weekday() == weekday:
                work_start_local = local.replace(
                    hour=start_hour, minute=start_min, second=0, microsecond=0
                )
                work_end_local = local.replace(
                    hour=end_hour, minute=end_min, second=0, microsecond=0
                )
                work_start_utc = work_start_local.astimezone(pytz.UTC)
                work_end_utc = work_end_local.astimezone(pytz.UTC)
                work_slots.update(slot_indexer.get_slots_in_range(work_start_utc, work_end_utc))
            current += timedelta(days=1)

    return work_slots


def get_participant_working_hours(
    participant_email: str,
    from_date_utc: datetime,
    to_date_utc: datetime,
    default_hours: str = "M-F 09:00-17:00",
    default_timezone: str = "America/New_York",
    slot_size_minutes: int = 15,  # accepted for API compat; SlotIndexer uses 15
) -> Tuple[Set[int], str]:
    """
    Drop-in replacement for identity_working_hours.get_participant_working_hours.

    Returns (work_slots, timezone_str). Timezone comes from canonical
    when available, otherwise default_timezone.
    """
    person = get_person_by_email(participant_email)

    if person:
        fm = person.get("frontmatter") or {}
        timezone_str = fm.get("timezone") or default_timezone
        wh = _normalize_working_hours(fm.get("working_hours"))
        if wh:
            slots = _convert_working_hours_to_slots(
                working_hours=wh,
                timezone_str=timezone_str,
                from_date_utc=from_date_utc,
                to_date_utc=to_date_utc,
            )
            logger.info(
                f"Canonical working hours loaded for {participant_email} "
                f"({timezone_str}): {len(slots)} slots"
            )
            return slots, timezone_str

        # Person known but no working_hours field — default 9-5 in their TZ
        logger.debug(
            f"No working_hours in canonical for {participant_email}; "
            f"defaulting to {default_hours} in {timezone_str}"
        )
    else:
        timezone_str = default_timezone
        logger.debug(
            f"No canonical entry for {participant_email}; "
            f"defaulting to {default_hours} in {timezone_str}"
        )

    default_wh = _default_weekly_working_hours(default_hours)
    slots = _convert_working_hours_to_slots(
        working_hours=default_wh,
        timezone_str=timezone_str,
        from_date_utc=from_date_utc,
        to_date_utc=to_date_utc,
    )
    return slots, timezone_str


def get_all_participants_working_hours(
    participant_emails: List[str],
    from_date_utc: datetime,
    to_date_utc: datetime,
    default_hours: str = "M-F 09:00-17:00",
    default_timezone: str = "America/New_York",
) -> Dict[str, Set[int]]:
    """Drop-in replacement for identity_working_hours.get_all_participants_working_hours."""
    result: Dict[str, Set[int]] = {}
    for email in participant_emails:
        slots, _ = get_participant_working_hours(
            participant_email=email,
            from_date_utc=from_date_utc,
            to_date_utc=to_date_utc,
            default_hours=default_hours,
            default_timezone=default_timezone,
        )
        result[email] = slots
    return result
