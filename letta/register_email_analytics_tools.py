#!/usr/bin/env python3
"""
Register Email Analytics Tool with Letta Agent
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found. Install with: pip install letta-client")
        sys.exit(1)

from email_analytics_tools import get_email_analytics

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")


def main():
    print(f"{'='*60}")
    print("Email Analytics Tool Registration")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Agent ID: {AGENT_ID if AGENT_ID else 'Not set'}\n")
    
    tools_to_register = [
        ("get_email_analytics", get_email_analytics, "Anonymized email analytics (org/quartile/individual modes)"),
    ]
    
    registered_tool_ids = []
    
    try:
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        for tool_name, tool_func, tool_description in tools_to_register:
            print(f"Registering tool: {tool_name}")
            print(f"  Description: {tool_description}")
            
            try:
                created_tool = client.tools.create_from_function(
                    func=tool_func,
                    tags=["email", "analytics", "privacy", "anonymized"]
                )
                print(f"  ✓ Registered: {tool_name}")
                tool_id = created_tool.id if hasattr(created_tool, 'id') else 'N/A'
                print(f"    Tool ID: {tool_id}")
                registered_tool_ids.append(tool_id)
                
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "409" in error_str:
                    print(f"  → Tool exists, updating...")
                    try:
                        all_tools = client.tools.list()
                        for tool in all_tools:
                            tool_name_check = tool.name if hasattr(tool, 'name') else tool.get("name")
                            if tool_name_check == tool_name:
                                tool_id = tool.id if hasattr(tool, 'id') else tool.get("id")
                                if tool_id:
                                    client.tools.delete(tool_id=tool_id)
                                    created_tool = client.tools.create_from_function(
                                        func=tool_func,
                                        tags=["email", "analytics", "privacy", "anonymized"]
                                    )
                                    new_tool_id = created_tool.id if hasattr(created_tool, 'id') else 'N/A'
                                    registered_tool_ids.append(new_tool_id)
                                    print(f"    ✓ Re-registered: {tool_name}")
                                    print(f"      New Tool ID: {new_tool_id}")
                                    break
                    except Exception as list_e:
                        print(f"    Could not update: {list_e}")
                else:
                    print(f"  ❌ Failed: {e}")
            print()
        
        if AGENT_ID and registered_tool_ids:
            print(f"→ Attaching tools to agent {AGENT_ID}...")
            for tool_id in registered_tool_ids:
                try:
                    client.agents.tools.attach(agent_id=AGENT_ID, tool_id=tool_id)
                    print(f"  ✓ Attached {tool_id}")
                except Exception as e:
                    if "already" in str(e).lower():
                        print(f"  → Already attached: {tool_id}")
                    else:
                        print(f"  ⚠ Could not attach: {e}")
        
        print(f"\n{'='*60}")
        print("Registration Complete")
        print(f"{'='*60}\n")
        
        print("Usage Examples:")
        print("  # Org-wide totals")
        print("  get_email_analytics(start_datetime='2025-12-17T00:00:00-05:00',")
        print("                      end_datetime='2025-12-24T00:00:00-05:00', mode='org')")
        print()
        print("  # Quartile analysis")
        print("  get_email_analytics(..., mode='quartile', quartile_pin_metric='sent')")
        print()
        print("  # Individual anonymized")
        print("  get_email_analytics(..., mode='individual')")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
