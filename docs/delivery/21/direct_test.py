#!/usr/bin/env python3
"""Direct test bypassing file loading"""

import json
from datetime import datetime
import pytz

# Directly test with Chad's event
event = {
    "id": "1iq2ne0eqqm6ijband1831s8iu",
    "title": "Chad out",
    "start": "2025-12-01T10:30:00-05:00",
    "end": "2025-12-01T12:45:00-05:00",
    "locked": False,
    "protected": False,
    "flexible": True
}

print("Event:")
print(f"  Start: {event['start']}")
print(f"  End: {event['end']}")

# Parse as normalizer does
start_str = event["start"]
end_str = event["end"]

try:
    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
    
    print(f"\nParsed:")
    print(f"  Start: {start_dt}")
    print(f"  End: {end_dt}")
    
    # Convert to UTC
    if start_dt.tzinfo is None:
        start_dt = pytz.UTC.localize(start_dt)
    else:
        start_dt = start_dt.astimezone(pytz.UTC)
    
    if end_dt.tzinfo is None:
        end_dt = pytz.UTC.localize(end_dt)
    else:
        end_dt = end_dt.astimezone(pytz.UTC)
    
    print(f"\nUTC:")
    print(f"  Start: {start_dt}")
    print(f"  End: {end_dt}")
    
    # Now create slot indexer
    et = pytz.timezone('America/New_York')
    from_date = datetime.fromisoformat("2025-12-01")
    to_date = datetime.fromisoformat("2025-12-12")
    from_date_et = et.localize(from_date)
    to_date_et = et.localize(to_date) + pytz.UTC.localize(datetime(2000,1,2)) - pytz.UTC.localize(datetime(2000,1,1))
    from_date_utc = from_date_et.astimezone(pytz.UTC)
    to_date_utc = to_date_et.astimezone(pytz.UTC)
    
    from scheduling_orchestrator.slot_indexer import SlotIndexer
    slot_indexer = SlotIndexer(from_date_utc, to_date_utc)
    
    print(f"\nHorizon:")
    print(f"  Start UTC: {slot_indexer.horizon_start}")
    print(f"  End UTC: {slot_indexer.horizon_end}")
    
    # Get slots
    event_slots = slot_indexer.get_slots_in_range(start_dt, end_dt)
    print(f"\nEvent slots: {sorted(event_slots)}")
    print(f"Number: {len(event_slots)}")
    
    # Show times
    print("\nSlot times (ET):")
    for slot in sorted(event_slots)[:10]:
        slot_dt = slot_indexer.slot_to_datetime(slot)
        et_dt = slot_dt.astimezone(et)
        print(f"  Slot {slot}: {et_dt.strftime('%I:%M %p')}")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

