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
            "labelIds": [label_id, "INBOX"],
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

        all_history: list[dict[str, Any]] = []
        page_token: Optional[str] = None

        while True:
            response = self.service.users().history().list(
                userId="me",
                startHistoryId=start_history_id,
                labelId="INBOX",
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

    def search_messages(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """Search Gmail messages by query."""
        response = self.service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        return response.get("messages", [])

    def remove_label(self, message_id: str, label_id: str) -> None:
        """Remove a label from a message."""
        self.service.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": [label_id]},
        ).execute()

    def get_label_id_by_name(self, label_name: str) -> Optional[str]:
        """Get the ID of a Gmail label by name.

        Returns None if label doesn't exist.
        """
        results = self.service.users().labels().list(userId="me").execute()
        for label in results.get("labels", []):
            if label["name"] == label_name:
                return label["id"]
        return None

    def list_messages_by_label(
        self, label_id: str, max_results: int = 10
    ) -> list[dict[str, Any]]:
        """List messages with a specific label."""
        response = self.service.users().messages().list(
            userId="me", labelIds=[label_id], maxResults=max_results,
        ).execute()
        return response.get("messages", [])

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
