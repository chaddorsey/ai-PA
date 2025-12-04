#!/usr/bin/env python3
"""
Debug why Saturday slot is being returned for Dec 1-12.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
import pytz

# Load .env
project_root = Path(__file__).parent.parent.parent.parent
env_path = project_root / '.env'
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "letta"))

from scheduling_orchestrator.normalizer import normalize_events
from scheduling_orchestrator.slot_indexer import SlotIndexer
from scheduling_orchestrator.fact_generator import _find_free_slots
from scheduling_orchestrator.schemas import SchedulingProblem


def load_events_from_example(example_file: Path) -> dict:
    """Load events - same as test script"""
    events_by_participant = {}
    
    with open(example_file, 'r') as f:
        content = f.read()
    
    participants = [
        "cdorsey@concord.org",
        "sbrau@concord.org",
        "dkehoe@concord.org"
    ]
    
    for participant in participants:
        marker = f"Event data for {participant}:"
        idx = content.find(marker)
        if idx == -1:
            continue
        
        json_start = content.find('[', idx)
        bracket_count = 0
        json_end = json_start
        for i, char in enumerate(content[json_start:], json_start):
            if char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
                if bracket_count == 0:
                    json_end = i + 1
                    break
        
        json_str = content[json_start:json_end]
        try:
            events = json.loads(json_str)
            normalized_events = []
            for event in events:
                start_val = event.get("start", "")
                if isinstance(start_val, dict):
                    start_str = start_val.get("dateTime", "")
                else:
                    start_str = str(start_val) if start_val else ""
                
                end_val = event.get("end", "")
                if isinstance(end_val, dict):
                    end_str = end_val.get("dateTime", "")
                else:
                    end_str = str(end_val) if end_val else ""
                
                normalized = {
                    "id": event.get("id", ""),
                    "title": event.get("summary") or event.get("title", ""),
                    "start": start_str,
                    "end": end_str,
                    "locked": event.get("locked", False),
                    "protected": event.get("protected", False),
                    "flexible": event.get("flexible", True),
                    "internal_only": event.get("internal_only", True),
                    "number_of_attendees": event.get("number_of_attendees", 0)
                }
                normalized_events.append(normalized)
            events_by_participant[participant] = normalized_events
        except json.JSONDecodeError:
            continue
    
    return events_by_participant


if __name__ == "__main__":
    print("="*80)
    print("DEBUGGING SATURDAY SLOT BUG")
    print("="*80)
    print()
    
    # Load events
    example_file = Path(__file__).parent / "example_event_data.md"
    events_by_participant = load_events_from_example(example_file)
    
    # Same context as test_orchestrator_sue_danielle.py (Dec 1-12)
    context_json = {
        "timeframe": {
            "from": "2025-12-01",
            "to": "2025-12-12",
            "tz": "America/New_York"
        },
        "participants": [
            {"id": "cdorsey@concord.org", "email": "cdorsey@concord.org"},
            {"id": "sbrau@concord.org", "email": "sbrau@concord.org"},
            {"id": "dkehoe@concord.org", "email": "dkehoe@concord.org"}
        ],
        "policy": {"hard": {"min_gap_min": 0}, "soft": {}},
        "slot_size_minutes": 15
    }
    
    scheduling_problem = SchedulingProblem(
        participants=["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"],
        duration_minutes=45,
        time_window_start="2025-12-01T00:00:00-05:00",
        time_window_end="2025-12-12T23:59:59-05:00"
    )
    
    print("Normalizing events...")
    normalized_data = normalize_events(events_by_participant, context_json=context_json)
    
    slot_indexer = normalized_data["slot_indexer"]
    busy_slots = normalized_data["busy_slots"]
    work_hours_slots = normalized_data["work_hours_slots"]
    
    print(f"Horizon: {slot_indexer.horizon_start} to {slot_indexer.horizon_end}")
    print()
    
    # Check work hours for Saturday Dec 6
    sat_dec6_9am_est = datetime(2025, 12, 6, 9, 0, 0)
    et = pytz.timezone('America/New_York')
    sat_dec6_9am_est = et.localize(sat_dec6_9am_est)
    sat_dec6_9am_utc = sat_dec6_9am_est.astimezone(pytz.UTC)
    
    sat_slot = slot_indexer.datetime_to_slot(sat_dec6_9am_utc)
    
    print(f"Saturday Dec 6, 9am EST = {sat_dec6_9am_utc} UTC")
    print(f"Slot index: {sat_slot}")
    print()
    
    print("Work hours check:")
    for participant_id in scheduling_problem.participants:
        participant_work_hours = work_hours_slots.get(participant_id, set())
        is_in_work_hours = sat_slot in participant_work_hours if sat_slot is not None and participant_work_hours else None
        
        print(f"  {participant_id}:")
        print(f"    Work hours slots count: {len(participant_work_hours)}")
        print(f"    Slot {sat_slot} in work hours: {is_in_work_hours}")
        
        # Check what days have work hours
        if participant_work_hours and sat_slot is not None:
            sample_slots = sorted(participant_work_hours)
            if sample_slots:
                sample_dt = slot_indexer.slot_to_datetime(sample_slots[0])
                if sample_dt:
                    sample_et = sample_dt.astimezone(et)
                    print(f"    First work hours slot: {sample_slots[0]} = {sample_et.strftime('%Y-%m-%d %A %H:%M')}")
                
                # Find slots around Dec 6
                dec6_slots = [s for s in participant_work_hours if 200 <= s <= 300]  # Approximate range
                if dec6_slots:
                    for s in sorted(dec6_slots)[:5]:
                        s_dt = slot_indexer.slot_to_datetime(s)
                        if s_dt:
                            s_et = s_dt.astimezone(et)
                            print(f"      Slot {s}: {s_et.strftime('%Y-%m-%d %A %H:%M')}")
    print()
    
    # Check if slot would be returned by _find_free_slots
    duration_slots = 3
    all_slots = list(range(slot_indexer.total_slots))
    
    free_slots = _find_free_slots(
        all_slots,
        busy_slots,
        work_hours_slots,
        scheduling_problem.participants,
        duration_slots,
        min_gap_slots=0
    )
    
    if sat_slot is not None:
        if sat_slot in free_slots:
            print(f"⚠️  BUG: Saturday slot {sat_slot} is in free_slots!")
        else:
            print(f"✓ Saturday slot {sat_slot} is NOT in free_slots (correct)")
    print()
    
    print(f"Total free slots: {len(free_slots)}")
    if free_slots:
        print("First 10 free slots:")
        et = pytz.timezone('America/New_York')
        for slot in sorted(free_slots)[:10]:
            dt = slot_indexer.slot_to_datetime(slot)
            if dt:
                dt_et = dt.astimezone(et)
                print(f"  Slot {slot}: {dt_et.strftime('%Y-%m-%d %A %H:%M %Z')}")

