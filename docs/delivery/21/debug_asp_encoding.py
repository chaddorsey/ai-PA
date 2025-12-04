#!/usr/bin/env python3
"""
Debug ASP encoding to see what's being generated for multi-move scenarios.
"""

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
from scheduling_orchestrator.fact_generator import generate_asp_program
from scheduling_orchestrator.schemas import SchedulingProblem
from scheduling_orchestrator.horizon_reducer import reduce_horizon_to_feasible_window

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
    print("DEBUG ASP ENCODING FOR MULTI-MOVE")
    print("="*80)
    print()
    
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
        },
        "policy": {
            "hard": {"min_gap_min": 0},
            "soft": {}
        },
        "slot_size_minutes": 15
    }
    
    scheduling_problem = SchedulingProblem(
        participants=["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"],
        duration_minutes=45,
        time_window_start="2025-12-03T09:00:00-05:00",
        time_window_end="2025-12-12T17:00:00-05:00"
    )
    
    print("1. Normalizing events...")
    normalized_data = normalize_events(events_by_participant, context_json=context_json)
    
    print("2. Reducing horizon for ASP...")
    asp_normalized_data = reduce_horizon_to_feasible_window(
        normalized_data,
        scheduling_problem,
        max_slots=48,
        prefer_time_window=True
    )
    
    print("3. Generating ASP program with multi-move enabled...")
    asp_program = generate_asp_program(
        asp_normalized_data,
        scheduling_problem,
        request_id="q1",
        include_soft_constraints=True,
        include_work_hours=True,
        include_min_gap=True,
        include_locked_events=True,
        phase=4,
        allow_multi_move=True
    )
    
    print(f"   Program size: {len(asp_program)} chars, {len(asp_program.splitlines())} lines")
    print()
    
    # Save to file for inspection
    output_file = Path(__file__).parent / "asp_program_debug.lp"
    with open(output_file, 'w') as f:
        f.write(asp_program)
    print(f"4. Saved ASP program to: {output_file}")
    print()
    
    # Count key facts
    facts = asp_program.split('\n')
    window_count = sum(1 for f in facts if f.strip().startswith('window(q1,'))
    occurs_count = sum(1 for f in facts if f.strip().startswith('occurs_if_start(q1,'))
    busy_count = sum(1 for f in facts if 'busy(' in f)
    locked_count = sum(1 for f in facts if 'locked_event(' in f)
    workhours_count = sum(1 for f in facts if 'workhours(' in f)
    
    print("5. Key fact counts:")
    print(f"   window facts: {window_count}")
    print(f"   occurs_if_start facts: {occurs_count}")
    print(f"   busy facts: {busy_count}")
    print(f"   locked_event facts: {locked_count}")
    print(f"   workhours facts: {workhours_count}")
    print()
    
    # Check if min_gap constraint is in the program
    has_min_gap_locked = any('locked_event(P, T2)' in f and 'min_gap' in f for f in facts)
    has_min_gap_busy = any('busy(P, T2)' in f and 'min_gap' in f for f in facts)
    print("6. Min-gap constraint check:")
    print(f"   Uses locked_event (correct for multi-move): {has_min_gap_locked}")
    print(f"   Uses busy (incorrect for multi-move): {has_min_gap_busy}")

