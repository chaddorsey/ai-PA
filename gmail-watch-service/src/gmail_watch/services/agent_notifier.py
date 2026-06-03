"""Agent notification service.

Local-mode (2026-06-03): notifications go to the letta-push-receiver
at host.docker.internal:8099/push. The receiver routes by source slug
to per-agent warm letta-code subprocesses. The pa_web.task_queue
substrate is still the source of truth — receiver pushes are an
optimization to wake the agent immediately instead of waiting for the
15-min launchd backup poller.

History: the Docker-Letta push path (HTTPX → /v1/agents/<id>/messages)
was removed when the Docker Letta server was decommissioned. The dual-
target write to pa_web.task_queue remains the durable producer step.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from gmail_watch.models import WatchedThread
from gmail_watch.settings import settings
from gmail_watch.utils.interval_parser import format_interval

logger = logging.getLogger(__name__)

# letta-push-receiver dispatches by source slug. From inside Docker the
# host-side daemon is reachable via host.docker.internal.
PUSH_RECEIVER_URL = os.environ.get(
    "LETTA_PUSH_RECEIVER_URL",
    "http://host.docker.internal:8099/push",
)


class AgentNotifier:
    """Sends notifications to local-mode Letta agents via push receiver."""

    def __init__(
        self,
        letta_base_url: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        # Kept for backward compat with constructor signature; not used
        # for routing anymore.
        self.letta_base_url = letta_base_url or settings.letta_base_url
        self.agent_id = agent_id or settings.letta_agent_id

    async def _write_watch_event_to_queue(
        self,
        event_type: str,
        thread_id: str,
        message: str,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        """Write a watch event to pa_web.task_queue for the local agent to claim.

        Idempotent on (source, source_ref) — source_ref is
        '{event_type}:{thread_id}:{iso_timestamp}' so repeated events
        on the same thread aren't deduped (a second reply IS a new event).

        Best-effort: failure is logged but doesn't break the Docker push
        path. Source='email-watch' was added to the task_queue source
        CHECK constraint on 2026-05-30.
        """
        try:
            import asyncpg
        except Exception as e:
            logger.warning("task_queue_asyncpg_import_failed", error=str(e))
            return

        # Derive Postgres URL (mirror task_queue_writer.py logic).
        db_url = os.environ.get("PA_WEB_POSTGRES_URL")
        if not db_url:
            db_url = os.environ.get("DATABASE_URL", "")
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        if not db_url:
            password = os.environ.get("POSTGRES_PASSWORD", "")
            db_url = f"postgresql://postgres:{password}@supabase-db:5432/postgres"

        now_iso = datetime.now(timezone.utc).isoformat()
        source_ref = f"{event_type}:{thread_id}:{now_iso}"
        payload = {
            "event_type": event_type,
            "thread_id": thread_id,
            "message": message,
            "occurred_at": now_iso,
        }
        if extra:
            payload.update(extra)
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
                    "email-watch",
                    source_ref,
                    payload_json,
                )
            finally:
                await conn.close()
            logger.info(
                "watch_event_queued",
                event_type=event_type,
                thread_id=thread_id,
            )
        except Exception as e:
            logger.warning(
                "watch_event_queue_write_failed",
                event_type=event_type,
                thread_id=thread_id,
                error=str(e),
            )

    def _format_reply_message(
        self,
        thread: WatchedThread,
        from_address: str,
        preview: str,
        received_at: Optional[datetime] = None,
    ) -> str:
        """Format the notification message for a reply."""
        received_at = received_at or datetime.now(timezone.utc)
        created_at = thread.created_at or datetime.now(timezone.utc)

        # Format time nicely
        received_str = received_at.strftime("%Y-%m-%d at %I:%M %p")
        created_str = created_at.strftime("%b %d")

        recipients_str = ", ".join(thread.original_recipients or ["unknown"])

        # Truncate long previews
        max_preview_len = 500
        truncated_preview = preview[:max_preview_len]
        if len(preview) > max_preview_len:
            truncated_preview += "..."

        message = f"""[Gmail Watch] Reply received on monitored thread

**Subject:** {thread.subject or "(no subject)"}
**From:** {from_address}
**Received:** {received_str}

**Thread Context:**
- You started this thread on {created_str}
- Original recipient: {recipients_str}
- This is message #{thread.message_count} in the thread

**New Message Preview:**
"{truncated_preview}"

**Full message available via read_email(message_id="{thread.reply_message_id}")**"""

        return message

    def _format_watch_started_message(
        self,
        thread: WatchedThread,
    ) -> str:
        """Format acknowledgment message when watch starts."""
        recipients_str = ", ".join(thread.original_recipients or ["unknown"])

        followup_str = ""
        if thread.followup_seconds and thread.followup_due_at:
            interval_str = format_interval(thread.followup_seconds)
            due_date_str = thread.followup_due_at.strftime("%b %d")
            followup_str = (
                f"\n**Follow-up deadline:** {interval_str} "
                f"(due {due_date_str})"
            )

        message = f"""[Gmail Watch] Now monitoring thread

**Subject:** {thread.subject or "(no subject)"}
**Recipients:** {recipients_str}{followup_str}

I'll notify you when a reply is received."""

        return message

    async def notify_reply_received(
        self,
        thread: WatchedThread,
        new_message_id: str,
        from_address: str,
        preview: str,
    ) -> dict[str, Any]:
        """Send reply notification to Email Agent.

        Dual-target: writes to pa_web.task_queue (for local agent) AND
        pushes to the Docker agent via Letta API (for rollback safety).
        """
        message = self._format_reply_message(
            thread=thread,
            from_address=from_address,
            preview=preview,
        )
        await self._write_watch_event_to_queue(
            event_type="reply_received",
            thread_id=thread.thread_id,
            message=message,
            extra={
                "new_message_id": new_message_id,
                "from_address": from_address,
                "preview": preview[:500],
                "subject": thread.subject,
            },
        )
        return await self._send_to_agent(message)

    def _format_followup_message(
        self,
        thread: WatchedThread,
    ) -> str:
        """Format notification message for an overdue follow-up."""
        recipients_str = ", ".join(thread.original_recipients or ["unknown"])
        interval_str = (
            format_interval(thread.followup_seconds)
            if thread.followup_seconds
            else "unknown"
        )

        # Calculate how overdue
        now = datetime.now(timezone.utc)
        overdue_str = "now"
        if thread.followup_due_at:
            overdue_delta = now - thread.followup_due_at
            overdue_hours = overdue_delta.total_seconds() / 3600
            if overdue_hours >= 48:
                overdue_str = f"{overdue_hours / 24:.0f} days ago"
            elif overdue_hours >= 1:
                overdue_str = f"{overdue_hours:.0f} hours ago"
            else:
                overdue_str = "just now"

        message = f"""[Gmail Watch] Follow-up needed — no reply received

**Subject:** {thread.subject or "(no subject)"}
**Recipients:** {recipients_str}
**Watch interval:** {interval_str}
**Follow-up was due:** {overdue_str}
**Messages in thread:** {thread.message_count}

No reply has been received. Consider following up.
Use read_email(thread_id="{thread.thread_id}") to review, or reply_to_email() to follow up."""

        return message

    async def notify_followup_needed(
        self,
        thread: WatchedThread,
    ) -> dict[str, Any]:
        """Send follow-up needed notification (dual-target: pa_web + Docker)."""
        message = self._format_followup_message(thread)
        await self._write_watch_event_to_queue(
            event_type="followup_needed",
            thread_id=thread.thread_id,
            message=message,
            extra={
                "subject": thread.subject,
                "followup_due_at": thread.followup_due_at.isoformat()
                                   if thread.followup_due_at else None,
                "message_count": thread.message_count,
            },
        )
        return await self._send_to_agent(message)

    async def notify_watch_started(
        self,
        thread: WatchedThread,
    ) -> dict[str, Any]:
        """Send watch started acknowledgment (dual-target)."""
        message = self._format_watch_started_message(thread)
        await self._write_watch_event_to_queue(
            event_type="watch_started",
            thread_id=thread.thread_id,
            message=message,
            extra={"subject": thread.subject},
        )
        return await self._send_to_agent(message)

    async def notify_watch_started_simple(
        self,
        subject: str,
        recipients: list[str],
        interval_str: str,
        followup_due_at: datetime,
    ) -> dict[str, Any]:
        """Send watch-started notification with simple params (for BCC auto-watch)."""
        recipients_str = ", ".join(recipients) if recipients else "unknown"
        due_date_str = followup_due_at.strftime("%b %d at %I:%M %p")

        message = f"""[Gmail Watch] Auto-watching thread via BCC

**Subject:** {subject or "(no subject)"}
**Recipients:** {recipients_str}
**Follow-up deadline:** {interval_str} (due {due_date_str})

I'll notify you when a reply is received, or remind you if no reply arrives by the deadline."""

        return await self._send_to_agent(message)

    async def notify_task_queued(
        self,
        entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Notify Email Agent that new task queue entries are ready for extraction.

        Args:
            entries: List of dicts with message_id, subject, from, has_notes,
                     is_forward, marker_type, task_hint.
        """
        if not entries:
            return {"status": "ok", "message": "no entries"}

        lines = ["[Gmail Watch] New email tasks queued for extraction\n"]
        for entry in entries:
            from_addr = entry.get("from", "unknown")
            marker_type = entry.get("marker_type")
            task_hint = entry.get("task_hint")

            if marker_type and task_hint:
                tag = (
                    "explicit task"
                    if marker_type == "explicit"
                    else "pointer — expand from email"
                )
                lines.append(f"- **{task_hint}** from {from_addr} ({tag})")
            else:
                subject = entry.get("subject", "(no subject)")
                has_notes = entry.get("has_notes", False)
                notes_tag = " (with notes)" if has_notes else ""
                lines.append(f"- **{subject}** from {from_addr}{notes_tag}")

        lines.append(
            "\nCYCLE-1 INSTRUCTIONS: Entries are queued in pa_web.task_queue "
            "(source='email'). Do NOT call process_email_task_queue or "
            "trigger_task_extraction — those legacy paths are retired. "
            "Instead:\n"
            "  1. Call consume_queue(source='email', limit=20) to claim the "
            "pending row(s).\n"
            "  2. For each claimed row, call add_extracted_tasks_postgres(...) "
            "to land it in pa_web.tasks. Use origin='user-indicated' for "
            "forward-to-tasks/TaskQueue-label entries. For 'explicit' marker "
            "entries the task_hint IS the task description (use it as "
            "raw_description). For 'pointer' marker entries, read the full "
            "email and expand the hint into a complete task description.\n"
            "  3. The enrichment-scanner will pick up enrichment_state="
            "'pending' rows on its 30s tick and run the 4-tool chain.\n"
            "DUPLICATE-CHECK POLICY: rely on the DB's ON CONFLICT (ref_id) DO "
            "NOTHING — if you suspect a duplicate, attempt the insert anyway "
            "and trust the tool's status='exists' vs 'ok' return."
        )

        message = "\n".join(lines)
        return await self._send_to_agent(message, source="email")

    async def notify_spark_queue(
        self,
        entries: list[dict[str, Any]],
        agent_id: Optional[str] = None,
        source: str = "slack",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Notify the owner agent that new sparks are ready in pa_web.task_queue.

        `agent_id` is accepted for backward-compat but unused in local mode —
        routing happens via `source` slug.
        """
        if not entries:
            return {"status": "ok", "message": "no entries"}

        message = (
            f"[Task Queue] {len(entries)} new spark(s) in pa_web.task_queue "
            f"(source={source}). Apply your per-source extraction recipe: "
            "`task queue-claim --source <src> --limit 20`, extract per row, "
            "`task write` to pa_web.tasks, `task queue-mark`."
        )
        return await self._send_to_agent(message, source=source)

    async def notify_drive_task_queued(
        self,
        entries: list[dict[str, Any]],
        agent_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Notify the docs agent that drive comment tasks are queued.

        Args:
            entries: List of dicts with comment_id, doc_title, comment_text,
                     triggered_by, marker_type, task_hint.
            agent_id: Accepted for backward-compat; unused in local mode
                     (routing happens via source='google-docs-comment').
        """
        if not entries:
            return {"status": "ok", "message": "no entries"}

        lines = ["[Gmail Watch] New drive comment tasks queued for extraction\n"]
        for entry in entries:
            doc_title = entry.get("doc_title", "(untitled)")
            marker_type = entry.get("marker_type")
            task_hint = entry.get("task_hint")

            if marker_type and task_hint:
                tag = (
                    "explicit task"
                    if marker_type == "explicit"
                    else "pointer — expand from comment context"
                )
                lines.append(f"- **{task_hint}** on {doc_title} ({tag})")
            else:
                comment_text = entry.get("comment_text", "")[:80]
                lines.append(f"- Comment on **{doc_title}**: \"{comment_text}\"")

        lines.append(
            "\nCYCLE-1 INSTRUCTIONS: Entries are queued in pa_web.task_queue "
            "(source='google-docs-comment'). The legacy "
            "queued_tasks_from_drive block + add_extracted_tasks path is "
            "retired. Instead:\n"
            "  1. Call consume_queue(source='google-docs-comment', limit=20) "
            "to claim pending row(s).\n"
            "  2. For each claimed row, call add_extracted_tasks_postgres(...). "
            "Use origin='user-indicated' for explicitly-marked comments. "
            "For 'explicit' marker entries the task_hint IS the task "
            "description. For 'pointer' marker entries, use the comment and "
            "document context (the queue payload includes comment text, "
            "quoted passage, and surrounding context) to expand the hint. "
            "For entries without markers, compose a task from the comment "
            "and surrounding context.\n"
            "  3. The enrichment-scanner will pick up enrichment_state="
            "'pending' rows on its 30s tick and run the 4-tool chain.\n"
            "DUPLICATE-CHECK POLICY: rely on the DB's ON CONFLICT (ref_id) DO "
            "NOTHING — if you suspect a duplicate, attempt the insert anyway "
            "and trust the tool's status='exists' vs 'ok' return."
        )

        message = "\n".join(lines)
        return await self._send_to_agent(message, source="google-docs-comment")

    async def _send_to_agent(
        self,
        message: str,
        source: str = "email-watch",
        source_ref: Optional[str] = None,
    ) -> dict[str, Any]:
        """Push a notification to the receiver, routed by source slug.

        Receiver routes:
          email, email-watch       → email agent
          slack                    → pulse agent
          drive, meeting,
            google-docs-comment    → docs agent
          mc-completion            → mc agent

        Non-fatal on failure: the work is already in pa_web.task_queue
        (via _write_watch_event_to_queue or the task_queue_writer), and
        the 15-min launchd backup poller will sweep it within the SLA.
        """
        body: dict[str, Any] = {
            "source": source,
            "prompt": message,
            "priority": "normal",
        }
        if source_ref:
            body["source_ref"] = source_ref
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(PUSH_RECEIVER_URL, json=body)
                if response.status_code >= 400:
                    logger.warning(
                        "push_receiver_error",
                        status=response.status_code,
                        body=response.text[:200],
                        source=source,
                    )
                    return {
                        "status": "error",
                        "error": f"HTTP {response.status_code}: {response.text[:200]}",
                    }
                return {
                    "status": "ok",
                    "source": source,
                    "response": response.json(),
                }
        except Exception as e:
            # Receiver down → row is still in task_queue; poller will catch.
            logger.warning("push_receiver_unreachable", error=str(e), source=source)
            return {"status": "error", "error": str(e)}
