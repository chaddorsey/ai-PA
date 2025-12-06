# Rescheduling Examples

This document provides detailed examples of rescheduling functionality, including request formats, response structures, and edge cases.

## Table of Contents

1. [Basic Examples](#basic-examples)
2. [Natural Language Examples](#natural-language-examples)
3. [Error Cases](#error-cases)
4. [Edge Cases](#edge-cases)
5. [Response Examples](#response-examples)

## Basic Examples

### Example 1: Reschedule with Explicit Event ID

**Scenario**: Agent has identified an event to reschedule and has the event ID.

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

**What happens**:
1. Tool fetches event `bahchtou3anfkj34qim5j7krc7_20251211T150000Z` from `lbondaryk@concord.org`'s calendar
2. Extracts meeting details: title, participants, duration, location
3. Searches for alternative time slots in the next 2 weeks (default)
4. Returns proposals with original event reference

**Expected Response**:
```json
{
  "status": "ok",
  "proposals": [
    {
      "proposal_id": "prop_abc123",
      "title": "Scott and Leslie check in",
      "participants": ["lbondaryk@concord.org"],
      "start_utc": "2025-12-12T15:00:00+00:00",
      "end_utc": "2025-12-12T15:30:00+00:00",
      "original_event_id": "bahchtou3anfkj34qim5j7krc7_20251211T150000Z",
      "original_event_details": {
        "title": "Scott and Leslie check in",
        "start_utc": "2025-12-11T15:00:00+00:00",
        "end_utc": "2025-12-11T15:30:00+00:00",
        "participants": ["lbondaryk@concord.org"],
        "duration_minutes": 30
      },
      "category": "zero_conflict"
    }
  ],
  "agent_data": {
    "event_registry": {
      "bahchtou3anfkj34qim5j7krc7_20251211T150000Z": {
        "title": "Scott and Leslie check in",
        "owner": "lbondaryk@concord.org",
        "start_utc": "2025-12-11T15:00:00+00:00",
        "end_utc": "2025-12-11T15:30:00+00:00",
        "participants": ["lbondaryk@concord.org"],
        "internal_only": true
      }
    }
  }
}
```

### Example 2: Reschedule with Preferences

**Scenario**: User wants to reschedule with specific time preferences.

**Request**:
```python
result = orchestrate_scheduling(
    utterance="Find new time options, preferably in the morning",
    event_id="evt_abc123xyz",
    event_participant_id="cdorsey@concord.org",
    participant_ids=["cdorsey@concord.org", "judi@example.com"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-22", "tz": "America/New_York"}}'
)
```

**What happens**:
1. Tool fetches the event and extracts details
2. Extracts "morning" preference from utterance
3. Prioritizes morning time slots in proposals
4. Returns proposals sorted by preference match

## Natural Language Examples

### Example 3: Identify Meeting by Participant and Date

**Scenario**: User describes the meeting to reschedule.

**Request**:
```python
result = orchestrate_scheduling(
    utterance="Find me a new time for the check-in with Judi on Dec. 10th",
    participant_ids=["cdorsey@concord.org", "judi@example.com"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-22", "tz": "America/New_York"}}'
)
```

**What happens**:
1. Tool extracts identifiers:
   - Participant: "Judi" → `judi@example.com`
   - Date: "Dec. 10th" → `2025-12-10`
2. Fetches calendar events for participants (next 30 days from today)
3. Matches events based on:
   - Participant match (Judi in attendees)
   - Date match (Dec. 10)
   - Title match (fuzzy match on "check-in")
4. Selects best matching event
5. Extracts details and searches for alternatives

**Expected Response**:
```json
{
  "status": "ok",
  "proposals": [
    {
      "original_event_id": "evt_checkin_judi_dec10",
      "original_event_details": {
        "title": "Check-in with Judi",
        "start_utc": "2025-12-10T15:00:00+00:00",
        "end_utc": "2025-12-10T15:45:00+00:00",
        "participants": ["cdorsey@concord.org", "judi@example.com"],
        "duration_minutes": 45
      }
    }
  ]
}
```

### Example 4: Identify Meeting by Multiple Participants

**Scenario**: User mentions multiple participants.

**Request**:
```python
result = orchestrate_scheduling(
    utterance="Find options for moving Leslie and Scott's meeting on Dec. 11",
    participant_ids=["lbondaryk@concord.org", "scytacki@concord.org"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-22", "tz": "America/New_York"}}'
)
```

**What happens**:
1. Tool extracts:
   - Participants: "Leslie" and "Scott"
   - Date: "Dec. 11" → `2025-12-11`
2. Maps names to emails (if available in context)
3. Searches for events on Dec. 11 with both participants
4. Matches event "Scott and Leslie check in"

### Example 5: Identify Meeting by Time

**Scenario**: User mentions a specific time.

**Request**:
```python
result = orchestrate_scheduling(
    utterance="Reschedule my 2pm meeting with Alex tomorrow",
    participant_ids=["cdorsey@concord.org", "alex@example.com"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-22", "tz": "America/New_York"}}'
)
```

**What happens**:
1. Tool extracts:
   - Participant: "Alex"
   - Time: "2pm"
   - Date: "tomorrow" → calculated date
2. Searches for events matching all three criteria
3. Selects best match

## Error Cases

### Example 6: Missing Event

**Request**:
```python
result = orchestrate_scheduling(
    utterance="Find new time options",
    event_id="nonexistent_event_12345",
    event_participant_id="cdorsey@concord.org",
    participant_ids=["cdorsey@concord.org"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-22", "tz": "America/New_York"}}'
)
```

**Response**:
```json
{
  "status": "bad_input",
  "error_message": "Event not found: nonexistent_event_12345. Searched in cdorsey@concord.org's calendar from today to 30 days in the future."
}
```

### Example 7: External Event

**Request**:
```python
result = orchestrate_scheduling(
    utterance="Find new time options",
    event_id="evt_external_meeting",
    event_participant_id="cdorsey@concord.org",
    participant_ids=["cdorsey@concord.org", "external@example.com"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-22", "tz": "America/New_York"}}'
)
```

**Response**:
```json
{
  "status": "bad_input",
  "error_message": "Cannot reschedule external event: event includes external participants (external@example.com)"
}
```

### Example 8: Event Identification Failure

**Request**:
```python
result = orchestrate_scheduling(
    utterance="Find new time for my meeting with Bob",
    participant_ids=["cdorsey@concord.org"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-22", "tz": "America/New_York"}}'
)
```

**Response**:
```json
{
  "status": "bad_input",
  "error_message": "Could not identify event from natural language description. No matching events found in participant calendars."
}
```

### Example 9: Missing Event Participant ID

**Request**:
```python
result = orchestrate_scheduling(
    utterance="Find new time options",
    event_id="evt_abc123xyz",
    participant_ids=["cdorsey@concord.org"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-22", "tz": "America/New_York"}}'
)
```

**Response**:
```json
{
  "status": "bad_input",
  "error_message": "event_participant_id is required when event_id is provided"
}
```

## Edge Cases

### Example 10: Recurring Event Instance

**Scenario**: User wants to reschedule a specific instance of a recurring meeting.

**Request**:
```python
result = orchestrate_scheduling(
    utterance="Find a new time for the standup on Dec. 12th",
    participant_ids=["cdorsey@concord.org", "team@example.com"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-22", "tz": "America/New_York"}}'
)
```

**What happens**:
1. Tool identifies the recurring event series
2. Extracts the specific instance for Dec. 12
3. Only considers that instance for rescheduling
4. Other instances of the recurring meeting are not affected

**Note**: The tool only reschedules the specific instance mentioned, not the entire series.

### Example 11: Original Event Movement

**Scenario**: Best proposal requires moving the original event.

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
```json
{
  "status": "ok",
  "proposals": [
    {
      "proposal_id": "prop_xyz789",
      "start_utc": "2025-12-12T10:00:00+00:00",
      "end_utc": "2025-12-12T10:45:00+00:00",
      "original_event_id": "evt_abc123xyz",
      "moved_events": [
        {
          "owner": "cdorsey@concord.org",
          "event_id": "evt_abc123xyz",
          "old_start": "2025-12-10T15:00:00+00:00",
          "new_start": "2025-12-12T10:00:00+00:00"
        }
      ],
      "category": "move_required"
    }
  ]
}
```

**Note**: The original event is included in `moved_events` if the best proposal requires moving it.

### Example 12: Extended Timeframe

**Scenario**: User wants to search beyond the default 2 weeks.

**Request**:
```python
result = orchestrate_scheduling(
    utterance="Find new time options in the next month",
    event_id="evt_abc123xyz",
    event_participant_id="cdorsey@concord.org",
    participant_ids=["cdorsey@concord.org", "judi@example.com"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2026-01-08", "tz": "America/New_York"}}'
)
```

**What happens**:
1. Tool extracts "next month" from utterance
2. Uses extended timeframe from `context_json` (up to 1 month)
3. Searches for alternatives in the extended window
4. Returns proposals within the specified timeframe

## Response Examples

### Complete Response Structure

```json
{
  "status": "ok",
  "proposals": [
    {
      "proposal_id": "prop_abc123",
      "title": "Check-in with Judi",
      "participants": ["cdorsey@concord.org", "judi@example.com"],
      "start_utc": "2025-12-12T15:00:00+00:00",
      "end_utc": "2025-12-12T15:45:00+00:00",
      "location": null,
      "notes_for_invite": null,
      "moved_events": [],
      "objective_scores": {
        "moved_minutes": 0,
        "focus_block_bonus": 200,
        "preference_penalty": 0,
        "protected_events_moved": 0,
        "priority_score": 1000.0
      },
      "original_event_id": "evt_abc123xyz",
      "original_event_details": {
        "title": "Check-in with Judi",
        "start_utc": "2025-12-10T15:00:00+00:00",
        "end_utc": "2025-12-10T15:45:00+00:00",
        "participants": ["cdorsey@concord.org", "judi@example.com"],
        "duration_minutes": 45,
        "location": null
      },
      "category": "zero_conflict",
      "rank": 1
    }
  ],
  "explanation": "Found alternative time slots for rescheduling your meeting. The original meeting on December 10 at 3:00 PM can be moved to December 12 at 3:00 PM with zero conflicts.",
  "user_display": {
    "refined_display": "Rescheduling Options\n\nOriginal Meeting: Check-in with Judi\nCurrent Time: December 10, 2025 at 3:00 PM\nParticipants: cdorsey@concord.org, judi@example.com\n\nBest Options:\n\nWednesday, December 12\n  3:00 PM – 3:45 PM (Zero conflicts)"
  },
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

## Summary

These examples demonstrate:
- ✅ Rescheduling with explicit event IDs
- ✅ Rescheduling with natural language identification
- ✅ Error handling for missing/external events
- ✅ Edge cases (recurring events, event movement, extended timeframes)
- ✅ Complete response structure with original event references

For usage guidelines, see the [Rescheduling Usage Guide](./rescheduling_usage_guide.md).

