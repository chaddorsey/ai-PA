"""
Calendly MCP Server - MCP Protocol Implementation

Handles JSON-RPC requests for the MCP protocol and tool execution.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import date, timedelta
import asyncio

from .calendly_slots import slots_for_profile_or_event

logger = logging.getLogger(__name__)

# Internal configuration constants
DEFAULT_SNIFF_WAIT = 6.0  # Seconds to wait for XHR sniffing (good balance of speed/reliability)
MIN_SNIFF_WAIT = 4.0      # Minimum for any reasonable success rate
PER_DAY_DELAY = 0.35      # Delay between per-day API calls (respectful rate limiting)
MAX_RETRIES = 2           # Number of retry attempts with increasing wait times

# Tool definitions for MCP protocol
CALENDLY_TOOLS = [
    {
        "name": "calendly_slots",
        "description": "Get all available Calendly slots (days & times) for a public profile or event URL. "
                      "Handles profile URLs (https://calendly.com/<owner>), event URLs "
                      "(https://calendly.com/<owner>/<slug>), and direct links (https://calendly.com/d/<code>/<name>). "
                      "Returns structured data with available days and time slots, properly formatted for the specified timezone. "
                      "Automatically handles UUID discovery, retry logic, and rate limiting. "
                      "Returns detailed error messages if issues occur.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Calendly profile URL (https://calendly.com/<owner>) or event URL "
                                  "(https://calendly.com/<owner>/<slug>)"
                },
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone for formatting times (e.g., 'America/New_York')",
                    "default": "America/New_York"
                },
                "start": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD). Defaults to today if omitted.",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                },
                "end": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD). Defaults to start+21 days if omitted.",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                }
            },
            "required": ["url"]
        }
    }
]


async def call_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool with the given arguments.
    
    Args:
        tool_name: Name of the tool to execute
        arguments: Tool arguments
        
    Returns:
        Tool execution result
        
    Raises:
        ValueError: If tool is unknown or arguments are invalid
    """
    if tool_name != "calendly_slots":
        raise ValueError(f"Unknown tool: '{tool_name}'. Available tools: calendly_slots")
    
    # Extract and validate arguments with expressive error messages
    url = arguments.get("url")
    if not url:
        raise ValueError(
            "Missing required parameter 'url'. "
            "Please provide a Calendly profile URL (https://calendly.com/<owner>) "
            "or event URL (https://calendly.com/<owner>/<slug> or https://calendly.com/d/<code>/<name>)."
        )
    
    # Validate URL format
    if not isinstance(url, str):
        raise ValueError(
            f"Parameter 'url' must be a string, got {type(url).__name__}. "
            f"Received value: {url}"
        )
    
    if not url.startswith("http"):
        raise ValueError(
            f"Parameter 'url' must be a valid HTTP(S) URL. "
            f"Received: '{url}'. "
            f"Expected format: https://calendly.com/<owner> or https://calendly.com/<owner>/<event>"
        )
    
    if "calendly.com" not in url.lower():
        raise ValueError(
            f"Parameter 'url' must be a Calendly URL (containing 'calendly.com'). "
            f"Received: '{url}'"
        )
    
    # Validate timezone
    timezone = arguments.get("timezone", "America/New_York")
    if not isinstance(timezone, str):
        raise ValueError(
            f"Parameter 'timezone' must be a string, got {type(timezone).__name__}. "
            f"Received value: {timezone}. "
            f"Expected IANA timezone like 'America/New_York' or 'Europe/London'."
        )
    
    # Validate and parse dates
    start = arguments.get("start")
    if start is None:
        start = date.today().isoformat()
    elif not isinstance(start, str):
        raise ValueError(
            f"Parameter 'start' must be a string in YYYY-MM-DD format, got {type(start).__name__}. "
            f"Received value: {start}"
        )
    else:
        # Validate date format
        try:
            date.fromisoformat(start)
        except ValueError as e:
            raise ValueError(
                f"Parameter 'start' has invalid date format. "
                f"Received: '{start}'. "
                f"Expected: YYYY-MM-DD (e.g., '2025-10-15'). "
                f"Parse error: {e}"
            )
    
    end = arguments.get("end")
    if end is None:
        end = (date.fromisoformat(start) + timedelta(days=21)).isoformat()
    elif not isinstance(end, str):
        raise ValueError(
            f"Parameter 'end' must be a string in YYYY-MM-DD format, got {type(end).__name__}. "
            f"Received value: {end}"
        )
    else:
        # Validate date format
        try:
            date.fromisoformat(end)
        except ValueError as e:
            raise ValueError(
                f"Parameter 'end' has invalid date format. "
                f"Received: '{end}'. "
                f"Expected: YYYY-MM-DD (e.g., '2025-11-15'). "
                f"Parse error: {e}"
            )
    
    # Validate date range makes sense
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        if end_date <= start_date:
            raise ValueError(
                f"Parameter 'end' must be after 'start'. "
                f"Received: start='{start}', end='{end}'. "
                f"The end date must be at least one day after the start date."
            )
        
        # Check if range is too large (performance consideration)
        days_diff = (end_date - start_date).days
        if days_diff > 180:
            logger.warning(f"Large date range requested: {days_diff} days. This may take longer to process.")
    except ValueError:
        # Already handled above, re-raise
        raise
    
    logger.info(f"Calling calendly_slots: url={url}, tz={timezone}, start={start}, end={end}, "
                f"using sniff_wait={DEFAULT_SNIFF_WAIT}s (with auto-retry up to {DEFAULT_SNIFF_WAIT + 3 * MAX_RETRIES}s), "
                f"per_day_delay={PER_DAY_DELAY}s")
    
    try:
        # Call the core calendly_slots function with retry logic
        result = await _call_with_retry(
            url=url,
            tz=timezone,
            start=start,
            end=end,
            initial_sniff_wait=DEFAULT_SNIFF_WAIT,
            sleep=PER_DAY_DELAY
        )
        
        events_count = len(result.get('events', []))
        logger.info(f"calendly_slots completed: {events_count} event(s) found")
        
        # Check for and report any per-event errors
        errors_found = []
        for event in result.get('events', []):
            if 'error' in event or 'error_hint' in event:
                errors_found.append({
                    'url': event.get('url'),
                    'error': event.get('error'),
                    'hint': event.get('error_hint')
                })
        
        if errors_found and events_count == len(errors_found):
            # All events failed - provide aggregate error
            error_details = "\n".join([
                f"  - {err['url']}: {err.get('hint') or err.get('error')}"
                for err in errors_found
            ])
            logger.warning(f"All events had errors:\n{error_details}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error executing calendly_slots: {e}", exc_info=True)
        
        # Provide context-specific error messages
        error_msg = str(e)
        if "timeout" in error_msg.lower():
            raise ValueError(
                f"Timeout while querying Calendly: {error_msg}. "
                f"The Calendly service may be slow or unavailable. Please try again in a moment."
            )
        elif "connection" in error_msg.lower():
            raise ValueError(
                f"Connection error while querying Calendly: {error_msg}. "
                f"Please check network connectivity or try again later."
            )
        elif "404" in error_msg or "not found" in error_msg.lower():
            raise ValueError(
                f"Calendly resource not found: {error_msg}. "
                f"Please verify the URL is correct and the event/profile is publicly accessible."
            )
        else:
            raise ValueError(
                f"Error querying Calendly: {error_msg}. "
                f"URL: {url}, Date range: {start} to {end}"
            )


async def _call_with_retry(url: str, tz: str, start: str, end: str, 
                           initial_sniff_wait: float, sleep: float,
                           max_retries: int = MAX_RETRIES) -> Dict[str, Any]:
    """
    Call calendly_slots with automatic retry and increasing wait times on UUID discovery failure.
    
    Args:
        url: Calendly URL
        tz: Timezone
        start: Start date
        end: End date
        initial_sniff_wait: Initial sniff wait time
        sleep: Per-day delay
        max_retries: Maximum number of retries
        
    Returns:
        Result from slots_for_profile_or_event
        
    Raises:
        ValueError: If all retries fail
    """
    sniff_wait = initial_sniff_wait
    
    for attempt in range(max_retries + 1):
        logger.info(f"Attempt {attempt + 1}/{max_retries + 1} with sniff_wait={sniff_wait}s")
        
        result = await slots_for_profile_or_event(
            url=url,
            tz=tz,
            start=start,
            end=end,
            sniff_wait=sniff_wait,
            sleep=sleep
        )
        
        # Check if any events had uuid_not_found error
        has_uuid_error = any(
            event.get('error') == 'uuid_not_found' 
            for event in result.get('events', [])
        )
        
        if not has_uuid_error:
            # Success!
            if attempt > 0:
                logger.info(f"UUID discovery succeeded on attempt {attempt + 1}")
            return result
        
        # UUID not found - retry with increased wait time
        if attempt < max_retries:
            sniff_wait += 3.0  # Increase by 3 seconds each retry
            logger.warning(
                f"UUID not found on attempt {attempt + 1}/{max_retries + 1}. "
                f"Retrying with increased sniff_wait={sniff_wait}s..."
            )
            # Small delay before retry
            await asyncio.sleep(1.0)
        else:
            # Final attempt failed - provide comprehensive error message
            logger.error(f"UUID discovery failed after {max_retries + 1} attempts with wait times up to {sniff_wait}s")
            # Add helpful error message
            for event in result.get('events', []):
                if event.get('error') == 'uuid_not_found':
                    event['error_hint'] = (
                        f"Could not discover event UUID after {max_retries + 1} attempts "
                        f"(wait times: {DEFAULT_SNIFF_WAIT}s → {sniff_wait}s). "
                        f"This typically means:\n"
                        f"  1) The event has no availability in the near future (Calendly pages with no available dates don't trigger the UUID API call)\n"
                        f"  2) The event URL may be private, expired, or invalid\n"
                        f"  3) The page may require authentication\n"
                        f"\nSuggestion: Try a different date range or verify the URL is publicly accessible. "
                        f"URL tested: {event.get('url')}"
                    )
            return result
    
    return result


def get_server_info() -> Dict[str, Any]:
    """Get server information for MCP initialize response."""
    return {
        "name": "calendly-tools",
        "version": "1.0.0",
        "protocolVersion": "2024-11-05"
    }


def get_server_capabilities() -> Dict[str, Any]:
    """Get server capabilities for MCP initialize response."""
    return {
        "tools": {}
    }


async def handle_initialize(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle MCP initialize request.
    
    Args:
        params: Initialize parameters
        
    Returns:
        Initialize response
    """
    logger.info("Handling initialize request")
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": get_server_capabilities(),
        "serverInfo": get_server_info()
    }


async def handle_tools_list(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle MCP tools/list request.
    
    Args:
        params: List parameters
        
    Returns:
        List of available tools
    """
    logger.info("Handling tools/list request")
    return {
        "tools": CALENDLY_TOOLS
    }


async def handle_tools_call(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle MCP tools/call request.
    
    Args:
        params: Call parameters containing tool name and arguments
        
    Returns:
        Tool execution result
    """
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    
    logger.info(f"Handling tools/call request: tool={tool_name}")
    
    if not tool_name:
        raise ValueError("Missing tool name in tools/call request")
    
    # Execute the tool
    result = await call_tool(tool_name, arguments)
    
    # Return in MCP format
    return {
        "content": [
            {
                "type": "text",
                "text": str(result)
            }
        ]
    }


async def handle_mcp_request(method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Route and handle MCP protocol requests.
    
    Args:
        method: JSON-RPC method name
        params: Method parameters
        
    Returns:
        Method response
        
    Raises:
        ValueError: If method is unknown
    """
    params = params or {}
    
    if method == "initialize":
        return await handle_initialize(params)
    elif method == "tools/list":
        return await handle_tools_list(params)
    elif method == "tools/call":
        return await handle_tools_call(params)
    else:
        raise ValueError(f"Unknown method: {method}")

