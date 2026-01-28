"""Parse natural language time windows into structured data."""
import logging
import re
from datetime import date, time, timedelta
from typing import Dict, List, Any, Optional

try:
    from .evaluation_models import ProposedWindow, TimeRange
except ImportError:
    from evaluation_models import ProposedWindow, TimeRange


# Default business hours
DEFAULT_START = time(8, 0)
DEFAULT_END = time(18, 0)

# Day name mappings
DAY_NAMES = {
    'monday': 0, 'mon': 0,
    'tuesday': 1, 'tue': 1, 'tues': 1,
    'wednesday': 2, 'wed': 2,
    'thursday': 3, 'thu': 3, 'thur': 3, 'thurs': 3,
    'friday': 4, 'fri': 4,
    'saturday': 5, 'sat': 5,
    'sunday': 6, 'sun': 6,
}


def _parse_time_string(time_str: str, suffix_hint: Optional[str] = None) -> time:
    """
    Parse a time string like '3:30pm', '4pm', '14:00' into a time object.

    Args:
        time_str: Time string in various formats
        suffix_hint: Optional am/pm hint for times without explicit suffix (e.g., "3:30" in "3:30-4:30pm")

    Returns:
        time object
    """
    time_str = time_str.strip().lower()

    # Handle 24-hour format (14:00) - only if no suffix hint
    match_24h = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
    if match_24h:
        hour = int(match_24h.group(1))
        minute = int(match_24h.group(2))
        # If we have a suffix hint and the hour is ambiguous (1-12), apply it
        if suffix_hint and hour <= 12:
            if suffix_hint == 'pm' and hour != 12:
                hour += 12
            elif suffix_hint == 'am' and hour == 12:
                hour = 0
        return time(hour, minute)

    # Handle 12-hour format with minutes (3:30pm)
    match_12h_min = re.match(r'^(\d{1,2}):(\d{2})\s*(am|pm)$', time_str)
    if match_12h_min:
        hour = int(match_12h_min.group(1))
        minute = int(match_12h_min.group(2))
        is_pm = match_12h_min.group(3) == 'pm'
        if is_pm and hour != 12:
            hour += 12
        elif not is_pm and hour == 12:
            hour = 0
        return time(hour, minute)

    # Handle 12-hour format without minutes (4pm)
    match_12h = re.match(r'^(\d{1,2})\s*(am|pm)$', time_str)
    if match_12h:
        hour = int(match_12h.group(1))
        is_pm = match_12h.group(2) == 'pm'
        if is_pm and hour != 12:
            hour += 12
        elif not is_pm and hour == 12:
            hour = 0
        return time(hour, 0)

    # Handle noon/midnight
    if 'noon' in time_str:
        return time(12, 0)
    if 'midnight' in time_str:
        return time(0, 0)

    raise ValueError(f"Could not parse time: {time_str}")


def parse_time_phrase(phrase: str) -> Dict[str, Any]:
    """
    Parse a time phrase into start/end times and exclusions.

    Args:
        phrase: Natural language time phrase like "anytime but 3:30-4:30pm"

    Returns:
        Dict with keys: start (time), end (time), exclusions (list of {start, end})
    """
    phrase = phrase.strip().lower()
    result = {
        "start": DEFAULT_START,
        "end": DEFAULT_END,
        "exclusions": []
    }

    # Handle "morning only"
    if "morning" in phrase:
        result["start"] = time(8, 0)
        result["end"] = time(12, 0)
        return result

    # Handle "afternoon"
    if phrase == "afternoon" or "afternoon only" in phrase:
        result["start"] = time(12, 0)
        result["end"] = time(18, 0)
        return result

    # Handle "between X and Y"
    between_match = re.search(r'between\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+and\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)', phrase)
    if between_match:
        result["start"] = _parse_time_string(between_match.group(1))
        result["end"] = _parse_time_string(between_match.group(2))
        return result

    # Handle "until X" or "before X"
    until_match = re.search(r'(?:until|before)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)', phrase)
    if until_match:
        result["end"] = _parse_time_string(until_match.group(1))
        return result

    # Handle "after X"
    after_match = re.search(r'after\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)', phrase)
    if after_match:
        result["start"] = _parse_time_string(after_match.group(1))
        return result

    # Handle "anytime but X-Y" or "except X-Y"
    exclude_match = re.search(
        r'(?:but|except)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*[-–]\s*(\d{1,2}(?::\d{2})?\s*(am|pm)?)',
        phrase
    )
    if exclude_match:
        start_str = exclude_match.group(1)
        end_str = exclude_match.group(2)
        # Extract suffix from end time to use as hint for start time if needed
        suffix_hint = exclude_match.group(3) if exclude_match.group(3) else None
        exclusion = {
            "start": _parse_time_string(start_str, suffix_hint=suffix_hint),
            "end": _parse_time_string(end_str)
        }
        result["exclusions"].append(exclusion)

    return result


def parse_date_phrase(phrase: str, reference_date: date) -> date:
    """
    Parse a date phrase into a date object.

    Args:
        phrase: Date phrase like "01/29", "01/29 (Thu)", "tomorrow", "Monday"
        reference_date: Reference date for relative parsing

    Returns:
        date object
    """
    phrase = phrase.strip().lower()

    # Handle "today"
    if phrase == 'today':
        return reference_date

    # Handle "tomorrow"
    if phrase == 'tomorrow':
        return reference_date + timedelta(days=1)

    # Handle MM/DD format with optional day name
    mm_dd_match = re.match(r'^(\d{1,2})/(\d{1,2})(?:\s*\(?(?:mon|tue|wed|thu|fri|sat|sun)\w*\)?)?', phrase)
    if mm_dd_match:
        month = int(mm_dd_match.group(1))
        day = int(mm_dd_match.group(2))
        year = reference_date.year

        # Handle year rollover (if date is in past, assume next year)
        result = date(year, month, day)
        if result < reference_date:
            result = date(year + 1, month, day)
        return result

    # Handle day name (find next occurrence)
    for day_name, day_num in DAY_NAMES.items():
        if phrase.startswith(day_name):
            # Calculate days until next occurrence
            current_day = reference_date.weekday()
            days_ahead = day_num - current_day
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            return reference_date + timedelta(days=days_ahead)

    raise ValueError(f"Could not parse date: {phrase}")


def parse_proposed_windows(text: str, reference_date: date) -> List[ProposedWindow]:
    """
    Parse multiple proposed time windows from text.

    Args:
        text: Multi-line text with one window per line
              Format: "MM/DD (Day), time description"
        reference_date: Reference date for parsing

    Returns:
        List of ProposedWindow objects
    """
    windows = []

    # Split into lines and process each
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]

    for line in lines:
        # Try to split on comma to separate date from time
        parts = line.split(',', 1)

        if len(parts) >= 2:
            date_part = parts[0].strip()
            time_part = parts[1].strip()
        else:
            # No comma - try to detect date vs time
            date_part = line
            time_part = "anytime"

        try:
            # Parse the date
            parsed_date = parse_date_phrase(date_part, reference_date)

            # Parse the time phrase
            time_info = parse_time_phrase(time_part)

            # Convert exclusions to TimeRange objects
            exclusions = [
                TimeRange(start=exc["start"], end=exc["end"])
                for exc in time_info.get("exclusions", [])
            ]

            window = ProposedWindow(
                date=parsed_date,
                start_time=time_info["start"],
                end_time=time_info["end"],
                exclusions=exclusions,
                raw_text=line
            )
            windows.append(window)

        except (ValueError, KeyError) as e:
            # Skip unparseable lines but log them
            logging.warning(f"Could not parse window line: {line} - {e}")
            continue

    return windows
