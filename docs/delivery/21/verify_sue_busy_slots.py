#!/usr/bin/env python3
"""Verify Sue's events are correctly marked as busy"""

import sys
from pathlib import Path
from datetime import timedelta
import pytz
from dateutil import parser

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "letta"))

from scheduling_orchestrator.normalizer import normalize_events
from scheduling_orchestrator.fact_generator import _find_free_slots
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

et = pytz.timezone("America/New_York")
sue_busy = busy_slots.get("sbrau@concord.org", set())

print("="*80)
print("VERIFYING SUE'S BUSY SLOTS ON DECEMBER 1")
print("="*80)

# Sue's events on Dec 1 from the file:
# 1. "Insource / Concord Check In": 1:00 PM - 1:25 PM
#    This should create busy slots: 1:00-1:15, 1:15-1:30 (1:25 PM ends in the 1:15-1:30 slot)

dec1_1pm_dt = parser.parse("2025-12-01T13:00:00-05:00")
dec1_125pm_dt = parser.parse("2025-12-01T13:25:00-05:00")
dec1_1pm_et = dec1_1pm_dt.astimezone(et) if dec1_1pm_dt.tzinfo else et.localize(dec1_1pm_dt)
dec1_125pm_et = dec1_125pm_dt.astimezone(et) if dec1_125pm_dt.tzinfo else et.localize(dec1_125pm_dt)
dec1_1pm_utc = dec1_1pm_et.astimezone(pytz.UTC)
dec1_125pm_utc = dec1_125pm_et.astimezone(pytz.UTC)

expected_slots = slot_indexer.get_slots_in_range(dec1_1pm_utc, dec1_125pm_utc)
print(f"\nEvent: 'Insource / Concord Check In' (1:00 PM - 1:25 PM)")
print(f"Expected busy slots: {sorted(expected_slots)}")

print(f"\nSue's actual busy slots on Dec 1:")
dec1_sue_busy = []
for slot in sorted(sue_busy):
    slot_dt = slot_indexer.slot_to_datetime(slot)
    slot_et = slot_dt.astimezone(et)
    if slot_et.strftime("%Y-%m-%d") == "2025-12-01":
        dec1_sue_busy.append(slot)
        print(f"  Slot {slot}: {slot_et.strftime('%I:%M %p')} - {(slot_et + timedelta(minutes=15)).strftime('%I:%M %p')} {slot_et.tzname()}")

print(f"\nTotal Sue busy slots on Dec 1: {len(dec1_sue_busy)}")

# Check if expected slots are in busy
missing = set(expected_slots) - set(dec1_sue_busy)
if missing:
    print(f"\n⚠️  PROBLEM: Expected slots {sorted(missing)} are NOT marked as busy!")
else:
    print(f"\n✓ All expected slots are marked as busy")

# Now check free slots that conflict
print("\n" + "="*80)
print("CHECKING FREE SLOTS FOR CONFLICTS")
print("="*80)

duration_slots = 3  # 45 minutes
all_slots = list(range(slot_indexer.total_slots))
participants = ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
work_hours_slots = normalized["work_hours_slots"]

free_slots = _find_free_slots(
    all_slots, busy_slots, work_hours_slots,
    participants, duration_slots, min_gap_slots=0
)

# Check slots that start between 1:00 PM and 3:00 PM on Dec 1
print("\nFree slots between 1:00 PM - 3:00 PM on Dec 1:")
problem_slots = []
for slot in sorted(free_slots):
    slot_dt = slot_indexer.slot_to_datetime(slot)
    slot_et = slot_dt.astimezone(et)
    if slot_et.strftime("%Y-%m-%d") == "2025-12-01" and 13 <= slot_et.hour < 15:
        meeting_slots = range(slot, slot + duration_slots)
        # Check if any meeting slot conflicts with Sue's busy slots
        conflict = set(meeting_slots).intersection(sue_busy)
        if conflict:
            problem_slots.append((slot, slot_et, conflict))
            print(f"  ⚠️  Slot {slot}: {slot_et.strftime('%I:%M %p')} - conflicts with Sue's slots: {sorted(conflict)}")
        else:
            print(f"  ✓ Slot {slot}: {slot_et.strftime('%I:%M %p')} - no conflict")

if problem_slots:
    print(f"\n⚠️  Found {len(problem_slots)} conflicting free slots!")
else:
    print("\n✓ No conflicts found")

