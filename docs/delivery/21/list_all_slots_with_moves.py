#!/usr/bin/env python3
"""
List all available 45-minute slots for Chad, Sue, and Danielle, including slots that require moves.
Shows prioritization based on internal_only and number_of_attendees.
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
from scheduling_orchestrator.python_solver import find_optimal_slot, _find_slots_with_single_move
from scheduling_orchestrator.fact_generator import _find_free_slots
from scheduling_orchestrator.schemas import SchedulingProblem
from scheduling_orchestrator.dspy_extraction import extract_scheduling_request


def load_events_from_example(example_file: Path) -> dict:
    """Load events from example_event_data.md"""
    events_by_participant = {}
    
    if not example_file.exists():
        print(f"Error: Example file not found: {example_file}")
        return {}
    
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
            events_by_participant[participant] = []
            continue
        
        json_start = content.find('[', idx)
        if json_start == -1:
            events_by_participant[participant] = []
            continue
        
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
        
        if bracket_count != 0:
            events_by_participant[participant] = []
            continue
        
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
                
                title = event.get("title") or event.get("summary", "")
                
                normalized = {
                    "id": event.get("id", ""),
                    "title": title,
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
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON for {participant}: {e}")
            events_by_participant[participant] = []
    
    return events_by_participant


def format_datetime(dt_str: str, tz_str: str = "America/New_York") -> str:
    """Format UTC datetime string to Eastern time"""
    try:
        from datetime import datetime, timezone
        import pytz
        
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        et = pytz.timezone(tz_str)
        dt_et = dt.astimezone(et)
        return dt_et.strftime('%Y-%m-%d %I:%M %p %Z')
    except:
        return dt_str


def main():
    print("="*80)
    print("LISTING ALL AVAILABLE 45-MINUTE SLOTS")
    print("Chad, Sue, and Danielle | Dec 3-12, 2025")
    print("="*80)
    print()
    
    # Load events
    example_file = Path(__file__).parent / "example_event_data.md"
    events_by_participant = load_events_from_example(example_file)
    
    # Create scheduling problem
    scheduling_problem = SchedulingProblem(
        participants=["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"],
        duration_minutes=45,
        time_window_start="2025-12-03T00:00:00-05:00",
        time_window_end="2025-12-12T23:59:59-05:00"
    )
    
    # Create context
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
        "policy": {
            "hard": {
                "min_gap_min": 0
            }
        }
    }
    
    # Normalize events
    normalized_data = normalize_events(events_by_participant, context_json)
    slot_indexer = normalized_data["slot_indexer"]
    busy_slots = normalized_data["busy_slots"]
    work_hours_slots = normalized_data["work_hours_slots"]
    event_protection = normalized_data["event_protection"]
    min_gap_slots = normalized_data["min_gap_slots"]
    event_metadata = normalized_data["event_metadata"]
    event_slots_map = normalized_data["event_slots_map"]
    
    all_slots = slot_indexer.get_all_slots()
    duration_slots = max(1, scheduling_problem.duration_minutes // 15)
    
    print("Finding free slots (no moves required)...")
    free_slots = _find_free_slots(
        all_slots,
        busy_slots,
        work_hours_slots,
        scheduling_problem.participants,
        duration_slots,
        min_gap_slots
    )
    
    # Filter by time window
    from scheduling_orchestrator.python_solver import _check_time_window, _check_locked_events
    
    locked_events = {}
    for (participant_id, event_id), protection_level in event_protection.items():
        if protection_level == "locked":
            if participant_id not in locked_events:
                locked_events[participant_id] = set()
    
    constrained_free_slots = []
    for slot in free_slots:
        time_window_ok = _check_time_window(slot, scheduling_problem, slot_indexer, duration_slots)
        locked_ok = _check_locked_events(slot, locked_events, scheduling_problem.participants, duration_slots)
        if time_window_ok and locked_ok:
            constrained_free_slots.append(slot)
    
    print(f"Found {len(constrained_free_slots)} free slots\n")
    
    # Find slots requiring single moves
    print("Finding slots that require single-meeting moves...")
    flexible_events = {}
    candidates_with_moves = _find_slots_with_single_move(
        all_slots,
        busy_slots,
        work_hours_slots,
        locked_events,
        flexible_events,
        event_protection,
        scheduling_problem,
        slot_indexer,
        duration_slots,
        min_gap_slots,
        context_json,
        normalized_data
    )
    
    # Sort by score
    candidates_with_moves.sort(key=lambda x: x["score"], reverse=True)
    print(f"Found {len(candidates_with_moves)} slots requiring moves\n")
    
    # Display results
    print("="*80)
    print("FREE SLOTS (No moves required)")
    print("="*80)
    
    if constrained_free_slots:
        for i, slot in enumerate(constrained_free_slots, 1):
            start_dt = slot_indexer.slot_to_datetime(slot)
            end_slot = slot + duration_slots
            end_dt = slot_indexer.slot_to_datetime(end_slot)
            
            if start_dt and end_dt:
                start_str = format_datetime(start_dt.isoformat())
                end_str = format_datetime(end_dt.isoformat())
                print(f"{i}. {start_str} - {end_str}")
            else:
                print(f"{i}. Slot {slot} (datetime conversion failed)")
    else:
        print("No free slots found.")
    
    print()
    print("="*80)
    print("SLOTS REQUIRING SINGLE-MEETING MOVES")
    print("(Sorted by priority: internal-only > external, fewer attendees > more)")
    print("="*80)
    
    if candidates_with_moves:
        for i, candidate in enumerate(candidates_with_moves, 1):
            slot = candidate["start_slot"]
            start_dt = slot_indexer.slot_to_datetime(slot)
            end_slot = slot + duration_slots
            end_dt = slot_indexer.slot_to_datetime(end_slot)
            
            moved_event = candidate["moved_events"][0] if candidate["moved_events"] else None
            
            if start_dt and end_dt:
                start_str = format_datetime(start_dt.isoformat())
                end_str = format_datetime(end_dt.isoformat())
                
                print(f"\n{i}. {start_str} - {end_str}")
                print(f"   Score: {candidate['score']:.2f}")
                
                if moved_event:
                    old_start = format_datetime(moved_event["old_start"])
                    new_start = format_datetime(moved_event["new_start"])
                    shift_mins = moved_event["shift_minutes"]
                    direction = "earlier" if shift_mins < 0 else "later"
                    
                    # Get event metadata for details
                    event_key = (moved_event["owner"], moved_event["event_id"])
                    meta = event_metadata.get(event_key, {})
                    internal = meta.get("internal_only", True)
                    num_attendees = meta.get("number_of_attendees", 0)
                    title = meta.get("title", moved_event.get("title", "Unknown"))
                    
                    print(f"   Requires moving: '{title}' ({abs(shift_mins)} min {direction})")
                    print(f"     Event owner: {moved_event['owner']}")
                    print(f"     Internal-only: {internal}")
                    print(f"     Attendees: {num_attendees}")
                    print(f"     Old time: {old_start}")
                    print(f"     New time: {new_start}")
                    print(f"     Protection level: {candidate.get('protection_level', 'flexible')}")
            else:
                print(f"{i}. Slot {slot} (datetime conversion failed)")
    else:
        print("No slots found that can be created with single-meeting moves.")
    
    print()
    print("="*80)
    print(f"TOTAL: {len(constrained_free_slots)} free slots + {len(candidates_with_moves)} slots with moves = {len(constrained_free_slots) + len(candidates_with_moves)} total options")
    print("="*80)


if __name__ == "__main__":
    main()

