#!/usr/bin/env python3
"""
Attach enrichment tools to MC agent for work packet assembly.

MC gains backtrace_task, write_packet_info, fetch_source_content —
the same tools the tasks agent uses for enrichment, now shared with MC.

SAFETY: PATCH /v1/agents/{id} with tool_ids REPLACES the entire list.
This script GETs current tool IDs first, appends new ones, then
PATCHes with the full list. Idempotent — re-running is safe.

Usage:
    python3 letta/attach_work_packet_tools_to_mc.py
"""

import json
import os
import sys
import urllib.request
import urllib.error

LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
MC_AGENT_ID = "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef"

# Tools to attach (registered via enrichment pipeline work)
WORK_PACKET_TOOLS = {
    "backtrace_task": "tool-1c09bef5-54a8-4349-a471-088acf25b233",
    "write_packet_info": "tool-760c3fbb-9f49-4043-a4f3-e13adba93894",
    "fetch_source_content": "tool-b90d4843-1473-4264-92c4-3bf3e514cbb7",
    "stage_resource": "tool-27124e48-086e-4356-820a-e827579a2551",
}


def letta_request(method, path, data=None, timeout=15):
    """HTTP request with redirect handling."""
    url = f"{LETTA_BASE}{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"} if body else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307, 308):
            loc = e.headers.get("Location", "")
            req2 = urllib.request.Request(
                loc, data=body,
                headers={"Content-Type": "application/json"} if body else {},
                method=method,
            )
            with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                return json.loads(resp2.read().decode("utf-8"))
        raise


def main():
    print(f"Attaching work packet tools to MC ({MC_AGENT_ID})")

    # Get current tool IDs
    current_tools = letta_request("GET", f"/v1/agents/{MC_AGENT_ID}/tools/?limit=100")
    current_ids = [t["id"] for t in current_tools]
    current_names = {t["id"]: t["name"] for t in current_tools}
    print(f"  Current tools: {len(current_ids)}")

    # Check which tools are missing
    to_add = []
    for name, tool_id in WORK_PACKET_TOOLS.items():
        if tool_id in current_ids:
            print(f"  {name}: already attached")
        else:
            print(f"  {name}: will attach")
            to_add.append(tool_id)

    if not to_add:
        print("All tools already attached. Nothing to do.")
        return

    # Append and PATCH with full list
    new_ids = current_ids + to_add
    print(f"  New total: {len(new_ids)} tools")

    result = letta_request("PATCH", f"/v1/agents/{MC_AGENT_ID}/", {"tool_ids": new_ids})

    # Verify
    verify_tools = letta_request("GET", f"/v1/agents/{MC_AGENT_ID}/tools/?limit=100")
    verify_names = [t["name"] for t in verify_tools]
    print(f"\nVerification: MC now has {len(verify_tools)} tools")
    for name in WORK_PACKET_TOOLS:
        status = "yes" if name in verify_names else "NO"
        print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
