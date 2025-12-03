#!/usr/bin/env python3
"""List the first 10 available slots returned by the orchestrator"""

import json
import sys
from pathlib import Path
from dateutil import parser
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
from scheduling_orchestrator.fact_generator import _find_free_slots
from scheduling_orchestrator.python_solver import find_optimal_slot
from test_e2e_orchestrator import load_events_from_example


def get_first_10_slots():
    """Get and display the first 10 available slots"""
    
    events = load_events_from_example(Path(__file__).parent / "example_event_data.md")
    
    context_json = {
        "timeframe": {
            "from": "2025-12-01",
            "to": "2025-12-12",
            "tz": "America/New_York"
        },
        "requester_id": "cdorsey@concord.org",
        "participants": [
            {"id": "cdorsey@concord.org", "email": "cdorsey@concord.org", "name": "Chad"},
            {"id": "sbrau@concord.org", "email": "sbrau@concord.org", "name": "Sue"},
            {"id": "dkehoe@concord.org", "email": "dkehoe@concord.org", "name": "Danielle"}
        ],
        "policy": {"hard": {"min_gap_min": 0}}
    }
    
    # Normalize events
    normalized = normalize_events(
        events_by_participant=events,
        context_json=context_json
    )
    
    slot_indexer = normalized["slot_indexer"]
    busy_slots = normalized["busy_slots"]
    work_hours_slots = normalized["work_hours_slots"]
    
    duration_slots = 3  # 45 minutes
    participants = ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
    
    # Get free slots
    all_slots = list(range(slot_indexer.total_slots))
    free_slots = _find_free_slots(
        all_slots, busy_slots, work_hours_slots,
        participants, duration_slots, min_gap_slots=0
    )
    
    # Create a simple scheduling problem for ranking
    from scheduling_orchestrator.schemas import SchedulingProblem
    scheduling_problem = SchedulingProblem(
        participants=participants,
        duration_minutes=45,
        time_window_start="2025-12-01T00:00:00-05:00",
        time_window_end="2025-12-12T23:59:59-05:00"
    )
    
    # Rank the slots
    from scheduling_orchestrator.python_solver import _rank_slots
    ranked = _rank_slots(
        list(free_slots),
        normalized,
        scheduling_problem,
        slot_indexer,
        context_json
    )
    
    # Display first 10
    et = pytz.timezone("America/New_York")
    
    print("="*80)
    print("FIRST 10 AVAILABLE SLOTS (ranked by preference)")
    print("="*80)
    print()
    
    for i, (slot, score) in enumerate(ranked[:10], 1):
        slot_dt = slot_indexer.slot_to_datetime(slot)
        meeting_end_dt = slot_indexer.slot_to_datetime(slot + duration_slots)
        et_start = slot_dt.astimezone(et)
        et_end = meeting_end_dt.astimezone(et)
        
        print(f"{i}. {et_start.strftime('%A, %B %d, %Y at %I:%M %p')} - {et_end.strftime('%I:%M %p')} {et_start.tzname()}")
        print(f"   Slot index: {slot}, Score: {score:.2f}")
        print()
    
    print("="*80)
    print(f"Total available slots: {len(free_slots)}")
    print("="*80)


if __name__ == "__main__":
    get_first_10_slots()

