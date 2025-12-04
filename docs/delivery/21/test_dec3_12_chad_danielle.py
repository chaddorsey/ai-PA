#!/usr/bin/env python3
"""
Test the orchestrator with Dec 3-12 date range for Chad and Danielle only
"""
import json
import sys
from pathlib import Path
from datetime import datetime
import pytz

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "letta"))

# Load .env file if it exists
env_path = project_root / '.env'
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        pass

from scheduling_orchestrator.orchestrate_scheduling import orchestrate_scheduling

def load_events_from_example(file_path: Path):
    """Load events from example_event_data.md format."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    events_by_participant = {}
    participants = ['cdorsey@concord.org', 'dkehoe@concord.org']
    
    for participant in participants:
        # Find the participant's section
        marker = f'Event data for {participant}:'
        idx = content.find(marker)
        if idx == -1:
            print(f"Warning: No events found for {participant}", file=sys.stderr)
            events_by_participant[participant] = []
            continue
        
        # Find the JSON array starting after the marker
        json_start = content.find('[', idx)
        if json_start == -1:
            print(f"Warning: No JSON array found for {participant}", file=sys.stderr)
            events_by_participant[participant] = []
            continue
        
        # Find the matching closing bracket
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
            # Normalize event structure (extract dateTime from nested objects)
            normalized_events = []
            for event in events:
                # Handle nested start/end objects
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
                    'internal_only': event.get('internal_only', True),
                    'number_of_attendees': event.get('number_of_attendees', 0)
                })
            events_by_participant[participant] = normalized_events
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON for {participant}: {e}", file=sys.stderr)
            events_by_participant[participant] = []
    
    return events_by_participant

def main():
    # Load event data
    example_file = Path(__file__).parent / 'example_event_data.md'
    if not example_file.exists():
        print(f"Error: {example_file} not found", file=sys.stderr)
        sys.exit(1)
    
    events_by_participant = load_events_from_example(example_file)
    
    # Print summary
    print("Loaded events:")
    for participant, events in events_by_participant.items():
        print(f"  {participant}: {len(events)} events")
    print()
    
    # Set up the scheduling request
    utterance = "Find me possible 45-minute meeting slots with Danielle between Dec. 3 and Dec. 12."
    
    # Create context JSON
    context_json = {
        'timeframe': {
            'from': '2025-12-03',
            'to': '2025-12-12',
            'tz': 'America/New_York'
        },
        'participants': [
            {
                'id': 'cdorsey@concord.org',
                'email': 'cdorsey@concord.org',
                'work_hours': 'M-F 09:00-17:00'
            },
            {
                'id': 'dkehoe@concord.org',
                'email': 'dkehoe@concord.org',
                'work_hours': 'M-F 09:00-17:00'
            }
        ],
        'policy': {
            'hard': {'min_gap_min': 0},
            'soft': {}
        },
        'slot_size_minutes': 15
    }
    
    print(f"Request: {utterance}")
    print(f"Date range: Dec 3-12, 2025")
    print(f"Participants: Chad and Danielle")
    print()
    
    # Convert events to JSON string format expected by orchestrate_scheduling
    events_json = json.dumps(events_by_participant)
    context_json_str = json.dumps(context_json)
    
    # Call the orchestrator
    try:
        result = orchestrate_scheduling(
            utterance=utterance,
            events_by_participant=events_json,
            context_json=context_json_str
        )
        
        # Print results
        if isinstance(result, dict):
            status = result.get('status', 'unknown')
            proposals = result.get('proposals', [])
            
            print(f"Status: {status}")
            print(f"Found {len(proposals)} proposal(s)")
            print()
            
            if proposals:
                for i, proposal in enumerate(proposals, 1):
                    print(f"Proposal {i}:")
                    start_str = proposal.get('start_utc', '') or proposal.get('start', '')
                    end_str = proposal.get('end_utc', '') or proposal.get('end', '')
                    
                    # Parse and format times
                    if start_str:
                        try:
                            start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                            if start_dt.tzinfo is None:
                                start_dt = pytz.UTC.localize(start_dt)
                            else:
                                start_dt = start_dt.astimezone(pytz.UTC)
                            et = start_dt.astimezone(pytz.timezone('America/New_York'))
                            print(f"  Start: {et.strftime('%A, %B %d, %Y at %I:%M %p %Z')}")
                        except Exception as e:
                            print(f"  Start: {start_str} (parse error: {e})")
                    
                    if end_str:
                        try:
                            end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                            if end_dt.tzinfo is None:
                                end_dt = pytz.UTC.localize(end_dt)
                            else:
                                end_dt = end_dt.astimezone(pytz.UTC)
                            et = end_dt.astimezone(pytz.timezone('America/New_York'))
                            print(f"  End: {et.strftime('%I:%M %p %Z')}")
                        except Exception as e:
                            print(f"  End: {end_str} (parse error: {e})")
                    
                    participants = proposal.get('participants', [])
                    if participants:
                        print(f"  Participants: {', '.join(participants)}")
                    
                    moved_events = proposal.get('moved_events', [])
                    if moved_events:
                        print(f"  Moved events: {len(moved_events)}")
                        for moved in moved_events:
                            event_id = moved.get('event_id', 'unknown')
                            owner = moved.get('owner', moved.get('participant_id', 'unknown'))
                            shift_minutes = moved.get('shift_minutes', moved.get('delta_minutes', 0))
                            old_start = moved.get('old_start', '')
                            new_start = moved.get('new_start', '')
                            print(f"    - {owner}: {event_id[:40]}... (shift {shift_minutes} min)")
                            if old_start and new_start:
                                try:
                                    old_dt = datetime.fromisoformat(old_start.replace('Z', '+00:00'))
                                    new_dt = datetime.fromisoformat(new_start.replace('Z', '+00:00'))
                                    if old_dt.tzinfo is None:
                                        old_dt = pytz.UTC.localize(old_dt)
                                    if new_dt.tzinfo is None:
                                        new_dt = pytz.UTC.localize(new_dt)
                                    old_et = old_dt.astimezone(pytz.timezone('America/New_York'))
                                    new_et = new_dt.astimezone(pytz.timezone('America/New_York'))
                                    actual_shift = int((new_dt - old_dt).total_seconds() / 60)
                                    if actual_shift != shift_minutes:
                                        print(f"      (calculated shift: {actual_shift} min from {old_et.strftime('%I:%M %p')} to {new_et.strftime('%I:%M %p')})")
                                except:
                                    pass
                    else:
                        print(f"  Moved events: None (free slot)")
                    print()
            else:
                print("No proposals found.")
                # Print debug info if available
                debug = result.get('debug', {})
                if debug:
                    print("\nDebug info:")
                    print(f"  Python solver stats: {debug.get('python_solver_stats', {})}")
                    asp_stats = debug.get('asp_stats', {})
                    if asp_stats:
                        print(f"  ASP solver stats: {asp_stats}")
        else:
            print(f"Unexpected result format: {type(result)}")
            print(result)
    
    except Exception as e:
        print(f"Error calling orchestrator: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Save results to file
    output_file = Path(__file__).parent / 'test_dec3_12_chad_danielle_results.json'
    try:
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nResults saved to: {output_file}")
    except Exception as e:
        print(f"Warning: Could not save results: {e}", file=sys.stderr)

if __name__ == '__main__':
    main()

