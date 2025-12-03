#!/usr/bin/env python3
"""Test that Chad's Dec 1 event creates busy slots"""

import json
from pathlib import Path
from dateutil import parser
import pytz

from test_e2e_orchestrator import load_events_from_example
from scheduling_orchestrator.normalizer import normalize_events
from scheduling_orchestrator.fact_generator import _find_free_slots

print("="*80)
print("TESTING CHAD'S DEC 1 EVENT")
print("="*80)

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

print("\nNormalizing events...")
normalized = normalize_events(events_by_participant=events, context_json=context_json)
slot_indexer = normalized['slot_indexer']
busy_slots = normalized['busy_slots']
work_hours_slots = normalized['work_hours_slots']

chad_busy = busy_slots.get('cdorsey@concord.org', set())
print(f"Chad's busy slots: {len(chad_busy)}")

# Check specific problematic slots
et = pytz.timezone('America/New_York')
problematic_times = [
    ('10:30 AM', '2025-12-01 10:30:00'),  # Start of "Chad out"
    ('10:45 AM', '2025-12-01 10:45:00'),  # Should be BUSY
    ('11:00 AM', '2025-12-01 11:00:00'),  # Should be BUSY
    ('12:30 PM', '2025-12-01 12:30:00'),  # Should be BUSY (last slot of event)
    ('12:45 PM', '2025-12-01 12:45:00'),  # Event ends here - should NOT be busy
    ('1:00 PM', '2025-12-01 13:00:00'),   # Should be FREE
]

print("\n" + "="*80)
print("Checking if slots are marked as busy:")
print("="*80)
for label, time_str in problematic_times:
    dt_parsed = parser.parse(f'2025-12-01 {time_str}')
    if dt_parsed.tzinfo is None:
        dt = et.localize(dt_parsed)
    else:
        dt = dt_parsed.astimezone(et)
    dt_utc = dt.astimezone(pytz.UTC)
    slot = slot_indexer.datetime_to_slot(dt_utc)
    if slot is not None:
        is_busy = slot in chad_busy
        status = '✓ BUSY' if is_busy else '✗ FREE'
        expected = 'BUSY' if label in ['10:30 AM', '10:45 AM', '11:00 AM', '12:30 PM'] else 'FREE'
        match = '✓' if (expected == 'BUSY' and is_busy) or (expected == 'FREE' and not is_busy) else '✗ MISMATCH'
        print(f'{label:12} (Slot {slot:3}): {status} (expected {expected}) {match}')
    else:
        print(f'{label:12}: Slot None')

# Now check free slots
print("\n" + "="*80)
print("Checking free slots calculation:")
print("="*80)
all_slots = list(range(slot_indexer.total_slots))
duration_slots = 3  # 45 minutes
participants = ['cdorsey@concord.org', 'sbrau@concord.org', 'dkehoe@concord.org']

free_slots = _find_free_slots(
    all_slots, busy_slots, work_hours_slots,
    participants, duration_slots, min_gap_slots=0
)

print(f"Total free slots found: {len(free_slots)}")

# Check if problematic slots are in free_slots
problematic_slots_to_check = []
for label, time_str in [('10:45 AM', '2025-12-01 10:45:00'), ('11:00 AM', '2025-12-01 11:00:00')]:
    dt_parsed = parser.parse(f'2025-12-01 {time_str}')
    if dt_parsed.tzinfo is None:
        dt = et.localize(dt_parsed)
    else:
        dt = dt_parsed.astimezone(et)
    dt_utc = dt.astimezone(pytz.UTC)
    slot = slot_indexer.datetime_to_slot(dt_utc)
    if slot is not None:
        problematic_slots_to_check.append((label, slot))

print("\nChecking if problematic slots are incorrectly marked as free:")
for label, slot in problematic_slots_to_check:
    is_free = slot in free_slots
    status = '✗ INCORRECTLY FREE' if is_free else '✓ Correctly excluded'
    print(f'{label:12} (Slot {slot:3}): {status}')

