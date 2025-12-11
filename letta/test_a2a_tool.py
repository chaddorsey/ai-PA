#!/usr/bin/env python3
"""
Test Agent-to-Agent Messaging Tool

This script tests the send_message_to_agent tool by sending a test message
from one agent to another and verifying the response.
"""

import os
import sys
import json
from pathlib import Path

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass
except Exception:
    pass

# Add letta directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from a2a_tool import send_message_to_agent

# Configuration
MAIN_ORCHESTRATION_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"
SCHEDULING_AGENT_ID = "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"

def main():
    """Test agent-to-agent messaging."""
    
    print("="*60)
    print("Test Agent-to-Agent Messaging Tool")
    print("="*60)
    print()
    
    # Check for required environment variables
    letta_api_key = os.getenv("LETTA_API_KEY")
    if not letta_api_key:
        print("❌ LETTA_API_KEY not set in environment")
        print("   Set it with: export LETTA_API_KEY=your-api-key")
        return 1
    
    print("✓ LETTA_API_KEY found")
    print(f"✓ LETTA_BASE_URL: {os.getenv('LETTA_BASE_URL', 'http://localhost:8283')}")
    print()
    
    # Test 1: Send message from main orchestration agent to scheduling agent
    print("Test 1: Main Orchestration Agent → Scheduling Agent")
    print("-" * 60)
    print(f"Sender: {MAIN_ORCHESTRATION_AGENT_ID}")
    print(f"Recipient: {SCHEDULING_AGENT_ID}")
    print(f"Message: 'Hello from the main orchestration agent! Can you confirm you received this message?'")
    print()
    
    try:
        result = send_message_to_agent(
            sender_agent_id=MAIN_ORCHESTRATION_AGENT_ID,
            recipient_agent_id=SCHEDULING_AGENT_ID,
            message="Hello from the main orchestration agent! Can you confirm you received this message?"
        )
        
        result_data = json.loads(result)
        
        if result_data.get("status") == "ok":
            print("✓ Message sent successfully")
            replies = result_data.get("replies", [])
            print(f"✓ Received {len(replies)} reply(ies)")
            for i, reply in enumerate(replies, 1):
                print(f"\nReply {i}:")
                print(f"  {reply}")
        else:
            print(f"✗ Error: {result_data.get('error', 'Unknown error')}")
            return 1
        
    except Exception as e:
        print(f"✗ Exception: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print()
    print("="*60)
    print("Test Complete")
    print("="*60)
    print()
    print("If you received a reply, the agent-to-agent communication is working!")
    print()
    print("Note: The recipient agent needs to be configured to respond to")
    print("incoming messages. Make sure the agent has appropriate instructions")
    print("to handle messages from other agents.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


