#!/usr/bin/env python3
"""Test that meetings extending beyond work hours are rejected"""

import sys
from pathlib import Path
import pytz
from datetime import datetime

project_root = Path(__file__).parent.parent.parent.parent
env_path = project_root / '.env'
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "letta"))

from scheduling_orchestrator.normalizer import normalize_events
from scheduling_orchestrator.fact_generator import _find_free_slots
from scheduling_orchestrator.slot_indexer import SlotIndexer
from test_e2e_orchestrator import load_events_from_example

events = load_events_from_example(Path(__file__).parent / "example_event_data.md")
context_json = {
    "timeframe": {
        "from": "2025-12-01",
        "to": "2025-12-01",  # Just one day for testing
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

et = pytz.timezone("America/New_York")

print("="*80)
print("TESTING WORK HOURS BOUNDARY")
print("="*80)

# Check work hours for one participant
participant = "cdorsey@concord.org"
work_slots = work_hours_slots.get(participant, set())
print(f"\nParticipant: {participant}")
print(f"Work hours slots: {len(work_slots)} slots")

# Find the last work hours slot
if work_slots:
    last_work_slot = max(work_slots)
    last_work_slot_dt = slot_indexer.slot_to_datetime(last_work_slot)
    last_work_slot_et = last_work_slot_dt.astimezone(et)
    print(f"Last work hours slot: {last_work_slot} ({last_work_slot_et.strftime('%I:%M %p')} - {(last_work_slot_et + timedelta(minutes=15)).strftime('%I:%M %p')} {last_work_slot_et.tzname()})")

# Test 45-minute meeting (3 slots)
duration_slots = 3
all_slots = list(range(slot_indexer.total_slots))
participants = ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]

free_slots = _find_free_slots(
    all_slots, busy_slots, work_hours_slots,
    participants, duration_slots, min_gap_slots=0
)

print(f"\nFree slots found: {len(free_slots)}")

# Check slots near end of workday
print("\nChecking slots near end of workday:")
print("(Work hours should end at 5:00 PM = 17:00)")

test_slots = sorted(list(free_slots))[-10:] if free_slots else []
for slot in test_slots:
    slot_dt = slot_indexer.slot_to_datetime(slot)
    slot_et = slot_dt.astimezone(et)
    meeting_end_slot = slot + duration_slots - 1
    meeting_end_dt = slot_indexer.slot_to_datetime(meeting_end_slot)
    meeting_end_et = meeting_end_dt.astimezone(et)
    meeting_end_time = (meeting_end_dt + timedelta(minutes=15)).astimezone(et)
    
    # Check if all meeting slots are in work hours
    meeting_slots = range(slot, slot + duration_slots)
    all_in_work_hours = all(s in work_slots for s in meeting_slots)
    
    status = "✓" if all_in_work_hours else "✗"
    print(f"  {status} Slot {slot}: {slot_et.strftime('%I:%M %p')} - {meeting_end_time.strftime('%I:%M %p')} (ends {meeting_end_time.strftime('%I:%M %p')})")

# Find slots that would extend beyond 5:00 PM
print("\nChecking for slots that would extend beyond 5:00 PM:")
problem_slots = []
for slot in free_slots:
    slot_dt = slot_indexer.slot_to_datetime(slot)
    slot_et = slot_dt.astimezone(et)
    meeting_end_slot = slot + duration_slots - 1
    meeting_end_dt = slot_indexer.slot_to_datetime(meeting_end_slot)
    meeting_end_time = (meeting_end_dt + timedelta(minutes=15)).astimezone(et)
    
    # Check if meeting ends after 5:00 PM
    if meeting_end_time.hour > 17 or (meeting_end_time.hour == 17 and meeting_end_time.minute > 0):
        problem_slots.append((slot, slot_et, meeting_end_time))

if problem_slots:
    print(f"  ⚠️  Found {len(problem_slots)} slots that extend beyond 5:00 PM:")
    for slot, start, end in problem_slots[:5]:
        print(f"    Slot {slot}: {start.strftime('%I:%M %p')} - {end.strftime('%I:%M %p')}")
else:
    print("  ✓ No slots extend beyond 5:00 PM")

