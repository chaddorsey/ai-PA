"""
Event matching module for identifying events from natural language descriptions.

This module provides functions to match extracted event identifiers (participant names,
dates, times, titles) against calendar events fetched from MCP.
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import pytz
import re
from difflib import SequenceMatcher


def parse_date_reference(date_str: str, reference_date: Optional[datetime] = None) -> Optional[datetime]:
    """
    Parse a date reference string into an actual date.
    
    Args:
        date_str: Date reference like "Dec. 10th", "Monday", "tomorrow", "next week"
        reference_date: Reference date for relative dates (defaults to today)
        
    Returns:
        Parsed datetime object or None if parsing fails
    """
    if reference_date is None:
        reference_date = datetime.now(pytz.UTC)
    
    date_str = date_str.strip().lower()
    
    # Relative dates
    if date_str in ["today", "this day"]:
        return reference_date.replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_str in ["tomorrow", "next day"]:
        return (reference_date + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_str in ["yesterday", "previous day"]:
        return (reference_date - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Day of week
    days_of_week = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6
    }
    if date_str in days_of_week:
        target_weekday = days_of_week[date_str]
        current_weekday = reference_date.weekday()
        days_ahead = target_weekday - current_weekday
        if days_ahead <= 0:
            days_ahead += 7  # Next occurrence
        return (reference_date + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Try parsing as "Month Day" or "Month Day, Year"
    # Patterns: "Dec. 10th", "December 10", "Dec 10, 2025"
    month_names = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12
    }
    
    # Remove ordinal suffixes (th, st, nd, rd)
    date_str_clean = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)
    
    # Try pattern: "month day" or "month day, year"
    pattern = r'(\w+)\s+(\d+)(?:\s*,\s*(\d+))?'
    match = re.search(pattern, date_str_clean)
    if match:
        month_str = match.group(1).lower()
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else reference_date.year
        
        if month_str in month_names:
            month = month_names[month_str]
            try:
                return datetime(year, month, day, tzinfo=reference_date.tzinfo)
            except ValueError:
                pass
    
    return None


def parse_time_reference(time_str: str) -> Optional[Tuple[int, int]]:
    """
    Parse a time reference string into hour and minute.
    
    Args:
        time_str: Time reference like "2pm", "morning", "afternoon", "14:00"
        
    Returns:
        Tuple of (hour, minute) in 24-hour format, or None if parsing fails
    """
    time_str = time_str.strip().lower()
    
    # Time of day keywords
    if time_str in ["morning", "am"]:
        return (9, 0)  # Default to 9 AM
    elif time_str in ["afternoon"]:
        return (14, 0)  # Default to 2 PM
    elif time_str in ["evening"]:
        return (18, 0)  # Default to 6 PM
    elif time_str in ["night", "evening"]:
        return (20, 0)  # Default to 8 PM
    
    # Parse "HH:MM" or "H:MM" format
    time_pattern = r'(\d{1,2}):(\d{2})'
    match = re.search(time_pattern, time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        return (hour, minute)
    
    # Parse "Xpm" or "Xam" format
    time_pattern = r'(\d{1,2})\s*(am|pm)'
    match = re.search(time_pattern, time_str)
    if match:
        hour = int(match.group(1))
        is_pm = match.group(2) == "pm"
        if is_pm and hour != 12:
            hour += 12
        elif not is_pm and hour == 12:
            hour = 0
        return (hour, 0)
    
    return None


def fuzzy_match_title(search_title: str, event_title: str, threshold: float = 0.6) -> float:
    """
    Calculate fuzzy match score between search title and event title.
    
    Args:
        search_title: Title keyword to search for
        event_title: Event title to match against
        threshold: Minimum similarity score to consider a match
        
    Returns:
        Similarity score between 0.0 and 1.0
    """
    search_title = search_title.lower().strip()
    event_title = event_title.lower().strip()
    
    # Exact match
    if search_title == event_title:
        return 1.0
    
    # Substring match
    if search_title in event_title or event_title in search_title:
        return 0.9
    
    # Word-based matching
    search_words = set(search_title.split())
    event_words = set(event_title.split())
    
    if not search_words:
        return 0.0
    
    # Calculate Jaccard similarity
    intersection = search_words & event_words
    union = search_words | event_words
    if union:
        jaccard = len(intersection) / len(union)
    else:
        jaccard = 0.0
    
    # Sequence similarity
    sequence_sim = SequenceMatcher(None, search_title, event_title).ratio()
    
    # Combined score
    combined = (jaccard * 0.6 + sequence_sim * 0.4)
    
    return combined if combined >= threshold else 0.0


def map_participant_names_to_emails(
    participant_names: List[str],
    context_json: Optional[Dict[str, Any]]
) -> List[str]:
    """
    Map participant names to email addresses using context.
    
    Args:
        participant_names: List of participant names (e.g., ["Judi", "Alex"])
        context_json: Context containing participant information
        
    Returns:
        List of email addresses corresponding to the names
    """
    # Handle both dict and string (JSON) formats
    if isinstance(context_json, str):
        try:
            import json
            context_json = json.loads(context_json)
        except:
            return []
    
    if not context_json or not isinstance(context_json, dict) or "participants" not in context_json:
        return []
    
    emails = []
    participants = context_json.get("participants", [])
    
    for name in participant_names:
        name_lower = name.lower().strip()
        # Try to find matching participant
        for p in participants:
            p_name = p.get("name", "").lower()
            p_email = p.get("email", "")
            p_id = p.get("id", "").lower()
            
            # Match by name or ID
            if name_lower == p_name or name_lower == p_id or name_lower == p_email.lower():
                if p_email:
                    emails.append(p_email)
                elif p_id:
                    emails.append(p_id)
                break
    
    return emails


def score_event_match(
    event: Dict[str, Any],
    event_identifiers: Dict[str, Any],
    context_json: Optional[Dict[str, Any]] = None
) -> float:
    """
    Score how well an event matches the extracted identifiers.
    
    Args:
        event: Event dictionary from MCP (with summary, id, start, end, attendees_list)
        event_identifiers: Extracted identifiers (participant_names, dates, times, titles)
        context_json: Context for participant name mapping
        
    Returns:
        Match score between 0.0 and 1.0 (higher is better)
    """
    # Defensive handling: ensure event_identifiers is a dict
    if event_identifiers is None:
        return 0.0
    
    if isinstance(event_identifiers, str):
        try:
            import json
            event_identifiers = json.loads(event_identifiers)
        except (json.JSONDecodeError, ValueError):
            return 0.0
    
    if not isinstance(event_identifiers, dict):
        return 0.0
    
    # Handle context_json as string (defensive)
    if isinstance(context_json, str):
        try:
            import json
            context_json = json.loads(context_json)
        except (json.JSONDecodeError, ValueError):
            context_json = None
    
    score = 0.0
    max_score = 0.0
    
    # Extract event details
    event_title = event.get("summary", "").strip()
    event_start = event.get("start", {})
    event_start_dt_str = event_start.get("dateTime") or event_start.get("date", "")
    event_attendees = event.get("attendees_list", [])
    
    # Parse event start time
    event_start_dt = None
    if event_start_dt_str:
        try:
            # Try parsing ISO format
            if "T" in event_start_dt_str:
                event_start_dt = datetime.fromisoformat(event_start_dt_str.replace("Z", "+00:00"))
            else:
                event_start_dt = datetime.strptime(event_start_dt_str, "%Y-%m-%d")
                event_start_dt = pytz.UTC.localize(event_start_dt)
        except (ValueError, AttributeError):
            pass
    
    # Score participant match (weight: 0.3)
    participant_names = event_identifiers.get("participant_names", [])
    if participant_names:
        max_score += 0.3
        participant_emails = map_participant_names_to_emails(participant_names, context_json)
        if participant_emails:
            # Check if any participant email is in event attendees
            matching_participants = [email for email in participant_emails if email in event_attendees]
            if matching_participants:
                score += 0.3
            # Partial match (at least one participant matches)
            elif len(participant_emails) > 0:
                score += 0.15
    
    # Score date match (weight: 0.3)
    dates = event_identifiers.get("dates", [])
    if dates and event_start_dt:
        max_score += 0.3
        for date_ref in dates:
            parsed_date = parse_date_reference(date_ref, datetime.now(pytz.UTC))
            if parsed_date and event_start_dt:
                # Compare dates (ignore time)
                event_date = event_start_dt.date()
                parsed_date_only = parsed_date.date()
                if event_date == parsed_date_only:
                    score += 0.3
                    break
                # Allow 1 day tolerance
                elif abs((event_date - parsed_date_only).days) <= 1:
                    score += 0.15
                    break
    
    # Score time match (weight: 0.2)
    times = event_identifiers.get("times", [])
    if times and event_start_dt:
        max_score += 0.2
        for time_ref in times:
            parsed_time = parse_time_reference(time_ref)
            if parsed_time:
                hour, minute = parsed_time
                event_hour = event_start_dt.hour
                # Allow 2 hour tolerance
                if abs(event_hour - hour) <= 2:
                    score += 0.2
                    break
    
    # Score title match (weight: 0.2)
    titles = event_identifiers.get("titles", [])
    if titles:
        max_score += 0.2
        best_title_score = 0.0
        for title_ref in titles:
            title_score = fuzzy_match_title(title_ref, event_title)
            best_title_score = max(best_title_score, title_score)
        score += best_title_score * 0.2
    
    # Normalize score
    if max_score > 0:
        return score / max_score
    return 0.0


def identify_event_from_natural_language(
    event_identifiers: Dict[str, Any],
    events_by_participant: Dict[str, List[Dict[str, Any]]],
    context_json: Optional[Dict[str, Any]] = None,
    min_score: float = 0.4
) -> Optional[Tuple[Dict[str, Any], str]]:
    """
    Identify an event from natural language identifiers.
    
    Args:
        event_identifiers: Extracted identifiers with participant_names, dates, times, titles
        events_by_participant: Dictionary mapping participant IDs to their calendar events
        context_json: Context for participant name mapping
        min_score: Minimum match score to consider (default: 0.4)
        
    Returns:
        Tuple of (event_dict, participant_id) for the best match, or None if no good match
    """
    # Handle case where event_identifiers might be None, string, or not a dict
    if event_identifiers is None:
        return None
    
    # If event_identifiers is a string (JSON), parse it
    if isinstance(event_identifiers, str):
        try:
            import json
            event_identifiers = json.loads(event_identifiers)
        except (json.JSONDecodeError, ValueError):
            return None
    
    # Ensure it's a dict
    if not isinstance(event_identifiers, dict):
        return None
    
    # Handle case where context_json might be a string
    if isinstance(context_json, str):
        try:
            import json
            context_json = json.loads(context_json)
        except (json.JSONDecodeError, ValueError):
            context_json = None
    
    best_match = None
    best_score = 0.0
    best_participant = None
    
    # Score all events across all participants
    for participant_id, events in events_by_participant.items():
        for event in events:
            score = score_event_match(event, event_identifiers, context_json)
            if score > best_score:
                best_score = score
                best_match = event
                best_participant = participant_id
    
    # Return best match if it meets minimum threshold
    if best_match and best_score >= min_score:
        return (best_match, best_participant)
    
    return None

