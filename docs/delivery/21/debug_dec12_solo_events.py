#!/usr/bin/env python3
"""
Debug script to check why Dec 12 1:00-2:15 PM slots are being reported as free
when they conflict with solo events.
"""

import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import after adding to path
from letta.scheduling_orchestrator.normalizer import normalize_events
from letta.scheduling_orchestrator.python_solver import find_top_candidates
from letta.scheduling_orchestrator.schemas import SchedulingProblem
from letta.scheduling_orchestrator.fact_generator import _find_free_slots
from letta.scheduling_orchestrator.python_solver import find_top_candidates
from letta.scheduling_orchestrator.schemas import SchedulingProblem
from datetime import datetime
import pytz

# Load events
events_by_participant = {}
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

# Load from example_event_data_v2.md
script_dir = Path(__file__).parent
with open(script_dir / "example_event_data_v2.md", "r") as f:
    content = f.read()

# Use the same loading function as the test script
def load_events_from_example_v2(file_path: Path):
    """Load events from example_event_data_v2.md format."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    events_by_participant = {}
    
    # Extract each participant's events
    participants = ["cdorsey@concord.org", "dkehoe@concord.org", "sbrau@concord.org"]
    for i, participant_id in enumerate(participants):
        if participant_id not in content:
            continue
        
        # Find this participant's section
        start_marker = f"{participant_id} events:"
        if start_marker not in content:
            continue
        
        section = content.split(start_marker)[1]
        
        # Find the next participant's marker or end of content
        next_marker_idx = len(section)
        for next_participant in participants[i+1:]:
            next_marker = f"\n{next_participant} events:"
            if next_marker in section:
                next_marker_idx = section.find(next_marker)
                break
        
        section = section[:next_marker_idx]
        
        # Extract JSON array
        lines = section.strip().split('\n')
        json_lines = []
        in_json = False
        for line in lines:
            if line.strip().startswith('['):
                in_json = True
                json_lines.append(line)
            elif in_json:
                json_lines.append(line)
                if line.strip().endswith(']'):
                    break
        
        if json_lines:
            try:
                events_json = json.loads('\n'.join(json_lines))
                # Flatten start/end objects to strings for normalizer
                flattened_events = []
                for event in events_json:
                    flattened = event.copy()
                    if isinstance(event.get("start"), dict):
                        flattened["start"] = event["start"].get("dateTime", "")
                    if isinstance(event.get("end"), dict):
                        flattened["end"] = event["end"].get("dateTime", "")
                    flattened_events.append(flattened)
                events_by_participant[participant_id] = flattened_events
            except json.JSONDecodeError as e:
                print(f"Error parsing {participant_id} events: {e}")
    
    return events_by_participant

# Load events properly
events_by_participant = load_events_from_example_v2(script_dir / "example_event_data_v2.md")
print(f"Loaded {len(events_by_participant.get('cdorsey@concord.org', []))} events for Chad")
print(f"Loaded {len(events_by_participant.get('dkehoe@concord.org', []))} events for Danielle")

# Check raw events first
print(f"\nChecking raw events for 'Chalk' or 'podcast':")
chad_events = events_by_participant.get("cdorsey@concord.org", [])
for event in chad_events:
    summary = event.get("summary", "")
    if "chalk" in summary.lower() or "podcast" in summary.lower() or "12-12" in event.get("start", ""):
        print(f"  Found: {summary}")
        print(f"    Start: {event.get('start', 'N/A')}")
        print(f"    End: {event.get('end', 'N/A')}")
        print(f"    Attendees: {event.get('number_of_attendees', 'N/A')}")
        print()

# Normalize events
print(f"\nNormalizing events...")
normalized_data = normalize_events(events_by_participant, context_json)
slot_indexer = normalized_data["slot_indexer"]
busy_slots = normalized_data["busy_slots"]
event_metadata = normalized_data["event_metadata"]
event_slots_map = normalized_data["event_slots_map"]

print(f"Total events in event_slots_map for Chad: {len([k for k in event_slots_map.keys() if k[0] == 'cdorsey@concord.org'])}")

# Check Dec 12 1:00 PM - 2:15 PM (45-minute meetings)
# Convert to UTC slots
target_start = datetime(2025, 12, 12, 13, 0, 0)
tz_eastern = pytz.timezone("America/New_York")
target_start = tz_eastern.localize(target_start)
target_start_utc = target_start.astimezone(pytz.UTC)
target_slot = slot_indexer.datetime_to_slot(target_start_utc)

print(f"\nDec 12 1:00 PM EST = {target_start} EST = {target_start_utc} UTC = slot {target_slot}")

# Also check what slot the event actually occupies
print(f"\nChecking all events on Dec 12:")
for (p_id, e_id), slots in event_slots_map.items():
    if p_id == "cdorsey@concord.org":
        event_meta = event_metadata.get((p_id, e_id), {})
        start_dt = event_meta.get("start_dt")
        if start_dt and start_dt.astimezone(tz_eastern).date() == datetime(2025, 12, 12).date():
            est_dt = start_dt.astimezone(tz_eastern)
            title = event_meta.get("title", "Unknown")
            print(f"  Event: {title}")
            print(f"    Start: {est_dt.strftime('%Y-%m-%d %I:%M %p %Z')}")
            print(f"    Slots: {min(slots)} to {max(slots)}")
            print(f"    Attendees: {event_meta.get('number_of_attendees', 'unknown')}")
            if "1:00" in est_dt.strftime('%I:%M %p') or "13:00" in str(est_dt):
                print(f"    *** THIS IS THE 1:00 PM EVENT ***")
            print()

# Check Chad's busy slots around this time
chad_busy = busy_slots.get("cdorsey@concord.org", set())
danielle_busy = busy_slots.get("dkehoe@concord.org", set())

print(f"\nChad's busy slots around slot {target_slot}:")
for slot in range(target_slot - 5, target_slot + 10):
    if slot in chad_busy:
        slot_dt = slot_indexer.slot_to_datetime(slot)
        print(f"  Slot {slot}: {slot_dt} (busy)")

# Check which events are at these slots
print(f"\nEvents on Chad's calendar at Dec 12 1:00 PM:")
for (p_id, e_id), slots in event_slots_map.items():
    if p_id == "cdorsey@concord.org" and target_slot in slots:
        event_meta = event_metadata.get((p_id, e_id), {})
        print(f"  Event: {event_meta.get('title', 'Unknown')}")
        print(f"    Event ID: {e_id}")
        print(f"    Slots: {min(slots)} to {max(slots)}")
        print(f"    Attendees: {event_meta.get('number_of_attendees', 'unknown')}")
        print(f"    Locked: {event_meta.get('locked', False)}")
        print(f"    Protected: {event_meta.get('protected', False)}")
        print(f"    Flexible: {event_meta.get('flexible', True)}")
        print()

# Check if 1:00 PM slot would be "free" according to _find_free_slots
duration_slots = 3  # 45 minutes = 3 slots
all_slots = list(range(slot_indexer.total_slots))
work_hours_slots = normalized_data["work_hours_slots"]
min_gap_slots = normalized_data.get("min_gap_slots", 0)

free_slots = _find_free_slots(
    all_slots,
    busy_slots,
    work_hours_slots,
    ["cdorsey@concord.org", "dkehoe@concord.org"],
    duration_slots,
    min_gap_slots
)

print(f"\nFree slots around Dec 12 1:00 PM:")
for slot in range(target_slot - 5, target_slot + 10):
    if slot in free_slots:
        slot_dt = slot_indexer.slot_to_datetime(slot)
        if slot_dt:
            est_dt = slot_dt.astimezone(pytz.timezone("America/New_York"))
            print(f"  Slot {slot}: {est_dt.strftime('%Y-%m-%d %I:%M %p %Z')} (FREE)")

# Check what find_top_candidates returns
scheduling_problem = SchedulingProblem(
    participants=["cdorsey@concord.org", "dkehoe@concord.org"],
    duration_minutes=45,
    time_window_start="2025-12-10T00:00:00-05:00",
    time_window_end="2025-12-19T23:59:59-05:00"
)

candidates = find_top_candidates(
    normalized_data,
    scheduling_problem,
    slot_indexer,
    context_json,
    max_candidates=2000
)

print(f"\n\nCandidates returned by find_top_candidates for Dec 12 1:00 PM area:")
for cand in candidates:
    if cand["start_slot"] in range(target_slot - 5, target_slot + 10):
        slot_dt = slot_indexer.slot_to_datetime(cand["start_slot"])
        if slot_dt:
            est_dt = slot_dt.astimezone(pytz.timezone("America/New_York"))
            method = cand.get("method", "unknown")
            moved_count = len(cand.get("moved_events", []))
            print(f"  Slot {cand['start_slot']}: {est_dt.strftime('%Y-%m-%d %I:%M %p %Z')}")
            print(f"    Method: {method}")
            print(f"    Moved events: {moved_count}")
            print(f"    Score: {cand.get('score', 'N/A')}")
            if "override_events" in cand:
                print(f"    Override events: {cand['override_events']}")
            print()

