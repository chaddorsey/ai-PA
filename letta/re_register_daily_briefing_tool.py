#!/usr/bin/env python3
"""
Re-register the daily briefing tool (delete old, register new).

This ensures Letta has the latest version with updated error handling.
"""

import os
import sys
from pathlib import Path

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except (ImportError, Exception):
    pass

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("❌ Error: letta_client or letta package not found")
        sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from daily_briefing.generate_daily_briefing import generate_daily_briefing

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
TOOL_NAME = "generate_daily_briefing"

def main():
    print(f"{'='*60}")
    print("Re-register Daily Briefing Tool")
    print(f"{'='*60}\n")
    
    client = Letta(base_url=LETTA_BASE_URL)
    print("✓ Connected to Letta server\n")
    
    # Find and delete existing tool
    print(f"Looking for existing tool: {TOOL_NAME}...")
    try:
        # Handle SDK v1.0 pagination (returns page object with .items)
        tools_result = client.tools.list()
        tools = tools_result.items if hasattr(tools_result, 'items') else tools_result
        for tool in tools:
            tool_name_attr = tool.name if hasattr(tool, 'name') else (tool.get("name") if isinstance(tool, dict) else None)
            tool_id_attr = tool.id if hasattr(tool, 'id') else (tool.get("id") if isinstance(tool, dict) else None)
            
            if tool_name_attr == TOOL_NAME:
                print(f"  Found tool (ID: {tool_id_attr})")
                try:
                    # Try to delete it
                    if hasattr(client.tools, 'delete'):
                        client.tools.delete(tool_id_attr)
                        print(f"  ✓ Deleted old tool")
                    else:
                        print(f"  ⚠ Cannot delete (delete method not available)")
                        print(f"     Please delete manually in Letta ADE")
                except Exception as e:
                    print(f"  ⚠ Could not delete: {e}")
                break
        else:
            print(f"  → Tool not found (will create new)")
    except Exception as e:
        print(f"  ⚠ Could not list tools: {e}")
    
    print()
    
    # Register new tool
    print(f"Registering new tool: {TOOL_NAME}...")
    try:
        created_tool = client.tools.create_from_function(
            func=generate_daily_briefing,
            tags=["calendar", "briefing", "schedule", "custom"]
        )
        tool_id = created_tool.id if hasattr(created_tool, 'id') else 'N/A'
        print(f"  ✓ Registered successfully")
        print(f"    Tool ID: {tool_id}")
        print(f"\n{'='*60}")
        print("✓ Re-registration Complete")
        print(f"{'='*60}\n")
        print("The tool has been updated with improved error handling.")
        print("The tool is already attached to your agent - no need to re-attach.\n")
        return 0
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
