# Event Data Requirements for Scheduling Orchestrator

## Summary

The `orchestrate_scheduling` tool has **minimal data requirements** from calendar events. Most event metadata (title, description, location, etc.) is **not used** during optimization and can be omitted to reduce payload size.

## Required Event Fields

The orchestrator only needs these 6 fields per event:

1. **`id`** (string, required): Unique identifier for the event
   - Used to track event protection levels
   - Can be any unique string (e.g., Google Calendar event ID)

2. **`start`** (string, required): Event start time in ISO 8601 format (UTC)
   - Format: `"2025-11-25T14:00:00Z"` or `"2025-11-25T14:00:00+00:00"`
   - Must be parseable by `datetime.fromisoformat()`

3. **`end`** (string, required): Event end time in ISO 8601 format (UTC)
   - Format: `"2025-11-25T14:15:00Z"` or `"2025-11-25T14:15:00+00:00"`
   - Must be parseable by `datetime.fromisoformat()`

4. **`locked`** (boolean, optional, default: `false`): If `true`, event cannot be moved (hard constraint)
   - Events with `locked=true` are treated as immovable
   - The new meeting cannot overlap with locked events

5. **`protected`** (boolean, optional, default: `false`): If `true`, event should not be moved if possible (soft constraint)
   - Protected events can be moved, but the optimizer will penalize moving them
   - Used in lexicographic optimization (priority level 1)

6. **`flexible`** (boolean, optional, default: `true`): If `true`, event can be moved to accommodate new meetings
   - Flexible events can be moved with lower penalty
   - Used in optimization cost calculation

## Unused Event Fields

The following fields are **NOT used** by the orchestrator and can be omitted to reduce payload size:

- ❌ **`title`** - Not used in optimization
- ❌ **`description`** - Not used in optimization
- ❌ **`location`** - Not used in optimization
- ❌ **`owner`** - Not used (participant ID comes from the dictionary key)
- ❌ Any other custom fields

## Minimal Event Format

The minimal event format is:

```json
{
  "id": "evt_abc123",
  "start": "2025-11-25T14:00:00Z",
  "end": "2025-11-25T14:15:00Z",
  "locked": false,
  "protected": false,
  "flexible": true
}
```

## Pre-filtering Recommendations

To reduce payload size and improve performance:

### 1. Filter by Time Horizon

Only include events that overlap with the planning horizon:
- If the scheduling request is for "next 2 weeks", only fetch events within that range
- Events outside the horizon are ignored anyway by the normalizer

### 2. Filter Out All-Day Events

All-day events (events that span 24+ hours) are typically not relevant for meeting scheduling:
- They don't block specific time slots
- They can be excluded to reduce payload size

### 3. Use Minimal Event Format

When preparing `events_by_participant`, only include the 6 required fields:
- Omit `title`, `description`, `location`, `owner`, and other metadata
- This can reduce payload size by 50-70% for typical events

### 4. Filter by Participant

Only fetch events for participants who are actually required for the meeting:
- If the request is for "Chad, Danielle, and Sue", only fetch their calendars
- Don't fetch events for participants not in the request

## Example: Optimized Event Payload

**Before (with all fields):**
```json
{
  "chad": [
    {
      "id": "evt_abc123",
      "title": "Team Standup Meeting",
      "description": "Daily team sync to discuss progress and blockers",
      "start": "2025-11-25T14:00:00Z",
      "end": "2025-11-25T14:15:00Z",
      "location": "Conference Room A",
      "locked": false,
      "protected": false,
      "flexible": true,
      "owner": "chad",
      "attendees": ["chad", "alex", "priya"]
    }
  ]
}
```

**After (minimal format):**
```json
{
  "chad": [
    {
      "id": "evt_abc123",
      "start": "2025-11-25T14:00:00Z",
      "end": "2025-11-25T14:15:00Z",
      "locked": false,
      "protected": false,
      "flexible": true
    }
  ]
}
```

**Size reduction: ~60-70%** (depending on title/description length)

## Implementation Options

### Option 1: Agent-Side Pre-filtering (Recommended)

Have the agent filter events before calling the orchestrator:

1. **Filter by time horizon**: Only include events within the planning window
2. **Use minimal format**: Strip unused fields (`title`, `description`, `location`, etc.)
3. **Filter all-day events**: Exclude events that span 24+ hours
4. **Filter by participant**: Only fetch events for required participants

**Pros:**
- No changes needed to orchestrator
- Agent has full control over data preparation
- Can be implemented immediately

**Cons:**
- Agent must do the filtering work
- Requires agent to understand the orchestrator's requirements

### Option 2: Direct Calendar Querying in Orchestrator

Add calendar querying capabilities directly to the orchestrator:

1. Add a new parameter: `participant_calendars` (list of calendar IDs/emails)
2. Orchestrator queries calendars directly using Google Calendar API
3. Orchestrator filters events internally before processing

**Pros:**
- Agent doesn't need to fetch events
- Orchestrator can optimize queries (only fetch what's needed)
- Reduces agent complexity

**Cons:**
- Requires Google Calendar API integration in orchestrator
- Adds dependencies and authentication complexity
- Less flexible (harder to use with non-Google calendars)

### Option 3: Hybrid Approach

1. Agent does initial filtering (time horizon, participants)
2. Orchestrator accepts minimal event format
3. Both sides optimize for payload size

**Pros:**
- Best of both worlds
- Agent can still use existing calendar tools
- Orchestrator remains lightweight

**Cons:**
- Requires coordination between agent and orchestrator

## Recommended Approach

**Start with Option 1 (Agent-Side Pre-filtering):**

1. Update agent instructions to:
   - Only include events within the planning horizon
   - Use minimal event format (6 fields only)
   - Filter out all-day events
   - Only fetch events for required participants

2. This should reduce payload size by **60-80%** for typical use cases

3. If payload size is still an issue, consider Option 2 (direct calendar querying)

## Payload Size Estimates

For a typical use case (3 participants, 10-20 work days, 3-10 events/day):

- **Full event format**: ~50-100 KB per participant = **150-300 KB total**
- **Minimal format**: ~15-30 KB per participant = **45-90 KB total**
- **With time filtering**: ~10-20 KB per participant = **30-60 KB total**

Most message size limits are 1-4 MB, so minimal format should work for most cases.

## Next Steps

1. Update agent instructions to use minimal event format
2. Add pre-filtering logic to agent's event preparation
3. Monitor payload sizes and adjust as needed
4. Consider Option 2 if payload size remains an issue

