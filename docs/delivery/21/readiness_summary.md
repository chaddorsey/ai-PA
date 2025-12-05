# Scheduling Orchestrator - Letta Integration Readiness

## Is it Ready for Use in Letta?

**Status: ⚠️ NOT YET READY**

The orchestrator currently requires the Letta agent to fetch events first. The MCP integration code has been **designed and documented** but **not yet implemented** in the orchestrator function.

### What's Done ✅
- ✅ MCP server tested and working
- ✅ `Core_Event_Data` tool interface confirmed
- ✅ Response structure documented
- ✅ Implementation plan created
- ✅ Code design completed

### What's Needed ⏳
- ⏳ MCP client module implementation
- ⏳ Function signature modification
- ⏳ Event fetching logic integration
- ⏳ Docstring update for Letta schema
- ⏳ Testing with Letta agent

## Minimum Information Required from Letta Agent

### Current Mode (Legacy - Still Works)
```python
{
    "utterance": "Find 45 minutes with Alex and Priya next week",
    "events_by_participant": '{"alex@example.com": [...events...], "priya@example.com": [...events...]}',
    "context_json": '{"timeframe": {...}}'  # Optional
}
```

**Agent must:**
- Call `Core_Event_Data` or `Get_Events` for each participant
- Format events correctly
- Pass as JSON string

### Future Mode (Recommended - After Implementation)
```python
{
    "utterance": "Find 45 minutes with Alex and Priya next week",
    "participant_ids": ["cdorsey@concord.org", "alex@example.com", "priya@example.com"],
    "context_json": '{"timeframe": {"from": "2025-12-08", "to": "2025-12-14", "tz": "America/New_York"}}'
}
```

**Agent only needs to:**
- Extract participant email addresses
- Provide date range (or infer from utterance)
- Call orchestrator - it handles event fetching!

## Schema Description Changes

### Current Problem

The docstring currently says:
- "Please call Get_Events for all participants"
- `events_by_participant` is described as required
- No mention of `participant_ids` option

This causes Letta to instruct the agent to fetch events first.

### Proposed Solution

Update the docstring to:

1. **Make `participant_ids` the recommended approach**
2. **Remove "call Get_Events" instructions**
3. **Make `events_by_participant` optional and marked as "legacy"**
4. **Clearly state the tool fetches events automatically**

**Key Changes:**
```python
"""
Orchestrate scheduling by finding optimal meeting times.

**RECOMMENDED: Provide participant_ids - the tool will fetch calendar events automatically.**
No need to call Get_Events or Core_Event_Data first.

Args:
    utterance: Natural language scheduling request
    
    participant_ids: (Recommended) List of participant email addresses.
                     The tool automatically fetches their calendar events.
                     Example: ["user@example.com", "alex@example.com"]
    
    context_json: (Required when using participant_ids) Must include timeframe:
                  {"timeframe": {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "tz": "America/New_York"}}
                  
    events_by_participant: (Legacy/optional) Pre-fetched events. 
                          Use participant_ids instead for automatic fetching.
"""
```

## Implementation Priority

To make this ready for Letta:

1. **High Priority:**
   - Create `mcp_client.py` module
   - Modify function signature (make `events_by_participant` optional, add `participant_ids`)
   - Implement event fetching logic
   - Update docstring

2. **Medium Priority:**
   - Add error handling for MCP failures
   - Add configuration (env vars)
   - Add dependencies (`httpx`)

3. **Low Priority:**
   - Testing with Letta agent
   - Performance optimization
   - Caching (if needed)

## Estimated Implementation Time

- MCP client module: ~2-3 hours
- Function modification: ~1-2 hours
- Event fetching integration: ~2-3 hours
- Docstring update: ~30 minutes
- Testing: ~1-2 hours

**Total: ~6-10 hours of implementation work**

## Recommendation

**Proceed with implementation** - All the design work is done, the MCP server is tested and working, and the integration will significantly improve reliability and simplify agent usage.

The code is ready to be implemented based on the detailed design in `mcp_event_retrieval_modifications.md`.

