# Google Calendar API Usage Investigation

## Executive Summary

After examining the codebase, **there are currently NO direct Google Calendar API calls** within Letta-facing tools. All calendar operations are currently routed through n8n workflows exposed as MCP tools. However, there IS a pattern for direct Google API integration (used for Drive Analytics), which could serve as a model for implementing native Google Calendar API support.

## Current Architecture

### Calendar Operations (via n8n MCP)

**Primary Location**: `letta/scheduling_orchestrator/mcp_client.py`

The `MCPCalendarClient` class handles all calendar event retrieval:

- **Protocol**: JSON-RPC 2.0 over HTTP
- **Endpoint**: `http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb`
- **Primary Tool**: `Core_Event_Data`
- **Method**: `get_core_event_data(calendar_id, before, after) -> List[Dict]`

**Used By**:
1. **Scheduling Orchestrator** (`letta/scheduling_orchestrator/orchestrate_scheduling.py`)
   - Fetches calendar events for participants during scheduling
   - Supports both participant-based and event-ID-based lookups
   - Handles rescheduling scenarios

2. **Daily Briefing Tool** (`letta/daily_briefing/generate_daily_briefing.py`)
   - Fetches calendar events for daily schedule generation
   - Retrieves events in a 3-day window (yesterday to day after tomorrow)
   - Filters and formats events for briefing display

### MCP Client Features

- Async/await pattern with `httpx`
- Session management with cookie persistence
- Retry logic (default: 3 attempts)
- Error handling with custom `MCPError` exception
- Supports SSE (Server-Sent Events) response format

## Direct Google API Integration Pattern (Drive Analytics)

**Location**: `letta/drive_analytics_tools.py`

This demonstrates the existing pattern for direct Google API integration:

### Authentication Pattern

```python
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# OAuth credentials stored in:
OAUTH_KEY_FILE = ~/.gmail-mcp/gcp-oauth.admin-reports.desktop.json
TOKEN_PATH = ~/.gmail-mcp/admin-reports.credentials.json

# Scopes defined per-service
SCOPES = [
    "https://www.googleapis.com/auth/admin.reports.audit.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.activity.readonly",
]

def _load_credentials():
    """Load/refresh OAuth credentials"""
    # Loads existing tokens, refreshes if expired
    # Runs local OAuth flow if no valid credentials exist
    return creds
```

### API Usage Pattern

```python
def _query_api(creds: Credentials):
    """Build service and query API"""
    service = build("drive", "v3", credentials=creds)
    # ... make API calls
    response = service.files().list(**params).execute()
    return response
```

### Key Characteristics

1. **OAuth 2.0 Flow**: Uses `InstalledAppFlow` for desktop app authentication
2. **Credential Management**: Stores and refreshes tokens automatically
3. **Service Building**: Uses `googleapiclient.discovery.build()` to create service clients
4. **Error Handling**: Handles `HttpError` from `googleapiclient.errors`
5. **Environment Configuration**: Uses environment variables for paths and credentials

## Google API Dependencies

**Location**: `letta/requirements.txt`

Existing dependencies that could support Calendar API:

```
google-api-python-client>=2.0.0
google-auth>=2.0.0
google-auth-oauthlib>=1.0.0
google-auth-httplib2>=0.1.0
```

These are already installed and could be used for Calendar API integration.

## Current Calendar Tools (Exposed via n8n MCP)

Based on documentation in `docs/delivery/21/`:

- **Core_Event_Data**: Stripped-down event data optimized for scheduling
- **Get_Events**: For user's own calendar (full event data)
- **Get_Events_On_Arbitrary_Calendar**: For other users' calendars

These tools are accessed via the n8n MCP server, which handles Google Calendar API authentication internally.

## Key Differences: n8n MCP vs Direct API

### n8n MCP Approach (Current)

**Advantages**:
- ✅ Centralized authentication management in n8n
- ✅ Easy workflow modification without code changes
- ✅ n8n handles OAuth token management
- ✅ Unified interface for multiple Google services

**Disadvantages**:
- ❌ Additional network hop adds latency
- ❌ Less flexibility for custom queries
- ❌ Dependency on n8n service availability
- ❌ Potential message size limits through MCP protocol

### Direct API Approach (Potential)

**Advantages**:
- ✅ Lower latency (direct API calls)
- ✅ Full flexibility of Google Calendar API
- ✅ Better error handling and retry control
- ✅ Can optimize queries for specific use cases
- ✅ No dependency on external service

**Disadvantages**:
- ❌ Need to manage OAuth credentials in code
- ❌ Code changes required for modifications
- ❌ Need to handle token refresh logic
- ❌ More complex error handling

## Recommended Scopes for Calendar API

Based on current usage patterns, the following scopes would likely be needed:

```python
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",  # Read calendar events
    "https://www.googleapis.com/auth/calendar",           # Full calendar access (for create/update)
]
```

Or for organization-wide access (domain-wide delegation):
```python
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar",
]
```

## Next Steps for Implementation

If moving to direct Google Calendar API integration:

1. **Create Calendar Client Module**
   - Similar structure to `drive_analytics_tools.py`
   - Handle OAuth credentials for Calendar API
   - Build Calendar service using `googleapiclient.discovery.build("calendar", "v3", credentials=creds)`

2. **Implement Core Functions**
   - `get_events(calendar_id, timeMin, timeMax) -> List[Event]`
   - `get_event_by_id(calendar_id, event_id) -> Event`
   - `create_event(calendar_id, event_data) -> Event`
   - `update_event(calendar_id, event_id, event_data) -> Event`
   - `delete_event(calendar_id, event_id) -> None`

3. **Migrate Existing Tools**
   - Update `MCPCalendarClient` or create parallel `GoogleCalendarClient`
   - Update `orchestrate_scheduling.py` to use direct API
   - Update `generate_daily_briefing.py` to use direct API

4. **Maintain Compatibility**
   - Consider supporting both MCP and direct API modes
   - Use environment variable to switch between approaches
   - Allow gradual migration

## Files to Review

- `letta/scheduling_orchestrator/mcp_client.py` - Current MCP calendar client
- `letta/drive_analytics_tools.py` - Reference implementation for direct Google API
- `letta/scheduling_orchestrator/orchestrate_scheduling.py` - Calendar event usage
- `letta/daily_briefing/generate_daily_briefing.py` - Calendar event usage
- `docs/delivery/21/mcp_calendar_integration_analysis.md` - Previous analysis of MCP approach

## Conclusion

While the codebase does NOT currently use direct Google Calendar API calls, there is a clear pattern established in `drive_analytics_tools.py` for direct Google API integration that could be adapted for Calendar operations. The infrastructure (dependencies, OAuth patterns) is already in place, making this a feasible path forward.

The main decision point is whether the benefits of direct API access (lower latency, more flexibility) outweigh the costs of managing authentication and maintaining the integration code, versus continuing to use n8n as an abstraction layer.

## Google Calendar API Permissions & Capabilities

### Using User OAuth Authentication (Same Pattern as Drive API)

When using the same user OAuth authentication pattern for Calendar API, your capabilities depend on **calendar sharing and permissions**, not just authentication:

#### 1. **Can you modify existing events on users' calendars?**

✅ **Yes, BUT only if:**
- The calendar owner has **shared their calendar** with your authenticated user account
- You have been granted at least **"Make changes to events"** permission level
- Or you have **"Make changes and manage sharing"** (owner/writer) access

❌ **No, if:**
- The calendar has not been shared with your account
- You only have "See only free/busy" or "See all event details" (read-only) access

**Key Point**: Authentication alone is not sufficient - explicit calendar sharing with write permissions is required.

#### 2. **Can you create events on users' calendars as yourself?**

✅ **Yes, BUT only if:**
- The calendar has been shared with your authenticated user account
- You have **"Make changes to events"** or higher permissions
- You specify the target `calendarId` in the `events.insert` API call

**What happens:**
- The event is created **by you** (your authenticated user account)
- It appears on **their calendar**
- The event creator/organizer will be your email address
- You can add them as attendees with permissions to modify
- Use the `attendees` field in the event payload to grant them edit permissions

**Example**:
```python
event = {
    'summary': 'Team Meeting',
    'start': {'dateTime': '2025-12-30T10:00:00-07:00'},
    'end': {'dateTime': '2025-12-30T11:00:00-07:00'},
    'attendees': [
        {'email': 'otheruser@concord.org', 'responseStatus': 'needsAction'},
    ],
    # You (authenticated user) will be the organizer by default
}
service.events().insert(calendarId='otheruser@concord.org', body=event).execute()
```

#### 3. **Can you see details of private events on their calendars?**

⚠️ **Partially - depends on your permission level:**

**Private events are ONLY fully visible if:**
- You have **"Make changes to events"** permission, OR
- You have **"Make changes and manage sharing"** permission

**Private events are NOT visible if:**
- You only have **"See all event details"** (read-only) - you'll only see "busy" blocks
- You only have **"See only free/busy"** - you'll only see availability

**Key Points:**
- Private events respect privacy settings even on shared calendars
- Read-only access (even "See all event details") does NOT reveal private event details
- Only write access or higher reveals private event contents
- The event's `visibility` property can be set to `"private"` programmatically, which enforces these rules

### Calendar Sharing Permission Levels

When a calendar owner shares their calendar, they can grant:

1. **See only free/busy (hide details)**: Time slots only, no event details
2. **See all event details**: Full event information, **except private events** (shows as busy)
3. **Make changes to events**: Can create, edit, delete events, **including private ones**
4. **Make changes and manage sharing**: Full control including sharing settings

### Domain-Wide Delegation Alternative

For organization-wide access without individual calendar sharing:

- Use **service account with domain-wide delegation**
- Allows impersonating users within your domain
- Requires Google Workspace admin setup
- Can access calendars without explicit sharing
- Different authentication pattern than user OAuth

### Important Limitations

1. **No automatic access**: Authenticating as a user does NOT automatically grant access to other users' calendars
2. **Sharing is required**: Each calendar must be explicitly shared with your authenticated account
3. **Permission levels matter**: What you can do depends on the permission level granted
4. **Private events are protected**: Even with read access, private events remain private unless you have write access
5. **Calendar list management**: Shared calendars may need to be added to your calendar list via `calendarList.insert` before they appear accessible

### Impact of Google Workspace Admin Access

**Important Clarification**: Having Google Workspace Super Admin privileges does **NOT** automatically grant you API access to users' calendars.

#### What Admin Access Does NOT Do:
- ❌ Does NOT bypass calendar sharing requirements in API calls
- ❌ Does NOT grant automatic access to user calendars via Calendar API
- ❌ Does NOT allow you to modify events without explicit sharing (using user OAuth)

#### What Admin Access DOES Enable:
- ✅ **You can set up domain-wide delegation yourself** (no need to request another admin)
- ✅ You can create service accounts and configure domain-wide delegation in Admin Console
- ✅ Once domain-wide delegation is configured, you can access all users' calendars programmatically

#### The Solution: Domain-Wide Delegation

With Super Admin access, you should **definitely use domain-wide delegation** because:

1. **You can set it up yourself**: Navigate to Admin Console > Security > API Controls > Domain-wide Delegation
2. **No individual calendar sharing needed**: Once configured, service account can access all calendars
3. **Better for automation**: Ideal for programmatic access across the organization
4. **Privacy-respecting**: Still respects user privacy settings, but allows access for organizational tools

#### Domain-Wide Delegation Setup (You Can Do This):

1. **Create Service Account** in Google Cloud Console
2. **Enable Domain-Wide Delegation** on the service account
3. **Authorize in Admin Console**: Add the service account's Client ID with Calendar scopes:
   - `https://www.googleapis.com/auth/calendar`
   - `https://www.googleapis.com/auth/calendar.events`
4. **Use Service Account Credentials** in your code to impersonate users

#### Updated Answer to Original Questions (With Admin Access):

1. **Modify events on users' calendars?**
   - ✅ **Yes**, if you set up domain-wide delegation (which you can do as admin)
   - ❌ **No**, if using user OAuth alone (even with admin account)

2. **Create events on their calendars?**
   - ✅ **Yes**, with domain-wide delegation service account (impersonating each user)
   - ✅ **Yes**, with user OAuth if calendars are shared with your account

3. **See private event details?**
   - ✅ **Yes**, with domain-wide delegation (service account has full access when impersonating)
   - ⚠️ **Only with write access**, even with domain-wide delegation (private events respect privacy)

### Recommendations for Your Use Case

Given that you have Super Admin access and likely need to:
- Read multiple users' calendars (for scheduling)
- Potentially create/modify events across calendars
- Access private event details for proper scheduling

**Recommendation: Use Service Account + Domain-Wide Delegation**

1. **Set up domain-wide delegation** (you have admin access, so you can do this)
2. **Use service account authentication** for Calendar API calls
3. **Impersonate users** as needed when accessing their calendars
4. **Benefits**:
   - No individual calendar sharing required
   - Organization-wide access
   - Proper authentication pattern for admin-level operations
   - More secure than sharing your personal account's OAuth credentials

**Note**: This is different from the Drive API pattern (which uses user OAuth). For Calendar API with admin access, service account is the recommended approach.

### Using Existing Shared Calendar Access via User OAuth

Since you already have shared calendar access and can create/modify events in the UI, you can use **user OAuth credentials** (same pattern as Drive API) to access those same calendars via the API.

#### How It Works

1. **Authenticate with User OAuth** (same as Drive API pattern)
   - Use `InstalledAppFlow` with Calendar scopes
   - Your authenticated user account will be used
   - Same credentials pattern as `drive_analytics_tools.py`

2. **List Calendars You Have Access To**
   - Call `calendarList.list()` to get all calendars you can access
   - Returns calendar IDs (typically email addresses) and permission levels
   - Includes both your own calendars and shared calendars

3. **Use Calendar ID to Create/Modify Events**
   - Use the `calendarId` (email address) as the calendar identifier
   - The same permissions you have in the UI apply to API calls
   - If you can modify in UI, you can modify via API (with same account)

#### Code Pattern (Following Drive API Style)

```python
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Same OAuth setup as Drive API
SCOPES = [
    "https://www.googleapis.com/auth/calendar",  # Full access (read + write)
    # Or use "https://www.googleapis.com/auth/calendar.readonly" for read-only
]

def _load_credentials():
    """Load OAuth credentials - same pattern as Drive API"""
    creds = None
    TOKEN_PATH = os.getenv("GMAIL_CREDENTIALS_PATH", 
                          str(Path.home() / ".gmail-mcp" / "calendar.credentials.json"))
    
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            OAUTH_KEY_FILE = os.getenv("GMAIL_OAUTH_PATH",
                                      str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json"))
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_KEY_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            
            # Save credentials
            with open(TOKEN_PATH, "w") as token:
                token.write(creds.to_json())
    
    return creds

def list_calendars():
    """List all calendars you have access to"""
    creds = _load_credentials()
    service = build("calendar", "v3", credentials=creds)
    
    calendars = []
    page_token = None
    
    while True:
        result = service.calendarList().list(pageToken=page_token).execute()
        calendars.extend(result.get('items', []))
        
        page_token = result.get('nextPageToken')
        if not page_token:
            break
    
    return calendars

def create_event(calendar_id: str, summary: str, start_time: str, end_time: str, 
                 attendees: List[str] = None):
    """Create an event on a shared calendar (calendar_id is typically email address)"""
    creds = _load_credentials()
    service = build("calendar", "v3", credentials=creds)
    
    event = {
        'summary': summary,
        'start': {'dateTime': start_time, 'timeZone': 'America/New_York'},
        'end': {'dateTime': end_time, 'timeZone': 'America/New_York'},
    }
    
    if attendees:
        event['attendees'] = [{'email': email} for email in attendees]
    
    try:
        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event
        ).execute()
        return created_event
    except HttpError as e:
        print(f"Error creating event: {e}")
        return None

def update_event(calendar_id: str, event_id: str, updates: dict):
    """Update an existing event on a shared calendar"""
    creds = _load_credentials()
    service = build("calendar", "v3", credentials=creds)
    
    try:
        # First get the existing event
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        
        # Apply updates
        event.update(updates)
        
        # Update the event
        updated_event = service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event
        ).execute()
        return updated_event
    except HttpError as e:
        print(f"Error updating event: {e}")
        return None

def get_events(calendar_id: str, time_min: str, time_max: str):
    """Get events from a calendar (your own or shared)"""
    creds = _load_credentials()
    service = build("calendar", "v3", credentials=creds)
    
    try:
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        return events_result.get('items', [])
    except HttpError as e:
        print(f"Error fetching events: {e}")
        return []
```

#### Key Points for Using Shared Calendars

1. **Calendar ID Format**: 
   - Typically the email address: `"cdorsey@concord.org"` or `"otheruser@concord.org"`
   - For your own primary calendar: use your email address or `"primary"`
   - For secondary calendars: may have custom IDs, check `calendarList.list()` output

2. **Permissions Match UI**:
   - If you can create/modify in the Google Calendar UI, you can do the same via API
   - API uses the same authenticated user account as the UI
   - Same permission levels apply

3. **Event Organizer**:
   - When you create an event on someone else's shared calendar, you are the organizer
   - The event appears on their calendar but is created by your account
   - You can add them as attendees with edit permissions

4. **Private Events**:
   - If you have write access to the calendar, you can see private events via API
   - Same visibility rules as UI

#### Example Usage

```python
# List calendars you have access to
calendars = list_calendars()
for cal in calendars:
    print(f"{cal['summary']}: {cal['id']} - Access: {cal.get('accessRole', 'unknown')}")

# Create event on shared calendar
create_event(
    calendar_id="colleague@concord.org",  # Calendar ID (email address)
    summary="Team Meeting",
    start_time="2025-12-30T10:00:00-05:00",
    end_time="2025-12-30T11:00:00-05:00",
    attendees=["colleague@concord.org"]
)

# Get events from shared calendar
events = get_events(
    calendar_id="colleague@concord.org",
    time_min="2025-12-01T00:00:00Z",
    time_max="2025-12-31T23:59:59Z"
)
```

#### Comparison: User OAuth vs Service Account

**User OAuth (Your Case - Existing Shared Access)**:
- ✅ Uses existing shared calendar permissions
- ✅ Same account as you use in UI
- ✅ Simple - just authenticate and use
- ✅ Works with calendars already shared with you
- ❌ Requires calendars to be explicitly shared
- ❌ Limited to calendars you have access to

**Service Account (Domain-Wide Delegation)**:
- ✅ Access to all calendars without individual sharing
- ✅ Better for organization-wide automation
- ❌ Requires setup of domain-wide delegation
- ❌ Different authentication pattern
- ❌ More complex setup

## Drive API Authentication Details

### Current Authentication Model

The Drive API setup uses **user OAuth credentials** (not service account impersonation):

1. **Authentication Type**: User OAuth 2.0 flow via `InstalledAppFlow`
   - User authenticates in browser when first running the tools
   - Credentials stored in `~/.gmail-mcp/admin-reports.credentials.json`
   - Uses `Credentials.from_authorized_user_file()` to load user tokens

2. **Authenticated User**: The credentials represent **the actual user who completed the OAuth flow**
   - No service account or impersonation happening
   - This user must have **Super Admin privileges** to use Admin Reports API
   - Typically would be `cdorsey@concord.org` based on the code defaults

3. **MY_EMAIL Variable**: 
   - Used as a query parameter (`user_key`) for Admin Reports API
   - Defaults to `"cdorsey@concord.org"` but can be set via environment variable
   - Does NOT represent impersonation - just tells the API which user's activity to retrieve
   - The API calls are still authenticated as the Super Admin user who authenticated

4. **Admin Reports API Behavior**:
   - Requires Super Admin account to access
   - Can query `user_key="all"` for organization-wide activity
   - Can query `user_key="cdorsey@concord.org"` for specific user's activity
   - Both queries use the same Super Admin credentials

### Key Takeaway

The **authenticated user** (whoever went through the OAuth flow) is the identity used for all API calls. For Calendar API integration, this would likely be the same pattern - the user who authenticates would be the one whose credentials are used. To access other users' calendars, you would need either:
- Domain-wide delegation with a service account, OR
- The authenticated user to have appropriate permissions/access to those calendars

