#!/usr/bin/env python3
"""Check Chad's schedule on December 1"""

import json
from pathlib import Path
from dateutil import parser
import pytz

from test_e2e_orchestrator import load_events_from_example

events = load_events_from_example(Path(__file__).parent / "example_event_data.md")
et = pytz.timezone("America/New_York")

chad_id = "cdorsey@concord.org"
chad_events = events.get(chad_id, [])

print("="*80)
print(f"CHAD'S SCHEDULE - DECEMBER 1, 2025")
print("="*80)
print()

dec1_events = []

for event in chad_events:
    start_str = event.get("start", "")
    if not start_str:
        continue
    
    try:
        start_dt = parser.parse(start_str)
        if start_dt.tzinfo is None:
            start_dt = et.localize(start_dt)
        else:
            start_dt = start_dt.astimezone(et)
        
        if start_dt.date().strftime("%Y-%m-%d") == "2025-12-01":
            end_str = event.get("end", "")
            end_dt = parser.parse(end_str) if end_str else start_dt
            if end_dt.tzinfo is None:
                end_dt = et.localize(end_dt)
            else:
                end_dt = end_dt.astimezone(et)
            
            dec1_events.append({
                "title": event.get("title", event.get("summary", "Untitled")),
                "start": start_dt,
                "end": end_dt,
                "locked": event.get("locked", False),
                "protected": event.get("protected", False),
                "flexible": event.get("flexible", True)
            })
    except Exception as e:
        pass

# Sort by start time
dec1_events.sort(key=lambda x: x["start"])

if dec1_events:
    print(f"Found {len(dec1_events)} event(s) on December 1:\n")
    for i, event in enumerate(dec1_events, 1):
        start_time = event["start"].strftime("%I:%M %p")
        end_time = event["end"].strftime("%I:%M %p")
        status = []
        if event.get("locked"):
            status.append("LOCKED")
        if event.get("protected"):
            status.append("PROTECTED")
        if not event.get("flexible"):
            status.append("NOT FLEXIBLE")
        
        status_str = f" [{', '.join(status)}]" if status else " [flexible]"
        print(f"{i}. {start_time} - {end_time}: {event['title']}{status_str}")
else:
    print("No events found for December 1, 2025")
    print("\n✓ Your calendar appears to be completely free that day!")

print()
print("="*80)
print("Available time windows for a 45-minute meeting:")
print("="*80)

# Show available windows
work_start = et.localize(parser.parse("2025-12-01 09:00:00"))
work_end = et.localize(parser.parse("2025-12-01 17:00:00"))

if not dec1_events:
    print(f"9:00 AM - 5:00 PM: COMPLETELY FREE")
else:
    # Find gaps
    current_time = work_start
    for event in dec1_events:
        if current_time < event["start"]:
            gap_minutes = (event["start"] - current_time).total_seconds() / 60
            if gap_minutes >= 45:
                print(f"{current_time.strftime('%I:%M %p')} - {event['start'].strftime('%I:%M %p')}: Available ({int(gap_minutes)} minutes)")
        current_time = max(current_time, event["end"])
    
    # Check after last event
    if current_time < work_end:
        gap_minutes = (work_end - current_time).total_seconds() / 60
        if gap_minutes >= 45:
            print(f"{current_time.strftime('%I:%M %p')} - {work_end.strftime('%I:%M %p')}: Available ({int(gap_minutes)} minutes)")

