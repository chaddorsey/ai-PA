#!/usr/bin/env python3
"""List all free slots for the 45-minute meeting"""

import sys
from pathlib import Path
from datetime import timedelta
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
        # No work_hours specified - will default to M-F 09:00-17:00
        {"id": "sbrau@concord.org", "email": "sbrau@concord.org", "name": "Sue"},
        # No work_hours specified - will default to M-F 09:00-17:00
        {"id": "dkehoe@concord.org", "email": "dkehoe@concord.org", "name": "Danielle"}
        # No work_hours specified - will default to M-F 09:00-17:00
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

# Rank the slots
from scheduling_orchestrator.schemas import SchedulingProblem
scheduling_problem = SchedulingProblem(
    participants=participants,
    duration_minutes=45,
    time_window_start="2025-12-01T00:00:00-05:00",
    time_window_end="2025-12-12T23:59:59-05:00"
)

ranked = _rank_slots(
    list(free_slots),
    normalized,
    scheduling_problem,
    slot_indexer,
    context_json
)

# Display all slots
et = pytz.timezone("America/New_York")

print("="*80)
print(f"ALL {len(free_slots)} FREE SLOTS FOR 45-MINUTE MEETING")
print("Dec 1-12, 2025 - Chad, Sue, and Danielle")
print("="*80)
print()

# Group by day
by_day = {}
for slot, score in ranked:
    dt = slot_indexer.slot_to_datetime(slot)
    et_dt = dt.astimezone(et)
    day_key = et_dt.strftime("%A, %B %d, %Y")
    
    if day_key not in by_day:
        by_day[day_key] = []
    meeting_end = slot_indexer.slot_to_datetime(slot + duration_slots).astimezone(et)
    by_day[day_key].append({
        "slot": slot,
        "score": score,
        "start": et_dt,
        "end": meeting_end
    })

# Sort days chronologically
sorted_days = sorted(by_day.keys(), key=lambda x: parser.parse(x.split(',')[1] + x.split(',')[2]))

for day in sorted_days:
        slots_for_day = sorted(by_day[day], key=lambda x: x["start"])
        print(f"{day} ({len(slots_for_day)} slots):")
        for item in slots_for_day:
            start = item["start"]
            # Meeting end time is start + duration (45 minutes)
            end_time = (start + timedelta(minutes=45)).astimezone(et)
            print(f"  {start.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')} {start.tzname()} (Score: {item['score']:.2f})")
        print()

