#!/usr/bin/env python3
"""
Test script for rescheduling functionality in the scheduling orchestrator.

This script tests the rescheduling features:
1. Rescheduling with explicit event_id
2. Rescheduling with natural language identification
3. Event detail extraction
4. Event matching from natural language

Usage:
    python test_rescheduling.py [--test-id <test_number>]
    
    Test numbers:
    1 - Reschedule with explicit event_id
    2 - Reschedule with natural language identification
    3 - Test event detail extraction
    4 - Test event matching
    5 - Run all tests
"""

import os
import sys
import json
import traceback
from pathlib import Path
from datetime import datetime, timedelta
import pytz

# Add letta directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Load .env if available
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

from scheduling_orchestrator.orchestrate_scheduling import orchestrate_scheduling
from scheduling_orchestrator.event_extractor import extract_event_details_for_rescheduling
from scheduling_orchestrator.event_matcher import identify_event_from_natural_language


def print_section(title):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def print_result(result):
    """Print formatted result."""
    print("\n" + "-" * 70)
    print("RESULT:")
    print("-" * 70)
    print(json.dumps(result, indent=2))
    
    if result.get("status") != "ok":
        print("\n" + "=" * 70)
        print("ERROR DETAILS:")
        print("=" * 70)
        if "error_message" in result:
            print(f"Error Message: {result['error_message']}")
        if "explanation" in result:
            print(f"Explanation: {result['explanation']}")
        if "error_traceback" in result:
            print(f"\nTraceback:\n{result['error_traceback']}")
        if "debug" in result:
            print(f"\nDebug Info: {json.dumps(result['debug'], indent=2)}")


def test_reschedule_with_event_id():
    """Test rescheduling with explicit event_id."""
    print_section("Test 1: Reschedule with explicit event_id")
    
    # Get test parameters from environment or use defaults
    event_id = os.getenv("TEST_EVENT_ID", None)
    event_participant_id = os.getenv("TEST_EVENT_PARTICIPANT_ID", None)
    participant_ids_str = os.getenv("TEST_PARTICIPANT_IDS", None)
    
    if not event_id or not event_participant_id:
        print("⚠️  Skipping test - requires TEST_EVENT_ID and TEST_EVENT_PARTICIPANT_ID")
        print("   Set environment variables to test with real event IDs")
        return
    
    # Parse participant IDs
    if participant_ids_str:
        participant_ids = json.loads(participant_ids_str)
    else:
        # Default: use event_participant_id
        participant_ids = [event_participant_id]
    
    # Build context
    now = datetime.now(pytz.UTC)
    timeframe = {
        "from": now.strftime("%Y-%m-%d"),
        "to": (now + timedelta(days=30)).strftime("%Y-%m-%d"),
        "tz": "America/New_York"
    }
    
    context_json = json.dumps({
        "timeframe": timeframe,
        "participants": [
            {
                "id": pid,
                "email": pid,
                "work_hours": "M-F 09:00-17:00"
            }
            for pid in participant_ids
        ]
    })
    
    utterance = "Find new time options"
    
    print(f"Event ID: {event_id}")
    print(f"Event Participant ID: {event_participant_id}")
    print(f"Participant IDs: {participant_ids}")
    print(f"Utterance: {utterance}")
    print(f"Timeframe: {timeframe}")
    
    try:
        result = orchestrate_scheduling(
            utterance=utterance,
            participant_ids=participant_ids,
            event_id=event_id,
            event_participant_id=event_participant_id,
            context_json=context_json
        )
        
        print_result(result)
        
        # Check if we got proposals
        if result.get("status") == "ok":
            proposals = result.get("proposals", [])
            print(f"\n✓ Success! Found {len(proposals)} proposal(s)")
            if proposals:
                print(f"  Best option: {proposals[0].get('start_utc')} - {proposals[0].get('end_utc')}")
        else:
            print(f"\n✗ Failed with status: {result.get('status')}")
            
    except Exception as e:
        print(f"\n✗ EXCEPTION: {type(e).__name__}: {e}")
        traceback.print_exc()


def test_reschedule_with_natural_language():
    """Test rescheduling with natural language identification."""
    print_section("Test 2: Reschedule with natural language identification")
    
    # Get test parameters
    participant_ids_str = os.getenv("TEST_PARTICIPANT_IDS", None)
    utterance = os.getenv("TEST_UTTERANCE", "Find me a new time for the check-in with Judi on Dec. 10th")
    
    if not participant_ids_str:
        print("⚠️  Skipping test - requires TEST_PARTICIPANT_IDS")
        print("   Example: TEST_PARTICIPANT_IDS='[\"cdorsey@concord.org\", \"judi@example.com\"]'")
        return
    
    participant_ids = json.loads(participant_ids_str)
    
    # Build context
    now = datetime.now(pytz.UTC)
    timeframe = {
        "from": now.strftime("%Y-%m-%d"),
        "to": (now + timedelta(days=30)).strftime("%Y-%m-%d"),
        "tz": "America/New_York"
    }
    
    context_json = json.dumps({
        "timeframe": timeframe,
        "participants": [
            {
                "id": pid,
                "email": pid,
                "name": pid.split("@")[0].capitalize(),  # Extract name from email
                "work_hours": "M-F 09:00-17:00"
            }
            for pid in participant_ids
        ]
    })
    
    print(f"Participant IDs: {participant_ids}")
    print(f"Utterance: {utterance}")
    print(f"Timeframe: {timeframe}")
    
    try:
        result = orchestrate_scheduling(
            utterance=utterance,
            participant_ids=participant_ids,
            context_json=context_json
        )
        
        print_result(result)
        
        # Check if we got proposals
        if result.get("status") == "ok":
            proposals = result.get("proposals", [])
            print(f"\n✓ Success! Found {len(proposals)} proposal(s)")
            if proposals:
                print(f"  Best option: {proposals[0].get('start_utc')} - {proposals[0].get('end_utc')}")
        else:
            print(f"\n✗ Failed with status: {result.get('status')}")
            
    except Exception as e:
        print(f"\n✗ EXCEPTION: {type(e).__name__}: {e}")
        traceback.print_exc()


def test_event_extraction():
    """Test event detail extraction."""
    print_section("Test 3: Event detail extraction")
    
    # Create a mock event
    now = datetime.now(pytz.UTC)
    start_dt = now + timedelta(days=1, hours=10)
    end_dt = start_dt + timedelta(minutes=45)
    
    mock_event = {
        "id": "test_event_123",
        "summary": "Test Meeting",
        "start": {
            "dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S%z")
        },
        "end": {
            "dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S%z")
        },
        "locked": False,
        "protected": False,
        "flexible": True,
        "internal_only": True,
        "attendees_list": ["alex@example.com", "priya@example.com"],
        "location": "Conference Room A"
    }
    
    event_owner_id = "cdorsey@concord.org"
    
    print(f"Mock Event: {json.dumps(mock_event, indent=2)}")
    print(f"Event Owner: {event_owner_id}")
    
    try:
        details = extract_event_details_for_rescheduling(
            event=mock_event,
            event_owner_id=event_owner_id
        )
        
        print("\n✓ Extraction successful!")
        print(f"  Event ID: {details['event_id']}")
        print(f"  Title: {details['title']}")
        print(f"  Duration: {details['duration_minutes']} minutes")
        print(f"  Participants: {details['participants']}")
        print(f"  Location: {details['location']}")
        print(f"  Current Start: {details['current_start_utc']}")
        print(f"  Current End: {details['current_end_utc']}")
        print(f"  Internal Only: {details['internal_only']}")
        
    except Exception as e:
        print(f"\n✗ EXCEPTION: {type(e).__name__}: {e}")
        traceback.print_exc()


def test_event_matching():
    """Test event matching from natural language."""
    print_section("Test 4: Event matching from natural language")
    
    # Create mock events
    now = datetime.now(pytz.UTC)
    
    events_by_participant = {
        "cdorsey@concord.org": [
            {
                "id": "evt1",
                "summary": "Weekly Check-in with Judi",
                "start": {
                    "dateTime": (now + timedelta(days=5, hours=14)).strftime("%Y-%m-%dT%H:%M:%S%z")
                },
                "end": {
                    "dateTime": (now + timedelta(days=5, hours=14, minutes=30)).strftime("%Y-%m-%dT%H:%M:%S%z")
                },
                "attendees_list": ["judi@example.com"],
                "internal_only": True
            },
            {
                "id": "evt2",
                "summary": "Team Standup",
                "start": {
                    "dateTime": (now + timedelta(days=3, hours=10)).strftime("%Y-%m-%dT%H:%M:%S%z")
                },
                "end": {
                    "dateTime": (now + timedelta(days=3, hours=10, minutes=30)).strftime("%Y-%m-%dT%H:%M:%S%z")
                },
                "attendees_list": [],
                "internal_only": True
            }
        ]
    }
    
    event_identifiers = {
        "participant_names": ["Judi"],
        "dates": ["Dec. 10th"],
        "times": ["afternoon"],
        "titles": ["check-in"]
    }
    
    context_json = {
        "participants": [
            {
                "id": "cdorsey@concord.org",
                "email": "cdorsey@concord.org",
                "name": "Chris"
            },
            {
                "id": "judi@example.com",
                "email": "judi@example.com",
                "name": "Judi"
            }
        ]
    }
    
    print(f"Event Identifiers: {json.dumps(event_identifiers, indent=2)}")
    print(f"Events: {len(events_by_participant['cdorsey@concord.org'])} events")
    
    try:
        match_result = identify_event_from_natural_language(
            event_identifiers=event_identifiers,
            events_by_participant=events_by_participant,
            context_json=context_json
        )
        
        if match_result:
            matched_event, matched_participant = match_result
            print("\n✓ Match found!")
            print(f"  Event: {matched_event.get('summary', '')}")
            print(f"  ID: {matched_event.get('id', '')}")
            print(f"  Participant: {matched_participant}")
        else:
            print("\n✗ No match found")
            
    except Exception as e:
        print(f"\n✗ EXCEPTION: {type(e).__name__}: {e}")
        traceback.print_exc()


def run_all_tests():
    """Run all tests."""
    print_section("Running All Rescheduling Tests")
    
    tests = [
        ("Event Extraction", test_event_extraction),
        ("Event Matching", test_event_matching),
        ("Reschedule with Natural Language", test_reschedule_with_natural_language),
        ("Reschedule with Event ID", test_reschedule_with_event_id),
    ]
    
    passed = 0
    skipped = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\n{'='*70}")
        print(f"Running: {test_name}")
        print(f"{'='*70}")
        try:
            test_func()
            passed += 1
        except Exception as e:
            if "Skipping" in str(e) or "requires" in str(e).lower():
                skipped += 1
            else:
                print(f"  ✗ Error: {type(e).__name__}: {e}")
                failed += 1
    
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Passed: {passed}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")
    print("=" * 70)


def main():
    """Main entry point."""
    print("\n" + "=" * 70)
    print("Rescheduling Functionality Test Suite")
    print("=" * 70)
    print("\nThis script tests the rescheduling features of the scheduling orchestrator.")
    print("\nAvailable tests:")
    print("  1 - Reschedule with explicit event_id")
    print("  2 - Reschedule with natural language identification")
    print("  3 - Test event detail extraction")
    print("  4 - Test event matching")
    print("  5 - Run all tests")
    print("\nEnvironment variables for testing:")
    print("  TEST_EVENT_ID - Event ID to reschedule")
    print("  TEST_EVENT_PARTICIPANT_ID - Participant ID whose calendar contains the event")
    print("  TEST_PARTICIPANT_IDS - JSON array of participant IDs")
    print("  TEST_UTTERANCE - Natural language rescheduling request")
    
    if len(sys.argv) > 1:
        test_id = sys.argv[1]
        if test_id == "1":
            test_reschedule_with_event_id()
        elif test_id == "2":
            test_reschedule_with_natural_language()
        elif test_id == "3":
            test_event_extraction()
        elif test_id == "4":
            test_event_matching()
        elif test_id == "5" or test_id == "--all":
            run_all_tests()
        else:
            print(f"\nUnknown test ID: {test_id}")
            print("Use 1-5 or --all")
    else:
        # Run all tests by default
        run_all_tests()


if __name__ == "__main__":
    main()

