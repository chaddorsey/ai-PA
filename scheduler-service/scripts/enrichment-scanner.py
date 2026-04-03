#!/usr/local/bin/python3
"""
Enrichment Pipeline Scanner

Runs as a scheduler service script action every 30 seconds.
Queries archival for tasks needing enrichment and dispatches
focused messages to the dedicated enrichment conversation.

Supports three queries:
1. enrichment:none → dispatch "Enrich ref_id X" message
2. enrichment:in-progress >10 min → reset to none (timeout recovery)
3. enrichment:phase-a-complete + user-indicated >10 min → dispatch backtrace-only

Pipeline busy guard: skips dispatch if any recent in-progress task exists.
"""

import json
import logging
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [enrichment-scanner] %(levelname)s %(message)s",
)
log = logging.getLogger("enrichment-scanner")

LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.environ.get("TASKS_AGENT_ID", "agent-dd15479e-6543-400e-8463-b2a48b13cd4a")
CONV_ID = os.environ.get("ENRICHMENT_CONV_ID", "")
ARCHIVE_ID = os.environ.get("ARCHIVE_ID", "archive-f9bcaa87-7630-41c9-9694-41d46fc47d26")
PENDING_BLOCK_ID = os.environ.get("PENDING_ENRICHMENT_BLOCK_ID", "block-266ccbfc-4c8d-41ee-aedf-da8019daa387")
TIMEOUT_MINUTES = 10


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


def search_archival(query, limit=5):
    """Search archival passages by text substring."""
    encoded = urllib.request.quote(query)
    return letta_get(f"/v1/agents/{AGENT_ID}/archival-memory/?search={encoded}&limit={limit}")


def update_passage_tag(passage, new_enrichment_tag):
    """Update a passage's enrichment tag via delete + re-insert."""
    pid = passage.get("id", "")
    text = passage.get("text", "")
    tags = passage.get("tags", []) or []

    # Update enrichment in text
    text = re.sub(r"- Status: \S+", f"- Status: {new_enrichment_tag}", text)

    # Update enrichment in tags
    tags = [t for t in tags if not t.startswith("enrichment:")]
    tags.append(f"enrichment:{new_enrichment_tag}")

    # Delete old
    del_url = f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages/{pid}"
    try:
        urllib.request.urlopen(urllib.request.Request(del_url, method="DELETE"), timeout=10)
    except urllib.error.HTTPError:
        pass  # May already be deleted

    # Insert new
    ins_data = json.dumps({"text": text, "tags": tags}).encode("utf-8")
    ins_req = urllib.request.Request(
        f"{LETTA_BASE}/v1/archives/{ARCHIVE_ID}/passages",
        data=ins_data, headers={"Content-Type": "application/json"}, method="POST",
    )
    urllib.request.urlopen(ins_req, timeout=15)


def extract_ref_id(text):
    """Extract REF_ID from passage text."""
    m = re.search(r"REF_ID: (\S+)", text)
    return m.group(1) if m else None


def extract_timestamp(text):
    """Extract extracted timestamp from passage text."""
    m = re.search(r"- Extracted: (.+)$", text, re.MULTILINE)
    if m:
        try:
            return datetime.fromisoformat(m.group(1).strip())
        except (ValueError, TypeError):
            pass
    return None


def dispatch_enrichment(ref_id):
    """Send enrichment message to the dedicated conversation."""
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

    payload = {
        "messages": [{"role": "user", "content": message}],
    }
    if CONV_ID:
        payload["conversation_id"] = CONV_ID

    return letta_post(f"/v1/agents/{AGENT_ID}/messages/", payload)


def dispatch_backtrace_only(ref_id):
    """Send backtrace-only message for stuck phase-a-complete tasks."""
    message = (
        f"Task ref_id {ref_id} was refined but backtrace was not completed.\n"
        f'Call backtrace_task(ref_id="{ref_id}") and then call write_packet_info '
        f"with your synthesis of the results."
    )

    payload = {
        "messages": [{"role": "user", "content": message}],
    }
    if CONV_ID:
        payload["conversation_id"] = CONV_ID

    return letta_post(f"/v1/agents/{AGENT_ID}/messages/", payload)


def read_pending_block():
    """Read the pending_enrichment block for ref_ids needing enrichment."""
    try:
        data = letta_get(f"/v1/blocks/{PENDING_BLOCK_ID}")
        value = data.get("value", "").strip()
        if not value or value == "(empty)":
            return []
        return [line.strip() for line in value.split("\n") if line.strip() and line.strip() != "(empty)"]
    except Exception as e:
        log.error(f"Failed to read pending_enrichment block: {e}")
        return []


def remove_from_pending(ref_id):
    """Remove a ref_id from the pending_enrichment block."""
    try:
        data = letta_get(f"/v1/blocks/{PENDING_BLOCK_ID}")
        value = data.get("value", "")
        lines = [l.strip() for l in value.split("\n") if l.strip() and l.strip() != ref_id]
        new_value = "\n".join(lines) if lines else "(empty)"
        body = json.dumps({"value": new_value}).encode("utf-8")
        url = f"{LETTA_BASE}/v1/blocks/{PENDING_BLOCK_ID}"
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="PATCH")
        try:
            urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as e:
            if e.code in (307, 308):
                loc = e.headers.get("Location", "")
                req2 = urllib.request.Request(loc, data=body, headers={"Content-Type": "application/json"}, method="PATCH")
                urllib.request.urlopen(req2, timeout=10)
    except Exception as e:
        log.warning(f"Failed to remove {ref_id} from pending block: {e}")


def main():
    now = datetime.now(timezone.utc)

    # ── Read pending enrichment ref_ids from block ──
    pending_ref_ids = read_pending_block()

    if not pending_ref_ids:
        log.debug("No tasks needing enrichment")
        return

    log.info(f"Found {len(pending_ref_ids)} pending enrichment ref_id(s): {pending_ref_ids}")

    # ── Pipeline busy guard: check if agent is currently processing ──
    # Look for any ref_id that was dispatched recently (track via a simple state approach)
    # For now, process one at a time: take the first ref_id
    ref_id = pending_ref_ids[0]

    # Remove from pending block BEFORE dispatching (prevents duplicate dispatch on next cycle)
    remove_from_pending(ref_id)

    # Update archival passage tag to in-progress
    try:
        results = search_archival(ref_id, limit=3)
        passage = None
        for p in (results if isinstance(results, list) else []):
            if isinstance(p, dict) and f"REF_ID: {ref_id}" in p.get("text", ""):
                passage = p
                break
        if passage:
            update_passage_tag(passage, "in-progress")
            log.info(f"Set enrichment:in-progress for {ref_id}")
        else:
            log.warning(f"Archival passage not found for {ref_id}, dispatching anyway")
    except Exception as e:
        log.warning(f"Failed to update tag for {ref_id}: {e}")

    # Dispatch enrichment message
    log.info(f"Dispatching enrichment for {ref_id}")
    try:
        dispatch_enrichment(ref_id)
        log.info(f"Enrichment dispatched successfully for {ref_id}")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            log.warning(f"Agent busy (400) for {ref_id}, will retry next cycle")
            # Re-add to pending block for retry
            try:
                data = letta_get(f"/v1/blocks/{PENDING_BLOCK_ID}")
                value = data.get("value", "").strip()
                if value == "(empty)":
                    value = ref_id
                else:
                    value += f"\n{ref_id}"
                body = json.dumps({"value": value}).encode("utf-8")
                url = f"{LETTA_BASE}/v1/blocks/{PENDING_BLOCK_ID}"
                req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="PATCH")
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass
        else:
            log.error(f"Dispatch failed for {ref_id}: HTTP {e.code}")
    except Exception as e:
        log.error(f"Dispatch failed for {ref_id}: {e}")


if __name__ == "__main__":
    main()
