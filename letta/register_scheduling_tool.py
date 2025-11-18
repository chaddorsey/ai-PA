#!/usr/bin/env python3
"""
Register Scheduling Orchestration Tool with Letta Agent

This script registers the orchestrate_scheduling tool with your Letta agent
so the agent can handle complex scheduling requests using ASP optimization.
"""

import os
import sys

# Add letta directory to path so we can import the scheduling orchestrator
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("❌ Error: letta_client or letta package not found")
        print("   Install with: pip install letta-client")
        sys.exit(1)

from scheduling_orchestrator.orchestrate_scheduling import orchestrate_scheduling

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

def main():
    """Register scheduling orchestration tool with Letta agent."""
    
    print(f"{'='*60}")
    print("Scheduling Orchestration Tool Registration")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}\n")
    
    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        # Register the tool
        tool_name = "orchestrate_scheduling"
        
        print(f"Registering tool: {tool_name}\n")
        
        try:
            # Try create_from_function first (newer API)
            try:
                created_tool = client.tools.create_from_function(
                    func=orchestrate_scheduling,
                    tags=["scheduling", "calendar", "optimization", "custom"]
                )
                print(f"  ✓ Registered: {tool_name}")
                print(f"    Tool ID: {created_tool.get('id', 'N/A')}")
                print(f"    Description: Scheduling orchestration tool using ASP optimization")
                
            except AttributeError:
                # Fallback to create_tool if create_from_function doesn't exist
                created_tool = client.create_tool(
                    func=orchestrate_scheduling,
                    name=tool_name,
                    tags=["scheduling", "calendar", "optimization", "custom"]
                )
                print(f"  ✓ Registered: {tool_name}")
                print(f"    Tool ID: {created_tool.get('id', 'N/A')}")
                print(f"    Description: Scheduling orchestration tool using ASP optimization")
            
            print(f"\n{'='*60}")
            print("Registration Complete")
            print(f"{'='*60}\n")
            
            print("✓ Tool registered successfully")
            print("\nTool Details:")
            print("  Name: orchestrate_scheduling")
            print("  Purpose: Find optimal meeting times using constraint-based optimization")
            print("  Inputs:")
            print("    - utterance: Natural language scheduling request")
            print("    - events_by_participant: Calendar events for all participants")
            print("    - context_json: Optional scheduling rules and preferences")
            print("  Outputs:")
            print("    - status: 'ok', 'unsat', or 'bad_input'")
            print("    - proposals: List of optimal meeting proposals")
            print("    - explanation: Human-readable explanation")
            print("    - relaxations: Suggested relaxations (if unsat)")
            print("\nTo attach this tool to your agent, run:")
            print(f"  python3 attach_scheduling_tool_to_agent.py\n")
            
            return 0
            
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str or "duplicate" in error_str:
                print(f"  → Tool already exists: {tool_name}")
                print("\nTo update the tool, delete it first and re-run this script.")
                return 0
            else:
                print(f"  ✗ Error registering {tool_name}: {e}")
                import traceback
                traceback.print_exc()
                return 1
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

