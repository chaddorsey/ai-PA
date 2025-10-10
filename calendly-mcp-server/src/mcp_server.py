"""
Calendly MCP Server - MCP Protocol Implementation

Handles JSON-RPC requests for the MCP protocol and tool execution.
"""

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import date, timedelta
import asyncio

from .calendly_slots import slots_for_profile_or_event
from .calendly_book_slot_safe import book_slot

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
    },
    {
        "name": "calendly_book_slot",
        "description": (
            "Book a Calendly time slot with automatic custom field discovery. "
            "\n\n"
            "RECOMMENDED WORKFLOW:\n"
            "1. Use calendly_slots tool first to find available dates and times\n"
            "2. Call this tool with basic info (url, date, time, name, email) and dry_run=true\n"
            "3. If error 'required_fields_missing' is returned, it lists the exact fields needed\n"
            "4. Ask user for missing information\n"
            "5. Retry with custom_fields populated\n"
            "6. When user confirms, call again with dry_run=false to create actual booking\n"
            "\n\n"
            "IMPORTANT NOTES:\n"
            "- Different Calendly users have different custom required fields (e.g., meeting title, company name)\n"
            "- This tool auto-discovers them and tells you exactly what's needed\n"
            "- ALWAYS use dry_run=true first (it's the default) to validate\n"
            "- Only set dry_run=false when user explicitly confirms the booking\n"
            "- Actual booking (dry_run=false) creates a REAL calendar event\n"
            "\n\n"
            "FEATURES:\n"
            "- Auto-discovers and validates custom required fields\n"
            "- Supports multiple guest email addresses\n"
            "- Handles both 12-hour (3:30pm) and 24-hour (15:30) time formats\n"
            "- Returns detailed errors with retry guidance\n"
            "- Safe dry-run mode by default"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Calendly event URL (e.g., https://calendly.com/user/30min)"
                },
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                },
                "time": {
                    "type": "string",
                    "description": "Time in HH:MM (24h) or h:mma format. Examples: '14:30', '2:30pm', '2:30 PM'"
                },
                "name": {
                    "type": "string",
                    "description": "Invitee full name"
                },
                "email": {
                    "type": "string",
                    "description": "Invitee email address"
                },
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone (e.g., 'America/New_York', 'Europe/London')",
                    "default": "America/New_York"
                },
                "guests": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: Additional guest email addresses to invite to the meeting"
                },
                "custom_fields": {
                    "type": "object",
                    "description": (
                        "Custom field responses for event-specific questions. "
                        "Keys should match part of the field label (case-insensitive substring match). "
                        "\n\n"
                        "Examples:\n"
                        "  {'title the meeting': 'Q4 Strategy Discussion'}\n"
                        "  {'company': 'Acme Corp', 'main topic': 'Budget review'}\n"
                        "\n\n"
                        "NOTE: If you don't know what fields are required, call this tool once without custom_fields. "
                        "If required fields exist, the tool will return an error listing them with examples."
                    ),
                    "additionalProperties": {"type": "string"}
                },
                "dry_run": {
                    "type": "boolean",
                    "description": (
                        "If true (DEFAULT), validates the booking flow without actually submitting. "
                        "Set to false ONLY when user explicitly confirms they want to create the booking. "
                        "\n\n"
                        "SAFETY: Always use dry_run=true first to validate, then ask user for confirmation before dry_run=false."
                    ),
                    "default": True
                }
            },
            "required": ["url", "date", "time", "name", "email"]
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
    if tool_name == "calendly_slots":
        return await _handle_calendly_slots(arguments)
    elif tool_name == "calendly_book_slot":
        return await _handle_calendly_book_slot(arguments)
    else:
        raise ValueError(f"Unknown tool: '{tool_name}'. Available tools: calendly_slots, calendly_book_slot")


async def _handle_calendly_slots(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle calendly_slots tool - check availability."""
    
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


async def _handle_calendly_book_slot(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle calendly_book_slot tool - book a specific time slot.
    
    Provides intelligent error handling for required custom fields and guides
    the LLM through successful booking.
    """
    # Extract and validate arguments
    url = arguments.get("url")
    if not url:
        raise ValueError("Missing required parameter 'url'")
    
    date_str = arguments.get("date")
    if not date_str:
        raise ValueError("Missing required parameter 'date' (format: YYYY-MM-DD)")
    
    time_str = arguments.get("time")
    if not time_str:
        raise ValueError("Missing required parameter 'time' (format: HH:MM or h:mma)")
    
    name = arguments.get("name")
    if not name:
        raise ValueError("Missing required parameter 'name'")
    
    email = arguments.get("email")
    if not email:
        raise ValueError("Missing required parameter 'email'")
    
    timezone = arguments.get("timezone", "America/New_York")
    guests = arguments.get("guests", [])
    custom_fields = arguments.get("custom_fields", {})
    dry_run = arguments.get("dry_run", True)  # Safe by default!
    
    # Validate date format
    try:
        date.fromisoformat(date_str)
    except ValueError as e:
        raise ValueError(f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD. Error: {e}")
    
    logger.info(f"Calling calendly_book_slot: url={url}, date={date_str}, time={time_str}, "
                f"name={name}, email={email}, guests={len(guests)}, "
                f"custom_fields={len(custom_fields)}, dry_run={dry_run}")
    
    try:
        # Call the booking function
        result = await book_slot(
            event_url=url,
            date_iso=date_str,
            time_str=time_str,
            invitee_name=name,
            invitee_email=email,
            timezone=timezone,
            answers=custom_fields,
            guests=guests,
            dry_run=dry_run,
            headless=True,
            click_months_ahead=6,
            settle_ms=2000,  # Increased to 2s for better confirmation detection
            screenshot_dir="/tmp"
        )
        
        # Check if booking succeeded
        if not result.get("ok"):
            reason = result.get("reason", "")
            
            # Required fields missing - provide detailed guidance
            if "required_fields_missing" in reason:
                validation = result.get("steps", {}).get("required_field_validation", {})
                missing = validation.get("missing_required_fields", [])
                
                if missing:
                    # Format helpful error message
                    field_list = "\n".join([f"  {i+1}. \"{field}\"" for i, field in enumerate(missing)])
                    
                    # Create example custom_fields object
                    example_fields = {}
                    for field in missing[:2]:  # Show example for first 2
                        if "title" in field.lower():
                            key = "title the meeting"
                            value = "Q4 Strategy Discussion"
                        elif "company" in field.lower():
                            key = "company"
                            value = "Acme Corp"
                        else:
                            # Use first few words as suggestion
                            key = " ".join(field.split()[:3]).lower()
                            value = "Your Answer Here"
                        example_fields[key] = value
                    
                    example_json = json.dumps({
                        "url": url,
                        "date": date_str,
                        "time": time_str,
                        "name": name,
                        "email": email,
                        "custom_fields": example_fields
                    }, indent=2)
                    
                    error_msg = (
                        f"This Calendly event requires {len(missing)} additional custom field(s):\n\n"
                        f"{field_list}\n\n"
                        f"NEXT STEPS:\n"
                        f"1. Ask the user for this information\n"
                        f"2. Retry this tool call with the custom_fields parameter\n"
                        f"3. Use substring matching for keys (case-insensitive)\n\n"
                        f"Example retry:\n{example_json}\n\n"
                        f"{validation.get('hint', '')}"
                    )
                    raise ValueError(error_msg)
            
            # Date not found
            elif "date_not_found" in reason:
                steps = result.get("steps", {}).get("date_selection", {})
                raise ValueError(
                    f"Could not find date {date_str} on the calendar after checking "
                    f"{steps.get('months_navigated', 0) + 1} month(s). "
                    f"This usually means:\n"
                    f"  1. The date has no availability (verify with calendly_slots tool first)\n"
                    f"  2. The date is too far in the future\n"
                    f"  3. The date is in the past\n\n"
                    f"Suggestion: Use calendly_slots('{url}') to find actually available dates."
                )
            
            # Time not found
            elif "time_not_found" in reason:
                steps = result.get("steps", {}).get("time_selection", {})
                raise ValueError(
                    f"Could not find time slot '{time_str}' on {date_str}. "
                    f"Tried variants: {steps.get('time_variants_tried', [])}. "
                    f"This usually means:\n"
                    f"  1. The time slot was just booked by someone else\n"
                    f"  2. The time is not available on this date\n\n"
                    f"Suggestion: Use calendly_slots('{url}', '{date_str}', '{date_str}') "
                    f"to see currently available times for this date."
                )
            
            # Next button not found
            elif "next_button_not_found" in reason:
                raise ValueError(
                    f"Could not find the 'Next' button after selecting time {time_str}. "
                    f"This may indicate a Calendly UI change. Please report this issue."
                )
            
            # Confirmation not detected (booking may have succeeded but verification failed)
            elif "confirmation_not_detected" in reason:
                conf_step = result.get("steps", {}).get("confirmation", {})
                raise ValueError(
                    f"Booking may have been submitted, but confirmation could not be verified. "
                    f"Details:\n"
                    f"  - Final URL: {conf_step.get('final_url', 'unknown')}\n"
                    f"  - URL changed: {conf_step.get('url_changed', False)}\n"
                    f"  - Invitee ID in URL: {conf_step.get('invitee_id_in_url', False)}\n"
                    f"  - Confirmation text found: {conf_step.get('confirmation_text_found', False)}\n"
                    f"  - ICS link found: {conf_step.get('ics_url') is not None}\n\n"
                    f"IMPORTANT: The booking MAY have succeeded. Please check:\n"
                    f"  1. User's email ({email}) for confirmation\n"
                    f"  2. Calendar for the event on {date_str} at {time_str}\n"
                    f"  3. Final URL above for invitee/confirmation page\n\n"
                    f"To avoid duplicate bookings, verify before retrying."
                )
            
            # Generic error
            else:
                raise ValueError(
                    f"Booking failed: {reason}. "
                    f"Message: {result.get('message', 'No additional details')}"
                )
        
        # Success!
        logger.info(f"calendly_book_slot completed: ok={result.get('ok')}, dry_run={dry_run}")
        
        # Return concise result for LLM
        return {
            "ok": result.get("ok"),
            "dry_run": dry_run,
            "message": result.get("message"),
            "event_url": url,
            "date": date_str,
            "time": time_str,
            "invitee_name": name,
            "invitee_email": email,
            "guests_added": result.get("steps", {}).get("guests", {}).get("added", []),
            "custom_fields_filled": list(result.get("steps", {}).get("custom_answers", {}).get("filled", {}).keys()),
            "confirmation_url": result.get("confirmation_url") if not dry_run else None,
            "ics_url": result.get("ics_url") if not dry_run else None,
            "steps_completed": [
                step_name for step_name, step_data in result.get("steps", {}).items()
                if step_data.get("ok") == True
            ]
        }
        
    except ValueError:
        # Re-raise validation errors
        raise
    except Exception as e:
        logger.error(f"Error executing calendly_book_slot: {e}", exc_info=True)
        raise ValueError(f"Unexpected error during booking: {str(e)}")


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

