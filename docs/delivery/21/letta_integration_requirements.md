# Letta Integration Requirements for Direct Event Retrieval

## Current Status

**Not Ready Yet** - The orchestrator currently requires `events_by_participant` as a required parameter, which forces the Letta agent to fetch events first.

## What Needs to Change

### 1. Function Signature Modification

**Current**:
```python
def orchestrate_scheduling(
    utterance: str,
    events_by_participant: str,  # Required
    context_json: Optional[str] = None
) -> dict:
```

**Proposed** (Hybrid Approach):
```python
def orchestrate_scheduling(
    utterance: str,
    participant_ids: Optional[List[str]] = None,  # NEW: List of participant email addresses
    user_id: Optional[str] = None,  # NEW: User's own email (for reference)
    context_json: Optional[str] = None,  # Required when using participant_ids
    events_by_participant: Optional[str] = None  # Made optional for backward compatibility
) -> dict:
```

### 2. Minimum Information Required from Letta Agent

When using direct event retrieval (recommended approach):

**Required:**
- `utterance`: Natural language scheduling request
- `participant_ids`: List of participant email addresses (e.g., `["cdorsey@concord.org", "alex@example.com"]`)
- `context_json`: Must include `timeframe` with `from`, `to`, and `tz` fields

**Optional:**
- `user_id`: User's own email address (for reference, but Core_Event_Data treats all calendars the same)
- `context_json` additional fields: `participants` (with work_hours), `policy`, etc.

**Example Minimal Call:**
```python
orchestrate_scheduling(
    utterance="Find 45 minutes with Alex and Priya next week",
    participant_ids=["cdorsey@concord.org", "alex@example.com", "priya@example.com"],
    context_json='{"timeframe": {"from": "2025-12-08", "to": "2025-12-14", "tz": "America/New_York"}}'
)
```

### 3. Schema Description for Letta

The docstring needs to be updated so Letta doesn't instruct the agent to fetch events:

**Current Docstring Issues:**
- Mentions "Please call Get_Events for all participants"
- Describes `events_by_participant` as required
- Doesn't mention the new `participant_ids` option

**Proposed Docstring Update:**
```python
"""
Orchestrate scheduling by finding optimal meeting times that satisfy constraints and preferences.

This tool can operate in two modes:

1. **Direct Event Retrieval (Recommended)**: Provide participant_ids and the tool will fetch
   calendar events automatically via MCP. This is more reliable and avoids message size limits.
   
2. **Pre-fetched Events (Legacy)**: Provide events_by_participant if you've already fetched
   events. Use this only for testing or custom calendar sources.

**Mode 1 - Direct Retrieval (Recommended):**
- Provide: utterance, participant_ids, context_json (with timeframe)
- The tool will automatically fetch calendar events for all participants
- No need to call Get_Events or Core_Event_Data first

**Mode 2 - Pre-fetched Events (Legacy):**
- Provide: utterance, events_by_participant, context_json
- Use only if you have already fetched events from another source

Args:
    utterance: Natural language scheduling request (e.g., "Find 45 minutes with Alex & Priya Tue–Thu mornings. Minimize disruption.")
    
    participant_ids: (Mode 1) List of participant email addresses. The tool will fetch their calendar events automatically.
                     Example: ["cdorsey@concord.org", "alex@example.com"]
                     
    user_id: (Mode 1, optional) User's own email address. For reference only - Core_Event_Data treats all calendars the same.
    
    context_json: (Mode 1 required, Mode 2 optional) JSON string containing:
                  - timeframe: {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "tz": "America/New_York"} (REQUIRED for Mode 1)
                  - participants: [{"id": "exec", "email": "me@acme.com", "work_hours": "M-F 09:00-17:30"}, ...]
                  - policy: {...}
                  
    events_by_participant: (Mode 2) JSON string mapping participant IDs to lists of calendar events.
                          Only use this if you've already fetched events. Otherwise, use participant_ids.
                          Example: '{"exec": [{"id": "evt1", "title": "Meeting", "start": "2025-11-25T10:00:00Z", "end": "2025-11-25T11:00:00Z", "locked": false}], "alex": []}'

Returns:
    Dictionary with status, proposals, explanation, and detailed scheduling results.
"""
```

### 4. Implementation Requirements

To make this ready, we need to:

1. ✅ **MCP Client Module**: Already designed in `mcp_event_retrieval_modifications.md`
2. ⏳ **Modify Function Signature**: Update to hybrid approach
3. ⏳ **Implement Event Fetching**: Add `fetch_calendar_events` function
4. ⏳ **Update Docstring**: Change schema description seen by Letta
5. ⏳ **Add Dependencies**: Add `httpx>=0.25.0` to requirements.txt
6. ⏳ **Environment Variables**: Add MCP server URL configuration

## Benefits for Letta Agent

1. **Simpler Agent Instructions**: Agent just needs to provide participant IDs
2. **No Message Size Limits**: Events fetched directly, not passed through agent
3. **More Reliable**: Eliminates agent error in fetching/preparing events
4. **Better Error Handling**: Orchestrator can handle calendar API errors directly

## Backward Compatibility

The hybrid approach maintains backward compatibility:
- Existing code using `events_by_participant` continues to work
- New code can use `participant_ids` for automatic fetching
- Agent can choose the best approach per situation

## Next Steps

1. Implement the MCP client module (`mcp_client.py`)
2. Modify `orchestrate_scheduling` function signature
3. Add event fetching logic
4. Update docstring
5. Test with Letta agent
6. Update agent instructions/documentation

