#!/usr/bin/env python3
"""Check if any free slots conflict with Email & Tasks events"""

import sys
from pathlib import Path
import pytz
from dateutil import parser

project_root = Path(__file__).parent.parent.parent.parent
env_path = project_root / '.env'
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "letta"))

from scheduling_orchestrator.normalizer import normalize_events
from scheduling_orchestrator.fact_generator import _find_free_slots
from scheduling_orchestrator.python_solver import _rank_slots
from test_e2e_orchestrator import load_events_from_example

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
work_hours_slots = normalized["work_hours_slots"]

all_slots = list(range(slot_indexer.total_slots))
duration_slots = 3  # 45 minutes
participants = ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]

free_slots = _find_free_slots(
    all_slots, busy_slots, work_hours_slots,
    participants, duration_slots, min_gap_slots=0
)

# Get Email & Tasks event slots
et = pytz.timezone("America/New_York")
chad_events = events.get("cdorsey@concord.org", [])
email_tasks_slots = set()

for event in chad_events:
    title = str(event.get("title", "") or event.get("summary", "")).lower()
    if "email" in title and "task" in title:
        start_str = event.get("start", "")
        end_str = event.get("end", "")
        if start_str and end_str:
            try:
                start_dt = parser.parse(start_str)
                if start_dt.tzinfo is None:
                    start_dt = et.localize(start_dt)
                else:
                    start_dt = start_dt.astimezone(et)
                
                end_dt = parser.parse(end_str)
                if end_dt.tzinfo is None:
                    end_dt = et.localize(end_dt)
                else:
                    end_dt = end_dt.astimezone(et)
                
                start_utc = start_dt.astimezone(pytz.UTC)
                end_utc = end_dt.astimezone(pytz.UTC)
                
                event_slots = slot_indexer.get_slots_in_range(start_utc, end_utc)
                email_tasks_slots.update(event_slots)
            except:
                pass

print("="*80)
print("CHECKING FOR CONFLICTS WITH EMAIL & TASKS EVENTS")
print("="*80)
print(f"\nEmail & Tasks events occupy {len(email_tasks_slots)} slots")
print(f"Free slots found: {len(free_slots)}")

# Check for conflicts
conflicting_slots = free_slots.intersection(email_tasks_slots)
if conflicting_slots:
    print(f"\n⚠️  PROBLEM: {len(conflicting_slots)} free slots conflict with Email & Tasks events!")
    print("\nConflicting slots:")
    for slot in sorted(list(conflicting_slots))[:20]:
        dt = slot_indexer.slot_to_datetime(slot)
        et_dt = dt.astimezone(et)
        meeting_end = slot_indexer.slot_to_datetime(slot + duration_slots).astimezone(et)
        print(f"  Slot {slot}: {et_dt.strftime('%A, %B %d, %Y %I:%M %p')} - {meeting_end.strftime('%I:%M %p')} {et_dt.tzname()}")
else:
    print("\n✓ No free slots conflict with Email & Tasks events")

# Show all free slots grouped by day
print("\n" + "="*80)
print("ALL FREE SLOTS BY DAY")
print("="*80)

by_day = {}
for slot in sorted(free_slots):
    dt = slot_indexer.slot_to_datetime(slot)
    et_dt = dt.astimezone(et)
    day_key = et_dt.strftime("%A, %B %d, %Y")
    
    if day_key not in by_day:
        by_day[day_key] = []
    meeting_end = slot_indexer.slot_to_datetime(slot + duration_slots).astimezone(et)
    by_day[day_key].append({
        "slot": slot,
        "start": et_dt,
        "end": meeting_end
    })

for day in sorted(by_day.keys(), key=lambda x: parser.parse(x.split(',')[1] + x.split(',')[2])):
    slots_for_day = by_day[day]
    print(f"\n{day} ({len(slots_for_day)} slots):")
    for item in slots_for_day[:10]:  # First 10 per day
        print(f"  {item['start'].strftime('%I:%M %p')} - {item['end'].strftime('%I:%M %p')} {item['start'].tzname()}")

