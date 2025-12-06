# Rescheduling Usage Guide

## Overview

The scheduling orchestrator now supports rescheduling existing meetings. This guide covers how to use the rescheduling functionality for both agent-generated requests and natural language user requests.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Rescheduling Methods](#rescheduling-methods)
3. [Natural Language Patterns](#natural-language-patterns)
4. [Response Structure](#response-structure)
5. [Error Handling](#error-handling)
6. [Best Practices](#best-practices)
7. [Examples](#examples)

## Quick Start

### Rescheduling with Event ID

```python
result = orchestrate_scheduling(
    utterance="Find new time options",
    event_id="bahchtou3anfkj34qim5j7krc7_20251211T150000Z",
    event_participant_id="lbondaryk@concord.org",
    participant_ids=["lbondaryk@concord.org", "other@example.com"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-22", "tz": "America/New_York"}}'
)
```

### Rescheduling with Natural Language

```python
result = orchestrate_scheduling(
    utterance="Find me a new time for the check-in with Judi on Dec. 10th",
    participant_ids=["cdorsey@concord.org", "judi@example.com"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-22", "tz": "America/New_York"}}'
)
```

## Rescheduling Methods

### Method 1: Explicit Event ID

**When to use**: When you already have the event ID (from calendar queries, user selection, etc.)

**Parameters**:
- `event_id` (required): The specific event ID to reschedule
- `event_participant_id` (required): Email of any participant in the event
- `participant_ids` (required): List of all participants in the original meeting
- `utterance` (optional): Can be simple like "Find new time options" or include preferences
- `context_json` (required): Must include timeframe

**How it works**:
1. Tool fetches the event via MCP using `event_participant_id`
2. Extracts meeting details (participants, duration, title, location)
3. Searches for alternative time slots
4. Returns proposals with original event reference

**Example**:
```python
{
  "utterance": "Find new time options, preferably in the morning",
  "event_id": "evt_abc123xyz",
  "event_participant_id": "cdorsey@concord.org",
  "participant_ids": ["cdorsey@concord.org", "judi@example.com"],
  "context_json": "{\"timeframe\": {\"from\": \"2025-12-08\", \"to\": \"2025-12-22\", \"tz\": \"America/New_York\"}}"
}
```

### Method 2: Natural Language Identification

**When to use**: When the user describes the meeting to reschedule in natural language

**Parameters**:
- `utterance` (required): Natural language description of the meeting to reschedule
- `participant_ids` (required): List of likely participants (tool will match against their calendars)
- `context_json` (required): Must include timeframe

**How it works**:
1. Tool extracts event identifiers from utterance (names, dates, times, titles)
2. Fetches calendar events for participants (next 30 days from today)
3. Uses fuzzy matching to identify the best matching event
4. Extracts meeting details and searches for alternatives
5. Returns proposals with original event reference

**Example**:
```python
{
  "utterance": "Find options for moving Leslie and Scott's meeting on Dec. 11",
  "participant_ids": ["lbondaryk@concord.org", "scytacki@concord.org"],
  "context_json": "{\"timeframe\": {\"from\": \"2025-12-08\", \"to\": \"2025-12-22\", \"tz\": \"America/New_York\"}}"
}
```

## Natural Language Patterns

### Detected Phrases

The tool recognizes rescheduling intent from phrases like:
- "Find me a new time for..."
- "Reschedule the meeting with..."
- "Move my meeting with... on [date]"
- "Find alternative times for..."
- "When else could we meet for..."
- "Find some new time options for..."

### Extracted Identifiers

The tool extracts:
- **Participant names**: "Judi", "Leslie and Scott", "the team"
- **Dates**: "Dec. 10th", "December 11", "Monday", "tomorrow", "next week"
- **Times**: "2pm", "morning", "afternoon", "evening"
- **Titles**: "check-in", "standup", "review meeting"

### Matching Logic

The tool uses fuzzy matching to score events:
- **Participant match**: Checks if event participants match extracted names
- **Date match**: Checks if event date matches extracted date reference
- **Time match**: Checks if event time matches extracted time reference
- **Title match**: Fuzzy string matching on event titles

The event with the highest score is selected.

## Response Structure

### Proposal Fields for Rescheduling

When rescheduling, proposals include additional fields:

```json
{
  "proposal_id": "prop_abc123",
  "title": "Meeting",
  "participants": ["cdorsey@concord.org", "judi@example.com"],
  "start_utc": "2025-12-12T15:00:00+00:00",
  "end_utc": "2025-12-12T15:45:00+00:00",
  "original_event_id": "evt_abc123xyz",
  "original_event_details": {
    "title": "Check-in with Judi",
    "start_utc": "2025-12-10T15:00:00+00:00",
    "end_utc": "2025-12-10T15:45:00+00:00",
    "participants": ["cdorsey@concord.org", "judi@example.com"],
    "duration_minutes": 45,
    "location": null
  },
  "moved_events": [],
  "category": "zero_conflict"
}
```

### Agent Data Structure

The `agent_data.event_registry` includes the original event:

```json
{
  "agent_data": {
    "event_registry": {
      "evt_abc123xyz": {
        "title": "Check-in with Judi",
        "owner": "cdorsey@concord.org",
        "start_utc": "2025-12-10T15:00:00+00:00",
        "end_utc": "2025-12-10T15:45:00+00:00",
        "participants": ["cdorsey@concord.org", "judi@example.com"],
        "internal_only": true
      }
    }
  }
}
```

This enables the agent to:
- Access full event metadata
- Perform follow-up actions (modify, cancel) using the event ID
- Reference the original event in user communications

### User Display

The `user_display.refined_display` shows rescheduling context:

```
Rescheduling Options

Original Meeting: Check-in with Judi
Current Time: December 10, 2025 at 3:00 PM
Participants: cdorsey@concord.org, judi@example.com

Best Options:

Wednesday, December 12
  3:00 PM – 3:45 PM (Zero conflicts)
  4:00 PM – 4:45 PM (Zero conflicts)
```

## Error Handling

### Missing Event

**Error**: Event not found in the specified participant's calendar

**Causes**:
- Event ID is incorrect
- Event is outside the 30-day search window (today forward)
- Event participant ID doesn't match any participant in the event
- Event has been deleted

**Response**:
```json
{
  "status": "bad_input",
  "error_message": "Event not found: evt_abc123xyz"
}
```

### External Event

**Error**: Event is not internal-only (has external participants)

**Causes**:
- Event includes external participants
- Tool can only reschedule internal events

**Response**:
```json
{
  "status": "bad_input",
  "error_message": "Cannot reschedule external event: event includes external participants"
}
```

### Event Identification Failure

**Error**: Could not identify event from natural language

**Causes**:
- No matching event found in participant calendars
- Ambiguous description (multiple matches)
- Event outside search window

**Response**:
```json
{
  "status": "bad_input",
  "error_message": "Could not identify event from natural language description"
}
```

### Missing Event Participant ID

**Error**: `event_participant_id` not provided when `event_id` is provided

**Response**:
```json
{
  "status": "bad_input",
  "error_message": "event_participant_id is required when event_id is provided"
}
```

## Best Practices

### For Agent-Generated Requests

1. **Use explicit event ID when available**: More reliable than natural language matching
2. **Include all participants**: Ensure `participant_ids` includes all original meeting participants
3. **Set appropriate timeframe**: Default is 2 weeks, but can be extended via `context_json`
4. **Handle errors gracefully**: Check for missing events, external events, etc.

### For Natural Language Requests

1. **Include likely participants**: Add all participants who might be in the meeting to `participant_ids`
2. **Be specific in utterance**: Include participant names, dates, and times when possible
3. **Handle ambiguity**: If multiple events match, the tool selects the best match, but you may want to confirm with the user
4. **Verify event identification**: Check that `original_event_id` matches the user's intent

### General Guidelines

1. **One meeting per request**: The tool only supports rescheduling one meeting at a time
2. **Recurring events**: Only the specific instance is considered, not the entire series
3. **Search window**: Default is 2 weeks for new slots, but can be customized
4. **Original event handling**: The original event is included in the solver's consideration, so it can be moved if needed

## Examples

### Example 1: Simple Reschedule with Event ID

**Request**:
```python
result = orchestrate_scheduling(
    utterance="Find new time options",
    event_id="bahchtou3anfkj34qim5j7krc7_20251211T150000Z",
    event_participant_id="lbondaryk@concord.org",
    participant_ids=["lbondaryk@concord.org"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-22", "tz": "America/New_York"}}'
)
```

**Response**:
- Status: `"ok"`
- Proposals include `original_event_id` and `original_event_details`
- Original event appears in `agent_data.event_registry`

### Example 2: Natural Language Reschedule

**Request**:
```python
result = orchestrate_scheduling(
    utterance="Find options for moving Leslie and Scott's meeting on Dec. 11",
    participant_ids=["lbondaryk@concord.org", "scytacki@concord.org"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-22", "tz": "America/New_York"}}'
)
```

**Response**:
- Tool identifies event "Scott and Leslie check in" on Dec. 11
- Returns proposals with original event reference
- Original event details included in proposals

### Example 3: Reschedule with Preferences

**Request**:
```python
result = orchestrate_scheduling(
    utterance="Find me a new time for the check-in with Judi on Dec. 10th, preferably in the morning",
    participant_ids=["cdorsey@concord.org", "judi@example.com"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-22", "tz": "America/New_York"}}'
)
```

**Response**:
- Tool identifies the original meeting
- Returns proposals prioritizing morning times
- Original event details preserved

### Example 4: Reschedule with Original Event Movement

**Request**:
```python
result = orchestrate_scheduling(
    utterance="Find new time options",
    event_id="evt_abc123xyz",
    event_participant_id="cdorsey@concord.org",
    participant_ids=["cdorsey@concord.org", "judi@example.com"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-22", "tz": "America/New_York"}}'
)
```

**Response**:
- If best proposal requires moving the original event, it appears in `moved_events`
- Original event is marked as movable in the solver
- Proposals show both the new time and any required moves

## Summary

The rescheduling functionality enables:
- ✅ Rescheduling by explicit event ID (agent-generated)
- ✅ Rescheduling by natural language identification (user requests)
- ✅ Automatic extraction of meeting details
- ✅ Preservation of original meeting information
- ✅ Support for moving original events if needed
- ✅ Full event metadata in agent data for follow-up actions

For more details, see the [Agent Instructions](../21/agent_instructions.md) and [Technical Documentation](./rescheduling_examples.md).

