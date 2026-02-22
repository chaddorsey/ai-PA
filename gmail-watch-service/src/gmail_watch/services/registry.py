"""Thread registry service for managing watched threads."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gmail_watch.models import WatchedThread
from gmail_watch.utils.interval_parser import parse_interval, format_interval


class ThreadRegistry:
    """Manages the registry of watched Gmail threads."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def watch_thread(
        self,
        thread_id: str,
        subject: Optional[str] = None,
        recipients: Optional[list[str]] = None,
        followup_interval: Optional[str] = None,
        context: Optional[str] = None,
        source: str = "manual",
        bcc_address: Optional[str] = None,
        followup_due_at_override: Optional[datetime] = None,
        ignore_own_replies: bool = True,
        external_only: bool = False,
        watch_for_senders: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Register a thread for watching.

        Args:
            thread_id: Gmail thread ID to watch.
            subject: Email subject line (optional).
            recipients: List of original recipients (optional).
            followup_interval: Interval string like '3d', '12h', '1w' (optional).
            context: Additional context about why watching (optional).
            source: How the watch was created ('manual', 'bcc', etc.).
            bcc_address: BCC address that triggered the watch (optional).
            followup_due_at_override: Explicit due-at time (optional).
            ignore_own_replies: Skip own replies (default True).
            external_only: Only trigger on replies from outside own domain.
            watch_for_senders: Specific email addresses or @domains to trigger on.

        Returns:
            Dictionary with status and thread information.
        """
        # Check if already watching
        stmt = select(WatchedThread).where(WatchedThread.thread_id == thread_id)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            if existing.is_active:
                return {
                    "status": "already_watching",
                    "thread_id": thread_id,
                    "message": "Thread is already being watched",
                }
            # Reactivate
            existing.is_active = True
            existing.reply_received = False
            existing.reply_received_at = None
            await self.session.commit()
            return {
                "status": "reactivated",
                "thread_id": thread_id,
                "message": "Thread watch reactivated",
            }

        # Calculate followup timing
        followup_seconds = None
        followup_due_at = None
        if followup_interval:
            followup_seconds = parse_interval(followup_interval)
            if followup_due_at_override:
                followup_due_at = followup_due_at_override
            else:
                followup_due_at = datetime.now(timezone.utc) + timedelta(
                    seconds=followup_seconds
                )

        thread = WatchedThread(
            thread_id=thread_id,
            subject=subject,
            original_recipients=recipients,
            followup_seconds=followup_seconds,
            followup_due_at=followup_due_at,
            source=source,
            bcc_address=bcc_address,
            ignore_own_replies=ignore_own_replies,
            external_only=external_only,
            watch_for_senders=watch_for_senders,
            extra_data={"context": context} if context else None,
        )
        self.session.add(thread)
        await self.session.commit()

        return {
            "status": "ok",
            "thread_id": thread_id,
            "message": "Thread is now being watched",
            "followup_interval": format_interval(followup_seconds) if followup_seconds else None,
            "followup_due_at": followup_due_at.isoformat() if followup_due_at else None,
        }

    async def unwatch_thread(self, thread_id: str) -> dict[str, Any]:
        """Stop watching a thread.

        Args:
            thread_id: Gmail thread ID to stop watching.

        Returns:
            Dictionary with status information.
        """
        stmt = select(WatchedThread).where(WatchedThread.thread_id == thread_id)
        result = await self.session.execute(stmt)
        thread = result.scalar_one_or_none()

        if not thread:
            return {
                "status": "not_found",
                "thread_id": thread_id,
                "message": "Thread was not being watched",
            }

        thread.is_active = False
        await self.session.commit()

        return {
            "status": "ok",
            "thread_id": thread_id,
            "message": "Thread is no longer being watched",
        }

    async def list_watched(
        self,
        include_inactive: bool = False,
        include_replied: bool = False,
    ) -> dict[str, Any]:
        """List watched threads.

        Args:
            include_inactive: Include deactivated watches (default False).
            include_replied: Include threads that received replies (default False).

        Returns:
            Dictionary with list of watched threads.
        """
        stmt = select(WatchedThread)

        if not include_inactive:
            stmt = stmt.where(WatchedThread.is_active == True)  # noqa: E712
        if not include_replied:
            stmt = stmt.where(WatchedThread.reply_received == False)  # noqa: E712

        stmt = stmt.order_by(WatchedThread.created_at.desc())

        result = await self.session.execute(stmt)
        threads = result.scalars().all()

        return {
            "status": "ok",
            "count": len(threads),
            "threads": [
                {
                    "thread_id": t.thread_id,
                    "subject": t.subject,
                    "is_active": t.is_active,
                    "reply_received": t.reply_received,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "followup_interval": (
                        format_interval(t.followup_seconds)
                        if t.followup_seconds
                        else None
                    ),
                    "followup_due_at": (
                        t.followup_due_at.isoformat() if t.followup_due_at else None
                    ),
                    "source": t.source,
                    "ignore_own_replies": t.ignore_own_replies,
                    "external_only": t.external_only,
                    "watch_for_senders": t.watch_for_senders,
                }
                for t in threads
            ],
        }

    async def get_watch_status(self, thread_id: str) -> dict[str, Any]:
        """Get detailed status of a watched thread.

        Args:
            thread_id: Gmail thread ID to get status for.

        Returns:
            Dictionary with detailed thread status or not_found.
        """
        stmt = select(WatchedThread).where(WatchedThread.thread_id == thread_id)
        result = await self.session.execute(stmt)
        thread = result.scalar_one_or_none()

        if not thread:
            return {"status": "not_found", "thread_id": thread_id}

        return {
            "status": "ok",
            "thread_id": thread.thread_id,
            "subject": thread.subject,
            "is_active": thread.is_active,
            "reply_received": thread.reply_received,
            "reply_received_at": (
                thread.reply_received_at.isoformat()
                if thread.reply_received_at
                else None
            ),
            "created_at": (
                thread.created_at.isoformat() if thread.created_at else None
            ),
            "followup_interval": (
                format_interval(thread.followup_seconds)
                if thread.followup_seconds
                else None
            ),
            "followup_due_at": (
                thread.followup_due_at.isoformat() if thread.followup_due_at else None
            ),
            "followup_notified": thread.followup_notified,
            "source": thread.source,
            "bcc_address": thread.bcc_address,
            "message_count": thread.message_count,
            "ignore_own_replies": thread.ignore_own_replies,
            "external_only": thread.external_only,
            "watch_for_senders": thread.watch_for_senders,
            "extra_data": thread.extra_data,
        }

    async def get_active_thread_ids(self) -> set[str]:
        """Return set of all active watched thread IDs.

        Returns:
            Set of thread IDs that are actively being watched.
        """
        stmt = select(WatchedThread.thread_id).where(
            WatchedThread.is_active == True,  # noqa: E712
            WatchedThread.reply_received == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return {row[0] for row in result.all()}

    async def mark_reply_received(
        self,
        thread_id: str,
        message_id: str,
    ) -> Optional[WatchedThread]:
        """Mark a thread as having received a reply.

        Args:
            thread_id: Gmail thread ID that received a reply.
            message_id: Gmail message ID of the reply.

        Returns:
            The updated WatchedThread if found and updated, None otherwise.
        """
        stmt = select(WatchedThread).where(WatchedThread.thread_id == thread_id)
        result = await self.session.execute(stmt)
        thread = result.scalar_one_or_none()

        if thread and thread.is_active and not thread.reply_received:
            thread.reply_received = True
            thread.reply_received_at = datetime.now(timezone.utc)
            thread.reply_message_id = message_id
            thread.message_count += 1
            thread.last_activity_at = datetime.now(timezone.utc)
            await self.session.commit()
            return thread

        return None
