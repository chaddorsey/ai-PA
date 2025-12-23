#!/usr/bin/env python3
"""
Test script for move validation functionality.

Tests the move validation implementation to ensure:
1. Internal-only constraint enforcement
2. Multi-participant conflict validation
3. Error handling
"""

import sys
from datetime import datetime, timedelta
import pytz
from typing import Dict, Any, List

# Add parent directory to path for imports
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scheduling_orchestrator.move_validator import validate_move_for_all_participants, validate_moved_event_dict
from scheduling_orchestrator.slot_indexer import SlotIndexer
from scheduling_orchestrator.normalizer import normalize_events


def create_test_normalized_data() -> Dict[str, Any]:
    """Create test normalized data with sample events."""
    # Create a simple timeframe
    from_date = datetime(2025, 1, 15, 0, 0, 0, tzinfo=pytz.UTC)
    to_date = datetime(2025, 1, 22, 0, 0, 0, tzinfo=pytz.UTC)
    
    slot_indexer = SlotIndexer(from_date, to_date)
    
    # Create test events
    events_by_participant = {
        "alice@example.com": [
            {
                "id": "evt1",
                "title": "Alice's Meeting",
                "start": "2025-01-15T10:00:00Z",
                "end": "2025-01-15T11:00:00Z",
                "locked": False,
                "protected": False,
                "flexible": True,
                "internal_only": True,
                "attendees": ["bob@example.com"]
            },
            {
                "id": "evt2",
                "title": "Alice's Other Meeting",
                "start": "2025-01-15T14:00:00Z",
                "end": "2025-01-15T15:00:00Z",
                "locked": False,
                "protected": False,
                "flexible": True,
                "internal_only": True,
                "attendees": []
            }
        ],
        "bob@example.com": [
            {
                "id": "evt3",
                "title": "Bob's Meeting",
                "start": "2025-01-15T16:00:00Z",
                "end": "2025-01-15T17:00:00Z",
                "locked": False,
                "protected": False,
                "flexible": True,
                "internal_only": True,
                "attendees": []
            }
        ]
    }
    
    context_json = {
        "timeframe": {
            "from": "2025-01-15",
            "to": "2025-01-21",
            "tz": "UTC"
        },
        "participants": [
            {"id": "alice@example.com", "email": "alice@example.com", "work_hours": "M-F 09:00-17:00"},
            {"id": "bob@example.com", "email": "bob@example.com", "work_hours": "M-F 09:00-17:00"}
        ]
    }
    
    normalized_data = normalize_events(events_by_participant, context_json)
    return normalized_data


def test_validation_no_conflict():
    """Test validation when move doesn't conflict."""
    print("Test 1: Validation with no conflict")
    normalized_data = create_test_normalized_data()
    slot_indexer = normalized_data["slot_indexer"]
    
    # Move evt1 to a time that doesn't conflict
    moved_event = {
        "owner": "alice@example.com",
        "event_id": "evt1",
        "new_start": "2025-01-15T12:00:00Z",
        "new_end": "2025-01-15T13:00:00Z"
    }
    
    is_valid, error_msg = validate_moved_event_dict(
        moved_event,
        normalized_data,
        slot_indexer
    )
    
    assert is_valid, f"Expected valid move, got error: {error_msg}"
    print("  ✓ Pass: No conflict detected correctly")
    return True


def test_validation_with_conflict():
    """Test validation when move conflicts with another event."""
    print("Test 2: Validation with conflict")
    normalized_data = create_test_normalized_data()
    slot_indexer = normalized_data["slot_indexer"]
    
    # Move evt1 to conflict with evt2 (Alice's other meeting)
    moved_event = {
        "owner": "alice@example.com",
        "event_id": "evt1",
        "new_start": "2025-01-15T14:00:00Z",
        "new_end": "2025-01-15T15:00:00Z"
    }
    
    is_valid, error_msg = validate_moved_event_dict(
        moved_event,
        normalized_data,
        slot_indexer
    )
    
    assert not is_valid, "Expected invalid move due to conflict"
    assert "conflicts" in error_msg.lower() or "conflict" in error_msg.lower(), f"Error message should mention conflict: {error_msg}"
    print(f"  ✓ Pass: Conflict detected correctly: {error_msg}")
    return True


def test_validation_multi_participant():
    """Test validation with multi-participant event."""
    print("Test 3: Multi-participant validation")
    normalized_data = create_test_normalized_data()
    slot_indexer = normalized_data["slot_indexer"]
    
    # evt1 has alice and bob as participants
    # Move it to conflict with bob's meeting
    moved_event = {
        "owner": "alice@example.com",
        "event_id": "evt1",
        "new_start": "2025-01-15T16:00:00Z",
        "new_end": "2025-01-15T17:00:00Z"
    }
    
    is_valid, error_msg = validate_moved_event_dict(
        moved_event,
        normalized_data,
        slot_indexer
    )
    
    assert not is_valid, "Expected invalid move due to conflict with bob's calendar"
    assert "bob@example.com" in error_msg, f"Error should mention bob: {error_msg}"
    print(f"  ✓ Pass: Multi-participant conflict detected: {error_msg}")
    return True


def test_validation_missing_participant():
    """Test validation when participant calendar is missing."""
    print("Test 4: Missing participant calendar")
    normalized_data = create_test_normalized_data()
    slot_indexer = normalized_data["slot_indexer"]
    
    # Create a moved event with a participant not in normalized_data
    moved_event = {
        "owner": "alice@example.com",
        "event_id": "evt1",
        "new_start": "2025-01-15T12:00:00Z",
        "new_end": "2025-01-15T13:00:00Z"
    }
    
    # Modify event_participants to include a missing participant
    event_key = (moved_event["owner"], moved_event["event_id"])
    normalized_data["event_participants"][event_key] = ["alice@example.com", "charlie@example.com"]
    
    is_valid, error_msg = validate_moved_event_dict(
        moved_event,
        normalized_data,
        slot_indexer
    )
    
    assert not is_valid, "Expected invalid move due to missing participant calendar"
    assert "not available" in error_msg.lower() or "missing" in error_msg.lower(), f"Error should mention missing calendar: {error_msg}"
    print(f"  ✓ Pass: Missing participant detected: {error_msg}")
    return True


def test_event_participants_mapping():
    """Test that event_participants mapping is created correctly."""
    print("Test 5: event_participants mapping")
    normalized_data = create_test_normalized_data()
    
    # Check that event_participants exists
    assert "event_participants" in normalized_data, "event_participants should be in normalized_data"
    
    # Check evt1 has both alice and bob
    event_key = ("alice@example.com", "evt1")
    participants = normalized_data["event_participants"].get(event_key, [])
    
    assert "alice@example.com" in participants, "Owner should be in participants"
    assert "bob@example.com" in participants, "Attendee should be in participants"
    print(f"  ✓ Pass: event_participants mapping correct: {participants}")
    return True


def test_attendees_storage():
    """Test that attendees are stored in event_metadata."""
    print("Test 6: Attendees storage in event_metadata")
    normalized_data = create_test_normalized_data()
    
    event_key = ("alice@example.com", "evt1")
    event_meta = normalized_data["event_metadata"].get(event_key, {})
    
    assert "attendees" in event_meta, "attendees should be in event_metadata"
    assert event_meta["attendees"] == ["bob@example.com"], f"Expected ['bob@example.com'], got {event_meta['attendees']}"
    print(f"  ✓ Pass: Attendees stored correctly: {event_meta['attendees']}")
    return True


def test_validation_exclude_all_participant_instances():
    """
    Test that validation excludes ALL participant instances of the moved event.
    
    This test reproduces the bug where an event with a participant not in the
    original request (e.g., dkehoe@concord.org) was incorrectly flagged as a conflict
    because only the owner's event_key was excluded, not all participant instances.
    
    Bug scenario:
    - Event "Development Weekly Check In" has participants: cdorsey, kbrown, lbondaryk, dkehoe
    - Original request only includes: cdorsey, kbrown, lbondaryk
    - When moving the event, validation should exclude the event for ALL participants
    - Before fix: Only excluded (cdorsey, event_id), so dkehoe's instance was treated as conflict
    - After fix: Excludes (cdorsey, event_id), (kbrown, event_id), (lbondaryk, event_id), (dkehoe, event_id)
    """
    print("Test 7: Exclude all participant instances of moved event")
    
    # Create test data with an event that has multiple participants
    # One participant (charlie) is NOT in the original request
    from_date = datetime(2025, 1, 15, 0, 0, 0, tzinfo=pytz.UTC)
    to_date = datetime(2025, 1, 22, 0, 0, 0, tzinfo=pytz.UTC)
    slot_indexer = SlotIndexer(from_date, to_date)
    
    # Create events: alice and bob are in the original request, charlie is not
    # This mimics the scenario: cdorsey/kbrown/lbondaryk in request, dkehoe not in request
    events_by_participant = {
        "alice@example.com": [
            {
                "id": "evt_shared",
                "title": "Development Weekly Check In",
                "start": "2025-01-15T10:00:00Z",
                "end": "2025-01-15T11:00:00Z",
                "locked": False,
                "protected": False,
                "flexible": True,
                "internal_only": True,
                "attendees": ["bob@example.com", "charlie@example.com"]  # charlie not in original request
            }
        ],
        "bob@example.com": [
            {
                "id": "evt_shared",
                "title": "Development Weekly Check In",
                "start": "2025-01-15T10:00:00Z",
                "end": "2025-01-15T11:00:00Z",
                "locked": False,
                "protected": False,
                "flexible": True,
                "internal_only": True,
                "attendees": ["alice@example.com", "charlie@example.com"]
            }
        ],
        "charlie@example.com": [
            {
                "id": "evt_shared",
                "title": "Development Weekly Check In",
                "start": "2025-01-15T10:00:00Z",
                "end": "2025-01-15T11:00:00Z",
                "locked": False,
                "protected": False,
                "flexible": True,
                "internal_only": True,
                "attendees": ["alice@example.com", "bob@example.com"]
            }
        ]
    }
    
    context_json = {
        "timeframe": {
            "from": "2025-01-15",
            "to": "2025-01-21",
            "tz": "UTC"
        },
        "participants": [
            {"id": "alice@example.com", "email": "alice@example.com", "work_hours": "M-F 09:00-17:00"},
            {"id": "bob@example.com", "email": "bob@example.com", "work_hours": "M-F 09:00-17:00"}
            # Note: charlie@example.com is NOT in the original request (like dkehoe@concord.org)
        ]
    }
    
    normalized_data = normalize_events(events_by_participant, context_json)
    
    # Verify charlie's calendar is in normalized_data (it should be, since we provided events)
    assert "charlie@example.com" in normalized_data["busy_slots"], "charlie's calendar should be in normalized_data"
    
    # Move the event to a new time that doesn't conflict with any other events
    # The move should be valid because we're moving to an empty slot
    moved_event = {
        "owner": "alice@example.com",
        "event_id": "evt_shared",
        "new_start": "2025-01-15T12:00:00Z",  # Move to 12:00 (empty slot)
        "new_end": "2025-01-15T13:00:00Z"
    }
    
    # This should be valid - the event should be excluded for ALL participants
    # (alice, bob, and charlie), not just the owner (alice)
    # Before the fix, this would fail because charlie's instance wasn't excluded
    is_valid, error_msg = validate_moved_event_dict(
        moved_event,
        normalized_data,
        slot_indexer
    )
    
    if not is_valid:
        print(f"  ✗ Fail: Move should be valid but was rejected: {error_msg}")
        print(f"    This indicates the bug: charlie's instance of the event was not excluded")
        print(f"    Error suggests conflict with 'Development Weekly Check In' for charlie")
        return False
    
    print("  ✓ Pass: All participant instances correctly excluded - move validated successfully")
    print("    (This confirms the fix: charlie's instance was properly excluded)")
    return True


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Move Validation Tests")
    print("=" * 60)
    print()
    
    tests = [
        test_event_participants_mapping,
        test_attendees_storage,
        test_validation_no_conflict,
        test_validation_with_conflict,
        test_validation_multi_participant,
        test_validation_missing_participant,
        test_validation_exclude_all_participant_instances,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ Fail: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ Error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        print()
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

