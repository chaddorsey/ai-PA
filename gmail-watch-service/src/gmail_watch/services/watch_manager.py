"""Watch manager orchestrator for Gmail watch service."""

from __future__ import annotations

import base64
import re
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gmail_watch.models import Notification, SyncState, WatchedThread
from gmail_watch.services.agent_notifier import AgentNotifier
from gmail_watch.services.gmail_client import GmailClient
from gmail_watch.services.pubsub_puller import PubSubPuller
from gmail_watch.services.registry import ThreadRegistry
from gmail_watch.services.drive_enricher import DriveEnricher
from gmail_watch.services.drive_task_queue_writer import DriveTaskQueueWriter
from gmail_watch.services.task_queue_writer import TaskQueueWriter
from gmail_watch.settings import settings
from gmail_watch.utils.interval_parser import (
    extract_interval_from_address,
    extract_watch_params_from_address,
    format_interval,
)

# Default threshold for watch renewal (1 day before expiration)
DEFAULT_RENEWAL_THRESHOLD_HOURS = 24

# Sync state uses single-row pattern with id=1
SYNC_STATE_ID = 1


class WatchManager:
    """Orchestrates Gmail watch, Pub/Sub polling, and agent notifications."""

    def __init__(
        self,
        gmail_client: Optional[GmailClient] = None,
        pubsub_puller: Optional[PubSubPuller] = None,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Initialize the WatchManager.

        Args:
            gmail_client: Gmail API client (optional, creates default if None).
            pubsub_puller: Pub/Sub puller (optional, creates default if None).
            session: Database session (optional).
        """
        self._gmail_client = gmail_client or GmailClient()
        self._pubsub_puller = pubsub_puller or PubSubPuller()
        self._session = session
        self._registry: Optional[ThreadRegistry] = None
        self._notifier: Optional[AgentNotifier] = None
        self._task_queue_writer: Optional[TaskQueueWriter] = None
        self._drive_task_queue_writer: Optional[DriveTaskQueueWriter] = None
        self._drive_enricher: Optional[DriveEnricher] = None

    @property
    def registry(self) -> ThreadRegistry:
        """Lazy-load thread registry."""
        if self._registry is None:
            self._registry = ThreadRegistry(self._session)
        return self._registry

    @property
    def notifier(self) -> AgentNotifier:
        """Lazy-load agent notifier."""
        if self._notifier is None:
            self._notifier = AgentNotifier()
        return self._notifier

    @property
    def task_queue_writer(self) -> TaskQueueWriter:
        """Lazy-load task queue writer."""
        if self._task_queue_writer is None:
            self._task_queue_writer = TaskQueueWriter()
        return self._task_queue_writer

    @property
    def drive_task_queue_writer(self) -> DriveTaskQueueWriter:
        """Lazy-load drive task queue writer."""
        if self._drive_task_queue_writer is None:
            self._drive_task_queue_writer = DriveTaskQueueWriter()
        return self._drive_task_queue_writer

    @property
    def drive_enricher(self) -> Optional[DriveEnricher]:
        """Lazy-load Drive API enricher (None if no token configured)."""
        if self._drive_enricher is None and settings.drive_token_path:
            self._drive_enricher = DriveEnricher(settings.drive_token_path)
        return self._drive_enricher

    async def _get_sync_state(self) -> Optional[SyncState]:
        """Get the current sync state from database.

        Returns:
            SyncState if exists, None otherwise.
        """
        stmt = select(SyncState).where(SyncState.id == SYNC_STATE_ID)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _update_sync_state(
        self,
        history_id: Optional[int] = None,
        watch_expiration: Optional[datetime] = None,
        watch_resource_id: Optional[str] = None,
        last_pull_at: Optional[datetime] = None,
        last_notification_at: Optional[datetime] = None,
    ) -> SyncState:
        """Update or create sync state.

        Args:
            history_id: New history ID from Gmail.
            watch_expiration: Watch expiration timestamp.
            watch_resource_id: Watch resource ID from Gmail.
            last_pull_at: Last successful pull timestamp.
            last_notification_at: Last notification timestamp.

        Returns:
            Updated or created SyncState.
        """
        sync_state = await self._get_sync_state()

        if sync_state is None:
            # Create new sync state
            sync_state = SyncState(
                id=SYNC_STATE_ID,
                history_id=history_id or 0,
                watch_expiration=watch_expiration,
                watch_resource_id=watch_resource_id,
                last_pull_at=last_pull_at,
                last_notification_at=last_notification_at,
            )
            self._session.add(sync_state)
        else:
            # Update existing
            if history_id is not None:
                sync_state.history_id = history_id
            if watch_expiration is not None:
                sync_state.watch_expiration = watch_expiration
            if watch_resource_id is not None:
                sync_state.watch_resource_id = watch_resource_id
            if last_pull_at is not None:
                sync_state.last_pull_at = last_pull_at
            if last_notification_at is not None:
                sync_state.last_notification_at = last_notification_at

        await self._session.commit()
        return sync_state

    async def _record_error(self, error_message: str) -> None:
        """Record an error in sync state.

        Args:
            error_message: Error message to record.
        """
        sync_state = await self._get_sync_state()
        if sync_state:
            sync_state.error_count += 1
            sync_state.last_error = error_message
            sync_state.last_error_at = datetime.now(timezone.utc)
            await self._session.commit()

    async def _log_notification(
        self,
        thread_id: str,
        notification_type: str,
        message_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        message_sent: Optional[str] = None,
        extra_data: Optional[dict[str, Any]] = None,
    ) -> Notification:
        """Log a notification to the database.

        Args:
            thread_id: Gmail thread ID.
            notification_type: Type of notification (e.g., "reply_received").
            message_id: Gmail message ID (optional).
            agent_id: Letta agent ID (optional).
            message_sent: Message content sent to agent (optional).
            extra_data: Additional metadata (optional).

        Returns:
            Created Notification record.
        """
        notification = Notification(
            thread_id=thread_id,
            notification_type=notification_type,
            message_id=message_id,
            agent_id=agent_id,
            message_sent=message_sent,
            extra_data=extra_data,
        )
        self._session.add(notification)
        await self._session.commit()
        return notification

    def _extract_header(
        self, message: dict[str, Any], header_name: str
    ) -> Optional[str]:
        """Extract a header value from a Gmail message.

        Args:
            message: Gmail message object.
            header_name: Header name to extract (e.g., "From", "Subject").

        Returns:
            Header value if found, None otherwise.
        """
        payload = message.get("payload", {})
        headers = payload.get("headers", [])

        for header in headers:
            if header.get("name", "").lower() == header_name.lower():
                return header.get("value")

        return None

    def _extract_email_address(self, from_header: str) -> str:
        """Extract bare email from a From header like 'Name <email@example.com>'."""
        match = self._EMAIL_PATTERN.search(from_header)
        return match.group(0).lower() if match else from_header.lower()

    def _passes_sender_filter(
        self, thread: WatchedThread, from_address: str
    ) -> bool:
        """Check if a reply sender passes the thread's sender filters.

        Returns True if the reply should trigger a notification.
        """
        sender_email = self._extract_email_address(from_address)
        own_email = settings.gmail_address.lower()

        # Check ignore_own_replies
        if thread.ignore_own_replies and sender_email == own_email:
            return False

        # Check external_only (skip replies from own domain)
        if thread.external_only:
            own_domain = own_email.split("@")[-1]
            if sender_email.endswith(f"@{own_domain}"):
                return False

        # Check watch_for_senders (allowlist — if set, sender must match)
        if thread.watch_for_senders:
            for pattern in thread.watch_for_senders:
                if pattern.startswith("@"):
                    if sender_email.endswith(pattern.lower()):
                        return True
                else:
                    if sender_email == pattern.lower():
                        return True
            return False

        return True

    async def _handle_reply(
        self,
        message_id: str,
        thread_id: str,
    ) -> Optional[dict[str, Any]]:
        """Handle a reply in a watched thread.

        Applies sender filtering before marking the reply and notifying.

        Args:
            message_id: Gmail message ID.
            thread_id: Gmail thread ID.

        Returns:
            Result dict if notification was sent, None otherwise.
        """
        import structlog

        log = structlog.get_logger()

        # Get message details
        message = self._gmail_client.get_message(message_id)

        # Extract headers
        from_address = self._extract_header(message, "From") or "unknown"
        preview = message.get("snippet", "")

        # Look up the watched thread to check sender filters
        stmt = select(WatchedThread).where(WatchedThread.thread_id == thread_id)
        result = await self._session.execute(stmt)
        watched = result.scalar_one_or_none()

        if watched is None or not watched.is_active or watched.reply_received:
            return None

        # Apply sender filtering
        if not self._passes_sender_filter(watched, from_address):
            log.info(
                "reply_filtered",
                thread_id=thread_id,
                from_address=from_address,
                ignore_own=watched.ignore_own_replies,
                external_only=watched.external_only,
            )
            # Update activity tracking but don't trigger notification
            watched.message_count += 1
            watched.last_activity_at = datetime.now(timezone.utc)
            await self._session.commit()
            return None

        # Mark reply in registry
        thread = await self.registry.mark_reply_received(
            thread_id=thread_id,
            message_id=message_id,
        )

        if thread is None:
            return None

        # Notify agent
        notify_result = await self.notifier.notify_reply_received(
            thread=thread,
            new_message_id=message_id,
            from_address=from_address,
            preview=preview,
        )

        # Log notification
        await self._log_notification(
            thread_id=thread_id,
            notification_type="reply_received",
            message_id=message_id,
            agent_id=self.notifier.agent_id,
            extra_data={
                "from": from_address,
                "notify_status": notify_result.get("status"),
            },
        )

        return notify_result

    async def initialize_watch(self) -> dict[str, Any]:
        """Initialize Gmail watch for push notifications.

        Returns:
            Dictionary with status and watch details.
        """
        try:
            # Get topic name from puller
            topic_name = self._pubsub_puller.get_topic_name()

            # Setup Gmail watch
            watch_result = self._gmail_client.setup_watch(topic_name)

            history_id = watch_result["history_id"]
            expiration_ms = watch_result["expiration"]
            watch_expiration = datetime.fromtimestamp(
                expiration_ms / 1000, tz=timezone.utc
            )

            # Store sync state
            await self._update_sync_state(
                history_id=history_id,
                watch_expiration=watch_expiration,
            )

            return {
                "status": "ok",
                "history_id": history_id,
                "watch_expiration": watch_expiration.isoformat(),
            }

        except Exception as e:
            error_msg = f"Failed to initialize watch: {str(e)}"
            await self._record_error(error_msg)
            return {
                "status": "error",
                "error": error_msg,
            }

    async def check_watch_expiration(
        self,
        threshold_hours: int = DEFAULT_RENEWAL_THRESHOLD_HOURS,
    ) -> dict[str, Any]:
        """Check if watch needs renewal.

        Args:
            threshold_hours: Hours before expiration to flag for renewal.

        Returns:
            Dictionary with status and needs_renewal flag.
        """
        sync_state = await self._get_sync_state()

        if sync_state is None or sync_state.watch_expiration is None:
            return {
                "status": "ok",
                "needs_renewal": True,
                "reason": "no_watch_configured",
            }

        now = datetime.now(timezone.utc)
        threshold = timedelta(hours=threshold_hours)
        time_until_expiration = sync_state.watch_expiration - now

        needs_renewal = time_until_expiration < threshold

        return {
            "status": "ok",
            "needs_renewal": needs_renewal,
            "watch_expiration": sync_state.watch_expiration.isoformat(),
            "hours_until_expiration": time_until_expiration.total_seconds() / 3600,
        }

    async def process_notifications(self) -> dict[str, Any]:
        """Process pending Pub/Sub notifications.

        Main loop iteration: pull from Pub/Sub, get Gmail history,
        filter for watched threads, and notify agent of replies.

        Returns:
            Dictionary with status and processing results.
        """
        try:
            # Get current sync state
            sync_state = await self._get_sync_state()
            if sync_state is None:
                return {
                    "status": "error",
                    "error": "No sync state found. Call initialize_watch() first.",
                }

            # Pull messages from Pub/Sub
            notifications = self._pubsub_puller.pull_messages()

            if not notifications:
                return {
                    "status": "ok",
                    "processed": 0,
                    "message": "No notifications pending",
                }

            # Update last pull time
            await self._update_sync_state(
                last_pull_at=datetime.now(timezone.utc),
            )

            # Get watched thread IDs
            watched_thread_ids = await self.registry.get_active_thread_ids()

            # Track processing results
            processed_count = 0
            replies_found = 0
            notifications_sent = 0

            # Process each notification
            for notification in notifications:
                history_id = notification.get("history_id", 0)

                if history_id <= sync_state.history_id:
                    # Already processed
                    continue

                # Get history since last known history_id
                history_records = self._gmail_client.get_history(
                    start_history_id=sync_state.history_id,
                )

                processed_count += 1

                # Process each history record
                for record in history_records:
                    messages_added = record.get("messagesAdded", [])

                    for msg_data in messages_added:
                        message = msg_data.get("message", {})
                        msg_id = message.get("id")
                        thread_id = message.get("threadId")

                        if thread_id not in watched_thread_ids:
                            # Not a watched thread — try BCC auto-register
                            auto_result = await self.try_auto_register(
                                message_id=msg_id,
                                thread_id=thread_id,
                            )
                            if auto_result and auto_result.get("status") == "ok":
                                watched_thread_ids.add(
                                    auto_result.get("thread_id", thread_id)
                                )
                            continue

                        replies_found += 1

                        # Handle the reply
                        result = await self._handle_reply(
                            message_id=msg_id,
                            thread_id=thread_id,
                        )

                        if result and result.get("status") == "ok":
                            notifications_sent += 1

                # Update history_id to the latest
                if history_id > sync_state.history_id:
                    sync_state.history_id = history_id
                    await self._session.commit()

            # Update last notification time if we sent any
            if notifications_sent > 0:
                await self._update_sync_state(
                    last_notification_at=datetime.now(timezone.utc),
                )

            return {
                "status": "ok",
                "processed": processed_count,
                "replies_found": replies_found,
                "notifications_sent": notifications_sent,
            }

        except Exception as e:
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            try:
                await self._record_error(error_msg)
            except Exception:
                pass  # Don't fail if we can't record the error

            return {
                "status": "error",
                "error": str(e),
            }

    async def check_followups(self) -> dict[str, Any]:
        """Check for threads with overdue follow-up deadlines."""
        try:
            now = datetime.now(timezone.utc)
            stmt = select(WatchedThread).where(
                WatchedThread.is_active == True,  # noqa: E712
                WatchedThread.followup_seconds.isnot(None),
                WatchedThread.followup_due_at < now,
                WatchedThread.followup_notified == False,  # noqa: E712
                WatchedThread.reply_received == False,  # noqa: E712
            )
            result = await self._session.execute(stmt)
            overdue_threads = result.scalars().all()

            notified_count = 0
            for thread in overdue_threads:
                notify_result = await self.notifier.notify_followup_needed(thread)
                thread.followup_notified = True
                await self._log_notification(
                    thread_id=thread.thread_id,
                    notification_type="followup_needed",
                    agent_id=self.notifier.agent_id,
                    extra_data={"followup_seconds": thread.followup_seconds},
                )
                if notify_result.get("status") == "ok":
                    notified_count += 1

            await self._session.commit()
            return {
                "status": "ok",
                "overdue_count": len(overdue_threads),
                "notified_count": notified_count,
            }
        except Exception as e:
            try:
                await self._record_error(f"check_followups: {e}")
            except Exception:
                pass
            return {
                "status": "error",
                "error": str(e),
                "overdue_count": 0,
                "notified_count": 0,
            }

    async def process_task_queue(self) -> dict[str, Any]:
        """Process emails with TaskQueue label and write to Letta memory block.

        Searches for messages with the TaskQueue Gmail label, extracts task
        information (detecting forwards with user notes), writes entries to
        the queued_tasks_from_email Letta memory block, and removes the label.

        Returns:
            Dictionary with processing results.
        """
        import structlog

        log = structlog.get_logger()

        if not settings.task_queue_enabled:
            return {"status": "disabled", "processed": 0}

        try:
            # Find TaskQueue label
            label_id = self._gmail_client.get_label_id_by_name(
                settings.task_queue_label_name
            )
            if not label_id:
                return {"status": "ok", "processed": 0, "message": "TaskQueue label not found"}

            # List messages with TaskQueue label
            messages = self._gmail_client.list_messages_by_label(label_id, max_results=10)
            if not messages:
                return {"status": "ok", "processed": 0}

            processed = []
            errors = []

            for msg_ref in messages:
                msg_id = msg_ref["id"]
                try:
                    # Fetch full message
                    message = self._gmail_client.get_message(msg_id, format="full")

                    # Extract headers
                    headers = {}
                    for h in message.get("payload", {}).get("headers", []):
                        headers[h["name"].lower()] = h["value"]

                    subject = headers.get("subject", "")
                    from_address = headers.get("from", "")
                    date = headers.get("date", "")
                    snippet = message.get("snippet", "")
                    thread_id = message.get("threadId", "")
                    original_message_id = msg_id
                    original_thread_id = thread_id
                    trigger = "TaskQueue"
                    notes = None
                    forwarded_message_id = None

                    # Extract body and check for forward
                    body = self._extract_body(message)
                    fwd_result = TaskQueueWriter.parse_forward(body)

                    if fwd_result["is_forward"]:
                        trigger = "forwarded"
                        notes = fwd_result.get("notes")
                        forwarded_message_id = msg_id

                        # Use forwarded message headers
                        if fwd_result.get("from"):
                            from_address = fwd_result["from"]
                        if fwd_result.get("subject"):
                            subject = fwd_result["subject"]
                        if fwd_result.get("date"):
                            date = fwd_result["date"]
                        if fwd_result.get("snippet"):
                            snippet = fwd_result["snippet"]

                        # Resolve original message via Gmail search
                        from_match = self._EMAIL_PATTERN.search(from_address)
                        from_email = from_match.group(0) if from_match else ""

                        if from_email and subject:
                            clean_subject = subject.replace('"', '\\"')
                            query = f'from:{from_email} subject:"{clean_subject}"'
                            try:
                                search_results = self._gmail_client.search_messages(query)
                                for sr in search_results:
                                    if sr["id"] != msg_id:
                                        original_message_id = sr["id"]
                                        original_thread_id = sr.get(
                                            "threadId", original_thread_id
                                        )
                                        break
                            except Exception:
                                pass  # Keep forwarded message ID as fallback

                    # Check for task markers in notes
                    marker_entries = (
                        TaskQueueWriter.parse_markers(notes) if notes else []
                    )

                    if marker_entries:
                        # Multi-task: one queue entry per marker
                        entry_defs = [
                            {
                                "marker_type": me["marker_type"],
                                "task_hint": me["task_hint"],
                                "context": me["context"],
                            }
                            for me in marker_entries
                        ]
                    else:
                        # Single task: use notes as-is
                        entry_defs = [
                            {
                                "marker_type": None,
                                "task_hint": None,
                                "context": None,
                            }
                        ]

                    msg_had_error = False
                    for entry_def in entry_defs:
                        entry = self.task_queue_writer.format_queue_entry(
                            message_id=original_message_id,
                            thread_id=original_thread_id,
                            subject=subject,
                            from_address=from_address,
                            date=date,
                            snippet=snippet,
                            trigger=trigger,
                            notes=notes if not entry_def["marker_type"] else None,
                            forwarded_message_id=forwarded_message_id,
                            marker_type=entry_def["marker_type"],
                            task_hint=entry_def["task_hint"],
                            context=entry_def["context"],
                        )

                        write_result = await self.task_queue_writer.write_to_block(
                            entry
                        )

                        if write_result.get("status") != "ok":
                            errors.append({
                                "message_id": msg_id,
                                "error": write_result.get("error", "write failed"),
                                "task_hint": entry_def.get("task_hint"),
                            })
                            msg_had_error = True
                            continue

                        processed.append({
                            "message_id": original_message_id,
                            "subject": subject,
                            "from": from_address,
                            "has_notes": bool(notes),
                            "is_forward": fwd_result.get("is_forward", False),
                            "marker_type": entry_def["marker_type"],
                            "task_hint": entry_def["task_hint"],
                        })

                        log.info(
                            "task_queued",
                            subject=subject,
                            from_address=from_address,
                            trigger=trigger,
                            marker_type=entry_def["marker_type"],
                            task_hint=entry_def.get("task_hint"),
                        )

                    if not msg_had_error:
                        # Remove TaskQueue label only if all entries wrote OK
                        self._gmail_client.remove_label(msg_id, label_id)

                    # Log notification
                    await self._log_notification(
                        thread_id=original_thread_id,
                        notification_type="task_queued",
                        message_id=original_message_id,
                        extra_data={
                            "subject": subject,
                            "from": from_address,
                            "trigger": trigger,
                            "has_notes": bool(notes),
                            "marker_count": len(marker_entries),
                        },
                    )

                except Exception as msg_err:
                    log.error(
                        "task_queue_message_error",
                        message_id=msg_id,
                        error=str(msg_err),
                    )
                    errors.append({"message_id": msg_id, "error": str(msg_err)})

            # Notify agent to process queue entries
            if processed:
                try:
                    await self.notifier.notify_task_queued(processed)
                except Exception as notify_err:
                    log.error("task_queue_notify_error", error=str(notify_err))

            result = {
                "status": "ok",
                "processed": len(processed),
                "details": processed,
            }
            if errors:
                result["errors"] = errors
            return result

        except Exception as e:
            log.error("task_queue_processing_error", error=str(e))
            try:
                await self._record_error(f"process_task_queue: {e}")
            except Exception:
                pass
            return {"status": "error", "error": str(e), "processed": 0}

    async def process_drive_task_queue(self) -> dict[str, Any]:
        """Process emails with DTaskQueue label for drive comment tasks.

        Searches for messages with the DTaskQueue Gmail label, extracts
        doc_id/comment_id from the notification email, parses reply text
        for task markers, writes entries to queued_tasks_from_drive block,
        and removes the label.
        """
        import structlog

        log = structlog.get_logger()

        if not settings.drive_task_queue_enabled:
            return {"status": "disabled", "processed": 0}

        try:
            label_id = self._gmail_client.get_label_id_by_name(
                settings.drive_task_queue_label_name
            )
            if not label_id:
                return {
                    "status": "ok",
                    "processed": 0,
                    "message": "DTaskQueue label not found",
                }

            # "Done" label prevents fallback query from re-processing
            done_label_name = f"{settings.drive_task_queue_label_name}Done"
            done_label_id = self._gmail_client.get_label_id_by_name(
                done_label_name
            )

            messages = self._gmail_client.list_messages_by_label(
                label_id, max_results=10
            )

            # Fallback: search by query for unlabeled notifications
            # (Google Docs system notifications may bypass Gmail filters)
            if not messages:
                query_results = self._gmail_client.search_messages(
                    "to:cdorsey+dtasks from:comments-noreply@docs.google.com "
                    "newer_than:1d",
                    max_results=10,
                )
                if query_results:
                    # Read current block to check already-processed IDs
                    block_value = ""
                    if settings.drive_task_queue_block_id:
                        try:
                            block_value = (
                                await self.drive_task_queue_writer.read_block()
                            )
                        except Exception:
                            pass

                    for msg_ref in query_results:
                        msg_id = msg_ref["id"]
                        # Skip if already in queue block
                        if msg_id in block_value:
                            continue
                        try:
                            msg_labels = self._gmail_client.get_message(
                                msg_id, format="minimal"
                            ).get("labelIds", [])
                            # Skip if already has pending or done label
                            if label_id in msg_labels:
                                continue
                            if done_label_id and done_label_id in msg_labels:
                                continue
                            self._gmail_client.service.users().messages().modify(
                                userId="me",
                                id=msg_id,
                                body={"addLabelIds": [label_id]},
                            ).execute()
                        except Exception:
                            pass

                    messages = self._gmail_client.list_messages_by_label(
                        label_id, max_results=10
                    )

            if not messages:
                return {"status": "ok", "processed": 0}

            processed = []
            errors = []

            for msg_ref in messages:
                msg_id = msg_ref["id"]
                try:
                    message = self._gmail_client.get_message(msg_id, format="full")

                    headers = {}
                    for h in message.get("payload", {}).get("headers", []):
                        headers[h["name"].lower()] = h["value"]

                    subject = headers.get("subject", "")
                    from_address = headers.get("from", "")
                    date = headers.get("date", "")

                    body = self._extract_body(message)
                    if not body:
                        errors.append({"message_id": msg_id, "error": "empty body"})
                        continue

                    # Extract doc_id and comment_id from notification URL
                    doc_id, comment_id = (
                        DriveTaskQueueWriter.extract_doc_and_comment_ids(body)
                    )
                    if not doc_id:
                        errors.append({
                            "message_id": msg_id,
                            "error": "no doc_id found in email body",
                        })
                        continue

                    # Parse notification body for author and comment text
                    notif = DriveTaskQueueWriter.parse_notification_body(body)

                    # Use parsed comment text (clean, no boilerplate)
                    comment_content = DriveTaskQueueWriter.strip_trigger_address(
                        notif["comment_text"]
                    )

                    # Parse for task markers from comment text only
                    marker_entries = TaskQueueWriter.parse_markers(comment_content)

                    # Extract doc title from email subject
                    doc_title = subject.replace("Comment on ", "").replace(
                        "Re: Comment on ", ""
                    ).strip(' "')

                    # Use real author email if available, fallback to From header
                    triggered_by = notif["author_email"] or from_address
                    comment_author = notif["author_name"]

                    if marker_entries:
                        entry_defs = [
                            {
                                "marker_type": me["marker_type"],
                                "task_hint": me["task_hint"],
                                "context": me["context"],
                            }
                            for me in marker_entries
                        ]
                    else:
                        notes = (
                            comment_content.strip()
                            if comment_content.strip()
                            else None
                        )
                        entry_defs = [{
                            "marker_type": None,
                            "task_hint": None,
                            "context": None,
                            "notes": notes,
                        }]

                    # ── Drive API enrichment (best-effort) ──
                    enriched: dict[str, Any] = {}
                    if self.drive_enricher:
                        try:
                            enriched = self.drive_enricher.enrich(
                                doc_id, comment_id
                            )
                        except Exception as enrich_err:
                            log.warning(
                                "drive_enrichment_failed",
                                doc_id=doc_id,
                                error=str(enrich_err),
                            )

                    # Override with enriched data when available
                    if enriched.get("doc_title"):
                        doc_title = enriched["doc_title"]
                    enriched_doc_type = enriched.get("doc_type", "unknown")
                    enriched_comment_text = enriched.get(
                        "comment_text", comment_content
                    )
                    if enriched.get("comment_author"):
                        author_name = enriched["comment_author"]
                        author_email = enriched.get(
                            "comment_author_email", ""
                        )
                        if author_email:
                            comment_author = (
                                f"{author_name} ({author_email})"
                            )
                        else:
                            comment_author = author_name
                    enriched_date = enriched.get("comment_date", date)

                    msg_had_error = False
                    for entry_def in entry_defs:
                        entry = self.drive_task_queue_writer.format_drive_queue_entry(
                            comment_id=comment_id or "",
                            doc_id=doc_id,
                            doc_title=doc_title,
                            doc_type=enriched_doc_type,
                            comment_author=comment_author,
                            triggered_by=triggered_by,
                            comment_date=enriched_date,
                            comment_text=enriched_comment_text,
                            gmail_message_id=msg_id,
                            quoted_passage=enriched.get("quoted_passage"),
                            surrounding_context=enriched.get(
                                "surrounding_context"
                            ),
                            urls=enriched.get("urls"),
                            notes=entry_def.get("notes"),
                            marker_type=entry_def["marker_type"],
                            task_hint=entry_def["task_hint"],
                            context=entry_def["context"],
                        )

                        write_result = await self.drive_task_queue_writer.write_to_block(
                            entry
                        )

                        if write_result.get("status") != "ok":
                            errors.append({
                                "message_id": msg_id,
                                "error": write_result.get("error", "write failed"),
                            })
                            msg_had_error = True
                            continue

                        processed.append({
                            "comment_id": comment_id,
                            "doc_id": doc_id,
                            "doc_title": doc_title,
                            "comment_text": comment_content,
                            "triggered_by": triggered_by,
                            "marker_type": entry_def["marker_type"],
                            "task_hint": entry_def.get("task_hint"),
                        })

                        log.info(
                            "drive_task_queued",
                            doc_title=doc_title,
                            doc_id=doc_id,
                            comment_id=comment_id,
                            marker_type=entry_def["marker_type"],
                        )

                    if not msg_had_error:
                        # Swap DTaskQueue → DTaskQueueDone to prevent
                        # fallback query from re-processing
                        modify_body: dict[str, Any] = {
                            "removeLabelIds": [label_id],
                        }
                        if not done_label_id:
                            # Auto-create done label on first use
                            try:
                                created = (
                                    self._gmail_client.service.users()
                                    .labels()
                                    .create(
                                        userId="me",
                                        body={
                                            "name": done_label_name,
                                            "labelListVisibility": "labelHide",
                                            "messageListVisibility": "hide",
                                        },
                                    )
                                    .execute()
                                )
                                done_label_id = created["id"]
                            except Exception:
                                pass
                        if done_label_id:
                            modify_body["addLabelIds"] = [done_label_id]
                        self._gmail_client.service.users().messages().modify(
                            userId="me",
                            id=msg_id,
                            body=modify_body,
                        ).execute()

                except Exception as msg_err:
                    log.error(
                        "drive_task_queue_message_error",
                        message_id=msg_id,
                        error=str(msg_err),
                    )
                    errors.append({"message_id": msg_id, "error": str(msg_err)})

            # Notify Docs & Transcripts agent
            if processed and settings.drive_task_queue_agent_id:
                try:
                    await self.notifier.notify_drive_task_queued(
                        entries=processed,
                        agent_id=settings.drive_task_queue_agent_id,
                    )
                except Exception as notify_err:
                    log.error(
                        "drive_task_queue_notify_error", error=str(notify_err)
                    )

            result = {
                "status": "ok",
                "processed": len(processed),
                "details": processed,
            }
            if errors:
                result["errors"] = errors
            return result

        except Exception as e:
            log.error("drive_task_queue_processing_error", error=str(e))
            try:
                await self._record_error(f"process_drive_task_queue: {e}")
            except Exception:
                pass
            return {"status": "error", "error": str(e), "processed": 0}

    # Forward detection patterns (same as email_task_queue_tool.py)
    _FORWARD_DELIMITER = re.compile(r"-{5,}\s*Forwarded message\s*-{5,}")
    _FORWARDED_HEADER = re.compile(r"^(From|Date|Subject|To):\s*(.+)$", re.MULTILINE)
    _EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+")

    async def try_auto_register(
        self,
        message_id: str,
        thread_id: str,
    ) -> Optional[dict[str, Any]]:
        """Try to auto-register a watch from BCC address detection.

        Called when a Pub/Sub notification arrives for a thread NOT in the
        registry. Fetches the message, checks for BCC watch address, and
        registers the watch if found. For forwards, resolves the original
        thread and uses the original send date as follow-up baseline.
        """
        try:
            message = self._gmail_client.get_message(message_id, format="full")

            # Extract all headers
            headers = {}
            for h in message.get("payload", {}).get("headers", []):
                headers[h["name"].lower()] = h["value"]

            # Check To, CC, BCC for watch address
            bcc_prefix = settings.bcc_watch_address
            matched_address = None
            interval_seconds = None
            external_only = False

            for header_name in ("to", "cc", "bcc"):
                value = headers.get(header_name, "")
                for addr in self._EMAIL_PATTERN.findall(value):
                    params = extract_watch_params_from_address(addr, bcc_prefix)
                    if params is not None:
                        matched_address = addr
                        interval_seconds = params["interval_seconds"]
                        external_only = params["external_only"]
                        break
                if matched_address:
                    break

            if not matched_address:
                return None

            subject = headers.get("subject", "")
            interval_str = format_interval(interval_seconds)

            is_forward = subject.lower().startswith("fwd:")
            watch_thread_id = thread_id
            followup_due_override = None
            recipients = []

            # Extract recipients from To header (excluding watch address)
            to_header = headers.get("to", "")
            for addr in self._EMAIL_PATTERN.findall(to_header):
                if not addr.lower().startswith(bcc_prefix.lower()):
                    recipients.append(addr)

            if is_forward:
                body = self._extract_body(message)
                fwd_match = self._FORWARD_DELIMITER.search(body) if body else None

                if fwd_match:
                    below = body[fwd_match.end():]
                    fwd_headers = {}
                    for match in self._FORWARDED_HEADER.finditer(below[:500]):
                        fwd_headers[match.group(1).lower()] = match.group(2).strip()

                    # Use original subject
                    original_subject = fwd_headers.get("subject", "")
                    if not original_subject:
                        original_subject = re.sub(
                            r"^(Fwd:\s*)+", "", subject, flags=re.IGNORECASE
                        ).strip()
                    subject = original_subject

                    # Parse original date for follow-up baseline
                    original_date_str = fwd_headers.get("date", "")
                    original_date = self._parse_date(original_date_str)
                    if original_date and interval_seconds:
                        followup_due_override = original_date + timedelta(
                            seconds=interval_seconds
                        )

                    # Extract original sender
                    original_from = fwd_headers.get("from", "")
                    from_match = self._EMAIL_PATTERN.search(original_from)
                    if from_match:
                        recipients = [from_match.group(0)]

                    # Resolve original thread via Gmail search
                    if from_match and original_subject:
                        clean_subject = original_subject.replace('"', '\\"')
                        query = f'from:{from_match.group(0)} subject:"{clean_subject}"'
                        try:
                            search_results = self._gmail_client.search_messages(query)
                            for sr in search_results:
                                if sr["id"] != message_id:
                                    watch_thread_id = sr.get(
                                        "threadId", watch_thread_id
                                    )
                                    break
                        except Exception:
                            pass

                    # Remove Watching label from forward if we resolved original
                    if watch_thread_id != thread_id:
                        try:
                            label_id = self._gmail_client.get_watching_label_id()
                            self._gmail_client.remove_label(message_id, label_id)
                        except Exception:
                            pass

            # Register the watch
            reg_result = await self.registry.watch_thread(
                thread_id=watch_thread_id,
                subject=subject,
                recipients=recipients if recipients else None,
                followup_interval=interval_str,
                source="bcc",
                bcc_address=matched_address,
                followup_due_at_override=followup_due_override,
                external_only=external_only,
            )

            # Log
            await self._log_notification(
                thread_id=watch_thread_id,
                notification_type="watch_auto_created",
                message_id=message_id,
                agent_id=self.notifier.agent_id,
                extra_data={
                    "bcc_address": matched_address,
                    "interval": interval_str,
                    "is_forward": is_forward,
                },
            )

            # Notify agent
            try:
                await self.notifier.notify_watch_started_simple(
                    subject=subject,
                    recipients=recipients or [],
                    interval_str=interval_str,
                    followup_due_at=followup_due_override
                    or (
                        datetime.now(timezone.utc)
                        + timedelta(seconds=interval_seconds)
                    ),
                )
            except Exception:
                pass  # Non-critical

            return reg_result

        except Exception as e:
            import structlog

            structlog.get_logger().error(
                "auto_register_error", error=str(e), thread_id=thread_id
            )
            return None

    def _extract_body(self, message: dict[str, Any]) -> str:
        """Extract text body from Gmail message using MIME walk."""
        plain_body = ""
        html_body = ""
        stack = [message.get("payload", {})]
        while stack:
            part = stack.pop()
            mime_type = part.get("mimeType", "")
            parts = part.get("parts", [])
            if parts:
                stack.extend(parts)
                continue
            body_data = part.get("body", {}).get("data", "")
            if not body_data:
                continue
            decoded = base64.urlsafe_b64decode(body_data).decode(
                "utf-8", errors="replace"
            )
            if mime_type == "text/plain" and not plain_body:
                plain_body = decoded
            elif mime_type == "text/html" and not html_body:
                html_body = decoded
        return plain_body if plain_body else html_body

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime]:
        """Parse email date header to datetime."""
        if not date_str:
            return None
        from email.utils import parsedate_to_datetime

        try:
            return parsedate_to_datetime(date_str)
        except Exception:
            return None

    async def fallback_scan(self) -> dict[str, Any]:
        """Scan Gmail for unregistered watch addresses.

        Catches forwards-to-watch-address that Gmail filters missed
        (e.g., forwards that thread into existing conversations).
        Searches for messages TO the watch address that lack the
        Watching label and tries to auto-register them.

        Returns:
            Dictionary with scan results.
        """
        import structlog

        log = structlog.get_logger()

        try:
            bcc_prefix = settings.bcc_watch_address
            label_name = settings.watching_label_name
            query = f"to:{bcc_prefix} -label:{label_name} newer_than:3d"

            results = self._gmail_client.search_messages(query, max_results=20)
            if not results:
                return {"status": "ok", "scanned": 0, "registered": 0}

            watched_ids = await self.registry.get_active_thread_ids()
            registered = 0

            for msg_ref in results:
                msg_id = msg_ref["id"]
                msg_thread_id = msg_ref.get("threadId", "")

                if msg_thread_id in watched_ids:
                    continue

                auto_result = await self.try_auto_register(
                    message_id=msg_id,
                    thread_id=msg_thread_id,
                )

                if auto_result and auto_result.get("status") == "ok":
                    registered += 1
                    watched_ids.add(
                        auto_result.get("thread_id", msg_thread_id)
                    )
                    log.info(
                        "fallback_scan_registered",
                        thread_id=auto_result.get("thread_id", msg_thread_id),
                        message_id=msg_id,
                    )

            return {
                "status": "ok",
                "scanned": len(results),
                "registered": registered,
            }

        except Exception as e:
            log.error("fallback_scan_error", error=str(e))
            return {"status": "error", "error": str(e), "scanned": 0, "registered": 0}

    async def get_sync_status(self) -> dict[str, Any]:
        """Get current sync status for external callers.

        Returns:
            Dictionary with sync state information.
        """
        sync_state = await self._get_sync_state()
        return {
            "history_id": sync_state.history_id if sync_state else None,
            "watch_expiration": (
                sync_state.watch_expiration.isoformat()
                if sync_state and sync_state.watch_expiration
                else None
            ),
            "last_pull_at": (
                sync_state.last_pull_at.isoformat()
                if sync_state and sync_state.last_pull_at
                else None
            ),
            "error_count": sync_state.error_count if sync_state else 0,
        }
