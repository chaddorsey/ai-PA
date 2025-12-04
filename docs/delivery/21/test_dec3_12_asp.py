#!/usr/bin/env python3
"""
Test orchestrator with Dec 3-12 date range to trigger ASP fallback for multi-move scenarios.
"""

import json
import sys
from pathlib import Path

# Load .env
project_root = Path(__file__).parent.parent.parent.parent
env_path = project_root / '.env'
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

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
            continue
        
        json_start = content.find('[', idx)
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
            # Normalize event structure: extract dateTime from nested start/end objects
            normalized_events = []
            for event in events:
                # Extract dateTime from nested structure or use string directly
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
                
                # Use "title" if available, otherwise "summary", otherwise empty
                title = event.get("title") or event.get("summary", "")
                
                normalized = {
                    "id": event.get("id", ""),
                    "title": title,  # Orchestrator expects "title" field
                    "start": start_str,
                    "end": end_str,
                    "locked": event.get("locked", False),
                    "protected": event.get("protected", False),
                    "flexible": event.get("flexible", True),
                    "internal_only": event.get("internal_only", True),
                    "number_of_attendees": event.get("number_of_attendees", 0)
                }
                normalized_events.append(normalized)
            
            events_by_participant[participant] = normalized_events
        except json.JSONDecodeError as e:
            print(f"Warning: Unmatched brackets for {participant}")
            continue
    
    return events_by_participant


if __name__ == "__main__":
    print("="*80)
    print("TESTING DEC 3-12 - ASP FALLBACK FOR MULTI-MOVE SCENARIOS")
    print("="*80)
    print()
    
    # Load events
    example_file = Path(__file__).parent / "example_event_data.md"
    events_by_participant = load_events_from_example(example_file)
    
    print(f"Loaded events:")
    for participant, events in events_by_participant.items():
        print(f"  {participant}: {len(events)} events")
    print()
    
    # Create context for Dec 3-12
    context_json = {
        "timeframe": {
            "from": "2025-12-03",
            "to": "2025-12-12",
            "tz": "America/New_York"
        },
        "participants": [
            {"id": "cdorsey@concord.org", "email": "cdorsey@concord.org", "work_hours": "M-F 09:00-17:00"},
            {"id": "sbrau@concord.org", "email": "sbrau@concord.org", "work_hours": "M-F 09:00-17:00"},
            {"id": "dkehoe@concord.org", "email": "dkehoe@concord.org", "work_hours": "M-F 09:00-17:00"}
        ],
        "policy": {
            "hard": {"min_gap_min": 0},
            "soft": {}
        },
        "slot_size_minutes": 15
    }
    
    utterance = "Find me possible 45-minute meeting slots with Sue and Danielle between Dec. 3 and 12."
    
    events_json = json.dumps(events_by_participant)
    context_json_str = json.dumps(context_json)
    
    print(f"Utterance: {utterance}")
    print(f"Timeframe: Dec 3-12, 2025")
    print()
    print("Running orchestrator (this may take longer if ASP fallback is triggered)...")
    print("-" * 80)
    print()
    
    try:
        result = orchestrate_scheduling(utterance, events_json, context_json_str)
    except Exception as e:
        print(f"\nERROR: Orchestrator call failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Print results
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"\nStatus: {result.get('status', 'unknown')}")
    
    if result.get('status') == 'ok':
        proposals = result.get('proposals', [])
        print(f"\nFound {len(proposals)} proposal(s):\n")
        
        for i, proposal in enumerate(proposals, 1):
            print(f"Proposal {i}:")
            print(f"  Title: {proposal.get('title', 'Meeting')}")
            print(f"  Start: {proposal.get('start_utc', 'N/A')}")
            print(f"  End: {proposal.get('end_utc', 'N/A')}")
            print(f"  Participants: {', '.join(proposal.get('participants', []))}")
            
            moved_events = proposal.get('moved_events', [])
            if moved_events:
                print(f"  Moved Events: {len(moved_events)} event(s) need to be moved")
                for me in moved_events:
                    owner = me.get('owner', 'unknown')
                    event_id = me.get('event_id', 'unknown')
                    shift = me.get('shift_minutes', 0)
                    print(f"    - {owner}: {event_id} (shift {shift} minutes)")
            else:
                print(f"  Moved Events: None (free slot)")
            print()
        
        if 'explanation' in result:
            print(f"Explanation:\n{result['explanation']}\n")
    elif result.get('status') == 'unsat':
        print("\nNo solution found (UNSAT)")
        print(f"Explanation: {result.get('explanation', 'N/A')}")
        relaxations = result.get('relaxations', [])
        if relaxations:
            print(f"\nSuggestions ({len(relaxations)}):")
            for r in relaxations:
                print(f"  - {r.get('description', 'N/A')}")
        print()
    else:
        print(f"\nError: {result.get('error_message', 'Unknown error')}")
        print()
    
    # Debug info
    debug = result.get('debug', {})
    if debug:
        print("-" * 80)
        print("DEBUG INFO")
        print("-" * 80)
        print(f"Free slots found: {debug.get('free_slots_found', 'N/A')}")
        print(f"Solve time: {debug.get('solve_time_ms', 'N/A')} ms")
        
        asp_stats = debug.get('asp_stats')
        if asp_stats:
            print(f"ASP Stats:")
            print(f"  Models found: {asp_stats.get('models', 'N/A')}")
            print(f"  Optimum proven: {asp_stats.get('optimum', 'N/A')}")
            print(f"  Solve time: {asp_stats.get('solve_time_ms', 'N/A')} ms")
            print(f"  Ground time: {asp_stats.get('ground_time_ms', 'N/A')} ms")
            if asp_stats.get('error'):
                print(f"  Error: {asp_stats.get('error')}")
            if asp_stats.get('error_type'):
                print(f"  Error type: {asp_stats.get('error_type')}")
        else:
            print("ASP fallback: Not triggered (Python solver found solution)")
        
        if debug.get('horizon_reduced'):
            print(f"Horizon reduced: {debug.get('reduced_slots', 'N/A')} slots (from {debug.get('original_slots', 'N/A')})")
        if debug.get('horizon_reduction_error'):
            print(f"Horizon reduction error: {debug.get('horizon_reduction_error')}")
        print()

