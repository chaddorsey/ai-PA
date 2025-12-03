#!/usr/bin/env python3
"""
End-to-end tests for the scheduling orchestrator tool.
Tests various scenarios to ensure the tool is fully operational for Letta agent use.
"""

import json
import sys
import os
from pathlib import Path
from typing import Dict, Any, List
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
        print(f"Warning: Example file not found: {example_file}")
        return {
            "cdorsey@concord.org": [],
            "sbrau@concord.org": [],
            "dkehoe@concord.org": []
        }
    
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


def create_context(requester_id: str = "cdorsey@concord.org", min_gap: int = 0) -> Dict[str, Any]:
    """Create a standard context for testing"""
    return {
        "timeframe": {
            "from": "2025-12-01",
            "to": "2025-12-12",
            "tz": "America/New_York"
        },
        "requester_id": requester_id,
        "participants": [
            {
                "id": "cdorsey@concord.org",
                "email": "cdorsey@concord.org",
                "name": "Chad"
                # No work_hours specified - will use default 9-5 Eastern
            },
            {
                "id": "sbrau@concord.org",
                "email": "sbrau@concord.org",
                "name": "Sue",
                "work_hours": "M-F 10:00-18:00"  # Different work hours to test individual settings
            },
            {
                "id": "dkehoe@concord.org",
                "email": "dkehoe@concord.org",
                "name": "Danielle"
                # No work_hours specified - will use default 9-5 Eastern
            }
        ],
        "policy": {
            "hard": {
                "min_gap_min": min_gap
            }
        }
    }


def validate_response_structure(response: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Validate that response has the expected Letta tool structure"""
    errors = []
    
    # Required top-level fields
    required_fields = ["status"]
    for field in required_fields:
        if field not in response:
            errors.append(f"Missing required field: {field}")
    
    # Status should be one of: "ok", "unsat", "bad_input"
    if "status" in response:
        valid_statuses = ["ok", "unsat", "bad_input"]
        if response["status"] not in valid_statuses:
            errors.append(f"Invalid status: {response['status']} (expected one of {valid_statuses})")
    
    # If status is "ok", should have proposals
    if response.get("status") == "ok":
        if "proposals" not in response:
            errors.append("Status is 'ok' but missing 'proposals' field")
        elif not isinstance(response["proposals"], list):
            errors.append("'proposals' should be a list")
        elif len(response["proposals"]) == 0:
            errors.append("Status is 'ok' but proposals list is empty")
        else:
            # Validate proposal structure
            for i, proposal in enumerate(response["proposals"]):
                required_proposal_fields = ["participants", "start_utc", "end_utc"]
                for field in required_proposal_fields:
                    if field not in proposal:
                        errors.append(f"Proposal {i} missing required field: {field}")
    
    # Should have debug info
    if "debug" not in response:
        errors.append("Missing 'debug' field")
    
    # Should have explanation
    if "explanation" not in response:
        errors.append("Missing 'explanation' field")
    
    return len(errors) == 0, errors


def run_test(name: str, utterance: str, events: dict, context: dict, 
             expected_status: str = "ok", expected_min_proposals: int = 1,
             validate_participants: List[str] = None) -> bool:
    """Run a single test case"""
    print(f"\n{'='*80}")
    print(f"TEST: {name}")
    print('='*80)
    print(f"Utterance: {utterance}")
    print(f"Expected status: {expected_status}")
    print(f"Expected min proposals: {expected_min_proposals}")
    if validate_participants:
        print(f"Expected participants: {validate_participants}")
    print('-'*80)
    
    events_json_str = json.dumps(events)
    context_json_str = json.dumps(context)
    
    try:
        response = orchestrate_scheduling(
            utterance=utterance,
            events_by_participant=events_json_str,
            context_json=context_json_str
        )
        
        # Validate response structure
        is_valid, errors = validate_response_structure(response)
        if not is_valid:
            print(f"✗ Response structure validation failed:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        # Check status
        actual_status = response.get("status")
        if actual_status != expected_status:
            print(f"✗ Status mismatch: expected '{expected_status}', got '{actual_status}'")
            if response.get("error_message"):
                print(f"  Error message: {response.get('error_message')}")
            return False
        
        # Check proposals
        if expected_status == "ok":
            proposals = response.get("proposals", [])
            if len(proposals) < expected_min_proposals:
                print(f"✗ Insufficient proposals: expected at least {expected_min_proposals}, got {len(proposals)}")
                return False
            
            # Check participants if specified
            if validate_participants:
                actual_participants = sorted(proposals[0].get("participants", []))
                expected_sorted = sorted(validate_participants)
                if actual_participants != expected_sorted:
                    print(f"✗ Participant mismatch:")
                    print(f"  Expected: {expected_sorted}")
                    print(f"  Actual:   {actual_participants}")
                    return False
            
            # Print proposal details
            proposal = proposals[0]
            print(f"✓ Status: {actual_status}")
            print(f"✓ Found {len(proposals)} proposal(s)")
            print(f"  Start: {proposal.get('start_utc')}")
            print(f"  End: {proposal.get('end_utc')}")
            print(f"  Participants: {proposal.get('participants')}")
            if proposal.get('moved_events'):
                print(f"  Moved events: {len(proposal.get('moved_events'))}")
            
            # Print debug info
            debug = response.get("debug", {})
            if debug.get("extraction_time_ms"):
                print(f"  DSPy extraction time: {debug.get('extraction_time_ms')}ms")
            if debug.get("solve_time_ms"):
                print(f"  Solver time: {debug.get('solve_time_ms')}ms")
            if debug.get("total_time_ms"):
                print(f"  Total time: {debug.get('total_time_ms')}ms")
        else:
            print(f"✓ Status: {actual_status}")
            if response.get("relaxations"):
                print(f"  Relaxations provided: {len(response.get('relaxations'))}")
        
        print(f"✓ Explanation: {response.get('explanation', 'N/A')[:100]}...")
        return True
        
    except Exception as e:
        print(f"✗ Exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("="*80)
    print("END-TO-END ORCHESTRATOR TEST SUITE")
    print("="*80)
    
    # Load events
    example_file = Path(__file__).parent / "example_event_data.md"
    events = load_events_from_example(example_file)
    print(f"\nLoaded events:")
    for participant, event_list in events.items():
        print(f"  {participant}: {len(event_list)} events")
    
    results = []
    
    # Test 1: Basic meeting with all participants
    context = create_context(min_gap=0)
    results.append((
        "Basic meeting with all participants",
        run_test(
            name="Basic meeting with all participants",
            utterance="Find a 45-minute meeting with Sue and Danielle between December 1 and December 12.",
            events=events,
            context=context,
            expected_status="ok",
            validate_participants=["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
        )
    ))
    
    # Test 2: Meeting excluding requester
    results.append((
        "Meeting excluding requester",
        run_test(
            name="Meeting excluding requester",
            utterance="Find a 45-minute meeting between Sue and Danielle.",
            events=events,
            context=context,
            expected_status="ok",
            validate_participants=["sbrau@concord.org", "dkehoe@concord.org"]
        )
    ))
    
    # Test 3: Meeting with specific duration
    results.append((
        "Meeting with 30-minute duration",
        run_test(
            name="Meeting with 30-minute duration",
            utterance="Schedule a 30-minute meeting with Sue and Danielle.",
            events=events,
            context=context,
            expected_status="ok",
            validate_participants=["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
        )
    ))
    
    # Test 4: Meeting with "me" phrasing
    results.append((
        "Meeting with 'me' phrasing",
        run_test(
            name="Meeting with 'me' phrasing",
            utterance="I need a 45-minute meeting with Sue and Danielle.",
            events=events,
            context=context,
            expected_status="ok",
            validate_participants=["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
        )
    ))
    
    # Test 5: Meeting with exclusion phrase
    results.append((
        "Meeting with 'just' exclusion",
        run_test(
            name="Meeting with 'just' exclusion",
            utterance="Find a 45-minute meeting for just Sue and Danielle.",
            events=events,
            context=context,
            expected_status="ok",
            validate_participants=["sbrau@concord.org", "dkehoe@concord.org"]
        )
    ))
    
    # Test 6: Empty events (should still work)
    results.append((
        "Meeting with empty calendars",
        run_test(
            name="Meeting with empty calendars",
            utterance="Find a 45-minute meeting with Sue and Danielle.",
            events={"cdorsey@concord.org": [], "sbrau@concord.org": [], "dkehoe@concord.org": []},
            context=context,
            expected_status="ok",
            validate_participants=["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
        )
    ))
    
    # Test 7: Very short time window (might be UNSAT)
    narrow_context = create_context(min_gap=0)
    narrow_context["timeframe"] = {
        "from": "2025-12-05",
        "to": "2025-12-05",
        "tz": "America/New_York"
    }
    results.append((
        "Narrow time window (1 day)",
        run_test(
            name="Narrow time window (1 day)",
            utterance="Find a 2-hour meeting with Sue and Danielle on December 5.",
            events=events,
            context=narrow_context,
            expected_status="unsat",  # Expected to be UNSAT due to narrow window
            expected_min_proposals=0  # Allow 0 if UNSAT
        )
    ))
    
    # Test 8: Invalid utterance (should handle gracefully)
    results.append((
        "Invalid utterance handling",
        run_test(
            name="Invalid utterance handling",
            utterance="xyzabc123 nonsense",
            events=events,
            context=context,
            expected_status="ok",  # Should still try to extract
            expected_min_proposals=0  # Might not find valid proposals
        )
    ))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    print(f"\nPassed: {passed}/{total}")
    print()
    
    for name, success in results:
        status = "✓" if success else "✗"
        print(f"{status} {name}")
    
    print()
    if passed == total:
        print("🎉 All tests passed! Orchestrator is ready for Letta agent use.")
        return 0
    else:
        print("⚠️  Some tests failed. Review output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

