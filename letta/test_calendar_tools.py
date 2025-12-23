#!/usr/bin/env python3
"""
Test Calendar Tools

Simple test script to verify calendar tools work correctly.
"""

import os
import sys
from pathlib import Path

# Add letta directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calendar_tools.tools import list_calendars

def test_list_calendars():
    """Test the list_calendars tool."""
    print("="*60)
    print("Testing list_calendars tool")
    print("="*60)
    print()
    
    try:
        result = list_calendars()
        
        if result.get("status") == "ok":
            print("✓ list_calendars succeeded!")
            print(f"  Found {result.get('count', 0)} calendars")
            print()
            
            calendars = result.get("calendars", [])
            if calendars:
                print("Calendars:")
                for cal in calendars[:5]:  # Show first 5
                    print(f"  - {cal.get('summary', 'N/A')} ({cal.get('id', 'N/A')})")
                if len(calendars) > 5:
                    print(f"  ... and {len(calendars) - 5} more")
            print()
            return True
        else:
            print(f"✗ list_calendars failed: {result.get('error_message', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"✗ Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_list_calendars()
    sys.exit(0 if success else 1)
