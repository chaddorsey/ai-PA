#!/usr/bin/env python3
"""
Test work hours handling - verify default 9-5 Eastern and individual settings work correctly.
"""

import json
import sys
import os
from pathlib import Path

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
from test_e2e_orchestrator import load_events_from_example


def test_default_work_hours():
    """Test that default 9-5 Eastern work hours are applied"""
    print("="*80)
    print("TEST 1: Default 9-5 Eastern Work Hours")
    print("="*80)
    
    events = load_events_from_example(Path(__file__).parent / "example_event_data.md")
    
    # Context with NO work_hours specified - should default to 9-5 Eastern
    context_json = {
        "timeframe": {
            "from": "2025-12-01",
            "to": "2025-12-12",
            "tz": "America/New_York"
        },
        "requester_id": "cdorsey@concord.org",
        "participants": [
            {
                "id": "cdorsey@concord.org",
                "email": "cdorsey@concord.org",
                "name": "Chad"
                # No work_hours - should default to 9-5 Eastern
            },
            {
                "id": "sbrau@concord.org",
                "email": "sbrau@concord.org",
                "name": "Sue"
                # No work_hours - should default to 9-5 Eastern
            }
        ],
        "policy": {
            "hard": {
                "min_gap_min": 0
            }
        }
    }
    
    utterance = "Find a 45-minute meeting with Sue between December 1 and 12."
    
    print(f"Utterance: {utterance}")
    print("Participants: Chad (no work_hours), Sue (no work_hours)")
    print("Expected: Both should default to 9-5 Eastern")
    print()
    
    result = orchestrate_scheduling(
        utterance=utterance,
        events_by_participant=json.dumps(events),
        context_json=json.dumps(context_json)
    )
    
    if result.get("status") == "ok" and result.get("proposals"):
        proposal = result["proposals"][0]
        start_utc = proposal.get("start_utc")
        
        # Convert to ET to verify it's within 9-5 Eastern
        from dateutil import parser
        from dateutil import tz
        utc_dt = parser.parse(start_utc)
        et = tz.gettz("America/New_York")
        et_dt = utc_dt.astimezone(et)
        
        print(f"✓ Found meeting slot:")
        print(f"  UTC: {start_utc}")
        print(f"  ET:  {et_dt.strftime('%A, %B %d at %I:%M %p %Z')}")
        print(f"  Day: {et_dt.strftime('%A')}, Hour: {et_dt.hour}")
        
        is_weekday = et_dt.weekday() < 5
        is_9_to_5 = 9 <= et_dt.hour < 17 or (et_dt.hour == 17 and et_dt.minute == 0)
        
        if is_weekday and is_9_to_5:
            print(f"✓ Within default 9-5 Eastern work hours!")
            return True
        else:
            print(f"✗ NOT within 9-5 Eastern work hours!")
            return False
    else:
        print(f"✗ No proposal found (status: {result.get('status')})")
        return False


def test_individual_work_hours():
    """Test that individual work hours are respected"""
    print("\n" + "="*80)
    print("TEST 2: Individual Work Hours")
    print("="*80)
    
    events = load_events_from_example(Path(__file__).parent / "example_event_data.md")
    
    # Context with different work hours for Sue
    context_json = {
        "timeframe": {
            "from": "2025-12-01",
            "to": "2025-12-12",
            "tz": "America/New_York"
        },
        "requester_id": "cdorsey@concord.org",
        "participants": [
            {
                "id": "cdorsey@concord.org",
                "email": "cdorsey@concord.org",
                "name": "Chad"
                # Default 9-5 Eastern
            },
            {
                "id": "sbrau@concord.org",
                "email": "sbrau@concord.org",
                "name": "Sue",
                "work_hours": "M-F 10:00-18:00"  # 10 AM - 6 PM Eastern
            }
        ],
        "policy": {
            "hard": {
                "min_gap_min": 0
            }
        }
    }
    
    utterance = "Find a 45-minute meeting with Sue between December 1 and 12."
    
    print(f"Utterance: {utterance}")
    print("Participants:")
    print("  Chad: Default 9-5 Eastern")
    print("  Sue: 10 AM - 6 PM Eastern (individual)")
    print("Expected: Meeting must be within 10 AM - 5 PM (intersection of both work hours)")
    print()
    
    result = orchestrate_scheduling(
        utterance=utterance,
        events_by_participant=json.dumps(events),
        context_json=json.dumps(context_json)
    )
    
    if result.get("status") == "ok" and result.get("proposals"):
        proposal = result["proposals"][0]
        start_utc = proposal.get("start_utc")
        
        from dateutil import parser
        from dateutil import tz
        utc_dt = parser.parse(start_utc)
        et = tz.gettz("America/New_York")
        et_dt = utc_dt.astimezone(et)
        
        print(f"✓ Found meeting slot:")
        print(f"  UTC: {start_utc}")
        print(f"  ET:  {et_dt.strftime('%A, %B %d at %I:%M %p %Z')}")
        print(f"  Hour: {et_dt.hour}")
        
        # Should be within intersection: 10 AM - 5 PM (since meeting is 45 min and Chad's day ends at 5)
        # Actually, meeting can start at 4:15 PM (45 min meeting ends at 5 PM)
        is_weekday = et_dt.weekday() < 5
        # Chad: 9-17 (5 PM), Sue: 10-18 (6 PM), intersection: 10-17, with 45 min meeting: start by 16:15
        within_chad = 9 <= et_dt.hour < 17 or (et_dt.hour == 16 and et_dt.minute <= 15)
        within_sue = 10 <= et_dt.hour < 18 or (et_dt.hour == 17 and et_dt.minute <= 45)
        is_within_intersection = is_weekday and (10 <= et_dt.hour < 17 or (et_dt.hour == 16 and et_dt.minute <= 15))
        
        if is_within_intersection:
            print(f"✓ Within intersection of work hours (10 AM - 4:15 PM)!")
            return True
        else:
            print(f"✗ NOT within intersection of work hours!")
            print(f"  Within Chad (9-5): {within_chad}")
            print(f"  Within Sue (10-6): {within_sue}")
            return False
    else:
        print(f"✗ No proposal found (status: {result.get('status')})")
        return False


def main():
    print("="*80)
    print("WORK HOURS TEST SUITE")
    print("="*80)
    print()
    
    test1 = test_default_work_hours()
    test2 = test_individual_work_hours()
    
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Default 9-5 Eastern: {'✓ PASSED' if test1 else '✗ FAILED'}")
    print(f"Individual work hours: {'✓ PASSED' if test2 else '✗ FAILED'}")
    
    return 0 if (test1 and test2) else 1


if __name__ == "__main__":
    sys.exit(main())

