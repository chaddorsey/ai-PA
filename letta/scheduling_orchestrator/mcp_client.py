"""
MCP Client for retrieving calendar events from n8n MCP server.

This module handles communication with the n8n MCP server to retrieve
stripped-down event data via the Core_Event_Data tool.
"""

import json
import uuid
import logging
from typing import Dict, List, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """Exception raised for MCP-related errors."""
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"MCP Error {code}: {message}")


class MCPCalendarClient:
    """Client for interacting with n8n MCP calendar server."""
    
    def __init__(
        self,
        base_url: str,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize MCP calendar client.
        
        Args:
            base_url: Base URL of the MCP server (e.g., "http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb")
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
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
                self.base_url,
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
                        self.base_url,
                        json=payload,
                        headers=headers
                    )
                    response.raise_for_status()
                    
                    # Update session ID if present
                    new_session_id = response.headers.get("mcp-session-id")
                    if new_session_id:
                        self.session_id = new_session_id
                        headers["mcp-session-id"] = new_session_id
                    
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
                            return result["result"]
                        
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
                "attendees_list": ["email1@example.com", ...],  # Legacy field (for backward compatibility)
                "attendees_details": [  # New field with names
                  {"email": "email1@example.com", "name": "Full Name"},
                  ...
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
    
    async def fetch_event_by_id(
        self,
        calendar_id: str,
        event_id: str,
        days_forward: int = 14
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a specific event by ID from a calendar.
        
        Since Core_Event_Data only supports date range queries, this method:
        1. Fetches events in a date range (default: today to 14 days in the future)
        2. Filters the results to find the event with the matching ID
        3. Returns the event if found, None otherwise
        
        This method is optimized for rescheduling use cases, which only need to look
        at current and future events (it's unusual to reschedule past meetings).
        
        Args:
            calendar_id: Calendar identifier (user ID or email address of a participant)
            event_id: The ID of the event to fetch
            days_forward: Number of days in the future to search (default: 14)
            
        Returns:
            Event dictionary with structure matching Core_Event_Data format, or None if not found.
            Event dict includes: id, summary, start, end, locked, protected, flexible, etc.
            
        Raises:
            MCPError: If there's an error communicating with the MCP server
        """
        from datetime import datetime, timedelta
        import pytz
        
        try:
            # Calculate date range: from today to N days in the future
            now = datetime.now(pytz.UTC)
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)  # Start of today
            end_date = now + timedelta(days=days_forward)
            
            # Format dates for Core_Event_Data
            # ⚠️ IMPORTANT: Parameter names are REVERSED!
            # "Before" = END date, "After" = START date
            after_date_iso = start_date.strftime("%Y-%m-%dT00:00:00Z")
            before_date_iso = end_date.strftime("%Y-%m-%dT23:59:59Z")
            
            # Fetch events in the date range
            events = await self.get_core_event_data(
                calendar_id=calendar_id,
                before=before_date_iso,  # END date
                after=after_date_iso     # START date
            )
            
            # Filter to find the event with matching ID
            for event in events:
                if event.get("id") == event_id:
                    return event
            
            # Event not found in the date range
            logger.warning(
                f"Event {event_id} not found in calendar {calendar_id} "
                f"for date range {after_date_iso} to {before_date_iso}"
            )
            return None
            
        except MCPError:
            # Re-raise MCP errors
            raise
        except Exception as e:
            # Wrap other errors
            logger.error(f"Error fetching event {event_id} from calendar {calendar_id}: {str(e)}")
            raise MCPError(
                code=-32603,
                message=f"Error fetching event by ID: {str(e)}"
            )

