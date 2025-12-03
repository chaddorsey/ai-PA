#!/usr/bin/env python3
"""
Comprehensive verification of free slots - check every slot against actual events.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
import pytz
from dateutil import parser

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
from test_e2e_orchestrator import load_events_from_example


def check_all_slots():
    """Check all free slots against actual events"""
    print("="*80)
    print("COMPREHENSIVE FREE SLOTS VERIFICATION")
    print("="*80)
    
    events = load_events_from_example(Path(__file__).parent / "example_event_data.md")
    
    context_json = {
        "timeframe": {"from": "2025-12-01", "to": "2025-12-12", "tz": "America/New_York"},
        "requester_id": "cdorsey@concord.org",
        "participants": [
            {"id": "cdorsey@concord.org", "email": "cdorsey@concord.org", "name": "Chad"},
            {"id": "sbrau@concord.org", "email": "sbrau@concord.org", "name": "Sue"},
            {"id": "dkehoe@concord.org", "email": "dkehoe@concord.org", "name": "Danielle"}
        ],
        "policy": {"hard": {"min_gap_min": 0}}
    }
    
    # Normalize
    normalized = normalize_events(events_by_participant=events, context_json=context_json)
    slot_indexer = normalized["slot_indexer"]
    busy_slots = normalized["busy_slots"]
    work_hours_slots = normalized["work_hours_slots"]
    
    # Get free slots
    all_slots = list(range(slot_indexer.total_slots))
    duration_slots = 3  # 45 minutes
    participants = ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
    
    free_slots = _find_free_slots(
        all_slots, busy_slots, work_hours_slots,
        participants, duration_slots, min_gap_slots=0
    )
    
    print(f"\nSystem reports: {len(free_slots)} free slots\n")
    
    # Check each free slot
    et = pytz.timezone("America/New_York")
    false_positives = []
    
    print("Checking each slot...")
    for i, slot in enumerate(sorted(free_slots)):
        slot_dt = slot_indexer.slot_to_datetime(slot)
        meeting_end_dt = slot_indexer.slot_to_datetime(slot + duration_slots)
        et_slot = slot_dt.astimezone(et)
        et_end = meeting_end_dt.astimezone(et)
        
        # Check if any participant has a busy slot in this range
        conflicts = []
        for p in participants:
            p_busy = busy_slots.get(p, set())
            meeting_range = set(range(slot, slot + duration_slots))
            overlap = meeting_range.intersection(p_busy)
            if overlap:
                conflicts.append({
                    "participant": p,
                    "overlapping_slots": sorted(overlap)
                })
        
        if conflicts:
            false_positives.append({
                "slot": slot,
                "datetime": et_slot,
                "end": et_end,
                "conflicts": conflicts
            })
    
    print(f"\n✓ Verified free: {len(free_slots) - len(false_positives)}")
    print(f"✗ False positives: {len(false_positives)}")
    
    if false_positives:
        print(f"\n" + "="*80)
        print("FALSE POSITIVES - Slots marked free but have busy slots!")
        print("="*80)
        for fp in false_positives[:10]:
            print(f"\nSlot {fp['slot']}: {fp['datetime'].strftime('%A, %B %d at %I:%M %p %Z')} - {fp['end'].strftime('%I:%M %p')}")
            for conflict in fp['conflicts']:
                print(f"  ✗ {conflict['participant']}: Busy slots {conflict['overlapping_slots']}")
    
    # Also check busy slot counts
    print(f"\n" + "="*80)
    print("BUSY SLOT SUMMARY")
    print("="*80)
    for p in participants:
        busy = busy_slots.get(p, set())
        print(f"{p}: {len(busy)} busy slots")
    
    # Check work hours
    print(f"\n" + "="*80)
    print("WORK HOURS SLOTS")
    print("="*80)
    for p in participants:
        wh = work_hours_slots.get(p, set())
        print(f"{p}: {len(wh)} work hour slots")
    
    # Sample some slots to show what they are
    print(f"\n" + "="*80)
    print("SAMPLE OF FREE SLOTS")
    print("="*80)
    for slot in sorted(free_slots)[:10]:
        dt = slot_indexer.slot_to_datetime(slot)
        et_dt = dt.astimezone(et)
        print(f"Slot {slot}: {et_dt.strftime('%A, %B %d at %I:%M %p %Z')}")


if __name__ == "__main__":
    check_all_slots()

