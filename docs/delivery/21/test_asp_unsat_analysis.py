#!/usr/bin/env python3
"""
Analyze whether the Dec 3-12 scenario is truly UNSAT or if there's an encoding issue.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
import pytz

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
from scheduling_orchestrator.clingo_wrapper import ClingoSolver


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
    print("ASP UNSAT ANALYSIS - Dec 3-12 Scenario")
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
        time_window_start="2025-12-03T09:00:00-05:00",
        time_window_end="2025-12-12T17:00:00-05:00"
    )
    
    print("1. Normalizing events...")
    normalized_data = normalize_events(events_by_participant, context_json=context_json)
    
    print("2. Analyzing work hours and busy slots in reduced horizon...")
    asp_normalized_data = reduce_horizon_to_feasible_window(
        normalized_data,
        scheduling_problem,
        max_slots=48,
        prefer_time_window=True
    )
    
    slot_indexer = asp_normalized_data["slot_indexer"]
    busy_slots = asp_normalized_data["busy_slots"]
    work_hours_slots = asp_normalized_data["work_hours_slots"]
    
    print(f"   Reduced horizon: {slot_indexer.horizon_start} to {slot_indexer.horizon_end}")
    print(f"   Total slots: {slot_indexer.total_slots}")
    print()
    
    # Check work hours coverage
    print("3. Work hours coverage:")
    for participant_id in scheduling_problem.participants:
        wh_slots = work_hours_slots.get(participant_id, set())
        busy = busy_slots.get(participant_id, set())
        print(f"   {participant_id}:")
        print(f"     Work hours slots: {len(wh_slots)}")
        print(f"     Busy slots: {len(busy)}")
        print(f"     Available slots: {len(wh_slots - busy)}")
    print()
    
    # Check if there are ANY slots where at least 2 participants are free
    print("4. Checking for potential multi-move candidates...")
    all_slots = list(range(slot_indexer.total_slots))
    potential_slots = []
    
    for slot in all_slots:
        free_count = 0
        conflicts = []
        for participant_id in scheduling_problem.participants:
            wh = work_hours_slots.get(participant_id, set())
            busy_set = busy_slots.get(participant_id, set())
            if slot in wh and slot not in busy_set:
                free_count += 1
            elif slot in wh and slot in busy_set:
                conflicts.append(participant_id)
        
        # Check if meeting would fit
        duration_slots = 3  # 45 minutes
        meeting_slots = range(slot, slot + duration_slots)
        if slot + duration_slots <= slot_indexer.total_slots:
            all_in_work_hours = True
            for participant_id in scheduling_problem.participants:
                wh = work_hours_slots.get(participant_id, set())
                if not all(s in wh for s in meeting_slots):
                    all_in_work_hours = False
                    break
            
            if all_in_work_hours:
                if free_count >= 1 and len(conflicts) <= 2:  # Could solve with 1-2 moves
                    potential_slots.append((slot, free_count, conflicts))
    
    print(f"   Found {len(potential_slots)} slots that could work with 1-2 moves")
    if potential_slots:
        print("   Sample slots:")
        for slot, free_count, conflicts in potential_slots[:5]:
            dt = slot_indexer.slot_to_datetime(slot)
            if dt:
                et = pytz.timezone('America/New_York')
                dt_et = dt.astimezone(et)
                print(f"     Slot {slot}: {dt_et.strftime('%Y-%m-%d %A %H:%M')} - {free_count} free, {len(conflicts)} conflicts: {conflicts}")
    print()
    
    # Test minimal ASP program (no soft constraints)
    print("5. Testing minimal ASP program (hard constraints only)...")
    minimal_program = generate_asp_program(
        asp_normalized_data,
        scheduling_problem,
        request_id="q1",
        include_soft_constraints=False,  # No soft constraints - just feasibility
        include_work_hours=True,
        include_min_gap=True,
        include_locked_events=True,
        phase=3,  # Hard constraints only
        allow_multi_move=True
    )
    
    solver = ClingoSolver(timeout=10)
    model, stats, result = solver.solve(minimal_program)
    
    print(f"   Models found: {stats.get('models_found', 0)}")
    print(f"   Satisfiable: {stats.get('satisfiable', 'N/A')}")
    if stats.get('error'):
        print(f"   Error: {stats.get('error')}")
    
    if model:
        print("   ✓ Found solution with minimal constraints!")
        # Extract solution
        from scheduling_orchestrator.clingo_wrapper import extract_model_predicates
        predicates = extract_model_predicates(model)
        start_preds = predicates.get("start", [])
        if start_preds:
            for args in start_preds:
                if args[0] == "q1":
                    start_slot = args[1]
                    dt = slot_indexer.slot_to_datetime(start_slot)
                    if dt:
                        et = pytz.timezone('America/New_York')
                        dt_et = dt.astimezone(et)
                        print(f"     Solution: Slot {start_slot} = {dt_et.strftime('%Y-%m-%d %A %H:%M')}")
    else:
        print("   ✗ No solution found even with minimal constraints - truly UNSAT")
    print()

