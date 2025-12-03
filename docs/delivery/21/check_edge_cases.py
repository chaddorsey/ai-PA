#!/usr/bin/env python3
"""Check for edge cases in free slot calculation"""

import json
import sys
from pathlib import Path
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


def check_edge_cases():
    """Check various edge cases"""
    
    print("="*80)
    print("EDGE CASE TESTING")
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
    
    normalized = normalize_events(events_by_participant=events, context_json=context_json)
    slot_indexer = normalized["slot_indexer"]
    busy_slots = normalized["busy_slots"]
    work_hours_slots = normalized["work_hours_slots"]
    
    all_slots = list(range(slot_indexer.total_slots))
    participants = ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
    et = pytz.timezone("America/New_York")
    
    # Test 1: Check boundary conditions - slot exactly at work hours start/end
    print("\n" + "="*80)
    print("TEST 1: Work Hours Boundaries")
    print("="*80)
    
    # Get first work hour slot
    chad_work = work_hours_slots.get("cdorsey@concord.org", set())
    if chad_work:
        first_work_slot = min(chad_work)
        last_work_slot = max(chad_work)
        
        first_dt = slot_indexer.slot_to_datetime(first_work_slot)
        last_dt = slot_indexer.slot_to_datetime(last_work_slot)
        
        print(f"First work hour slot: {first_work_slot} = {first_dt.astimezone(et).strftime('%a %b %d %I:%M %p')}")
        print(f"Last work hour slot: {last_work_slot} = {last_dt.astimezone(et).strftime('%a %b %d %I:%M %p')}")
        
        # Check if a meeting starting at last_work_slot - 2 would fit (needs 3 slots)
        test_slot = last_work_slot - 2
        if test_slot >= 0:
            meeting_slots = set(range(test_slot, test_slot + 3))
            fits_in_work_hours = meeting_slots.issubset(chad_work)
            print(f"\nMeeting starting at slot {test_slot} (needs 3 slots):")
            print(f"  Fits in work hours: {fits_in_work_hours}")
            if not fits_in_work_hours:
                outside = meeting_slots - chad_work
                print(f"  Slots outside: {sorted(outside)}")
    
    # Test 2: Check events at exact boundaries
    print("\n" + "="*80)
    print("TEST 2: Event Boundaries")
    print("="*80)
    
    # Check if Chad's "Chad out" event boundaries are handled correctly
    chad_busy = busy_slots.get("cdorsey@concord.org", set())
    
    # Event is 10:30 AM - 12:45 PM
    # Should include slots: 10:30, 10:45, 11:00, 11:15, 11:30, 11:45, 12:00, 12:15, 12:30 (9 slots, since 12:45 is exclusive)
    
    # Find slot for 10:30 AM EST
    event_start = et.localize(parser.parse("2025-12-01 10:30:00"))
    event_start_utc = event_start.astimezone(pytz.UTC)
    start_slot = slot_indexer.datetime_to_slot(event_start_utc)
    
    # Find slot for 12:45 PM EST  
    event_end = et.localize(parser.parse("2025-12-01 12:45:00"))
    event_end_utc = event_end.astimezone(pytz.UTC)
    end_slot = slot_indexer.datetime_to_slot(event_end_utc)
    
    print(f"Chad's 'Chad out' event:")
    print(f"  Start: 10:30 AM EST -> Slot {start_slot}")
    print(f"  End: 12:45 PM EST -> Slot {end_slot} (exclusive)")
    
    # Expected busy slots: start_slot to end_slot-1 (if end_slot is the slot that starts at 12:45)
    # Actually, get_slots_in_range uses exclusive end, so it should include slots from start_slot
    # up to but not including the slot that starts at end time
    expected_busy_slots = []
    for slot in range(start_slot, end_slot):  # end_slot is exclusive
        if slot < slot_indexer.total_slots:
            expected_busy_slots.append(slot)
    
    actual_busy_slots = sorted([s for s in expected_busy_slots if s in chad_busy])
    
    print(f"  Expected busy slots (range {start_slot} to {end_slot-1}): {expected_busy_slots[:5]}... ({len(expected_busy_slots)} total)")
    print(f"  Actual busy slots in range: {actual_busy_slots[:5]}... ({len(actual_busy_slots)} total)")
    
    missing = set(expected_busy_slots) - chad_busy
    if missing:
        print(f"  ✗ MISSING: {sorted(missing)}")
    else:
        print(f"  ✓ All expected slots are marked as busy")
    
    # Test 3: Check for consecutive free slots (meeting can span multiple free periods)
    print("\n" + "="*80)
    print("TEST 3: Meeting Duration Spanning")
    print("="*80)
    
    duration_slots = 3  # 45 minutes
    free_slots = _find_free_slots(
        all_slots, busy_slots, work_hours_slots,
        participants, duration_slots, min_gap_slots=0
    )
    
    # Check if any free slots have gaps in the middle (shouldn't happen)
    gaps_found = []
    for slot in sorted(free_slots):
        meeting_slots = list(range(slot, slot + duration_slots))
        # All slots in the meeting should be free
        for p in participants:
            p_busy = busy_slots.get(p, set())
            busy_in_range = [s for s in meeting_slots if s in p_busy]
            if busy_in_range:
                gaps_found.append((slot, p, busy_in_range))
    
    if gaps_found:
        print(f"✗ Found {len(gaps_found)} free slots with busy slots in the middle!")
        for slot, p, busy in gaps_found[:5]:
            slot_dt = slot_indexer.slot_to_datetime(slot)
            print(f"  Slot {slot} ({slot_dt.astimezone(et).strftime('%I:%M %p')}): {p} busy at {busy}")
    else:
        print(f"✓ No gaps found - all free slots have consecutive availability")
    
    # Test 4: Check work hours enforcement
    print("\n" + "="*80)
    print("TEST 4: Work Hours Enforcement")
    print("="*80)
    
    outside_work_hours = 0
    for slot in sorted(free_slots):
        slot_dt = slot_indexer.slot_to_datetime(slot)
        et_dt = slot_dt.astimezone(et)
        
        # Check if within work hours for all participants
        meeting_slots = set(range(slot, slot + duration_slots))
        all_in_work_hours = True
        
        for p in participants:
            p_work = work_hours_slots.get(p, set())
            if p_work:  # Work hours defined
                work_overlap = meeting_slots.intersection(p_work)
                if len(work_overlap) < duration_slots:
                    all_in_work_hours = False
                    break
        
        if not all_in_work_hours:
            outside_work_hours += 1
    
    print(f"Free slots outside work hours: {outside_work_hours}")
    if outside_work_hours > 0:
        print(f"✗ ERROR: {outside_work_hours} slots are outside work hours!")
    else:
        print(f"✓ All free slots are within work hours")
    
    # Test 5: Check weekend exclusion
    print("\n" + "="*80)
    print("TEST 5: Weekend Exclusion")
    print("="*80)
    
    weekend_slots = 0
    for slot in sorted(free_slots):
        slot_dt = slot_indexer.slot_to_datetime(slot)
        et_dt = slot_dt.astimezone(et)
        if et_dt.weekday() >= 5:  # Saturday or Sunday
            weekend_slots += 1
    
    print(f"Free slots on weekends: {weekend_slots}")
    if weekend_slots > 0:
        print(f"✗ ERROR: {weekend_slots} slots are on weekends!")
        for slot in sorted(free_slots)[:10]:
            slot_dt = slot_indexer.slot_to_datetime(slot)
            et_dt = slot_dt.astimezone(et)
            if et_dt.weekday() >= 5:
                print(f"  Slot {slot}: {et_dt.strftime('%A, %B %d at %I:%M %p')}")
    else:
        print(f"✓ No weekend slots (work hours are weekdays only)")
    
    return outside_work_hours == 0 and weekend_slots == 0 and len(gaps_found) == 0


if __name__ == "__main__":
    success = check_edge_cases()
    sys.exit(0 if success else 1)

