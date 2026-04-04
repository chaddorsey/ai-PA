#!/usr/local/bin/python3
"""
Enrichment Pipeline Scanner

Runs as a scheduler service script action every 30 seconds.
Two responsibilities:

1. SPARK DRAIN: If the spark_queue block has unprocessed sparks,
   nudge the tasks agent to call process_spark_queue().
   (Replaces the retired spark-queue-drain.sh cron job.)

2. ENRICHMENT DISPATCH: If the pending_enrichment block has ref_ids,
   dispatch a focused enrichment message to the dedicated enrichment
   conversation. One task per cycle.

Conversation lookup is by label ("enrichment-pipeline") at runtime,
not by static ID. This makes weekly conversation resets simple —
just delete and recreate with the same label.
"""

import json
import logging
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [enrichment-scanner] %(levelname)s %(message)s",
)
log = logging.getLogger("enrichment-scanner")

LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.environ.get("TASKS_AGENT_ID", "agent-dd15479e-6543-400e-8463-b2a48b13cd4a")
ARCHIVE_ID = os.environ.get("ARCHIVE_ID", "archive-f9bcaa87-7630-41c9-9694-41d46fc47d26")
PENDING_BLOCK_ID = os.environ.get("PENDING_ENRICHMENT_BLOCK_ID", "block-266ccbfc-4c8d-41ee-aedf-da8019daa387")
SPARK_BLOCK_ID = os.environ.get("SPARK_QUEUE_BLOCK_ID", "block-534bb56d-f7f1-4ea4-b2d9-20dc75eca03a")
CONV_LABEL = "enrichment-pipeline"


# ── HTTP helpers ──

def letta_get(path, timeout=15):
    """GET request to Letta API with redirect handling."""
    url = f"{LETTA_BASE}{path}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307, 308):
            loc = e.headers.get("Location", "")
            req2 = urllib.request.Request(loc)
            with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                return json.loads(resp2.read().decode("utf-8"))
        raise


def letta_post(path, data, timeout=120):
    """POST request to Letta API with redirect handling."""
    url = f"{LETTA_BASE}{path}"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307, 308):
            loc = e.headers.get("Location", "")
            req2 = urllib.request.Request(loc, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                return json.loads(resp2.read().decode("utf-8"))
        raise


def letta_patch(path, data, timeout=10):
    """PATCH request to Letta API with redirect handling."""
    url = f"{LETTA_BASE}{path}"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (307, 308):
            loc = e.headers.get("Location", "")
            req2 = urllib.request.Request(loc, data=body, headers={"Content-Type": "application/json"}, method="PATCH")
            with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                return json.loads(resp2.read().decode("utf-8"))
        raise


# ── Conversation lookup ──

_cached_conv_id = None


def resolve_conversation_id():
    """Look up enrichment conversation by label. Cached for the process lifetime."""
    global _cached_conv_id
    if _cached_conv_id:
        return _cached_conv_id

    try:
        convs = letta_get(f"/v1/conversations/?agent_id={AGENT_ID}")
        if isinstance(convs, list):
            for c in convs:
                # Labels may not be returned by list API — try matching by checking each
                cid = c.get("id", "")
                if c.get("label") == CONV_LABEL:
                    _cached_conv_id = cid
                    return cid
            # If label not in list response, try each conversation
            # (Letta v0.16 may not return labels in list)
            # Fall back to env var if set
            env_id = os.environ.get("ENRICHMENT_CONV_ID", "")
            if env_id:
                _cached_conv_id = env_id
                return env_id
    except Exception as e:
        log.warning(f"Conversation lookup failed: {e}")

    # Final fallback
    env_id = os.environ.get("ENRICHMENT_CONV_ID", "")
    if env_id:
        _cached_conv_id = env_id
    return env_id


# ── Block helpers ──

def read_block(block_id):
    """Read a Letta memory block value."""
    try:
        data = letta_get(f"/v1/blocks/{block_id}")
        return data.get("value", "").strip()
    except Exception as e:
        log.error(f"Failed to read block {block_id}: {e}")
        return ""


def write_block(block_id, value):
    """Write a Letta memory block value."""
    letta_patch(f"/v1/blocks/{block_id}", {"value": value})


# ── Spark drain ──

def check_spark_queue():
    """If spark queue has unprocessed sparks, nudge the tasks agent."""
    value = read_block(SPARK_BLOCK_ID)

    if not value or "(empty)" in value or len(value) < 30:
        return

    # Count entries
    entry_count = value.count('"spark_id"')
    if entry_count == 0:
        return

    log.info(f"Spark queue has {entry_count} unprocessed spark(s), nudging agent")

    message = (
        f"[Spark Queue Poll] {entry_count} unprocessed spark(s). "
        "Call process_spark_queue()."
    )

    try:
        letta_post(f"/v1/agents/{AGENT_ID}/messages/", {
            "messages": [{"role": "user", "content": message}],
        })
        log.info("Tasks agent nudged for spark processing")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            log.debug("Agent busy, spark nudge will retry next cycle")
        else:
            log.warning(f"Spark nudge failed: HTTP {e.code}")
    except Exception as e:
        log.warning(f"Spark nudge failed: {e}")


# ── Enrichment dispatch ──

def dispatch_to_conversation(conv_id, message):
    """Send a message to the enrichment conversation via SSE endpoint.

    Uses POST /v1/conversations/{id}/messages (no trailing slash).
    Reads the full SSE stream — closing early cancels agent processing.
    """
    url = f"{LETTA_BASE}/v1/conversations/{conv_id}/messages"
    body = json.dumps({"input": message}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as resp:
        response_data = resp.read().decode("utf-8", "replace")
        tool_calls = response_data.count('"tool_call_message"')
        return {"status": "dispatched", "tool_calls": tool_calls}


def dispatch_enrichment(ref_id, conv_id):
    """Send enrichment message for a task."""
    message = (
        f"Enrich task ref_id {ref_id}.\n"
        f'Step 1: Call fetch_source_content(ref_id="{ref_id}") to get the full source content.\n'
        f"Step 2: Read the content and formulate a clear, specific task name. "
        f'Call refine_task_description(ref_id="{ref_id}", new_description="your refined name").\n'
        f"Step 3: If backtrace materials are returned in the response, read them and call "
        f"write_packet_info with your synthesis of the three-node model, context brief, "
        f"resources, and knowns/unknowns.\n"
        f"If no backtrace materials are returned, you are done after Step 2."
    )

    if conv_id:
        return dispatch_to_conversation(conv_id, message)
    else:
        # Fallback: agent messages endpoint (no conversation isolation)
        return letta_post(f"/v1/agents/{AGENT_ID}/messages/", {
            "messages": [{"role": "user", "content": message}],
        })


def process_enrichment():
    """Check pending_enrichment block and dispatch one task."""
    value = read_block(PENDING_BLOCK_ID)
    if not value or value == "(empty)":
        return

    pending = [l.strip() for l in value.split("\n") if l.strip() and l.strip() != "(empty)"]
    if not pending:
        return

    log.info(f"Found {len(pending)} pending enrichment ref_id(s)")

    ref_id = pending[0]

    # Remove from pending before dispatch (prevents duplicate on next cycle)
    remaining = [r for r in pending[1:]]
    write_block(PENDING_BLOCK_ID, "\n".join(remaining) if remaining else "(empty)")

    # Update archival tag to in-progress
    try:
        results = letta_get(f"/v1/agents/{AGENT_ID}/archival-memory/?search={ref_id}&limit=3")
        for p in (results if isinstance(results, list) else []):
            if isinstance(p, dict) and f"REF_ID: {ref_id}" in p.get("text", ""):
                pid = p["id"]
                text = re.sub(r"- Status: \S+", "- Status: in-progress", p["text"])
                tags = [t for t in (p.get("tags") or []) if not t.startswith("enrichment:")]
                tags.append("enrichment:in-progress")
                try:
                    urllib.request.urlopen(urllib.request.Request(
                        f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages/{pid}", method="DELETE"
                    ), timeout=10)
                except urllib.error.HTTPError:
                    pass
                ins_data = json.dumps({"text": text, "tags": tags}).encode("utf-8")
                urllib.request.urlopen(urllib.request.Request(
                    f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages",
                    data=ins_data, headers={"Content-Type": "application/json"}, method="POST",
                ), timeout=15)
                log.info(f"Set enrichment:in-progress for {ref_id}")
                break
    except Exception as e:
        log.warning(f"Failed to update tag for {ref_id}: {e}")

    # Resolve conversation and dispatch
    conv_id = resolve_conversation_id()
    if not conv_id:
        log.error("No enrichment conversation found — cannot dispatch")
        # Re-add to pending for retry
        write_block(PENDING_BLOCK_ID, ref_id if not remaining else f"{ref_id}\n" + "\n".join(remaining))
        return

    log.info(f"Dispatching enrichment for {ref_id} to conversation {conv_id}")
    try:
        result = dispatch_enrichment(ref_id, conv_id)
        log.info(f"Enrichment complete for {ref_id}: {result.get('tool_calls', '?')} tool calls")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            log.warning(f"Agent busy (400) for {ref_id}, re-queuing")
            current = read_block(PENDING_BLOCK_ID)
            if current == "(empty)":
                write_block(PENDING_BLOCK_ID, ref_id)
            else:
                write_block(PENDING_BLOCK_ID, f"{current}\n{ref_id}")
        else:
            log.error(f"Dispatch failed for {ref_id}: HTTP {e.code}")
    except Exception as e:
        log.error(f"Dispatch failed for {ref_id}: {e}")


# ── Main ──

def main():
    # 1. Spark drain — check if spark queue needs processing
    check_spark_queue()

    # 2. Enrichment dispatch — process one pending task
    process_enrichment()


if __name__ == "__main__":
    main()
