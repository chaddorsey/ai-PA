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


def fuzzy_match_title(search_title: str, event_title: str, threshold: float = 0.4) -> float:
    """
    Calculate fuzzy match score between search title and event title.
    
    Handles partial matches well (e.g., "Support Team meeting" matches "Weekly Support Team Standup").
    
    Args:
        search_title: Title keyword to search for (may be partial, e.g., "Support Team meeting")
        event_title: Event title to match against (full title, e.g., "Weekly Support Team Standup")
        threshold: Minimum similarity score to consider a match (lowered to 0.4 for better partial matching)
        
    Returns:
        Similarity score between 0.0 and 1.0
    """
    search_title = search_title.lower().strip()
    event_title = event_title.lower().strip()
    
    if not search_title or not event_title:
        return 0.0
    
    # Exact match
    if search_title == event_title:
        return 1.0
    
    # Substring match (either direction) - high score for partial matches
    if search_title in event_title:
        # Search title is contained in event title (e.g., "support team" in "weekly support team standup")
        return 0.9
    if event_title in search_title:
        # Event title is contained in search (less common but still good match)
        return 0.85
    
    # Word-based matching - better for partial references
    search_words = set(word for word in search_title.split() if len(word) > 2)  # Ignore short words
    event_words = set(word for word in event_title.split() if len(word) > 2)
    
    if not search_words:
        return 0.0
    
    # Calculate how many search words appear in event title
    matching_words = search_words & event_words
    word_coverage = len(matching_words) / len(search_words) if search_words else 0.0
    
    # If most/all search words match, give high score even if event has more words
    if word_coverage >= 0.8:  # 80%+ of search words match
        return 0.85
    elif word_coverage >= 0.6:  # 60%+ of search words match
        return 0.7
    elif word_coverage >= 0.4:  # 40%+ of search words match
        return 0.5
    
    # Calculate Jaccard similarity (for cases where word order matters)
    intersection = search_words & event_words
    union = search_words | event_words
    if union:
        jaccard = len(intersection) / len(union)
    else:
        jaccard = 0.0
    
    # Sequence similarity (for character-level matching)
    sequence_sim = SequenceMatcher(None, search_title, event_title).ratio()
    
    # Combined score (weighted toward word coverage for partial matches)
    combined = (word_coverage * 0.5 + jaccard * 0.3 + sequence_sim * 0.2)
    
    return combined if combined >= threshold else 0.0


def map_participant_names_to_emails(
    participant_names: List[str],
    context_json: Optional[Dict[str, Any]],
    participant_ids: Optional[List[str]] = None
) -> List[str]:
    """
    Map participant names to email addresses using context and participant_ids.
    
    Args:
        participant_names: List of participant names (e.g., ["Judi Raiff", "Alex"])
        context_json: Context containing participant information
        participant_ids: Optional list of participant email addresses to use as fallback
        
    Returns:
        List of email addresses corresponding to the names
    """
    emails = []
    
    # Handle both dict and string (JSON) formats
    if isinstance(context_json, str):
        try:
            import json
            context_json = json.loads(context_json)
        except:
            context_json = None
    
    # Try to match from context_json participants first
    if context_json and isinstance(context_json, dict) and "participants" in context_json:
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
    
    # If we still have unmatched names and participant_ids is available, try fuzzy matching
    if participant_ids:
        from difflib import SequenceMatcher
        
        for name in participant_names:
            # Skip if already matched
            name_lower = name.lower().strip()
            already_matched = any(name_lower in email.lower() or email.lower() in name_lower for email in emails)
            if already_matched:
                continue
            
            # Try to match name to email prefix or full email
            # e.g., "Judi Raiff" -> "jraiff@concord.org" (match "jraiff" or "judi")
            best_match = None
            best_score = 0.0
            
            for p_id in participant_ids:
                email_prefix = p_id.split("@")[0].lower()
                email_lower = p_id.lower()
                
                # Try matching name parts to email prefix
                name_parts = name_lower.split()
                for name_part in name_parts:
                    # Exact match on email prefix
                    if name_part == email_prefix:
                        best_match = p_id
                        best_score = 1.0
                        break
                    # Fuzzy match on email prefix
                    similarity = SequenceMatcher(None, name_part, email_prefix).ratio()
                    if similarity > best_score and similarity > 0.6:  # 60% similarity threshold
                        best_score = similarity
                        best_match = p_id
                    # Check if name contains email prefix or vice versa
                    if name_part in email_prefix or email_prefix in name_part:
                        if len(name_part) >= 3:  # At least 3 characters
                            best_match = p_id
                            best_score = 0.8
                            break
            
            if best_match and best_match not in emails:
                emails.append(best_match)
    
    return emails


def score_event_match(
    event: Dict[str, Any],
    event_identifiers: Dict[str, Any],
    context_json: Optional[Dict[str, Any]] = None,
    events_by_participant: Optional[Dict[str, List[Dict[str, Any]]]] = None
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
    
    # Handle both dict format (with dateTime/date fields) and string format (ISO 8601)
    if isinstance(event_start, str):
        # start is already an ISO 8601 string
        event_start_dt_str = event_start
    elif isinstance(event_start, dict):
        # start is a dict with dateTime or date fields
        event_start_dt_str = event_start.get("dateTime") or event_start.get("date", "")
    else:
        # Fallback: try to get as string or empty
        event_start_dt_str = str(event_start) if event_start else ""
    
    # Extract attendees - prefer attendees_details (with names) over attendees_list
    event_attendees = event.get("attendees_list", [])
    event_attendees_details = event.get("attendees_details", [])
    
    # Build attendee emails and names from attendees_details if available
    attendee_emails_from_details = []
    attendee_names_from_details = []
    if event_attendees_details and isinstance(event_attendees_details, list):
        for attendee in event_attendees_details:
            if isinstance(attendee, dict):
                email = attendee.get("email", "")
                name = attendee.get("name", "")
                if email:
                    attendee_emails_from_details.append(email)
                if name:
                    attendee_names_from_details.append(name.lower())
    
    # Use attendees_details emails if available, fallback to attendees_list
    if attendee_emails_from_details:
        event_attendees = attendee_emails_from_details
    
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
    
    # Extract participant names from titles if not explicitly provided
    # Handles cases like "Kate/Chad check in" where participants are in the title
    participant_names = event_identifiers.get("participant_names", [])
    titles = event_identifiers.get("titles", [])
    
    # If no explicit participant names but we have titles, try to extract names from titles
    # Now we can also match extracted names to attendee names from attendees_details
    if not participant_names and titles:
        for title_ref in titles:
            # Look for patterns like "Name1/Name2", "Name1 & Name2", "Name1 and Name2"
            # Split on common separators
            title_lower = title_ref.lower()
            # Common patterns: "kate/chad", "kate & chad", "kate and chad", "kate, chad"
            import re
            # Try to find name patterns (2-3 words separated by /, &, and, or comma)
            name_patterns = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*[/&,]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', title_ref)
            if name_patterns:
                for name1, name2 in name_patterns:
                    if name1.strip() not in participant_names:
                        participant_names.append(name1.strip())
                    if name2.strip() not in participant_names:
                        participant_names.append(name2.strip())
    
    # Enhanced: If we have attendee names from attendees_details, try to match title-extracted names
    # This helps with cases like "Kate/Chad check in" where Kate and Chad are in attendees_details
    if participant_names and attendee_names_from_details:
        # Check if any extracted name matches attendee names (case-insensitive)
        matched_names = []
        for p_name in participant_names:
            p_name_lower = p_name.lower()
            # Try exact match
            if p_name_lower in attendee_names_from_details:
                matched_names.append(p_name)
            else:
                # Try partial match (first name only)
                p_first_name = p_name_lower.split()[0] if p_name_lower.split() else ""
                for attendee_name in attendee_names_from_details:
                    attendee_first_name = attendee_name.split()[0] if attendee_name.split() else ""
                    if p_first_name and attendee_first_name and p_first_name == attendee_first_name:
                        matched_names.append(p_name)
                        break
    
    # Track individual component scores for combination bonuses
    participant_score = 0.0
    date_score = 0.0
    title_score = 0.0
    time_score = 0.0
    
    # Score participant match (weight: 0.35)
    if participant_names:
        max_score += 0.35
        # Extract participant_ids from events_by_participant if available
        participant_ids = None
        if isinstance(events_by_participant, dict):
            participant_ids = list(events_by_participant.keys())
        participant_emails = map_participant_names_to_emails(participant_names, context_json, participant_ids)
        
        # ENHANCED: Direct name matching using attendees_details
        name_matches = 0
        if attendee_names_from_details:
            participant_names_lower = [name.lower() for name in participant_names]
            for p_name_lower in participant_names_lower:
                # Try exact match
                if p_name_lower in attendee_names_from_details:
                    name_matches += 1
                else:
                    # Try partial match (first name only)
                    p_first_name = p_name_lower.split()[0] if p_name_lower.split() else ""
                    for attendee_name in attendee_names_from_details:
                        attendee_first_name = attendee_name.split()[0] if attendee_name.split() else ""
                        if p_first_name and attendee_first_name and p_first_name == attendee_first_name:
                            name_matches += 1
                            break
        
        # Email-based matching (fallback or supplement)
        email_matches = 0
        if participant_emails:
            # Check if any participant email is in event attendees
            matching_participants = [email for email in participant_emails if email in event_attendees]
            # Also check if the event owner (from events_by_participant key) is a participant
            event_owner = None
            if isinstance(events_by_participant, dict):
                for owner_id, events_list in events_by_participant.items():
                    if event in events_list:
                        event_owner = owner_id
                        break
            
            # Count how many required participants are present
            all_participants_present = set(participant_emails)
            if event_owner and event_owner in participant_emails:
                all_participants_present.add(event_owner)
            if matching_participants:
                all_participants_present.update(matching_participants)
            
            email_matches = len(all_participants_present)
        
        # Combine name and email matches - prefer name matches (more accurate)
        total_matches = max(name_matches, email_matches) if name_matches > 0 or email_matches > 0 else 0
        total_participants = max(len(participant_names), len(participant_emails) if participant_emails else 0)
        
        if total_matches > 0 and total_participants > 0:
            # Full match: all participants are present
            if total_matches >= total_participants:
                participant_score = 0.35
            # Partial match: at least one participant matches
            elif total_matches >= 1:
                # Scale score based on match ratio
                participant_score = 0.2 + (0.15 * (total_matches / total_participants))
            score += participant_score
    
    # Score date match (weight: 0.35)
    dates = event_identifiers.get("dates", [])
    if dates and event_start_dt:
        max_score += 0.35
        for date_ref in dates:
            parsed_date = parse_date_reference(date_ref, datetime.now(pytz.UTC))
            if parsed_date and event_start_dt:
                # Compare dates (ignore time)
                event_date = event_start_dt.date()
                parsed_date_only = parsed_date.date()
                if event_date == parsed_date_only:
                    date_score = 0.35
                    score += date_score
                    break
                # Allow 1 day tolerance (but with lower score)
                elif abs((event_date - parsed_date_only).days) == 1:
                    date_score = 0.15
                    score += date_score
                    break
    
    # Score title match (weight: 0.35 - increased for rescheduling)
    if titles:
        max_score += 0.35
        best_title_score_raw = 0.0
        for title_ref in titles:
            title_score_raw = fuzzy_match_title(title_ref, event_title)
            best_title_score_raw = max(best_title_score_raw, title_score_raw)
        title_score = best_title_score_raw * 0.35
        score += title_score
    
    # Score time match (weight: 0.15 - lower priority, often not specified)
    times = event_identifiers.get("times", [])
    if times and event_start_dt:
        max_score += 0.15
        for time_ref in times:
            parsed_time = parse_time_reference(time_ref)
            if parsed_time:
                hour, minute = parsed_time
                event_hour = event_start_dt.hour
                # Allow 2 hour tolerance
                if abs(event_hour - hour) <= 2:
                    time_score = 0.15
                    score += time_score
                    break
    
    # COMBINATION BONUSES: Reward common patterns
    # Pattern 1: Title + Date (very common: "tomorrow's Support Team meeting")
    if title_score > 0 and date_score > 0:
        # Both title and date match - this is a strong signal
        bonus = min(title_score, date_score) * 0.3  # 30% bonus of the lower score
        score += bonus
        max_score += bonus
    
    # Pattern 2: Participants + Date (very common: "Dec. 12 Kate/Chad check in")
    if participant_score > 0 and date_score > 0:
        # Both participants and date match - this is a strong signal
        bonus = min(participant_score, date_score) * 0.3  # 30% bonus of the lower score
        score += bonus
        max_score += bonus
    
    # Pattern 3: Title + Participants (less common but still valuable)
    if title_score > 0 and participant_score > 0:
        # Both title and participants match
        bonus = min(title_score, participant_score) * 0.2  # 20% bonus
        score += bonus
        max_score += bonus
    
    # Pattern 4: All three (Title + Participants + Date) - very strong match
    if title_score > 0 and participant_score > 0 and date_score > 0:
        # Triple match - maximum confidence
        bonus = (title_score + participant_score + date_score) * 0.15  # 15% bonus on sum
        score += bonus
        max_score += bonus
    
    # Normalize score
    if max_score > 0:
        return min(score / max_score, 1.0)  # Cap at 1.0
    return 0.0


def identify_event_from_natural_language(
    event_identifiers: Dict[str, Any],
    events_by_participant: Dict[str, List[Dict[str, Any]]],
    context_json: Optional[Dict[str, Any]] = None,
    min_score: float = 0.5
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
    
    # Log for debugging
    import sys
    try:
        print(f"[identify_event_from_natural_language] Searching for event with identifiers: {event_identifiers}", file=sys.stderr, flush=True)
        print(f"[identify_event_from_natural_language] Total participants: {len(events_by_participant)}, Total events: {sum(len(events) for events in events_by_participant.values())}", file=sys.stderr, flush=True)
    except:
        pass
    
    # Score all events across all participants
    top_candidates = []  # Track top candidates for debugging
    for participant_id, events in events_by_participant.items():
        for event in events:
            score = score_event_match(event, event_identifiers, context_json, events_by_participant)
            if score > best_score:
                best_score = score
                best_match = event
                best_participant = participant_id
            # Track top candidates (score >= 0.2)
            if score >= 0.2:
                top_candidates.append((score, event.get("summary", ""), event.get("id", ""), participant_id))
    
    # Log top candidates for debugging with more details
    try:
        top_candidates.sort(reverse=True, key=lambda x: x[0])
        print(f"[identify_event_from_natural_language] Top 5 candidates:", file=sys.stderr, flush=True)
        for i, (score, title, event_id, part_id) in enumerate(top_candidates[:5], 1):
            # Try to get more event details for logging
            event_details = ""
            for p_id, events in events_by_participant.items():
                for evt in events:
                    if evt.get("id", "") == event_id:
                        # Get date info
                        start_raw = evt.get("start", {})
                        if isinstance(start_raw, str):
                            start_str = start_raw[:10] if len(start_raw) >= 10 else start_raw
                        elif isinstance(start_raw, dict):
                            start_str = start_raw.get("dateTime", start_raw.get("date", ""))[:10]
                        else:
                            start_str = ""
                        # Get attendees count
                        attendees = evt.get("attendees_list", [])
                        num_attendees = len(attendees) if isinstance(attendees, list) else 0
                        event_details = f" | Date: {start_str} | Attendees: {num_attendees}"
                        break
                if event_details:
                    break
            print(f"  {i}. Score {score:.2f}: '{title}' (ID: {event_id[:50]}...){event_details} in {part_id}", file=sys.stderr, flush=True)
    except:
        pass
    
    # Log best match found
    try:
        if best_match:
            print(f"[identify_event_from_natural_language] Best match found: '{best_match.get('summary', '')}' (ID: {best_match.get('id', '')}) with score {best_score:.2f} (min: {min_score})", file=sys.stderr, flush=True)
        else:
            print(f"[identify_event_from_natural_language] No match found (best_score: {best_score:.2f}, min_score: {min_score})", file=sys.stderr, flush=True)
    except:
        pass
    
    # Return best match if it meets minimum threshold
    if best_match and best_score >= min_score:
        return (best_match, best_participant)
    
    return None

