#!/usr/bin/env python3
"""
Debug script to check why Dec 15 3:30 PM slot is being proposed when it conflicts with locked "Chad out" event
"""

import sys
import json
from pathlib import Path
from datetime import datetime
import pytz

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from letta.scheduling_orchestrator.normalizer import normalize_events
from letta.scheduling_orchestrator.python_solver import find_top_candidates
from letta.scheduling_orchestrator.schemas import SchedulingProblem

# Load events using the same method as test script
def load_events_from_example_v2(file_path: Path):
    """Load events from example_event_data_v2.md format."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    events_by_participant = {}
    participants = ['cdorsey@concord.org', 'dkehoe@concord.org']
    
    for participant in participants:
        marker = f'{participant} events:'
        idx = content.find(marker)
        if idx == -1:
            events_by_participant[participant] = []
            continue
        
        json_start = content.find('[', idx)
        if json_start == -1:
            events_by_participant[participant] = []
            continue
        
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
                start_val = event.get('start', '')
                if isinstance(start_val, dict):
                    start_str = start_val.get('dateTime', '')
                else:
                    start_str = str(start_val) if start_val else ''
                
                end_val = event.get('end', '')
                if isinstance(end_val, dict):
                    end_str = end_val.get('dateTime', '')
                else:
                    end_str = str(end_val) if end_val else ''
                
                normalized_events.append({
                    'id': event.get('id', ''),
                    'summary': event.get('summary', '') or event.get('title', ''),
                    'start': start_str,
                    'end': end_str,
                    'locked': event.get('locked', False),
                    'protected': event.get('protected', False),
                    'flexible': event.get('flexible', True),
                    'number_of_attendees': event.get('number_of_attendees', 0),
                    'internal_only': event.get('internal_only', True)
                })
            events_by_participant[participant] = normalized_events
        except json.JSONDecodeError as e:
            print(f"Error parsing {participant} events: {e}", file=sys.stderr)
            events_by_participant[participant] = []
    
    return events_by_participant

# Load events
script_dir = Path(__file__).parent
events_by_participant = load_events_from_example_v2(script_dir / "example_event_data_v2.md")

context_json = {
    "participants": [
        {"id": "cdorsey@concord.org", "email": "cdorsey@concord.org"},
        {"id": "dkehoe@concord.org", "email": "dkehoe@concord.org"}
    ],
    "timeframe": {
        "from": "2025-12-10T00:00:00-05:00",
        "to": "2025-12-19T23:59:59-05:00",
        "tz": "America/New_York"
    }
}

# Check for "Chad out" event on Dec 15
print("Checking for 'Chad out' event on Dec 15:")
chad_events = events_by_participant.get("cdorsey@concord.org", [])
for event in chad_events:
    summary = event.get("summary", "")
    start_str = event.get("start", "")
    if "chad out" in summary.lower() and "2025-12-15" in start_str:
        print(f"  Found: {summary}")
        print(f"    Start: {start_str}")
        print(f"    End: {event.get('end', '')}")
        print(f"    Locked: {event.get('locked', False)}")
        print(f"    Protected: {event.get('protected', False)}")
        print(f"    Flexible: {event.get('flexible', True)}")
        print()

# Normalize events
normalized_data = normalize_events(events_by_participant, context_json)
slot_indexer = normalized_data["slot_indexer"]
busy_slots = normalized_data["busy_slots"]
event_metadata = normalized_data["event_metadata"]
event_slots_map = normalized_data["event_slots_map"]
event_protection = normalized_data["event_protection"]

# Check Dec 15 3:30 PM slot
target_start = datetime(2025, 12, 15, 15, 30, 0)
tz_eastern = pytz.timezone("America/New_York")
target_start = tz_eastern.localize(target_start)
target_start_utc = target_start.astimezone(pytz.UTC)
target_slot = slot_indexer.datetime_to_slot(target_start_utc)

print(f"\nDec 15 3:30 PM EST = {target_start} EST = {target_start_utc} UTC = slot {target_slot}")

# Check conflicts for a 45-minute meeting (3 slots)
duration_slots = 3
meeting_slots = range(target_slot, target_slot + duration_slots)

print(f"\nMeeting slots: {target_slot} to {target_slot + duration_slots - 1}")

# Check Chad's busy slots
chad_busy = busy_slots.get("cdorsey@concord.org", set())
print(f"\nChad's busy slots in this range:")
for slot in meeting_slots:
    if slot in chad_busy:
        slot_dt = slot_indexer.slot_to_datetime(slot)
        if slot_dt:
            est_dt = slot_dt.astimezone(tz_eastern)
            print(f"  Slot {slot}: {est_dt.strftime('%Y-%m-%d %I:%M %p %Z')} (busy)")
            
            # Find which events are at this slot
            for (p_id, e_id), slots in event_slots_map.items():
                if p_id == "cdorsey@concord.org" and slot in slots:
                    event_meta = event_metadata.get((p_id, e_id), {})
                    protection = event_protection.get((p_id, e_id), "flexible")
                    print(f"    Event: {event_meta.get('title', 'Unknown')}")
                    print(f"      Protection level: {protection}")
                    print(f"      Locked: {event_meta.get('locked', False)}")
                    print(f"      Protected: {event_meta.get('protected', False)}")
                    print(f"      Flexible: {event_meta.get('flexible', True)}")

# Check locked events
print(f"\nChecking locked events for Chad:")
locked_events_dict = {}
for (p_id, e_id), protection in event_protection.items():
    if p_id == "cdorsey@concord.org" and protection == "locked":
        event_meta = event_metadata.get((p_id, e_id), {})
        event_slots = event_slots_map.get((p_id, e_id), set())
        if event_slots:
            start_slot = min(event_slots)
            start_dt = slot_indexer.slot_to_datetime(start_slot)
            if start_dt:
                est_dt = start_dt.astimezone(tz_eastern)
                if "2025-12-15" in est_dt.strftime('%Y-%m-%d'):
                    print(f"  Locked event: {event_meta.get('title', 'Unknown')}")
                    print(f"    Slots: {min(event_slots)} to {max(event_slots)}")
                    print(f"    Start: {est_dt.strftime('%Y-%m-%d %I:%M %p %Z')}")
                    if set(meeting_slots).intersection(event_slots):
                        print(f"    *** CONFLICTS with meeting slot {target_slot} ***")
                    locked_events_dict[(p_id, e_id)] = event_slots

print(f"\nChecking if 3:30 PM slot is in locked events:")
for (p_id, e_id), locked_slots in locked_events_dict.items():
    if set(meeting_slots).intersection(locked_slots):
        event_meta = event_metadata.get((p_id, e_id), {})
        print(f"  YES - conflicts with locked event: {event_meta.get('title', 'Unknown')}")

