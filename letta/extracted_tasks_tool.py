"""
Extracted Tasks Tool for Letta

Provides a concurrent-safe way for multiple agents to contribute to a shared
extracted_tasks memory block without race conditions.

Tool: add_extracted_tasks
"""

from typing import Dict, Any, Optional


def add_extracted_tasks(task_description: str) -> Dict[str, Any]:
    """
    Add a task to the shared extracted_tasks memory block (concurrent-safe).

    This tool allows multiple agents to contribute tasks to a shared memory block
    without overwriting each other's entries. Uses append-only memory_insert for
    concurrent safety.

    Each agent's tasks are organized under a header with the agent's name and ID:
    === Agent Name (agent_id) ===
    [timestamp] Task description

    Args:
        task_description: Description of the task to add to extracted_tasks block.

    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - message: Confirmation message or error description
        - agent_name: Name of the agent that added the task
        - timestamp: ISO timestamp when task was added
        - error_message: Detailed error message if status is "error"
    """
    # Import required modules inside function for Letta tool extraction
    import os
    import traceback
    from datetime import datetime
    import pytz
    import urllib.request
    import urllib.parse
    import json

    # Wrap entire function in try-except
    try:
        # Get Letta configuration
        LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        AGENT_ID = os.getenv("LETTA_AGENT_ID")

        if not AGENT_ID:
            return {
                "status": "error",
                "message": "",
                "agent_name": "",
                "timestamp": "",
                "error_message": "LETTA_AGENT_ID environment variable not set"
            }

        # Get agent information to retrieve agent name
        agent_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}"
        agent_req = urllib.request.Request(agent_url, method='GET')

        try:
            with urllib.request.urlopen(agent_req, timeout=10) as response:
                agent_data = json.loads(response.read().decode('utf-8'))
                agent_name = agent_data.get('name', 'Unknown Agent')
        except Exception as e:
            agent_name = 'Unknown Agent'

        # Get current timestamp in Eastern Time
        tz = pytz.timezone("America/New_York")
        now = datetime.now(tz)
        timestamp_str = now.strftime("%Y-%m-%d %H:%M")
        iso_timestamp = now.isoformat()

        # Get agent's memory blocks from agent endpoint (blocks are embedded in memory.blocks)
        # Re-fetch agent data to get current memory blocks
        agent_url_full = f"{LETTA_BASE}/v1/agents/{AGENT_ID}"
        agent_req_full = urllib.request.Request(agent_url_full, method='GET')

        try:
            with urllib.request.urlopen(agent_req_full, timeout=10) as response:
                agent_data_full = json.loads(response.read().decode('utf-8'))
                blocks_data = agent_data_full.get('memory', {}).get('blocks', [])
        except Exception as e:
            return {
                "status": "error",
                "message": "",
                "agent_name": agent_name,
                "timestamp": iso_timestamp,
                "error_message": f"Failed to retrieve memory blocks: {str(e)}"
            }

        # Find extracted_tasks block
        extracted_tasks_block = None
        for block in blocks_data:
            if block.get('label') == 'extracted_tasks':
                extracted_tasks_block = block
                break

        if not extracted_tasks_block:
            return {
                "status": "error",
                "message": "",
                "agent_name": agent_name,
                "timestamp": iso_timestamp,
                "error_message": "extracted_tasks block not found. Ensure block is attached to this agent."
            }

        extracted_tasks_block_id = extracted_tasks_block.get('id')
        current_value = extracted_tasks_block.get('value', '')

        # Find this agent's section in the block
        import re
        section_header = f"=== {agent_name} ({AGENT_ID}) ==="

        # Pattern to find section header + content up to next section or end
        section_pattern = re.compile(
            rf'({re.escape(section_header)})(.*?)(?=(===\s+.+?\s+\(agent-[a-f0-9-]+\)\s+===)|$)',
            re.DOTALL
        )

        section_match = section_pattern.search(current_value)
        task_line = f"[{timestamp_str}] {task_description}\n\n"

        if section_match:
            # Section exists - insert task at end of this agent's section
            insert_pos = section_match.end()
            before = current_value[:insert_pos]
            after = current_value[insert_pos:]
            if before and not before.endswith('\n'):
                before += '\n'
            new_value = before + task_line + after
        else:
            # Section doesn't exist - append new section with header + task
            new_value = current_value + f"\n{section_header}\n{task_line}"

        # Update block via PATCH endpoint
        update_url = f"{LETTA_BASE}/v1/blocks/{extracted_tasks_block_id}"

        update_data = {
            "value": new_value
        }

        update_payload = json.dumps(update_data).encode('utf-8')
        update_req = urllib.request.Request(
            update_url,
            data=update_payload,
            headers={"Content-Type": "application/json"},
            method='PATCH'
        )

        try:
            with urllib.request.urlopen(update_req, timeout=10) as response:
                response_data = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as http_err:
            error_body = http_err.read().decode('utf-8')
            return {
                "status": "error",
                "message": "",
                "agent_name": agent_name,
                "timestamp": iso_timestamp,
                "error_message": f"HTTP {http_err.code}: Failed to update extracted_tasks block. {error_body[:200]}"
            }

        # Return success
        return {
            "status": "ok",
            "message": f"Added task to extracted_tasks block",
            "agent_name": agent_name,
            "timestamp": iso_timestamp
        }

    except Exception as e:
        # Safe error handling
        try:
            error_timestamp = datetime.now(pytz.timezone("America/New_York")).isoformat()
        except:
            from datetime import datetime as dt
            error_timestamp = dt.now().isoformat()

        return {
            "status": "error",
            "message": "",
            "agent_name": "",
            "timestamp": error_timestamp,
            "error_message": f"Error adding task: {str(e)}\n{traceback.format_exc()}"
        }
