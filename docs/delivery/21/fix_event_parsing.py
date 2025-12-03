#!/usr/bin/env python3
"""Fix event parsing and verify Chad's event creates busy slots"""

import json
from pathlib import Path
from dateutil import parser
from datetime import datetime
import pytz

from test_e2e_orchestrator import load_events_from_example
from scheduling_orchestrator.normalizer import normalize_events

print("="*80)
print("CHECKING EVENT PARSING")
print("="*80)

# Load Chad's events
events = load_events_from_example(Path(__file__).parent / "example_event_data.md")
chad_events = events.get("cdorsey@concord.org", [])

# Find the "Chad out" event
chad_out_event = None
for event in chad_events:
    if "Chad out" in event.get("title", event.get("summary", "")) and "2025-12-01" in event.get("start", ""):
        chad_out_event = event
        break

if chad_out_event:
    print(f"\nFound 'Chad out' event:")
    print(f"  Raw start: {chad_out_event.get('start')}")
    print(f"  Raw end: {chad_out_event.get('end')}")
    
    # Parse it the way normalizer does
    start_str = chad_out_event.get("start", "")
    end_str = chad_out_event.get("end", "")
    
    print(f"\nParsing event:")
    try:
        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        
        print(f"  Start (parsed): {start_dt}")
        print(f"  End (parsed): {end_dt}")
        
        # Convert to UTC
        if start_dt.tzinfo is None:
            start_dt = pytz.UTC.localize(start_dt)
        else:
            start_dt = start_dt.astimezone(pytz.UTC)
        
        if end_dt.tzinfo is None:
            end_dt = pytz.UTC.localize(end_dt)
        else:
            end_dt = end_dt.astimezone(pytz.UTC)
        
        print(f"  Start (UTC): {start_dt}")
        print(f"  End (UTC): {end_dt}")
        
        # Now normalize and check slots
        context_json = {
            'timeframe': {'from': '2025-12-01', 'to': '2025-12-12', 'tz': 'America/New_York'},
            'participants': []
        }
        
        normalized = normalize_events(events_by_participant=events, context_json=context_json)
        slot_indexer = normalized['slot_indexer']
        
        print(f"\nHorizon:")
        print(f"  Start (UTC): {slot_indexer.horizon_start}")
        print(f"  Start (ET):  {slot_indexer.horizon_start.astimezone(pytz.timezone('America/New_York'))}")
        
        # Get slots for the event
        event_slots = slot_indexer.get_slots_in_range(start_dt, end_dt)
        print(f"\nEvent slots: {sorted(event_slots)}")
        print(f"Number of slots: {len(event_slots)}")
        
        # Check specific slots
        et = pytz.timezone('America/New_York')
        for slot in sorted(event_slots)[:5]:
            slot_dt = slot_indexer.slot_to_datetime(slot)
            et_dt = slot_dt.astimezone(et)
            print(f"  Slot {slot}: {et_dt.strftime('%I:%M %p %Z')}")
        
        # Now check if Chad's busy slots include these
        busy_slots = normalized['busy_slots']
        chad_busy = busy_slots.get('cdorsey@concord.org', set())
        
        print(f"\nChad's busy slots:")
        print(f"  Total: {len(chad_busy)}")
        
        missing = set(event_slots) - chad_busy
        if missing:
            print(f"  ✗ MISSING from busy slots: {sorted(missing)}")
        else:
            print(f"  ✓ All event slots are in busy_slots")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
else:
    print("Could not find 'Chad out' event on Dec 1")

