#!/usr/bin/env python3
"""
Test script for the orchestrate_scheduling tool.

This script allows you to test the scheduling tool directly and see full error messages,
tracebacks, and debug information that might be truncated in Letta's agent responses.
"""

import os
import sys
import json
from pathlib import Path

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


def test_basic():
    """Test with minimal valid input."""
    print("=" * 70)
    print("Test 1: Basic scheduling request")
    print("=" * 70)
    
    utterance = "Find 30 minutes with Alex next Tuesday"
    
    events_by_participant = json.dumps({
        "alex": [
            {
                "id": "evt1",
                "title": "Existing Meeting",
                "start": "2025-11-25T10:00:00Z",
                "end": "2025-11-25T11:00:00Z",
                "locked": False,
                "protected": False,
                "flexible": True
            }
        ]
    })
    
    context_json = json.dumps({
        "timeframe": {
            "from": "2025-11-24",
            "to": "2025-11-28",
            "tz": "America/New_York"
        },
        "participants": [
            {
                "id": "alex",
                "email": "alex@example.com",
                "work_hours": "M-F 09:00-17:00"
            }
        ]
    })
    
    print(f"Utterance: {utterance}")
    print(f"\nEvents: {events_by_participant}")
    print(f"\nContext: {context_json}")
    print("\n" + "-" * 70)
    print("Calling orchestrate_scheduling...")
    print("-" * 70 + "\n")
    
    try:
        result = orchestrate_scheduling(utterance, events_by_participant, context_json)
        
        print("RESULT:")
        print(json.dumps(result, indent=2))
        
        if result.get("status") != "ok":
            print("\n" + "=" * 70)
            print("ERROR DETAILS:")
            print("=" * 70)
            if "error_message" in result:
                print(f"Error Message: {result['error_message']}")
            if "error_traceback" in result:
                print(f"\nTraceback:\n{result['error_traceback']}")
            if "debug" in result:
                print(f"\nDebug Info: {json.dumps(result['debug'], indent=2)}")
        
    except Exception as e:
        print(f"\nEXCEPTION RAISED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


def test_with_custom_input():
    """Test with custom input from command line or environment."""
    print("\n" + "=" * 70)
    print("Test 2: Custom input")
    print("=" * 70)
    
    # Get input from environment or use defaults
    utterance = os.getenv("TEST_UTTERANCE", "Find 45 minutes with team next week")
    
    events_str = os.getenv("TEST_EVENTS", json.dumps({
        "team": []
    }))
    
    context_str = os.getenv("TEST_CONTEXT", json.dumps({
        "timeframe": {
            "from": "2025-11-24",
            "to": "2025-12-01",
            "tz": "America/New_York"
        }
    }))
    
    print(f"Utterance: {utterance}")
    print(f"\nEvents: {events_str}")
    print(f"\nContext: {context_str}")
    print("\n" + "-" * 70)
    print("Calling orchestrate_scheduling...")
    print("-" * 70 + "\n")
    
    try:
        result = orchestrate_scheduling(utterance, events_str, context_str)
        
        print("RESULT:")
        print(json.dumps(result, indent=2))
        
        if result.get("status") != "ok":
            print("\n" + "=" * 70)
            print("ERROR DETAILS:")
            print("=" * 70)
            if "error_message" in result:
                print(f"Error Message: {result['error_message']}")
            if "error_traceback" in result:
                print(f"\nTraceback:\n{result['error_traceback']}")
            if "debug" in result:
                print(f"\nDebug Info: {json.dumps(result['debug'], indent=2)}")
        
    except Exception as e:
        print(f"\nEXCEPTION RAISED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Run tests."""
    print("\n" + "=" * 70)
    print("Scheduling Orchestrator Tool - Direct Test")
    print("=" * 70)
    print("\nThis script tests the orchestrate_scheduling tool directly,")
    print("showing full error messages and tracebacks that might be")
    print("truncated when called through Letta.\n")
    
    # Run basic test
    test_basic()
    
    # Run custom test if requested
    if len(sys.argv) > 1 and sys.argv[1] == "--custom":
        test_with_custom_input()
    
    print("\n" + "=" * 70)
    print("Testing Complete")
    print("=" * 70)
    print("\nTo test with custom input, set environment variables:")
    print("  TEST_UTTERANCE='your request'")
    print("  TEST_EVENTS='{...}'")
    print("  TEST_CONTEXT='{...}'")
    print("\nOr run with --custom flag to use defaults\n")


if __name__ == "__main__":
    main()

