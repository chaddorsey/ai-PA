#!/usr/bin/env python3
"""Quick check for events on Dec 1 around 2:30 PM"""

import json
from pathlib import Path
from dateutil import parser
import pytz

from test_e2e_orchestrator import load_events_from_example

events = load_events_from_example(Path(__file__).parent / "example_event_data.md")
et = pytz.timezone("America/New_York")

target_start = et.localize(parser.parse("2025-12-01 14:30:00"))  # 2:30 PM
target_end = et.localize(parser.parse("2025-12-01 15:15:00"))   # 3:15 PM

print(f"Checking for conflicts on December 1, 2025 from 2:30 PM to 3:15 PM Eastern")
print(f"="*80)

participants = ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]

for p in participants:
    print(f"\n{p}:")
    p_events = events.get(p, [])
    
    # Check Dec 1 events
    dec1_events = []
    for event in p_events:
        start_str = event.get("start", "")
        if not start_str:
            continue
        
        try:
            start_dt = parser.parse(start_str)
            # Convert to ET if needed
            if start_dt.tzinfo is None:
                start_dt = et.localize(start_dt)
            else:
                start_dt = start_dt.astimezone(et)
            
            if start_dt.date() == target_start.date():  # Same day
                end_str = event.get("end", "")
                end_dt = parser.parse(end_str) if end_str else start_dt
                if end_dt.tzinfo is None:
                    end_dt = et.localize(end_dt)
                else:
                    end_dt = end_dt.astimezone(et)
                
                dec1_events.append({
                    "title": event.get("title", event.get("summary", "")),
                    "start": start_dt,
                    "end": end_dt
                })
        except Exception as e:
            pass
    
    # Sort by time
    dec1_events.sort(key=lambda x: x["start"])
    
    # Check for conflicts with 2:30-3:15 PM
    conflicts = []
    for event in dec1_events:
        # Check overlap: target_start < event_end AND target_end > event_start
        if target_start < event["end"] and target_end > event["start"]:
            conflicts.append(event)
    
    if conflicts:
        print(f"  ✗ CONFLICT at 2:30-3:15 PM:")
        for event in conflicts:
            print(f"      {event['title']}")
            print(f"      {event['start'].strftime('%I:%M %p')} - {event['end'].strftime('%I:%M %p')}")
    else:
        print(f"  ✓ Free at 2:30-3:15 PM")
    
    # Show all Dec 1 events for context
    print(f"  All Dec 1 events:")
    if dec1_events:
        for event in dec1_events:
            print(f"      {event['start'].strftime('%I:%M %p')} - {event['end'].strftime('%I:%M %p')}: {event['title']}")
    else:
        print(f"      (none)")

