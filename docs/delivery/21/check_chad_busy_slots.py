#!/usr/bin/env python3
"""Check if Chad's Dec 1 events are being marked as busy correctly"""

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
    'participants': [
        {'id': 'cdorsey@concord.org', 'email': 'cdorsey@concord.org', 'name': 'Chad'},
    ],
    'policy': {'hard': {'min_gap_min': 0}}
}

print("Normalizing events...")
normalized = normalize_events(events_by_participant=events, context_json=context_json)
slot_indexer = normalized['slot_indexer']
busy_slots = normalized['busy_slots']
chad_busy = busy_slots.get('cdorsey@concord.org', set())

print(f"\nChad's total busy slots: {len(chad_busy)}")

# Check specific times on Dec 1
et = pytz.timezone('America/New_York')
test_times = [
    ('10:30 AM', '2025-12-01 10:30:00'),  # Start of "Chad out"
    ('10:45 AM', '2025-12-01 10:45:00'),  # Should be busy
    ('11:00 AM', '2025-12-01 11:00:00'),  # Should be busy
    ('12:45 PM', '2025-12-01 12:45:00'),  # End of "Chad out"
    ('1:00 PM', '2025-12-01 13:00:00'),   # Should be free
    ('2:30 PM', '2025-12-01 14:30:00'),   # Should be free
]

print("\n" + "="*80)
print("Checking specific slots on December 1:")
print("="*80)
for label, time_str in test_times:
    dt = et.localize(parser.parse(f'2025-12-01 {time_str}'))
    dt_utc = dt.astimezone(pytz.UTC)
    slot = slot_indexer.datetime_to_slot(dt_utc)
    if slot is not None:
        is_busy = slot in chad_busy
        status = '✓ BUSY' if is_busy else '✗ FREE (ERROR!)'
        print(f'{label:12} (Slot {slot:3}): {status}')
    else:
        print(f'{label:12}: Slot None (outside horizon)')

