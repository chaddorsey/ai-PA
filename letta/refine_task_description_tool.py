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

        # Also update archival passage: TASK line and ENRICHMENT status
        ARCHIVE_ID = "archive-f9bcaa87-7630-41c9-9694-41d46fc47d26"
        try:
            search_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}/archival-memory/?search={ref_id}&limit=1"
            sreq = urllib.request.Request(search_url)
            try:
                with urllib.request.urlopen(sreq, timeout=10) as sresp:
                    passages = json.loads(sresp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (301, 302, 307, 308):
                    sreq2 = urllib.request.Request(e.headers.get("Location", ""))
                    with urllib.request.urlopen(sreq2, timeout=10) as sresp:
                        passages = json.loads(sresp.read().decode("utf-8"))
                else:
                    passages = []

            for p in (passages if isinstance(passages, list) else []):
                if not isinstance(p, dict):
                    continue
                text = p.get("text", "")
                if f"REF_ID: {ref_id}" not in text:
                    continue
                pid = p.get("id", "")
                if not pid:
                    continue

                # Update TASK line
                new_text = re.sub(r"^TASK: .+$", f"TASK: {new_description.strip()}", text, count=1, flags=re.MULTILINE)
                # Update ENRICHMENT status
                new_text = re.sub(r"- Status: none", "- Status: phase-a-complete", new_text)

                tags = p.get("tags", []) or []
                tags = [t for t in tags if not t.startswith("enrichment:")]
                tags.append("enrichment:phase-a-complete")

                # Delete old, insert new
                del_url = f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages/{pid}"
                urllib.request.urlopen(urllib.request.Request(del_url, method="DELETE"), timeout=10)

                ins_data = json.dumps({"text": new_text, "tags": tags}).encode("utf-8")
                ins_req = urllib.request.Request(
                    f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages",
                    data=ins_data, headers={"Content-Type": "application/json"}, method="POST",
                )
                urllib.request.urlopen(ins_req, timeout=15)
                break
        except Exception:
            pass  # Archival update is best-effort

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
