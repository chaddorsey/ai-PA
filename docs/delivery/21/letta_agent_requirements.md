# Letta Agent Requirements for Scheduling Orchestrator

## Current Status: ⚠️ Not Ready - Requires Implementation

The orchestrator is **not yet ready** for use with direct event retrieval. It currently requires the agent to fetch events first.

## What the Letta Agent Currently Needs to Provide

**Current (Legacy) Mode:**
1. `utterance`: Natural language scheduling request
2. `events_by_participant`: JSON string with pre-fetched calendar events
3. `context_json`: Optional context (but must include timeframe if using new mode)

**The agent must:**
- Call `Get_Events` or `Core_Event_Data` for each participant
- Format the events correctly
- Pass them as a JSON string
- Risk hitting message size limits
- Handle errors in event fetching/formatting

## What the Letta Agent Should Need (After Implementation)

**New (Recommended) Mode:**
1. `utterance`: Natural language scheduling request
2. `participant_ids`: List of participant email addresses
3. `context_json`: Must include `timeframe` with `from`, `to`, and `tz`

**The agent only needs to:**
- Extract participant email addresses from the request
- Provide a date range (or let the tool infer from utterance)
- Call the orchestrator - it handles the rest!

## Minimum Information Required

### Required Parameters:
```python
{
    "utterance": "Find 45 minutes with Alex and Priya next week",
    "participant_ids": ["cdorsey@concord.org", "alex@example.com", "priya@example.com"],
    "context_json": "{\"timeframe\": {\"from\": \"2025-12-08\", \"to\": \"2025-12-14\", \"tz\": \"America/New_York\"}}"
}
```

### Optional but Recommended:
- `user_id`: User's own email (for reference)
- `context_json.participants`: Work hours and preferences
- `context_json.policy`: Scheduling policies

## Schema Description Changes Needed

### Current Docstring Issues:
- ❌ Says "Please call Get_Events for all participants"
- ❌ Describes `events_by_participant` as required
- ❌ Doesn't mention `participant_ids` option
- ❌ Instructs agent to fetch events first

### Proposed Docstring (for Letta Schema):
```python
"""
Orchestrate scheduling by finding optimal meeting times.

**RECOMMENDED MODE - Direct Event Retrieval:**
Provide participant_ids and the tool will automatically fetch calendar events.
No need to call Get_Events or Core_Event_Data first.

**LEGACY MODE - Pre-fetched Events:**
Only use events_by_participant if you've already fetched events from another source.

Args:
    utterance: Natural language scheduling request
    
    participant_ids: (Recommended) List of participant email addresses.
                     The tool will fetch their calendars automatically.
                     Example: ["user@example.com", "alex@example.com"]
    
    context_json: (Required when using participant_ids) Must include timeframe:
                  {"timeframe": {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "tz": "America/New_York"}}
                  
    events_by_participant: (Legacy only) Pre-fetched events. Use participant_ids instead.
    
    user_id: (Optional) User's own email for reference.

Returns:
    Scheduling proposals with optimal meeting times.
"""
```

## Implementation Checklist

To make this ready for Letta:

- [ ] **1. Create MCP Client Module** (`mcp_client.py`)
  - [ ] Implement `MCPCalendarClient` class
  - [ ] Add `initialize()` method
  - [ ] Add `get_core_event_data()` method
  - [ ] Handle SSE response parsing
  - [ ] Add error handling

- [ ] **2. Modify Function Signature**
  - [ ] Make `events_by_participant` optional
  - [ ] Add `participant_ids` parameter
  - [ ] Add `user_id` parameter
  - [ ] Add logic to choose between modes

- [ ] **3. Implement Event Fetching**
  - [ ] Add `fetch_calendar_events()` function
  - [ ] Handle parallel fetching with `asyncio.gather()`
  - [ ] Normalize Core_Event_Data format to orchestrator format
  - [ ] Handle errors gracefully

- [ ] **4. Update Docstring**
  - [ ] Remove "call Get_Events" instructions
  - [ ] Document `participant_ids` as recommended approach
  - [ ] Make it clear agent doesn't need to fetch events

- [ ] **5. Add Dependencies**
  - [ ] Add `httpx>=0.25.0` to `requirements.txt`

- [ ] **6. Configuration**
  - [ ] Add `MCP_CALENDAR_SERVER_URL` environment variable
  - [ ] Add timeout and retry configuration

- [ ] **7. Testing**
  - [ ] Test with real calendar data
  - [ ] Test error handling
  - [ ] Test with Letta agent
  - [ ] Verify schema generation

## Benefits for Letta Agent

Once implemented:

1. **Simpler**: Agent just provides participant IDs
2. **More Reliable**: No agent errors in event fetching
3. **No Size Limits**: Events fetched directly
4. **Better Errors**: Orchestrator handles calendar API errors
5. **Faster**: Parallel fetching of all calendars

## Backward Compatibility

The implementation will maintain backward compatibility:
- Existing code using `events_by_participant` continues to work
- New code can use `participant_ids` for automatic fetching
- Agent can choose the best approach per situation

## Example Agent Usage (After Implementation)

**Before (Current - Complex):**
```
1. Agent extracts participants: ["alex@example.com", "priya@example.com"]
2. Agent calls Core_Event_Data for each participant
3. Agent formats events into JSON string
4. Agent calls orchestrate_scheduling with events
```

**After (Future - Simple):**
```
1. Agent extracts participants: ["alex@example.com", "priya@example.com"]
2. Agent calls orchestrate_scheduling with participant_ids
   (Tool fetches events automatically)
```

## Next Steps

1. Review the implementation plan in `mcp_event_retrieval_modifications.md`
2. Implement the MCP client module
3. Modify the orchestrator function
4. Update the docstring
5. Test with Letta agent
6. Update agent instructions

