#!/usr/bin/env python3
"""Check Sue's events on December 1"""

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

# Get Sue's events
sue_events = events.get("sbrau@concord.org", [])
et = pytz.timezone("America/New_York")

print("="*80)
print("SUE'S (sbrau@concord.org) EVENTS ON DECEMBER 1, 2025")
print("="*80)
print()

dec1_events = []
for event in sue_events:
    start_str = event.get("start", "")
    if start_str and "2025-12-01" in start_str:
        try:
            start_dt = parser.parse(start_str)
            if start_dt.tzinfo is None:
                start_dt = et.localize(start_dt)
            else:
                start_dt = start_dt.astimezone(et)
            
            end_str = event.get("end", "")
            end_dt = parser.parse(end_str) if end_str else start_dt
            if end_dt.tzinfo is None:
                end_dt = et.localize(end_dt)
            else:
                end_dt = end_dt.astimezone(et)
            
            title = event.get("title", "") or event.get("summary", "")
            dec1_events.append({
                "title": title,
                "start": start_dt,
                "end": end_dt
            })
        except Exception as e:
            print(f"Error parsing event: {e}")
            print(f"  start_str: {start_str}")

if dec1_events:
    dec1_events.sort(key=lambda x: x["start"])
    print(f"Found {len(dec1_events)} event(s):\n")
    for event in dec1_events:
        print(f"{event['start'].strftime('%I:%M %p')} - {event['end'].strftime('%I:%M %p')} {event['start'].tzname()}: {event['title']}")
else:
    print("No events found for Sue on December 1, 2025")

print("\n" + "="*80)
print("CHECKING NORMALIZATION")
print("="*80)

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

normalized = normalize_events(events_by_participant=events, context_json=context_json)
slot_indexer = normalized["slot_indexer"]
busy_slots = normalized["busy_slots"]

sue_busy = busy_slots.get("sbrau@concord.org", set())
print(f"\nSue's busy slots: {len(sue_busy)}")

# Check slots between 1:00 PM and 3:00 PM on Dec 1
print("\nChecking slots 1:00 PM - 3:00 PM on Dec 1:")
from datetime import datetime, timedelta
dec1_1pm_et = et.localize(datetime(2025, 12, 1, 13, 0, 0))
dec1_3pm_et = et.localize(datetime(2025, 12, 1, 15, 0, 0))
dec1_1pm_utc = dec1_1pm_et.astimezone(pytz.UTC)
dec1_3pm_utc = dec1_3pm_et.astimezone(pytz.UTC)

start_slot = slot_indexer.datetime_to_slot(dec1_1pm_utc)
end_slot = slot_indexer.datetime_to_slot(dec1_3pm_utc)

if start_slot is not None and end_slot is not None:
    print(f"Slot range: {start_slot} to {end_slot}")
    print(f"\nSue's busy slots in this range:")
    busy_in_range = [s for s in range(start_slot, end_slot + 1) if s in sue_busy]
    if busy_in_range:
        for slot in busy_in_range:
            slot_dt = slot_indexer.slot_to_datetime(slot)
            slot_et = slot_dt.astimezone(et)
            print(f"  Slot {slot}: {slot_et.strftime('%I:%M %p')} - {(slot_et + timedelta(minutes=15)).strftime('%I:%M %p')} {slot_et.tzname()}")
    else:
        print("  ⚠️  NO BUSY SLOTS FOUND - This is a problem!")

