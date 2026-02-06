"""
Google Calendar CRUD Tools

Comprehensive calendar event management tools following Letta conventions.
All functions follow the pattern: imports → try-except → defaults → logic → error handling
No nested def statements - all logic is inlined.

This module provides full CRUD (Create, Read, Update, Delete) operations for Google Calendar events
using user OAuth authentication. All tools use direct Google Calendar API integration for
low latency and full API flexibility.

Authentication:
- Uses user OAuth 2.0 flow (same pattern as drive_analytics_tools.py)
- Credentials stored in ~/.gmail-mcp/calendar.credentials.json
- OAuth key file: ~/.gmail-mcp/gcp-oauth.calendar.desktop.json
- Scope: https://www.googleapis.com/auth/calendar

All tools support calendars that are already shared with the authenticated user account.
"""

from typing import Dict, Any, Optional, List


def list_calendars() -> Dict[str, Any]:
    """
    List all calendars accessible to the authenticated user.
    
    Returns all calendars the user has access to, including their own calendars
    and shared calendars, with permission levels and metadata.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - calendars: List of calendar dictionaries, each containing:
          - id: Calendar ID (email address or custom ID)
          - summary: Display name of the calendar
          - accessRole: Permission level (owner, writer, reader, etc.)
          - primary: Boolean indicating if this is the primary calendar
          - timeZone: Calendar timezone
        - count: Total number of calendars (if status is "ok")
        - error_message: Error message if status is "error"
    """
    # Import required modules inside function for Letta tool extraction
    import traceback
    import os
    import sys
    from pathlib import Path
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    
    try:
        # Authentication logic (inline - will be documented in task 25-2)
        # Check for calendar-specific OAuth path first, then fall back to shared GMAIL_OAUTH_PATH
        # The same OAuth key file can be used for multiple scopes
        OAUTH_KEY_FILE = os.getenv(
            "CALENDAR_OAUTH_PATH",
            os.getenv(
                "GMAIL_OAUTH_PATH",
                str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json")
            )
        )
        # Use calendar-specific token path (separate from admin-reports tokens)
        # IMPORTANT: Don't use GMAIL_CREDENTIALS_PATH as it points to admin-reports.credentials.json
        # Always use calendar.credentials.json for calendar tools
        TOKEN_PATH = os.getenv(
            "CALENDAR_CREDENTIALS_PATH",
            str(Path.home() / ".gmail-mcp" / "calendar.credentials.json")
        )
        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        
        # Load credentials
        creds = None
        credential_load_error = None
        
        # Debug: Check path resolution
        token_path_exists = os.path.exists(TOKEN_PATH)
        oauth_key_exists = os.path.exists(OAUTH_KEY_FILE)
        
        if not token_path_exists:
            # Return early with diagnostic info
            return {
                "status": "error",
                "calendars": [],
                "count": 0,
                "error_message": (
                    f"Credentials file not found at {TOKEN_PATH}. "
                    f"File exists check: {token_path_exists}. "
                    f"Current directory: {os.getcwd()}. "
                    f"HOME: {os.path.expanduser('~')}. "
                    f"Please run: python3 letta/calendar_tools/authenticate_calendar.py"
                )
            }
        
        if token_path_exists:
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            except Exception as e:
                # Store error for debugging
                credential_load_error = f"Failed to load credentials from {TOKEN_PATH}: {type(e).__name__}: {str(e)}"
                creds = None
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            
            if not creds:
                # Include diagnostic information in error message
                error_parts = [
                    "OAuth authentication required. Calendar credentials not found or invalid.",
                    f"TOKEN_PATH: {TOKEN_PATH}",
                    f"TOKEN_PATH exists: {token_path_exists}",
                    f"OAUTH_KEY_FILE: {OAUTH_KEY_FILE}",
                    f"OAUTH_KEY_FILE exists: {oauth_key_exists}",
                ]
                
                if credential_load_error:
                    error_parts.append(f"Load error: {credential_load_error}")
                
                error_parts.extend([
                    "",
                    "Please run the authentication script on your host machine:",
                    "",
                    "  python3 letta/calendar_tools/authenticate_calendar.py",
                    "",
                    "This will save credentials to ~/.gmail-mcp/calendar.credentials.json",
                    "which is mounted in the Docker container at /root/.gmail-mcp/calendar.credentials.json"
                ])
                
                if not oauth_key_exists:
                    return {
                        "status": "error",
                        "calendars": [],
                        "count": 0,
                        "error_message": f"OAuth key file not found at {OAUTH_KEY_FILE}. Set CALENDAR_OAUTH_PATH or GMAIL_OAUTH_PATH environment variable."
                    }
                
                return {
                    "status": "error",
                    "calendars": [],
                    "count": 0,
                    "error_message": "\n".join(error_parts)
                }
                
                os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
                with open(TOKEN_PATH, "w") as token:
                    token.write(creds.to_json())
        
        # Build Calendar service
        service = build("calendar", "v3", credentials=creds)
        
        # List calendars
        calendars_result = service.calendarList().list().execute()
        calendars_list = calendars_result.get('items', [])
        
        # Transform to structured format
        calendars = []
        for cal in calendars_list:
            calendars.append({
                "id": cal.get("id", ""),
                "summary": cal.get("summary", ""),
                "accessRole": cal.get("accessRole", ""),
                "primary": cal.get("primary", False),
                "timeZone": cal.get("timeZone", "")
            })
        
        return {
            "status": "ok",
            "calendars": calendars,
            "count": len(calendars)
        }
    
    except HttpError as e:
        # Map HTTP status codes to meaningful error messages
        status_code = e.resp.status if hasattr(e.resp, 'status') else None
        error_details = e.error_details if hasattr(e, 'error_details') else None
        
        if status_code == 401:
            error_msg = "Authentication required. Please run the tool again to complete OAuth flow."
        elif status_code == 403:
            error_msg = "Permission denied. Ensure your account has access to the calendar API and required scopes."
        elif status_code == 404:
            error_msg = "Calendar not found. Check that the calendar ID is correct."
        elif status_code == 400:
            error_msg = f"Invalid request: {str(e)}"
        else:
            error_msg = f"Calendar API error ({status_code}): {str(e)}"
        
        if error_details:
            error_msg += f" Details: {error_details}"
        
        return {
            "status": "error",
            "calendars": [],
            "count": 0,
            "error_message": error_msg
        }
    except Exception as e:
        return {
            "status": "error",
            "calendars": [],
            "count": 0,
            "error_message": f"Error listing calendars: {str(e)}\n{traceback.format_exc()}"
        }


def create_calendar_event(
    calendar_id: str,
    summary: str,
    start_datetime: str,
    end_datetime: str,
    timezone: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    attachment_file_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Create a new calendar event.
    
    Creates an event on the specified calendar (own or shared calendar with write access).
    Supports all standard event properties including attendees and file attachments.
    
    Args:
        calendar_id: Calendar ID (email address) or "primary" for user's primary calendar
        summary: Event title/summary (required)
        start_datetime: ISO 8601 datetime string (e.g., "2025-12-30T14:00:00") (required)
        end_datetime: ISO 8601 datetime string (required)
        timezone: IANA timezone (e.g., "America/New_York"), defaults to "America/New_York"
        description: Event description text (optional)
        location: Event location text (optional)
        attendees: List of email addresses for attendees (optional)
        attachment_file_ids: List of Google Drive file IDs to attach (optional)
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - event: Event dictionary with full event details including:
          - id: Event ID (for future updates/deletes)
          - summary: Event title
          - start: Start time with timezone
          - end: End time with timezone
          - description: Event description
          - location: Event location
          - attendees: List of attendees
          - attachments: List of attachments
          - created: Creation timestamp
          - updated: Last update timestamp
        - error_message: Error message if status is "error"
    """
    # Import required modules inside function for Letta tool extraction
    import traceback
    import re
    import os
    from pathlib import Path
    from datetime import datetime
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    
    try:
        # Set defaults
        if timezone is None:
            timezone = "America/New_York"
        if attendees is None:
            attendees = []
        if attachment_file_ids is None:
            attachment_file_ids = []
        
        # Validation (inline - no helper functions)
        # Validate calendar_id
        if not calendar_id or not isinstance(calendar_id, str):
            return {
                "status": "error",
                "event": {},
                "error_message": "calendar_id is required and must be a string"
            }
        
        # Validate required fields
        if not summary or not isinstance(summary, str):
            return {
                "status": "error",
                "event": {},
                "error_message": "summary is required and must be a string"
            }
        
        if not start_datetime or not isinstance(start_datetime, str):
            return {
                "status": "error",
                "event": {},
                "error_message": "start_datetime is required and must be an ISO 8601 datetime string"
            }
        
        if not end_datetime or not isinstance(end_datetime, str):
            return {
                "status": "error",
                "event": {},
                "error_message": "end_datetime is required and must be an ISO 8601 datetime string"
            }
        
        # Validate datetime format (basic ISO 8601 check)
        datetime_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
        if not re.match(datetime_pattern, start_datetime):
            return {
                "status": "error",
                "event": {},
                "error_message": f"start_datetime must be in ISO 8601 format (e.g., '2025-12-30T14:00:00'). Got: {start_datetime}"
            }
        
        if not re.match(datetime_pattern, end_datetime):
            return {
                "status": "error",
                "event": {},
                "error_message": f"end_datetime must be in ISO 8601 format (e.g., '2025-12-30T15:00:00'). Got: {end_datetime}"
            }
        
        # Validate end is after start
        try:
            start_dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_datetime.replace('Z', '+00:00'))
            if end_dt <= start_dt:
                return {
                    "status": "error",
                    "event": {},
                    "error_message": "end_datetime must be after start_datetime"
                }
        except ValueError as e:
            return {
                "status": "error",
                "event": {},
                "error_message": f"Invalid datetime format: {str(e)}"
            }
        
        # Validate email addresses in attendees
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        for attendee in attendees:
            if not isinstance(attendee, str) or not re.match(email_pattern, attendee):
                return {
                    "status": "error",
                    "event": {},
                    "error_message": f"Invalid email address in attendees: {attendee}"
                }
        
        # Validate attachment file IDs are strings
        for file_id in attachment_file_ids:
            if not isinstance(file_id, str) or not file_id:
                return {
                    "status": "error",
                    "event": {},
                    "error_message": f"Invalid file ID in attachment_file_ids: {file_id}"
                }
        
        # Authentication logic (inline - will be documented in task 25-2)
        # Check for calendar-specific OAuth path first, then fall back to shared GMAIL_OAUTH_PATH
        # The same OAuth key file can be used for multiple scopes
        OAUTH_KEY_FILE = os.getenv(
            "CALENDAR_OAUTH_PATH",
            os.getenv(
                "GMAIL_OAUTH_PATH",
                str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json")
            )
        )
        # Use calendar-specific token path (separate from admin-reports tokens)
        # IMPORTANT: Don't use GMAIL_CREDENTIALS_PATH as it points to admin-reports.credentials.json
        # Always use calendar.credentials.json for calendar tools
        TOKEN_PATH = os.getenv(
            "CALENDAR_CREDENTIALS_PATH",
            str(Path.home() / ".gmail-mcp" / "calendar.credentials.json")
        )
        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        
        # Load credentials
        creds = None
        if os.path.exists(TOKEN_PATH):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            except Exception:
                pass
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            
            if not creds:
                if not os.path.exists(OAUTH_KEY_FILE):
                    return {
                        "status": "error",
                        "event": {},
                        "error_message": f"OAuth key file not found at {OAUTH_KEY_FILE}. Set GMAIL_OAUTH_PATH environment variable."
                    }
                
                flow = InstalledAppFlow.from_client_secrets_file(OAUTH_KEY_FILE, SCOPES)
                # Browser-based auth doesn't work in Docker - need manual authentication
                # Return error with instructions for user to authenticate manually
                return {
                    "status": "error",
                    "event": {},
                    "error_message": (
                        "OAuth authentication required. Calendar credentials not found. "
                        "Please run the authentication script on your host machine:\n\n"
                        "  python3 letta/calendar_tools/authenticate_calendar.py\n\n"
                        "This will save credentials to ~/.gmail-mcp/calendar.credentials.json "
                        "which is mounted in the Docker container at /root/.gmail-mcp/calendar.credentials.json"
                    )
                }
        
        # Build Calendar service
        service = build("calendar", "v3", credentials=creds)
        
        # Build event body
        event_body = {
            "summary": summary,
            "start": {
                "dateTime": start_datetime,
                "timeZone": timezone
            },
            "end": {
                "dateTime": end_datetime,
                "timeZone": timezone
            }
        }
        
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        if attendees:
            event_body["attendees"] = [{"email": email, "responseStatus": "needsAction"} for email in attendees]
        if attachment_file_ids:
            event_body["attachments"] = [{"fileId": file_id} for file_id in attachment_file_ids]
        
        # Create event
        created_event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
        
        # Transform response
        event_result = {
            "id": created_event.get("id", ""),
            "summary": created_event.get("summary", ""),
            "start": created_event.get("start", {}),
            "end": created_event.get("end", {}),
            "description": created_event.get("description", ""),
            "location": created_event.get("location", ""),
            "attendees": created_event.get("attendees", []),
            "attachments": created_event.get("attachments", []),
            "created": created_event.get("created", ""),
            "updated": created_event.get("updated", "")
        }
        
        return {
            "status": "ok",
            "event": event_result
        }
    
    except HttpError as e:
        # Map HTTP status codes to meaningful error messages
        status_code = e.resp.status if hasattr(e.resp, 'status') else None
        error_details = e.error_details if hasattr(e, 'error_details') else None
        
        if status_code == 401:
            error_msg = "Authentication required. Please run the tool again to complete OAuth flow."
        elif status_code == 403:
            error_msg = "Permission denied. The calendar may not be shared with your account, or you don't have write access. Ensure the calendar is shared with 'Make changes to events' permission."
        elif status_code == 404:
            error_msg = "Calendar not found. Check that the calendar ID is correct."
        elif status_code == 400:
            error_msg = f"Invalid request: {str(e)}"
        else:
            error_msg = f"Calendar API error ({status_code}): {str(e)}"
        
        if error_details:
            error_msg += f" Details: {error_details}"
        
        return {
            "status": "error",
            "event": {},
            "error_message": error_msg
        }
    except Exception as e:
        return {
            "status": "error",
            "event": {},
            "error_message": f"Error creating event: {str(e)}\n{traceback.format_exc()}"
        }


def get_calendar_events(
    calendar_id: str,
    time_min: str,
    time_max: str,
    max_results: Optional[str] = None,
    single_events: Optional[str] = None,
    order_by: Optional[str] = None,
    attendee_emails: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve calendar events within a date range.

    Gets all events from the specified calendar that fall within the given
    time range, with options for result limits and sorting. Optionally filter
    by attendee email addresses.

    Args:
        calendar_id: Calendar ID (email address) or "primary"
        time_min: RFC3339 datetime string with timezone for start of query range (required).
            MUST include timezone suffix. Examples: "2026-01-27T00:00:00Z" (UTC) or
            "2026-01-27T00:00:00-05:00" (EST). If timezone is omitted, UTC (Z) is assumed.
        time_max: RFC3339 datetime string with timezone for end of query range (required).
            MUST include timezone suffix. Examples: "2026-01-28T00:00:00Z" (UTC) or
            "2026-01-28T00:00:00-05:00" (EST). If timezone is omitted, UTC (Z) is assumed.
        max_results: Maximum number of events to return as string (default: "100")
        single_events: Expand recurring events as string "true" or "false" (default: "true")
        order_by: "startTime" or "updated" (default: "startTime")
        attendee_emails: Comma-separated list of attendee email addresses to filter by.
            Returns events where at least one of the specified attendees is present.
            Example: "person1@example.com,person2@example.com"

    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - events: List of event dictionaries with full event details
        - count: Number of events returned (if status is "ok")
        - error_message: Error message if status is "error"
    """
    # Import required modules inside function for Letta tool extraction
    import traceback
    import re
    import os
    from pathlib import Path
    from datetime import datetime
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    
    try:
        # Convert string parameters (workaround for Letta Optional[int]/Optional[bool] handling)
        # max_results: str -> int
        if max_results is None or max_results == "" or max_results == "None":
            max_results = 100
        elif isinstance(max_results, int):
            pass  # Already int
        elif isinstance(max_results, str):
            try:
                max_results = int(max_results)
            except ValueError:
                max_results = 100
        else:
            max_results = 100

        # single_events: str -> bool
        if single_events is None or single_events == "" or single_events == "None":
            single_events = True
        elif isinstance(single_events, bool):
            pass  # Already bool
        elif isinstance(single_events, str):
            single_events = single_events.lower() in ("true", "1", "yes")
        else:
            single_events = True

        # order_by: already str
        if order_by is None or order_by == "" or order_by == "None":
            order_by = "startTime"
        
        # Validation (inline - no helper functions)
        # Validate calendar_id
        if not calendar_id or not isinstance(calendar_id, str):
            return {
                "status": "error",
                "events": [],
                "count": 0,
                "error_message": "calendar_id is required and must be a string"
            }
        
        # Validate required fields
        if not time_min or not isinstance(time_min, str):
            return {
                "status": "error",
                "events": [],
                "count": 0,
                "error_message": "time_min is required and must be an ISO 8601 datetime string"
            }
        
        if not time_max or not isinstance(time_max, str):
            return {
                "status": "error",
                "events": [],
                "count": 0,
                "error_message": "time_max is required and must be an ISO 8601 datetime string"
            }
        
        # Validate datetime format
        datetime_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
        if not re.match(datetime_pattern, time_min):
            return {
                "status": "error",
                "events": [],
                "count": 0,
                "error_message": f"time_min must be in ISO 8601 format. Got: {time_min}"
            }
        
        if not re.match(datetime_pattern, time_max):
            return {
                "status": "error",
                "events": [],
                "count": 0,
                "error_message": f"time_max must be in ISO 8601 format. Got: {time_max}"
            }

        # Auto-fix missing timezone: Google Calendar API requires RFC3339 with timezone
        # If no timezone suffix (Z or +/-HH:MM), append Z (UTC)
        timezone_pattern = r'.*([Zz]|[+-]\d{2}:\d{2})$'
        if not re.match(timezone_pattern, time_min):
            time_min = time_min + 'Z'
        if not re.match(timezone_pattern, time_max):
            time_max = time_max + 'Z'

        # Validate time_max is after time_min
        try:
            min_dt = datetime.fromisoformat(time_min.replace('Z', '+00:00'))
            max_dt = datetime.fromisoformat(time_max.replace('Z', '+00:00'))
            if max_dt <= min_dt:
                return {
                    "status": "error",
                    "events": [],
                    "count": 0,
                    "error_message": "time_max must be after time_min"
                }
        except ValueError as e:
            return {
                "status": "error",
                "events": [],
                "count": 0,
                "error_message": f"Invalid datetime format: {str(e)}"
            }
        
        # Validate max_results
        if not isinstance(max_results, int) or max_results < 1 or max_results > 2500:
            return {
                "status": "error",
                "events": [],
                "count": 0,
                "error_message": "max_results must be an integer between 1 and 2500"
            }
        
        # Validate order_by
        if order_by not in ["startTime", "updated"]:
            return {
                "status": "error",
                "events": [],
                "count": 0,
                "error_message": "order_by must be 'startTime' or 'updated'"
            }
        
        # Authentication logic (inline)
        # Check for calendar-specific OAuth path first, then fall back to shared GMAIL_OAUTH_PATH
        # The same OAuth key file can be used for multiple scopes
        OAUTH_KEY_FILE = os.getenv(
            "CALENDAR_OAUTH_PATH",
            os.getenv(
                "GMAIL_OAUTH_PATH",
                str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json")
            )
        )
        # Use calendar-specific token path (separate from admin-reports tokens)
        # IMPORTANT: Don't use GMAIL_CREDENTIALS_PATH as it points to admin-reports.credentials.json
        # Always use calendar.credentials.json for calendar tools
        TOKEN_PATH = os.getenv(
            "CALENDAR_CREDENTIALS_PATH",
            str(Path.home() / ".gmail-mcp" / "calendar.credentials.json")
        )
        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        
        # Load credentials
        creds = None
        if os.path.exists(TOKEN_PATH):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            except Exception:
                pass
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            
            if not creds:
                if not os.path.exists(OAUTH_KEY_FILE):
                    return {
                        "status": "error",
                        "events": [],
                        "count": 0,
                        "error_message": f"OAuth key file not found at {OAUTH_KEY_FILE}. Set GMAIL_OAUTH_PATH environment variable."
                    }
                
                flow = InstalledAppFlow.from_client_secrets_file(OAUTH_KEY_FILE, SCOPES)
                # Browser-based auth doesn't work in Docker - need manual authentication
                # Return error with instructions for user to authenticate manually
                return {
                    "status": "error",
                    "event": {},
                    "error_message": (
                        "OAuth authentication required. Calendar credentials not found. "
                        "Please run the authentication script on your host machine:\n\n"
                        "  python3 letta/calendar_tools/authenticate_calendar.py\n\n"
                        "This will save credentials to ~/.gmail-mcp/calendar.credentials.json "
                        "which is mounted in the Docker container at /root/.gmail-mcp/calendar.credentials.json"
                    )
                }
        
        # Build Calendar service
        service = build("calendar", "v3", credentials=creds)
        
        # Build query parameters
        params = {
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": max_results,
            "singleEvents": single_events,
            "orderBy": order_by
        }
        
        # Get events
        events_result = service.events().list(calendarId=calendar_id, **params).execute()
        events_list = events_result.get('items', [])
        
        # Handle pagination if needed
        page_token = events_result.get('nextPageToken')
        while page_token and len(events_list) < max_results:
            params['pageToken'] = page_token
            next_page = service.events().list(calendarId=calendar_id, **params).execute()
            events_list.extend(next_page.get('items', []))
            page_token = next_page.get('nextPageToken')
            if not page_token:
                break
        
        # Transform to structured format
        events = []
        for evt in events_list:
            # Google Calendar API returns "transparency" with values "transparent" (free) or "opaque" (busy)
            # Convert to boolean for easier handling: True = free/transparent, False = busy/opaque
            raw_transparency = evt.get("transparency", "opaque")  # Default to opaque (busy)
            is_transparent = raw_transparency == "transparent"

            events.append({
                "id": evt.get("id", ""),
                "summary": evt.get("summary", ""),
                "start": evt.get("start", {}),
                "end": evt.get("end", {}),
                "description": evt.get("description", ""),
                "location": evt.get("location", ""),
                "attendees": evt.get("attendees", []),
                "organizer": evt.get("organizer", {}),
                "attachments": evt.get("attachments", []),
                "created": evt.get("created", ""),
                "updated": evt.get("updated", ""),
                "transparent": is_transparent  # True = free/available, False = busy/blocking
            })

        # Filter by attendee emails if specified
        if attendee_emails and attendee_emails.strip():
            # Parse comma-separated emails (inline - no helper function)
            filter_emails = [email.strip().lower() for email in attendee_emails.split(',') if email.strip()]

            if filter_emails:
                filtered_events = []
                for event in events:
                    attendees = event.get("attendees", [])
                    # Check if any of the filter emails match any attendee
                    event_attendee_emails = [
                        att.get("email", "").lower()
                        for att in attendees
                        if isinstance(att, dict) and att.get("email")
                    ]
                    # Include event if any filter email matches any attendee
                    if any(filter_email in event_attendee_emails for filter_email in filter_emails):
                        filtered_events.append(event)

                events = filtered_events

        return {
            "status": "ok",
            "events": events,
            "count": len(events)
        }
    
    except HttpError as e:
        # Map HTTP status codes to meaningful error messages
        status_code = e.resp.status if hasattr(e.resp, 'status') else None
        error_details = e.error_details if hasattr(e, 'error_details') else None
        
        if status_code == 401:
            error_msg = "Authentication required. Please run the tool again to complete OAuth flow."
        elif status_code == 403:
            error_msg = "Permission denied. The calendar may not be shared with your account. Ensure the calendar is shared with at least 'See all event details' permission."
        elif status_code == 404:
            error_msg = "Calendar not found. Check that the calendar ID is correct."
        elif status_code == 400:
            error_msg = f"Invalid request: {str(e)}"
        else:
            error_msg = f"Calendar API error ({status_code}): {str(e)}"
        
        if error_details:
            error_msg += f" Details: {error_details}"
        
        return {
            "status": "error",
            "events": [],
            "count": 0,
            "error_message": error_msg
        }
    except Exception as e:
        return {
            "status": "error",
            "events": [],
            "count": 0,
            "error_message": f"Error retrieving events: {str(e)}\n{traceback.format_exc()}"
        }


def get_calendar_event(
    calendar_id: str,
    event_id: str
) -> Dict[str, Any]:
    """
    Retrieve a single calendar event by ID.
    
    Gets the complete details of a specific event from the calendar.
    
    Args:
        calendar_id: Calendar ID (email address) or "primary"
        event_id: Event ID from calendar (required)
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - event: Event dictionary with complete event details including:
          - id: Event ID
          - summary: Event title
          - start: Start time with timezone
          - end: End time with timezone
          - description: Event description
          - location: Event location
          - attendees: List of attendees with response status
          - organizer: Organizer information
          - attachments: List of attachments
          - created: Creation timestamp
          - updated: Last update timestamp
        - error_message: Error message if status is "error"
    """
    # Import required modules inside function for Letta tool extraction
    import traceback
    import os
    from pathlib import Path
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    
    try:
        # Validation (inline - no helper functions)
        # Validate calendar_id
        if not calendar_id or not isinstance(calendar_id, str):
            return {
                "status": "error",
                "event": {},
                "error_message": "calendar_id is required and must be a string"
            }
        
        # Validate event_id
        if not event_id or not isinstance(event_id, str):
            return {
                "status": "error",
                "event": {},
                "error_message": "event_id is required and must be a string"
            }
        
        # Authentication logic (inline)
        # Check for calendar-specific OAuth path first, then fall back to shared GMAIL_OAUTH_PATH
        # The same OAuth key file can be used for multiple scopes
        OAUTH_KEY_FILE = os.getenv(
            "CALENDAR_OAUTH_PATH",
            os.getenv(
                "GMAIL_OAUTH_PATH",
                str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json")
            )
        )
        # Use calendar-specific token path (separate from admin-reports tokens)
        # IMPORTANT: Don't use GMAIL_CREDENTIALS_PATH as it points to admin-reports.credentials.json
        # Always use calendar.credentials.json for calendar tools
        TOKEN_PATH = os.getenv(
            "CALENDAR_CREDENTIALS_PATH",
            str(Path.home() / ".gmail-mcp" / "calendar.credentials.json")
        )
        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        
        # Load credentials
        creds = None
        if os.path.exists(TOKEN_PATH):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            except Exception:
                pass
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            
            if not creds:
                if not os.path.exists(OAUTH_KEY_FILE):
                    return {
                        "status": "error",
                        "event": {},
                        "error_message": f"OAuth key file not found at {OAUTH_KEY_FILE}. Set GMAIL_OAUTH_PATH environment variable."
                    }
                
                flow = InstalledAppFlow.from_client_secrets_file(OAUTH_KEY_FILE, SCOPES)
                # Browser-based auth doesn't work in Docker - need manual authentication
                # Return error with instructions for user to authenticate manually
                return {
                    "status": "error",
                    "event": {},
                    "error_message": (
                        "OAuth authentication required. Calendar credentials not found. "
                        "Please run the authentication script on your host machine:\n\n"
                        "  python3 letta/calendar_tools/authenticate_calendar.py\n\n"
                        "This will save credentials to ~/.gmail-mcp/calendar.credentials.json "
                        "which is mounted in the Docker container at /root/.gmail-mcp/calendar.credentials.json"
                    )
                }
        
        # Build Calendar service
        service = build("calendar", "v3", credentials=creds)
        
        # Get event
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        
        # Transform to structured format
        # Google Calendar API returns "transparency" with values "transparent" (free) or "opaque" (busy)
        # Convert to boolean for easier handling: True = free/transparent, False = busy/opaque
        raw_transparency = event.get("transparency", "opaque")  # Default to opaque (busy)
        is_transparent = raw_transparency == "transparent"

        event_result = {
            "id": event.get("id", ""),
            "summary": event.get("summary", ""),
            "start": event.get("start", {}),
            "end": event.get("end", {}),
            "description": event.get("description", ""),
            "location": event.get("location", ""),
            "attendees": event.get("attendees", []),
            "organizer": event.get("organizer", {}),
            "attachments": event.get("attachments", []),
            "created": event.get("created", ""),
            "updated": event.get("updated", ""),
            "transparent": is_transparent  # True = free/available, False = busy/blocking
        }

        return {
            "status": "ok",
            "event": event_result
        }
    
    except HttpError as e:
        # Map HTTP status codes to meaningful error messages
        status_code = e.resp.status if hasattr(e.resp, 'status') else None
        error_details = e.error_details if hasattr(e, 'error_details') else None
        
        if status_code == 401:
            error_msg = "Authentication required. Please run the tool again to complete OAuth flow."
        elif status_code == 403:
            error_msg = "Permission denied. The calendar may not be shared with your account, or you don't have write access. Ensure the calendar is shared with 'Make changes to events' permission."
        elif status_code == 404:
            error_msg = "Calendar not found. Check that the calendar ID is correct."
        elif status_code == 400:
            error_msg = f"Invalid request: {str(e)}"
        else:
            error_msg = f"Calendar API error ({status_code}): {str(e)}"
        
        if error_details:
            error_msg += f" Details: {error_details}"
        
        return {
            "status": "error",
            "event": {},
            "error_message": error_msg
        }
    except Exception as e:
        return {
            "status": "error",
            "event": {},
            "error_message": f"Error retrieving event: {str(e)}\n{traceback.format_exc()}"
        }


def update_calendar_event(
    calendar_id: str,
    event_id: str,
    summary: Optional[str] = None,
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None,
    timezone: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    attachment_file_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Update an existing calendar event.
    
    Modifies an existing event, updating only the fields that are provided.
    All other fields remain unchanged. Supports partial updates.
    
    Args:
        calendar_id: Calendar ID (email address) or "primary"
        event_id: Event ID of event to update (required)
        summary: New event title (optional)
        start_datetime: New start datetime (ISO 8601) (optional)
        end_datetime: New end datetime (ISO 8601) (optional)
        timezone: Timezone for datetime fields (optional, defaults to "America/New_York")
        description: New description (optional)
        location: New location (optional)
        attendees: New attendees list - replaces existing (optional)
        attachment_file_ids: New attachments list - replaces existing (optional)
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - event: Updated event dictionary with full event details
        - error_message: Error message if status is "error"
    """
    # Import required modules inside function for Letta tool extraction
    import traceback
    import re
    import os
    from pathlib import Path
    from datetime import datetime
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    
    try:
        # Set defaults
        if timezone is None:
            timezone = "America/New_York"

        # Normalize empty strings to None (agent may pass "" for omitted fields)
        if summary == "":
            summary = None
        if start_datetime == "":
            start_datetime = None
        if end_datetime == "":
            end_datetime = None
        if description == "":
            description = None
        if location == "":
            location = None
        if attendees is not None and len(attendees) == 0:
            attendees = None
        if attachment_file_ids is not None and len(attachment_file_ids) == 0:
            attachment_file_ids = None

        # Validation (inline - no helper functions)
        # Validate calendar_id
        if not calendar_id or not isinstance(calendar_id, str):
            return {
                "status": "error",
                "event": {},
                "error_message": "calendar_id is required and must be a string"
            }
        
        # Validate event_id
        if not event_id or not isinstance(event_id, str):
            return {
                "status": "error",
                "event": {},
                "error_message": "event_id is required and must be a string"
            }
        
        # Validate datetime formats if provided
        datetime_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
        
        if start_datetime is not None:
            if not isinstance(start_datetime, str) or not re.match(datetime_pattern, start_datetime):
                return {
                    "status": "error",
                    "event": {},
                    "error_message": f"start_datetime must be in ISO 8601 format. Got: {start_datetime}"
                }
        
        if end_datetime is not None:
            if not isinstance(end_datetime, str) or not re.match(datetime_pattern, end_datetime):
                return {
                    "status": "error",
                    "event": {},
                    "error_message": f"end_datetime must be in ISO 8601 format. Got: {end_datetime}"
                }
        
        # Validate end is after start if both provided
        if start_datetime is not None and end_datetime is not None:
            try:
                start_dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_datetime.replace('Z', '+00:00'))
                if end_dt <= start_dt:
                    return {
                        "status": "error",
                        "event": {},
                        "error_message": "end_datetime must be after start_datetime"
                    }
            except ValueError as e:
                return {
                    "status": "error",
                    "event": {},
                    "error_message": f"Invalid datetime format: {str(e)}"
                }
        
        # Validate email addresses in attendees if provided
        if attendees is not None:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            for attendee in attendees:
                if not isinstance(attendee, str) or not re.match(email_pattern, attendee):
                    return {
                        "status": "error",
                        "event": {},
                        "error_message": f"Invalid email address in attendees: {attendee}"
                    }
        
        # Validate attachment file IDs if provided
        if attachment_file_ids is not None:
            for file_id in attachment_file_ids:
                if not isinstance(file_id, str) or not file_id:
                    return {
                        "status": "error",
                        "event": {},
                        "error_message": f"Invalid file ID in attachment_file_ids: {file_id}"
                    }
        
        # Authentication logic (inline)
        # Check for calendar-specific OAuth path first, then fall back to shared GMAIL_OAUTH_PATH
        # The same OAuth key file can be used for multiple scopes
        OAUTH_KEY_FILE = os.getenv(
            "CALENDAR_OAUTH_PATH",
            os.getenv(
                "GMAIL_OAUTH_PATH",
                str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json")
            )
        )
        # Use calendar-specific token path (separate from admin-reports tokens)
        # IMPORTANT: Don't use GMAIL_CREDENTIALS_PATH as it points to admin-reports.credentials.json
        # Always use calendar.credentials.json for calendar tools
        TOKEN_PATH = os.getenv(
            "CALENDAR_CREDENTIALS_PATH",
            str(Path.home() / ".gmail-mcp" / "calendar.credentials.json")
        )
        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        
        # Load credentials
        creds = None
        if os.path.exists(TOKEN_PATH):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            except Exception:
                pass
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            
            if not creds:
                if not os.path.exists(OAUTH_KEY_FILE):
                    return {
                        "status": "error",
                        "event": {},
                        "error_message": f"OAuth key file not found at {OAUTH_KEY_FILE}. Set GMAIL_OAUTH_PATH environment variable."
                    }
                
                flow = InstalledAppFlow.from_client_secrets_file(OAUTH_KEY_FILE, SCOPES)
                # Browser-based auth doesn't work in Docker - need manual authentication
                # Return error with instructions for user to authenticate manually
                return {
                    "status": "error",
                    "event": {},
                    "error_message": (
                        "OAuth authentication required. Calendar credentials not found. "
                        "Please run the authentication script on your host machine:\n\n"
                        "  python3 letta/calendar_tools/authenticate_calendar.py\n\n"
                        "This will save credentials to ~/.gmail-mcp/calendar.credentials.json "
                        "which is mounted in the Docker container at /root/.gmail-mcp/calendar.credentials.json"
                    )
                }
        
        # Build Calendar service
        service = build("calendar", "v3", credentials=creds)
        
        # Retrieve existing event
        existing_event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        
        # Update only provided fields
        if summary is not None:
            existing_event["summary"] = summary
        if start_datetime is not None:
            existing_event["start"] = {
                "dateTime": start_datetime,
                "timeZone": timezone
            }
        if end_datetime is not None:
            existing_event["end"] = {
                "dateTime": end_datetime,
                "timeZone": timezone
            }
        if description is not None:
            existing_event["description"] = description
        if location is not None:
            existing_event["location"] = location
        if attendees is not None:
            existing_event["attendees"] = [{"email": email, "responseStatus": "needsAction"} for email in attendees]
        if attachment_file_ids is not None:
            existing_event["attachments"] = [{"fileId": file_id} for file_id in attachment_file_ids]
        
        # Update event
        updated_event = service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=existing_event
        ).execute()
        
        # Transform response
        event_result = {
            "id": updated_event.get("id", ""),
            "summary": updated_event.get("summary", ""),
            "start": updated_event.get("start", {}),
            "end": updated_event.get("end", {}),
            "description": updated_event.get("description", ""),
            "location": updated_event.get("location", ""),
            "attendees": updated_event.get("attendees", []),
            "attachments": updated_event.get("attachments", []),
            "created": updated_event.get("created", ""),
            "updated": updated_event.get("updated", "")
        }
        
        return {
            "status": "ok",
            "event": event_result
        }
    
    except HttpError as e:
        # Map HTTP status codes to meaningful error messages
        status_code = e.resp.status if hasattr(e.resp, 'status') else None
        error_details = e.error_details if hasattr(e, 'error_details') else None
        
        if status_code == 401:
            error_msg = "Authentication required. Please run the tool again to complete OAuth flow."
        elif status_code == 403:
            error_msg = "Permission denied. The calendar may not be shared with your account, or you don't have write access. Ensure the calendar is shared with 'Make changes to events' permission."
        elif status_code == 404:
            error_msg = "Calendar not found. Check that the calendar ID is correct."
        elif status_code == 400:
            error_msg = f"Invalid request: {str(e)}"
        else:
            error_msg = f"Calendar API error ({status_code}): {str(e)}"
        
        if error_details:
            error_msg += f" Details: {error_details}"
        
        return {
            "status": "error",
            "event": {},
            "error_message": error_msg
        }
    except Exception as e:
        return {
            "status": "error",
            "event": {},
            "error_message": f"Error updating event: {str(e)}\n{traceback.format_exc()}"
        }


def delete_calendar_event(
    calendar_id: str,
    event_id: str,
    send_updates: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete a calendar event.
    
    Removes an event from the calendar. Optionally sends cancellation emails
    to attendees based on the send_updates parameter.
    
    Args:
        calendar_id: Calendar ID (email address) or "primary"
        event_id: Event ID of event to delete (required)
        send_updates: "all", "externalOnly", or "none" (default: "all")
          - "all": Send cancellation emails to all attendees
          - "externalOnly": Send cancellation emails only to external attendees
          - "none": Do not send cancellation emails
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - message: Confirmation message if status is "ok"
        - event_id: ID of deleted event (if status is "ok")
        - error_message: Error message if status is "error"
    """
    # Import required modules inside function for Letta tool extraction
    import traceback
    import os
    from pathlib import Path
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    
    try:
        # Set defaults
        if send_updates is None:
            send_updates = "all"
        
        # Validation (inline - no helper functions)
        # Validate calendar_id
        if not calendar_id or not isinstance(calendar_id, str):
            return {
                "status": "error",
                "message": "",
                "event_id": event_id if event_id else "",
                "error_message": "calendar_id is required and must be a string"
            }
        
        # Validate event_id
        if not event_id or not isinstance(event_id, str):
            return {
                "status": "error",
                "message": "",
                "event_id": "",
                "error_message": "event_id is required and must be a string"
            }
        
        # Validate send_updates
        if send_updates not in ["all", "externalOnly", "none"]:
            return {
                "status": "error",
                "message": "",
                "event_id": event_id,
                "error_message": "send_updates must be 'all', 'externalOnly', or 'none'"
            }
        
        # Authentication logic (inline)
        # Check for calendar-specific OAuth path first, then fall back to shared GMAIL_OAUTH_PATH
        # The same OAuth key file can be used for multiple scopes
        OAUTH_KEY_FILE = os.getenv(
            "CALENDAR_OAUTH_PATH",
            os.getenv(
                "GMAIL_OAUTH_PATH",
                str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json")
            )
        )
        # Use calendar-specific token path (separate from admin-reports tokens)
        # IMPORTANT: Don't use GMAIL_CREDENTIALS_PATH as it points to admin-reports.credentials.json
        # Always use calendar.credentials.json for calendar tools
        TOKEN_PATH = os.getenv(
            "CALENDAR_CREDENTIALS_PATH",
            str(Path.home() / ".gmail-mcp" / "calendar.credentials.json")
        )
        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        
        # Load credentials
        creds = None
        if os.path.exists(TOKEN_PATH):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            except Exception:
                pass
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            
            if not creds:
                if not os.path.exists(OAUTH_KEY_FILE):
                    return {
                        "status": "error",
                        "message": "",
                        "event_id": event_id,
                        "error_message": f"OAuth key file not found at {OAUTH_KEY_FILE}. Set GMAIL_OAUTH_PATH environment variable."
                    }
                
                flow = InstalledAppFlow.from_client_secrets_file(OAUTH_KEY_FILE, SCOPES)
                # Browser-based auth doesn't work in Docker - need manual authentication
                # Return error with instructions for user to authenticate manually
                return {
                    "status": "error",
                    "event": {},
                    "error_message": (
                        "OAuth authentication required. Calendar credentials not found. "
                        "Please run the authentication script on your host machine:\n\n"
                        "  python3 letta/calendar_tools/authenticate_calendar.py\n\n"
                        "This will save credentials to ~/.gmail-mcp/calendar.credentials.json "
                        "which is mounted in the Docker container at /root/.gmail-mcp/calendar.credentials.json"
                    )
                }
        
        # Build Calendar service
        service = build("calendar", "v3", credentials=creds)
        
        # Delete event
        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id,
            sendUpdates=send_updates
        ).execute()
        
        return {
            "status": "ok",
            "message": f"Event {event_id} deleted successfully",
            "event_id": event_id
        }
    
    except HttpError as e:
        # Map HTTP status codes to meaningful error messages
        status_code = e.resp.status if hasattr(e.resp, 'status') else None
        error_details = e.error_details if hasattr(e, 'error_details') else None
        
        if status_code == 401:
            error_msg = "Authentication required. Please run the tool again to complete OAuth flow."
        elif status_code == 403:
            error_msg = "Permission denied. You may not have delete access to this event, or the calendar is not shared with your account."
        elif status_code == 404:
            error_msg = f"Event not found. The event ID '{event_id}' may be incorrect or the event may have been deleted."
        elif status_code == 400:
            error_msg = f"Invalid request: {str(e)}"
        else:
            error_msg = f"Calendar API error ({status_code}): {str(e)}"
        
        if error_details:
            error_msg += f" Details: {error_details}"
        
        return {
            "status": "error",
            "message": "",
            "event_id": event_id,
            "error_message": error_msg
        }
    except Exception as e:
        return {
            "status": "error",
            "message": "",
            "event_id": event_id,
            "error_message": f"Error deleting event: {str(e)}\n{traceback.format_exc()}"
        }
