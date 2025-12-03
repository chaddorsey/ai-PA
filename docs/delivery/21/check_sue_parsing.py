#!/usr/bin/env python3
"""Check Sue's event parsing"""

from pathlib import Path
import json

example_file = Path(__file__).parent / "example_event_data.md"
with open(example_file, 'r') as f:
    content = f.read()

participant = "sbrau@concord.org"
marker = f"Event data for {participant}:"
idx = content.find(marker)

if idx == -1:
    print(f"Marker not found for {participant}")
    exit(1)

print(f"Found marker at position {idx}")

json_start = content.find('[', idx)
if json_start == -1:
    print("Could not find JSON array start")
    exit(1)

print(f"JSON start at position {json_start}")

# Count brackets to find the end
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

print(f"JSON end at position {json_end}")
print(f"Bracket count after parsing: {bracket_count}")

if bracket_count != 0:
    print("\n⚠️  Unmatched brackets!")
    # Show context around the problem area
    context_start = max(0, json_start - 50)
    context_end = min(len(content), json_end + 50)
    print("\nContext around JSON:")
    print(content[context_start:context_end])
else:
    json_str = content[json_start:json_end]
    try:
        events = json.loads(json_str)
        print(f"\n✓ Successfully parsed {len(events)} events for {participant}")
    except json.JSONDecodeError as e:
        print(f"\n✗ JSON decode error: {e}")
        print(f"Error at position: {e.pos if hasattr(e, 'pos') else 'unknown'}")
        # Show error context
        if hasattr(e, 'pos'):
            error_pos = json_start + e.pos
            context_start = max(0, error_pos - 100)
            context_end = min(len(content), error_pos + 100)
            print(f"\nContext around error:")
            print(content[context_start:context_end])

