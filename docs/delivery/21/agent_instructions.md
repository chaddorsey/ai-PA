# Scheduling Orchestration Tool - Agent Instructions

## Overview

The `orchestrate_scheduling` tool uses constraint-based optimization to find optimal meeting times. **IMPORTANT**: The tool automatically fetches calendar events via MCP - you don't need to call `Get_Events` or `Core_Event_Data` first.

## Quick Start

**Required inputs**:
- `utterance`: Natural language request (e.g., "Find 45 minutes with Alex & Priya next Tuesday morning")
- `participant_ids`: List of participant emails (e.g., `["cdorsey@concord.org", "alex@example.com"]`)
- `context_json`: JSON string with `timeframe` (REQUIRED):
  ```json
  {"timeframe": {"from": "2025-12-08", "to": "2025-12-14", "tz": "America/New_York"}}
  ```

**Optional inputs**:
- `user_id`: User's email (for reference)
- `event_id` + `event_participant_id`: For rescheduling (see below)

**What the tool does automatically**:
- ✅ Fetches calendar events for all participants via MCP
- ✅ Extracts requirements from natural language
- ✅ Finds optimal times minimizing disruption
- ✅ Returns ready-to-schedule proposals

**You do NOT need to**:
- ❌ Call `Get_Events` or `Core_Event_Data` first
- ❌ Format events into JSON
- ❌ Filter or process events

## Response Handling

**Status: "ok"**:
- Present proposal from `proposals[0]`
- Use `explanation` to explain why this time was chosen
- Check `moved_events` for any events that need moving
- Ask user if they want to schedule

**Status: "unsat"**:
- Explain no solution found
- Present `relaxations` suggestions
- Ask which constraints to relax, then re-call with updated `context_json`

**Status: "bad_input"**:
- Check `error_message`
- Fix issue (timeframe missing, invalid JSON, etc.) and retry

## Rescheduling Existing Meetings

**Method 1: Explicit Event ID** (when you have the event ID):
```python
{
  "utterance": "Find new time options",
  "event_id": "evt_abc123xyz",
  "event_participant_id": "cdorsey@concord.org",  # Any participant's email
  "participant_ids": ["cdorsey@concord.org", "judi@example.com"],  # All participants
  "context_json": "{\"timeframe\": {\"from\": \"2025-12-08\", \"to\": \"2025-12-22\", \"tz\": \"America/New_York\"}}"
}
```

**Method 2: Natural Language** (user describes the meeting):
```python
{
  "utterance": "Find me a new time for the check-in with Judi on Dec. 10th",
  "participant_ids": ["cdorsey@concord.org", "judi@example.com"],
  "context_json": "{\"timeframe\": {\"from\": \"2025-12-08\", \"to\": \"2025-12-22\", \"tz\": \"America/New_York\"}}"
}
```

**Rescheduling response includes**:
- `proposals[].original_event_id`: ID of event being rescheduled
- `proposals[].original_event_details`: Original meeting details
- `agent_data.event_registry[original_event_id]`: Full event metadata for follow-up actions

**Natural language patterns**: "Find me a new time for...", "Reschedule the meeting with...", "Move my meeting with... on [date]"

**Constraints**: One meeting per request, internal events only, default 2-week search window (extendable via `context_json`)

## Key Points

- **Always provide timeframe**: `context_json` must include `timeframe` with `from`, `to`, `tz` when using `participant_ids`
- **Map names to emails**: If user says "Alex", map to email address
- **Handle UNSAT gracefully**: Present relaxations and negotiate with user
- **Use explanation field**: Help user understand why a time was chosen

## Common Errors

**"Missing timeframe in context_json"**: Add `{"timeframe": {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "tz": "America/New_York"}}`

**"Failed to fetch calendar events"**: Verify participant emails are correct and MCP server is accessible

**"No events provided or fetched"**: Check date range and participant calendar access

**"Event not found"** (rescheduling): Event may be outside 30-day search window or ID is incorrect

**"Cannot reschedule external event"**: Tool only reschedules internal events (all participants internal)
