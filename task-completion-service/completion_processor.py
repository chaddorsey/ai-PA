"""Shared completion processing logic.

Handles archival memory lookup, passage updates, and follow-up routing
for completed OmniFocus tasks. Used by both the push endpoint and the
reconciliation poller.

2026-06-01: MC notification path rewired from direct HTTP POST
(/v1/agents/{MC}/messages) to pa_web.task_queue insert with
source='mc-completion'. Reason: LettaBot decommissioning + MC's
upcoming local-mode migration both make HTTP-to-MC delivery untenable.
The queue pattern matches the email-watch substrate established
2026-05-30; MC claims via `task queue-claim --source mc-completion`
when summoned.
"""
import os
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

# Local-mode push target — wakes MC's warm subprocess immediately after
# the queue row is written. Non-fatal on error: the row is durable in
# pa_web.task_queue and the 15-min launchd backup poller will catch up.
PUSH_RECEIVER_URL = os.environ.get(
    "LETTA_PUSH_RECEIVER_URL",
    "http://host.docker.internal:8099/push",
)


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
    client: httpx.AsyncClient,  # kept for signature compat; no longer used
) -> None:
    """Queue a task-completion event for MC via pa_web.task_queue.

    Source = 'mc-completion'. Local-mode MC claims via
    `task queue-claim --source mc-completion` when summoned. The pre-
    formatted human-readable message is in payload.message, ready for
    direct use by the agent; structured fields are also present for
    programmatic use.

    Idempotent on (source, source_ref). source_ref encodes task name +
    completion date + a UTC timestamp so two completions of the same
    task on different dates are NOT deduped.
    """
    # Build the human-readable message (same shape MC was getting
    # historically — preserve so prompt-side behavior is unchanged).
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
    message = "\n".join(lines)

    try:
        import asyncpg
    except Exception as e:
        logger.warning("mc_notify_asyncpg_import_failed", exc_info=e)
        return

    # Resolve DB URL from env (same pattern as gmail-watch-service).
    db_url = os.environ.get("PA_WEB_POSTGRES_URL")
    if not db_url:
        db_url = os.environ.get("DATABASE_URL", "")
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    if not db_url:
        password = os.environ.get("POSTGRES_PASSWORD", "")
        db_url = f"postgresql://postgres:{password}@supabase-db:5432/postgres"

    now_iso = datetime.now(timezone.utc).isoformat()
    # Source-ref uniqueness: task_name + completion_date + utc-now.
    # The utc-now prevents collisions if the same task is somehow
    # re-completed (rare; OmniFocus does allow uncomplete + recomplete).
    source_ref = f"{task_name}:{completion_date}:{now_iso}"
    payload = {
        "event_type": "task_completed",
        "task_name": task_name,
        "project_name": project_name,
        "completion_date": completion_date,
        "timing_summary": timing_summary,
        "extraction_info": extraction_info,
        "message": message,
        "occurred_at": now_iso,
    }
    payload_json = json.dumps(payload)

    try:
        conn = await asyncpg.connect(db_url, timeout=10.0)
        try:
            await conn.execute(
                """
                INSERT INTO pa_web.task_queue (source, source_ref, payload)
                VALUES ($1, $2, $3::jsonb)
                ON CONFLICT (source, source_ref) DO NOTHING
                """,
                "mc-completion",
                source_ref,
                payload_json,
            )
        finally:
            await conn.close()
        logger.info(
            "mc_completion_queued",
            extra={"task_name": task_name, "completion_date": completion_date},
        )
    except Exception as e:
        logger.warning("mc_notify_queue_write_failed", exc_info=e)
        return

    # Wake MC's warm subprocess via the push receiver. The row is
    # already durable in pa_web.task_queue, so failure here is non-fatal.
    push_prompt = (
        f"[Task Completed] {task_name}"
        + (f" (project: {project_name})" if project_name else "")
        + f" — completed {completion_date}."
        + (f" Timing: {timing_summary}." if timing_summary else "")
        + (
            f" Source extraction: ref_id={extraction_info.get('ref_id','')}, "
            f"follow_up_pending={extraction_info.get('has_external_origin', False)}."
            if extraction_info else ""
        )
        + " Claim from pa_web.task_queue source='mc-completion' "
        "(`task queue-claim --source mc-completion`) for full payload, "
        "then handle follow-up routing per your completion protocol."
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as push_client:
            r = await push_client.post(
                PUSH_RECEIVER_URL,
                json={
                    "agent": "mc",
                    "source": "mc-completion",
                    "source_ref": source_ref,
                    "prompt": push_prompt,
                    "priority": "normal",
                },
            )
            if r.status_code >= 400:
                logger.warning(
                    "mc_push_receiver_error",
                    extra={"status": r.status_code, "body": r.text[:200]},
                )
            else:
                logger.info("mc_push_receiver_accepted")
    except Exception as e:
        logger.warning("mc_push_receiver_unreachable", exc_info=e)
