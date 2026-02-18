"""Gmail API client for watch service."""

from __future__ import annotations

from typing import Any, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build

from gmail_watch.settings import settings


class GmailClient:
    """Client for Gmail API operations needed by watch service."""

    def __init__(self, credentials_path: Optional[str] = None) -> None:
        self.credentials_path = credentials_path or settings.gmail_credentials_path
        self._service: Optional[Resource] = None
        self._watching_label_id: Optional[str] = None

    @property
    def service(self) -> Resource:
        """Lazy-load Gmail API service."""
        if self._service is None:
            creds = Credentials.from_authorized_user_file(self.credentials_path)
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def get_watching_label_id(self) -> str:
        """Get the ID of the 'Watching' label, creating if needed."""
        if self._watching_label_id:
            return self._watching_label_id

        # List all labels
        results = self.service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])

        for label in labels:
            if label["name"] == settings.watching_label_name:
                self._watching_label_id = label["id"]
                return self._watching_label_id

        # Create label if not exists
        label_body = {
            "name": settings.watching_label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        created = self.service.users().labels().create(
            userId="me", body=label_body
        ).execute()
        self._watching_label_id = created["id"]
        return self._watching_label_id

    def setup_watch(self, topic_name: str) -> dict[str, Any]:
        """Set up Gmail push notifications.

        Returns dict with historyId and expiration.
        """
        label_id = self.get_watching_label_id()

        body = {
            "topicName": topic_name,
            "labelIds": [label_id],
            "labelFilterBehavior": "include",
        }

        response = self.service.users().watch(userId="me", body=body).execute()

        return {
            "history_id": int(response["historyId"]),
            "expiration": int(response["expiration"]),
        }

    def stop_watch(self) -> None:
        """Stop Gmail push notifications."""
        self.service.users().stop(userId="me").execute()

    def get_history(
        self,
        start_history_id: int,
        history_types: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Get mailbox history since given historyId.

        Returns list of history records.
        """
        if history_types is None:
            history_types = ["messageAdded"]

        label_id = self.get_watching_label_id()

        all_history: list[dict[str, Any]] = []
        page_token: Optional[str] = None

        while True:
            response = self.service.users().history().list(
                userId="me",
                startHistoryId=start_history_id,
                labelId=label_id,
                historyTypes=history_types,
                pageToken=page_token,
            ).execute()

            history = response.get("history", [])
            all_history.extend(history)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return all_history

    def get_message(self, message_id: str, format: str = "metadata") -> dict[str, Any]:
        """Get a message by ID."""
        return self.service.users().messages().get(
            userId="me",
            id=message_id,
            format=format,
        ).execute()

    def get_thread(self, thread_id: str, format: str = "metadata") -> dict[str, Any]:
        """Get a thread by ID."""
        return self.service.users().threads().get(
            userId="me",
            id=thread_id,
            format=format,
        ).execute()

    def get_profile(self) -> dict[str, Any]:
        """Get user profile (for health checks)."""
        return self.service.users().getProfile(userId="me").execute()
