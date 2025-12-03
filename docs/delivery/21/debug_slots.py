#!/usr/bin/env python3
"""
Debug script to understand why we're getting 140 free slots and slots outside work hours.
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
from test_e2e_orchestrator import load_events_from_example


def analyze_free_slots():
    """Analyze free slots and work hours enforcement"""
    print("="*80)
    print("FREE SLOTS ANALYSIS")
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
            {
                "id": "cdorsey@concord.org",
                "email": "cdorsey@concord.org",
                "name": "Chad"
            },
            {
                "id": "sbrau@concord.org",
                "email": "sbrau@concord.org",
                "name": "Sue"
            },
            {
                "id": "dkehoe@concord.org",
                "email": "dkehoe@concord.org",
                "name": "Danielle"
            }
        ],
        "policy": {
            "hard": {
                "min_gap_min": 0
            }
        }
    }
    
    # Normalize events
    from scheduling_orchestrator.normalizer import SlotIndexer
    normalized = normalize_events(
        events_by_participant=events,
        context_json=context_json
    )
    
    slot_indexer = normalized["slot_indexer"]
    busy_slots = normalized["busy_slots"]
    work_hours_slots = normalized["work_hours_slots"]
    
    print(f"\nNormalization Results:")
    print(f"  Total slots in horizon: {slot_indexer.total_slots}")
    print(f"  Horizon start: {slot_indexer.horizon_start}")
    print(f"  Horizon end: {slot_indexer.horizon_end}")
    
    print(f"\nWork Hours Slots:")
    for participant_id, slots in work_hours_slots.items():
        print(f"  {participant_id}: {len(slots)} work hour slots")
        if slots:
            # Convert first and last slots to times
            first_slot = min(slots)
            last_slot = max(slots)
            first_dt = slot_indexer.slot_to_datetime(first_slot)
            last_dt = slot_indexer.slot_to_datetime(last_slot)
            et = pytz.timezone("America/New_York")
            first_et = first_dt.astimezone(et)
            last_et = last_dt.astimezone(et)
            print(f"    Range: {first_et.strftime('%a %b %d %I:%M %p %Z')} to {last_et.strftime('%a %b %d %I:%M %p %Z')}")
            
            # Check for weekdays only
            weekdays_only = True
            for slot in list(slots)[:10]:  # Sample first 10
                dt = slot_indexer.slot_to_datetime(slot)
                et_dt = dt.astimezone(et)
                if et_dt.weekday() >= 5:  # Saturday or Sunday
                    weekdays_only = False
                    print(f"    WARNING: Found weekend slot: {et_dt.strftime('%a %b %d')}")
                    break
            if weekdays_only:
                print(f"    ✓ Weekdays only (checked first 10)")
    
    print(f"\nBusy Slots:")
    for participant_id, slots in busy_slots.items():
        print(f"  {participant_id}: {len(slots)} busy slots")
    
    # Check free slots WITH work hours
    duration_slots = 3  # 45 minutes = 3 slots
    participants = ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
    
    print(f"\n" + "="*80)
    print("FREE SLOTS ANALYSIS (with work hours)")
    print("="*80)
    
    all_slots = list(range(slot_indexer.total_slots))
    free_slots_with_workhours = _find_free_slots(
        all_slots,
        busy_slots,
        work_hours_slots,
        participants,
        duration_slots,
        min_gap_slots=0
    )
    
    print(f"  Free slots found (WITH work hours): {len(free_slots_with_workhours)}")
    
    # Check free slots WITHOUT work hours
    free_slots_no_workhours = _find_free_slots(
        all_slots,
        busy_slots,
        {},  # Empty dict = no work hours
        participants,
        duration_slots,
        min_gap_slots=0
    )
    
    print(f"  Free slots found (WITHOUT work hours): {len(free_slots_no_workhours)}")
    
    # Sample some free slots to see what times they are
    print(f"\n  Sample of first 10 free slots (WITH work hours):")
    for i, slot in enumerate(sorted(free_slots_with_workhours)[:10]):
        dt = slot_indexer.slot_to_datetime(slot)
        et = pytz.timezone("America/New_York")
        et_dt = dt.astimezone(et)
        is_weekday = et_dt.weekday() < 5
        is_9_to_5 = 9 <= et_dt.hour < 17 or (et_dt.hour == 17 and et_dt.minute == 0)
        status = "✓" if (is_weekday and is_9_to_5) else "✗"
        print(f"    {i+1}. Slot {slot}: {et_dt.strftime('%a %b %d at %I:%M %p %Z')} {status}")
        if not is_weekday:
            print(f"       ⚠ Weekend!")
        if not is_9_to_5:
            print(f"       ⚠ Outside 9-5!")
    
    # Check the actual result from orchestrator
    print(f"\n" + "="*80)
    print("ORCHESTRATOR RESULT")
    print("="*80)
    
    utterance = "Find me possible 45-minute meeting slots with Sue and Danielle between Dec. 1 and 12."
    result = orchestrate_scheduling(
        utterance=utterance,
        events_by_participant=json.dumps(events),
        context_json=json.dumps(context_json)
    )
    
    if result.get("status") == "ok" and result.get("proposals"):
        proposal = result["proposals"][0]
        start_utc = proposal.get("start_utc")
        utc_dt = parser.parse(start_utc)
        et = pytz.timezone("America/New_York")
        et_dt = utc_dt.astimezone(et)
        
        print(f"  Returned proposal:")
        print(f"    Start UTC: {start_utc}")
        print(f"    Start ET:  {et_dt.strftime('%A, %B %d at %I:%M %p %Z')}")
        print(f"    Day: {et_dt.strftime('%A')}, Hour: {et_dt.hour}")
        
        is_weekday = et_dt.weekday() < 5
        is_9_to_5 = 9 <= et_dt.hour < 17 or (et_dt.hour == 17 and et_dt.minute == 0)
        
        print(f"    Is weekday: {is_weekday}")
        print(f"    Is 9-5: {is_9_to_5}")
        
        if not (is_weekday and is_9_to_5):
            print(f"    ✗ PROBLEM: Slot is outside work hours!")
            
            # Try to find which slot this is
            # Need to find the slot index for this datetime
            print(f"\n    Debugging slot calculation...")
            # The slot_indexer should be able to convert this
            try:
                slot_idx = slot_indexer.datetime_to_slot(utc_dt)
                print(f"    Slot index: {slot_idx}")
                print(f"    Is in free_slots_with_workhours: {slot_idx in free_slots_with_workhours}")
                print(f"    Is in free_slots_no_workhours: {slot_idx in free_slots_no_workhours}")
                
                # Check work hours for each participant
                for p in participants:
                    wh = work_hours_slots.get(p, set())
                    print(f"    {p} work hours contains slot {slot_idx}: {slot_idx in wh}")
            except Exception as e:
                print(f"    Error finding slot: {e}")


if __name__ == "__main__":
    analyze_free_slots()

