#!/usr/bin/env python3
"""
Investigate which slots are being marked as free for Dec 3-12.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

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
import pytz


def load_events_from_example(example_file: Path) -> dict:
    """Load events from example_event_data.md"""
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
            # Normalize event structure: extract dateTime from nested start/end objects
            normalized_events = []
            for event in events:
                normalized = {
                    "id": event.get("id", ""),
                    "title": event.get("summary") or event.get("title", ""),
                    "start": event.get("start", {}).get("dateTime") if isinstance(event.get("start"), dict) else event.get("start", ""),
                    "end": event.get("end", {}).get("dateTime") if isinstance(event.get("end"), dict) else event.get("end", ""),
                    "locked": event.get("locked", False),
                    "protected": event.get("protected", False),
                    "flexible": event.get("flexible", True),
                    "internal_only": event.get("internal_only", True),
                    "number_of_attendees": event.get("number_of_attendees", 0)
                }
                normalized_events.append(normalized)
            events_by_participant[participant] = normalized_events
        except json.JSONDecodeError as e:
            print(f"Warning: Unmatched brackets for {participant}")
            continue
    
    return events_by_participant


if __name__ == "__main__":
    print("="*80)
    print("INVESTIGATING FREE SLOTS FOR DEC 3-12")
    print("="*80)
    print()
    
    # Load events
    example_file = Path(__file__).parent / "example_event_data.md"
    events_by_participant = load_events_from_example(example_file)
    
    # Create context for Dec 3-12
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
        "policy": {
            "hard": {"min_gap_min": 0},
            "soft": {}
        },
        "slot_size_minutes": 15
    }
    
    scheduling_problem = SchedulingProblem(
        participants=["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"],
        duration_minutes=45,
        time_window_start="2025-12-03T00:00:00-05:00",
        time_window_end="2025-12-12T23:59:59-05:00"
    )
    
    print("Normalizing events...")
    normalized_data = normalize_events(
        events_by_participant,
        context_json=context_json
    )
    
    slot_indexer = normalized_data["slot_indexer"]
    busy_slots = normalized_data["busy_slots"]
    work_hours_slots = normalized_data["work_hours_slots"]
    
    print(f"Horizon: {slot_indexer.horizon_start} to {slot_indexer.horizon_end}")
    print(f"Total slots: {slot_indexer.total_slots}")
    print()
    
    # Check work hours and busy slots per participant
    for participant_id in scheduling_problem.participants:
        participant_work_hours = work_hours_slots.get(participant_id, set())
        participant_busy = busy_slots.get(participant_id, set())
        
        # Find slots that are in work hours but NOT busy
        participant_free_in_work_hours = participant_work_hours - participant_busy
        
        print(f"{participant_id}:")
        print(f"  Work hours slots: {len(participant_work_hours)}")
        print(f"  Busy slots: {len(participant_busy)}")
        print(f"  Free slots (in work hours): {len(participant_free_in_work_hours)}")
        
        # Show first 5 free slots
        if participant_free_in_work_hours:
            print(f"  First 5 free slots:")
            for slot in sorted(participant_free_in_work_hours)[:5]:
                dt = slot_indexer.slot_to_datetime(slot)
                if dt:
                    et = dt.astimezone(pytz.timezone('America/New_York'))
                    print(f"    Slot {slot}: {et.strftime('%Y-%m-%d %H:%M %Z')}")
        print()
    
    # Now check what _find_free_slots returns
    print("="*80)
    print("CHECKING _find_free_slots() OUTPUT")
    print("="*80)
    print()
    
    duration_slots = max(1, scheduling_problem.duration_minutes // 15)
    all_slots = list(range(slot_indexer.total_slots))
    
    free_slots = _find_free_slots(
        all_slots,
        busy_slots,
        work_hours_slots,
        scheduling_problem.participants,
        duration_slots,
        min_gap_slots=0
    )
    
    print(f"_find_free_slots() returned: {len(free_slots)} free slots")
    print()
    
    if free_slots:
        print("First 20 free slots:")
        for slot in sorted(free_slots)[:20]:
            dt = slot_indexer.slot_to_datetime(slot)
            if dt:
                et = dt.astimezone(pytz.timezone('America/New_York'))
                print(f"  Slot {slot}: {et.strftime('%Y-%m-%d %A %H:%M %Z')}")
                
                # Verify it's actually free for all participants
                for participant_id in scheduling_problem.participants:
                    participant_busy = busy_slots.get(participant_id, set())
                    participant_work_hours = work_hours_slots.get(participant_id, set())
                    
                    # Check all 3 slots of the 45-minute meeting
                    meeting_slots = set(range(slot, min(slot + duration_slots, slot_indexer.total_slots)))
                    overlapping_busy = meeting_slots & participant_busy
                    in_work_hours = meeting_slots.issubset(participant_work_hours)
                    
                    if overlapping_busy:
                        print(f"    ⚠️  {participant_id}: CONFLICT at slots {overlapping_busy}")
                    if not in_work_hours:
                        print(f"    ⚠️  {participant_id}: OUTSIDE WORK HOURS")
        print()
    else:
        print("No free slots found!")
        print()
    
    # Verify by checking a specific slot manually
    print("="*80)
    print("MANUAL VERIFICATION: Checking slot from test result")
    print("="*80)
    print()
    
    # The test returned: 2025-12-12T21:15:00+00:00
    result_dt = datetime.fromisoformat("2025-12-12T21:15:00+00:00")
    result_slot = slot_indexer.datetime_to_slot(result_dt)
    
    if result_slot is not None:
        print(f"Result slot: {result_slot}")
        et = result_dt.astimezone(pytz.timezone('America/New_York'))
        print(f"Result time: {et.strftime('%Y-%m-%d %A %H:%M %Z')}")
        print()
        
        # Check all 3 slots of the meeting
        meeting_slots = set(range(result_slot, min(result_slot + duration_slots, slot_indexer.total_slots)))
        print(f"Meeting occupies slots: {sorted(meeting_slots)}")
        print()
        
        for participant_id in scheduling_problem.participants:
            participant_busy = busy_slots.get(participant_id, set())
            participant_work_hours = work_hours_slots.get(participant_id, set())
            
            overlapping_busy = meeting_slots & participant_busy
            in_work_hours = meeting_slots.issubset(participant_work_hours)
            
            print(f"{participant_id}:")
            print(f"  In work hours: {in_work_hours} (work hours: {sorted(meeting_slots & participant_work_hours)})")
            print(f"  Overlapping busy: {bool(overlapping_busy)} (slots: {sorted(overlapping_busy)})")
            
            if overlapping_busy:
                print(f"  ⚠️  CONFLICT DETECTED!")
            if not in_work_hours:
                print(f"  ⚠️  OUTSIDE WORK HOURS!")
            print()

