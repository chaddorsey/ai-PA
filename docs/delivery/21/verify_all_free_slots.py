#!/usr/bin/env python3
"""Comprehensive verification that all free slots are actually free for all participants"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytz
from dateutil import parser

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


def verify_free_slots():
    """Verify every free slot against actual event data"""
    
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
    
    print("="*80)
    print("COMPREHENSIVE FREE SLOTS VERIFICATION")
    print("="*80)
    print(f"\nSystem reports: {len(free_slots)} free slots")
    
    # Verify each slot
    et = pytz.timezone("America/New_York")
    verified_count = 0
    errors = []
    
    print(f"\nVerifying each slot...")
    for slot in sorted(free_slots):
        # Check if all participants are free for the entire meeting duration
        meeting_slots = set(range(slot, slot + duration_slots))
        is_valid = True
        issues = []
        
        for participant_id in participants:
            participant_busy = busy_slots.get(participant_id, set())
            participant_work_hours = work_hours_slots.get(participant_id, set())
            
            # Check busy slots
            busy_overlap = meeting_slots.intersection(participant_busy)
            if busy_overlap:
                is_valid = False
                issues.append(f"{participant_id}: BUSY at slots {sorted(busy_overlap)}")
            
            # Check work hours
            if work_hours_slots:  # Work hours are enforced
                if participant_work_hours:  # Participant has defined work hours
                    work_overlap = meeting_slots.intersection(participant_work_hours)
                    if len(work_overlap) < duration_slots:
                        # Not all meeting slots are in work hours
                        missing = meeting_slots - work_overlap
                        is_valid = False
                        issues.append(f"{participant_id}: OUTSIDE WORK HOURS at slots {sorted(missing)}")
        
        if is_valid:
            verified_count += 1
        else:
            slot_dt = slot_indexer.slot_to_datetime(slot)
            et_dt = slot_dt.astimezone(et)
            errors.append({
                "slot": slot,
                "datetime": et_dt,
                "issues": issues
            })
    
    print(f"\n" + "="*80)
    print("VERIFICATION RESULTS")
    print("="*80)
    print(f"✓ Verified correct: {verified_count} slots")
    print(f"✗ Errors found: {len(errors)} slots")
    
    if errors:
        print(f"\n" + "="*80)
        print("ERRORS - Slots incorrectly marked as free:")
        print("="*80)
        for error in errors[:10]:  # Show first 10 errors
            print(f"\nSlot {error['slot']}: {error['datetime'].strftime('%A, %B %d at %I:%M %p %Z')}")
            for issue in error['issues']:
                print(f"  ✗ {issue}")
    
    # Summary by day
    print(f"\n" + "="*80)
    print("FREE SLOTS BY DAY")
    print("="*80)
    
    by_day = {}
    for slot in sorted(free_slots):
        dt = slot_indexer.slot_to_datetime(slot)
        et_dt = dt.astimezone(et)
        day_key = et_dt.strftime("%A, %B %d")
        if day_key not in by_day:
            by_day[day_key] = []
        by_day[day_key].append(et_dt.strftime("%I:%M %p"))
    
    total = 0
    for day in sorted(by_day.keys()):
        count = len(by_day[day])
        total += count
        print(f"{day}: {count} slots")
    
    print(f"\nTotal: {total} slots")
    
    return len(errors) == 0


if __name__ == "__main__":
    success = verify_free_slots()
    sys.exit(0 if success else 1)

