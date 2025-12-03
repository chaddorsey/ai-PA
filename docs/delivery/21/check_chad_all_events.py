#!/usr/bin/env python3
"""List all of Chad's events to find 'Email & Tasks'"""

import json
from pathlib import Path
from dateutil import parser
import pytz

from test_e2e_orchestrator import load_events_from_example

events = load_events_from_example(Path(__file__).parent / "example_event_data.md")
chad_events = events.get("cdorsey@concord.org", [])

et = pytz.timezone("America/New_York")

print("="*80)
print("ALL OF CHAD'S EVENTS")
print("="*80)
print(f"Total events: {len(chad_events)}\n")

# Group by date
by_date = {}
for event in chad_events:
    start_str = event.get("start", "")
    if start_str:
        try:
            start_dt = parser.parse(start_str)
            if start_dt.tzinfo is None:
                start_dt = et.localize(start_dt)
            else:
                start_dt = start_dt.astimezone(et)
            
            date_key = start_dt.strftime("%Y-%m-%d")
            if date_key not in by_date:
                by_date[date_key] = []
            
            end_str = event.get("end", "")
            end_dt = parser.parse(end_str) if end_str else start_dt
            if end_dt.tzinfo is None:
                end_dt = et.localize(end_dt)
            else:
                end_dt = end_dt.astimezone(et)
            
            title = event.get("title", "") or event.get("summary", "")
            by_date[date_key].append({
                "title": title,
                "start": start_dt,
                "end": end_dt
            })
        except:
            pass

# Sort and display
for date in sorted(by_date.keys()):
    events_on_date = sorted(by_date[date], key=lambda x: x["start"])
    print(f"{date}:")
    for e in events_on_date:
        print(f"  {e['start'].strftime('%I:%M %p')} - {e['end'].strftime('%I:%M %p')}: {e['title']}")
    print()

# Search for any events with "email" or "task" in the name
print("="*80)
print("SEARCHING FOR 'EMAIL' OR 'TASK' IN EVENT TITLES")
print("="*80)
found = []
for event in chad_events:
    title = (event.get("title", "") or event.get("summary", "")).lower()
    if "email" in title or "task" in title:
        found.append(event)

if found:
    print(f"Found {len(found)} event(s):\n")
    for event in found:
        title = event.get("title", "") or event.get("summary", "")
        start_str = event.get("start", "")
        print(f"  '{title}'")
        print(f"    Start: {start_str}")
        print()
else:
    print("No events found with 'email' or 'task' in the title")

