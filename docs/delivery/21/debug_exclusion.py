#!/usr/bin/env python3
"""Debug why slots are being excluded"""

import json
from pathlib import Path
from dateutil import parser
import pytz

from test_e2e_orchestrator import load_events_from_example
from scheduling_orchestrator.normalizer import normalize_events
from scheduling_orchestrator.fact_generator import _find_free_slots

events = load_events_from_example(Path(__file__).parent / "example_event_data.md")
context_json = {
    'timeframe': {'from': '2025-12-01', 'to': '2025-12-12', 'tz': 'America/New_York'},
    'requester_id': 'cdorsey@concord.org',
    'participants': [
        {'id': 'cdorsey@concord.org', 'email': 'cdorsey@concord.org', 'name': 'Chad'},
        {'id': 'sbrau@concord.org', 'email': 'sbrau@concord.org', 'name': 'Sue'},
        {'id': 'dkehoe@concord.org', 'email': 'dkehoe@concord.org', 'name': 'Danielle'}
    ],
    'policy': {'hard': {'min_gap_min': 0}}
}

normalized = normalize_events(events_by_participant=events, context_json=context_json)
slot_indexer = normalized['slot_indexer']
busy_slots = normalized['busy_slots']
work_hours_slots = normalized['work_hours_slots']

et = pytz.timezone('America/New_York')
test_slot = 27  # 10:45 AM
duration_slots = 3

print("="*80)
print(f"DEBUGGING SLOT {test_slot} (10:45 AM)")
print("="*80)

dt = slot_indexer.slot_to_datetime(test_slot)
et_dt = dt.astimezone(et)
print(f"Slot {test_slot} = {et_dt.strftime('%I:%M %p %Z')}")

participants = ['cdorsey@concord.org', 'sbrau@concord.org', 'dkehoe@concord.org']

print(f"\nChecking each participant:")
for p in participants:
    p_busy = busy_slots.get(p, set())
    p_work = work_hours_slots.get(p, set())
    
    meeting_slots = set(range(test_slot, test_slot + duration_slots))
    busy_overlap = meeting_slots.intersection(p_busy)
    work_overlap = meeting_slots.intersection(p_work)
    
    is_busy = len(busy_overlap) > 0
    in_work_hours = len(work_overlap) == duration_slots
    
    print(f"\n  {p}:")
    print(f"    Busy slots: {len(p_busy)} total")
    print(f"    Work hour slots: {len(p_work)} total")
    print(f"    Meeting slots: {meeting_slots}")
    print(f"    Busy overlap: {busy_overlap} ({'BUSY' if is_busy else 'FREE'})")
    print(f"    Work hours overlap: {work_overlap} ({'IN WORK HOURS' if in_work_hours else 'OUT OF WORK HOURS'})")
    print(f"    Result: {'BUSY' if is_busy else ('NOT IN WORK HOURS' if not in_work_hours else 'FREE')}")

# Check why _find_free_slots excludes it
print(f"\n" + "="*80)
print("Checking _find_free_slots logic:")
print("="*80)

all_slots = list(range(slot_indexer.total_slots))
free_slots = _find_free_slots(
    all_slots, busy_slots, work_hours_slots,
    participants, duration_slots, min_gap_slots=0
)

print(f"Slot {test_slot} in free_slots: {test_slot in free_slots}")

