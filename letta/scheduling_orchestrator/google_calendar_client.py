"""
Google Calendar client for the scheduling orchestrator using gws CLI.

Uses the gws CLI (Google Workspace CLI) to make Calendar API calls via
subprocess, replacing the previous google-api-python-client implementation.

Credentials are mounted at /root/.gws/credentials.json (same OAuth2 tokens
used by gws-bridge and other gws-based services).

Interface is compatible with MCPCalendarClient so orchestrate_scheduling.py
can swap imports with minimal changes.
"""

import json
import logging
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Re-export MCPError for backward compatibility with orchestrate_scheduling.py imports
from mcp_client import MCPError

GWS_CMD = "/usr/local/bin/gws"


def _gws_calendar(resource: str, method: str, params: Dict[str, Any]) -> Any:
    """
    Run a gws calendar CLI command and return parsed JSON output.

    Args:
        resource: Calendar API resource (e.g. "events")
        method: API method (e.g. "list", "get")
        params: API parameters as a dict

    Returns:
        Parsed JSON response from gws.

    Raises:
        MCPError: On API errors (404, 403, etc.)
    """
    cmd = [GWS_CMD, "calendar", resource, method, "--params", json.dumps(params)]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise MCPError(code=-32603, message="gws calendar command timed out after 30s")
    except FileNotFoundError:
        raise MCPError(
            code=-32603,
            message=f"gws CLI not found at {GWS_CMD}. Check Dockerfile installation.",
        )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "404" in stderr or "Not Found" in stderr or "notFound" in stderr:
            raise MCPError(code=-32603, message=f"Calendar API 404: {stderr}")
        if "403" in stderr or "forbidden" in stderr.lower():
            raise MCPError(code=-32603, message=f"Calendar API 403: {stderr}")
        raise MCPError(code=-32603, message=f"gws calendar error: {stderr}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise MCPError(
            code=-32603,
            message=f"Failed to parse gws output: {e}\nstdout: {result.stdout[:500]}",
        )


def _classify_event(event: Dict[str, Any]) -> Dict[str, bool]:
    """
    Compute scheduling classification flags for a calendar event.

    Uses description markers matching the n8n Core_Event_Data workflow:
    - [lk] in description -> locked (cannot be moved)
    - [pr] in description -> protected (important, shouldn't move)
    - neither -> flexible (can be freely rescheduled)
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
    Google Calendar client using gws CLI.

    Drop-in replacement for MCPCalendarClient with the same interface:
    - initialize() (verifies gws is available)
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
        pass

    async def initialize(self) -> None:
        """Verify gws CLI is available and working."""
        try:
            result = subprocess.run(
                [GWS_CMD, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise MCPError(
                    code=-32603,
                    message=f"gws CLI check failed: {result.stderr.strip()}",
                )
            logger.info("gws CLI available: %s", result.stdout.strip())
        except FileNotFoundError:
            raise MCPError(
                code=-32603,
                message=f"gws CLI not found at {GWS_CMD}. Check Dockerfile installation.",
            )

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
        params = {
            "calendarId": calendar_id,
            "timeMin": after,    # START date
            "timeMax": before,   # END date
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": 500,
        }

        try:
            events_result = _gws_calendar("events", "list", params)
        except MCPError as e:
            if "404" in e.message:
                raise MCPError(
                    code=-32603,
                    message=f"Calendar not found: {calendar_id}",
                )
            if "403" in e.message:
                raise MCPError(
                    code=-32603,
                    message=f"No access to calendar: {calendar_id}. "
                    "Ensure the calendar is shared with the authenticated account.",
                )
            raise

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

        Args:
            calendar_id: Calendar ID (email address)
            event_id: Google Calendar event ID
            days_forward: Not used (kept for interface compatibility)

        Returns:
            Event dict in Core_Event_Data format, or None if not found.
        """
        params = {
            "calendarId": calendar_id,
            "eventId": event_id,
        }

        try:
            event = _gws_calendar("events", "get", params)
        except MCPError as e:
            if "404" in e.message:
                logger.warning(
                    "Event %s not found in calendar %s", event_id, calendar_id
                )
                return None
            raise MCPError(
                code=-32603,
                message=f"Error fetching event {event_id}: {e.message}",
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
