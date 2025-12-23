#!/usr/bin/env python3
"""
Debug Calendar Tool - Direct test of list_calendars in container context
"""

import os
import sys

# Add letta directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Change to the tool execution directory
os.chdir('/app/tools/letta')
sys.path.insert(0, '/app/tools/letta')

print("Python path:", sys.path[:3])
print("Working directory:", os.getcwd())
print()

# Test imports
print("Testing imports...")
try:
    from calendar_tools.tools import list_calendars
    print("✓ Successfully imported list_calendars")
except Exception as e:
    print(f"✗ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("Calling list_calendars()...")
print()

try:
    import json
    result = list_calendars()
    print("Result:")
    print(json.dumps(result, indent=2))
except Exception as e:
    print(f"✗ Error calling list_calendars: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
