"""Watch manager orchestrator for Gmail watch service."""

from __future__ import annotations

import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gmail_watch.models import Notification, SyncState
from gmail_watch.services.agent_notifier import AgentNotifier
from gmail_watch.services.gmail_client import GmailClient
from gmail_watch.services.pubsub_puller import PubSubPuller
from gmail_watch.services.registry import ThreadRegistry

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

    async def _handle_reply(
        self,
        message_id: str,
        thread_id: str,
    ) -> Optional[dict[str, Any]]:
        """Handle a reply in a watched thread.

        Args:
            message_id: Gmail message ID.
            thread_id: Gmail thread ID.

        Returns:
            Result dict if notification was sent, None otherwise.
        """
        # Get message details
        message = self._gmail_client.get_message(message_id)

        # Extract headers
        from_address = self._extract_header(message, "From") or "unknown"
        preview = message.get("snippet", "")

        # Mark reply in registry
        thread = await self.registry.mark_reply_received(
            thread_id=thread_id,
            message_id=message_id,
        )

        if thread is None:
            # Thread not found or already replied
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
                            # Not a watched thread
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
