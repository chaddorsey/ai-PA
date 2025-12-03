#!/usr/bin/env python3
"""
More detailed debugging - check what happens after horizon reduction.
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import pytz
from dateutil import parser

# Load .env
project_root = Path(__file__).parent.parent.parent.parent
env_path = project_root / '.env'
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

# Add paths
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "letta"))

from scheduling_orchestrator.orchestrate_scheduling import orchestrate_scheduling
from scheduling_orchestrator.normalizer import normalize_events
from scheduling_orchestrator.fact_generator import _find_free_slots
from scheduling_orchestrator.horizon_reducer import reduce_horizon_to_feasible_window
from test_e2e_orchestrator import load_events_from_example


def analyze_after_horizon_reduction():
    """Check what happens to free slots after horizon reduction"""
    print("="*80)
    print("HORIZON REDUCTION ANALYSIS")
    print("="*80)
    
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
    
    print(f"\nBEFORE Horizon Reduction:")
    print(f"  Total slots: {slot_indexer.total_slots}")
    
    all_slots = list(range(slot_indexer.total_slots))
    duration_slots = 3  # 45 minutes
    participants = ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
    
    free_slots_before = _find_free_slots(
        all_slots, busy_slots, work_hours_slots,
        participants, duration_slots, min_gap_slots=0
    )
    print(f"  Free slots: {len(free_slots_before)}")
    
    # Now reduce horizon
    print(f"\nReducing horizon...")
    
    # Create a dummy scheduling problem for horizon reduction
    from scheduling_orchestrator.schemas import SchedulingProblem
    scheduling_problem = SchedulingProblem(
        participants=participants,
        duration_minutes=45,
        time_window_start="2025-12-01T00:00:00-05:00",
        time_window_end="2025-12-12T23:59:59-05:00"
    )
    
    reduced_data = reduce_horizon_to_feasible_window(
        normalized_data=normalized.copy(),
        scheduling_problem=scheduling_problem,
        max_slots=672  # 7 days
    )
    
    if reduced_data:
        reduced_slot_indexer = reduced_data["slot_indexer"]
        reduced_busy_slots = reduced_data["busy_slots"]
        reduced_work_hours_slots = reduced_data["work_hours_slots"]
        
        print(f"\nAFTER Horizon Reduction:")
        print(f"  Total slots: {reduced_slot_indexer.total_slots}")
        print(f"  Horizon start: {reduced_slot_indexer.horizon_start}")
        print(f"  Horizon end: {reduced_slot_indexer.horizon_end}")
        
        print(f"\n  Work hours slots:")
        for p in participants:
            wh = reduced_work_hours_slots.get(p, set())
            print(f"    {p}: {len(wh)} slots")
            if wh:
                first = min(wh)
                last = max(wh)
                first_dt = reduced_slot_indexer.slot_to_datetime(first)
                last_dt = reduced_slot_indexer.slot_to_datetime(last)
                et = pytz.timezone("America/New_York")
                print(f"      Range: {first_dt.astimezone(et).strftime('%a %b %d %I:%M %p')} to {last_dt.astimezone(et).strftime('%a %b %d %I:%M %p')}")
        
        reduced_all_slots = list(range(reduced_slot_indexer.total_slots))
        
        free_slots_after = _find_free_slots(
            reduced_all_slots, reduced_busy_slots, reduced_work_hours_slots,
            participants, duration_slots, min_gap_slots=0
        )
        print(f"\n  Free slots (with work hours): {len(free_slots_after)}")
        
        # Also check without work hours for comparison
        free_slots_no_wh = _find_free_slots(
            reduced_all_slots, reduced_busy_slots, {},
            participants, duration_slots, min_gap_slots=0
        )
        print(f"  Free slots (without work hours): {len(free_slots_no_wh)}")
        
        # Sample some slots
        print(f"\n  Sample of first 5 free slots:")
        for i, slot in enumerate(sorted(free_slots_after)[:5]):
            dt = reduced_slot_indexer.slot_to_datetime(slot)
            et = pytz.timezone("America/New_York")
            et_dt = dt.astimezone(et)
            is_weekday = et_dt.weekday() < 5
            is_9_to_5 = 9 <= et_dt.hour < 17 or (et_dt.hour == 17 and et_dt.minute == 0)
            status = "✓" if (is_weekday and is_9_to_5) else "✗"
            print(f"    {i+1}. Slot {slot}: {et_dt.strftime('%a %b %d at %I:%M %p %Z')} {status}")
    else:
        print("  Horizon reduction returned None - no reduction performed")


if __name__ == "__main__":
    analyze_after_horizon_reduction()

