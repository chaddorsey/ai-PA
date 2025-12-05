# Core_Event_Data MCP Tool Testing Summary

## Overview

This document summarizes the testing attempts and findings for the `Core_Event_Data` tool provided by the n8n MCP server at `http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb`.

## Server Information

- **Server Name**: `MCP_Server_Trigger`
- **Version**: `0.1.0`
- **Protocol**: JSON-RPC 2.0 over HTTP
- **Transport**: HTTP Streamable (Server-Sent Events)
- **Endpoint**: `http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb`

## Testing Results

### Successful Operations

1. **Initialization**: Successfully initialized MCP session
   - Method: `initialize`
   - Protocol Version: `2024-11-05`
   - Response: Server info returned correctly

### Challenges Encountered

1. **Session Persistence**: The server requires initialization, but session state is not persisting between requests
   - Error: `"Bad Request: Server not initialized"` on subsequent requests
   - Attempted: Session ID header management, but session still not maintained

2. **Tool Discovery**: Unable to list available tools due to session persistence issue
   - Method: `tools/list`
   - Status: Fails with "Server not initialized" error

3. **Tool Invocation**: Unable to call `Core_Event_Data` tool due to session issue
   - Method: `tools/call`
   - Status: Cannot test without working session

## Required Headers

The server requires:
- `Content-Type: application/json`
- `Accept: application/json, text/event-stream` (both must be accepted)

## Response Format

The server returns responses in Server-Sent Events (SSE) format:
```
event: message
data: {"jsonrpc":"2.0","result":{...},"id":0}
```

## Next Steps

To complete the testing and understand `Core_Event_Data`:

1. **Resolve Session Management**
   - Determine how Letta maintains session with this n8n MCP server
   - Check if n8n MCP servers require a different session mechanism
   - Possibly: Each request needs to include initialization, or state is maintained differently

2. **Discover Tool Parameters**
   - Once session works, call `tools/list` to see `Core_Event_Data` schema
   - Understand what parameters it accepts (likely: `user_ids`, `from`, `to`, etc.)

3. **Test Tool Response**
   - Call `Core_Event_Data` with test parameters
   - Understand the response format and data structure
   - Verify it returns the stripped-down event data as expected

4. **Document Integration Requirements**
   - Update the modifications document with actual tool interface
   - Design the orchestrator integration based on real tool behavior

## Questions for Clarification

1. How does Letta currently maintain session state with this n8n MCP server?
2. Can you provide an example of how `Core_Event_Data` is currently being called?
3. What parameters does `Core_Event_Data` accept?
4. What is the exact response format/structure from `Core_Event_Data`?
5. Is there documentation or workflow definition for this n8n MCP server?

## Test Script

A test script has been created at:
- `letta/scheduling_orchestrator/test_core_event_data.py`

This script can be used once session management is resolved.

