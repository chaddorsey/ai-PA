"""
Calendly Pre-filled Booking Link Generator

Creates booking URLs with pre-filled form data, avoiding CAPTCHA issues
while still saving user time by auto-filling fields.
"""

from typing import Dict, Any, List, Optional
from urllib.parse import urlencode, quote
from datetime import datetime


def create_booking_link(
    url: str,
    date: str,
    time: str,
    name: str,
    email: str,
    timezone: str = "America/New_York",
    custom_fields: Optional[Dict[str, str]] = None,
    guests: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Generate a pre-filled Calendly booking link.
    
    Args:
        url: Calendly event URL (must include event slug)
        date: Date in YYYY-MM-DD format
        time: Time in HH:MM or h:mma format
        name: Invitee name
        email: Invitee email
        timezone: IANA timezone
        custom_fields: Custom field answers (matched to question_0, question_1, etc.)
        guests: Guest email addresses
        
    Returns:
        Dict with booking_url and metadata
        
    Raises:
        ValueError: If URL is not a full event URL
    """
    custom_fields = custom_fields or {}
    guests = guests or []
    
    # Validate that this is a full event URL (not just a profile)
    # Profile URL: https://calendly.com/username
    # Event URL:   https://calendly.com/username/event-slug
    url_parts = url.rstrip('/').split('/')
    
    # Should have at least: ['https:', '', 'calendly.com', 'username', 'event-slug']
    if len(url_parts) < 5:
        raise ValueError(
            f"URL must be a full event URL, not a profile URL.\n"
            f"❌ Received: {url}\n"
            f"✅ Expected format: https://calendly.com/username/event-slug\n"
            f"\n"
            f"Example: https://calendly.com/zarek-drozda/30min\n"
            f"\n"
            f"To get the event URL:\n"
            f"1. Use calendly_slots tool first to find available events\n"
            f"2. Each event in the response has a 'url' field with the full event URL\n"
            f"3. Use that URL for booking"
        )
    
    # Parse time to ISO format
    time_normalized = _normalize_time(time, timezone, date)
    
    # Build base URL with time slot
    base_url = url.rstrip('/')
    if not time_normalized:
        # If can't parse time, just use the base event URL
        slot_url = base_url
    else:
        slot_url = f"{base_url}/{time_normalized}"
    
    # Build query parameters
    params = {
        'name': name,
        'email': email
    }
    
    # Add custom fields (map to question_0, question_1, etc.)
    # Since we don't know which field is which without loading the page,
    # we'll add them with generic keys and document that user may need to fill
    for i, (key, value) in enumerate(custom_fields.items()):
        params[f'question_{i}'] = value
        # Also try the 'a' prefix pattern
        params[f'a{i+1}'] = value
    
    # Note: Guests typically can't be pre-filled via URL
    # They must be added manually
    
    # Build final URL
    query_string = urlencode(params, quote_via=quote)
    booking_url = f"{slot_url}?{query_string}"
    
    return {
        "booking_url": booking_url,
        "event_url": url,
        "date": date,
        "time": time,
        "timezone": timezone,
        "prefilled_fields": {
            "name": name,
            "email": email,
            "custom_fields": custom_fields
        },
        "manual_fields": {
            "guests": guests if guests else [],
            "note": "Guests must be added manually via 'Add Guests' button"
        },
        "instructions": [
            "1. Click the booking_url link",
            "2. Verify the pre-filled information is correct",
            f"3. Add guests manually: {', '.join(guests)}" if guests else "3. No guests to add",
            "4. Click 'Schedule Event' button",
            "5. Complete CAPTCHA if prompted"
        ]
    }


def _normalize_time(time_str: str, timezone: str, date_str: str) -> Optional[str]:
    """
    Convert time string to ISO format for Calendly URL.
    
    Args:
        time_str: Time in HH:MM or h:mma format
        timezone: IANA timezone
        date_str: Date in YYYY-MM-DD
        
    Returns:
        ISO format string like "2025-10-29T12:30:00-04:00" or None if parsing fails
    """
    try:
        time_normalized = time_str.strip().lower()
        
        # Parse to datetime
        if 'am' in time_normalized or 'pm' in time_normalized:
            # 12-hour format
            dt = datetime.strptime(time_normalized.replace(' ', ''), "%I:%M%p")
        else:
            # 24-hour format
            dt = datetime.strptime(time_normalized, "%H:%M")
        
        # Combine with date
        full_dt = datetime.fromisoformat(f"{date_str}T{dt.strftime('%H:%M')}:00")
        
        # Calendly expects timezone offset in the URL
        # For America/New_York, that's typically -04:00 (EDT) or -05:00 (EST)
        # We'll use a simple heuristic for common timezones
        # (In production, would use proper timezone library)
        
        tz_offsets = {
            "America/New_York": "-04:00",  # EDT (most of the year)
            "America/Chicago": "-05:00",
            "America/Denver": "-06:00",
            "America/Los_Angeles": "-07:00",
            "Europe/London": "+01:00",
            "UTC": "+00:00"
        }
        
        offset = tz_offsets.get(timezone, "-04:00")  # Default to EDT
        
        return f"{full_dt.isoformat()}{offset}"
        
    except Exception:
        return None

