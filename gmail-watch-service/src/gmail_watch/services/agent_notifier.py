"""Agent notification service for sending messages to Letta."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from gmail_watch.models import WatchedThread
from gmail_watch.settings import settings
from gmail_watch.utils.interval_parser import format_interval


class AgentNotifier:
    """Sends notifications to Letta Email Agent."""

    def __init__(
        self,
        letta_base_url: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        self.letta_base_url = letta_base_url or settings.letta_base_url
        self.agent_id = agent_id or settings.letta_agent_id

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
        """Send reply notification to Email Agent."""
        message = self._format_reply_message(
            thread=thread,
            from_address=from_address,
            preview=preview,
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
        """Send follow-up needed notification to Email Agent."""
        message = self._format_followup_message(thread)
        return await self._send_to_agent(message)

    async def notify_watch_started(
        self,
        thread: WatchedThread,
    ) -> dict[str, Any]:
        """Send watch started acknowledgment to Email Agent."""
        message = self._format_watch_started_message(thread)
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
            "\nIMPORTANT: Do NOT call process_email_task_queue — the entries are "
            "already queued in your queued_tasks_from_email memory block. "
            "Read each entry from the block, then call trigger_task_extraction() "
            "for each one with source_type='email' and the entry's message_id, "
            "subject, and snippet. "
            "Use origin='user-indicated' (these tasks were explicitly queued by the user "
            "via forward-to-tasks or TaskQueue label). "
            'For "explicit" marker entries, the task_hint IS the task description. '
            'For "pointer" marker entries, read the full email and expand the hint '
            "into a complete task. "
            "Remove each entry from the block after successful extraction."
        )

        message = "\n".join(lines)
        return await self._send_to_agent(message)

    async def notify_drive_task_queued(
        self,
        entries: list[dict[str, Any]],
        agent_id: str,
    ) -> dict[str, Any]:
        """Notify Docs & Transcripts Agent that drive comment tasks are queued.

        Args:
            entries: List of dicts with comment_id, doc_title, comment_text,
                     triggered_by, marker_type, task_hint.
            agent_id: Target agent ID (Docs & Transcripts agent).
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
            "\nEntries are enriched with Drive API data (comment text, "
            "quoted passage, surrounding context). Extract tasks from the "
            "queued_tasks_from_drive block using add_extracted_tasks. "
            "Use origin='user-indicated' (these tasks were explicitly marked by the user "
            "in document comments). "
            'For "explicit" marker entries, the task_hint IS the task description. '
            'For "pointer" marker entries, use the comment and document context '
            "to expand the hint into a complete task. "
            "For entries without markers, compose a task from the comment text "
            "and surrounding context. "
            "Remove each entry from the block after extraction."
        )

        message = "\n".join(lines)

        # Temporarily target the Docs & Transcripts agent
        original_agent_id = self.agent_id
        self.agent_id = agent_id
        try:
            return await self._send_to_agent(message)
        finally:
            self.agent_id = original_agent_id

    async def _send_to_agent(self, message: str) -> dict[str, Any]:
        """Send a message to the Letta agent."""
        url = f"{self.letta_base_url}/v1/agents/{self.agent_id}/messages"

        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": message,
                }
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()

                return {
                    "status": "ok",
                    "agent_id": self.agent_id,
                    "response": response.json(),
                }
        except httpx.HTTPStatusError as e:
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }
