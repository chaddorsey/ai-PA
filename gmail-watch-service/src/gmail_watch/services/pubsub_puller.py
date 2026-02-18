"""Pub/Sub pull subscription service for Gmail notifications."""

from __future__ import annotations

import base64
import json
from typing import Any, Optional

from google.cloud.pubsub_v1 import SubscriberClient
from google.cloud.pubsub_v1.subscriber.message import Message

from gmail_watch.settings import settings


class PubSubPuller:
    """Pulls messages from Google Cloud Pub/Sub subscription."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
    ) -> None:
        self.project_id = project_id or settings.gcp_project_id
        self.subscription_id = subscription_id or settings.pubsub_subscription
        self.subscription_path = (
            f"projects/{self.project_id}/subscriptions/{self.subscription_id}"
        )
        self._client: Optional[SubscriberClient] = None

    @property
    def client(self) -> SubscriberClient:
        """Lazy-load Pub/Sub subscriber client."""
        if self._client is None:
            self._client = SubscriberClient()
        return self._client

    def parse_notification(self, message: Message) -> dict[str, Any]:
        """
        Parse a Gmail notification message.

        Gmail push notifications contain:
        - emailAddress: The email address
        - historyId: The new history ID to sync from
        """
        try:
            # Message data is base64 encoded JSON
            if isinstance(message.data, bytes):
                data_str = message.data.decode("utf-8")
            else:
                data_str = message.data

            # Try to decode if base64
            try:
                decoded = base64.b64decode(data_str).decode("utf-8")
                data = json.loads(decoded)
            except Exception:
                # Maybe it's already JSON
                data = json.loads(data_str)

            return {
                "history_id": int(data.get("historyId", 0)),
                "email": data.get("emailAddress", ""),
            }
        except Exception as e:
            return {
                "history_id": 0,
                "email": "",
                "error": str(e),
            }

    def pull_messages(self, max_messages: int = 10) -> list[dict[str, Any]]:
        """
        Pull messages from subscription synchronously.

        Returns list of parsed notifications. Returns empty list if no
        messages are available (timeout is normal, not an error).
        """
        from google.api_core.exceptions import DeadlineExceeded

        try:
            response = self.client.pull(
                subscription=self.subscription_path,
                max_messages=max_messages,
                timeout=10,
            )
        except DeadlineExceeded:
            # No messages available within timeout — this is normal
            return []

        notifications = []
        ack_ids = []

        for received_message in response.received_messages:
            notification = self.parse_notification(received_message.message)
            notification["ack_id"] = received_message.ack_id
            notifications.append(notification)
            ack_ids.append(received_message.ack_id)

        # Acknowledge all messages
        if ack_ids:
            self.client.acknowledge(
                subscription=self.subscription_path,
                ack_ids=ack_ids,
            )

        return notifications

    def get_topic_name(self) -> str:
        """Return the full topic name for Gmail watch setup."""
        return f"projects/{self.project_id}/topics/gmail-watch"
