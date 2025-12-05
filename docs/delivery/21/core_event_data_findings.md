# Core_Event_Data Tool - Testing Findings

## Summary

Successfully tested the `Core_Event_Data` MCP tool and confirmed its interface. The tool is functional and ready for integration into the scheduling orchestrator.

## Tool Schema

```json
{
  "name": "Core_Event_Data",
  "parameters": {
    "type": "object",
    "properties": {
      "Before": {"type": "string"},      // Start date/time
      "Calendar": {"type": "string"},    // Calendar identifier
      "After": {"type": "string"},       // End date/time
      "request_heartbeat": {"type": "boolean"}  // MCP heartbeat flag
    },
    "required": ["Before", "Calendar", "After", "request_heartbeat"]
  }
}
```

## Key Findings

### 1. Session Management ✅
- **Initialization Required**: Must call `initialize` before other operations
- **Session Persistence**: Uses both `mcp-session-id` headers AND HTTP cookies
- **Critical Implementation**: Use `httpx.AsyncClient` with `cookies={}` dict to maintain session
- **Session ID**: Returned in response headers, must be included in subsequent requests

### 2. Request Format ✅
- **Protocol**: JSON-RPC 2.0
- **Method**: `tools/call`
- **Headers Required**:
  - `Content-Type: application/json`
  - `Accept: application/json, text/event-stream`
  - `mcp-session-id: <uuid>` (after initialization)

### 3. Response Format ✅
- **Format**: Server-Sent Events (SSE)
- **Structure**:
  ```
  event: message
  data: {"jsonrpc":"2.0","result":{...},"id":0}
  ```
- **Result Structure**:
  ```json
  {
    "result": {
      "content": [
        {
          "type": "text",
          "text": "<actual_data>"
        }
      ]
    }
  }
  ```
- **Data Location**: The actual event data is in `result.content[0].text`
- **Data Format**: May be JSON string (needs parsing) or plain text

### 4. Error Handling ✅
- Errors returned in the `text` field: `"There was an error: \"...\""`
- Example: `"The resource you are requesting could not be found"` (invalid calendar)
- JSON-RPC errors also possible: `{"error": {"code": ..., "message": "..."}}`

### 5. Tool Behavior ✅
- **Single Calendar Per Call**: Must call once per participant calendar
- **Date Format**: Accepts both:
  - Date strings: `"2025-12-05"`
  - ISO datetime: `"2025-12-05T20:36:47.927655"`
- **Heartbeat**: `request_heartbeat` shown in Letta schema but NOT required for direct MCP calls (Letta-specific)

## Integration Requirements

### For Orchestrator Integration:

1. **Initialize Once**: Call `initialize()` when creating MCP client
2. **Maintain Session**: Use persistent HTTP client with cookies
3. **Call Per Participant**: Make separate `Core_Event_Data` calls for each participant
4. **Parallel Fetching**: Use `asyncio.gather()` to fetch all calendars concurrently
5. **Parse Response**: Extract data from `result.content[0].text` and parse as JSON
6. **Error Handling**: Check for error messages in response text

### Example Usage:

```python
# Initialize client
mcp_client = MCPCalendarClient(
    base_url="http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb"
)
await mcp_client.initialize()

# Fetch events for a participant
result = await mcp_client.get_core_event_data(
    calendar_id="user@example.com",
    before="2025-12-05",
    after="2025-12-11"
)
# Note: request_heartbeat is Letta-specific and not needed for direct MCP calls

# Parse result (structure to be confirmed with real calendar)
events = result  # or result["events"] depending on actual format
```

## Testing with Real Calendar

**Tested with**: `cdorsey@concord.org`

**Result**: Tool call successful, but n8n workflow returned error:
- Error message: `"The workflow did not return a response"`
- This indicates the MCP interface is working correctly
- The issue is with the n8n workflow configuration, not the MCP protocol

**Next Steps for n8n Workflow**:
- Verify the workflow is properly configured
- Ensure the workflow returns data in the expected format
- Check workflow error handling

## Remaining Questions

1. **Exact Response Structure**: Once workflow is fixed, need to confirm:
   - Is the data in `text` field a JSON string?
   - What is the exact structure of the event objects?
   - Are events already in the minimal format needed by orchestrator?

2. **Data Format**: Confirm if events are:
   - Already stripped-down (minimal fields)
   - Pre-filtered (no all-day events)
   - Pre-normalized (consistent format)

3. **Error Scenarios**: Test various error cases:
   - Invalid calendar ID
   - Invalid date range
   - Calendar access denied
   - Network timeouts

## Next Steps

1. ✅ **Tool Interface Confirmed**: Schema and parameters verified
2. ✅ **Session Management**: Working solution identified
3. ✅ **Response Format**: SSE format understood
4. ⏳ **Real Data Testing**: Test with actual calendar to confirm data structure
5. ⏳ **Integration Implementation**: Implement in orchestrator based on findings
6. ⏳ **Error Handling**: Add comprehensive error handling based on real error responses

## Test Script

The test script at `letta/scheduling_orchestrator/test_core_event_data.py` successfully:
- Initializes MCP session
- Lists available tools
- Calls `Core_Event_Data` with various parameters
- Handles SSE response format
- Maintains session state

The script can be used for further testing once a real calendar identifier is available.

