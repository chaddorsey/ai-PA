"""Agent notification service for sending messages to Letta."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from gmail_watch.models import WatchedThread
from gmail_watch.settings import settings


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
        if thread.followup_days and thread.followup_due_at:
            due_date_str = thread.followup_due_at.strftime("%b %d")
            followup_str = (
                f"\n**Follow-up deadline:** {thread.followup_days} days "
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

    async def notify_watch_started(
        self,
        thread: WatchedThread,
    ) -> dict[str, Any]:
        """Send watch started acknowledgment to Email Agent."""
        message = self._format_watch_started_message(thread)
        return await self._send_to_agent(message)

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
