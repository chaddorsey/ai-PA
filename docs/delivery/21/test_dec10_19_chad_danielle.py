#!/usr/bin/env python3
"""
Test the orchestrator with Dec 10-19 date range for Chad and Danielle only
"""
import json
import sys
import re
from pathlib import Path
from datetime import datetime, timedelta
import pytz
from collections import defaultdict

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


def identify_overridden_events(proposal, events_by_participant, event_metadata):
    """Identify which solo events are being overridden by this proposal."""
    start_str = proposal.get('start_utc', '') or proposal.get('start', '')
    end_str = proposal.get('end_utc', '') or proposal.get('end', '')
    
    if not start_str or not end_str:
        return []
    
    try:
        start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
        if start_dt.tzinfo is None:
            start_dt = pytz.UTC.localize(start_dt)
        if end_dt.tzinfo is None:
            end_dt = pytz.UTC.localize(end_dt)
    except:
        return []
    
    participants = proposal.get('participants', [])
    overridden_events = []
    
    for participant_id in participants:
        events = events_by_participant.get(participant_id, [])
        for event in events:
            event_id = event.get('id', '')
            event_start_str = event.get('start', '')
            event_end_str = event.get('end', '')
            
            if not event_start_str or not event_end_str:
                continue
            
            try:
                event_start = datetime.fromisoformat(event_start_str.replace('Z', '+00:00'))
                event_end = datetime.fromisoformat(event_end_str.replace('Z', '+00:00'))
                if event_start.tzinfo is None:
                    event_start = pytz.UTC.localize(event_start)
                if event_end.tzinfo is None:
                    event_end = pytz.UTC.localize(event_end)
                
                # Check if proposal overlaps with this event
                if start_dt < event_end and end_dt > event_start:
                    # Check if this is a solo event (0 attendees)
                    meta = event_metadata.get((participant_id, event_id), {})
                    num_attendees = meta.get('number_of_attendees', 0)
                    if num_attendees == 0:
                        overridden_events.append((participant_id, event_id))
            except:
                continue
    
    return overridden_events


def _print_move_option(proposal, option_num):
    """Print a single-move proposal option."""
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
            print(f"  Option {option_num}: {et.strftime('%A, %B %d, %Y at %I:%M %p %Z')}")
        except Exception as e:
            print(f"  Option {option_num}: {start_str} (parse error: {e})")
    
    if end_str:
        try:
            end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
            if end_dt.tzinfo is None:
                end_dt = pytz.UTC.localize(end_dt)
            else:
                end_dt = end_dt.astimezone(pytz.UTC)
            et = end_dt.astimezone(pytz.timezone('America/New_York'))
            print(f"    End: {et.strftime('%I:%M %p %Z')}")
        except Exception as e:
            pass
    
    # Show free-block stats if available
    free_block_stats = proposal.get('free_block_stats')
    if free_block_stats:
        fb_score = free_block_stats.get('free_block_score', 0.0)
        if fb_score != 0.0:
            print(f"    Free-block score: {fb_score:.2f}")
    
    # Show move details
    moved_events = proposal.get('moved_events', [])
    if moved_events:
        moved = moved_events[0]
        shift_minutes = moved.get('shift_minutes', 0)
        old_start = moved.get('old_start', '')
        new_start = moved.get('new_start', '')
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
                direction = "earlier" if shift_minutes < 0 else "later"
                print(f"    (Move {abs(shift_minutes)} minutes {direction}: {old_et.strftime('%I:%M %p')} -> {new_et.strftime('%I:%M %p')})")
            except:
                pass


def _print_solo_override_option(proposal, option_num):
    """Print a solo-override proposal option."""
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
            print(f"  Option {option_num}: {et.strftime('%A, %B %d, %Y at %I:%M %p %Z')}")
        except Exception as e:
            print(f"  Option {option_num}: {start_str} (parse error: {e})")
    
    if end_str:
        try:
            end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
            if end_dt.tzinfo is None:
                end_dt = pytz.UTC.localize(end_dt)
            else:
                end_dt = end_dt.astimezone(pytz.UTC)
            et = end_dt.astimezone(pytz.timezone('America/New_York'))
            print(f"    End: {et.strftime('%I:%M %p %Z')}")
        except Exception as e:
            pass
    
    # Show free-block stats if available
    free_block_stats = proposal.get('free_block_stats')
    if free_block_stats:
        fb_score = free_block_stats.get('free_block_score', 0.0)
        if fb_score != 0.0:
            print(f"    Free-block score: {fb_score:.2f}")


def _print_proposal_details(proposal, option_num):
    """Helper function to print proposal details."""
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
        print(f"  Type: Single-move (requires moving {len(moved_events)} event(s))")
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
                    print(f"      ({old_et.strftime('%I:%M %p')} -> {new_et.strftime('%I:%M %p')})")
                except:
                    pass
    else:
        # Check if this is a solo-override proposal
        notes = proposal.get('notes_for_invite', '')
        if notes and 'solo/blocking events' in notes.lower():
            print(f"  Type: Solo-override slot")
        else:
            print(f"  Type: Free slot (zero-conflict)")
    
    # Show priority score and objective scores if available
    objective_scores = proposal.get('objective_scores', {})
    if objective_scores:
        priority_score = objective_scores.get('priority_score', 0.0)
        if priority_score != 0.0:
            print(f"  Priority score: {priority_score:.2f}")
        moved_minutes = objective_scores.get('moved_minutes', 0)
        protected_moved = objective_scores.get('protected_events_moved', 0)
        if moved_minutes > 0:
            print(f"  Move details: {moved_minutes} minutes, {protected_moved} protected event(s)")
    
    # Show free-block stats if available
    free_block_stats = proposal.get('free_block_stats')
    if free_block_stats:
        fb_score = free_block_stats.get('free_block_score', 0.0)
        median_hours = free_block_stats.get('median_block_hours', 0.0)
        max_hours = free_block_stats.get('max_block_hours', 0.0)
        avg_hours = free_block_stats.get('avg_block_hours', 0.0)
        total_hours = free_block_stats.get('total_effective_hours', 0.0)
        if fb_score != 0.0:
            print(f"  Free-block score: {fb_score:.2f}")
            print(f"    - Median block: {median_hours:.2f}h | Max block: {max_hours:.2f}h | Avg block: {avg_hours:.2f}h | Total: {total_hours:.2f}h")
    print()


def load_events_and_metadata(file_path: Path):
    """Load events and build metadata map for event lookups."""
    events_by_participant = {}
    event_metadata = {}  # Maps (participant_id, event_id) -> {title, number_of_attendees, ...}
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Extract JSON blocks for each participant
    participants = ['cdorsey@concord.org', 'dkehoe@concord.org', 'sbrau@concord.org']
    
    for participant in participants:
        # Find the participant's event array - format is "participant events:\n\n[{...}]"
        pattern = rf'{participant}\s+events:\s*\n\s*\n(.*?)(?=\n\w+@\w+\.\w+\s+events:|\Z)'
        match = re.search(pattern, content, re.DOTALL | re.MULTILINE)
        
        if not match:
            # Try alternative pattern with JSON array
            pattern2 = rf'{participant}.*?\[(.*?)\]'
            match2 = re.search(pattern2, content, re.DOTALL)
            if match2:
                json_str = match2.group(1)
            else:
                continue
        else:
            json_str = match.group(1).strip()
        # Try to parse the events
        try:
            # The json_str should already be a JSON array, so try parsing directly
            try:
                events_json = json.loads(json_str)
            except:
                # If that fails, wrap in brackets
                events_json = json.loads('[' + json_str + ']')
            
            # Handle case where it's already a list
            if not isinstance(events_json, list):
                events_json = [events_json]
            
            normalized_events = []
            
            for event in events_json:
                if not isinstance(event, dict):
                    continue  # Skip non-dict items
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
                
                event_id = event.get('id', '')
                title = event.get('summary', '') or event.get('title', '')
                num_attendees = event.get('number_of_attendees', 0)
                
                # Store metadata
                event_metadata[(participant, event_id)] = {
                    'title': title,
                    'number_of_attendees': num_attendees,
                    'owner': participant,
                    'start': start_str,
                    'end': end_str
                }
                
                normalized_events.append({
                    'id': event_id,
                    'summary': title,
                    'start': start_str,
                    'end': end_str,
                    'locked': event.get('locked', False),
                    'protected': event.get('protected', False),
                    'flexible': event.get('flexible', True),
                    'internal_only': event.get('internal_only', True),
                    'number_of_attendees': num_attendees
                })
            events_by_participant[participant] = normalized_events
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON for {participant}: {e}", file=sys.stderr)
            events_by_participant[participant] = []
    
    return events_by_participant, event_metadata


def load_events_from_example_v2(file_path: Path):
    """Load events from example_event_data_v2.md format."""
    events_by_participant = {}
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Extract JSON blocks for each participant
    participants = ['cdorsey@concord.org', 'dkehoe@concord.org', 'sbrau@concord.org']
    
    for participant in participants:
        # Find the participant's event array - format is "participant events:\n\n[{...}]"
        pattern = rf'{participant}\s+events:\s*\n\s*\n(.*?)(?=\n\w+@\w+\.\w+\s+events:|\Z)'
        match = re.search(pattern, content, re.DOTALL | re.MULTILINE)
        
        if not match:
            # Try alternative pattern with JSON array
            pattern2 = rf'{participant}.*?\[(.*?)\]'
            match2 = re.search(pattern2, content, re.DOTALL)
            if match2:
                json_str = match2.group(1)
            else:
                events_by_participant[participant] = []
                continue
        else:
            json_str = match.group(1).strip()
        # Try to parse the events
        try:
            # The json_str should already be a JSON array, so try parsing directly
            try:
                events = json.loads(json_str)
            except:
                # If that fails, wrap in brackets
                events = json.loads('[' + json_str + ']')
            
            # Handle case where it's already a list
            if not isinstance(events, list):
                events = [events]
            
            # Normalize event structure (extract dateTime from nested objects)
            normalized_events = []
            for event in events:
                if not isinstance(event, dict):
                    continue  # Skip non-dict items
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
    example_file = Path(__file__).parent / 'example_event_data_v2.md'
    if not example_file.exists():
        print(f"Error: {example_file} not found", file=sys.stderr)
        sys.exit(1)
    
    # Load both metadata and events for orchestrate_scheduling
    events_by_participant_raw, event_metadata = load_events_and_metadata(example_file)
    
    # Use the same format for orchestrate_scheduling (events_by_participant_raw is already in the right format)
    events_by_participant = events_by_participant_raw
    
    # Print summary
    print("Loaded events:")
    for participant, events in events_by_participant.items():
        print(f"  {participant}: {len(events)} events")
    print()
    
    # Set up the scheduling request
    utterance = "Find me possible 45-minute meeting slots with Danielle between Dec. 10 and Dec. 19."
    
    # Create context JSON
    context_json = {
        'timeframe': {
            'from': '2025-12-10',
            'to': '2025-12-19',
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
    print(f"Date range: Dec 10-19, 2025")
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
            print(f"Total proposals found: {len(proposals)}")
            print()
            
            if proposals:
                # Separate proposals into categories
                zero_conflict_proposals = []
                move_override_proposals = []
                
                for proposal in proposals:
                    moved_events = proposal.get('moved_events', [])
                    notes = proposal.get('notes_for_invite', '')
                    is_solo_override = notes and 'solo/blocking events' in notes.lower()
                    
                    if len(moved_events) == 0 and not is_solo_override:
                        zero_conflict_proposals.append(proposal)
                    else:
                        move_override_proposals.append(proposal)
                
                # Print Best Options (all zero-conflict)
                print(f"{'='*70}")
                print("BEST OPTIONS (Zero-Conflict)")
                print(f"{'='*70}")
                print(f"Found {len(zero_conflict_proposals)} zero-conflict option(s)\n")
                
                for i, proposal in enumerate(zero_conflict_proposals, 1):
                    print(f"Option {i}:")
                    _print_proposal_details(proposal, i)
                
                # Print With Moves and Overrides (grouped by event)
                print(f"\n{'='*70}")
                print("WITH MOVES AND OVERRIDES")
                print(f"{'='*70}\n")
                
                # Separate single-move from solo-override
                single_move_proposals = []
                solo_override_proposals = []
                
                for proposal in move_override_proposals:
                    moved_events = proposal.get('moved_events', [])
                    notes = proposal.get('notes_for_invite', '')
                    is_solo_override = notes and 'solo/blocking events' in notes.lower()
                    
                    if len(moved_events) > 0:
                        single_move_proposals.append(proposal)
                    elif is_solo_override:
                        solo_override_proposals.append(proposal)
                
                # Group single-move proposals by moved event (owner + event_id)
                move_groups = defaultdict(list)
                for proposal in single_move_proposals:
                    moved_events = proposal.get('moved_events', [])
                    if moved_events:
                        # For single-move, there should be exactly one moved event
                        moved = moved_events[0]
                        owner = moved.get('owner', 'unknown')
                        event_id = moved.get('event_id', 'unknown')
                        key = (owner, event_id)
                        move_groups[key].append(proposal)
                
                # Sort move groups by number of attendees (from event metadata), then by highest free-block score
                def get_move_group_sort_key(group_key):
                    owner, event_id = group_key
                    meta = event_metadata.get((owner, event_id), {})
                    num_attendees = meta.get('number_of_attendees', 999)
                    # Get highest free-block score in this group
                    group_proposals = move_groups[group_key]
                    max_fb_score = max(
                        (prop.get('free_block_stats', {}).get('free_block_score', 0.0) or 0.0
                         for prop in group_proposals),
                        default=0.0
                    )
                    return (num_attendees, -max_fb_score)  # Lower attendees first, then higher score
                
                sorted_move_groups = sorted(move_groups.items(), key=lambda x: get_move_group_sort_key(x[0]))
                
                # Print single-move groups
                option_num = 1
                for (owner, event_id), group_proposals in sorted_move_groups:
                    # Sort proposals within group by free-block score
                    group_proposals.sort(
                        key=lambda p: -(p.get('free_block_stats', {}).get('free_block_score', 0.0) or 0.0)
                    )
                    
                    # Get event title
                    meta = event_metadata.get((owner, event_id), {})
                    event_title = meta.get('title', event_id[:40])
                    num_attendees = meta.get('number_of_attendees', 0)
                    
                    # Format owner name (remove email domain for display)
                    owner_display = owner.split('@')[0].title() if '@' in owner else owner
                    
                    print(f"If you can adjust or move the meeting {owner_display}/{event_title}:")
                    print()
                    
                    for proposal in group_proposals:
                        _print_move_option(proposal, option_num)
                        option_num += 1
                    print()
                
                # Group solo-override proposals by override event
                override_groups = defaultdict(list)
                for proposal in solo_override_proposals:
                    # Identify which solo events are being overridden
                    overridden = identify_overridden_events(proposal, events_by_participant_raw, event_metadata)
                    if overridden:
                        # Group by first overridden event (usually there's one primary override)
                        key = overridden[0]
                        override_groups[key].append(proposal)
                    else:
                        # Fallback: group all unknown overrides together
                        override_groups[('unknown', 'unknown')].append(proposal)
                
                # Sort override groups by highest free-block score
                def get_override_group_sort_key(group_key):
                    group_proposals = override_groups[group_key]
                    max_fb_score = max(
                        (prop.get('free_block_stats', {}).get('free_block_score', 0.0) or 0.0
                         for prop in group_proposals),
                        default=0.0
                    )
                    return -max_fb_score  # Higher score first
                
                sorted_override_groups = sorted(override_groups.items(), key=lambda x: get_override_group_sort_key(x[0]))
                
                # Print solo-override groups
                for (owner, event_id), group_proposals in sorted_override_groups:
                    # Sort proposals within group by free-block score
                    group_proposals.sort(
                        key=lambda p: -(p.get('free_block_stats', {}).get('free_block_score', 0.0) or 0.0)
                    )
                    
                    # Get event title
                    meta = event_metadata.get((owner, event_id), {})
                    event_title = meta.get('title', 'solo/blocking event')
                    owner_display = owner.split('@')[0].title() if '@' in owner and owner != 'unknown' else owner
                    
                    if owner != 'unknown':
                        print(f"If you can override {owner_display}'s event for {event_title}:")
                    else:
                        print("If you can override solo/blocking events:")
                    print()
                    
                    # Limit to top 6 per override event
                    for proposal in group_proposals[:6]:
                        _print_solo_override_option(proposal, option_num)
                        option_num += 1
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
    output_file = Path(__file__).parent / 'test_dec10_19_chad_danielle_results.json'
    try:
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nResults saved to: {output_file}")
    except Exception as e:
        print(f"Warning: Could not save results: {e}", file=sys.stderr)

if __name__ == '__main__':
    main()
