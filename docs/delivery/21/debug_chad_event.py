#!/usr/bin/env python3
"""Debug why Chad's Dec 1 event isn't creating busy slots"""

import json
from pathlib import Path
from dateutil import parser
import pytz

from test_e2e_orchestrator import load_events_from_example
from scheduling_orchestrator.normalizer import normalize_events

print("="*80)
print("DEBUGGING CHAD'S DEC 1 EVENT")
print("="*80)

# Load events
events = load_events_from_example(Path(__file__).parent / "example_event_data.md")
chad_events = events.get("cdorsey@concord.org", [])

print(f"\nChad has {len(chad_events)} total events")

# Find the "Chad out" event on Dec 1
dec1_events = []
for event in chad_events:
    start_str = event.get("start", "")
    if start_str and "2025-12-01" in start_str:
        dec1_events.append(event)
        if "Chad out" in event.get("title", event.get("summary", "")):
            print(f"\nFound 'Chad out' event:")
            print(f"  ID: {event.get('id')}")
            print(f"  Start: {event.get('start')}")
            print(f"  End: {event.get('end')}")
            print(f"  Title: {event.get('title', event.get('summary', ''))}")

print(f"\nTotal Dec 1 events for Chad: {len(dec1_events)}")

# Now normalize
context_json = {
    'timeframe': {'from': '2025-12-01', 'to': '2025-12-12', 'tz': 'America/New_York'},
    'requester_id': 'cdorsey@concord.org',
    'participants': [
        {'id': 'cdorsey@concord.org', 'email': 'cdorsey@concord.org', 'name': 'Chad'},
    ],
    'policy': {'hard': {'min_gap_min': 0}}
}

print("\nNormalizing events...")
try:
    normalized = normalize_events(events_by_participant=events, context_json=context_json)
    slot_indexer = normalized['slot_indexer']
    busy_slots = normalized['busy_slots']
    chad_busy = busy_slots.get('cdorsey@concord.org', set())
    
    print(f"\nChad's busy slots after normalization: {len(chad_busy)}")
    
    # Check specific times
    et = pytz.timezone('America/New_York')
    test_times = [
        ('10:30 AM', '2025-12-01 10:30:00'),
        ('10:45 AM', '2025-12-01 10:45:00'),
        ('11:00 AM', '2025-12-01 11:00:00'),
        ('12:45 PM', '2025-12-01 12:45:00'),
        ('1:00 PM', '2025-12-01 13:00:00'),
    ]
    
    print("\n" + "="*80)
    print("Slot check:")
    print("="*80)
    for label, time_str in test_times:
        dt = et.localize(parser.parse(f'2025-12-01 {time_str}'))
        dt_utc = dt.astimezone(pytz.UTC)
        slot = slot_indexer.datetime_to_slot(dt_utc)
        if slot is not None:
            is_busy = slot in chad_busy
            status = 'BUSY' if is_busy else 'FREE'
            print(f'{label:12} (Slot {slot:3}): {status}')
        else:
            print(f'{label:12}: Slot None')
            
except Exception as e:
    print(f"\nERROR during normalization: {e}")
    import traceback
    traceback.print_exc()

