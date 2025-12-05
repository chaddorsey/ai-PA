# Modifications Required for Direct Event Retrieval in Scheduling Orchestrator

## Overview

This document describes the modifications needed to extend the `orchestrate_scheduling` tool to retrieve event data directly from the n8n MCP server, rather than relying on Letta agents to provide it. This will eliminate the unreliable step of agent-provided event data and improve the reliability of the scheduling workflow.

## Current Architecture

### Current Flow
1. Letta agent receives scheduling request with participant IDs and date range
2. Agent calls `Get_Events` / `Get_Events_On_Arbitrary_Calendar` via MCP server at `http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb`
3. Agent receives full event data (potentially large payloads)
4. Agent filters/prepares events (may hit message size limits or make errors)
5. Agent calls `orchestrate_scheduling` with prepared events as JSON string
6. Orchestrator processes scheduling

### Current Function Signature
```python
def orchestrate_scheduling(
    utterance: str,
    events_by_participant: str,  # JSON string: Dict[str, List[Dict[str, Any]]]
    context_json: Optional[str] = None
) -> dict:
```

## n8n MCP Server Analysis

### Endpoint Details
- **Base URL**: `http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb`
- **Protocol**: JSON-RPC 2.0 over HTTP POST
- **Transport**: HTTP Streamable (standard MCP protocol)
- **Server Name**: `MCP_Server_Trigger` (version 0.1.0)
- **Response Format**: Server-Sent Events (SSE) with `event: message` and `data: {...}` format

### Available Tools

**Primary Tool: `Core_Event_Data`**

This is the main tool provided by this MCP server. It provides a stripped-down version of event data that should be more efficient than full calendar event retrieval.

**Tool Schema:**
```json
{
  "name": "Core_Event_Data",
  "description": "",
  "parameters": {
    "type": "object",
    "properties": {
      "Before": {
        "type": "string",
        "description": "Start date/time for the event range"
      },
      "Calendar": {
        "type": "string",
        "description": "Calendar identifier (user ID or email address)"
      },
      "After": {
        "type": "string",
        "description": "End date/time for the event range"
      },
      "request_heartbeat": {
        "type": "boolean",
        "description": "Request an immediate heartbeat after function execution. Set to True if chaining multiple tools."
      }
    },
    "required": ["Before", "Calendar", "After"]
    // Note: request_heartbeat is shown in Letta schema but is NOT required for direct MCP calls
    // It's a Letta-specific parameter and should be omitted when calling directly
    },
    "required": ["Before", "Calendar", "After", "request_heartbeat"]
  }
}
```

**Key Observations:**
- **Single Calendar Per Call**: The tool accepts one calendar at a time (not multiple user_ids)
- **Date Format**: Accepts both date strings (YYYY-MM-DD) and ISO datetime strings (YYYY-MM-DDTHH:MM:SSZ)
- **⚠️ IMPORTANT - Parameter Names are Reversed**:
  - `Before`: This is the **END** date/time (counterintuitive naming!)
  - `After`: This is the **START** date/time (counterintuitive naming!)
- **request_heartbeat**: NOT needed for direct MCP calls (Letta-specific parameter)

### Testing Results

1. **Initialization**: Successfully initialized MCP session
   - Method: `initialize`
   - Protocol Version: `2024-11-05`
   - Returns server info: `{"name": "MCP_Server_Trigger", "version": "0.1.0"}`

2. **Session Management**: 
   - Server uses `mcp-session-id` headers AND HTTP cookies for session management
   - Session ID is returned in response headers: `mcp-session-id: <uuid>`
   - HTTP client must maintain cookies to preserve session state
   - **Critical**: Use `httpx.AsyncClient` with `cookies={}` to maintain session

3. **Response Format**: 
   - Responses use Server-Sent Events (SSE) format:
     ```
     event: message
     data: {"jsonrpc":"2.0","result":{...},"id":0}
     ```
   - Result structure: `{"content": [{"type": "text", "text": "<data>"}]}`
   - The `text` field contains the actual data (may be JSON string or plain text)

4. **Error Handling**: 
   - Server returns errors in the `text` field: `"There was an error: \"...\""`
   - Example: `"The resource you are requesting could not be found"` (for invalid calendar)

5. **Tool Discovery**: Successfully listed tools
   - Method: `tools/list`
   - Returns: `{"result": {"tools": [{"name": "Core_Event_Data", ...}]}}`

### Response Format

The tool returns data in the MCP standard format:
```json
{
  "jsonrpc": "2.0",
  "id": <request_id>,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "<actual_data_here>"
      }
    ]
  }
}
```

The `text` field contains the actual event data as a JSON string. The structure is:

**Response Format:**
```json
[
  {
    "summary": "Event title",
    "id": "event_id",
    "start": {
      "dateTime": "2025-12-09T11:00:00-05:00"
    },
    "end": {
      "dateTime": "2025-12-09T15:00:00-05:00"
    },
    "locked": false,
    "protected": false,
    "flexible": true,
    "number_of_attendees": 0,
    "internal_only": true
  },
  ...
]
```

**Key Fields:**
- `summary`: Event title/name
- `id`: Unique event identifier
- `start.dateTime`: ISO 8601 datetime string with timezone offset
- `end.dateTime`: ISO 8601 datetime string with timezone offset
- `locked`: Whether event is locked (cannot be moved)
- `protected`: Whether event is protected (should not be moved if possible)
- `flexible`: Whether event can be moved
- `number_of_attendees`: Number of attendees
- `internal_only`: Whether event is internal-only

**Note**: The data is already in a good format, but needs normalization to match orchestrator's expected format:
- Extract `start.dateTime` → `start`
- Extract `end.dateTime` → `end`
- Map `summary` → `title`

### MCP Protocol Format

The n8n MCP server follows the standard MCP JSON-RPC 2.0 protocol:

**Request Format:**
```json
{
  "jsonrpc": "2.0",
  "id": <unique_request_id>,
  "method": "tools/call",
  "params": {
    "name": "<tool_name>",
    "arguments": {
      "<param1>": "<value1>",
      "<param2>": "<value2>"
    }
  }
}
```

**Response Format:**
```json
{
  "jsonrpc": "2.0",
  "id": <request_id>,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "<result_data>"
      }
    ]
  }
}
```

**Error Response:**
```json
{
  "jsonrpc": "2.0",
  "id": <request_id>,
  "error": {
    "code": <error_code>,
    "message": "<error_message>"
  }
}
```

**HTTP Headers:**
- `Content-Type: application/json`
- `mcp-session-id`: Optional session identifier (server generates if not provided)

## Required Modifications

### 1. Add HTTP Client Dependency

**File**: `letta/requirements.txt`

Add:
```txt
httpx>=0.25.0  # For async HTTP requests to MCP server
```

### 2. Create MCP Client Module

**New File**: `letta/scheduling_orchestrator/mcp_client.py`

This module will handle:
- JSON-RPC 2.0 protocol communication
- Session management (mcp-session-id header)
- Error handling and retries
- Tool invocation

**Implementation Outline:**
```python
"""
MCP Client for retrieving calendar events from n8n MCP server.
"""

import json
import uuid
from typing import Dict, List, Any, Optional
import httpx
import logging

logger = logging.getLogger(__name__)

class MCPCalendarClient:
    """Client for interacting with n8n MCP calendar server."""
    
    def __init__(
        self,
        base_url: str,
        timeout: int = 30,
        max_retries: int = 3
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.session_id: Optional[str] = None
        self._initialized = False
        self._cookies = {}  # Maintain cookies for session persistence
    
    async def initialize(self) -> None:
        """
        Initialize the MCP session.
        Must be called before other operations.
        """
        if self._initialized:
            return
        
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "scheduling-orchestrator",
                    "version": "1.0.0"
                }
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        
        async with httpx.AsyncClient(timeout=self.timeout, cookies=self._cookies) as client:
            response = await client.post(
                f"{self.base_url}/mcp",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            # Extract session ID from headers
            session_id = response.headers.get("mcp-session-id")
            if session_id:
                self.session_id = session_id
                headers["mcp-session-id"] = session_id
            
            # Parse SSE response if needed
            if "text/event-stream" in response.headers.get("content-type", ""):
                lines = response.text.split('\n')
                for line in lines:
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if "error" in data:
                            error = data["error"]
                            raise MCPError(
                                code=error.get("code", -32603),
                                message=error.get("message", "Unknown error")
                            )
                        break
            else:
                result = response.json()
                if "error" in result:
                    error = result["error"]
                    raise MCPError(
                        code=error.get("code", -32603),
                        message=error.get("message", "Unknown error")
                    )
        
        self._initialized = True
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call an MCP tool via JSON-RPC 2.0.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            Tool result as dictionary
        """
        # Ensure initialized
        if not self._initialized:
            await self.initialize()
        
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        
        async with httpx.AsyncClient(timeout=self.timeout, cookies=self._cookies) as client:
            for attempt in range(self.max_retries):
                try:
                    response = await client.post(
                        f"{self.base_url}/mcp",
                        json=payload,
                        headers=headers
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                    
                    # Extract session ID from response headers
                    if "mcp-session-id" in response.headers:
                        self.session_id = response.headers["mcp-session-id"]
                    
                    # Check for JSON-RPC error
                    if "error" in result:
                        error = result["error"]
                        raise MCPError(
                            code=error.get("code", -32603),
                            message=error.get("message", "Unknown error")
                        )
                    
                    # Handle SSE response format
                    if "text/event-stream" in response.headers.get("content-type", ""):
                        # Parse SSE format
                        lines = response.text.split('\n')
                        for line in lines:
                            if line.startswith('data: '):
                                data = json.loads(line[6:])
                                if "error" in data:
                                    error = data["error"]
                                    raise MCPError(
                                        code=error.get("code", -32603),
                                        message=error.get("message", "Unknown error")
                                    )
                                if "result" in data:
                                    return data["result"]
                                return data
                        raise MCPError(code=-32603, message="No data in SSE response")
                    else:
                        # Standard JSON response
                        result = response.json()
                        
                        # Check for JSON-RPC error
                        if "error" in result:
                            error = result["error"]
                            raise MCPError(
                                code=error.get("code", -32603),
                                message=error.get("message", "Unknown error")
                            )
                        
                        # Extract result content
                        if "result" in result:
                            result_data = result["result"]
                            # MCP tools typically return content array
                            if "content" in result_data:
                                content = result_data["content"]
                                if content and len(content) > 0:
                                    # Parse the text content (may be JSON)
                                    text_content = content[0].get("text", "")
                                    try:
                                        return json.loads(text_content)
                                    except json.JSONDecodeError:
                                        return {"raw": text_content}
                            return result_data
                        
                        return result
                    
                except httpx.TimeoutException:
                    if attempt == self.max_retries - 1:
                        raise MCPError(
                            code=-32603,
                            message=f"Timeout after {self.max_retries} attempts"
                        )
                    logger.warning(f"MCP call timeout, retrying ({attempt + 1}/{self.max_retries})")
                    
                except httpx.HTTPStatusError as e:
                    raise MCPError(
                        code=-32603,
                        message=f"HTTP error: {e.response.status_code} - {e.response.text}"
                    )
    
    async def get_core_event_data(
        self,
        calendar_id: str,
        before: str,
        after: str
    ) -> List[Dict[str, Any]]:
        """
        Get core event data for a specific calendar.
        
        This is the primary method for retrieving stripped-down event data
        optimized for scheduling.
        
        Args:
            calendar_id: Calendar identifier (user ID or email address)
            before: END date/time (YYYY-MM-DD or ISO datetime string)
                   ⚠️ Note: Parameter name is counterintuitive - "Before" is the END date
            after: START date/time (YYYY-MM-DD or ISO datetime string)
                  ⚠️ Note: Parameter name is counterintuitive - "After" is the START date
            
        Returns:
            List of event dictionaries with structure:
            [
              {
                "summary": "Event title",
                "id": "event_id",
                "start": {"dateTime": "2025-12-09T11:00:00-05:00"},
                "end": {"dateTime": "2025-12-09T15:00:00-05:00"},
                "locked": false,
                "protected": false,
                "flexible": true,
                "number_of_attendees": 0,
                "internal_only": true,
                "attendees_list": [
                  "attendee1@example.com",
                  "attendee2@example.com"
                ]
              },
              ...
            ]
            
        Note: request_heartbeat is a Letta-specific parameter and is NOT included
        in direct MCP tool calls.
        """
        arguments = {
            "Calendar": calendar_id,
            "Before": before,  # END date
            "After": after     # START date
        }
        
        result = await self.call_tool("Core_Event_Data", arguments)
        
        # The result comes in MCP content format
        # Extract the text content which contains the actual data (JSON array string)
        if isinstance(result, dict) and "content" in result:
            content = result["content"]
            if content and len(content) > 0:
                text_content = content[0].get("text", "")
                # Parse the JSON string to get the event array
                try:
                    events = json.loads(text_content)
                    if isinstance(events, list):
                        return events
                    else:
                        return [events] if events else []
                except json.JSONDecodeError:
                    # If not JSON, check for error messages
                    if "error" in text_content.lower():
                        raise MCPError(
                            code=-32603,
                            message=f"Calendar API error: {text_content}"
                        )
                    raise MCPError(
                        code=-32603,
                        message=f"Unexpected response format: {text_content[:200]}"
                    )
        
        # If result is already a list (shouldn't happen, but handle it)
        if isinstance(result, list):
            return result
        
        return []


class MCPError(Exception):
    """Exception raised for MCP-related errors."""
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"MCP Error {code}: {message}")
```

### 3. Modify Orchestrator Function Signature

**File**: `letta/scheduling_orchestrator/orchestrate_scheduling.py`

**Current Signature:**
```python
def orchestrate_scheduling(
    utterance: str,
    events_by_participant: str,  # JSON string
    context_json: Optional[str] = None
) -> dict:
```

**Proposed Hybrid Signature:**
```python
def orchestrate_scheduling(
    utterance: str,
    # Option 1: Provide events directly (current approach, backward compatible)
    events_by_participant: Optional[str] = None,
    # Option 2: Provide participant IDs and let orchestrator fetch
    participant_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None,  # User's own ID (for Get_Events)
    context_json: Optional[str] = None,
    # MCP configuration (optional, uses env vars if not provided)
    mcp_server_url: Optional[str] = None
) -> dict:
```

### 4. Add Event Fetching Logic

**File**: `letta/scheduling_orchestrator/orchestrate_scheduling.py`

Add a new function to fetch events:

```python
async def fetch_calendar_events(
    participant_ids: List[str],
    user_id: Optional[str],
    timeframe: Dict[str, str],
    mcp_client: MCPCalendarClient
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch calendar events for all participants via MCP Core_Event_Data tool.
    
    Args:
        participant_ids: List of participant IDs (calendar identifiers)
        user_id: User's own ID (for reference, but Core_Event_Data treats all the same)
        timeframe: {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "tz": "America/New_York"}
        mcp_client: MCP client instance
        
    Returns:
        Dictionary mapping participant_id -> list of events
    """
    import pytz
    from datetime import datetime
    
    events_by_participant = {}
    
    # Convert date strings to format expected by Core_Event_Data
    # ⚠️ IMPORTANT: Parameter names are REVERSED!
    # "Before" = END date, "After" = START date
    after_date = timeframe["from"]   # START date (goes in "After" parameter)
    before_date = timeframe["to"]     # END date (goes in "Before" parameter)
    
    # Convert to ISO format with timezone if needed
    # Core_Event_Data accepts both YYYY-MM-DD and ISO datetime strings
    # Using ISO format with timezone for consistency: YYYY-MM-DDTHH:MM:SSZ
    import pytz
    from datetime import datetime
    
    tz = pytz.timezone(timeframe.get("tz", "America/New_York"))
    start_dt = datetime.strptime(timeframe["from"], "%Y-%m-%d")
    start_dt = tz.localize(start_dt)
    after_date_iso = start_dt.strftime("%Y-%m-%dT00:00:00Z")
    
    end_dt = datetime.strptime(timeframe["to"], "%Y-%m-%d")
    end_dt = tz.localize(end_dt.replace(hour=23, minute=59, second=59))
    before_date_iso = end_dt.strftime("%Y-%m-%dT23:59:59Z")
    
    # Fetch events for each participant concurrently
    import asyncio
    
    async def fetch_participant_events(participant_id: str):
        try:
            # Core_Event_Data accepts one calendar at a time
            # Note: request_heartbeat is Letta-specific and not needed for direct MCP calls
            # ⚠️ IMPORTANT: Parameter names are REVERSED - Before=end, After=start
            result = await mcp_client.get_core_event_data(
                calendar_id=participant_id,
                before=before_date_iso,  # END date
                after=after_date_iso      # START date
            )
            
            # The result is a JSON array of events (already parsed from text field)
            # Structure: [{"summary": "...", "id": "...", "start": {"dateTime": "..."}, ...}, ...]
            if isinstance(result, list):
                events = result
            elif isinstance(result, dict):
                # If wrapped in a dict, try to extract
                if "events" in result:
                    events = result["events"]
                elif "items" in result:
                    events = result["items"]
                elif "data" in result:
                    events = result["data"]
                else:
                    events = []
            else:
                events = []
            
            # Normalize to orchestrator's expected format
            # Core_Event_Data provides: summary, id, start.dateTime, end.dateTime, locked, protected, flexible, attendees_list
            # Orchestrator expects: id, title, start, end, locked, protected, flexible, attendees
            normalized_events = []
            for evt in events:
                # Skip all-day events if present (though Core_Event_Data should filter these)
                if evt.get("start", {}).get("date"):  # All-day events have "date" not "dateTime"
                    continue
                
                # Extract start/end from nested structure
                start_dt = evt.get("start", {}).get("dateTime") or evt.get("start", {}).get("date")
                end_dt = evt.get("end", {}).get("dateTime") or evt.get("end", {}).get("date")
                
                if not start_dt or not end_dt:
                    continue  # Skip events without valid start/end
                
                # Extract attendees_list (handle both array and potential string representation from workflow)
                attendees_list = evt.get("attendees_list", [])
                if isinstance(attendees_list, str):
                    # If it's a string representation, try to parse it
                    # This handles workflow errors where it's returned as a string
                    try:
                        import ast
                        attendees_list = ast.literal_eval(attendees_list)
                    except:
                        # If parsing fails, treat as empty
                        attendees_list = []
                elif not isinstance(attendees_list, list):
                    attendees_list = []
                
                # Normalize to orchestrator format
                normalized_events.append({
                    "id": evt.get("id", ""),
                    "title": evt.get("summary", ""),
                    "start": start_dt,
                    "end": end_dt,
                    "locked": evt.get("locked", False),
                    "protected": evt.get("protected", False),
                    "flexible": evt.get("flexible", True),
                    "attendees": attendees_list  # Include attendees list (renamed from attendees_list)
                })
            
            return participant_id, normalized_events
        except MCPError as e:
            logger.error(f"MCP error fetching events for {participant_id}: {e}")
            return participant_id, []
        except Exception as e:
            logger.error(f"Failed to fetch events for {participant_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return participant_id, []
    
    # Fetch all calendars concurrently
    tasks = [fetch_participant_events(pid) for pid in participant_ids]
    results = await asyncio.gather(*tasks)
    
    # Build result dictionary
    for participant_id, events in results:
        events_by_participant[participant_id] = events
    
    return events_by_participant
```

### 5. Modify Main Orchestrator Function

**File**: `letta/scheduling_orchestrator/orchestrate_scheduling.py`

Add logic at the beginning of `orchestrate_scheduling` to handle both modes:

```python
def orchestrate_scheduling(
    utterance: str,
    events_by_participant: Optional[str] = None,
    participant_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    context_json: Optional[str] = None,
    mcp_server_url: Optional[str] = None
) -> dict:
    """
    Orchestrate scheduling with flexible input options.
    
    Either provide events_by_participant (current approach) OR
    provide participant_ids and let orchestrator fetch calendars.
    """
    import os
    import asyncio
    
    # Determine which mode to use
    if events_by_participant:
        # Mode 1: Use provided events (current behavior)
        events_dict = json.loads(events_by_participant)
    elif participant_ids:
        # Mode 2: Fetch events from MCP
        if not context_json:
            return ResponseEnvelope(
                status="bad_input",
                explanation="context_json with timeframe is required when using participant_ids",
                proposals=[],
                error_message="Missing context_json with timeframe"
            ).model_dump()
        
        context = json.loads(context_json)
        if "timeframe" not in context:
            return ResponseEnvelope(
                status="bad_input",
                explanation="timeframe is required in context_json when using participant_ids",
                proposals=[],
                error_message="Missing timeframe in context_json"
            ).model_dump()
        
        # Get MCP server URL from parameter or environment
        mcp_url = mcp_server_url or os.getenv(
            "MCP_CALENDAR_SERVER_URL",
            "http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb"
        )
        
        # Create MCP client
        from .mcp_client import MCPCalendarClient
        mcp_client = MCPCalendarClient(
            base_url=mcp_url,
            timeout=int(os.getenv("MCP_CALENDAR_TIMEOUT", "30")),
            max_retries=int(os.getenv("MCP_CALENDAR_RETRY_ATTEMPTS", "3"))
        )
        
        # Fetch events asynchronously
        try:
            events_dict = asyncio.run(
                fetch_calendar_events(
                    participant_ids,
                    user_id,
                    context["timeframe"],
                    mcp_client
                )
            )
        except Exception as e:
            error_traceback = traceback.format_exc()
            return ResponseEnvelope(
                status="bad_input",
                explanation=f"Failed to fetch calendar events: {str(e)}",
                proposals=[],
                error_message=str(e),
                debug=DebugInfo()
            ).model_dump() | {"error_traceback": error_traceback}
    else:
        # Neither provided
        return ResponseEnvelope(
            status="bad_input",
            explanation="Must provide either events_by_participant or participant_ids",
            proposals=[],
            error_message="Missing required input"
        ).model_dump()
    
    # Continue with normal processing using events_dict...
    # (rest of function remains the same)
```

### 6. Add Configuration

**Environment Variables** (add to docker-compose.yml or .env):

```bash
MCP_CALENDAR_SERVER_URL=http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb
MCP_CALENDAR_TIMEOUT=30
MCP_CALENDAR_RETRY_ATTEMPTS=3
```

## Implementation Considerations

### Error Handling

The orchestrator must handle:
- **MCP server unavailable**: Return clear error message
- **Calendar API rate limits**: Implement retry with backoff
- **Invalid participant IDs**: Return specific error per participant
- **Missing calendar permissions**: Distinguish from other errors
- **Network timeouts**: Use configurable timeout
- **Partial calendar fetch failures**: Continue with available data or fail gracefully

### Performance

- **Parallel fetching**: Fetch all calendars concurrently using `asyncio.gather()`
- **Timeout**: Set reasonable timeouts (30s per calendar by default)
- **Retry logic**: Retry failed calendar fetches with exponential backoff
- **Caching**: Consider caching calendar data (with TTL) for repeated queries

### Backward Compatibility

The hybrid approach maintains full backward compatibility:
- Existing code using `events_by_participant` continues to work
- New code can use `participant_ids` for automatic fetching
- Agent can choose the best approach per situation

### Data Format Normalization

The MCP server may return events in Google Calendar API format. The `fetch_calendar_events` function must normalize to the expected format:
- Extract `start.dateTime` or `start` as ISO 8601 string
- Extract `end.dateTime` or `end` as ISO 8601 string
- Map `summary` or `title` to `title`
- Handle `locked`, `protected`, `flexible` flags
- Filter out all-day events

## Testing Strategy

1. **Unit Tests**: Test MCP client with mocked HTTP responses
2. **Integration Tests**: Test with real n8n MCP server (test environment)
3. **Error Scenarios**: Test timeout, network errors, invalid responses
4. **Format Normalization**: Test various event formats from MCP server
5. **Concurrent Fetching**: Verify parallel calendar fetching works correctly

## Migration Path

1. **Phase 1**: Add MCP client module (non-breaking)
2. **Phase 2**: Add hybrid function signature (backward compatible)
3. **Phase 3**: Update agent instructions to use new approach
4. **Phase 4**: Monitor and optimize based on usage

## Summary

The modifications required are:

1. ✅ Add `httpx` dependency
2. ✅ Create `mcp_client.py` module for MCP communication
3. ✅ Modify `orchestrate_scheduling` to accept `participant_ids` parameter
4. ✅ Add `fetch_calendar_events` function for parallel calendar fetching
5. ✅ Add error handling for MCP failures
6. ✅ Add configuration via environment variables
7. ✅ Maintain backward compatibility with existing `events_by_participant` parameter

This hybrid approach provides the best of both worlds: reliability through direct MCP access while maintaining flexibility for testing and custom calendar sources.

