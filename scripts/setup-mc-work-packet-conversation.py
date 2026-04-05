#!/usr/bin/env python3
"""
One-time setup for MC work packet assembly:
1. Creates a dedicated Letta conversation on MC agent labeled "mc-work-packets"
2. Prints configuration values

Idempotent — re-running detects and reuses existing conversation.
Setup is minimal: the confirmation handler looks up the conversation
by label at runtime (same pattern as enrichment-pipeline).
"""

import json
import os
import sys
import urllib.request
import urllib.error

LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
MC_AGENT_ID = "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef"
CONV_LABEL = "mc-work-packets"


def letta_request(method, path, data=None, timeout=15):
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
    print(f"Setting up MC work packets conversation on {MC_AGENT_ID}")

    # Check for existing conversation with this label
    convs = letta_request("GET", f"/v1/conversations/?agent_id={MC_AGENT_ID}")
    if isinstance(convs, list):
        for c in convs:
            if c.get("label") == CONV_LABEL:
                conv_id = c["id"]
                print(f"Found existing conversation: {conv_id}")
                print(f"\nConfiguration:")
                print(f"  MC_WORK_PACKET_CONV_ID={conv_id}")
                return

    # Create new conversation
    conv = letta_request(
        "POST",
        f"/v1/conversations/?agent_id={MC_AGENT_ID}",
        {"label": CONV_LABEL},
    )
    conv_id = conv["id"]
    print(f"Created conversation: {conv_id}")
    print(f"\nConfiguration:")
    print(f"  MC_WORK_PACKET_CONV_ID={conv_id}")
    print(f"\nNote: The confirmation handler looks up by label at runtime,")
    print(f"      so no env var update is strictly required.")


if __name__ == "__main__":
    main()
