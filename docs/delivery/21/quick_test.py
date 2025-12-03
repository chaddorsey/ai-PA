#!/usr/bin/env python3
"""Quick test to verify Email & Tasks events are being processed"""

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

print("Normalizing events...")
normalized = normalize_events(events_by_participant=events, context_json=context_json)
slot_indexer = normalized["slot_indexer"]
busy_slots = normalized["busy_slots"]

chad_busy = busy_slots.get("cdorsey@concord.org", set())
print(f"Chad's busy slots: {len(chad_busy)}")

# Check a few Email & Tasks slots specifically
et = pytz.timezone("America/New_York")
email_tasks_events = [e for e in events.get("cdorsey@concord.org", []) if "email" in str(e.get("title", "")).lower() and "task" in str(e.get("title", "")).lower()]

print(f"\nEmail & Tasks events: {len(email_tasks_events)}")
print("\nChecking if Email & Tasks slots are marked as busy:")
conflicts = 0
for event in email_tasks_events[:3]:  # Check first 3
    start_str = event.get("start", "")
    end_str = event.get("end", "")
    if start_str and end_str:
        try:
            start_dt = parser.parse(start_str)
            if start_dt.tzinfo is None:
                start_dt = et.localize(start_dt)
            else:
                start_dt = start_dt.astimezone(et)
            
            end_dt = parser.parse(end_str)
            if end_dt.tzinfo is None:
                end_dt = et.localize(end_dt)
            else:
                end_dt = end_dt.astimezone(et)
            
            start_utc = start_dt.astimezone(pytz.UTC)
            end_utc = end_dt.astimezone(pytz.UTC)
            
            event_slots = slot_indexer.get_slots_in_range(start_utc, end_utc)
            missing = set(event_slots) - chad_busy
            if missing:
                conflicts += len(missing)
                print(f"  {start_dt.strftime('%A, %B %d, %I:%M %p')}: {len(missing)} slots NOT marked busy")
            else:
                print(f"  {start_dt.strftime('%A, %B %d, %I:%M %p')}: ✓ All slots marked busy")
        except Exception as e:
            print(f"  Error: {e}")

if conflicts == 0:
    print("\n✓ All Email & Tasks events are correctly marked as busy")
else:
    print(f"\n⚠️  {conflicts} Email & Tasks slots are not marked as busy")

print("\nReady to run full orchestrator test!")

