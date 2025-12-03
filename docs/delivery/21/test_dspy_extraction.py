#!/usr/bin/env python3
"""
Test DSPy extraction directly to verify it's working.
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

from scheduling_orchestrator.dspy_extraction import extract_with_fallback, extract_scheduling_request
from scheduling_orchestrator.schemas import SchedulingProblem

def test_dspy():
    utterance = "Provide me options for a 45-minute meeting with Sue and Danielle between December 1 and December 12."
    
    context_json = {
        "timeframe": {
            "from": "2025-12-01",
            "to": "2025-12-12",
            "tz": "America/New_York"
        },
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
    
    print("=" * 80)
    print("Testing DSPy Extraction")
    print("=" * 80)
    print(f"\nUtterance: {utterance}")
    print(f"\nContext participants:")
    for p in context_json["participants"]:
        print(f"  - {p.get('name', 'N/A')}: {p['id']}")
    print("\n" + "-" * 80)
    print("Calling extract_scheduling_request...")
    print("-" * 80 + "\n")
    
    try:
        result = extract_scheduling_request(utterance, context_json)
        print("\n" + "=" * 80)
        print("SUCCESS!")
        print("=" * 80)
        print(f"\nExtracted SchedulingProblem:")
        print(f"  Participants: {result.participants}")
        print(f"  Duration: {result.duration_minutes} minutes")
        print(f"  Time window: {result.time_window_start} to {result.time_window_end}")
        print(f"  Title: {result.title}")
        print(f"  Preferred days: {result.preferred_days}")
        print(f"  Allow off hours: {result.allow_off_hours}")
        
        # Verify participant mapping
        expected = ["sbrau@concord.org", "dkehoe@concord.org"]
        if set(result.participants) == set(expected):
            print(f"\n✓ Participant mapping correct!")
        else:
            print(f"\n⚠ Participant mapping issue:")
            print(f"  Expected: {expected}")
            print(f"  Got: {result.participants}")
        
        return result
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = test_dspy()
    sys.exit(0 if result else 1)

