# PBI-25: Google Calendar CRUD Tool for Letta

## Overview
Deliver a comprehensive Google Calendar tool for Letta agents that provides full CRUD (Create, Read, Update, Delete) operations for calendar events. The tool uses user OAuth authentication (following the Drive API pattern) to access calendars that are already shared with the authenticated account, enabling creation and modification of events on both the user's own calendar and shared calendars. The tool supports comprehensive event properties including times with timezone specification, attendees, location, description, and file attachments.

[View in Backlog](../backlog.md#user-content-25)

## Problem Statement
Currently, calendar operations in Letta are routed through n8n MCP workflows, which adds latency and limits flexibility. While the scheduling orchestrator can fetch calendar events via MCP for read operations, there is no native Letta tool for creating or modifying calendar events. Users need the ability to:
- Create events on their own calendar or shared calendars they have access to
- Read event details from calendars they can access
- Update existing events (modify times, attendees, descriptions, etc.)
- Delete events they have permission to delete
- Attach files to calendar events
- Work with timezone-aware event scheduling

Direct Google Calendar API integration following the existing Drive API pattern would provide lower latency, better error handling, and full control over calendar operations.

## User Stories
- As a user, I want Letta to create calendar events on my calendar or shared calendars I have access to, so that I can schedule meetings through natural language requests.
- As a user, I want Letta to read calendar event details from calendars I can access, so that I can query meeting information and details.
- As a user, I want Letta to update existing calendar events (change times, attendees, descriptions), so that I can modify meetings without leaving the conversation.
- As a user, I want Letta to delete calendar events I have permission to delete, so that I can cancel meetings through conversation.
- As a user, I want Letta to attach files to calendar events, so that meeting materials are linked directly to the event.
- As a Letta agent, I want a calendar tool with clear CRUD operations and comprehensive parameter support, so that I can handle diverse calendar-related requests accurately.

## Technical Approach

### Architecture
- **Letta Integration**: Separate tool functions (one per CRUD operation) with typed signatures and comprehensive docstrings. Tools follow Letta's custom tool conventions (see `context/coding_custom_letta_tools.md`):
  - Module-level imports only for type hints (`from typing import Dict, Any, Optional, List`)
  - All runtime imports inside each function at the very beginning
  - No nested `def` statements - inline all helper logic (use lambdas for simple operations)
  - Entire function body wrapped in try-except
  - Return `Dict[str, Any]` with consistent structure
  - Tool code lives in `letta/calendar_tools/` directory
- **Authentication**: Use user OAuth 2.0 flow (same pattern as `drive_analytics_tools.py`)
  - OAuth credentials stored in `~/.gmail-mcp/calendar.credentials.json`
  - OAuth key file: `~/.gmail-mcp/gcp-oauth.calendar.desktop.json`
  - Scopes: `https://www.googleapis.com/auth/calendar` (read + write)
  - Authentication logic will be inlined in each tool function (following Letta conventions)
- **Google Calendar API**: Direct API integration using `google-api-python-client`
  - Build service: `build("calendar", "v3", credentials=creds)`
  - Use standard Calendar API methods: `events.insert`, `events.get`, `events.update`, `events.delete`, `events.list`
  - Handle `calendarList.list` to discover accessible calendars
- **Event Management**: 
  - Support for timezone-aware scheduling using `dateTime` with `timeZone` fields
  - Handle attendees with email addresses and optional response status
  - Support file attachments via Google Drive file IDs
  - Preserve event metadata (organizer, creation time, etc.)

### Dependencies
- Google API Python Client: `google-api-python-client>=2.0.0` (already in requirements.txt)
- Google Auth libraries: `google-auth>=2.0.0`, `google-auth-oauthlib>=1.0.0` (already in requirements.txt)
- Timezone handling: `pytz>=2023.3` (already in requirements.txt)
- Letta SDK: For tool registration via `create_from_function`

### Critical Letta Tool Structure Requirements

All calendar tools must follow Letta's custom tool conventions (see `context/coding_custom_letta_tools.md`):

1. **Function Structure**:
   - Module-level imports only for type hints: `from typing import Dict, Any, Optional, List`
   - All runtime imports inside function at the very beginning (before any other code)
   - Entire function wrapped in try-except
   - No nested `def` statements - inline all helper logic
   - Use lambdas for simple operations (sorting, filtering)
   - Use `async def` only if absolutely necessary for asyncio operations

2. **Code Order Within Function**:
   - Docstring
   - Imports (first thing after docstring)
   - try-except wrapper
   - Default value assignments (inside try)
   - Path setup (if needed for module imports)
   - Module imports (with fallbacks using try-except)
   - Main logic (all inlined, no helper functions)
   - Error handling (safe fallbacks in except block)

3. **Return Format**: All tools return `Dict[str, Any]` with:
   - `status`: "ok" or "error"
   - Tool-specific result data
   - `error_message`: Present if status is "error"

4. **Registration**: Tools registered using `client.tools.create_from_function(func=tool_function, tags=[...])`

## UX Flow (Agent)

### Create Event
1. User: "Create a meeting with Alex tomorrow at 2pm called 'Project Review'"
2. Agent calls `create_calendar_event()` with appropriate parameters
3. Tool creates event on specified calendar (or user's primary calendar)
4. Agent confirms event creation with event details

### Read Event
1. User: "What's on my calendar for tomorrow?" or "Show me the details of the 2pm meeting"
2. Agent calls `get_calendar_events()` or `get_calendar_event()` 
3. Tool retrieves event(s) from calendar
4. Agent displays event information to user

### Update Event
1. User: "Move the 2pm meeting to 3pm" or "Add Sarah to the Project Review meeting"
2. Agent calls `update_calendar_event()` with event ID and updates
3. Tool modifies the event
4. Agent confirms the update

### Delete Event
1. User: "Cancel the 2pm meeting tomorrow"
2. Agent calls `delete_calendar_event()` with event ID
3. Tool deletes the event
4. Agent confirms deletion

## Functional Requirements

### FR1: Authentication and Calendar Discovery
- Tool authenticates using user OAuth 2.0 (same pattern as Drive API)
- Tool can list all calendars the authenticated user has access to via `calendarList.list`
- Tool supports using calendar ID (typically email address) for operations
- Tool handles authentication errors gracefully with clear messages

### FR2: Create Event (`create_calendar_event`)
- **Required Parameters**:
  - `calendar_id` (str): Calendar ID (email address) or "primary" for user's primary calendar
  - `summary` (str): Event title/summary
  - `start_datetime` (str): ISO 8601 datetime string (e.g., "2025-12-30T14:00:00")
  - `end_datetime` (str): ISO 8601 datetime string
- **Optional Parameters**:
  - `timezone` (str): IANA timezone (e.g., "America/New_York"), defaults to "America/New_York"
  - `description` (str): Event description text
  - `location` (str): Event location text
  - `attendees` (List[str]): List of email addresses for attendees
  - `attachment_file_ids` (List[str]): List of Google Drive file IDs to attach
- **Returns**: Event object with ID, creation details, and full event data

### FR3: Get Events (`get_calendar_events`)
- **Required Parameters**:
  - `calendar_id` (str): Calendar ID (email address) or "primary"
  - `time_min` (str): ISO 8601 datetime string for start of query range
  - `time_max` (str): ISO 8601 datetime string for end of query range
- **Optional Parameters**:
  - `max_results` (int): Maximum number of events to return (default: 100)
  - `single_events` (bool): Expand recurring events (default: True)
- **Returns**: List of event objects with full details

### FR4: Get Single Event (`get_calendar_event`)
- **Required Parameters**:
  - `calendar_id` (str): Calendar ID (email address) or "primary"
  - `event_id` (str): Event ID from calendar
- **Returns**: Complete event object with all details

### FR5: Update Event (`update_calendar_event`)
- **Required Parameters**:
  - `calendar_id` (str): Calendar ID (email address) or "primary"
  - `event_id` (str): Event ID of event to update
- **Optional Parameters** (all optional, only provided fields are updated):
  - `summary` (str): New event title
  - `start_datetime` (str): New start datetime (ISO 8601)
  - `end_datetime` (str): New end datetime (ISO 8601)
  - `timezone` (str): Timezone for datetime fields
  - `description` (str): New description
  - `location` (str): New location
  - `attendees` (List[str]): New attendees list (replaces existing)
  - `attachment_file_ids` (List[str]): New attachments list (replaces existing)
- **Returns**: Updated event object

### FR6: Delete Event (`delete_calendar_event`)
- **Required Parameters**:
  - `calendar_id` (str): Calendar ID (email address) or "primary"
  - `event_id` (str): Event ID of event to delete
- **Optional Parameters**:
  - `send_updates` (str): "all", "externalOnly", or "none" (default: "all")
- **Returns**: Success confirmation or error details

### FR7: List Accessible Calendars (`list_calendars`)
- **Optional Parameters**: None
- **Returns**: List of calendars with:
  - Calendar ID (email address)
  - Summary (display name)
  - Access role (owner, writer, reader, etc.)
  - Primary calendar indicator

### FR8: Timezone Support
- All datetime operations support explicit timezone specification
- Default timezone: "America/New_York" (configurable)
- Datetime strings include timezone information or timezone specified separately
- Event times stored and retrieved with proper timezone handling

### FR9: File Attachments
- Support attaching Google Drive files to events
- Accept Drive file IDs in `attachment_file_ids` parameter
- Files must be accessible to attendees (or shared appropriately)
- Attachment metadata included in event response

### FR10: Error Handling
- Handle API errors gracefully with descriptive messages
- Handle permission errors (calendar not shared, insufficient permissions)
- Handle invalid calendar IDs or event IDs
- Handle authentication failures with clear instructions
- Provide structured error responses for agent handling

## Goals & Non-Goals

### Goals
- Full CRUD functionality for calendar events
- Support for all standard event properties (title, description, attendees, location, times, attachments)
- Timezone-aware event scheduling
- Support for both own calendar and shared calendars
- Clear, well-documented tool interfaces
- Follows existing Drive API authentication pattern
- Proper error handling and validation

### Non-Goals
- Domain-wide delegation or service account authentication (uses user OAuth)
- Calendar sharing management (only uses already-shared calendars)
- Recurring event series management (single event operations)
- Event reminders configuration (focus on core CRUD)
- Calendar creation/deletion (focus on events only)
- Multiple timezone conversions in single call (one timezone per operation)

## Acceptance Criteria

1. **Authentication**: Tool authenticates using user OAuth and loads/stores credentials correctly
2. **Create Event**: Can create events on primary calendar and shared calendars with all supported fields
3. **Read Events**: Can retrieve single events and lists of events within date ranges
4. **Update Event**: Can update any event property on events user has permission to modify
5. **Delete Event**: Can delete events user has permission to delete
6. **List Calendars**: Can list all accessible calendars with permission levels
7. **Timezone Handling**: All datetime operations respect specified timezones correctly
8. **File Attachments**: Can attach Google Drive files to events
9. **Error Handling**: Handles all error cases gracefully with clear messages
10. **Tool Registration**: All tools registered with Letta with correct schemas
11. **Documentation**: Comprehensive docstrings and parameter documentation
12. **Testing**: Manual testing confirms all CRUD operations work correctly

## Dependencies
- Google API Python Client library (already available)
- Google Auth libraries (already available)
- User OAuth credentials configured (calendar OAuth key file)
- Calendars already shared with authenticated user account
- Letta SDK for tool registration

## Open Questions
- Should this be one comprehensive tool with operation parameter, or separate tools for each CRUD operation?
  - **Decision**: Separate tools for clarity and better schema generation
- Should we support recurring event series operations?
  - **Decision**: Not in initial version (focus on single events)
- How should we handle event reminders/settings?
  - **Decision**: Not in initial version (focus on core event data)
- Should we provide a convenience tool that combines create + send invites?
  - **Decision**: Create operation can include attendees, which sends invites automatically
- How should authentication code be structured given Letta's no-nested-functions requirement?
  - **Decision**: Authentication logic will be inlined in each tool function (following pattern from `generate_daily_briefing.py`)

## Related Tasks
- [Back to task list](./tasks.md)
- Tasks tracked in `docs/delivery/25/tasks.md` with detailed files
