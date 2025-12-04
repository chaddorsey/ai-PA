#!/usr/bin/env python3
"""
Comprehensive debugging of UNSAT issues in ASP multi-move encoding.
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
from scheduling_orchestrator.fact_generator import generate_asp_program, _find_free_slots
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


def analyze_constraints(normalized_data, scheduling_problem):
    """Analyze what constraints are blocking solutions"""
    slot_indexer = normalized_data["slot_indexer"]
    busy_slots = normalized_data.get("busy_slots", {})
    work_hours_slots = normalized_data.get("work_hours_slots", {})
    locked_events = normalized_data.get("locked_events", {})
    duration_slots = max(1, scheduling_problem.duration_minutes // 15)
    
    print("\n" + "="*80)
    print("CONSTRAINT ANALYSIS")
    print("="*80)
    
    print(f"\n1. Horizon: {slot_indexer.horizon_start} to {slot_indexer.horizon_end}")
    print(f"   Total slots: {slot_indexer.total_slots}")
    print(f"   Meeting duration: {duration_slots} slots ({scheduling_problem.duration_minutes} minutes)")
    
    print(f"\n2. Work hours coverage:")
    for participant_id in scheduling_problem.participants:
        wh = work_hours_slots.get(participant_id, set())
        busy = busy_slots.get(participant_id, set())
        locked = locked_events.get(participant_id, set())
        print(f"   {participant_id}:")
        print(f"     Work hours slots: {len(wh)}")
        print(f"     Busy slots: {len(busy)}")
        print(f"     Locked slots: {len(locked)}")
        print(f"     Free slots: {len(wh - busy)}")
        
        # Check if there are ANY slots where meeting could fit
        potential_slots = []
        for start_slot in range(slot_indexer.total_slots - duration_slots + 1):
            meeting_slots = set(range(start_slot, start_slot + duration_slots))
            if meeting_slots.issubset(wh):  # All slots in work hours
                if not meeting_slots.issubset(locked):  # Not all locked
                    potential_slots.append(start_slot)
        print(f"     Potential start slots (in work hours, not all locked): {len(potential_slots)}")
    
    print(f"\n3. Intersection analysis:")
    # Find slots where at least one participant is free
    all_slots = set(range(slot_indexer.total_slots))
    slots_with_potential = []
    
    for start_slot in range(slot_indexer.total_slots - duration_slots + 1):
        meeting_slots = set(range(start_slot, start_slot + duration_slots))
        
        # Check each participant
        participants_free = []
        participants_busy = []
        participants_locked = []
        participants_work_hours = []
        
        for participant_id in scheduling_problem.participants:
            wh = work_hours_slots.get(participant_id, set())
            busy = busy_slots.get(participant_id, set())
            locked = locked_events.get(participant_id, set())
            
            if meeting_slots.issubset(wh):
                participants_work_hours.append(participant_id)
            
            overlap_busy = meeting_slots & busy
            overlap_locked = meeting_slots & locked
            
            if overlap_locked:
                participants_locked.append(participant_id)
            elif overlap_busy:
                participants_busy.append(participant_id)
            else:
                participants_free.append(participant_id)
        
        # If all participants have work hours, and no locked conflicts, this is a candidate
        if (len(participants_work_hours) == len(scheduling_problem.participants) and
            len(participants_locked) == 0):
            slots_with_potential.append({
                'slot': start_slot,
                'free': participants_free,
                'busy': participants_busy,
                'locked': participants_locked
            })
    
    print(f"   Slots where meeting could fit (all in work hours, no locked conflicts): {len(slots_with_potential)}")
    if slots_with_potential:
        print("   Sample slots:")
        for slot_info in slots_with_potential[:5]:
            dt = slot_indexer.slot_to_datetime(slot_info['slot'])
            if dt:
                et = pytz.timezone('America/New_York')
                dt_et = dt.astimezone(et)
                print(f"     Slot {slot_info['slot']}: {dt_et.strftime('%Y-%m-%d %A %H:%M')}")
                print(f"       Free: {slot_info['free']}")
                print(f"       Busy (flexible): {slot_info['busy']}")
    
    return slots_with_potential


if __name__ == "__main__":
    print("="*80)
    print("UNSAT ISSUE INVESTIGATION")
    print("="*80)
    
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
    
    print("\n1. Normalizing events...")
    normalized_data = normalize_events(events_by_participant, context_json=context_json)
    
    print("\n2. Analyzing constraints BEFORE horizon reduction...")
    slots_before = analyze_constraints(normalized_data, scheduling_problem)
    
    print("\n3. Reducing horizon for ASP...")
    asp_normalized_data = reduce_horizon_to_feasible_window(
        normalized_data,
        scheduling_problem,
        max_slots=48,
        prefer_time_window=True
    )
    
    print("\n4. Analyzing constraints AFTER horizon reduction...")
    slots_after = analyze_constraints(asp_normalized_data, scheduling_problem)
    
    print("\n5. Generating ASP program...")
    asp_program = generate_asp_program(
        asp_normalized_data,
        scheduling_problem,
        request_id="q1",
        include_soft_constraints=False,  # Start without soft constraints
        include_work_hours=True,
        include_min_gap=True,
        include_locked_events=True,
        phase=3,  # Hard constraints only
        allow_multi_move=True
    )
    
    # Save program
    output_file = Path(__file__).parent / "asp_program_unsat_debug.lp"
    with open(output_file, 'w') as f:
        f.write(asp_program)
    print(f"   Saved to: {output_file}")
    
    # Count key facts
    facts = asp_program.split('\n')
    window_count = sum(1 for f in facts if f.strip().startswith('window(q1,'))
    occurs_count = sum(1 for f in facts if f.strip().startswith('occurs_if_start(q1,'))
    busy_count = sum(1 for f in facts if 'busy(' in f)
    locked_count = sum(1 for f in facts if 'locked_event(' in f)
    workhours_count = sum(1 for f in facts if 'workhours(' in f)
    
    print(f"\n6. ASP program statistics:")
    print(f"   Total lines: {len(facts)}")
    print(f"   window facts: {window_count}")
    print(f"   occurs_if_start facts: {occurs_count}")
    print(f"   busy facts: {busy_count}")
    print(f"   locked_event facts: {locked_count}")
    print(f"   workhours facts: {workhours_count}")
    
    # Check constraint rules
    min_gap_locked = sum(1 for f in facts if 'locked_event(P, T2)' in f and 'min_gap' in f)
    min_gap_busy = sum(1 for f in facts if 'busy(P, T2)' in f and 'min_gap' in f and 'locked_event' not in f)
    print(f"\n7. Constraint rules:")
    print(f"   min_gap with locked_event: {min_gap_locked}")
    print(f"   min_gap with busy (should be 0 in multi-move): {min_gap_busy}")
    
    print("\n8. Testing with minimal constraints...")
    solver = ClingoSolver(timeout=10)
    model, stats, result = solver.solve(asp_program)
    
    print(f"   Models found: {stats.get('models_found', 0)}")
    print(f"   Satisfiable: {stats.get('satisfiable', 'N/A')}")
    if stats.get('error'):
        print(f"   Error: {stats['error']}")

