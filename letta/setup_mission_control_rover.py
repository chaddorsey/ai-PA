#!/usr/bin/env python3
"""
Setup Mission Control + Rover Two-Agent Architecture

This script:
1. Verifies/creates the Rover agent (laptop-resident execution agent)
2. Renames existing LettaBot agent to "Mission Control"
3. Creates shared memory blocks (tasks, status, shared_context)
4. Attaches shared blocks to both agents
5. Registers message_agent tool (letta_client SDK pattern) and attaches to both
6. Creates/updates agent_info blocks for both agents
7. Outputs laptop LettaBot config for Rover

Prerequisites:
- Letta server running at LETTA_BASE_URL
- LettaBot agent agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef exists
- letta-client package installed (pip install letta-client)

Inter-agent messaging pattern per Letta docs:
https://docs.letta.com/guides/agents/multi-agent-custom-tools/
"""

import os
import sys
import json
import urllib.request
import urllib.error
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

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
MC_AGENT_ID = "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef"
ROVER_AGENT_ID = "agent-76ee5448-68ec-4fdd-b102-d4895d44e090"
TAILSCALE_HOSTNAME = "dorseys-mac-mini"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def http_get(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f"  GET Error ({url}): {e}")
        return None


def http_post(url, data):
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"  POST Error {e.code}: {error_body}")
        return None
    except Exception as e:
        print(f"  POST Error: {e}")
        return None


def http_patch(url, data):
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='PATCH'
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"  PATCH Error {e.code}: {error_body}")
        return None
    except Exception as e:
        print(f"  PATCH Error: {e}")
        return None


def detach_block(agent_id, block_id, label="block"):
    """Detach a block from an agent. Returns True on success or already-detached."""
    try:
        req = urllib.request.Request(
            f"{LETTA_BASE_URL}/v1/agents/{agent_id}/core-memory/blocks/detach/{block_id}",
            data=json.dumps({}).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='PATCH'
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"  Detached '{label}' from agent")
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  '{label}' already detached")
            return True
        error_body = e.read().decode('utf-8')
        print(f"  Detach error for '{label}': {e.code} {error_body}")
        return False
    except Exception as e:
        print(f"  Detach error for '{label}': {e}")
        return False


def detach_tool(client, agent_id, tool_id, tool_name="tool"):
    """Detach a tool from an agent. Handles already-detached."""
    try:
        client.agents.tools.detach(agent_id=agent_id, tool_id=tool_id)
        print(f"  Detached tool '{tool_name}' from agent")
    except Exception as e:
        error_str = str(e).lower()
        if "not found" in error_str or "404" in error_str:
            print(f"  Tool '{tool_name}' already detached")
        else:
            print(f"  Warning: could not detach tool '{tool_name}': {e}")


# ---------------------------------------------------------------------------
# Block helpers
# ---------------------------------------------------------------------------

def find_or_create_block(label, value, description, limit=5000):
    """Find existing block by label or create new one. Returns block ID."""
    existing = http_get(f"{LETTA_BASE_URL}/v1/blocks/?label={label}")
    if existing and len(existing) > 0:
        block_id = existing[0].get('id')
        print(f"  Found existing '{label}' block (ID: {block_id})")
        # Don't overwrite existing block values — they may have live data
        return block_id

    print(f"  Creating '{label}' block...")
    result = http_post(f"{LETTA_BASE_URL}/v1/blocks/", {
        "label": label,
        "description": description,
        "value": value,
        "limit": limit,
    })
    if result and result.get('id'):
        block_id = result['id']
        print(f"  Created block (ID: {block_id})")
        return block_id
    print(f"  Failed to create '{label}' block")
    return None


def get_agent_block_ids(agent_id):
    """Return set of block IDs currently attached to an agent."""
    response = http_get(f"{LETTA_BASE_URL}/v1/agents/{agent_id}/core-memory")
    if response and 'blocks' in response:
        return {b.get('id') for b in response['blocks']}
    return set()


def attach_block(agent_id, block_id, agent_name="agent"):
    """Attach block to agent if not already attached."""
    existing = get_agent_block_ids(agent_id)
    if block_id in existing:
        print(f"  Block already attached to {agent_name}")
        return True
    result = http_patch(
        f"{LETTA_BASE_URL}/v1/agents/{agent_id}/core-memory/blocks/attach/{block_id}",
        {}
    )
    if result is not None:
        print(f"  Attached block to {agent_name}")
        return True
    print(f"  Failed to attach block to {agent_name}")
    return False


# ---------------------------------------------------------------------------
# Tool helpers
# ---------------------------------------------------------------------------

def find_tool_by_name(client, name):
    """Find a tool by name using the SDK. Returns tool ID or None."""
    tools_result = client.tools.list()
    tools = tools_result.items if hasattr(tools_result, 'items') else tools_result
    for tool in tools:
        tool_name = tool.name if hasattr(tool, 'name') else (tool.get("name") if isinstance(tool, dict) else None)
        tool_id = tool.id if hasattr(tool, 'id') else (tool.get("id") if isinstance(tool, dict) else None)
        if tool_name == name:
            return tool_id
    return None


def attach_tool_to_agent(client, agent_id, tool_id, agent_name="agent"):
    """Attach tool to agent using safe SDK method. Handles already-attached."""
    try:
        client.agents.tools.attach(agent_id=agent_id, tool_id=tool_id)
        print(f"  Tool attached to {agent_name}")
    except Exception as e:
        error_str = str(e).lower()
        if "already attached" in error_str or "already exists" in error_str or "409" in error_str:
            print(f"  Tool already attached to {agent_name}")
        else:
            print(f"  Warning: could not attach tool to {agent_name}: {e}")


# ---------------------------------------------------------------------------
# message_agent tool source (per Letta docs)
# Uses letta_client SDK, runs server-side in sandbox
# ---------------------------------------------------------------------------

MESSAGE_AGENT_SOURCE = '''
def message_agent(target_agent_id: str, message: str) -> str:
    """
    Send a message to another Letta agent and return its text response.

    Args:
        target_agent_id: The agent ID to send the message to (e.g., "agent-abc123...")
        message: The message content to send to the target agent

    Returns:
        The text response from the target agent
    """
    import os
    from letta_client import Letta

    # letta_client auto-reads LETTA_API_KEY from env; empty string causes crash
    if not os.environ.get("LETTA_API_KEY"):
        os.environ.pop("LETTA_API_KEY", None)

    client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"))
    response = client.agents.messages.create(
        agent_id=target_agent_id,
        messages=[{"role": "user", "content": message}],
        streaming=False
    )
    texts = []
    for m in response.messages:
        if hasattr(m, "content") and m.content:
            texts.append(m.content)
    return "\\n".join(texts) if texts else "(no text response)"
'''


# ---------------------------------------------------------------------------
# message_rover_local tool source
# Calls LettaBot's chat API on the laptop via Tailscale for local tool access
# ---------------------------------------------------------------------------

MESSAGE_ROVER_LOCAL_SOURCE = '''
def message_rover_local(message: str) -> str:
    """
    Send a message to Rover through the laptop's LettaBot instance.
    This gives Rover local Bash/filesystem access on the laptop.
    Falls back gracefully if the laptop is offline.

    Args:
        message: The task or message for Rover to handle locally

    Returns:
        Rover's response, or an offline notice
    """
    import os
    import requests

    laptop_url = os.getenv("ROVER_LETTABOT_URL", "http://100.95.213.46:8080")
    api_key = os.getenv("ROVER_LETTABOT_API_KEY", "")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key

    try:
        resp = requests.post(
            f"{laptop_url}/api/v1/chat",
            json={"message": message},
            headers=headers,
            timeout=120
        )
        if resp.ok:
            data = resp.json()
            return data.get("response", str(data))
        return f"Rover returned HTTP {resp.status_code}: {resp.text[:500]}"
    except requests.exceptions.ConnectionError:
        return "OFFLINE: Laptop is not reachable. Queue this task in the tasks block instead."
    except requests.exceptions.Timeout:
        return "TIMEOUT: Rover is busy or unresponsive. Queue this task in the tasks block instead."
    except Exception as e:
        return f"ERROR: {str(e)}"
'''


# ---------------------------------------------------------------------------
# Persona definitions
# ---------------------------------------------------------------------------

def mc_persona(rover_agent_id):
    return f"""I am Mission Control, the always-on server agent. I am the user's primary conversational interface.

ROLE:
- I own all user-facing channels (Telegram, etc.)
- I respond to user messages directly for conversation, planning, reasoning, and any server-side tasks
- I coordinate with Rover (my laptop execution agent) for tasks requiring the user's local machine

ROVER COORDINATION:
- Rover's agent ID: {rover_agent_id}
- Rover has Bash and filesystem access on the user's laptop, but ONLY when the laptop is on and LettaBot is running

COMMUNICATION PRIORITY:
1. For laptop tasks needing immediate execution: use message_rover_local
   - This calls Rover's LettaBot on the laptop directly, giving Rover full Bash access
   - If it returns OFFLINE or TIMEOUT: fall back to tasks block
   - Tell the user: "Your laptop appears offline -- I've queued this for when it comes back"
2. For non-urgent laptop tasks: write directly to tasks block (Rover heartbeat picks up every 2 min)
3. For coordination that doesn't need Bash (memory updates, questions): use message_agent

TASK BLOCK FORMAT (for tasks block):
Task: [short description]
Priority: high/medium/low
From: mission-control
Requested: [timestamp]
Details: [what to do]

WHEN LAPTOP IS OFFLINE:
- Tasks queue in the tasks block until Rover comes online
- Tell the user: "I've queued that for your laptop -- it'll be handled when it comes online"
- I can still do anything that doesn't require laptop access: conversation, memory updates, server-side tools, planning

SHARED CONTEXT:
- The "shared_context" block contains persistent knowledge both agents need
- Update it when I learn important user preferences or project state"""


def rover_persona(mc_agent_id):
    return f"""I am Rover, the laptop execution agent. I run on the user's laptop and handle local tasks.

ROLE:
- Execute tasks delegated by Mission Control via the "tasks" memory block
- Run Bash commands, manage local files, interact with local services on the user's laptop
- Report results back via the "status" memory block
- Message Mission Control ({mc_agent_id}) via message_agent tool when tasks complete or need clarification

HEARTBEAT WORKFLOW:
On each heartbeat:
1. Read the "tasks" block for pending work
2. Execute each task using local tools (Bash, Read, Write, etc.)
3. Write results to the "status" block with timestamp and outcome
4. Clear completed tasks from the "tasks" block
5. If no tasks pending, optionally do proactive maintenance

STATUS BLOCK FORMAT:
Write results like this:
Result: [task description]
Completed: [timestamp]
Outcome: success/failure/needs-input
Details: [output, errors, or questions]

MISSION CONTROL COORDINATION:
- Mission Control's agent ID: {mc_agent_id}
- For important results or questions: also message Mission Control directly using message_agent
- Mission Control handles all user communication -- I do not talk to the user directly

SHARED CONTEXT:
- The "shared_context" block contains persistent knowledge both agents share
- Update it when I discover relevant local system state (installed tools, project locations, etc.)

LOCAL CAPABILITIES:
- Full Bash access on the user's laptop
- File read/write/edit
- Git operations
- Any CLI tool installed on the laptop"""


# ---------------------------------------------------------------------------
# Main setup
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Mission Control + Rover: Two-Agent Architecture Setup")
    print("=" * 60)
    print(f"\nLetta Base URL: {LETTA_BASE_URL}\n")

    # ------------------------------------------------------------------
    # Step 0: Import SDK
    # ------------------------------------------------------------------
    try:
        from letta_client import Letta
    except ImportError:
        try:
            from letta import Letta
        except ImportError:
            print("Error: letta_client or letta package not found")
            print("  Install with: pip install letta-client")
            return 1

    client = Letta(base_url=LETTA_BASE_URL)
    print("Connected to Letta server\n")

    # ------------------------------------------------------------------
    # Step 1: Verify both agents exist
    # ------------------------------------------------------------------
    print("--- Step 1: Verify agents ---")
    mc_agent = http_get(f"{LETTA_BASE_URL}/v1/agents/{MC_AGENT_ID}")
    if not mc_agent:
        print(f"  Error: Mission Control agent {MC_AGENT_ID} not found!")
        return 1
    print(f"  Mission Control: {mc_agent.get('name')} ({MC_AGENT_ID})")

    rover_agent = http_get(f"{LETTA_BASE_URL}/v1/agents/{ROVER_AGENT_ID}")
    if not rover_agent:
        print(f"  Error: Rover agent {ROVER_AGENT_ID} not found!")
        print("  Create Rover first or update ROVER_AGENT_ID in this script.")
        return 1
    print(f"  Rover: {rover_agent.get('name')} ({ROVER_AGENT_ID})")

    # ------------------------------------------------------------------
    # Step 2: Update personas with cross-references
    # ------------------------------------------------------------------
    print("\n--- Step 2: Update agent personas ---")

    # Update MC persona
    mc_blocks = http_get(f"{LETTA_BASE_URL}/v1/agents/{MC_AGENT_ID}/core-memory")
    if mc_blocks and 'blocks' in mc_blocks:
        for block in mc_blocks['blocks']:
            if block.get('label') == 'persona':
                http_patch(
                    f"{LETTA_BASE_URL}/v1/blocks/{block['id']}",
                    {"value": mc_persona(ROVER_AGENT_ID)}
                )
                print(f"  Updated Mission Control persona")
                break

    # Rename MC agent if needed
    if mc_agent.get('name') != 'Mission Control':
        http_patch(f"{LETTA_BASE_URL}/v1/agents/{MC_AGENT_ID}", {"name": "Mission Control"})
        print("  Renamed agent to 'Mission Control'")

    # Update Rover persona
    rover_blocks = http_get(f"{LETTA_BASE_URL}/v1/agents/{ROVER_AGENT_ID}/core-memory")
    if rover_blocks and 'blocks' in rover_blocks:
        for block in rover_blocks['blocks']:
            if block.get('label') == 'persona':
                http_patch(
                    f"{LETTA_BASE_URL}/v1/blocks/{block['id']}",
                    {"value": rover_persona(MC_AGENT_ID)}
                )
                print(f"  Updated Rover persona")
                break

    # ------------------------------------------------------------------
    # Step 3: Create and attach shared memory blocks
    # ------------------------------------------------------------------
    print("\n--- Step 3: Create shared memory blocks ---")

    shared_blocks = [
        {
            "label": "tasks",
            "description": "Task queue: Mission Control writes tasks, Rover reads and executes them",
            "value": "# Pending Tasks\n\nNo pending tasks.",
            "limit": 5000,
        },
        {
            "label": "status",
            "description": "Status/results: Rover writes completed results, Mission Control reads and relays to user",
            "value": "# Task Results\n\nNo recent results.",
            "limit": 5000,
        },
        {
            "label": "shared_context",
            "description": "Persistent shared context between Mission Control and Rover (laptop state, preferences, project notes)",
            "value": "# Shared Context\n\nUser preferences, project state, and cross-agent notes go here.",
            "limit": 5000,
        },
    ]

    block_ids = {}
    for block_spec in shared_blocks:
        block_id = find_or_create_block(
            block_spec["label"],
            block_spec["value"],
            block_spec["description"],
            block_spec["limit"],
        )
        if block_id:
            block_ids[block_spec["label"]] = block_id
        else:
            print(f"  Failed on block '{block_spec['label']}' — aborting")
            return 1

    # Attach shared blocks to both agents
    print("\n--- Step 3b: Attach shared blocks to both agents ---")
    for label, block_id in block_ids.items():
        attach_block(MC_AGENT_ID, block_id, f"Mission Control ({label})")
        attach_block(ROVER_AGENT_ID, block_id, f"Rover ({label})")

    # ------------------------------------------------------------------
    # Step 4: Register message_agent tool and attach to both agents
    # Per Letta docs: https://docs.letta.com/guides/agents/multi-agent-custom-tools/
    # ------------------------------------------------------------------
    print("\n--- Step 4: message_agent tool (letta_client SDK pattern) ---")

    # Check for old tool and new tool
    old_tool_id = find_tool_by_name(client, "send_message_to_agent")
    new_tool_id = find_tool_by_name(client, "message_agent")

    if old_tool_id and not new_tool_id:
        print(f"  Found old send_message_to_agent tool ({old_tool_id}) — will register new one")

    if new_tool_id:
        print(f"  message_agent tool already registered (ID: {new_tool_id})")
    else:
        print("  Registering message_agent tool via source_code...")
        try:
            created = client.tools.create(source_code=MESSAGE_AGENT_SOURCE)
            new_tool_id = created.id if hasattr(created, 'id') else created.get('id')
            print(f"  Registered message_agent tool (ID: {new_tool_id})")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str or "duplicate" in error_str:
                new_tool_id = find_tool_by_name(client, "message_agent")
                print(f"  message_agent tool already exists (ID: {new_tool_id})")
            else:
                print(f"  Error registering message_agent tool: {e}")
                return 1

    if new_tool_id:
        attach_tool_to_agent(client, MC_AGENT_ID, new_tool_id, "Mission Control")
        attach_tool_to_agent(client, ROVER_AGENT_ID, new_tool_id, "Rover")

    # ------------------------------------------------------------------
    # Step 4b: Register message_rover_local tool (MC only)
    # Calls LettaBot chat API on laptop for local Bash access
    # ------------------------------------------------------------------
    print("\n--- Step 4b: message_rover_local tool (LettaBot chat API) ---")

    rover_local_tool_id = find_tool_by_name(client, "message_rover_local")
    if rover_local_tool_id:
        print(f"  message_rover_local tool already registered (ID: {rover_local_tool_id})")
    else:
        print("  Registering message_rover_local tool via source_code...")
        try:
            created = client.tools.create(source_code=MESSAGE_ROVER_LOCAL_SOURCE)
            rover_local_tool_id = created.id if hasattr(created, 'id') else created.get('id')
            print(f"  Registered message_rover_local tool (ID: {rover_local_tool_id})")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str or "duplicate" in error_str:
                rover_local_tool_id = find_tool_by_name(client, "message_rover_local")
                print(f"  message_rover_local tool already exists (ID: {rover_local_tool_id})")
            else:
                print(f"  Error registering message_rover_local tool: {e}")
                return 1

    if rover_local_tool_id:
        attach_tool_to_agent(client, MC_AGENT_ID, rover_local_tool_id, "Mission Control")
        # NOT attached to Rover — only MC calls this tool

    # ------------------------------------------------------------------
    # Step 5: Agent info blocks (for existing A2A system compatibility)
    # ------------------------------------------------------------------
    print("\n--- Step 5: Agent info blocks ---")

    for agent_name, agent_id in [("Mission Control", MC_AGENT_ID), ("Rover", ROVER_AGENT_ID)]:
        block_label = "agent_info"
        block_value = f"agent_id: {agent_id}"
        existing = http_get(f"{LETTA_BASE_URL}/v1/blocks/?label={block_label}")
        found_block_id = None
        if existing:
            for b in existing:
                if b.get('value', '').strip() == block_value.strip():
                    found_block_id = b.get('id')
                    break

        if found_block_id:
            print(f"  {agent_name}: agent_info block exists (ID: {found_block_id})")
        else:
            result = http_post(f"{LETTA_BASE_URL}/v1/blocks/", {
                "label": block_label,
                "description": f"Read-only block containing {agent_name}'s agent ID for inter-agent communication",
                "value": block_value,
                "limit": 1000,
            })
            if result and result.get('id'):
                found_block_id = result['id']
                print(f"  {agent_name}: created agent_info block (ID: {found_block_id})")
            else:
                print(f"  {agent_name}: failed to create agent_info block")
                continue

        attach_block(agent_id, found_block_id, f"{agent_name} (agent_info)")

    # ------------------------------------------------------------------
    # Step 6: Clean up old blocks and tools from both agents
    # ------------------------------------------------------------------
    print("\n--- Step 6: Detach old mc_rover_* blocks ---")
    old_block_labels = ["mc_rover_tasks", "mc_rover_status", "mc_rover_context"]
    for agent_name, agent_id in [("Mission Control", MC_AGENT_ID), ("Rover", ROVER_AGENT_ID)]:
        agent_blocks = http_get(f"{LETTA_BASE_URL}/v1/agents/{agent_id}/core-memory")
        if agent_blocks and 'blocks' in agent_blocks:
            for block in agent_blocks['blocks']:
                if block.get('label') in old_block_labels:
                    print(f"  {agent_name}:")
                    detach_block(agent_id, block['id'], block['label'])

    print("\n--- Step 6b: Detach old A2A tools ---")
    old_tool_names = ["send_message_to_agent", "send_message_to_agent_async",
                      "send_message_to_agent_and_wait_for_reply"]
    for agent_name, agent_id in [("Mission Control", MC_AGENT_ID), ("Rover", ROVER_AGENT_ID)]:
        # Get this agent's actual attached tools
        try:
            agent_tools = client.agents.tools.list(agent_id=agent_id)
            for t in agent_tools:
                t_name = t.name if hasattr(t, 'name') else t.get('name')
                t_id = t.id if hasattr(t, 'id') else t.get('id')
                if t_name in old_tool_names:
                    print(f"  {agent_name}:")
                    detach_tool(client, agent_id, t_id, t_name)
        except Exception as e:
            print(f"  Warning: could not list tools for {agent_name}: {e}")

    # ------------------------------------------------------------------
    # Step 7: Output summary and laptop config
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Setup Complete!")
    print("=" * 60)

    print(f"""
Agent IDs:
  Mission Control: {MC_AGENT_ID}
  Rover:           {ROVER_AGENT_ID}

Shared Blocks:
  tasks:          {block_ids.get('tasks', 'N/A')}
  status:         {block_ids.get('status', 'N/A')}
  shared_context: {block_ids.get('shared_context', 'N/A')}

message_agent tool:       {new_tool_id or 'N/A'}
message_rover_local tool: {rover_local_tool_id or 'N/A'}
""")

    # Generate laptop LettaBot config
    laptop_config = f"""# Rover LettaBot config — place in lettabot-rover directory on laptop
server:
  mode: docker
  baseUrl: http://{TAILSCALE_HOSTNAME}:8283

agents:
  - name: Rover
    id: {ROVER_AGENT_ID}
    conversations:
      mode: shared
      heartbeat: last-active
    channels:
      telegram:
        enabled: true
        token: "PASTE_BOTFATHER_TOKEN_HERE"
        dmPolicy: open

features:
  cron: false
  heartbeat:
    enabled: true
    intervalMin: 2
    skipRecentUserMin: 0
"""

    laptop_config_path = Path(__file__).parent.parent / "lettabot" / "lettabot-rover.yaml"
    with open(laptop_config_path, 'w') as f:
        f.write(laptop_config)
    print(f"Laptop config template written to: {laptop_config_path}")

    print(f"""
Verification commands:
  # Check agents
  curl -s http://localhost:8283/v1/agents/ | python3 -c "import sys,json; [print(a['name'], a['id']) for a in json.load(sys.stdin)]"

  # Check shared blocks on MC
  curl -s http://localhost:8283/v1/agents/{MC_AGENT_ID}/core-memory | python3 -c "import sys,json; [print(b['label'], b['id']) for b in json.load(sys.stdin)['blocks']]"

  # Check shared blocks on Rover
  curl -s http://localhost:8283/v1/agents/{ROVER_AGENT_ID}/core-memory | python3 -c "import sys,json; [print(b['label'], b['id']) for b in json.load(sys.stdin)['blocks']]"

  # Test message_agent tool (MC -> Rover)
  # curl -s -X POST http://localhost:8283/v1/agents/{MC_AGENT_ID}/messages \\
  #   -H "Content-Type: application/json" \\
  #   -d '{{"messages": [{{"role": "user", "content": "Send a test message to Rover using message_agent"}}]}}'

Laptop setup (run ON the laptop):
  scp dorseyhomeserver@{TAILSCALE_HOSTNAME}:{laptop_config_path} ~/dev/lettabot-rover/lettabot.yaml
""")

    return 0


if __name__ == "__main__":
    sys.exit(main())
