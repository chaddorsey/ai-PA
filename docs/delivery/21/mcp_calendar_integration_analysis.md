# MCP Calendar Integration Analysis

## Overview

This document analyzes the trade-offs and implementation requirements for adding MCP calendar querying directly to the `orchestrate_scheduling` tool, allowing it to fetch calendar events itself rather than receiving them from the agent.

## Current Architecture

**Current Flow:**
1. Agent calls `Get_Events` / `Get_Events_On_Arbitrary_Calendar` via MCP
2. Agent receives full event data (potentially large payloads)
3. Agent filters/prepares events (may hit message size limits)
4. Agent calls `orchestrate_scheduling` with prepared events
5. Orchestrator processes scheduling

**Proposed Flow:**
1. Agent calls `orchestrate_scheduling` with participant IDs and timeframe
2. Orchestrator calls MCP calendar tools directly
3. Orchestrator filters/prepares events internally
4. Orchestrator processes scheduling

## MCP Server Details

- **MCP Server URL**: `http://n8n:5678/mcp/80b10600-d5be-4552-b00c-5c9790bded31`
- **Tools Available**:
  - `Get_Events`: For user's own calendar
  - `Get_Events_On_Arbitrary_Calendar`: For other users' calendars

## Trade-offs Analysis

### Advantages ✅

1. **Eliminates Message Size Limits**
   - Agent no longer needs to transmit large event payloads
   - Orchestrator can fetch only what it needs
   - No risk of JSON truncation in agent-to-orchestrator communication

2. **Better Data Filtering**
   - Orchestrator can filter events at source (by timeframe, participant)
   - Can use minimal event format from the start
   - More efficient than agent-side filtering

3. **Reduced Agent Complexity**
   - Agent doesn't need to understand event format requirements
   - Agent doesn't need to do pre-filtering
   - Simpler agent instructions

4. **Single Source of Truth**
   - Orchestrator controls what data it needs
   - Can optimize queries based on scheduling requirements
   - Less chance of data inconsistencies

5. **Better Error Handling**
   - Orchestrator can handle calendar API errors directly
   - Can provide specific error messages about missing calendar data
   - More granular error reporting

### Disadvantages ❌

1. **Added Dependencies**
   - Orchestrator needs MCP client library
   - Requires HTTP client (requests/httpx)
   - Adds network dependency to orchestrator

2. **Authentication Complexity**
   - Need to handle MCP authentication in orchestrator
   - May need to pass auth tokens/credentials
   - Different from current stateless design

3. **Network Latency**
   - Each scheduling request requires multiple calendar API calls
   - Adds latency to orchestrator execution
   - May need timeout handling for slow calendar APIs

4. **Reduced Flexibility**
   - Harder to use with non-MCP calendar sources
   - Tied to specific MCP server implementation
   - Less portable across different calendar systems

5. **Error Propagation**
   - Calendar API errors become orchestrator errors
   - Need to distinguish between calendar errors and scheduling errors
   - More complex error handling

6. **Testing Complexity**
   - Harder to test orchestrator in isolation
   - Need to mock MCP server responses
   - More integration points to test

## Implementation Requirements

### 1. MCP Client Integration

**Option A: Use MCP SDK (if available)**
```python
from mcp import Client

mcp_client = Client(base_url="http://n8n:5678/mcp/80b10600-d5be-4552-b00c-5c9790bded31")
result = mcp_client.call_tool("Get_Events", {...})
```

**Option B: Direct HTTP Requests**
```python
import httpx

async def call_mcp_tool(tool_name: str, params: dict):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://n8n:5678/mcp/80b10600-d5be-4552-b00c-5c9790bded31/tools/{tool_name}",
            json=params
        )
        return response.json()
```

### 2. Modified Function Signature

**Current:**
```python
def orchestrate_scheduling(
    utterance: str,
    events_by_participant: str,  # JSON string
    context_json: Optional[str] = None
) -> dict:
```

**Proposed:**
```python
def orchestrate_scheduling(
    utterance: str,
    participant_ids: List[str],  # List of participant IDs
    user_id: Optional[str] = None,  # User's own ID (for Get_Events)
    context_json: Optional[str] = None,
    fetch_calendars: bool = True,  # Whether to fetch calendars or use provided events
    events_by_participant: Optional[str] = None  # Optional: provide events directly
) -> dict:
```

### 3. Calendar Fetching Logic

```python
async def fetch_calendar_events(
    participant_ids: List[str],
    user_id: Optional[str],
    timeframe: Dict[str, str],
    mcp_base_url: str
) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch calendar events for all participants via MCP."""
    events_by_participant = {}
    
    for participant_id in participant_ids:
        if participant_id == user_id:
            # Use Get_Events for user's own calendar
            tool_name = "Get_Events"
            params = {
                "timeMin": timeframe["from"],
                "timeMax": timeframe["to"]
            }
        else:
            # Use Get_Events_On_Arbitrary_Calendar for others
            tool_name = "Get_Events_On_Arbitrary_Calendar"
            params = {
                "calendar_id": participant_id,  # or email
                "timeMin": timeframe["from"],
                "timeMax": timeframe["to"]
            }
        
        # Call MCP tool
        events = await call_mcp_tool(tool_name, params)
        
        # Filter to minimal format immediately
        events_by_participant[participant_id] = [
            {
                "id": evt.get("id"),
                "start": evt.get("start"),
                "end": evt.get("end"),
                "locked": evt.get("locked", False),
                "protected": evt.get("protected", False),
                "flexible": evt.get("flexible", True)
            }
            for evt in events
            if not is_all_day_event(evt)  # Filter all-day events
        ]
    
    return events_by_participant
```

### 4. Configuration

Add to orchestrator configuration:
- MCP server URL (environment variable)
- MCP authentication (if needed)
- Timeout settings for calendar API calls
- Retry logic for failed calendar calls

## Hybrid Approach (Recommended)

**Best of Both Worlds:**

Allow orchestrator to accept either:
1. **Participant IDs** (fetches calendars itself)
2. **Pre-fetched events** (current approach, for flexibility)

```python
def orchestrate_scheduling(
    utterance: str,
    # Option 1: Provide events directly (current approach)
    events_by_participant: Optional[str] = None,
    # Option 2: Provide participant IDs and let orchestrator fetch
    participant_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    context_json: Optional[str] = None
) -> dict:
    """
    Orchestrate scheduling with flexible input options.
    
    Either provide events_by_participant (current approach) OR
    provide participant_ids and let orchestrator fetch calendars.
    """
    # If events provided, use them (current behavior)
    if events_by_participant:
        events = json.loads(events_by_participant)
    # Otherwise, fetch from MCP
    elif participant_ids:
        if not context_json or "timeframe" not in context_json:
            return {"error": "timeframe required when fetching calendars"}
        events = await fetch_calendar_events(
            participant_ids, user_id, context_json["timeframe"]
        )
    else:
        return {"error": "Must provide either events_by_participant or participant_ids"}
    
    # Continue with normal processing...
```

## Implementation Steps

### Phase 1: Add MCP Client (Non-Breaking)
1. Add MCP client dependency to `letta/requirements.txt`
2. Add MCP client wrapper module
3. Add configuration for MCP server URL
4. Keep current `events_by_participant` parameter (backward compatible)

### Phase 2: Add Calendar Fetching (Optional Feature)
1. Add `participant_ids` parameter (optional)
2. Add `fetch_calendars` flag
3. Implement `fetch_calendar_events()` function
4. Add error handling for MCP failures

### Phase 3: Update Agent Instructions
1. Document both approaches
2. Recommend MCP approach for large datasets
3. Keep events approach for testing/custom sources

## Dependencies to Add

```txt
# letta/requirements.txt additions
httpx>=0.25.0  # For async HTTP requests to MCP server
# OR
mcp>=0.1.0  # If MCP SDK exists
```

## Configuration

```python
# Environment variables
MCP_CALENDAR_SERVER_URL=http://n8n:5678/mcp/80b10600-d5be-4552-b00c-5c9790bded31
MCP_CALENDAR_TIMEOUT=30  # seconds
MCP_CALENDAR_RETRY_ATTEMPTS=3
```

## Error Handling

Need to handle:
- MCP server unavailable
- Calendar API rate limits
- Invalid participant IDs
- Missing calendar permissions
- Network timeouts
- Partial calendar fetch failures

## Performance Considerations

- **Parallel fetching**: Fetch all calendars concurrently (async)
- **Caching**: Consider caching calendar data (with TTL)
- **Timeout**: Set reasonable timeouts (30s per calendar)
- **Retry logic**: Retry failed calendar fetches

## Security Considerations

- **Authentication**: How to pass auth tokens to MCP?
- **Authorization**: Ensure orchestrator has permission to access calendars
- **Network security**: MCP server should be on internal network
- **Data privacy**: Calendar data in orchestrator memory

## Recommendation

**Implement Hybrid Approach:**

1. ✅ Keep current `events_by_participant` parameter (backward compatible)
2. ✅ Add optional `participant_ids` parameter for MCP fetching
3. ✅ Let orchestrator choose based on what's provided
4. ✅ Agent can use either approach based on situation

**Benefits:**
- Solves message size limit problem
- Maintains flexibility for testing/custom sources
- Backward compatible
- Agent can choose best approach per situation

**When to use each:**
- **MCP approach**: Large datasets, multiple participants, long timeframes
- **Events approach**: Testing, custom calendar sources, small datasets

## Next Steps

1. **Research MCP Protocol**: Understand exact API format
2. **Prototype MCP Client**: Test calendar fetching in isolation
3. **Add to Orchestrator**: Implement hybrid approach
4. **Update Agent Instructions**: Document both approaches
5. **Test**: Verify with real calendar data

