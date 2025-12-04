#!/usr/bin/env python3
"""
Check ASP fact count for Dec 3-12 scenario to diagnose "too many messages" error.
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
from scheduling_orchestrator.schemas import SchedulingProblem
from scheduling_orchestrator.fact_generator import generate_asp_program
from scheduling_orchestrator.horizon_reducer import reduce_horizon_to_feasible_window


def load_events_from_example(example_file: Path) -> dict:
    """Load and normalize events"""
    events_by_participant = {}
    
    with open(example_file, 'r') as f:
        content = f.read()
    
    participants = ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
    
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
    print("CHECKING ASP FACT COUNT FOR DEC 3-12")
    print("="*80)
    print()
    
    example_file = Path(__file__).parent / "example_event_data.md"
    events_by_participant = load_events_from_example(example_file)
    
    context_json = {
        "timeframe": {"from": "2025-12-03", "to": "2025-12-12", "tz": "America/New_York"},
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
    normalized_data = normalize_events(events_by_participant, context_json)
    
    print(f"Original horizon: {normalized_data['slot_indexer'].total_slots} slots")
    print()
    
    # Reduce horizon
    print("Reducing horizon to 96 slots...")
    reduced_data = reduce_horizon_to_feasible_window(
        normalized_data,
        scheduling_problem,
        max_slots=96,
        prefer_time_window=True
    )
    
    print(f"Reduced horizon: {reduced_data['slot_indexer'].total_slots} slots")
    print()
    
    # Generate ASP program
    print("Generating ASP program with multi-move encoding...")
    asp_program = generate_asp_program(
        reduced_data,
        scheduling_problem,
        request_id="q1",
        include_soft_constraints=True,
        include_work_hours=True,
        include_min_gap=True,
        include_locked_events=True,
        phase=4,
        allow_multi_move=True
    )
    
    # Count facts
    fact_lines = [line for line in asp_program.split('\n') if line.strip() and not line.strip().startswith('%')]
    total_facts = len(fact_lines)
    
    print(f"Total ASP program lines: {len(asp_program.split(chr(10)))}")
    print(f"Total fact lines (non-comment): {total_facts}")
    print(f"Program size: {len(asp_program)} characters")
    print()
    
    # Count by type
    fact_types = {}
    for line in fact_lines:
        if '(' in line:
            fact_type = line.split('(')[0].strip()
            fact_types[fact_type] = fact_types.get(fact_type, 0) + 1
    
    print("Fact counts by type:")
    for fact_type, count in sorted(fact_types.items(), key=lambda x: -x[1]):
        print(f"  {fact_type}: {count}")
    print()
    
    # Check for specific high-count facts
    occurs_count = sum(1 for line in fact_lines if 'occurs_if_start' in line)
    busy_count = sum(1 for line in fact_lines if line.startswith('busy('))
    slot_count = sum(1 for line in fact_lines if line.startswith('slot('))
    workhours_count = sum(1 for line in fact_lines if 'workhours' in line)
    
    print("Key fact counts:")
    print(f"  occurs_if_start: {occurs_count}")
    print(f"  busy: {busy_count}")
    print(f"  slot: {slot_count}")
    print(f"  workhours: {workhours_count}")
    print()

