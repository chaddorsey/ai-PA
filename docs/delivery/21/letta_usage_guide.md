# Letta Agent Usage Guide - Scheduling Orchestrator

## Overview

The scheduling orchestrator now supports **automatic event retrieval** via MCP. The Letta agent no longer needs to fetch calendar events before calling the orchestrator.

## Recommended Usage (New Mode)

### Minimum Required Information

```python
{
    "utterance": "Find 45 minutes with Alex and Priya next week",
    "participant_ids": ["cdorsey@concord.org", "alex@example.com", "priya@example.com"],
    "context_json": "{\"timeframe\": {\"from\": \"2025-12-08\", \"to\": \"2025-12-14\", \"tz\": \"America/New_York\"}}"
}
```

### What the Agent Needs to Provide

1. **utterance** (required): Natural language scheduling request
2. **participant_ids** (required for new mode): List of participant email addresses
3. **context_json** (required for new mode): Must include `timeframe` with:
   - `from`: Start date (YYYY-MM-DD)
   - `to`: End date (YYYY-MM-DD)
   - `tz`: Timezone (e.g., "America/New_York")

### Optional Parameters

- **user_id**: User's own email (for reference)
- **context_json.participants**: Work hours and preferences
- **context_json.policy**: Scheduling policies

## What the Tool Does Automatically

1. ✅ Fetches calendar events for all participants via MCP `Core_Event_Data`
2. ✅ Normalizes event data to expected format
3. ✅ Handles attendees information
4. ✅ Processes scheduling request
5. ✅ Returns optimal meeting proposals

## Schema Description (What Letta Sees)

The updated docstring ensures Letta sees:

- `participant_ids` as the **recommended** parameter
- Clear indication that the tool **fetches events automatically**
- No instructions to "call Get_Events first"
- `events_by_participant` marked as **legacy/optional**

## Example Agent Workflow

### Before (Complex):
```
1. User: "Find time with Alex and Priya next week"
2. Agent extracts: participants = ["alex@example.com", "priya@example.com"]
3. Agent calls Core_Event_Data for each participant
4. Agent formats events into JSON string
5. Agent calls orchestrate_scheduling with events
```

### After (Simple):
```
1. User: "Find time with Alex and Priya next week"
2. Agent extracts: 
   - participants = ["alex@example.com", "priya@example.com"]
   - timeframe = {"from": "2025-12-08", "to": "2025-12-14", "tz": "America/New_York"}
3. Agent calls orchestrate_scheduling with participant_ids
   (Tool fetches events automatically)
```

## Error Handling

The tool provides clear error messages:
- Missing timeframe: "timeframe is required in context_json when using participant_ids"
- Invalid participant: "Failed to fetch calendar events from MCP server: ..."
- Missing participants: "Missing events for participants: ..."

## Benefits

1. **Simpler**: Agent just provides participant IDs
2. **More Reliable**: No agent errors in event fetching/formatting
3. **No Size Limits**: Events fetched directly, not passed through agent
4. **Better Errors**: Orchestrator handles calendar API errors directly
5. **Faster**: Parallel fetching of all calendars

## Backward Compatibility

The legacy mode still works:
- Agent can still provide `events_by_participant` if needed
- Useful for testing or custom calendar sources
- Not recommended for normal use

## Next Steps for Agent

1. **Update Instructions**: Remove "call Get_Events first" instructions
2. **Use participant_ids**: Provide participant email addresses directly
3. **Include timeframe**: Always provide timeframe in context_json
4. **Test**: Verify the new mode works correctly

