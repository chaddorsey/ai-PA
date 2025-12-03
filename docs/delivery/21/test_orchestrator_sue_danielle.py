#!/usr/bin/env python3
"""
Test script for orchestrator with Sue and Danielle meeting request.

This script tests the scheduling orchestrator with real calendar data to find
a 45-minute meeting slot between Chad, Sue, and Danielle from Dec 1-12, 2025.
"""

import json
import sys
import os
from pathlib import Path

# Load .env file if it exists (before any imports that might use environment variables)
project_root = Path(__file__).parent.parent.parent.parent
env_path = project_root / '.env'
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
        print(f"Loaded environment variables from {env_path}")
    except ImportError:
        print("Warning: python-dotenv not installed, .env file not loaded")
    except Exception as e:
        print(f"Warning: Error loading .env file: {e}")

# Add project root and letta directory to path so we can import the orchestrator
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "letta"))

# Check for API keys after loading .env
openai_key = os.getenv("OPENAI_API_KEY")
anthropic_key = os.getenv("ANTHROPIC_API_KEY")

if not openai_key and not anthropic_key:
    print("WARNING: No API keys found (OPENAI_API_KEY or ANTHROPIC_API_KEY)")
    print("DSPy extraction may fail. The orchestrator will use fallback extraction.")
    print()
else:
    if openai_key:
        print(f"Found OPENAI_API_KEY (length: {len(openai_key)})")
    if anthropic_key:
        print(f"Found ANTHROPIC_API_KEY (length: {len(anthropic_key)})")
    print()
sys.stdout.flush()

from scheduling_orchestrator.orchestrate_scheduling import orchestrate_scheduling


def main():
    # Test parameters
    utterance = "Provide me options for a 45-minute meeting with Sue and Danielle between December 1 and December 12."
    
    # Load events data from the example file
    example_file = Path(__file__).parent / "example_event_data.md"
    events_by_participant = load_events_from_example(example_file)
    
    # Context with timeframe and participant info
    context_json = {
        "timeframe": {
            "from": "2025-12-01",
            "to": "2025-12-12",
            "tz": "America/New_York"
        },
        "participants": [
            {
                "id": "cdorsey@concord.org",
                "email": "cdorsey@concord.org",
                "name": "Chad"
                # No work_hours specified - will default to M-F 09:00-17:00
            },
            {
                "id": "sbrau@concord.org",
                "email": "sbrau@concord.org",
                "name": "Sue"
                # No work_hours specified - will default to M-F 09:00-17:00
            },
            {
                "id": "dkehoe@concord.org",
                "email": "dkehoe@concord.org",
                "name": "Danielle"
                # No work_hours specified - will default to M-F 09:00-17:00
            }
        ],
        "policy": {
            "hard": {
                "min_gap_min": 0
            },
            "soft": {
                "maximize_focus_blocks": {
                    "block_min": 90,
                    "weight": 10
                },
                "minimize_moves_of_existing": {
                    "weight_per_min_shift": 2,
                    "tier": "protected"
                },
                "respect_others_prefs_weight": 3
            },
            "lexicographic_levels": [
                "feasibility",
                "protected_events",
                "move_costs",
                "focus_blocks"
            ]
        },
        "slot_size_minutes": 15
    }
    
    print("=" * 80)
    print("Testing Scheduling Orchestrator")
    print("=" * 80)
    print(f"\nUtterance: {utterance}")
    print(f"\nParticipants: cdorsey@concord.org, sbrau@concord.org, dkehoe@concord.org")
    print(f"Timeframe: Dec 1-12, 2025")
    print(f"Duration: 45 minutes")
    print(f"Min gap: 0 minutes (adjusted per request)")
    print("\n" + "-" * 80)
    print("Loading events...")
    sys.stdout.flush()
    
    # Convert events to JSON string format expected by orchestrator
    events_json_str = json.dumps(events_by_participant)
    context_json_str = json.dumps(context_json)
    
    total_events = sum(len(events) for events in events_by_participant.values())
    print(f"Loaded {total_events} total events")
    for pid, events in events_by_participant.items():
        print(f"  {pid}: {len(events)} events")
    print("\nRunning orchestrator (this may take a moment for DSPy extraction)...")
    print("-" * 80 + "\n")
    sys.stdout.flush()
    
    # Call orchestrator
    try:
        result = orchestrate_scheduling(
            utterance=utterance,
            events_by_participant=events_json_str,
            context_json=context_json_str
        )
    except Exception as e:
        print(f"\nERROR: Orchestrator call failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error_message": str(e)}
    
    # Print results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"\nStatus: {result.get('status', 'unknown')}")
    
    # Check if there was an error
    if result.get('status') == 'error':
        print(f"\nError occurred: {result.get('error_message', 'Unknown error')}")
        return result
    
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
                print(f"  Moved Events: {len(moved_events)}")
                for me in moved_events:
                    print(f"    - {me.get('event_id', 'unknown')}: {me.get('shift_minutes', 0)} min shift")
            else:
                print(f"  Moved Events: None (free slot)")
            print()
        
        if 'explanation' in result:
            print(f"Explanation:\n{result['explanation']}\n")
    
    elif result.get('status') == 'unsat':
        print("\nNo feasible solution found.")
        relaxations = result.get('relaxations', [])
        if relaxations:
            print(f"\nSuggested relaxations ({len(relaxations)}):")
            for i, rel in enumerate(relaxations, 1):
                print(f"  {i}. {rel.get('description', 'N/A')}")
        if 'explanation' in result:
            print(f"\nExplanation:\n{result['explanation']}")
    
    elif result.get('status') == 'bad_input':
        error_msg = result.get('error_message', 'Unknown error')
        print(f"\nBad input: {error_msg}")
    
    # Print debug info
    if 'debug' in result:
        debug = result['debug']
        print("\n" + "-" * 80)
        print("DEBUG INFO")
        print("-" * 80)
        for key, value in debug.items():
            if hasattr(value, '__dict__'):
                print(f"{key}:")
                for k, v in value.__dict__.items():
                    print(f"  {k}: {v}")
            else:
                print(f"{key}: {value}")
    
    # Save results to file
    output_file = Path(__file__).parent / "test_output_sue_danielle.json"
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nFull results saved to: {output_file}")
    
    return result


def load_events_from_example(example_file: Path) -> dict:
    """
    Parse events from the example_event_data.md file.
    
    The file has sections like:
    Event data for cdorsey@concord.org:
    [ ... JSON array ... ]
    
    Event data for sbrau@concord.org:
    [ ... JSON array ... ]
    
    Event data for dkehoe@concord.org:
    [ ... JSON array ... ]
    """
    events_by_participant = {}
    
    print(f"Loading events from: {example_file}")
    print(f"File exists: {example_file.exists()}")
    if not example_file.exists():
        print(f"Warning: Example file not found: {example_file}")
        print("Using empty events.")
        return {
            "cdorsey@concord.org": [],
            "sbrau@concord.org": [],
            "dkehoe@concord.org": []
        }
    
    with open(example_file, 'r') as f:
        content = f.read()
    
    print(f"File content length: {len(content)} characters")
    sys.stdout.flush()
    
    # Find each participant's section
    participants = [
        "cdorsey@concord.org",
        "sbrau@concord.org",
        "dkehoe@concord.org"
    ]
    
    for participant in participants:
        # Find the section for this participant
        marker = f"Event data for {participant}:"
        idx = content.find(marker)
        
        if idx == -1:
            print(f"Warning: Marker '{marker}' not found in file for {participant}")
            events_by_participant[participant] = []
            continue
        
        print(f"Found marker for {participant} at position {idx}")
        sys.stdout.flush()
        
        # Find the start of the JSON array (skip past the marker and whitespace)
        json_start = content.find('[', idx)
        if json_start == -1:
            print(f"Warning: Could not find JSON array start for {participant}")
            events_by_participant[participant] = []
            continue
        
        # Find the end of the JSON array (find matching closing bracket)
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
            print(f"Warning: Unmatched brackets for {participant}")
            events_by_participant[participant] = []
            continue
        
        # Extract and parse JSON
        json_str = content[json_start:json_end]
        try:
            events = json.loads(json_str)
            # Convert event format from the example file to what orchestrator expects
            # The example has nested start/end with dateTime, but orchestrator expects
            # flat start/end fields. Also convert "summary" to "title" if needed.
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
                    "internal_only": event.get("internal_only", True),  # Include internal_only field
                    "number_of_attendees": event.get("number_of_attendees", 0)  # Include number_of_attendees field
                }
                normalized_events.append(normalized)
            
            events_by_participant[participant] = normalized_events
            print(f"Loaded {len(normalized_events)} events for {participant}")
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON for {participant}: {e}")
            events_by_participant[participant] = []
    
    return events_by_participant


if __name__ == "__main__":
    result = main()
    sys.exit(0 if result.get('status') == 'ok' else 1)

