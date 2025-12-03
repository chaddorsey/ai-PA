#!/usr/bin/env python3
"""Break down free slots by day"""

import json
from pathlib import Path
import pytz

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "letta"))

from scheduling_orchestrator.normalizer import normalize_events
from scheduling_orchestrator.fact_generator import _find_free_slots
from test_e2e_orchestrator import load_events_from_example

events = load_events_from_example(Path(__file__).parent / "example_event_data.md")
context_json = {
    "timeframe": {"from": "2025-12-01", "to": "2025-12-12", "tz": "America/New_York"},
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
duration_slots = 3
participants = ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]

free_slots = _find_free_slots(
    all_slots, busy_slots, work_hours_slots,
    participants, duration_slots, min_gap_slots=0
)

et = pytz.timezone("America/New_York")

# Group by day
by_day = {}
for slot in sorted(free_slots):
    dt = slot_indexer.slot_to_datetime(slot)
    et_dt = dt.astimezone(et)
    day_key = et_dt.strftime("%A, %B %d")
    if day_key not in by_day:
        by_day[day_key] = []
    by_day[day_key].append(et_dt.strftime("%I:%M %p"))

print("Free slots by day:")
print("="*80)
total = 0
for day in sorted(by_day.keys()):
    count = len(by_day[day])
    total += count
    print(f"{day}: {count} slots")
    if count <= 10:
        print(f"  Times: {', '.join(by_day[day])}")
    else:
        print(f"  First 5: {', '.join(by_day[day][:5])} ... (and {count-5} more)")
print(f"\nTotal: {total} slots")

