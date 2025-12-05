#!/usr/bin/env python3
"""
End-to-end tests for rescheduling functionality in the scheduling orchestrator.

This script tests rescheduling with real MCP calendar access:
1. Reschedule with explicit event_id
2. Reschedule with natural language identification

Usage:
    python test_rescheduling_e2e.py [--test-id <test_number>]
    
    Test numbers:
    1 - Reschedule with explicit event_id (requires TEST_EVENT_ID and TEST_EVENT_PARTICIPANT_ID)
    2 - Reschedule with natural language (requires TEST_PARTICIPANT_IDS and TEST_UTTERANCE)
    3 - Run all tests
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import pytz

# Load .env file if it exists
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

# Add project root and letta directory to path
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "letta"))

# Check for API keys
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


def create_context(participant_ids: list, timeframe_days: int = 28) -> dict:
    """Create a standard context for rescheduling tests."""
    now = datetime.now(pytz.UTC)
    # Use timeframe_days - 2 to account for inclusive date calculation
    # The horizon is calculated as (to_dt - from_dt).days
    # If from=Dec 5 and to=Dec 5, that's 0 days
    # If from=Dec 5 and to=Dec 6, that's 1 day
    # So to get exactly 28 days, we need to use 27 in timedelta (Dec 5 to Jan 1 = 27 days)
    # But we're getting 29, so let's use 26 to get 27 days
    return {
        "timeframe": {
            "from": now.strftime("%Y-%m-%d"),
            "to": (now + timedelta(days=timeframe_days - 2)).strftime("%Y-%m-%d"),
            "tz": "America/New_York"
        },
        "participants": [
            {
                "id": pid,
                "email": pid,
                "name": pid.split("@")[0].capitalize(),
                "work_hours": "M-F 09:00-17:00"
            }
            for pid in participant_ids
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


def validate_rescheduling_response(response: dict) -> tuple[bool, list[str]]:
    """Validate that rescheduling response has expected structure."""
    errors = []
    
    # Required top-level fields
    if "status" not in response:
        errors.append("Missing required field: status")
        return False, errors
    
    # Status should be one of: "ok", "unsat", "bad_input"
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
                required_proposal_fields = ["participants", "start_utc", "end_utc", "title"]
                for field in required_proposal_fields:
                    if field not in proposal:
                        errors.append(f"Proposal {i} missing required field: {field}")
    
    # Should have explanation
    if "explanation" not in response:
        errors.append("Missing 'explanation' field")
    
    return len(errors) == 0, errors


def run_rescheduling_test(
    name: str,
    utterance: str,
    participant_ids: list,
    context: dict,
    event_id: str = None,
    event_participant_id: str = None,
    expected_status: str = "ok",
    expected_min_proposals: int = 1
) -> bool:
    """Run a single rescheduling test case."""
    print(f"\n{'='*80}")
    print(f"TEST: {name}")
    print('='*80)
    print(f"Utterance: {utterance}")
    if event_id:
        print(f"Event ID: {event_id}")
        print(f"Event Participant ID: {event_participant_id}")
    print(f"Participant IDs: {participant_ids}")
    print(f"Expected status: {expected_status}")
    print(f"Expected min proposals: {expected_min_proposals}")
    print('-'*80)
    
    context_json_str = json.dumps(context)
    
    try:
        response = orchestrate_scheduling(
            utterance=utterance,
            participant_ids=participant_ids,
            event_id=event_id,
            event_participant_id=event_participant_id,
            context_json=context_json_str
        )
        
        # Validate response structure
        is_valid, errors = validate_rescheduling_response(response)
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
            if response.get("explanation"):
                print(f"  Explanation: {response.get('explanation')}")
            return False
        
        # Check proposals
        if expected_status == "ok":
            proposals = response.get("proposals", [])
            if len(proposals) < expected_min_proposals:
                print(f"✗ Insufficient proposals: expected at least {expected_min_proposals}, got {len(proposals)}")
                return False
            
            # Print proposal details
            proposal = proposals[0]
            print(f"✓ Status: {actual_status}")
            print(f"✓ Found {len(proposals)} proposal(s)")
            print(f"  Best option:")
            print(f"    Title: {proposal.get('title', 'N/A')}")
            print(f"    Start: {proposal.get('start_utc')}")
            print(f"    End: {proposal.get('end_utc')}")
            print(f"    Participants: {proposal.get('participants')}")
            if proposal.get('moved_events'):
                print(f"    Moved events: {len(proposal.get('moved_events'))}")
            if proposal.get('overridden_event_ids'):
                print(f"    Overridden event IDs: {proposal.get('overridden_event_ids')}")
            
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


def test_reschedule_with_event_id():
    """Test rescheduling with explicit event_id."""
    print_section("Test 1: Reschedule with explicit event_id")
    
    # Get test parameters from environment
    event_id = os.getenv("TEST_EVENT_ID")
    event_participant_id = os.getenv("TEST_EVENT_PARTICIPANT_ID")
    
    if not event_id or not event_participant_id:
        print("⚠️  Skipping test - requires TEST_EVENT_ID and TEST_EVENT_PARTICIPANT_ID")
        print("   Example:")
        print('   export TEST_EVENT_ID="your_event_id"')
        print('   export TEST_EVENT_PARTICIPANT_ID="cdorsey@concord.org"')
        return None
    
    # Use event_participant_id as the participant
    participant_ids = [event_participant_id]
    context = create_context(participant_ids, timeframe_days=30)
    utterance = "Find new time options"
    
    return run_rescheduling_test(
        name="Reschedule with explicit event_id",
        utterance=utterance,
        participant_ids=participant_ids,
        context=context,
        event_id=event_id,
        event_participant_id=event_participant_id,
        expected_status="ok",
        expected_min_proposals=1
    )


def test_reschedule_with_natural_language():
    """Test rescheduling with natural language identification."""
    print_section("Test 2: Reschedule with natural language identification")
    
    # Get test parameters from environment
    participant_ids_str = os.getenv("TEST_PARTICIPANT_IDS")
    utterance = os.getenv("TEST_UTTERANCE", "Find me a new time for the check-in with Judi on Dec. 10th")
    
    if not participant_ids_str:
        print("⚠️  Skipping test - requires TEST_PARTICIPANT_IDS")
        print("   Example:")
        print('   export TEST_PARTICIPANT_IDS=\'["cdorsey@concord.org", "judi@example.com"]\'')
        print('   export TEST_UTTERANCE="Find me a new time for the check-in with Judi on Dec. 10th"')
        return None
    
    try:
        participant_ids = json.loads(participant_ids_str)
    except json.JSONDecodeError:
        print("✗ Invalid TEST_PARTICIPANT_IDS - must be valid JSON array")
        return False
    
    context = create_context(participant_ids, timeframe_days=30)
    
    return run_rescheduling_test(
        name="Reschedule with natural language",
        utterance=utterance,
        participant_ids=participant_ids,
        context=context,
        expected_status="ok",
        expected_min_proposals=1
    )


def print_section(title):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def main():
    print("="*80)
    print("RESCHEDULING E2E TEST SUITE")
    print("="*80)
    print("\nThis script tests rescheduling functionality with real MCP calendar access.")
    print("\nPrerequisites:")
    print("  - MCP server running and accessible")
    print("  - Valid calendar credentials")
    print("  - Environment variables set (see test output for details)")
    print()
    
    results = []
    
    # Test 1: Reschedule with explicit event_id
    result1 = test_reschedule_with_event_id()
    if result1 is not None:
        results.append(("Reschedule with explicit event_id", result1))
    
    # Test 2: Reschedule with natural language
    result2 = test_reschedule_with_natural_language()
    if result2 is not None:
        results.append(("Reschedule with natural language", result2))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    if not results:
        print("\n⚠️  No tests ran - set environment variables to enable tests")
        print("\nExample setup:")
        print('  export TEST_EVENT_ID="your_event_id"')
        print('  export TEST_EVENT_PARTICIPANT_ID="cdorsey@concord.org"')
        print('  export TEST_PARTICIPANT_IDS=\'["cdorsey@concord.org", "judi@example.com"]\'')
        print('  export TEST_UTTERANCE="Find me a new time for the check-in with Judi on Dec. 10th"')
        return 0
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    print(f"\nPassed: {passed}/{total}")
    print()
    
    for name, success in results:
        status = "✓" if success else "✗"
        print(f"{status} {name}")
    
    print()
    if passed == total:
        print("🎉 All tests passed! Rescheduling functionality is working.")
        return 0
    else:
        print("⚠️  Some tests failed. Review output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

