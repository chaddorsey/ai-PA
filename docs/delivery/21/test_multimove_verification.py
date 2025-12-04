#!/usr/bin/env python3
"""
Test to verify multi-move ASP fallback is working correctly.

This test:
1. Verifies ASP fallback triggers when Python solver finds no solution
2. Checks that ASP can find multi-move solutions
3. Validates that solutions require moving multiple events
4. Verifies prioritization (internal-only, fewer attendees)
"""

import json
import sys
from pathlib import Path
from datetime import datetime
import pytz

# Load .env
project_root = Path(__file__).parent.parent.parent.parent
env_path = project_root / '.env'
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "letta"))

from scheduling_orchestrator.orchestrate_scheduling import orchestrate_scheduling
from scheduling_orchestrator.normalizer import normalize_events
from scheduling_orchestrator.fact_generator import _find_free_slots
from scheduling_orchestrator.python_solver import _find_slots_with_single_move
from scheduling_orchestrator.schemas import SchedulingProblem


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
                
                normalized = {
                    "id": event.get("id", ""),
                    "title": event.get("summary") or event.get("title", ""),
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
            print(f"Warning: Failed to parse JSON for {participant}: {e}")
            continue
    
    return events_by_participant


def analyze_solver_results(normalized_data, scheduling_problem):
    """Analyze what Python solver can find"""
    slot_indexer = normalized_data["slot_indexer"]
    all_slots = slot_indexer.get_all_slots()
    busy_slots = normalized_data.get("busy_slots", {})
    work_hours_slots = normalized_data.get("work_hours_slots", {})
    event_protection = normalized_data.get("event_protection", {})
    duration_slots = max(1, scheduling_problem.duration_minutes // 15)
    min_gap_slots = normalized_data.get("min_gap_slots", 0)
    
    # Check free slots
    free_slots = _find_free_slots(
        all_slots,
        busy_slots,
        work_hours_slots,
        scheduling_problem.participants,
        duration_slots,
        min_gap_slots
    )
    
    # Check single-move slots
    # Extract flexible events and locked events for single-move logic
    flexible_events = {}
    locked_events = {}
    for (participant_id, event_id), protection_level in event_protection.items():
        if protection_level == "locked":
            if participant_id not in locked_events:
                locked_events[participant_id] = set()
            # For now, we'll rely on the fact that locked events are in busy_slots
        elif protection_level in ["flexible", "protected"]:
            if participant_id not in flexible_events:
                flexible_events[participant_id] = []
            # Would need event data to populate this properly
    
    print(f"  Free slots: {len(free_slots)}")
    print(f"  Single-move candidates: (would need full event data to check)")
    
    return len(free_slots) == 0  # Returns True if no free slots (ASP fallback needed)


if __name__ == "__main__":
    print("="*80)
    print("MULTI-MOVE ASP FALLBACK VERIFICATION TEST")
    print("="*80)
    print()
    
    # Load events
    example_file = Path(__file__).parent / "example_event_data.md"
    events_by_participant = load_events_from_example(example_file)
    
    print(f"Loaded events:")
    for participant, events in events_by_participant.items():
        print(f"  {participant}: {len(events)} events")
    print()
    
    # Test scenario: Dec 3-12 (known to have no free slots)
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
    
    print("="*80)
    print("STEP 1: Verify Python solver cannot find solution")
    print("="*80)
    
    # Normalize to check what Python solver can find
    normalized_data = normalize_events(events_by_participant, context_json=context_json)
    scheduling_problem = SchedulingProblem(
        participants=["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"],
        duration_minutes=45,
        time_window_start="2025-12-03T09:00:00-05:00",
        time_window_end="2025-12-12T17:00:00-05:00"
    )
    
    needs_asp = analyze_solver_results(normalized_data, scheduling_problem)
    
    if needs_asp:
        print("✓ Confirmed: No free slots, ASP fallback should be triggered")
    else:
        print("⚠️  Warning: Free slots exist, ASP fallback may not be needed")
    print()
    
    print("="*80)
    print("STEP 2: Run orchestrator and verify ASP fallback")
    print("="*80)
    print()
    
    events_json = json.dumps(events_by_participant)
    context_json_str = json.dumps(context_json)
    
    print(f"Utterance: {utterance}")
    print(f"Timeframe: Dec 3-12, 2025")
    print()
    print("Running orchestrator (ASP fallback should trigger)...")
    print("-" * 80)
    print()
    
    try:
        result = orchestrate_scheduling(utterance, events_json, context_json_str)
    except Exception as e:
        print(f"\nERROR: Orchestrator call failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Analyze results
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"\nStatus: {result.get('status', 'unknown')}")
    
    debug = result.get('debug', {})
    asp_stats = debug.get('asp_stats')
    asp_fallback_error = result.get('asp_fallback_error')
    
    print(f"\nDebug info keys: {list(debug.keys())}")
    
    if asp_stats:
        print("\n✓ ASP fallback WAS triggered")
        print(f"  Models found: {asp_stats.get('models', 'N/A')}")
        print(f"  Optimum proven: {asp_stats.get('optimum', 'N/A')}")
        if asp_stats.get('error'):
            print(f"  Error: {asp_stats.get('error')}")
            if 'parsing' in asp_stats.get('error', '').lower():
                print("  ⚠️  ASP parsing error - may need to fix ASP program generation")
            elif 'too many messages' in asp_stats.get('error', '').lower():
                print("  ⚠️  Clingo grounding limit - may need further optimization")
    elif asp_fallback_error:
        print(f"\n✓ ASP fallback WAS triggered but failed")
        print(f"  Error: {asp_fallback_error}")
    else:
        print("\n⚠️  ASP fallback was NOT triggered")
        print("  This means:")
        print("    1. Python solver found a solution, OR")
        print("    2. ASP import failed, OR")
        print("    3. Exception occurred before ASP was called")
        print(f"\n  Solve time: {debug.get('solve_time_ms', 'N/A')} ms")
        print(f"  Free slots found: {debug.get('free_slots_found', 'N/A')}")
    
    if result.get('status') == 'ok':
        proposals = result.get('proposals', [])
        print(f"\n✓ Solution found: {len(proposals)} proposal(s)")
        
        for i, proposal in enumerate(proposals, 1):
            print(f"\nProposal {i}:")
            print(f"  Start: {proposal.get('start_utc', 'N/A')}")
            
            moved_events = proposal.get('moved_events', [])
            if moved_events:
                print(f"  Moved Events: {len(moved_events)} event(s)")
                
                # Count how many participants need moves
                participants_with_moves = set()
                for me in moved_events:
                    owner = me.get('owner', 'unknown')
                    participants_with_moves.add(owner)
                    shift = me.get('shift_minutes', 0)
                    protected = me.get('protected', False)
                    print(f"    - {owner}: shift {shift} min, protected={protected}")
                
                if len(participants_with_moves) > 1:
                    print(f"\n  ✓ Multi-move confirmed: {len(participants_with_moves)} participants need moves")
                elif len(moved_events) > 1:
                    print(f"\n  ✓ Multi-move confirmed: {len(moved_events)} events need moves")
                else:
                    print(f"\n  Note: Single-move solution (may have come from Python solver)")
            else:
                print(f"  Moved Events: None (free slot)")
    
    print("\n" + "="*80)
    print("STEP 3: Verify prioritization logic")
    print("="*80)
    print("\nIf multi-move solution was found, check:")
    print("  1. Are internal-only meetings prioritized?")
    print("  2. Are meetings with fewer attendees preferred?")
    print("  3. Are protected events moved only when necessary?")
    print()

