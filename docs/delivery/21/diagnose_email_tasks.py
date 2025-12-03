#!/usr/bin/env python3
"""Diagnose Email & Tasks event processing"""

import json
import sys
from pathlib import Path
import pytz
from dateutil import parser

project_root = Path(__file__).parent.parent.parent.parent
env_path = project_root / '.env'
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "letta"))

from scheduling_orchestrator.normalizer import normalize_events
from test_e2e_orchestrator import load_events_from_example

events = load_events_from_example(Path(__file__).parent / "example_event_data.md")
context_json = {
    "timeframe": {
        "from": "2025-12-01",
        "to": "2025-12-12",
        "tz": "America/New_York"
    },
    "requester_id": "cdorsey@concord.org",
    "participants": [
        {"id": "cdorsey@concord.org", "email": "cdorsey@concord.org", "name": "Chad"},
        {"id": "sbrau@concord.org", "email": "sbrau@concord.org", "name": "Sue"},
        {"id": "dkehoe@concord.org", "email": "dkehoe@concord.org", "name": "Danielle"}
    ],
    "policy": {"hard": {"min_gap_min": 0}}
}

print("Loading events...")
print(f"Chad's raw events: {len(events.get('cdorsey@concord.org', []))}")

# Check raw events for Email & Tasks
chad_raw = events.get("cdorsey@concord.org", [])
email_tasks_raw = [e for e in chad_raw if "email" in (e.get("title", "") or e.get("summary", "")).lower() and "task" in (e.get("title", "") or e.get("summary", "")).lower()]
print(f"Email & Tasks events found in raw data: {len(email_tasks_raw)}")

print("\nNormalizing events...")
normalized = normalize_events(events_by_participant=events, context_json=context_json)
slot_indexer = normalized["slot_indexer"]
busy_slots = normalized["busy_slots"]

chad_busy = busy_slots.get("cdorsey@concord.org", set())
print(f"Chad's busy slots after normalization: {len(chad_busy)}")

# Check if Email & Tasks events were processed
et = pytz.timezone("America/New_York")
print("\nChecking Email & Tasks event slots:")
for event in email_tasks_raw[:5]:  # First 5
    title = event.get("title", "") or event.get("summary", "")
    start_str = event.get("start", "")
    end_str = event.get("end", "")
    
    try:
        event_start = parser.parse(start_str)
        if event_start.tzinfo is None:
            event_start = et.localize(event_start)
        else:
            event_start = event_start.astimezone(et)
        
        event_end = parser.parse(end_str) if end_str else event_start
        if event_end.tzinfo is None:
            event_end = et.localize(event_end)
        else:
            event_end = event_end.astimezone(et)
        
        # Convert to UTC for slot calculation
        event_start_utc = event_start.astimezone(pytz.UTC)
        event_end_utc = event_end.astimezone(pytz.UTC)
        
        # Get slots
        event_slots = slot_indexer.get_slots_in_range(event_start_utc, event_end_utc)
        
        print(f"\n  {title}")
        print(f"    Time: {event_start.strftime('%A, %B %d, %Y %I:%M %p')} - {event_end.strftime('%I:%M %p')} {event_start.tzname()}")
        print(f"    UTC: {event_start_utc.strftime('%Y-%m-%d %H:%M:%S')} - {event_end_utc.strftime('%H:%M:%S')}")
        print(f"    Slots: {sorted(event_slots)[:5]}... (first 5 of {len(event_slots)})")
        
        # Check if these slots are in Chad's busy slots
        missing = set(event_slots) - chad_busy
        if missing:
            print(f"    ⚠️  {len(missing)} slots NOT in busy_slots!")
            print(f"    Missing slots: {sorted(list(missing))[:10]}")
        else:
            print(f"    ✓ All {len(event_slots)} slots are in busy_slots")
            
    except Exception as e:
        print(f"    ERROR processing event: {e}")
        print(f"    start_str: {start_str}, end_str: {end_str}")

