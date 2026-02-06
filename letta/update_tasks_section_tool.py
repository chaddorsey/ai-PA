"""
Update Tasks Section Tool for Letta

Provides a concurrent-safe way for agents to curate/replace their entire section
in the shared extracted_tasks memory block.

Tool: update_tasks_section
"""

from typing import Dict, Any, Optional


def update_tasks_section(new_content: str) -> Dict[str, Any]:
    """
    Replace your entire section in the extracted_tasks block with new curated content.

    This tool allows you to reorganize, update, or completely replace your section
    of tasks. Safe for concurrent use - each agent can only modify their own section
    bounded by their section header.

    If your section doesn't exist yet, it will be created automatically.

    Args:
        new_content: New content for your tasks section. Can include task lists,
                     priorities, notes, etc. Do not include your section header -
                     it will be preserved automatically.

    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - message: Confirmation message or error description
        - agent_name: Name of the agent that updated the section
        - section_size: Size of the new section in characters
        - timestamp: ISO timestamp when section was updated
        - error_message: Detailed error message if status is "error"
    """
    # Import required modules inside function for Letta tool extraction
    import os
    import traceback
    import re
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
                "section_size": 0,
                "timestamp": "",
                "error_message": "LETTA_AGENT_ID environment variable not set"
            }

        # Get agent information
        agent_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}"
        agent_req = urllib.request.Request(agent_url, method='GET')

        try:
            with urllib.request.urlopen(agent_req, timeout=10) as response:
                agent_data = json.loads(response.read().decode('utf-8'))
                agent_name = agent_data.get('name', 'Unknown Agent')
        except Exception as e:
            agent_name = 'Unknown Agent'

        # Get current timestamp
        tz = pytz.timezone("America/New_York")
        now = datetime.now(tz)
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
                "section_size": 0,
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
                "section_size": 0,
                "timestamp": iso_timestamp,
                "error_message": "extracted_tasks block not found. Ensure block is attached to this agent."
            }

        current_value = extracted_tasks_block.get('value', '')
        block_id = extracted_tasks_block.get('id')

        # Create section header for this agent
        short_agent_id = AGENT_ID[:8] if len(AGENT_ID) >= 8 else AGENT_ID
        section_header = f"=== {agent_name} ({short_agent_id}) ==="

        # Validate new_content doesn't contain other agents' section markers
        # Pattern to match section headers: === AnyText (agent-xxx) ===
        other_section_pattern = re.compile(r'===\s+.+?\s+\(agent-[a-f0-9]+\)\s+===')
        found_markers = other_section_pattern.findall(new_content)

        if found_markers:
            # Check if any found markers are NOT our own
            for marker in found_markers:
                if short_agent_id not in marker:
                    return {
                        "status": "error",
                        "message": "",
                        "agent_name": agent_name,
                        "section_size": 0,
                        "timestamp": iso_timestamp,
                        "error_message": f"New content contains section markers for other agents: {marker}. You can only modify your own section."
                    }

        # Find this agent's section boundaries in current block
        # Pattern: === AgentName (agent_id) === followed by content until next === or end
        section_pattern = re.compile(
            rf'({re.escape(section_header)})(.*?)(?=(===\s+.+?\s+\(agent-[a-f0-9]+\)\s+===)|$)',
            re.DOTALL
        )

        section_match = section_pattern.search(current_value)

        # Construct new section with header and new content
        if new_content.strip():
            new_section = f"{section_header}\n{new_content.rstrip()}\n"
        else:
            new_section = f"{section_header}\n"

        # Compute new block value
        if section_match:
            # Section exists - replace it using string replacement
            old_section = section_match.group(0)
            new_block_value = current_value.replace(old_section, new_section, 1)
            action_message = f"Updated your tasks section ({len(new_content)} chars)"
        else:
            # Section doesn't exist - append it
            new_block_value = current_value + f"\n{new_section}"
            action_message = f"Created new tasks section ({len(new_content)} chars)"

        # Update block via PATCH endpoint
        update_url = f"{LETTA_BASE}/v1/blocks/{block_id}"

        update_data = {
            "value": new_block_value
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
                "section_size": 0,
                "timestamp": iso_timestamp,
                "error_message": f"HTTP {http_err.code}: Failed to update section. {error_body[:200]}"
            }

        return {
            "status": "ok",
            "message": action_message,
            "agent_name": agent_name,
            "section_size": len(new_content),
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
            "section_size": 0,
            "timestamp": error_timestamp,
            "error_message": f"Error updating section: {str(e)}\n{traceback.format_exc()}"
        }
