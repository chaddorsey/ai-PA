#!/usr/bin/env python3
"""Check specific slots that were returned against Chad's actual events"""

import json
from pathlib import Path
from dateutil import parser
import pytz

from test_e2e_orchestrator import load_events_from_example
from scheduling_orchestrator.normalizer import normalize_events
from scheduling_orchestrator.fact_generator import _find_free_slots

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

# Check the specific slots from the output
test_slots = [
    (64, "Monday Dec 1, 4:00 PM"),
    (65, "Monday Dec 1, 4:15 PM"),
    (66, "Monday Dec 1, 4:30 PM"),
]

et = pytz.timezone("America/New_York")

print("="*80)
print("CHECKING SPECIFIC RETURNED SLOTS")
print("="*80)

# Load Chad's raw events for comparison
chad_events_raw = events.get("cdorsey@concord.org", [])

for slot, description in test_slots:
    print(f"\n{description}:")
    slot_dt = slot_indexer.slot_to_datetime(slot)
    et_start = slot_dt.astimezone(et)
    et_end = slot_indexer.slot_to_datetime(slot + 3).astimezone(et)
    print(f"  Meeting time: {et_start.strftime('%I:%M %p')} - {et_end.strftime('%I:%M %p')} {et_start.tzname()}")
    
    # Check if slot is marked as busy for Chad
    chad_busy = busy_slots.get("cdorsey@concord.org", set())
    meeting_slots = set(range(slot, slot + 3))
    busy_overlap = meeting_slots.intersection(chad_busy)
    
    if busy_overlap:
        print(f"  ✗ CONFLICT: Marked as busy at slots {sorted(busy_overlap)}")
    else:
        print(f"  ✓ Not marked as busy")
    
    # Check against raw events
    print(f"  Checking against raw events on {et_start.strftime('%A, %B %d')}:")
    conflicts = []
    for event in chad_events_raw:
        start_str = event.get("start", "")
        if not start_str or "2025-12-01" not in start_str:
            continue
        
        try:
            event_start = parser.parse(start_str)
            if event_start.tzinfo is None:
                event_start = et.localize(event_start)
            else:
                event_start = event_start.astimezone(et)
            
            end_str = event.get("end", "")
            event_end = parser.parse(end_str) if end_str else event_start
            if event_end.tzinfo is None:
                event_end = et.localize(event_end)
            else:
                event_end = event_end.astimezone(et)
            
            title = event.get("title", "") or event.get("summary", "")
            
            # Check for overlap
            if et_start < event_end and et_end > event_start:
                conflicts.append({
                    "title": title,
                    "start": event_start,
                    "end": event_end
                })
        except:
            pass
    
    if conflicts:
        print(f"  ✗ CONFLICTS FOUND:")
        for conflict in conflicts:
            print(f"      {conflict['title']}")
            print(f"      {conflict['start'].strftime('%I:%M %p')} - {conflict['end'].strftime('%I:%M %p')}")
    else:
        print(f"  ✓ No conflicts found in raw events")
    
    # Also check if there are events with "Email" or "Task" in the name on this day
    print(f"  Events with 'Email' or 'Task' in name on {et_start.strftime('%B %d')}:")
    email_task_events = []
    for event in chad_events_raw:
        title = (event.get("title", "") or event.get("summary", "")).lower()
        start_str = event.get("start", "")
        if ("email" in title or "task" in title) and "2025-12-01" in start_str:
            email_task_events.append(event)
    
    if email_task_events:
        print(f"  ⚠ FOUND {len(email_task_events)} event(s):")
        for event in email_task_events:
            title = event.get("title", "") or event.get("summary", "")
            start_str = event.get("start", "")
            end_str = event.get("end", "")
            print(f"      '{title}'")
            print(f"      {start_str} - {end_str}")
    else:
        print(f"  No 'Email' or 'Task' events found")

# Also list all Chad's events on Monday Dec 1
print(f"\n" + "="*80)
print("ALL CHAD'S EVENTS ON MONDAY DECEMBER 1, 2025")
print("="*80)

dec1_events = []
for event in chad_events_raw:
    start_str = event.get("start", "")
    if start_str and "2025-12-01" in start_str:
        try:
            event_start = parser.parse(start_str)
            if event_start.tzinfo is None:
                event_start = et.localize(event_start)
            else:
                event_start = event_start.astimezone(et)
            
            end_str = event.get("end", "")
            event_end = parser.parse(end_str) if end_str else event_start
            if event_end.tzinfo is None:
                event_end = et.localize(event_end)
            else:
                event_end = event_end.astimezone(et)
            
            title = event.get("title", "") or event.get("summary", "")
            dec1_events.append({
                "title": title,
                "start": event_start,
                "end": event_end
            })
        except:
            pass

dec1_events.sort(key=lambda x: x["start"])

if dec1_events:
    for event in dec1_events:
        print(f"{event['start'].strftime('%I:%M %p')} - {event['end'].strftime('%I:%M %p')}: {event['title']}")
else:
    print("No events found")

