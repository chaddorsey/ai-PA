#!/usr/bin/env python3
"""
Test multi-move ASP with a simple, controlled scenario where we know solutions exist.

This creates a minimal test case:
- 2 participants
- 1 day (Monday, Dec 1)
- Both participants have events during the day
- A 30-minute meeting can be scheduled by moving one event
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
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
from scheduling_orchestrator.clingo_wrapper import ClingoSolver, extract_model_predicates


def create_simple_test_scenario():
    """
    Create a simple test scenario:
    - Dec 1, 2025 (Monday)
    - 2 participants: p1@test.com, p2@test.com
    - p1 has an event 10:00-11:00
    - p2 has an event 11:00-12:00
    - Both are free 9:00-10:00 and 12:00-17:00
    - Meeting request: 30 minutes between 9:00-17:00
    - Expected: Solution at 10:00-10:30 (move p1's event) or 11:30-12:00 (move p2's event)
    """
    et = pytz.timezone('America/New_York')
    
    # Dec 1, 2025 is a Monday
    base_date = et.localize(datetime(2025, 12, 1, 0, 0, 0))
    
    events_by_participant = {
        "p1@test.com": [
            {
                "id": "e1",
                "title": "Event 1",
                "start": (base_date + timedelta(hours=10)).isoformat(),
                "end": (base_date + timedelta(hours=11)).isoformat(),
                "locked": False,
                "protected": False,
                "flexible": True,
                "internal_only": True,
                "number_of_attendees": 1
            }
        ],
        "p2@test.com": [
            {
                "id": "e2",
                "title": "Event 2",
                "start": (base_date + timedelta(hours=11)).isoformat(),
                "end": (base_date + timedelta(hours=12)).isoformat(),
                "locked": False,
                "protected": False,
                "flexible": True,
                "internal_only": True,
                "number_of_attendees": 1
            }
        ]
    }
    
    context_json = {
        "timeframe": {
            "from": "2025-12-01",
            "to": "2025-12-01",
            "tz": "America/New_York"
        },
        "participants": [
            {"id": "p1@test.com", "email": "p1@test.com", "work_hours": "M-F 09:00-17:00"},
            {"id": "p2@test.com", "email": "p2@test.com", "work_hours": "M-F 09:00-17:00"}
        ],
        "policy": {
            "hard": {"min_gap_min": 0},
            "soft": {}
        },
        "slot_size_minutes": 15
    }
    
    scheduling_problem = SchedulingProblem(
        participants=["p1@test.com", "p2@test.com"],
        duration_minutes=30,  # 2 slots
        time_window_start="2025-12-01T09:00:00-05:00",
        time_window_end="2025-12-01T17:00:00-05:00"
    )
    
    return events_by_participant, context_json, scheduling_problem


if __name__ == "__main__":
    print("="*80)
    print("SIMPLE MULTI-MOVE TEST")
    print("="*80)
    print()
    print("Scenario:")
    print("  - 2 participants: p1@test.com, p2@test.com")
    print("  - p1 has event 10:00-11:00")
    print("  - p2 has event 11:00-12:00")
    print("  - Both free 9:00-10:00 and 12:00-17:00")
    print("  - Request: 30-minute meeting")
    print("  - Expected: Solution requiring 1 move")
    print()
    
    events_by_participant, context_json, scheduling_problem = create_simple_test_scenario()
    
    print("1. Normalizing events...")
    normalized_data = normalize_events(events_by_participant, context_json=context_json)
    
    slot_indexer = normalized_data["slot_indexer"]
    busy_slots = normalized_data["busy_slots"]
    work_hours_slots = normalized_data["work_hours_slots"]
    
    print(f"   Horizon: {slot_indexer.horizon_start} to {slot_indexer.horizon_end}")
    print(f"   Total slots: {slot_indexer.total_slots}")
    print()
    
    print("2. Busy slots:")
    for participant_id in scheduling_problem.participants:
        busy = busy_slots.get(participant_id, set())
        print(f"   {participant_id}: {sorted(busy)}")
    print()
    
    print("3. Generating ASP program with multi-move enabled...")
    asp_program = generate_asp_program(
        normalized_data,
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
    
    print("4. Solving with clingo...")
    solver = ClingoSolver(timeout=10)
    model, stats, result = solver.solve(asp_program)
    
    print(f"   Models found: {stats.get('models_found', 0)}")
    print(f"   Satisfiable: {stats.get('satisfiable', 'N/A')}")
    print(f"   Optimum: {stats.get('optimum', 'N/A')}")
    if stats.get('error'):
        print(f"   Error: {stats.get('error')}")
    print()
    
    if model:
        print("✓ Solution found!")
        predicates = extract_model_predicates(model)
        
        # Extract start slot
        start_preds = predicates.get("start", [])
        if start_preds:
            for args in start_preds:
                if args[0] == "q1":
                    start_slot = args[1]
                    dt = slot_indexer.slot_to_datetime(start_slot)
                    if dt:
                        et = pytz.timezone('America/New_York')
                        dt_et = dt.astimezone(et)
                        print(f"   Meeting start: Slot {start_slot} = {dt_et.strftime('%Y-%m-%d %A %H:%M')}")
        
        # Extract occurs slots
        occurs_preds = predicates.get("occurs", [])
        if occurs_preds:
            occurs_slots = [args[1] for args in occurs_preds if args[0] == "q1"]
            print(f"   Meeting occupies slots: {sorted(occurs_slots)}")
            
            # Check which participants have conflicts
            print()
            print("   Conflicts:")
            for participant_id in scheduling_problem.participants:
                busy = busy_slots.get(participant_id, set())
                overlaps = set(occurs_slots) & busy
                if overlaps:
                    print(f"     {participant_id}: overlaps at slots {sorted(overlaps)}")
                else:
                    print(f"     {participant_id}: no conflicts (free slot)")
    else:
        print("✗ No solution found")
        print("   This indicates an issue with the multi-move encoding")

