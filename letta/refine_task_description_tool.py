"""
Refine Task Description Tool for Letta

Simple tool to update a task's description in the extracted_tasks block
by ref_id. Used by Phase A enrichment after the agent formulates a
better task name.

Tool: refine_task_description
"""

from typing import Dict, Any


def refine_task_description(ref_id: str, new_description: str) -> Dict[str, Any]:
    """
    Update the description of an extracted task in the extracted_tasks block.

    Finds the task line by ref_id and replaces only the description text
    (everything after the ] bracket). Metadata (extracted_time, ref_id,
    origin, est) is preserved.

    Args:
        ref_id: The 8-char hex reference ID of the task to refine.
        new_description: The new verb-led task description (max ~120 chars).

    Returns:
        Dictionary with status and the old/new descriptions.
    """
    import json
    import os
    import re
    import traceback
    import urllib.request

    try:
        LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
        AGENT_ID = os.environ.get("LETTA_AGENT_ID", "agent-dd15479e-6543-400e-8463-b2a48b13cd4a")

        if not ref_id or not new_description:
            return {"status": "error", "error_message": "ref_id and new_description are required"}

        # Get the extracted_tasks block
        agent_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}/"
        try:
            req = urllib.request.Request(agent_url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                agent_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 307, 308):
                redirect = e.headers.get("Location", "")
                req2 = urllib.request.Request(redirect)
                with urllib.request.urlopen(req2, timeout=10) as resp:
                    agent_data = json.loads(resp.read().decode("utf-8"))
            else:
                raise

        et_block = None
        for blk in agent_data.get("memory", {}).get("blocks", []):
            if blk.get("label") == "extracted_tasks":
                et_block = blk
                break

        if not et_block:
            return {"status": "error", "error_message": "extracted_tasks block not found"}

        block_id = et_block["id"]
        value = et_block["value"]

        # Find the line with this ref_id
        lines = value.split("\n")
        found = False
        old_desc = ""
        new_lines = []

        for line in lines:
            if f"ref_id: {ref_id}" in line and line.strip().startswith("[extracted_time:"):
                # Extract the old description (everything after the ] bracket)
                bracket_end = line.find("] ")
                if bracket_end > 0:
                    old_desc = line[bracket_end + 2:]
                    new_line = line[:bracket_end + 2] + new_description.strip()
                    new_lines.append(new_line)
                    found = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        if not found:
            return {
                "status": "error",
                "error_message": f"No task line found with ref_id {ref_id} in extracted_tasks block",
            }

        # Write back
        new_value = "\n".join(new_lines)
        update_data = json.dumps({"value": new_value}).encode("utf-8")
        update_req = urllib.request.Request(
            f"{LETTA_BASE}/v1/blocks/{block_id}",
            data=update_data,
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        try:
            urllib.request.urlopen(update_req, timeout=10)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 307, 308):
                redirect = e.headers.get("Location", "")
                req2 = urllib.request.Request(
                    redirect, data=update_data,
                    headers={"Content-Type": "application/json"},
                    method="PATCH",
                )
                urllib.request.urlopen(req2, timeout=10)
            else:
                raise

        return {
            "status": "ok",
            "ref_id": ref_id,
            "old_description": old_desc.strip(),
            "new_description": new_description.strip(),
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
