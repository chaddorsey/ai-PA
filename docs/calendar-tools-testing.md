# Calendar Tools Testing Guide

## Quick Test: Direct Function Call

Test the tools directly using the test script:

```bash
python3 letta/test_calendar_tools.py
```

This will test the `list_calendars` tool and should show your calendars.

## Testing via Letta Agent

The calendar tools should be registered and attached to your agent. You can test them by:

### 1. Verify Tools are Attached

Check if tools are attached to your agent (replace with your agent ID):

```bash
export LETTA_AGENT_ID=agent-892a2d58-b9f6-4baf-84f3-c431fe46487d
python3 letta/register_calendar_tools.py
```

This will show which tools are registered and attached.

### 2. Test via Letta UI

1. Open Letta UI at http://localhost:8283
2. Select your agent
3. Use the chat interface to test calendar operations, for example:
   - "List my calendars"
   - "Show me events on my calendar for tomorrow"
   - "Create a test event for tomorrow at 2pm"

### 3. Test CRUD Operations

#### Test Create Event

```python
from letta.calendar_tools.tools import create_calendar_event

result = create_calendar_event(
    calendar_id="your-email@example.com",  # Use your primary calendar ID
    summary="Test Event",
    start_datetime="2025-01-24T14:00:00",
    end_datetime="2025-01-24T15:00:00",
    timezone="America/New_York",
    description="This is a test event",
    location="Test Location"
)
print(result)
```

#### Test Get Events

```python
from letta.calendar_tools.tools import get_calendar_events

result = get_calendar_events(
    calendar_id="your-email@example.com",
    time_min="2025-01-24T00:00:00Z",
    time_max="2025-01-25T00:00:00Z"
)
print(result)
```

#### Test Update Event

```python
from letta.calendar_tools.tools import update_calendar_event

# Use an event ID from a previous get_calendar_events call
result = update_calendar_event(
    calendar_id="your-email@example.com",
    event_id="event-id-here",
    summary="Updated Test Event"
)
print(result)
```

#### Test Delete Event

```python
from letta.calendar_tools.tools import delete_calendar_event

result = delete_calendar_event(
    calendar_id="your-email@example.com",
    event_id="event-id-here",
    send_updates="none"  # or "all" to notify attendees
)
print(result)
```

## Expected Results

- **list_calendars**: Should return all calendars you have access to
- **create_calendar_event**: Should create an event and return event details with ID
- **get_calendar_events**: Should return events in the specified time range
- **update_calendar_event**: Should update the event and return updated details
- **delete_calendar_event**: Should delete the event and return success status

## Troubleshooting

### Authentication Errors

If you get authentication errors:
1. Verify credentials file exists: `ls -la ~/.gmail-mcp/calendar.credentials.json`
2. Check credentials are valid (not expired)
3. Re-run authentication if needed: `python3 letta/calendar_tools/authenticate_calendar.py`

### Tool Not Found Errors

If tools aren't found in Letta:
1. Re-register tools: `python3 letta/register_calendar_tools.py`
2. Verify agent ID is correct
3. Check Letta logs for registration errors

### Permission Errors

If you get permission errors:
1. Verify the calendar ID is correct (use `list_calendars` to see available calendars)
2. Check that you have write access to the calendar you're trying to modify
3. For shared calendars, ensure they're properly shared with your account
