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
    # Remove periods after month abbreviations (e.g., "Dec." -> "Dec")
    date_str_clean = re.sub(r'(\w+)\.', r'\1', date_str_clean)
    
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
    # But be more strict to avoid false positives (e.g., "Concord" matching "Concord Consortium/Hewlett" vs "Concord Audit Drafts")
    search_words = set(word for word in search_title.split() if len(word) > 2)  # Ignore short words
    event_words = set(word for word in event_title.split() if len(word) > 2)
    
    if not search_words:
        return 0.0
    
    # Calculate how many search words appear in event title
    matching_words = search_words & event_words
    word_coverage = len(matching_words) / len(search_words) if search_words else 0.0
    
    # CRITICAL: Require at least 2 matching words (not just one common word like "Concord")
    # This prevents "Concord Audit Drafts" from matching "Concord Consortium/Hewlett" 
    # when only "Concord" matches
    if len(matching_words) < 2 and len(search_words) >= 2:
        # If search has 2+ words but only 1 matches, it's likely a false positive
        # Only allow if it's a very short search (e.g., "Support Team" with 2 words, 1 matches)
        if len(search_words) == 2 and word_coverage >= 0.5:
            # Allow if 50%+ coverage and only 2 words total
            pass
        else:
            # Too few matching words - likely false positive
            return 0.0
    
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
    participant_ids: Optional[List[str]] = None,
    default_domain: str = "@concord.org"
) -> List[str]:
    """
    Map participant names to email addresses using context and participant_ids.
    Also constructs emails from shortened user IDs (e.g., "kmiller" -> "kmiller@concord.org").
    
    Args:
        participant_names: List of participant names (e.g., ["Judi Raiff", "Alex", "kmiller"])
        context_json: Context containing participant information
        participant_ids: Optional list of participant email addresses to use as fallback
        default_domain: Default domain to use when constructing emails from shortened IDs (default: "@concord.org")
        
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
    
    # Extract domain from context if available (e.g., from existing participant emails)
    domain_to_use = default_domain
    if context_json and isinstance(context_json, dict) and "participants" in context_json:
        participants = context_json.get("participants", [])
        # Try to infer domain from existing participant emails
        for p in participants:
            p_email = p.get("email", "")
            if p_email and "@" in p_email:
                domain_to_use = "@" + p_email.split("@")[1]
                break
    
    # Try to match from context_json participants first
    matched_names = set()
    if context_json and isinstance(context_json, dict) and "participants" in context_json:
        participants = context_json.get("participants", [])
        
        for name in participant_names:
            name_lower = name.lower().strip()
            matched = False
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
                    matched = True
                    matched_names.add(name_lower)
                    break
    
    # For unmatched names, try to construct emails from shortened IDs
    for name in participant_names:
        name_lower = name.lower().strip()
        # Skip if already matched or if it already looks like an email
        if name_lower in matched_names or "@" in name:
            continue
        
        # If name looks like a shortened user ID (no spaces, reasonable length, no @)
        if " " not in name and 2 <= len(name) <= 20:
            # Try to construct email from shortened ID
            constructed_email = name_lower + domain_to_use
            if constructed_email not in emails:
                emails.append(constructed_email)
                try:
                    print(f"[map_participant_names_to_emails] Constructed email from shortened ID: {name_lower} -> {constructed_email}", file=sys.stderr, flush=True)
                except:
                    pass
    
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
    events_by_participant: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    participant_ids: Optional[List[str]] = None
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
    # Check both 'title' (normalized) and 'summary' (raw MCP) fields
    event_title = (event.get("title", "") or event.get("summary", "")).strip()
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
    # Handles cases like "Kate/Chad check in" or "kmiller's Hold meeting" where participants are in the title
    participant_names = event_identifiers.get("participant_names", [])
    titles = event_identifiers.get("titles", [])
    
    # If no explicit participant names but we have titles, try to extract names from titles
    # Now we can also match extracted names to attendee names from attendees_details
    if not participant_names and titles:
        # Note: 're' is already imported at the module level
        for title_ref in titles:
            # Look for patterns like "Name1/Name2", "Name1 & Name2", "Name1 and Name2"
            # Also handle possessive forms like "kmiller's", "kmiller"
            title_lower = title_ref.lower()
            
            # Pattern 1: Two names separated by /, &, and, or comma
            # Common patterns: "kate/chad", "kate & chad", "kate and chad", "kate, chad"
            name_patterns = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*[/&,]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', title_ref)
            if name_patterns:
                for name1, name2 in name_patterns:
                    if name1.strip() not in participant_names:
                        participant_names.append(name1.strip())
                    if name2.strip() not in participant_names:
                        participant_names.append(name2.strip())
            
            # Pattern 2: Possessive forms like "kmiller's", "kmiller" (email prefix patterns)
            # Matches word patterns that look like email prefixes (2-20 chars, no spaces, may have 's)
            possessive_pattern = r"\b([a-z]{2,20})('s)?\b"
            possessive_matches = re.findall(possessive_pattern, title_lower)
            for match in possessive_matches:
                name_part = match[0]  # The name part without 's
                # Skip common words that aren't names
                skip_words = {'the', 'and', 'or', 'for', 'with', 'from', 'this', 'that', 'meeting', 'check', 'in', 'hold', 'block'}
                if name_part not in skip_words and name_part not in [p.lower() for p in participant_names]:
                    participant_names.append(name_part)
    
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
    # ENHANCED: If participant_ids are provided directly, use them for exact matching
    if participant_ids and isinstance(participant_ids, list) and len(participant_ids) > 0:
        # Direct participant_ids provided - check for exact matches
        max_score += 0.35
        
        # Get event attendees (emails)
        event_attendee_emails = set(event_attendees)
        # Also include event owner if available
        event_owner = None
        if isinstance(events_by_participant, dict):
            for owner_id, events_list in events_by_participant.items():
                if event in events_list:
                    event_owner = owner_id
                    event_attendee_emails.add(owner_id)  # Owner is always an attendee
                    break
        
        # Check if ALL participant_ids are in event attendees
        participant_ids_set = set(participant_ids)
        matching_participants = participant_ids_set.intersection(event_attendee_emails)
        all_participants_present = len(matching_participants) == len(participant_ids_set)
        
        # Count total attendees (excluding organizer if it's one of the participant_ids)
        total_event_attendees = len(event_attendee_emails)
        # If event owner is one of the participant_ids, don't count it as "extra"
        if event_owner and event_owner in participant_ids_set:
            total_event_attendees -= 1
        
        if all_participants_present:
            # All required participants are present
            # BONUS: Favor events that have ONLY the specified participants (or those + organizer)
            # If event has exactly the specified participants (or those + 1 organizer), give full score
            if total_event_attendees == len(participant_ids_set) or (total_event_attendees == len(participant_ids_set) + 1 and event_owner):
                participant_score = 0.35  # Perfect match - exact participants
            else:
                # Has all required participants but also has extras - slightly lower score
                participant_score = 0.30  # All present but has extras
            score += participant_score
        elif len(matching_participants) > 0:
            # Partial match - some but not all participants
            participant_score = 0.15 + (0.10 * (len(matching_participants) / len(participant_ids_set)))
            score += participant_score
    
    elif participant_names:
        max_score += 0.35
        # Extract participant_ids from events_by_participant if available (fallback)
        fallback_participant_ids = None
        if isinstance(events_by_participant, dict):
            fallback_participant_ids = list(events_by_participant.keys())
        participant_emails = map_participant_names_to_emails(participant_names, context_json, fallback_participant_ids)
        
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
        
        # Count total event attendees for penalty calculation
        total_event_attendees = len(event_attendees) if isinstance(event_attendees, list) else 0
        if attendee_names_from_details:
            total_event_attendees = max(total_event_attendees, len(attendee_names_from_details))
        # Include event owner if available
        event_owner = None
        if isinstance(events_by_participant, dict):
            for owner_id, events_list in events_by_participant.items():
                if event in events_list:
                    event_owner = owner_id
                    total_event_attendees += 1  # Count owner as attendee
                    break
        
        if total_matches > 0 and total_participants > 0:
            # Full match: all participants are present
            if total_matches >= total_participants:
                participant_score = 0.35
                # PENALTY: If event has many more attendees than specified participants, reduce score
                # This prevents large meetings (e.g., "All-hands") from matching small meeting requests
                if total_event_attendees > total_participants * 3:
                    # Event has 3x+ more attendees than specified - significant penalty
                    participant_score = 0.20  # Reduce from 0.35 to 0.20
                elif total_event_attendees > total_participants * 2:
                    # Event has 2x+ more attendees than specified - moderate penalty
                    participant_score = 0.28  # Reduce from 0.35 to 0.28
            # Partial match: at least one participant matches
            elif total_matches >= 1:
                # Scale score based on match ratio
                participant_score = 0.2 + (0.15 * (total_matches / total_participants))
                # Apply same penalty for large meetings
                if total_event_attendees > total_participants * 3:
                    participant_score *= 0.6  # 40% penalty
                elif total_event_attendees > total_participants * 2:
                    participant_score *= 0.8  # 20% penalty
            score += participant_score
    
    # Score date match (weight: 0.35)
    # CRITICAL: If we have multiple dates AND a title, the dates are likely the search window,
    # not the event date. In this case, prioritize title matching and ignore date matching.
    dates = event_identifiers.get("dates", [])
    titles = event_identifiers.get("titles", [])
    
    # If we have both title and multiple dates, dates are likely search window - skip date matching
    skip_date_matching = bool(titles) and len(dates) > 1
    
    if dates and event_start_dt and not skip_date_matching:
        max_score += 0.35
        date_score = 0.0
        date_mismatch_days = None
        for date_ref in dates:
            parsed_date = parse_date_reference(date_ref, datetime.now(pytz.UTC))
            try:
                import sys
                print(f"[score_event_match] DEBUG: Parsing date_ref='{date_ref}', parsed_date={parsed_date}, event_start_dt={event_start_dt}", file=sys.stderr, flush=True)
            except:
                pass
            if parsed_date and event_start_dt:
                # Compare dates (ignore time)
                event_date = event_start_dt.date()
                parsed_date_only = parsed_date.date()
                date_mismatch_days = abs((event_date - parsed_date_only).days)
                try:
                    import sys
                    print(f"[score_event_match] DEBUG: event_date={event_date}, parsed_date_only={parsed_date_only}, date_mismatch_days={date_mismatch_days}", file=sys.stderr, flush=True)
                except:
                    pass
                if event_date == parsed_date_only:
                    date_score = 0.35
                    score += date_score
                    break
                # CRITICAL: Reduce or eliminate 1-day tolerance to prevent wrong-day matches
                # Only allow 1-day tolerance if no participant names are specified (less specific request)
                elif date_mismatch_days == 1:
                    # If participant names are specified, be strict about date matching
                    # This prevents "Wednesday meeting with Judi" from matching Thursday events
                    if participant_names or (participant_ids and len(participant_ids) > 0):
                        # Participant specified - no tolerance for wrong day
                        date_score = 0.0
                    else:
                        # No participant specified - allow small tolerance
                        date_score = 0.10  # Reduced from 0.15 to 0.10
                    if date_score > 0:
                        score += date_score
                    break
                else:
                    # Date mismatch is more than 1 day - record for penalty calculation
                    date_score = 0.0
                    break
        
        # CRITICAL: Apply penalty for date mismatches beyond 1 day when participants are specified
        # This ensures that "Chad/Sue meeting on Dec. 11" doesn't match "Chad/Sue/Kathy on Dec. 18"
        try:
            import sys
            print(f"[score_event_match] DEBUG: date_mismatch_days={date_mismatch_days}, participant_names={participant_names}, participant_ids={participant_ids}", file=sys.stderr, flush=True)
        except:
            pass
        if date_mismatch_days is not None and date_mismatch_days > 1:
            if participant_names or (participant_ids and len(participant_ids) > 0):
                # Both participants and specific date provided - date mismatch is a strong negative signal
                # Apply penalty proportional to the mismatch (more days = bigger penalty)
                # Penalty reduces the overall score, not just the date component
                penalty = min(0.3, date_mismatch_days * 0.05)  # Up to 0.3 penalty (6+ days)
                score_before_penalty = score
                score = max(0.0, score - penalty)
                try:
                    import sys
                    print(f"[score_event_match] Applying date mismatch penalty: {penalty:.2f} for {date_mismatch_days} day(s) difference (participants specified). Score: {score_before_penalty:.2f} -> {score:.2f}", file=sys.stderr, flush=True)
                except:
                    pass
            else:
                try:
                    import sys
                    print(f"[score_event_match] DEBUG: Skipping penalty - no participant_names or participant_ids", file=sys.stderr, flush=True)
                except:
                    pass
        else:
            try:
                import sys
                print(f"[score_event_match] DEBUG: Skipping penalty - date_mismatch_days={date_mismatch_days} (not > 1)", file=sys.stderr, flush=True)
            except:
                pass
    elif skip_date_matching:
        # Log that we're skipping date matching due to ambiguous dates
        try:
            import sys
            print(f"[score_event_match] Skipping date matching - title present ({titles}) and multiple dates ({dates}) likely represent search window, not event date", file=sys.stderr, flush=True)
        except:
            pass
    
    # BONUS: Check if participant names appear in event title (e.g., "Judi / Chad meeting")
    # This is a strong signal that this is the right event
    participant_name_in_title_bonus = 0.0
    if participant_names and event_title:
        event_title_lower = event_title.lower()
        for p_name in participant_names:
            p_name_lower = p_name.lower()
            # Check if participant name appears in title (exact word match or as part of name pattern)
            if p_name_lower in event_title_lower:
                # Check if it's a word boundary match (not just substring)
                # Note: 're' is already imported at the top of the file
                if re.search(r'\b' + re.escape(p_name_lower) + r'\b', event_title_lower):
                    participant_name_in_title_bonus = 0.15  # Strong bonus for name in title
                    break
                # Also check for patterns like "Judi/Chad" or "Judi & Chad"
                if re.search(r'\b' + re.escape(p_name_lower) + r'[/&,]', event_title_lower) or \
                   re.search(r'[/&,]\s*' + re.escape(p_name_lower) + r'\b', event_title_lower):
                    participant_name_in_title_bonus = 0.15  # Strong bonus for name in title pattern
                    break
    
    # Score title match (weight: 0.35 - increased for rescheduling)
    # CRITICAL: Exact title matches get maximum priority
    if titles:
        max_score += 0.35
        best_title_score_raw = 0.0
        has_exact_match = False
        for title_ref in titles:
            title_score_raw = fuzzy_match_title(title_ref, event_title)
            # Check for exact match (case-insensitive)
            if title_ref.lower().strip() == event_title.lower().strip():
                has_exact_match = True
                best_title_score_raw = 1.0  # Force exact match to 1.0
                break  # Exact match found - no need to check other titles
            best_title_score_raw = max(best_title_score_raw, title_score_raw)
        
        # If exact match found, give it maximum weight (0.35) and add significant bonus
        if has_exact_match:
            title_score = 0.35  # Full weight for exact match
            score += title_score
            # Add bonus for exact match to ensure it beats fuzzy matches
            score += 0.2  # Additional bonus for exact match
            max_score += 0.2
        else:
            # Fuzzy match - use normal scoring
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
    
    # Apply participant name in title bonus (after combination bonuses)
    if participant_name_in_title_bonus > 0:
        score += participant_name_in_title_bonus
        max_score += participant_name_in_title_bonus
    
    # Normalize score
    if max_score > 0:
        return min(score / max_score, 1.0)  # Cap at 1.0
    return 0.0


def identify_event_from_natural_language(
    event_identifiers: Dict[str, Any],
    events_by_participant: Dict[str, List[Dict[str, Any]]],
    context_json: Optional[Dict[str, Any]] = None,
    min_score: float = 0.5,
    participant_ids: Optional[List[str]] = None
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
            score = score_event_match(event, event_identifiers, context_json, events_by_participant, participant_ids)
            if score > best_score:
                best_score = score
                best_match = event
                best_participant = participant_id
            # Track top candidates (score >= 0.2)
            if score >= 0.2:
                # Get more details for logging
                # Check both 'title' (normalized) and 'summary' (raw MCP) fields
                event_summary = event.get("title", "") or event.get("summary", "")
                event_id = event.get("id", "")
                # Get attendees for logging
                attendees = event.get("attendees_list", [])
                attendees_details = event.get("attendees_details", [])
                num_attendees = len(attendees) if isinstance(attendees, list) else 0
                if attendees_details and isinstance(attendees_details, list):
                    num_attendees = len(attendees_details)
                top_candidates.append((score, event_summary, event_id, participant_id, num_attendees))
    
    # Log top candidates for debugging with more details
    try:
        top_candidates.sort(reverse=True, key=lambda x: x[0])
        print(f"[identify_event_from_natural_language] Top 5 candidates:", file=sys.stderr, flush=True)
        for i, candidate in enumerate(top_candidates[:5], 1):
            if len(candidate) >= 5:
                score, title, event_id, part_id, num_attendees = candidate[:5]
            else:
                score, title, event_id, part_id = candidate[:4]
                num_attendees = 0
            
            # Try to get more event details for logging
            event_details = ""
            event_summary_from_mcp = ""
            event_attendees_list = []
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
                        
                        # Get summary from MCP (to verify it was returned)
                        # Check both 'title' (normalized) and 'summary' (raw MCP) fields
                        event_summary_from_mcp = evt.get("title", "") or evt.get("summary", "")
                        
                        # Get attendees list
                        attendees = evt.get("attendees_list", [])
                        attendees_details = evt.get("attendees_details", [])
                        if isinstance(attendees, list):
                            event_attendees_list = attendees
                        elif attendees_details and isinstance(attendees_details, list):
                            event_attendees_list = [a.get("email", "") for a in attendees_details if isinstance(a, dict)]
                        
                        event_details = f" | Date: {start_str} | Attendees: {len(event_attendees_list)} | Summary from MCP: '{event_summary_from_mcp}' | Attendee emails: {event_attendees_list}"
                        break
                if event_details:
                    break
            
            print(f"  {i}. Score {score:.2f}: '{title}' (ID: {event_id[:50]}...){event_details} in {part_id}", file=sys.stderr, flush=True)
    except Exception as e:
        import traceback
        print(f"[identify_event_from_natural_language] Error logging candidates: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
    
    # Log best match found
    try:
        if best_match:
            print(f"[identify_event_from_natural_language] Best match found: '{best_match.get('summary', '')}' (ID: {best_match.get('id', '')}) with score {best_score:.2f} (min: {min_score})", file=sys.stderr, flush=True)
        else:
            print(f"[identify_event_from_natural_language] No match found (best_score: {best_score:.2f}, min_score: {min_score})", file=sys.stderr, flush=True)
    except:
        pass
    
    # Return best match if it meets minimum threshold
    # Use a small epsilon (0.01) for floating point comparison to handle edge cases
    # This accounts for rounding differences in score calculations
    epsilon = 0.01
    if best_match and best_score >= (min_score - epsilon):
        try:
            print(f"[identify_event_from_natural_language] Returning match: score={best_score:.3f}, min={min_score:.3f}, threshold={min_score - epsilon:.3f}, match={best_match is not None}, participant={best_participant}", file=sys.stderr, flush=True)
        except:
            pass
        return (best_match, best_participant)
    
    try:
        print(f"[identify_event_from_natural_language] NOT returning match: score={best_score:.3f}, min={min_score:.3f}, threshold={min_score - epsilon:.3f}, match={best_match is not None}", file=sys.stderr, flush=True)
    except:
        pass
    return None

