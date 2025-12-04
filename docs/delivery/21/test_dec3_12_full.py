#!/usr/bin/env python3
"""
Test script for orchestrator with Dec 3-12 date range.
"""

import json
import sys
import os
from pathlib import Path

# Load .env file if it exists
project_root = Path(__file__).parent.parent.parent.parent
env_path = project_root / '.env'
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        pass

sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "letta"))

from scheduling_orchestrator.orchestrate_scheduling import orchestrate_scheduling

def load_events_from_example(example_file):
    """Load events from the example markdown file."""
    with open(example_file, 'r') as f:
        content = f.read()
    
    events_by_participant = {}
    participants = ['cdorsey@concord.org', 'sbrau@concord.org', 'dkehoe@concord.org']
    
    for participant in participants:
        marker = f'Event data for {participant}:'
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
            normalized_events = []
            for event in events:
                start_val = event.get('start', '')
                start_str = start_val.get('dateTime', '') if isinstance(start_val, dict) else str(start_val) if start_val else ''
                end_val = event.get('end', '')
                end_str = end_val.get('dateTime', '') if isinstance(end_val, dict) else str(end_val) if end_val else ''
                normalized_events.append({
                    'id': event.get('id', ''),
                    'title': event.get('summary') or event.get('title', ''),
                    'start': start_str,
                    'end': end_str,
                    'locked': event.get('locked', False),
                    'protected': event.get('protected', False),
                    'flexible': event.get('flexible', True),
                    'internal_only': event.get('internal_only', True),
                    'number_of_attendees': event.get('number_of_attendees', 0)
                })
            events_by_participant[participant] = normalized_events
        except Exception as e:
            print(f"Error parsing events for {participant}: {e}")
    
    return events_by_participant

def main():
    utterance = "Find me possible 45-minute meeting slots with Sue and Danielle between Dec. 3 and Dec. 12."
    
    example_file = Path(__file__).parent / "example_event_data.md"
    events_by_participant = load_events_from_example(example_file)
    
    context_json = {
        'timeframe': {'from': '2025-12-03', 'to': '2025-12-12', 'tz': 'America/New_York'},
        'participants': [
            {'id': 'cdorsey@concord.org', 'email': 'cdorsey@concord.org', 'work_hours': 'M-F 09:00-17:00'},
            {'id': 'sbrau@concord.org', 'email': 'sbrau@concord.org', 'work_hours': 'M-F 09:00-17:00'},
            {'id': 'dkehoe@concord.org', 'email': 'dkehoe@concord.org', 'work_hours': 'M-F 09:00-17:00'}
        ],
        'policy': {'hard': {'min_gap_min': 0}, 'soft': {}},
        'slot_size_minutes': 15
    }
    
    events_json = json.dumps(events_by_participant)
    context_json_str = json.dumps(context_json)
    
    print("=" * 80)
    print("ORCHESTRATOR TEST: Dec 3-12, 2025")
    print("=" * 80)
    print(f"Utterance: {utterance}")
    print(f"Participants: Chad, Sue, Danielle")
    print(f"Duration: 45 minutes")
    print(f"Time range: Dec 3-12, 2025")
    print()
    print("Running orchestrator...")
    print("-" * 80)
    print()
    
    result = orchestrate_scheduling(utterance, events_json, context_json_str)
    
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"\nStatus: {result.get('status', 'unknown')}")
    
    proposals = result.get('proposals', [])
    print(f"\nFound {len(proposals)} proposal(s):\n")
    
    from datetime import datetime
    import pytz
    
    for i, proposal in enumerate(proposals, 1):
        print(f"Proposal {i}:")
        print(f"  Title: {proposal.get('title', 'N/A')}")
        
        # Parse start/end times
        start_utc_str = proposal.get('start_utc', '')
        end_utc_str = proposal.get('end_utc', '')
        if start_utc_str:
            try:
                start_dt = datetime.fromisoformat(start_utc_str.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_utc_str.replace('Z', '+00:00'))
                et_tz = pytz.timezone('America/New_York')
                start_et = start_dt.astimezone(et_tz)
                end_et = end_dt.astimezone(et_tz)
                print(f"  Start: {start_et.strftime('%A, %B %d, %Y at %I:%M %p %Z')}")
                print(f"  End: {end_et.strftime('%I:%M %p %Z')}")
            except:
                print(f"  Start: {start_utc_str}")
                print(f"  End: {end_utc_str}")
        else:
            print(f"  Start: N/A")
            print(f"  End: N/A")
        
        print(f"  Participants: {', '.join(proposal.get('participants', []))}")
        
        moved_events = proposal.get('moved_events', [])
        if moved_events:
            print(f"  Moved Events ({len(moved_events)}):")
            for me in moved_events:
                print(f"    - {me.get('owner', 'N/A')}: {me.get('shift_minutes', 0)} minutes")
        else:
            print(f"  Moved Events: None (free slot)")
        print()
    
    explanation = result.get('explanation', '')
    if explanation:
        print(f"Explanation:\n{explanation}\n")
    
    debug = result.get('debug', {})
    if debug:
        print("-" * 80)
        print("DEBUG INFO")
        print("-" * 80)
        asp_stats = debug.get('asp_stats', {})
        if asp_stats:
            print(f"ASP Stats: {asp_stats}")
        print(f"Free slots found: {debug.get('free_slots_found', 'N/A')}")
        print(f"Horizon reduced: {debug.get('horizon_reduced', False)}")
        if debug.get('horizon_reduced'):
            print(f"  Original slots: {debug.get('original_slots', 'N/A')}")
            print(f"  Reduced slots: {debug.get('reduced_slots', 'N/A')}")
        print(f"Models found (ASP): {asp_stats.get('models', 0) if asp_stats else 'N/A'}")
        print(f"Solve time: {debug.get('solve_time_ms', 0)}ms")

if __name__ == "__main__":
    main()

