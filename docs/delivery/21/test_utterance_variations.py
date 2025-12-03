#!/usr/bin/env python3
"""
Test orchestrator with various utterance phrasings to verify "me" and "with" handling.
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


def test_utterance(utterance: str, expected_participants: list):
    """Test a single utterance and verify participants match expected"""
    print(f"\n{'='*80}")
    print(f"Testing utterance: {utterance}")
    print(f"Expected participants: {expected_participants}")
    print('-'*80)
    
    # Load events
    example_file = Path(__file__).parent / "example_event_data.md"
    events_by_participant = load_events_from_example(example_file)
    
    context_json = {
        "timeframe": {
            "from": "2025-12-01",
            "to": "2025-12-12",
            "tz": "America/New_York"
        },
        "requester_id": "cdorsey@concord.org",  # Explicitly set requester
        "participants": [
            {
                "id": "cdorsey@concord.org",
                "email": "cdorsey@concord.org",
                "name": "Chad",
                "work_hours": "M-F 09:00-17:30"
            },
            {
                "id": "sbrau@concord.org",
                "email": "sbrau@concord.org",
                "name": "Sue",
                "work_hours": "M-F 09:00-17:30"
            },
            {
                "id": "dkehoe@concord.org",
                "email": "dkehoe@concord.org",
                "name": "Danielle",
                "work_hours": "M-F 09:00-17:30"
            }
        ],
        "policy": {
            "hard": {
                "min_gap_min": 0
            }
        }
    }
    
    events_json_str = json.dumps(events_by_participant)
    context_json_str = json.dumps(context_json)
    
    try:
        result = orchestrate_scheduling(
            utterance=utterance,
            events_by_participant=events_json_str,
            context_json=context_json_str
        )
        
        if result.get('status') == 'ok' and result.get('proposals'):
            proposal = result['proposals'][0]
            actual_participants = sorted(proposal.get('participants', []))
            expected_sorted = sorted(expected_participants)
            
            print(f"✓ Status: {result.get('status')}")
            print(f"  Actual participants: {actual_participants}")
            
            if actual_participants == expected_sorted:
                print(f"✓ Participants match expected!")
            else:
                print(f"✗ PARTICIPANT MISMATCH!")
                print(f"  Expected: {expected_sorted}")
                print(f"  Actual:   {actual_participants}")
            
            if proposal.get('start_utc'):
                print(f"  Proposed time: {proposal.get('start_utc')} to {proposal.get('end_utc')}")
            
            return actual_participants == expected_sorted
        else:
            print(f"✗ Status: {result.get('status')}")
            if result.get('error_message'):
                print(f"  Error: {result.get('error_message')}")
            return False
    except Exception as e:
        print(f"✗ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("="*80)
    print("Testing Utterance Variations for Requester Inclusion")
    print("="*80)
    
    # Test cases: (utterance, expected_participants)
    test_cases = [
        # "with" phrasings - should include Chad
        (
            "Provide me options for a 45-minute meeting with Sue and Danielle between December 1 and December 12.",
            ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
        ),
        (
            "Schedule a 45-minute meeting with Sue and Danielle next week.",
            ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
        ),
        (
            "Find time for a 45-minute meeting with Sue and Danielle.",
            ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
        ),
        # "me" phrasings - should include Chad
        (
            "I need a 45-minute meeting with Sue and Danielle.",
            ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
        ),
        (
            "Schedule me a 45-minute meeting with Sue and Danielle.",
            ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
        ),
        (
            "Find a 45-minute slot for me with Sue and Danielle.",
            ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
        ),
        # Explicit "me" mentions
        (
            "Find a 45-minute meeting time for me, Sue, and Danielle.",
            ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]
        ),
        # Edge case: without "with" or "me" (DSPy may infer requester should be included)
        (
            "Schedule a 45-minute meeting: Sue and Danielle.",
            ["cdorsey@concord.org", "sbrau@concord.org", "dkehoe@concord.org"]  # DSPy infers requester inclusion
        ),
        # Exclusion phrasings - should NOT include Chad
        (
            "Find a meeting between Sue and Danielle.",
            ["sbrau@concord.org", "dkehoe@concord.org"]
        ),
        (
            "Find a 45-minute meeting for just Sue and Danielle.",
            ["sbrau@concord.org", "dkehoe@concord.org"]
        ),
        (
            "Schedule a meeting for only Sue and Danielle.",
            ["sbrau@concord.org", "dkehoe@concord.org"]
        ),
        (
            "Find a 45-minute slot for Sue and Danielle without me.",
            ["sbrau@concord.org", "dkehoe@concord.org"]
        ),
        (
            "Schedule a meeting for Sue and Danielle excluding me.",
            ["sbrau@concord.org", "dkehoe@concord.org"]
        ),
    ]
    
    results = []
    for utterance, expected in test_cases:
        success = test_utterance(utterance, expected)
        results.append((utterance, success))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    passed = sum(1 for _, success in results if success)
    total = len(results)
    print(f"\nPassed: {passed}/{total}")
    
    for utterance, success in results:
        status = "✓" if success else "✗"
        print(f"{status} {utterance[:60]}...")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

