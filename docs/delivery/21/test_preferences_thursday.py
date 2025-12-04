#!/usr/bin/env python3
"""
Test the orchestrator with preferences: prefer Thursdays, lock Danielle's "Pick up" and "Ryan" events
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
    
    # Mark events with "Pick up" or containing "Ryan" on Danielle's calendar as locked
    dkehoe_events = events_by_participant_raw.get('dkehoe@concord.org', [])
    for event in dkehoe_events:
        title = event.get('summary', '') or event.get('title', '')
        if 'Pick up' in title or 'pickup' in title.lower() or 'Ryan' in title:
            event['locked'] = True
            event['protected'] = True
            event['flexible'] = False
            print(f"Marked as locked: {title} ({event.get('id', 'unknown')})")
    
    # Use the same format for orchestrate_scheduling
    events_by_participant = events_by_participant_raw
    
    # Print summary
    print("Loaded events:")
    for participant, events in events_by_participant.items():
        print(f"  {participant}: {len(events)} events")
    print()
    
    # Set up the scheduling request with preference for Thursdays
    utterance = "Can you suggest times for 45-minute meetings with Danielle between Dec. 10 and Dec. 19? Prefer Thursdays."
    
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
    print(f"Preferences: Prefer Thursdays")
    print(f"Locking rules: Danielle's events with 'Pick up' or 'Ryan' are locked")
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
                
                # Group single-move proposals by moved event
                move_groups = defaultdict(list)
                for proposal in single_move_proposals:
                    moved_events = proposal.get('moved_events', [])
                    if moved_events:
                        first_move = moved_events[0]
                        owner = first_move.get('owner', 'unknown')
                        event_id = first_move.get('event_id', 'unknown')
                        key = (owner, event_id)
                        move_groups[key].append(proposal)
                
                # Print grouped by moved event
                for (owner, event_id), proposals_group in move_groups.items():
                    meta = event_metadata.get((owner, event_id), {})
                    event_title = meta.get('title', event_id[:40])
                    owner_display = owner.split('@')[0].title() if '@' in owner else owner
                    
                    print(f"If you can adjust or move the meeting {owner_display}/{event_title}:")
                    print()
                    
                    # Sort by free-block score (if available)
                    proposals_group.sort(
                        key=lambda p: -(p.get('free_block_stats', {}).get('free_block_score', 0.0) or 0.0)
                    )
                    
                    for i, proposal in enumerate(proposals_group, 1):
                        _print_move_option(proposal, i)
                    print()
                
                # Print solo-override proposals grouped by override event
                if solo_override_proposals:
                    override_groups = defaultdict(list)
                    for proposal in solo_override_proposals:
                        overridden = identify_overridden_events(proposal, events_by_participant_raw, event_metadata)
                        if overridden:
                            # Group by first overridden event
                            first_override = overridden[0]
                            override_groups[first_override].append(proposal)
                        else:
                            # Unidentified override
                            override_groups[('unknown', 'unknown')].append(proposal)
                    
                    for (owner, event_id), proposals_group in override_groups.items():
                        if owner != 'unknown':
                            meta = event_metadata.get((owner, event_id), {})
                            event_title = meta.get('title', 'solo/blocking event')
                            owner_display = owner.split('@')[0].title() if '@' in owner else owner
                            
                            print(f"If you can override {owner_display}'s event for {event_title}:")
                            print()
                            
                            # Sort by free-block score
                            proposals_group.sort(
                                key=lambda p: -(p.get('free_block_stats', {}).get('free_block_score', 0.0) or 0.0)
                            )
                            
                            for i, proposal in enumerate(proposals_group, 1):
                                _print_solo_override_option(proposal, i)
                            print()
                
                # Print all proposals in priority order (sorted by free-block score)
                print(f"\n{'='*70}")
                print("ALL OPTIONS IN PRIORITY ORDER (Sorted by Free-Block Score + Preferences)")
                print(f"{'='*70}")
                print()
                
                # Combine all proposals and sort by free-block score
                all_proposals_flat = []
                for prop in zero_conflict_proposals:
                    all_proposals_flat.append(('zero-conflict', prop))
                for prop in single_move_proposals:
                    all_proposals_flat.append(('single-move', prop))
                for prop in solo_override_proposals:
                    all_proposals_flat.append(('solo-override', prop))
                
                # Sort by free-block score (descending), then preference score
                all_proposals_flat.sort(
                    key=lambda x: (
                        -(x[1].get('free_block_stats', {}).get('free_block_score', 0.0) or 0.0),
                        # Preference score is already factored into sorting in orchestrate_scheduling
                    )
                )
                
                # Print all in priority order
                for idx, (proposal_type, proposal) in enumerate(all_proposals_flat, 1):
                    start_dt = datetime.fromisoformat(proposal['start_utc'].replace('Z', '+00:00'))
                    duration_minutes = proposal.get('duration_minutes', 45)
                    end_dt = start_dt + timedelta(minutes=duration_minutes)
                    et_tz = pytz.timezone('America/New_York')
                    start_et = start_dt.astimezone(et_tz)
                    end_et = end_dt.astimezone(et_tz)
                    
                    fb_score = proposal.get('free_block_stats', {}).get('free_block_score', 0.0) or 0.0
                    
                    # Check if Thursday
                    weekday = start_et.strftime('%A')
                    thursday_indicator = " [THURSDAY - Preferred]" if weekday == 'Thursday' else ""
                    
                    print(f"#{idx}. {start_et.strftime('%A, %B %d, %Y at %I:%M %p %Z')}{thursday_indicator}")
                    print(f"   End: {end_et.strftime('%I:%M %p %Z')}")
                    print(f"   Type: {proposal_type}")
                    print(f"   Free-block score: {fb_score:.2f}")
                    
                    # Show move details if applicable
                    moved_events = proposal.get('moved_events', [])
                    if moved_events:
                        for moved in moved_events:
                            owner = moved.get('owner', 'unknown')
                            event_id = moved.get('event_id', 'unknown')
                            shift_minutes = moved.get('shift_minutes', 0)
                            old_start = moved.get('old_start', '')
                            new_start = moved.get('new_start', '')
                            
                            meta = event_metadata.get((owner, event_id), {})
                            event_title = meta.get('title', event_id[:40])
                            owner_display = owner.split('@')[0].title() if '@' in owner else owner
                            
                            print(f"   Move: {owner_display}/{event_title} (shift {shift_minutes} min)")
                            if old_start and new_start:
                                try:
                                    old_dt = datetime.fromisoformat(old_start.replace('Z', '+00:00'))
                                    new_dt = datetime.fromisoformat(new_start.replace('Z', '+00:00'))
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
        else:
            print(f"Unexpected result format: {type(result)}")
            print(result)
    
    except Exception as e:
        print(f"Error calling orchestrator: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()

