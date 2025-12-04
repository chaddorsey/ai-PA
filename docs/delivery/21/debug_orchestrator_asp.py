#!/usr/bin/env python3
"""
Debug why orchestrator reports 0 models while direct testing finds models.
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

from scheduling_orchestrator.orchestrate_scheduling import orchestrate_scheduling
from scheduling_orchestrator.fact_generator import generate_asp_program
from scheduling_orchestrator.schemas import SchedulingProblem
from scheduling_orchestrator.normalizer import normalize_events
from scheduling_orchestrator.horizon_reducer import reduce_horizon_to_feasible_window
from scheduling_orchestrator.clingo_wrapper import ClingoSolver, extract_scheduling_solution

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
    print("ORCHESTRATOR ASP DEBUG")
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
    
    utterance = "Find me possible 45-minute meeting slots with Sue and Danielle between Dec. 3 and 12."
    
    print("1. Running orchestrator...")
    result = orchestrate_scheduling(utterance, events_by_participant, context_json)
    
    print("\n2. Checking result...")
    print(f"   Status: {result.get('status')}")
    if 'debug' in result and result['debug']:
        asp_stats = result['debug'].get('asp_stats', {})
        print(f"   ASP Models found: {asp_stats.get('models', 'N/A')}")
        print(f"   ASP Satisfiable: {asp_stats.get('satisfiable', 'N/A')}")
        print(f"   ASP Error: {asp_stats.get('error', 'N/A')}")
    
    print("\n3. Replicating orchestrator's ASP call directly...")
    
    # Replicate what orchestrator does
    from scheduling_orchestrator.dspy_extraction import extract_with_fallback
    scheduling_problem = extract_with_fallback(utterance, context_json)
    
    normalized_data = normalize_events(events_by_participant, context_json=context_json)
    slot_indexer = normalized_data["slot_indexer"]
    
    # Horizon reduction (as orchestrator does)
    asp_normalized_data = reduce_horizon_to_feasible_window(
        normalized_data,
        scheduling_problem,
        max_slots=48,
        prefer_time_window=True
    )
    
    # Generate ASP program (as orchestrator does)
    asp_program = generate_asp_program(
        asp_normalized_data,
        scheduling_problem,
        request_id="q1",
        include_soft_constraints=True,
        include_work_hours=True,
        include_min_gap=True,
        include_locked_events=True,
        phase=4,  # Full program with all constraints
        allow_multi_move=True  # Enable multi-move encoding
    )
    
    print(f"   Generated program: {len(asp_program)} chars, {len(asp_program.splitlines())} lines")
    
    # Solve (as orchestrator does)
    asp_solver = ClingoSolver(timeout=30)
    asp_model, asp_stats, asp_result = asp_solver.solve(asp_program)
    
    print(f"\n4. Direct ASP solver results:")
    print(f"   Models found: {asp_stats.get('models_found', 0)}")
    print(f"   Satisfiable: {asp_stats.get('satisfiable', 'N/A')}")
    print(f"   asp_model type: {type(asp_model)}")
    print(f"   asp_model truthy: {bool(asp_model)}")
    if asp_model:
        print(f"   asp_model keys: {asp_model.keys() if isinstance(asp_model, dict) else 'N/A'}")
    print(f"   asp_result.satisfiable: {asp_result.satisfiable if hasattr(asp_result, 'satisfiable') else 'N/A'}")
    
    if asp_model and hasattr(asp_result, 'satisfiable') and asp_result.satisfiable:
        print("\n5. Extracting solution...")
        asp_solution = extract_scheduling_solution(asp_model, "q1")
        print(f"   Solution extracted: {asp_solution is not None}")
        if asp_solution:
            print(f"   Start slot: {asp_solution.get('start_slot')}")
    else:
        print("\n5. No solution to extract")
        if not asp_model:
            print("   Reason: asp_model is None/empty")
        elif not hasattr(asp_result, 'satisfiable'):
            print("   Reason: asp_result has no satisfiable attribute")
        elif not asp_result.satisfiable:
            print("   Reason: asp_result.satisfiable is False")

