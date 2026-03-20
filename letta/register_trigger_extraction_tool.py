#!/usr/bin/env python3
"""Register trigger_task_extraction tool and attach to MC."""

import json
import os
import inspect
import urllib.request

LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
MC_AGENT_ID = "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef"

from trigger_task_extraction_tool import trigger_task_extraction

source = inspect.getsource(trigger_task_extraction)

# Check for existing tool
resp = urllib.request.urlopen(f"{LETTA_BASE}/v1/tools/?limit=100", timeout=10)
tools = json.loads(resp.read())
existing = None
for t in tools:
    if t["name"] == "trigger_task_extraction":
        existing = t
        break

if existing:
    print(f"Updating existing tool: {existing['id']}")
    req = urllib.request.Request(
        f"{LETTA_BASE}/v1/tools/{existing['id']}",
        data=json.dumps({"source_code": source}).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    urllib.request.urlopen(req, timeout=10)
    tool_id = existing["id"]
else:
    print("Creating new tool")
    req = urllib.request.Request(
        f"{LETTA_BASE}/v1/tools/",
        data=json.dumps({
            "name": "trigger_task_extraction",
            "source_code": source,
            "tags": ["extraction", "tasks", "mc"],
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=10)
    tool = json.loads(resp.read())
    tool_id = tool["id"]
    print(f"Created: {tool_id}")

# Check if attached to MC
resp = urllib.request.urlopen(f"{LETTA_BASE}/v1/agents/{MC_AGENT_ID}/tools?limit=50", timeout=10)
mc_tools = json.loads(resp.read())
mc_tool_ids = [t["id"] for t in mc_tools]

if tool_id in mc_tool_ids:
    print("Already attached to MC")
else:
    print("Attaching to MC...")
    mc_tool_ids.append(tool_id)
    req = urllib.request.Request(
        f"{LETTA_BASE}/v1/agents/{MC_AGENT_ID}/",
        data=json.dumps({"tool_ids": mc_tool_ids}).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    urllib.request.urlopen(req, timeout=10)
    print("Attached")

print(f"\nDone! Tool ID: {tool_id}")
