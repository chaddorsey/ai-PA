"""Shared completion processing logic.

Handles archival memory lookup, passage updates, and follow-up routing
for completed OmniFocus tasks. Used by both the push endpoint and the
reconciliation poller.
"""
import re
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger("completion-processor")

LETTA_BASE_URL = "http://letta:8283"
# Note: archive API not used — we use agent archival memory API which includes shared archives
# This is tasks-agent-sleeptime — the agent whose archival memory stores extracted task passages
TASKS_AGENT_ID = "agent-62edcfac-2cc7-41a5-a3c2-d417da393397"
MC_AGENT_ID = "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef"


def parse_timing_from_note(note: str) -> Optional[str]:
    """Extract timing summary from Time Tracking block in task note."""
    match = re.search(
        r"--- Time Tracking ---\n(.*?)\n--- End Time Tracking ---",
        note,
        re.DOTALL,
    )
    if not match:
        return None
    block = match.group(1)
    total_match = re.search(r"Total:\s*(.+)", block)
    sessions = re.findall(r"\[.+?\]\s+\S+", block)
    summary = f"{len(sessions)} session(s)"
    if total_match:
        summary += f", {total_match.group(1).strip()} active"
    return summary


async def find_extracted_task(task_id: str, client: httpx.AsyncClient) -> Optional[dict]:
    """Search archival memory for an extracted task passage matching this OmniFocus task ID."""
    url = f"{LETTA_BASE_URL}/v1/agents/{TASKS_AGENT_ID}/archival-memory"
    resp = await client.get(url, params={"search": task_id, "limit": 20})
    if resp.status_code != 200:
        logger.error(f"Archival search failed: {resp.status_code}")
        return None

    for passage in resp.json():
        text = passage.get("text", "")
        if f"- Task ID: {task_id}" in text and "status:confirmed" in str(passage.get("tags", [])):
            return passage
    return None


async def update_passage_completed(
    passage: dict,
    completion_date: str,
    was_dropped: bool,
    client: httpx.AsyncClient,
) -> dict:
    """Update an extracted task passage to completed/dropped status.

    Returns routing metadata for follow-up actions.
    """
    text = passage["text"]
    passage_id = passage["id"]
    status_word = "DROPPED" if was_dropped else "COMPLETED"

    # Prefix TASK line
    text = re.sub(r"^(TASK:\s*)", rf"TASK: [{status_word}] ", text, count=1)

    # Update status in OMNIFOCUS section
    text = re.sub(r"- Status:\s*\w+", f"- Status: {status_word.lower()}", text)

    # Add completion timestamp
    timestamp_line = f"- {'Dropped' if was_dropped else 'Completed'}: {completion_date}"
    text = re.sub(
        r"(TIMESTAMPS\n(?:- .+\n)*)",
        rf"\g<1>{timestamp_line}\n",
        text,
    )

    # Extract routing metadata
    source_type = ""
    from_person = ""
    m = re.search(r"- Type:\s*(.+)", text)
    if m:
        source_type = m.group(1).strip()
    m = re.search(r"- From:\s*(.+)", text)
    if m:
        from_person = m.group(1).strip()
    has_external_origin = bool(from_person) and "Chad Dorsey" not in from_person

    ref_id = ""
    m = re.search(r"REF_ID:\s*(\S+)", text)
    if m:
        ref_id = m.group(1)

    # Update tags
    old_tags = passage.get("tags", [])
    new_tags = [t for t in old_tags if not t.startswith("status:")]
    new_tags.append(f"status:{status_word.lower()}")

    # Insert new passage first, then delete old (safer ordering)
    insert_url = f"{LETTA_BASE_URL}/v1/agents/{TASKS_AGENT_ID}/archival-memory"
    insert_resp = await client.post(
        insert_url,
        json={"text": text, "tags": new_tags},
    )

    if insert_resp.status_code in (200, 201):
        delete_url = f"{LETTA_BASE_URL}/v1/agents/{TASKS_AGENT_ID}/archival-memory/{passage_id}"
        await client.delete(delete_url)

    return {
        "ref_id": ref_id,
        "source_type": source_type,
        "from_person": from_person,
        "has_external_origin": has_external_origin,
    }


async def notify_mc(
    task_name: str,
    project_name: Optional[str],
    completion_date: str,
    timing_summary: Optional[str],
    extraction_info: Optional[dict],
    client: httpx.AsyncClient,
) -> None:
    """Send a completion notification to Mission Control."""
    lines = [f"TASK COMPLETED: '{task_name}'"]
    if project_name:
        lines.append(f"Project: {project_name}")
    lines.append(f"Completed: {completion_date}")
    if timing_summary:
        lines.append(f"Timing: {timing_summary}")
    if extraction_info:
        ref = extraction_info.get("ref_id", "")
        src = extraction_info.get("source_type", "")
        ext = extraction_info.get("has_external_origin", False)
        lines.append(f"Extraction: ref_id {ref}, source: {src}, follow-up {'pending' if ext else 'none'}")

    content = "\n".join(lines)

    url = f"{LETTA_BASE_URL}/v1/agents/{MC_AGENT_ID}/messages/"
    resp = await client.post(
        url,
        json={"messages": [{"role": "system", "content": content}]},
        timeout=300.0,
    )
    if resp.status_code not in (200, 201):
        # Fall back to user role if system role rejected
        logger.warning(f"MC notification with system role failed ({resp.status_code}), retrying with user role")
        await client.post(
            url,
            json={"messages": [{"role": "user", "content": f"[SYSTEM NOTIFICATION] {content}"}]},
            timeout=300.0,
        )
