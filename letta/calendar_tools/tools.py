"""
Google Calendar CRUD Tools

Comprehensive calendar event management tools following Letta conventions.
All functions follow the pattern: imports → try-except → defaults → logic → error handling
No nested def statements - all logic is inlined.
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
        OAUTH_KEY_FILE = os.getenv(
            "GMAIL_OAUTH_PATH",
            str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json")
        )
        TOKEN_PATH = os.getenv(
            "GMAIL_CREDENTIALS_PATH",
            str(Path.home() / ".gmail-mcp" / "calendar.credentials.json")
        )
        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        
        # Load credentials
        creds = None
        if os.path.exists(TOKEN_PATH):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            except Exception as e:
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
                        "calendars": [],
                        "count": 0,
                        "error_message": f"OAuth key file not found at {OAUTH_KEY_FILE}. Set GMAIL_OAUTH_PATH environment variable or place file at default location."
                    }
                
                flow = InstalledAppFlow.from_client_secrets_file(OAUTH_KEY_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
                
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
        return {
            "status": "error",
            "calendars": [],
            "count": 0,
            "error_message": f"Calendar API error: {str(e)}"
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
    import os
    from pathlib import Path
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
        
        # TODO: Add validation (task 25-8)
        # Validate datetime format, end after start, email addresses, etc.
        
        # Authentication logic (inline - will be documented in task 25-2)
        OAUTH_KEY_FILE = os.getenv(
            "GMAIL_OAUTH_PATH",
            str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json")
        )
        TOKEN_PATH = os.getenv(
            "GMAIL_CREDENTIALS_PATH",
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
                creds = flow.run_local_server(port=0)
                
                os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
                with open(TOKEN_PATH, "w") as token:
                    token.write(creds.to_json())
        
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
        return {
            "status": "error",
            "event": {},
            "error_message": f"Calendar API error: {str(e)}"
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
    max_results: Optional[int] = None,
    single_events: Optional[bool] = None,
    order_by: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve calendar events within a date range.
    
    Gets all events from the specified calendar that fall within the given
    time range, with options for result limits and sorting.
    
    Args:
        calendar_id: Calendar ID (email address) or "primary"
        time_min: ISO 8601 datetime string for start of query range (required)
        time_max: ISO 8601 datetime string for end of query range (required)
        max_results: Maximum number of events to return (default: 100)
        single_events: Expand recurring events (default: True)
        order_by: "startTime" or "updated" (default: "startTime")
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - events: List of event dictionaries with full event details
        - count: Number of events returned (if status is "ok")
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
        if max_results is None:
            max_results = 100
        if single_events is None:
            single_events = True
        if order_by is None:
            order_by = "startTime"
        
        # TODO: Add validation (task 25-8)
        
        # Authentication logic (inline)
        OAUTH_KEY_FILE = os.getenv(
            "GMAIL_OAUTH_PATH",
            str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json")
        )
        TOKEN_PATH = os.getenv(
            "GMAIL_CREDENTIALS_PATH",
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
                creds = flow.run_local_server(port=0)
                
                os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
                with open(TOKEN_PATH, "w") as token:
                    token.write(creds.to_json())
        
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
                "updated": evt.get("updated", "")
            })
        
        return {
            "status": "ok",
            "events": events,
            "count": len(events)
        }
    
    except HttpError as e:
        return {
            "status": "error",
            "events": [],
            "count": 0,
            "error_message": f"Calendar API error: {str(e)}"
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
        # TODO: Add validation (task 25-8)
        
        # Authentication logic (inline)
        OAUTH_KEY_FILE = os.getenv(
            "GMAIL_OAUTH_PATH",
            str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json")
        )
        TOKEN_PATH = os.getenv(
            "GMAIL_CREDENTIALS_PATH",
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
                creds = flow.run_local_server(port=0)
                
                os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
                with open(TOKEN_PATH, "w") as token:
                    token.write(creds.to_json())
        
        # Build Calendar service
        service = build("calendar", "v3", credentials=creds)
        
        # Get event
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        
        # Transform to structured format
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
            "updated": event.get("updated", "")
        }
        
        return {
            "status": "ok",
            "event": event_result
        }
    
    except HttpError as e:
        return {
            "status": "error",
            "event": {},
            "error_message": f"Calendar API error: {str(e)}"
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
    import os
    from pathlib import Path
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    
    try:
        # Set defaults
        if timezone is None:
            timezone = "America/New_York"
        
        # TODO: Add validation (task 25-8)
        
        # Authentication logic (inline)
        OAUTH_KEY_FILE = os.getenv(
            "GMAIL_OAUTH_PATH",
            str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json")
        )
        TOKEN_PATH = os.getenv(
            "GMAIL_CREDENTIALS_PATH",
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
                creds = flow.run_local_server(port=0)
                
                os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
                with open(TOKEN_PATH, "w") as token:
                    token.write(creds.to_json())
        
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
        return {
            "status": "error",
            "event": {},
            "error_message": f"Calendar API error: {str(e)}"
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
        
        # TODO: Add validation (task 25-8)
        
        # Authentication logic (inline)
        OAUTH_KEY_FILE = os.getenv(
            "GMAIL_OAUTH_PATH",
            str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json")
        )
        TOKEN_PATH = os.getenv(
            "GMAIL_CREDENTIALS_PATH",
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
                creds = flow.run_local_server(port=0)
                
                os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
                with open(TOKEN_PATH, "w") as token:
                    token.write(creds.to_json())
        
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
        return {
            "status": "error",
            "message": "",
            "event_id": event_id,
            "error_message": f"Calendar API error: {str(e)}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": "",
            "event_id": event_id,
            "error_message": f"Error deleting event: {str(e)}\n{traceback.format_exc()}"
        }
