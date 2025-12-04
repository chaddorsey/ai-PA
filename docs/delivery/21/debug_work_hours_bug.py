#!/usr/bin/env python3
"""
Debug the work hours bug - check what's happening with the returned slot.
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
            # Normalize event structure
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
    print("DEBUGGING WORK HOURS BUG")
    print("="*80)
    print()
    
    # Load events
    example_file = Path(__file__).parent / "example_event_data.md"
    events_by_participant = load_events_from_example(example_file)
    
    context_json = {
        "timeframe": {
            "from": "2025-12-03",
            "to": "2025-12-12",
            "tz": "America/New_York"
        },
        "participants": [
            {"id": "cdorsey@concord.org", "email": "cdorsey@concord.org", "work_hours": "M-F 09:00-17:00"},
            {"id": "sbrau@concord.org", "email": "sbrau@concord.org", "work_hours": "M-F 09:00-17:00"},
            {"id": "dkehoe@concord.org", "email": "dkehoe@concord.org", "work_hours": "M-F 09:00-17:00"}
        ],
        "policy": {"hard": {"min_gap_min": 0}, "soft": {}},
        "slot_size_minutes": 15
    }
    
    scheduling_problem = SchedulingProblem(
        participants=["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"],
        duration_minutes=45,
        time_window_start="2025-12-03T00:00:00-05:00",
        time_window_end="2025-12-12T23:59:59-05:00"
    )
    
    print("Normalizing events...")
    normalized_data = normalize_events(events_by_participant, context_json=context_json)
    
    slot_indexer = normalized_data["slot_indexer"]
    busy_slots = normalized_data["busy_slots"]
    work_hours_slots = normalized_data["work_hours_slots"]
    
    print(f"Full horizon: {slot_indexer.horizon_start} to {slot_indexer.horizon_end}")
    print(f"Total slots: {slot_indexer.total_slots}")
    print()
    
    # Check the problematic slot: 2025-12-08T00:00:00+00:00
    problem_dt = datetime.fromisoformat("2025-12-08T00:00:00+00:00")
    problem_slot = slot_indexer.datetime_to_slot(problem_dt)
    
    print(f"Problem slot time: {problem_dt} UTC")
    et = pytz.timezone('America/New_York')
    problem_et = problem_dt.astimezone(et)
    print(f"In Eastern: {problem_et.strftime('%Y-%m-%d %A %H:%M %Z')}")
    print(f"Problem slot index: {problem_slot}")
    print()
    
    if problem_slot is not None:
        # Check work hours for this slot
        print("Work hours check for problem slot:")
        for participant_id in scheduling_problem.participants:
            participant_work_hours = work_hours_slots.get(participant_id, set())
            is_in_work_hours = problem_slot in participant_work_hours if participant_work_hours else None
            
            print(f"  {participant_id}:")
            print(f"    Work hours slots defined: {bool(participant_work_hours)}")
            print(f"    Work hours slots count: {len(participant_work_hours)}")
            print(f"    Slot {problem_slot} in work hours: {is_in_work_hours}")
            
            # Check a few work hours slots to see what times they represent
            if participant_work_hours:
                sample_slots = sorted(participant_work_hours)[:5]
                print(f"    Sample work hours slots: {sample_slots}")
                for s in sample_slots:
                    s_dt = slot_indexer.slot_to_datetime(s)
                    if s_dt:
                        s_et = s_dt.astimezone(et)
                        print(f"      Slot {s}: {s_et.strftime('%Y-%m-%d %A %H:%M %Z')}")
        print()
        
        # Check if slot would be returned by _find_free_slots
        print("Checking _find_free_slots...")
        duration_slots = 3  # 45 minutes
        all_slots = list(range(slot_indexer.total_slots))
        
        free_slots = _find_free_slots(
            all_slots,
            busy_slots,
            work_hours_slots,
            scheduling_problem.participants,
            duration_slots,
            min_gap_slots=0
        )
        
        print(f"Free slots found: {len(free_slots)}")
        if problem_slot in free_slots:
            print(f"⚠️  PROBLEM: Slot {problem_slot} is in free_slots!")
            
            # Manual check
            meeting_slots = range(problem_slot, problem_slot + duration_slots)
            print(f"Meeting slots: {list(meeting_slots)}")
            
            for participant_id in scheduling_problem.participants:
                participant_work_hours = work_hours_slots.get(participant_id, set())
                participant_busy = busy_slots.get(participant_id, set())
                
                all_in_work_hours = all(s in participant_work_hours for s in meeting_slots)
                all_free = not any(s in participant_busy for s in meeting_slots)
                
                print(f"  {participant_id}:")
                print(f"    All slots in work hours: {all_in_work_hours}")
                print(f"    All slots free: {all_free}")
                if not all_in_work_hours:
                    print(f"    ⚠️  NOT ALL IN WORK HOURS!")
                    for s in meeting_slots:
                        in_wh = s in participant_work_hours
                        print(f"      Slot {s}: in work hours = {in_wh}")
        else:
            print(f"✓ Slot {problem_slot} is NOT in free_slots (correct)")
    else:
        print("⚠️  Problem slot not found in horizon!")

