#!/usr/bin/env python3
"""
Test the orchestrator with Dec 10-19 date range for Chad, Danielle, and Sue
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

# Import helper functions from the other test file
sys.path.insert(0, str(Path(__file__).parent))
from test_dec10_19_chad_danielle import (
    identify_overridden_events,
    _print_move_option,
    _print_solo_override_option,
    _print_proposal_details,
    load_events_and_metadata
)

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
    if not events_by_participant or sum(len(events) for events in events_by_participant.values()) == 0:
        print("WARNING: No events loaded! Check file format.")
    print()
    
    # Set up the scheduling request
    utterance = "Find me possible 45-minute meeting slots with Sue and Danielle between Dec. 10 and Dec. 19."
    
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
            },
            {
                'id': 'sbrau@concord.org',
                'email': 'sbrau@concord.org',
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
    print(f"Participants: Chad, Sue, and Danielle")
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
            # Print all proposals in priority order (sorted by free-block score)
            print(f"\n{'='*70}")
            print("ALL OPTIONS IN PRIORITY ORDER (Sorted by Free-Block Score)")
            print(f"{'='*70}")
            print()
            
            # Helper function to get free-block score
            def get_fb_score(prop):
                if isinstance(prop, dict):
                    fb_stats = prop.get('free_block_stats', {})
                    if isinstance(fb_stats, dict):
                        return fb_stats.get('free_block_score', 0.0) or 0.0
                # Try as attribute if it's a Pydantic model
                if hasattr(prop, 'free_block_stats') and prop.free_block_stats:
                    return prop.free_block_stats.free_block_score or 0.0
                return 0.0
            
            # Combine all proposals and sort by free-block score
            all_proposals_flat = []
            for prop in zero_conflict_proposals:
                all_proposals_flat.append(('zero-conflict', prop))
            for prop in single_move_proposals:
                all_proposals_flat.append(('single-move', prop))
            for prop in solo_override_proposals:
                all_proposals_flat.append(('solo-override', prop))
            
            # Sort by free-block score (descending)
            all_proposals_flat.sort(
                key=lambda x: -get_fb_score(x[1])
            )
            
            # Print all in priority order
            for idx, (proposal_type, proposal) in enumerate(all_proposals_flat, 1):
                # Handle both dict and Pydantic model
                if isinstance(proposal, dict):
                    start_utc = proposal.get('start_utc', '')
                    moved_events = proposal.get('moved_events', [])
                else:
                    start_utc = proposal.start_utc
                    moved_events = proposal.moved_events if hasattr(proposal, 'moved_events') else []
                
                start_dt = datetime.fromisoformat(start_utc.replace('Z', '+00:00'))
                # Get duration from proposal (default 45 minutes)
                duration_minutes = proposal.get('duration_minutes', 45) if isinstance(proposal, dict) else (proposal.duration_minutes if hasattr(proposal, 'duration_minutes') else 45)
                end_dt = start_dt + timedelta(minutes=duration_minutes)
                et_tz = pytz.timezone('America/New_York')
                start_et = start_dt.astimezone(et_tz)
                end_et = end_dt.astimezone(et_tz)
                
                fb_score = get_fb_score(proposal)
                
                print(f"#{idx}. {start_et.strftime('%A, %B %d, %Y at %I:%M %p %Z')}")
                print(f"   End: {end_et.strftime('%I:%M %p %Z')}")
                print(f"   Type: {proposal_type}")
                print(f"   Free-block score: {fb_score:.2f}")
                
                # Show move details if applicable
                if moved_events:
                    for moved in moved_events:
                        if isinstance(moved, dict):
                            owner = moved.get('owner', 'unknown')
                            event_id = moved.get('event_id', 'unknown')
                            shift_minutes = moved.get('shift_minutes', 0)
                            old_start = moved.get('old_start', '')
                            new_start = moved.get('new_start', '')
                        else:
                            owner = moved.owner if hasattr(moved, 'owner') else 'unknown'
                            event_id = moved.event_id if hasattr(moved, 'event_id') else 'unknown'
                            shift_minutes = moved.shift_minutes if hasattr(moved, 'shift_minutes') else 0
                            old_start = moved.old_start if hasattr(moved, 'old_start') else ''
                            new_start = moved.new_start if hasattr(moved, 'new_start') else ''
                        
                        meta = event_metadata.get((owner, event_id), {})
                        event_title = meta.get('title', event_id[:40])
                        owner_display = owner.split('@')[0].title() if '@' in owner else owner
                        
                        print(f"   Move: {owner_display}/{event_title} (shift {shift_minutes} min)")
                        if old_start and new_start:
                            try:
                                old_dt = datetime.fromisoformat(str(old_start).replace('Z', '+00:00'))
                                new_dt = datetime.fromisoformat(str(new_start).replace('Z', '+00:00'))
                                old_et = old_dt.astimezone(et_tz)
                                new_et = new_dt.astimezone(et_tz)
                                print(f"         {old_et.strftime('%I:%M %p')} -> {new_et.strftime('%I:%M %p')}")
                            except:
                                pass
                
                # Show override details if applicable
                if proposal_type == 'solo-override':
                    overridden = identify_overridden_events(proposal, events_by_participant_raw, event_metadata)
                    if overridden:
                        for owner, event_id in overridden:
                            meta = event_metadata.get((owner, event_id), {})
                            event_title = meta.get('title', 'solo/blocking event')
                            owner_display = owner.split('@')[0].title() if '@' in owner else owner
                            print(f"   Override: {owner_display}'s {event_title}")
                
                print()
            
            if not all_proposals_flat:
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
    output_file = Path(__file__).parent / 'test_dec10_19_all_three_results.json'
    try:
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nResults saved to: {output_file}")
    except Exception as e:
        print(f"Warning: Could not save results: {e}", file=sys.stderr)

if __name__ == '__main__':
    main()

