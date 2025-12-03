#!/usr/bin/env python3
"""Minimal test of event to slot conversion"""

from datetime import datetime, timedelta
import pytz
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'letta'))

from scheduling_orchestrator.slot_indexer import SlotIndexer

# Set up horizon: Dec 1-12, 2025, Eastern time
et = pytz.timezone('America/New_York')
horizon_start_et = et.localize(datetime(2025, 12, 1, 0, 0, 0))  # Midnight EST Dec 1
horizon_end_et = et.localize(datetime(2025, 12, 13, 0, 0, 0))   # Midnight EST Dec 13

horizon_start_utc = horizon_start_et.astimezone(pytz.UTC)
horizon_end_utc = horizon_end_et.astimezone(pytz.UTC)

print("="*80)
print("HORIZON SETUP")
print("="*80)
print(f"Start ET: {horizon_start_et}")
print(f"Start UTC: {horizon_start_utc}")
print(f"End ET: {horizon_end_et}")
print(f"End UTC: {horizon_end_utc}")

slot_indexer = SlotIndexer(horizon_start_utc, horizon_end_utc)
print(f"Total slots: {slot_indexer.total_slots}")

# Test event: 10:30 AM - 12:45 PM EST on Dec 1
event_start_et = et.localize(datetime(2025, 12, 1, 10, 30, 0))
event_end_et = et.localize(datetime(2025, 12, 1, 12, 45, 0))

event_start_utc = event_start_et.astimezone(pytz.UTC)
event_end_utc = event_end_et.astimezone(pytz.UTC)

print("\n" + "="*80)
print("EVENT")
print("="*80)
print(f"Event: {event_start_et.strftime('%I:%M %p')} - {event_end_et.strftime('%I:%M %p')} ET")
print(f"Event UTC: {event_start_utc} - {event_end_utc}")

# Get slots
event_slots = slot_indexer.get_slots_in_range(event_start_utc, event_end_utc)
print(f"\nEvent slots: {sorted(event_slots)}")
print(f"Number of slots: {len(event_slots)}")

# Show what times these slots represent
print("\nSlot times (ET):")
for slot in sorted(event_slots)[:10]:
    slot_dt = slot_indexer.slot_to_datetime(slot)
    et_dt = slot_dt.astimezone(et)
    print(f"  Slot {slot}: {et_dt.strftime('%I:%M %p')}")

# Check the slots we expect
print("\n" + "="*80)
print("VERIFICATION")
print("="*80)
expected_slots = []
current_time = event_start_et
while current_time < event_end_et:
    slot = slot_indexer.datetime_to_slot(current_time.astimezone(pytz.UTC))
    if slot is not None and slot not in expected_slots:
        expected_slots.append(slot)
    current_time += timedelta(minutes=15)

print(f"Expected slots (manually calculated): {sorted(expected_slots)}")
print(f"Actual slots from get_slots_in_range: {sorted(event_slots)}")
print(f"Match: {set(expected_slots) == set(event_slots)}")

if set(expected_slots) != set(event_slots):
    missing = set(expected_slots) - set(event_slots)
    extra = set(event_slots) - set(expected_slots)
    if missing:
        print(f"Missing from result: {sorted(missing)}")
    if extra:
        print(f"Extra in result: {sorted(extra)}")

