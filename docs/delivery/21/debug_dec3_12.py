#!/usr/bin/env python3
"""Debug why no slots found for Dec 3-12"""

import json
import sys
from pathlib import Path

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
from datetime import datetime
import pytz

def load_events_from_example(example_file: Path) -> dict:
    """Load events - simplified version"""
    events_by_participant = {}
    with open(example_file, 'r') as f:
        content = f.read()
    
    participants = ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
    
    for participant in participants:
        marker = f"Event data for {participant}:"
        idx = content.find(marker)
        if idx == -1:
            events_by_participant[participant] = []
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
                start_str = start_val.get("dateTime", "") if isinstance(start_val, dict) else str(start_val) if start_val else ""
                end_val = event.get("end", "")
                end_str = end_val.get("dateTime", "") if isinstance(end_val, dict) else str(end_val) if end_val else ""
                
                normalized = {
                    "id": event.get("id", ""),
                    "title": event.get("title") or event.get("summary", ""),
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
        except:
            events_by_participant[participant] = []
    
    return events_by_participant

def main():
    example_file = Path(__file__).parent / "example_event_data.md"
    events_by_participant = load_events_from_example(example_file)
    
    context_json = {
        "timeframe": {
            "from": "2025-12-03",
            "to": "2025-12-12",
            "tz": "America/New_York"
        },
        "participants": [
            {"id": "cdorsey@concord.org", "email": "cdorsey@concord.org", "name": "Chad"},
            {"id": "sbrau@concord.org", "email": "sbrau@concord.org", "name": "Sue"},
            {"id": "dkehoe@concord.org", "email": "dkehoe@concord.org", "name": "Danielle"}
        ],
        "policy": {"hard": {"min_gap_min": 0}}
    }
    
    normalized_data = normalize_events(events_by_participant, context_json)
    slot_indexer = normalized_data["slot_indexer"]
    busy_slots = normalized_data["busy_slots"]
    work_hours_slots = normalized_data["work_hours_slots"]
    
    scheduling_problem = SchedulingProblem(
        participants=["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"],
        duration_minutes=45,
        time_window_start="2025-12-03T00:00:00-05:00",
        time_window_end="2025-12-12T23:59:59-05:00"
    )
    
    duration_slots = max(1, scheduling_problem.duration_minutes // 15)
    all_slots = slot_indexer.get_all_slots()
    
    print(f"Total slots in horizon: {len(all_slots)}")
    print(f"Duration slots needed: {duration_slots}")
    print()
    
    # Check work hours
    for participant_id in scheduling_problem.participants:
        work_slots = work_hours_slots.get(participant_id, set())
        busy = busy_slots.get(participant_id, set())
        print(f"{participant_id}:")
        print(f"  Work hours slots: {len(work_slots)}")
        print(f"  Busy slots: {len(busy)}")
        print(f"  Free slots (work hours only): {len(work_slots - busy)}")
    
    print()
    print("Checking for slots with conflicts...")
    
    # Check a sample of slots
    sample_size = min(100, len(all_slots))
    sample_slots = all_slots[:sample_size] if all_slots else []
    
    conflicts_by_participant_count = {}
    
    for slot in sample_slots:
        if slot + duration_slots > max(all_slots) + 1:
            continue
        
        meeting_slots = range(slot, slot + duration_slots)
        conflicting_participants = []
        
        for participant_id in scheduling_problem.participants:
            participant_work_hours = work_hours_slots.get(participant_id, set())
            participant_busy = busy_slots.get(participant_id, set())
            
            # Check work hours
            if participant_work_hours and not all(s in participant_work_hours for s in meeting_slots):
                conflicting_participants.append(f"{participant_id} (outside work hours)")
            elif set(meeting_slots).intersection(participant_busy):
                conflicting_participants.append(f"{participant_id} (busy)")
        
        num_conflicts = len(conflicting_participants)
        conflicts_by_participant_count[num_conflicts] = conflicts_by_participant_count.get(num_conflicts, 0) + 1
    
    print(f"\nConflict distribution (first {sample_size} slots):")
    for num_conflicts in sorted(conflicts_by_participant_count.keys()):
        count = conflicts_by_participant_count[num_conflicts]
        print(f"  {num_conflicts} conflicting participant(s): {count} slots")
    
    print("\nNote: Single-move logic only handles slots where exactly 1 participant has a conflict.")
    print("If multiple participants conflict simultaneously, multi-move logic (ASP) is needed.")

if __name__ == "__main__":
    main()

