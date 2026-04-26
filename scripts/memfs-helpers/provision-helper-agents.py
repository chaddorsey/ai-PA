#!/usr/bin/env python3
"""Provision persistent helper subagents for Task fallback / defense-in-depth.

Even with Path C applied (which fixes the silent-exit on `letta --new-agent`
headless), there's value in pre-creating one persistent helper agent per
subagent_type and tagging them as `role:helper, type:<subagent-type>`. Why:

1. **Defense-in-depth against patch loss.** If letta-code auto-update wipes
   Path C, Task(subagent_type='X') with no agent_id silently breaks.
   Task(subagent_type='X', agent_id=helper-...) goes through a different
   code path (`letta --conv` / `letta --agent X --new`) that doesn't touch
   the broken handle resolution. So personas instructed to use the helper
   pattern survive Path-C wipes.

2. **Deterministic identity per task class.** When the doctor helper is
   always the same agent, you can inspect its conversation history,
   recompile its prompt, debug its behavior. With fresh-spawn-per-call
   subagents, every invocation creates a new agent and you have to grep
   the database to find them.

3. **Cleaner cleanup.** Persistent helpers occupy known agent slots; you
   can prune their conversation history periodically or wipe them and
   recreate without hunting for ephemeral cruft.

This script is idempotent — it checks whether a helper already exists per
subagent_type and only creates if missing. Tags are how we identify them.

Usage:
    LETTA_BASE_URL=http://localhost:8283 python3 provision-helper-agents.py
    LETTA_BASE_URL=http://localhost:8283 python3 provision-helper-agents.py \
        --types general-purpose,explore,plan
    LETTA_BASE_URL=http://localhost:8283 python3 provision-helper-agents.py \
        --list   # show existing helpers, don't create
    LETTA_BASE_URL=http://localhost:8283 python3 provision-helper-agents.py \
        --recreate general-purpose   # wipe + recreate one specific type

Output is JSON: {subagent_type: agent_id} for everything provisioned.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Optional, Tuple, Dict

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283").rstrip("/")
DEFAULT_TYPES = [
    "general-purpose",
    "explore",
    "plan",
    "init",
    "memory",
    "history-analyzer",
]
HELPER_TAG_PREFIX = "type:"
HELPER_ROLE_TAG = "role:helper"
DEFAULT_MODEL_HANDLE = os.environ.get("HELPER_MODEL_HANDLE", "litellm/gpt-4.1-mini")


def http(method: str, path: str, body: Optional[dict] = None) -> Tuple[int, dict]:
    url = f"{LETTA_BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body_text)
        except json.JSONDecodeError:
            return e.code, {"_raw": body_text}


def list_existing_helpers() -> Dict[str, str]:
    """Return {subagent_type: agent_id} for any agent tagged role:helper."""
    code, agents = http("GET", "/v1/agents/?limit=200")
    if code != 200:
        sys.exit(f"GET /v1/agents/ failed: {code} {agents}")
    helpers = {}
    for a in agents:
        tags = a.get("tags") or []
        if HELPER_ROLE_TAG not in tags:
            continue
        for t in tags:
            if t.startswith(HELPER_TAG_PREFIX):
                stype = t[len(HELPER_TAG_PREFIX):]
                if stype in helpers:
                    print(
                        f"WARN: multiple helpers tagged type:{stype} — "
                        f"keeping {helpers[stype]}, ignoring {a['id']}",
                        file=sys.stderr,
                    )
                else:
                    helpers[stype] = a["id"]
                break
    return helpers


def create_helper(subagent_type: str) -> str:
    """Create a fresh persistent helper agent for subagent_type. Returns agent_id."""
    payload = {
        "name": f"helper-{subagent_type}",
        "agent_type": "letta_v1_agent",
        "tags": [HELPER_ROLE_TAG, f"{HELPER_TAG_PREFIX}{subagent_type}", "origin:provisioning"],
        "llm_config": {
            "handle": DEFAULT_MODEL_HANDLE,
            "model": DEFAULT_MODEL_HANDLE.split("/", 1)[-1],
            "model_endpoint_type": "openai",
            "model_endpoint": "http://litellm:4000/v1",
            "context_window": 128000,
        },
        "embedding_config": {
            "embedding_endpoint_type": "openai",
            "embedding_endpoint": "http://litellm:4000/v1",
            "embedding_model": "text-embedding-3-small",
            "embedding_dim": 1536,
        },
        "memory_blocks": [
            {"label": "persona", "value": f"I am a persistent helper subagent for the {subagent_type} role. I do focused work, return concise output, and don't accumulate state across tasks."},
            {"label": "human", "value": "The user is operating an AI Personal Assistant ecosystem. Tasks delegated to me are short-horizon (one Task invocation) and shouldn't require building up cross-task memory."},
        ],
    }
    code, resp = http("POST", "/v1/agents/", payload)
    if 200 <= code < 300:
        return resp.get("id")
    sys.exit(f"POST /v1/agents/ failed for {subagent_type}: {code} {resp}")


def detach_and_delete(agent_id: str) -> None:
    code, _ = http("DELETE", f"/v1/agents/{agent_id}")
    if not (200 <= code < 300):
        print(f"WARN: failed to delete {agent_id}: {code}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--types", default=",".join(DEFAULT_TYPES),
                    help=f"Comma-separated subagent types (default: {','.join(DEFAULT_TYPES)})")
    ap.add_argument("--list", action="store_true",
                    help="List existing helpers and exit (no creation)")
    ap.add_argument("--recreate", default="",
                    help="Comma-separated types to delete-and-recreate")
    args = ap.parse_args()

    requested = [t.strip() for t in args.types.split(",") if t.strip()]
    recreate = {t.strip() for t in args.recreate.split(",") if t.strip()}

    existing = list_existing_helpers()

    if args.list:
        print(json.dumps(existing, indent=2))
        return 0

    if recreate:
        for t in recreate:
            if t in existing:
                print(f"recreating helper for {t} (deleting {existing[t]})", file=sys.stderr)
                detach_and_delete(existing[t])
                del existing[t]

    result = dict(existing)
    for t in requested:
        if t in existing:
            print(f"helper-{t} already exists: {existing[t]}", file=sys.stderr)
            continue
        aid = create_helper(t)
        result[t] = aid
        print(f"created helper-{t}: {aid}", file=sys.stderr)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
