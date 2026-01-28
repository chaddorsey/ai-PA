#!/usr/bin/env python3
"""
Migrate existing working hours data to new structured schema.

This script:
1. Fetches all identities from Letta
2. Parses existing working_week and working_hours properties
3. Converts to new structured format:
   - timezone: IANA timezone string
   - working_hours: {"monday": {"start": "09:00", "end": "17:00"}, ...}
4. Updates identities via Letta API

Usage:
    python migrate_working_hours.py --dry-run  # Preview changes
    python migrate_working_hours.py            # Apply changes
"""

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Default timezone for staff (can be overridden per-identity)
DEFAULT_TIMEZONE = "America/New_York"

# Staff known to be on West Coast (update this list as needed)
WEST_COAST_STAFF = {
    # Add emails of staff in Pacific timezone
    # "example@concord.org": "America/Los_Angeles"
}

# Default working hours for full-time staff (9-5)
DEFAULT_FULL_TIME_HOURS = {
    "monday": {"start": "09:00", "end": "17:00"},
    "tuesday": {"start": "09:00", "end": "17:00"},
    "wednesday": {"start": "09:00", "end": "17:00"},
    "thursday": {"start": "09:00", "end": "17:00"},
    "friday": {"start": "09:00", "end": "17:00"},
    "saturday": None,
    "sunday": None,
}


def parse_time_12h(time_str: str) -> str:
    """Convert 12-hour time string to 24-hour format.

    Examples:
        "11:00AM" -> "11:00"
        "7:00PM" -> "19:00"
        "12:00PM" -> "12:00"
        "12:00AM" -> "00:00"
    """
    time_str = time_str.strip().upper()

    # Match patterns like "11:00AM", "7:00PM", "11:30AM"
    match = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM)', time_str)
    if not match:
        raise ValueError(f"Cannot parse time: {time_str}")

    hour, minute, period = match.groups()
    hour = int(hour)

    if period == "PM" and hour != 12:
        hour += 12
    elif period == "AM" and hour == 12:
        hour = 0

    return f"{hour:02d}:{minute}"


def parse_existing_working_hours(hours_str: str) -> Tuple[str, str]:
    """Parse existing working_hours format like '11:00AM-7:00PM'.

    Returns:
        Tuple of (start_time, end_time) in 24-hour format
    """
    parts = hours_str.split("-")
    if len(parts) != 2:
        raise ValueError(f"Cannot parse working hours: {hours_str}")

    start = parse_time_12h(parts[0])
    end = parse_time_12h(parts[1])
    return start, end


def parse_existing_working_week(week_str: str) -> List[str]:
    """Parse existing working_week format like 'Monday-Thursday'.

    Returns:
        List of day names (lowercase)
    """
    week_str = week_str.strip()

    # Handle range format like "Monday-Thursday"
    if "-" in week_str:
        days_order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        parts = week_str.lower().split("-")
        if len(parts) == 2:
            try:
                start_idx = days_order.index(parts[0].strip())
                end_idx = days_order.index(parts[1].strip())
                return days_order[start_idx:end_idx + 1]
            except ValueError:
                pass

    # Handle comma-separated list
    days = [d.strip().lower() for d in week_str.replace(",", " ").split()]
    return [d for d in days if d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]]


def get_property(properties: List[Dict], key: str) -> Optional[str]:
    """Get a property value by key."""
    for prop in properties:
        if isinstance(prop, dict) and prop.get("key") == key:
            return prop.get("value")
    return None


def build_new_working_hours(
    existing_week: Optional[str],
    existing_hours: Optional[str],
    default_hours: Tuple[str, str] = ("09:00", "17:00")
) -> Dict[str, Optional[Dict[str, str]]]:
    """Build new working_hours schema from existing data.

    Args:
        existing_week: Existing working_week value like "Monday-Thursday"
        existing_hours: Existing working_hours value like "11:00AM-7:00PM"
        default_hours: Default (start, end) times if not specified

    Returns:
        New working_hours dict in structured format
    """
    all_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    # Parse working days (default to Monday-Friday)
    if existing_week:
        working_days = set(parse_existing_working_week(existing_week))
    else:
        working_days = {"monday", "tuesday", "wednesday", "thursday", "friday"}

    # Parse hours (default to 9-5)
    if existing_hours:
        start, end = parse_existing_working_hours(existing_hours)
    else:
        start, end = default_hours

    # Build result
    result = {}
    for day in all_days:
        if day in working_days:
            result[day] = {"start": start, "end": end}
        else:
            result[day] = None

    return result


def fetch_all_identities() -> List[Dict]:
    """Fetch all identities from Letta API."""
    response = requests.get(f"{LETTA_BASE_URL}/v1/identities/", timeout=30)
    response.raise_for_status()
    return response.json()


def update_identity_properties(identity_id: str, properties: List[Dict]) -> bool:
    """Update an identity's properties via Letta API."""
    response = requests.patch(
        f"{LETTA_BASE_URL}/v1/identities/{identity_id}",
        json={"properties": properties},
        timeout=30
    )
    return response.status_code == 200


def migrate_identity(identity: Dict, dry_run: bool = True) -> Optional[Dict]:
    """Migrate a single identity to new working hours schema.

    Returns:
        Dict with migration details, or None if no migration needed
    """
    identity_id = identity.get("id")
    name = identity.get("name", "Unknown")
    email = identity.get("identifier_key", "")
    properties = identity.get("properties") or []

    # Get existing values
    existing_week = get_property(properties, "working_week")
    existing_hours = get_property(properties, "working_hours")
    existing_timezone = get_property(properties, "timezone")

    # Skip if no working hours data and already has timezone
    if not existing_week and not existing_hours and existing_timezone:
        return None

    # Build new properties list (preserve existing, update working hours)
    new_properties = []
    keys_to_skip = {"working_week", "working_hours", "timezone"}

    for prop in properties:
        if isinstance(prop, dict) and prop.get("key") not in keys_to_skip:
            new_properties.append(prop)

    # Add timezone
    timezone = WEST_COAST_STAFF.get(email, DEFAULT_TIMEZONE)
    new_properties.append({"key": "timezone", "value": timezone, "type": "string"})

    # Add structured working_hours if there was any working hours data
    if existing_week or existing_hours:
        new_working_hours = build_new_working_hours(existing_week, existing_hours)
        new_properties.append({
            "key": "working_hours",
            "value": json.dumps(new_working_hours),
            "type": "string"
        })

    migration_info = {
        "identity_id": identity_id,
        "name": name,
        "email": email,
        "existing_week": existing_week,
        "existing_hours": existing_hours,
        "existing_timezone": existing_timezone,
        "new_timezone": timezone,
        "new_working_hours": new_working_hours if (existing_week or existing_hours) else None,
    }

    if not dry_run:
        success = update_identity_properties(identity_id, new_properties)
        migration_info["success"] = success

    return migration_info


def main():
    parser = argparse.ArgumentParser(description="Migrate working hours to new schema")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    args = parser.parse_args()

    print(f"Fetching identities from {LETTA_BASE_URL}...")
    identities = fetch_all_identities()
    print(f"Found {len(identities)} identities\n")

    migrations = []
    for identity in identities:
        result = migrate_identity(identity, dry_run=args.dry_run)
        if result:
            migrations.append(result)

    if not migrations:
        print("No migrations needed.")
        return

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Migrations ({len(migrations)} identities):\n")

    for m in migrations:
        print(f"  {m['name']} ({m['email']})")
        if m['existing_week']:
            print(f"    existing working_week: {m['existing_week']}")
        if m['existing_hours']:
            print(f"    existing working_hours: {m['existing_hours']}")
        print(f"    -> timezone: {m['new_timezone']}")
        if m['new_working_hours']:
            # Summarize the new hours
            working_days = [d for d, h in m['new_working_hours'].items() if h]
            if working_days:
                first_day_hours = m['new_working_hours'][working_days[0]]
                print(f"    -> working_hours: {', '.join(d.title() for d in working_days)}")
                print(f"       hours: {first_day_hours['start']}-{first_day_hours['end']}")
        if not args.dry_run:
            status = "✓" if m.get('success') else "✗"
            print(f"    {status} {'Updated' if m.get('success') else 'FAILED'}")
        print()

    if args.dry_run:
        print("Run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
