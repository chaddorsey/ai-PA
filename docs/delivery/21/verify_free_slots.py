#!/usr/bin/env python3
"""
Verify that all "free" slots are actually free for all participants.
Check the specific Dec 1 2:30 PM slot and list all conflicts.
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

from scheduling_orchestrator.normalizer import normalize_events, SlotIndexer
from scheduling_orchestrator.fact_generator import _find_free_slots
from test_e2e_orchestrator import load_events_from_example


def load_events_raw():
    """Load events in raw format for checking"""
    events_by_participant = load_events_from_example(Path(__file__).parent / "example_event_data.md")
    
    # Parse into datetime objects for easy checking
    parsed_events = {}
    for participant_id, event_list in events_by_participant.items():
        parsed_events[participant_id] = []
        for event in event_list:
            start_str = event.get("start", "")
            end_str = event.get("end", "")
            if start_str and end_str:
                try:
                    start_dt = parser.parse(start_str)
                    end_dt = parser.parse(end_str)
                    parsed_events[participant_id].append({
                        "id": event.get("id", ""),
                        "title": event.get("title", ""),
                        "start": start_dt,
                        "end": end_dt
                    })
                except:
                    pass
    
    return parsed_events


def check_slot_against_events(slot_indexer, slot, duration_slots, participants, parsed_events):
    """Check if a slot is actually free for all participants"""
    slot_dt = slot_indexer.slot_to_datetime(slot)
    meeting_end_dt = slot_indexer.slot_to_datetime(slot + duration_slots)
    
    conflicts = []
    for participant_id in participants:
        participant_events = parsed_events.get(participant_id, [])
        for event in participant_events:
            # Check for overlap: meeting_start < event_end AND meeting_end > event_start
            if slot_dt < event["end"] and meeting_end_dt > event["start"]:
                conflicts.append({
                    "participant": participant_id,
                    "event": event["title"],
                    "event_start": event["start"],
                    "event_end": event["end"],
                    "meeting_start": slot_dt,
                    "meeting_end": meeting_end_dt
                })
    
    return conflicts


def verify_all_free_slots():
    """Verify all reported free slots are actually free"""
    print("="*80)
    print("FREE SLOTS VERIFICATION")
    print("="*80)
    
    events = load_events_from_example(Path(__file__).parent / "example_event_data.md")
    parsed_events = load_events_raw()
    
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
    
    # Get free slots as calculated by the system
    all_slots = list(range(slot_indexer.total_slots))
    free_slots = _find_free_slots(
        all_slots, busy_slots, work_hours_slots,
        participants, duration_slots, min_gap_slots=0
    )
    
    print(f"\nSystem reports {len(free_slots)} free slots")
    print(f"\nVerifying each slot against actual event data...")
    print()
    
    et = pytz.timezone("America/New_York")
    verified_free = []
    conflicts_found = []
    
    for slot in sorted(free_slots):
        slot_dt = slot_indexer.slot_to_datetime(slot)
        et_dt = slot_dt.astimezone(et)
        
        # Check against actual events
        conflicts = check_slot_against_events(
            slot_indexer, slot, duration_slots, participants, parsed_events
        )
        
        if conflicts:
            conflicts_found.append({
                "slot": slot,
                "datetime": et_dt,
                "conflicts": conflicts
            })
        else:
            verified_free.append(slot)
    
    print(f"✓ Verified free slots: {len(verified_free)}")
    print(f"✗ Conflicts found: {len(conflicts_found)}")
    
    if conflicts_found:
        print(f"\n" + "="*80)
        print("CONFLICTS FOUND - These slots are NOT actually free!")
        print("="*80)
        for item in conflicts_found[:10]:  # Show first 10 conflicts
            et_dt = item["datetime"]
            print(f"\nSlot {item['slot']}: {et_dt.strftime('%A, %B %d at %I:%M %p %Z')}")
            for conflict in item["conflicts"]:
                print(f"  ✗ CONFLICT with {conflict['participant']}:")
                print(f"      Event: {conflict['event']}")
                print(f"      Event time: {conflict['event_start'].strftime('%I:%M %p')} - {conflict['event_end'].strftime('%I:%M %p')}")
                print(f"      Meeting would be: {conflict['meeting_start'].strftime('%I:%M %p')} - {conflict['meeting_end'].strftime('%I:%M %p')}")
    
    # Check the specific Dec 1 2:30 PM slot
    print(f"\n" + "="*80)
    print("SPECIFIC CHECK: December 1 at 2:30 PM Eastern")
    print("="*80)
    
    target_dt_et = et.localize(datetime(2025, 12, 1, 14, 30))  # 2:30 PM
    target_dt_utc = target_dt_et.astimezone(pytz.UTC)
    
    # Find the slot for this time
    # Find the slot by iterating through slots
    target_slot = None
    for slot in range(slot_indexer.total_slots):
        slot_dt = slot_indexer.slot_to_datetime(slot)
        if abs((slot_dt - target_dt_utc).total_seconds()) < 60:  # Within 1 minute
            target_slot = slot
            break
    
    try:
        if target_slot is None:
            print(f"Could not find slot for {target_dt_et}")
            return
        print(f"Target slot: {target_slot}")
        print(f"Target time: {target_dt_et.strftime('%A, %B %d at %I:%M %p %Z')}")
        
        # Check if it's in free_slots
        print(f"In free_slots: {target_slot in free_slots}")
        
        # Check busy slots for each participant
        print(f"\nBusy slots check:")
        for p in participants:
            busy = busy_slots.get(p, set())
            meeting_slots = range(target_slot, target_slot + duration_slots)
            overlaps = [s for s in meeting_slots if s in busy]
            print(f"  {p}:")
            print(f"    Meeting slots: {list(meeting_slots)}")
            print(f"    Overlaps with busy slots: {overlaps}")
            if overlaps:
                print(f"    ✗ CONFLICT!")
        
        # Check against actual events
        conflicts = check_slot_against_events(
            slot_indexer, target_slot, duration_slots, participants, parsed_events
        )
        
        if conflicts:
            print(f"\n✗ CONFLICTS FOUND with actual events:")
            for conflict in conflicts:
                print(f"  {conflict['participant']}:")
                print(f"    Event: {conflict['event']}")
                print(f"    Event: {conflict['event_start'].strftime('%a %b %d %I:%M %p')} - {conflict['event_end'].strftime('%I:%M %p')}")
                print(f"    Meeting: {conflict['meeting_start'].strftime('%a %b %d %I:%M %p')} - {conflict['meeting_end'].strftime('%I:%M %p')}")
        else:
            print(f"\n✓ No conflicts with actual events")
            
    except Exception as e:
        print(f"Error finding target slot: {e}")
        import traceback
        traceback.print_exc()
    
    # Summary
    print(f"\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"System reports: {len(free_slots)} free slots")
    print(f"Verified free: {len(verified_free)} slots")
    print(f"False positives: {len(conflicts_found)} slots")
    
    if len(conflicts_found) > 0:
        print(f"\n⚠ PROBLEM: {len(conflicts_found)} slots are incorrectly marked as free!")
        print(f"This suggests a bug in the busy slot calculation or normalization.")
    else:
        print(f"\n✓ All reported free slots are actually free!")


if __name__ == "__main__":
    verify_all_free_slots()

