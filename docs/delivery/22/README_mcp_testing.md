# MCP Summary Field Testing

This directory contains a test script to troubleshoot why MCP responses might have empty `summary` fields.

## Quick Start

```bash
# Set environment variables (optional - defaults provided)
export MCP_CALENDAR_SERVER_URL="http://localhost:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb"
export TEST_CALENDAR_ID="cdorsey@concord.org"
export TEST_EVENT_ID="6uhtevmd3ri7n5i5rv1pge7rin"

# Run the test
python docs/delivery/22/test_mcp_summary.py
```

## What the Test Does

1. **Initializes MCP Client**: Connects to the n8n MCP server
2. **Fetches Events**: Retrieves all events for the specified calendar in the next 30 days
3. **Analyzes Summary Fields**: 
   - Counts events with/without summaries
   - Shows examples of events with summaries
   - Displays detailed information for the target event
4. **Tests fetch_event_by_id**: Specifically tests the method used for rescheduling

## Output

The script will show:

- **Summary Statistics**: How many events have summaries vs empty/missing
- **Event Details**: Full structure of the target event
- **Field Analysis**: All fields present in the event, including `summary`, `attendees_list`, `attendees_details`
- **Type Information**: The actual type and value of the `summary` field

## Troubleshooting

### If summaries are empty:

1. **Check MCP Server Response**: The script shows the raw event structure
2. **Check Field Names**: The script checks for alternative field names (`title`, `name`, `subject`, etc.)
3. **Check Date Range**: Ensure the event is within the 30-day forward window
4. **Check Calendar ID**: Verify the calendar ID matches the event's calendar

### Common Issues:

- **Empty String vs None**: The script distinguishes between `summary: ""` (empty string) and `summary: None` (missing field)
- **Alternative Fields**: Some calendar systems use `title` instead of `summary`
- **Date Range**: Events outside the date range won't be found by `fetch_event_by_id`

## Example Output

```
================================================================================
MCP Event Summary Troubleshooting Test
================================================================================
MCP Server URL: http://localhost:5678/mcp/...
Calendar ID: cdorsey@concord.org
Event ID to find: 6uhtevmd3ri7n5i5rv1pge7rin

✓ MCP client initialized

Fetching events from 2025-12-06T00:00:00Z to 2026-01-05T23:59:59Z

✓ Fetched 39 events

================================================================================
Summary Field Analysis
================================================================================

Event 1: 6uhtevmd3ri7n5i5rv1pge7rin...
  Summary: EMPTY STRING
  Summary type: str
  Summary value (repr): ''
  All fields: ['id', 'summary', 'start', 'end', 'attendees_list', 'attendees_details', ...]
  ...
```

