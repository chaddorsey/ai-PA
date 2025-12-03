#!/usr/bin/env python3
"""Check horizon setup"""

import json
from pathlib import Path
from dateutil import parser
import pytz

from test_e2e_orchestrator import load_events_from_example
from scheduling_orchestrator.normalizer import normalize_events

events = load_events_from_example(Path(__file__).parent / "example_event_data.md")
context_json = {
    'timeframe': {'from': '2025-12-01', 'to': '2025-12-12', 'tz': 'America/New_York'},
    'requester_id': 'cdorsey@concord.org',
    'participants': [],
    'policy': {'hard': {'min_gap_min': 0}}
}

normalized = normalize_events(events_by_participant=events, context_json=context_json)
slot_indexer = normalized['slot_indexer']

et = pytz.timezone('America/New_York')
utc = pytz.UTC

print("="*80)
print("HORIZON SETUP")
print("="*80)
print(f"Horizon start (UTC): {slot_indexer.horizon_start}")
print(f"Horizon start (ET):  {slot_indexer.horizon_start.astimezone(et)}")
print(f"Horizon end (UTC):   {slot_indexer.horizon_end}")
print(f"Horizon end (ET):    {slot_indexer.horizon_end.astimezone(et)}")
print(f"Total slots: {slot_indexer.total_slots}")

print("\n" + "="*80)
print("SAMPLE SLOTS")
print("="*80)

# Check slot 0, 26, 27, 28 (around 10:30-11:00 AM)
for slot in [0, 26, 27, 28, 43, 44]:
    dt = slot_indexer.slot_to_datetime(slot)
    if dt:
        et_dt = dt.astimezone(et)
        print(f"Slot {slot:3}: {dt} UTC = {et_dt.strftime('%a %b %d %I:%M %p %Z')}")

# Now check the actual event time
print("\n" + "="*80)
print("CHAD'S EVENT TIME")
print("="*80)
event_start_str = "2025-12-01T10:30:00-05:00"
event_start = parser.parse(event_start_str)
event_start_utc = event_start.astimezone(pytz.UTC)
print(f"Event start: {event_start} = {event_start_utc} UTC")

slot = slot_indexer.datetime_to_slot(event_start_utc)
print(f"Slot for event start: {slot}")
if slot is not None:
    slot_dt = slot_indexer.slot_to_datetime(slot)
    print(f"Slot {slot} = {slot_dt} UTC = {slot_dt.astimezone(et)} ET")

