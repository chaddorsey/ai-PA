"""Shared completion processing logic.

Handles task-lookup, status updates, and follow-up routing for
completed OmniFocus tasks. Used by both the push endpoint and the
reconciliation poller.

History:
- 2026-06-01: MC notification path rewired from direct HTTP POST
  (/v1/agents/{MC}/messages) to pa_web.task_queue insert with
  source='mc-completion'. The queue pattern matches the email-watch
  substrate established 2026-05-30; MC claims via `task queue-claim
  --source mc-completion` when summoned.
- 2026-06-04: Archival-memory passage lookup + rewrite removed.
  Replaced with direct UPDATE against pa_web.tasks (omnifocus_id is
  a first-class column). The Docker Letta server is being
  decommissioned; archival becomes a read-only museum, and
  pa_web.tasks is the canonical task substrate.
"""
import os
import re
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger("completion-processor")

MC_AGENT_ID = "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef"

# Local-mode push target — wakes MC's warm subprocess immediately after
# the queue row is written. Non-fatal on error: the row is durable in
# pa_web.task_queue and the 15-min launchd backup poller will catch up.
PUSH_RECEIVER_URL = os.environ.get(
    "LETTA_PUSH_RECEIVER_URL",
    "http://host.docker.internal:8099/push",
)


def _resolve_pg_url() -> str:
    db_url = os.environ.get("PA_WEB_POSTGRES_URL")
    if db_url:
        return db_url
    db_url = os.environ.get("DATABASE_URL", "")
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    if db_url:
        return db_url
    password = os.environ.get("POSTGRES_PASSWORD", "")
    return f"postgresql://postgres:{password}@supabase-db:5432/postgres"


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
    """Look up a pa_web.tasks row by its OmniFocus task ID.

    `client` is accepted for backward-compat with the old archival
    signature; not used (we go directly to Postgres via asyncpg).

    Returns the row as a dict, or None if no matching row exists.
    Skip sentinel values ('pending', 'TEMP', '') — those indicate a
    task that's queued for OF sync but doesn't have a real OF id yet.
    """
    if not task_id or task_id in ("pending", "TEMP"):
        return None
    try:
        import asyncpg
    except Exception as e:
        logger.warning("find_extracted_task asyncpg import failed: %s", e)
        return None
    try:
        conn = await asyncpg.connect(_resolve_pg_url(), timeout=10.0)
        try:
            row = await conn.fetchrow(
                """SELECT ref_id, source, status, omnifocus_id,
                          source_metadata, raw_description, closed_at
                     FROM pa_web.tasks
                    WHERE omnifocus_id = $1
                    LIMIT 1""",
                task_id,
            )
        finally:
            await conn.close()
    except Exception as e:
        logger.warning("find_extracted_task pg lookup failed for %s: %s",
                       task_id, e)
        return None
    return dict(row) if row else None


async def update_passage_completed(
    row: dict,
    completion_date: str,
    was_dropped: bool,
    client: httpx.AsyncClient,
) -> dict:
    """Mark a pa_web.tasks row as completed/rejected on OF sync-back.

    `client` is accepted for backward-compat (unused). Returns the
    routing metadata that notify_mc uses to compose the completion
    summary.
    """
    new_status = "rejected" if was_dropped else "completed"

    # Parse completion_date into a tz-aware datetime for closed_at. Accept
    # ISO 8601 in any form; fall back to NOW() if parsing fails so we
    # never lose the close.
    try:
        ts = datetime.fromisoformat(completion_date.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except Exception:
        ts = datetime.now(timezone.utc)

    try:
        import asyncpg
    except Exception as e:
        logger.warning("update pa_web.tasks asyncpg import failed: %s", e)
    else:
        try:
            conn = await asyncpg.connect(_resolve_pg_url(), timeout=10.0)
            try:
                await conn.execute(
                    """UPDATE pa_web.tasks
                          SET status = $1,
                              closed_at = $2,
                              updated_at = NOW()
                        WHERE ref_id = $3""",
                    new_status, ts, row.get("ref_id"),
                )
            finally:
                await conn.close()
        except Exception as e:
            logger.warning(
                "pa_web.tasks completion update failed for ref_id=%s: %s",
                row.get("ref_id"), e,
            )

    # Routing metadata for MC notification. source_metadata holds the
    # from_person and similar producer-captured fields.
    smeta = row.get("source_metadata") or {}
    if isinstance(smeta, str):
        try:
            smeta = json.loads(smeta)
        except Exception:
            smeta = {}
    from_person = smeta.get("from_person", "") or ""
    has_external_origin = bool(from_person) and "Chad Dorsey" not in from_person

    return {
        "ref_id": row.get("ref_id", ""),
        "source_type": row.get("source", "") or "",
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
