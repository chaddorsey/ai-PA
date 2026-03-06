"""
Direct Google Calendar API client for the scheduling orchestrator.

Replaces MCPCalendarClient (which routes through n8n MCP) with direct
Google Calendar API calls using google-api-python-client.

Uses existing OAuth2 credentials from ~/.gmail-mcp/calendar.credentials.json
(same credentials as letta/calendar_tools/tools.py).

Interface is compatible with MCPCalendarClient so orchestrate_scheduling.py
can swap imports with minimal changes.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Re-export MCPError for backward compatibility with orchestrate_scheduling.py imports
from mcp_client import MCPError


def _get_calendar_service():
    """
    Build an authenticated Google Calendar API service.

    Uses OAuth2 credentials from calendar.credentials.json,
    auto-refreshing expired tokens.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    TOKEN_PATH = os.getenv(
        "CALENDAR_CREDENTIALS_PATH",
        str(Path.home() / ".gmail-mcp" / "calendar.credentials.json"),
    )
    OAUTH_KEY_FILE = os.getenv(
        "CALENDAR_OAUTH_PATH",
        str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json"),
    )
    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    # Check for refreshed token in /tmp first (read-only mount workaround)
    tmp_token = "/tmp/calendar.credentials.json"
    if os.path.exists(tmp_token):
        token_file = tmp_token
    elif os.path.exists(TOKEN_PATH):
        token_file = TOKEN_PATH
    else:
        raise MCPError(
            code=-32603,
            message=f"Calendar credentials not found at {TOKEN_PATH}. "
            "Run: python3 letta/calendar_tools/authenticate_calendar.py",
        )

    creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Persist refreshed token (try original path, fall back to /tmp)
            for save_path in [TOKEN_PATH, "/tmp/calendar.credentials.json"]:
                try:
                    with open(save_path, "w") as f:
                        f.write(creds.to_json())
                    logger.info("Refreshed calendar OAuth token, saved to %s", save_path)
                    break
                except OSError:
                    continue
        else:
            raise MCPError(
                code=-32603,
                message="Calendar credentials expired and cannot be refreshed. "
                "Run: python3 letta/calendar_tools/authenticate_calendar.py",
            )

    return build("calendar", "v3", credentials=creds)


def _classify_event(event: Dict[str, Any]) -> Dict[str, bool]:
    """
    Compute scheduling classification flags for a calendar event.

    Uses description markers matching the n8n Core_Event_Data workflow:
    - [lk] in description → locked (cannot be moved)
    - [pr] in description → protected (important, shouldn't move)
    - neither → flexible (can be freely rescheduled)
    - transparent: event set to "show as free"
    """
    description = event.get("description", "") or ""
    transparency = event.get("transparency", "opaque")

    locked = "[lk]" in description
    protected = "[pr]" in description
    flexible = not locked and not protected
    is_transparent = transparency == "transparent"

    return {
        "locked": locked,
        "protected": protected,
        "flexible": flexible,
        "transparent": is_transparent,
    }


class GoogleCalendarClient:
    """
    Direct Google Calendar API client.

    Drop-in replacement for MCPCalendarClient with the same interface:
    - initialize() (no-op, kept for compatibility)
    - get_core_event_data(calendar_id, before, after)
    - fetch_event_by_id(calendar_id, event_id, days_forward)
    """

    def __init__(self, timeout: int = 30, max_retries: int = 3, **kwargs):
        """
        Initialize the Google Calendar client.

        Args:
            timeout: Not used (kept for interface compatibility)
            max_retries: Not used (kept for interface compatibility)
            **kwargs: Absorbs extra args like base_url for compatibility
        """
        self._service = None

    def _get_service(self):
        if self._service is None:
            self._service = _get_calendar_service()
        return self._service

    async def initialize(self) -> None:
        """No-op for interface compatibility with MCPCalendarClient."""
        # Eagerly build the service to fail fast on credential issues
        self._get_service()

    async def get_core_event_data(
        self,
        calendar_id: str,
        before: str,
        after: str,
    ) -> List[Dict[str, Any]]:
        """
        Get calendar events for scheduling.

        Args:
            calendar_id: Calendar ID (email address)
            before: END date (ISO datetime string) — yes, naming is counterintuitive
            after: START date (ISO datetime string) — yes, naming is counterintuitive

        Returns:
            List of event dicts matching the Core_Event_Data format:
            [{summary, id, start, end, locked, protected, flexible, transparent,
              attendees_list, attendees_details, number_of_attendees, internal_only}]
        """
        service = self._get_service()

        try:
            # The Google Calendar API events.list parameters:
            # timeMin = start of range, timeMax = end of range
            # "after" param = start date, "before" param = end date (counterintuitive naming)
            events_result = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=after,   # START date
                    timeMax=before,  # END date
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=500,
                )
                .execute()
            )
        except Exception as e:
            error_msg = str(e)
            if "404" in error_msg or "Not Found" in error_msg:
                raise MCPError(
                    code=-32603,
                    message=f"Calendar not found: {calendar_id}",
                )
            if "403" in error_msg or "forbidden" in error_msg.lower():
                raise MCPError(
                    code=-32603,
                    message=f"No access to calendar: {calendar_id}. "
                    "Ensure the calendar is shared with the authenticated account.",
                )
            raise MCPError(code=-32603, message=f"Calendar API error: {error_msg}")

        items = events_result.get("items", [])
        result = []

        for event in items:
            # Skip cancelled events
            if event.get("status") == "cancelled":
                continue

            # Extract start/end
            start = event.get("start", {})
            end = event.get("end", {})

            # Build attendees lists
            attendees_raw = event.get("attendees", [])
            attendees_list = [
                a["email"] for a in attendees_raw if "email" in a
            ]
            attendees_details = [
                {
                    "email": a.get("email", ""),
                    "name": a.get("displayName", a.get("email", "").split("@")[0]),
                }
                for a in attendees_raw
                if "email" in a
            ]

            # Compute scheduling classification flags
            flags = _classify_event(event)

            # Check if all attendees are internal (same domain)
            organizer_domain = (
                event.get("organizer", {}).get("email", "").split("@")[-1]
                if "@" in event.get("organizer", {}).get("email", "")
                else ""
            )
            internal_only = all(
                a.get("email", "").split("@")[-1] == organizer_domain
                for a in attendees_raw
                if "email" in a
            ) if organizer_domain and attendees_raw else True

            result.append(
                {
                    "summary": event.get("summary", "(No title)"),
                    "description": event.get("description", ""),
                    "id": event.get("id", ""),
                    "start": start,
                    "end": end,
                    "locked": flags["locked"],
                    "protected": flags["protected"],
                    "flexible": flags["flexible"],
                    "transparent": flags["transparent"],
                    "number_of_attendees": len(attendees_raw),
                    "internal_only": internal_only,
                    "attendees_list": attendees_list,
                    "attendees_details": attendees_details,
                }
            )

        return result

    async def fetch_event_by_id(
        self,
        calendar_id: str,
        event_id: str,
        days_forward: int = 14,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a specific event by ID.

        Uses events.get() for direct lookup (more efficient than
        MCPCalendarClient which had to list + filter).

        Args:
            calendar_id: Calendar ID (email address)
            event_id: Google Calendar event ID
            days_forward: Not used (kept for interface compatibility)

        Returns:
            Event dict in Core_Event_Data format, or None if not found.
        """
        service = self._get_service()

        try:
            event = (
                service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            )
        except Exception as e:
            error_msg = str(e)
            if "404" in error_msg or "Not Found" in error_msg:
                logger.warning(
                    "Event %s not found in calendar %s", event_id, calendar_id
                )
                return None
            raise MCPError(
                code=-32603,
                message=f"Error fetching event {event_id}: {error_msg}",
            )

        if event.get("status") == "cancelled":
            return None

        # Build same format as get_core_event_data
        attendees_raw = event.get("attendees", [])
        attendees_list = [a["email"] for a in attendees_raw if "email" in a]
        attendees_details = [
            {
                "email": a.get("email", ""),
                "name": a.get("displayName", a.get("email", "").split("@")[0]),
            }
            for a in attendees_raw
            if "email" in a
        ]
        flags = _classify_event(event)

        return {
            "summary": event.get("summary", "(No title)"),
            "description": event.get("description", ""),
            "id": event.get("id", ""),
            "start": event.get("start", {}),
            "end": event.get("end", {}),
            "locked": flags["locked"],
            "protected": flags["protected"],
            "flexible": flags["flexible"],
            "transparent": flags["transparent"],
            "number_of_attendees": len(attendees_raw),
            "attendees_list": attendees_list,
            "attendees_details": attendees_details,
        }
