#!/usr/bin/env python3
"""
Debug script to inspect free-block calculations for Chad/Paul move options
"""
import json
import sys
from pathlib import Path
from datetime import datetime
import pytz

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "letta"))

from scheduling_orchestrator.normalizer import normalize_events
from scheduling_orchestrator.schemas import SchedulingProblem
from scheduling_orchestrator.free_block_scorer import calculate_free_block_score, identify_requester
from scheduling_orchestrator.slot_indexer import SlotIndexer
import json as json_module

# Load events
example_file = Path(__file__).parent / 'example_event_data_v2.md'
with open(example_file, 'r') as f:
    content = f.read()

# Extract events for cdorsey@concord.org
participant = 'cdorsey@concord.org'
pattern = rf'{participant}\s+events:\s*\n\s*\n(.*?)(?=\n\w+@\w+\.\w+\s+events:|\Z)'
import re
match = re.search(pattern, content, re.DOTALL | re.MULTILINE)

events_by_participant = {}
if match:
    json_str = match.group(1).strip()
    try:
        events = json.loads(json_str)
        if not isinstance(events, list):
            events = [events]
        events_by_participant[participant] = events
    except:
        pass

# Create scheduling problem
scheduling_problem = SchedulingProblem(
    participants=["cdorsey@concord.org", "dkehoe@concord.org", "sbrau@concord.org"],
    duration_minutes=45,
    time_window_start="2025-12-15T00:00:00-05:00",
    time_window_end="2025-12-15T23:59:59-05:00"
)

context_json = {
    'participants': [
        {'id': 'cdorsey@concord.org', 'work_hours': 'M-F 09:00-17:00'},
        {'id': 'dkehoe@concord.org', 'work_hours': 'M-F 09:00-17:00'},
        {'id': 'sbrau@concord.org', 'work_hours': 'M-F 09:00-17:00'}
    ]
}

# Normalize events
normalized_data = normalize_events(events_by_participant, context_json)

# Test Option 1: Meeting 12:00-12:45, Event moved 45min later (12:00->12:45)
option1_start = "2025-12-15T17:00:00Z"  # 12:00 PM EST
option1_moved_events = [{
    'owner': 'cdorsey@concord.org',
    'event_id': '479qiof9eq3hl5q6f1kmuhml2r_20251222T1900',  # Chad/Paul event
    'old_start': '2025-12-15T17:00:00Z',  # 12:00 PM EST
    'old_end': '2025-12-15T17:45:00Z',   # 12:45 PM EST
    'new_start': '2025-12-15T17:45:00Z', # 12:45 PM EST
    'new_end': '2025-12-15T18:30:00Z'    # 1:30 PM EST
}]

# Test Option 2: Meeting 12:00-12:45, Event moved 60min later (12:00->1:00)
option2_start = "2025-12-15T17:00:00Z"  # 12:00 PM EST
option2_moved_events = [{
    'owner': 'cdorsey@concord.org',
    'event_id': '479qiof9eq3hl5q6f1kmuhml2r_20251222T1900',  # Chad/Paul event
    'old_start': '2025-12-15T17:00:00Z',  # 12:00 PM EST
    'old_end': '2025-12-15T17:45:00Z',   # 12:45 PM EST
    'new_start': '2025-12-15T18:00:00Z', # 1:00 PM EST
    'new_end': '2025-12-15T18:45:00Z'    # 1:45 PM EST
}]

slot_indexer = normalized_data["slot_indexer"]
requester_id = "cdorsey@concord.org"

print("Testing free-block calculations:\n")

print("Option 1: Meeting 12:00-12:45 PM, Event moved 45min later (12:00->12:45)")
print("  Gap: 0 minutes (back-to-back)")
stats1 = calculate_free_block_score(
    option1_start,
    scheduling_problem,
    normalized_data,
    slot_indexer,
    requester_id,
    moved_events=option1_moved_events
)
print(f"  Free-block score: {stats1['free_block_score']:.2f}")
print(f"  Max block: {stats1['max_block_hours']:.2f}h")
print(f"  Median block: {stats1['median_block_hours']:.2f}h")
print(f"  Total effective hours: {stats1['total_effective_hours']:.2f}h")
print()

print("Option 2: Meeting 12:00-12:45 PM, Event moved 60min later (12:00->1:00)")
print("  Gap: 15 minutes (12:45-1:00)")
stats2 = calculate_free_block_score(
    option2_start,
    scheduling_problem,
    normalized_data,
    slot_indexer,
    requester_id,
    moved_events=option2_moved_events
)
print(f"  Free-block score: {stats2['free_block_score']:.2f}")
print(f"  Max block: {stats2['max_block_hours']:.2f}h")
print(f"  Median block: {stats2['median_block_hours']:.2f}h")
print(f"  Total effective hours: {stats2['total_effective_hours']:.2f}h")
print()

print(f"Score difference: Option 1 - Option 2 = {stats1['free_block_score'] - stats2['free_block_score']:.2f}")
if stats2['free_block_score'] > stats1['free_block_score']:
    print("✓ Option 2 correctly ranks higher")
else:
    print("✗ Option 1 incorrectly ranks higher - needs investigation")

