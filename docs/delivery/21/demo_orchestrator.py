#!/usr/bin/env python3
"""
Demo script to show how the orchestrator processes a specific utterance
and returns results.
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

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


def load_events_from_example(example_file: Path) -> dict:
    """Load events from example_event_data.md"""
    events_by_participant = {}
    
    if not example_file.exists():
        print(f"Error: Example file not found: {example_file}")
        return {}
    
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
        
        if bracket_count != 0:
            events_by_participant[participant] = []
            continue
        
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
                
                title = event.get("title") or event.get("summary", "")
                
                normalized = {
                    "id": event.get("id", ""),
                    "title": title,
                    "start": start_str,
                    "end": end_str,
                    "locked": event.get("locked", False),
                    "protected": event.get("protected", False),
                    "flexible": event.get("flexible", True)
                }
                normalized_events.append(normalized)
            
            events_by_participant[participant] = normalized_events
        except json.JSONDecodeError:
            events_by_participant[participant] = []
    
    return events_by_participant


def format_datetime(dt_str: str) -> str:
    """Format ISO datetime string to readable format"""
    try:
        from dateutil import parser
        dt = parser.parse(dt_str)
        return dt.strftime("%A, %B %d, %Y at %I:%M %p %Z")
    except:
        return dt_str


def main():
    print("="*80)
    print("SCHEDULING ORCHESTRATOR DEMO")
    print("="*80)
    print()
    
    # Load events
    example_file = Path(__file__).parent / "example_event_data.md"
    print(f"Loading events from: {example_file.name}")
    events = load_events_from_example(example_file)
    
    total_events = sum(len(evts) for evts in events.values())
    print(f"Loaded {total_events} total events:")
    for participant, event_list in events.items():
        name = participant.split('@')[0]
        print(f"  {name}: {len(event_list)} events")
    print()
    
    # Prepare utterance and context
    utterance = "Find me possible 45-minute meeting slots with Sue and Danielle between Dec. 1 and 12."
    
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
                # No work_hours - will default to 9-5 Eastern
            },
            {
                "id": "sbrau@concord.org",
                "email": "sbrau@concord.org",
                "name": "Sue"
                # No work_hours - will default to 9-5 Eastern
            },
            {
                "id": "dkehoe@concord.org",
                "email": "dkehoe@concord.org",
                "name": "Danielle"
                # No work_hours - will default to 9-5 Eastern
            }
        ],
        "policy": {
            "hard": {
                "min_gap_min": 0
            }
        }
    }
    
    print("="*80)
    print("INPUT")
    print("="*80)
    print(f"Utterance: {utterance}")
    print()
    print("Context:")
    print(f"  Timeframe: {context_json['timeframe']['from']} to {context_json['timeframe']['to']}")
    print(f"  Timezone: {context_json['timeframe']['tz']}")
    print(f"  Requester: {context_json['requester_id']}")
    print(f"  Participants: {', '.join([p['name'] for p in context_json['participants']])}")
    print()
    
    print("="*80)
    print("PROCESSING...")
    print("="*80)
    print("(This may take a few seconds for DSPy extraction...)")
    print()
    
    # Convert to JSON strings for the tool
    events_json_str = json.dumps(events)
    context_json_str = json.dumps(context_json)
    
    # Call orchestrator
    try:
        result = orchestrate_scheduling(
            utterance=utterance,
            events_by_participant=events_json_str,
            context_json=context_json_str
        )
        
        # Display results
        print()
        print("="*80)
        print("RESULTS")
        print("="*80)
        print()
        
        # Status
        status = result.get("status", "unknown")
        status_emoji = "✓" if status == "ok" else "⚠" if status == "unsat" else "✗"
        print(f"Status: {status_emoji} {status.upper()}")
        print()
        
        if status == "ok":
            proposals = result.get("proposals", [])
            print(f"Found {len(proposals)} proposal(s):")
            print()
            
            for i, proposal in enumerate(proposals, 1):
                print(f"{'─'*78}")
                print(f"Proposal {i}:")
                print(f"{'─'*78}")
                
                # Title
                title = proposal.get("title", "Meeting")
                print(f"  Title: {title}")
                
                # Time
                start_utc = proposal.get("start_utc")
                end_utc = proposal.get("end_utc")
                print(f"  Start: {format_datetime(start_utc)}")
                print(f"  End:   {format_datetime(end_utc)}")
                
                # Participants
                participants = proposal.get("participants", [])
                participant_names = []
                for p_email in participants:
                    # Find name from context
                    name = p_email.split('@')[0]
                    for p in context_json["participants"]:
                        if p["id"] == p_email:
                            name = p.get("name", name)
                            break
                    participant_names.append(name)
                print(f"  Participants: {', '.join(participant_names)} ({', '.join(participants)})")
                
        # Location
        location = proposal.get("location")
        if location:
            print(f"  Location: {location}")
        
        # Verify work hours
        from dateutil import parser
        from dateutil import tz
        start_dt = parser.parse(start_utc)
        et = tz.gettz("America/New_York")
        et_dt = start_dt.astimezone(et)
        is_weekday = et_dt.weekday() < 5
        is_9_to_5 = 9 <= et_dt.hour < 17 or (et_dt.hour == 17 and et_dt.minute == 0)
        if is_weekday and is_9_to_5:
            print(f"  ✓ Within 9-5 Eastern work hours")
        else:
            print(f"  ⚠ Outside 9-5 Eastern work hours (Day: {et_dt.strftime('%A')}, Time: {et_dt.strftime('%I:%M %p %Z')})")
                
                # Moved events
                moved_events = proposal.get("moved_events", [])
                if moved_events:
                    print(f"  Moved Events: {len(moved_events)}")
                    for moved in moved_events[:3]:  # Show first 3
                        print(f"    - {moved.get('title', 'Event')}: {moved.get('original_start')} → {moved.get('new_start')}")
                    if len(moved_events) > 3:
                        print(f"    ... and {len(moved_events) - 3} more")
                else:
                    print(f"  Moved Events: None (free slot)")
                
                # Objective scores
                scores = proposal.get("objective_scores", {})
                if scores:
                    print(f"  Optimization Scores:")
                    if scores.get("moved_minutes"):
                        print(f"    - Moved minutes: {scores.get('moved_minutes')}")
                    if scores.get("focus_block_bonus"):
                        print(f"    - Focus block bonus: {scores.get('focus_block_bonus')}")
                    if scores.get("preference_penalty"):
                        print(f"    - Preference penalty: {scores.get('preference_penalty')}")
                
                print()
            
            # Explanation
            explanation = result.get("explanation", "")
            if explanation:
                print(f"{'─'*78}")
                print("Explanation:")
                print(f"  {explanation}")
                print()
        
        elif status == "unsat":
            print("No feasible solution found with current constraints.")
            print()
            
            relaxations = result.get("relaxations", [])
            if relaxations:
                print(f"Suggested Relaxations ({len(relaxations)}):")
                for i, relax in enumerate(relaxations, 1):
                    print(f"  {i}. {relax.get('description', 'Unknown relaxation')}")
                print()
            
            explanation = result.get("explanation", "")
            if explanation:
                print("Explanation:")
                print(f"  {explanation}")
                print()
        
        else:  # bad_input
            error_msg = result.get("error_message", "Unknown error")
            print(f"Error: {error_msg}")
            print()
        
        # Debug info
        debug = result.get("debug", {})
        if debug:
            print(f"{'─'*78}")
            print("Debug Information:")
            if debug.get("extraction_time_ms"):
                print(f"  DSPy Extraction Time: {debug.get('extraction_time_ms')}ms")
            if debug.get("normalization_time_ms"):
                print(f"  Event Normalization Time: {debug.get('normalization_time_ms')}ms")
            if debug.get("solve_time_ms"):
                print(f"  Solver Time: {debug.get('solve_time_ms')}ms")
            if debug.get("total_time_ms"):
                print(f"  Total Time: {debug.get('total_time_ms')}ms")
            
            input_summary = debug.get("input_summary", {})
            if input_summary:
                print(f"  Input Summary:")
                print(f"    - Total events: {input_summary.get('total_events', 0)}")
                print(f"    - Participants: {input_summary.get('num_participants', 0)}")
                print(f"    - Events per participant: {input_summary.get('events_per_participant', {})}")
            
            if debug.get("free_slots_found"):
                print(f"  Free Slots Found: {debug.get('free_slots_found')}")
            if debug.get("slots_considered"):
                print(f"  Slots Considered: {debug.get('slots_considered')}")
            print()
        
        # Show raw JSON for reference
        print("="*80)
        print("RAW JSON OUTPUT")
        print("="*80)
        print(json.dumps(result, indent=2, default=str))
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

