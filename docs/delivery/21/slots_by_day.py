#!/usr/bin/env python3
"""List first 3 free slots for each day"""

import json
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

# Group by day and show first 3 per day
et = pytz.timezone("America/New_York")

by_day = {}
for slot, score in ranked:
    dt = slot_indexer.slot_to_datetime(slot)
    et_dt = dt.astimezone(et)
    day_key = et_dt.strftime("%A, %B %d, %Y")
    
    if day_key not in by_day:
        by_day[day_key] = []
    by_day[day_key].append({
        "slot": slot,
        "score": score,
        "datetime": et_dt
    })

print("="*80)
print("FIRST 3 FREE SLOTS PER DAY")
print("="*80)
print()

# Sort days chronologically
sorted_days = sorted(by_day.keys(), key=lambda x: parser.parse(x.split(',')[1] + x.split(',')[2]))

for day in sorted_days:
    slots_for_day = by_day[day][:3]  # First 3 slots
    print(f"{day}:")
    for i, item in enumerate(slots_for_day, 1):
        slot = item["slot"]
        score = item["score"]
        dt = item["datetime"]
        end_dt = slot_indexer.slot_to_datetime(slot + duration_slots).astimezone(et)
        print(f"  {i}. {dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')} {dt.tzname()} (Slot {slot}, Score: {score:.2f})")
    print()

