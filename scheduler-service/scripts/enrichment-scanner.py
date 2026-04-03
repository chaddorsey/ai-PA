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


def main():
    now = datetime.now(timezone.utc)

    # ── Query 1: Find tasks needing enrichment ──
    try:
        none_results = search_archival("enrichment:none", limit=10)
    except Exception as e:
        log.error(f"Archival search failed: {e}")
        sys.exit(1)

    # Filter to actual enrichment:none passages (substring search may return false positives)
    none_passages = []
    for p in (none_results if isinstance(none_results, list) else []):
        if not isinstance(p, dict):
            continue
        text = p.get("text", "")
        if "enrichment:none" not in text and "enrichment: none" not in text:
            continue
        if "REF_ID:" not in text:
            continue
        none_passages.append(p)

    # ── Query 2: Check for stuck in-progress tasks ──
    try:
        progress_results = search_archival("enrichment:in-progress", limit=5)
    except Exception:
        progress_results = []

    in_progress_recent = False
    for p in (progress_results if isinstance(progress_results, list) else []):
        if not isinstance(p, dict):
            continue
        text = p.get("text", "")
        if "enrichment:in-progress" not in text:
            continue

        # Check passage age via created_at (reflects when tag was set)
        created_at = p.get("created_at")
        if created_at:
            try:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                age_minutes = (now - created).total_seconds() / 60
                if age_minutes > TIMEOUT_MINUTES:
                    ref_id = extract_ref_id(text)
                    log.info(f"Resetting stuck in-progress task {ref_id} (age: {age_minutes:.0f}m)")
                    update_passage_tag(p, "none")
                else:
                    in_progress_recent = True
            except (ValueError, TypeError):
                in_progress_recent = True

    # ── Pipeline busy guard ──
    if in_progress_recent:
        log.debug("Pipeline busy — recent in-progress task exists, skipping cycle")
        return

    # ── Query 3: Check for stuck phase-a-complete user-indicated tasks ──
    try:
        phase_a_results = search_archival("enrichment:phase-a-complete", limit=5)
    except Exception:
        phase_a_results = []

    for p in (phase_a_results if isinstance(phase_a_results, list) else []):
        if not isinstance(p, dict):
            continue
        text = p.get("text", "")
        if "enrichment:phase-a-complete" not in text:
            continue
        if "user-indicated" not in text:
            continue
        # Check if PACKET INFO already exists
        if "PACKET INFO" in text:
            continue

        created_at = p.get("created_at")
        if created_at:
            try:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                age_minutes = (now - created).total_seconds() / 60
                if age_minutes > TIMEOUT_MINUTES:
                    ref_id = extract_ref_id(text)
                    if ref_id:
                        log.info(f"Dispatching backtrace-only for stuck phase-a-complete task {ref_id}")
                        try:
                            dispatch_backtrace_only(ref_id)
                        except Exception as e:
                            log.warning(f"Backtrace dispatch failed for {ref_id}: {e}")
            except (ValueError, TypeError):
                pass

    # ── Dispatch enrichment for oldest none task ──
    if not none_passages:
        log.debug("No tasks needing enrichment")
        return

    # Sort by extracted timestamp (oldest first)
    oldest = None
    oldest_ts = None
    for p in none_passages:
        ts = extract_timestamp(p.get("text", ""))
        if ts and (oldest_ts is None or ts < oldest_ts):
            oldest_ts = ts
            oldest = p

    if not oldest:
        oldest = none_passages[0]

    ref_id = extract_ref_id(oldest.get("text", ""))
    if not ref_id:
        log.error("Could not extract ref_id from passage")
        return

    # Set in-progress tag before dispatching
    log.info(f"Setting enrichment:in-progress for {ref_id}")
    try:
        update_passage_tag(oldest, "in-progress")
    except Exception as e:
        log.error(f"Failed to set in-progress tag for {ref_id}: {e}")
        return

    # Dispatch enrichment message
    log.info(f"Dispatching enrichment for {ref_id}")
    try:
        dispatch_enrichment(ref_id)
        log.info(f"Enrichment dispatched successfully for {ref_id}")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            log.warning(f"Agent busy (400) for {ref_id}, will retry next cycle")
        else:
            log.error(f"Dispatch failed for {ref_id}: HTTP {e.code}")
    except Exception as e:
        log.error(f"Dispatch failed for {ref_id}: {e}")


if __name__ == "__main__":
    main()
