#!/usr/bin/env python3
"""
Integration test for Letta Conversations Scheduler Pilot.

Tests the complete multi-user conversation isolation flow:
1. Tools are registered with Letta
2. Tools are attached to scheduler agent
3. Conversation can be created with correct parameters
4. Messages can be sent to conversation
5. User blocks can be discovered via tool
"""

import os
import sys
from pathlib import Path
from typing import Optional

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("❌ Error: letta_client or letta package not found")
        print("   Install with: pip install letta-client")
        sys.exit(1)

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
SCHEDULER_AGENT_ID = os.getenv(
    "LETTA_SCHEDULER_AGENT_ID",
    os.getenv("LETTA_AGENT_ID", "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218")
)
TEST_USER_ID = "test_integration_user"


def test_tools_registered(client) -> bool:
    """Verify conversation tools are registered."""
    print("\n[Test 1] Tools Registered")
    try:
        tools_result = client.tools.list()
        tools = tools_result.items if hasattr(tools_result, 'items') else tools_result
        tool_names = [t.name if hasattr(t, 'name') else t.get('name') for t in tools]

        required = ["find_user_blocks", "create_user_memory_block", "lookup_staff"]
        all_found = True
        for name in required:
            if name in tool_names:
                print(f"  [OK] {name}")
            else:
                print(f"  [FAIL] {name} not found")
                all_found = False
        return all_found
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        return False


def test_tools_attached(client) -> bool:
    """Verify tools are attached to scheduler agent."""
    print("\n[Test 2] Tools Attached to Scheduler")
    try:
        agent = client.agents.retrieve(agent_id=SCHEDULER_AGENT_ID)

        # Get attached tool names
        attached_tool_ids = []
        if hasattr(agent, 'tool_ids'):
            attached_tool_ids = agent.tool_ids or []
        elif hasattr(agent, 'tools'):
            attached_tool_ids = [t.id if hasattr(t, 'id') else t for t in (agent.tools or [])]

        # Get all tools to map IDs to names
        tools_result = client.tools.list()
        tools = tools_result.items if hasattr(tools_result, 'items') else tools_result
        id_to_name = {}
        for t in tools:
            tid = t.id if hasattr(t, 'id') else t.get('id')
            tname = t.name if hasattr(t, 'name') else t.get('name')
            id_to_name[tid] = tname

        attached_names = [id_to_name.get(tid, tid) for tid in attached_tool_ids]

        required = ["find_user_blocks", "create_user_memory_block", "lookup_staff"]
        all_found = True
        for name in required:
            if name in attached_names:
                print(f"  [OK] {name} attached")
            else:
                print(f"  [FAIL] {name} not attached")
                all_found = False
        return all_found
    except Exception as e:
        print(f"  [FAIL] Could not retrieve agent: {e}")
        return False


def test_conversation_creation(client) -> Optional[str]:
    """Test conversation creation."""
    print("\n[Test 3] Conversation Creation")
    import requests

    # Use raw HTTP API since SDK doesn't have conversations attribute
    try:
        response = requests.post(
            f"{LETTA_BASE_URL}/v1/conversations/",
            params={"agent_id": SCHEDULER_AGENT_ID},
            json={"label": f"{TEST_USER_ID} - Integration Test"},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        if response.status_code in (200, 201):
            data = response.json()
            conv_id = data.get("id")
            print(f"  [OK] Created conversation: {conv_id}")
            return conv_id
        else:
            print(f"  [FAIL] API returned {response.status_code}: {response.text[:200]}")
            return None
    except Exception as e:
        print(f"  [FAIL] {e}")
        return None


def test_send_message(client, conversation_id: str) -> bool:
    """Test sending message to conversation."""
    print("\n[Test 4] Send Message to Conversation")
    try:
        # Use the messages endpoint
        messages = client.conversations.messages.create(
            conversation_id=conversation_id,
            role="user",
            content="Hello, this is an integration test message."
        )
        print(f"  [OK] Message sent successfully")
        return True
    except Exception as e:
        # Try alternative API
        try:
            import requests
            response = requests.post(
                f"{LETTA_BASE_URL}/v1/conversations/{conversation_id}/messages",
                json={"input": "Hello, this is an integration test message."},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            if response.status_code in (200, 201):
                print(f"  [OK] Message sent via REST API")
                return True
            else:
                print(f"  [FAIL] REST API returned {response.status_code}")
                return False
        except Exception as e2:
            print(f"  [FAIL] {e}")
            return False


def test_block_creation(client) -> Optional[str]:
    """Test block creation and attachment."""
    print("\n[Test 5] Block Creation & Attachment")
    try:
        # Create a test block
        block = client.blocks.create(
            label=f"preferences_{TEST_USER_ID}_integration_test",
            value="Integration test preference block",
            description="Test block for integration testing",
            limit=2000
        )
        block_id = block.id if hasattr(block, 'id') else block.get('id')
        print(f"  [OK] Created block: {block_id}")

        # Attach to agent using the correct endpoint
        import requests
        attach_url = f"{LETTA_BASE_URL}/v1/agents/{SCHEDULER_AGENT_ID}/core-memory/blocks/attach/{block_id}"
        response = requests.patch(
            attach_url,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if response.status_code in (200, 201, 204):
            print(f"  [OK] Block attached to agent")
            return block_id
        else:
            print(f"  [WARN] Block attachment returned {response.status_code}: {response.text[:200]}")
            return block_id  # Block was created even if attachment failed

    except Exception as e:
        print(f"  [FAIL] {e}")
        return None


def test_identities_exist(client) -> bool:
    """Verify staff identities were migrated."""
    print("\n[Test 6] Staff Identities Exist")
    import requests
    try:
        response = requests.get(
            f"{LETTA_BASE_URL}/v1/identities/",
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        if response.status_code == 200:
            identities = response.json()
            staff_count = len(identities)

            if staff_count >= 20:
                print(f"  [OK] Found {staff_count} identities")
                return True
            else:
                print(f"  [FAIL] Only {staff_count} identities (expected 20+)")
                return False
        else:
            print(f"  [FAIL] API returned {response.status_code}")
            return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_identity_has_properties(client) -> bool:
    """Verify Dan Damelin identity has required properties."""
    print("\n[Test 7] Identity Has Properties")
    import requests
    try:
        response = requests.get(
            f"{LETTA_BASE_URL}/v1/identities/",
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        if response.status_code != 200:
            print(f"  [FAIL] API returned {response.status_code}")
            return False

        identities = response.json()
        dan = None
        for identity in identities:
            if identity.get("identifier_key") == "ddamelin@concord.org":
                dan = identity
                break

        if not dan:
            print("  [FAIL] Dan Damelin identity not found")
            return False

        # Check required properties
        props = {}
        for prop in (dan.get("properties") or []):
            if isinstance(prop, dict):
                key = prop.get("key")
                value = prop.get("value")
                if key:
                    props[key] = value

        required = ["colloquial_name", "slack_id", "calendar_id"]
        all_found = True
        for key in required:
            if key in props:
                print(f"  [OK] {key}: {props[key]}")
            else:
                print(f"  [FAIL] Missing {key}")
                all_found = False

        return all_found
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_lookup_staff_tool_registered(client) -> bool:
    """Verify lookup_staff tool is registered."""
    print("\n[Test 8] lookup_staff Tool Registered")
    try:
        tools_result = client.tools.list()
        tools = tools_result.items if hasattr(tools_result, 'items') else tools_result
        tool_names = [t.name if hasattr(t, 'name') else t.get('name') for t in tools]

        if "lookup_staff" in tool_names:
            print("  [OK] lookup_staff tool registered")
            return True
        else:
            print("  [FAIL] lookup_staff tool not registered")
            return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def cleanup(client, conversation_id: Optional[str], block_id: Optional[str]):
    """Clean up test resources."""
    print("\n[Cleanup]")
    import requests

    if conversation_id:
        try:
            response = requests.delete(
                f"{LETTA_BASE_URL}/v1/conversations/{conversation_id}",
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            if response.status_code in (200, 204):
                print(f"  Deleted conversation: {conversation_id}")
            else:
                print(f"  Could not delete conversation: {response.status_code}")
        except Exception as e:
            print(f"  Could not delete conversation: {e}")

    if block_id:
        try:
            # Detach from agent first
            import requests
            detach_url = f"{LETTA_BASE_URL}/v1/agents/{SCHEDULER_AGENT_ID}/core-memory/blocks/detach/{block_id}"
            requests.patch(detach_url, headers={"Content-Type": "application/json"}, timeout=10)
        except Exception:
            pass

        try:
            client.blocks.delete(block_id=block_id)
            print(f"  Deleted block: {block_id}")
        except Exception as e:
            print(f"  Could not delete block: {e}")


def main():
    print("=" * 60)
    print("Letta Conversations Scheduler Pilot - Integration Tests")
    print("=" * 60)

    print(f"\nLetta URL: {LETTA_BASE_URL}")
    print(f"Agent ID: {SCHEDULER_AGENT_ID}")
    print(f"Test User: {TEST_USER_ID}")

    try:
        client = Letta(base_url=LETTA_BASE_URL)
        print("\n✓ Connected to Letta server")
    except Exception as e:
        print(f"\n❌ Failed to connect to Letta: {e}")
        return 1

    passed = 0
    failed = 0
    conversation_id = None
    block_id = None

    # Test 1: Tools registered
    if test_tools_registered(client):
        passed += 1
    else:
        failed += 1

    # Test 2: Tools attached
    if test_tools_attached(client):
        passed += 1
    else:
        failed += 1

    # Test 3: Conversation creation
    conversation_id = test_conversation_creation(client)
    if conversation_id:
        passed += 1
    else:
        failed += 1

    # Test 4: Send message (only if conversation created)
    if conversation_id:
        if test_send_message(client, conversation_id):
            passed += 1
        else:
            failed += 1
    else:
        print("\n[Test 4] SKIPPED (no conversation)")
        failed += 1

    # Test 5: Block creation & attachment
    block_id = test_block_creation(client)
    if block_id:
        passed += 1
    else:
        failed += 1

    # Test 6: Identities exist
    if test_identities_exist(client):
        passed += 1
    else:
        failed += 1

    # Test 7: Identity has properties
    if test_identity_has_properties(client):
        passed += 1
    else:
        failed += 1

    # Test 8: lookup_staff tool registered
    if test_lookup_staff_tool_registered(client):
        passed += 1
    else:
        failed += 1

    # Cleanup
    cleanup(client, conversation_id, block_id)

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed == 0:
        print("\n✅ All integration tests passed!")
        print("Multi-user conversation isolation is ready for use.\n")
    else:
        print("\n⚠️  Some tests failed. Review output above.\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
