#!/usr/bin/env python3
"""Check if any returned slots conflict with Email & Tasks events"""

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
from scheduling_orchestrator.fact_generator import _find_free_slots
from scheduling_orchestrator.python_solver import _rank_slots
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

normalized = normalize_events(events_by_participant=events, context_json=context_json)
slot_indexer = normalized["slot_indexer"]
busy_slots = normalized["busy_slots"]
work_hours_slots = normalized["work_hours_slots"]

all_slots = list(range(slot_indexer.total_slots))
duration_slots = 3  # 45 minutes
participants = ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]

free_slots = _find_free_slots(
    all_slots, busy_slots, work_hours_slots,
    participants, duration_slots, min_gap_slots=0
)

# Check Email & Tasks events specifically
et = pytz.timezone("America/New_York")
chad_events = events.get("cdorsey@concord.org", [])

print("="*80)
print("EMAIL & TASKS EVENTS")
print("="*80)
email_tasks_events = []
for event in chad_events:
    title = (event.get("title", "") or event.get("summary", "")).lower()
    if "email" in title and "task" in title:
        start_str = event.get("start", "")
        end_str = event.get("end", "")
        if start_str:
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
            
            email_tasks_events.append({
                "start": event_start,
                "end": event_end,
                "protected": event.get("protected", False),
                "flexible": event.get("flexible", True)
            })

print(f"Found {len(email_tasks_events)} Email & Tasks events:")
for i, event in enumerate(email_tasks_events, 1):
    print(f"  {i}. {event['start'].strftime('%A, %B %d, %Y %I:%M %p')} - {event['end'].strftime('%I:%M %p')} {event['start'].tzname()}")
    print(f"     Protected: {event['protected']}, Flexible: {event['flexible']}")

print("\n" + "="*80)
print("CHECKING IF FREE SLOTS CONFLICT")
print("="*80)

# Convert Email & Tasks events to slots
email_tasks_slots = set()
for event in email_tasks_events:
    start_slot = slot_indexer.datetime_to_slot(event["start"])
    end_slot = slot_indexer.datetime_to_slot(event["end"])
    # Mark all slots in the event as busy
    for slot in range(start_slot, end_slot):
        email_tasks_slots.add(slot)

print(f"\nEmail & Tasks events occupy {len(email_tasks_slots)} slots")

# Check Chad's busy slots
chad_busy = busy_slots.get("cdorsey@concord.org", set())
print(f"Chad's total busy slots: {len(chad_busy)}")

# Check if Email & Tasks slots are in Chad's busy slots
missing_from_busy = email_tasks_slots - chad_busy
if missing_from_busy:
    print(f"\n⚠️  PROBLEM: {len(missing_from_busy)} Email & Tasks slots are NOT marked as busy!")
    print("\nMissing slots (first 10):")
    for slot in sorted(list(missing_from_busy))[:10]:
        dt = slot_indexer.slot_to_datetime(slot)
        et_dt = dt.astimezone(et)
        print(f"  Slot {slot}: {et_dt.strftime('%A, %B %d, %Y %I:%M %p')} {et_dt.tzname()}")
else:
    print("\n✓ All Email & Tasks slots are correctly marked as busy")

# Check if any free slots overlap with Email & Tasks
conflicting_slots = free_slots.intersection(email_tasks_slots)
if conflicting_slots:
    print(f"\n⚠️  PROBLEM: {len(conflicting_slots)} free slots conflict with Email & Tasks events!")
    print("\nConflicting slots (first 10):")
    for slot in sorted(list(conflicting_slots))[:10]:
        dt = slot_indexer.slot_to_datetime(slot)
        et_dt = dt.astimezone(et)
        meeting_end = slot_indexer.slot_to_datetime(slot + duration_slots).astimezone(et)
        print(f"  Slot {slot}: {et_dt.strftime('%A, %B %d, %Y %I:%M %p')} - {meeting_end.strftime('%I:%M %p')} {et_dt.tzname()}")
else:
    print("\n✓ No free slots conflict with Email & Tasks events")

# Show all free slots to verify
print("\n" + "="*80)
print(f"ALL FREE SLOTS ({len(free_slots)} total)")
print("="*80)
print("\nFirst 20 free slots:")
for slot in sorted(list(free_slots))[:20]:
    dt = slot_indexer.slot_to_datetime(slot)
    et_dt = dt.astimezone(et)
    meeting_end = slot_indexer.slot_to_datetime(slot + duration_slots).astimezone(et)
    print(f"  Slot {slot}: {et_dt.strftime('%A, %B %d, %Y %I:%M %p')} - {meeting_end.strftime('%I:%M %p')} {et_dt.tzname()}")

