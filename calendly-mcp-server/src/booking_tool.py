"""
Calendly Booking Tool for MCP Server

Intelligent booking tool that auto-discovers custom fields and guides the LLM
through a successful booking flow with minimal friction.
"""

# MCP Tool Definition
CALENDLY_BOOK_TOOL = {
    "name": "calendly_book_slot",
    "description": (
        "Book a Calendly time slot with automatic custom field discovery. "
        "\n\n"
        "RECOMMENDED WORKFLOW:\n"
        "1. First call with basic info (url, date, time, name, email)\n"
        "2. If tool returns error 'required_fields_missing', it will list the required fields\n"
        "3. Gather missing information from user\n"
        "4. Retry with custom_fields populated\n"
        "5. Tool defaults to dry_run=true for safety - set to false only when user confirms\n"
        "\n"
        "IMPORTANT NOTES:\n"
        "- Different Calendly users have different custom required fields (e.g., meeting title, company)\n"
        "- This tool discovers them automatically and reports what's needed\n"
        "- Always use dry_run=true first to validate before actual booking\n"
        "- Actual booking (dry_run=false) creates a real calendar event\n"
        "\n"
        "SUPPORTS:\n"
        "- Profile URLs, event URLs, and direct links (/d/ format)\n"
        "- Multiple guest email addresses\n"
        "- Custom required and optional fields (auto-discovered)\n"
        "- Both 12-hour (3:30pm) and 24-hour (15:30) time formats"
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
                    "\n"
                    "NOTE: If you don't know what fields are required, call this tool once without custom_fields. "
                    "If required fields exist, the tool will return an error listing them, then you can retry with values."
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


# Error message templates
ERROR_MESSAGES = {
    "required_fields_missing": (
        "This Calendly event requires {count} additional custom field(s) to complete booking:\n\n"
        "{field_list}\n\n"
        "NEXT STEPS:\n"
        "1. Ask the user for this information\n"
        "2. Retry this tool call with the custom_fields parameter populated\n"
        "3. Use substring matching for field keys (e.g., 'title' matches 'What do you want to title the meeting?')\n\n"
        "Example retry:\n"
        "{example}"
    ),
    
    "date_not_found": (
        "Could not find date {date} (day {day}) on the calendar after checking {months} month(s). "
        "This usually means:\n"
        "1. The date is too far in the future (try a closer date)\n"
        "2. The date has no availability (verify with calendly_slots tool first)\n"
        "3. The date is in the past\n\n"
        "Suggestion: Use calendly_slots tool to find actually available dates."
    ),
    
    "time_not_found": (
        "Could not find time slot '{time}' on {date}. Tried variants: {variants}\n\n"
        "This usually means:\n"
        "1. The time slot was just booked by someone else\n"
        "2. The time format doesn't match (try both '14:30' and '2:30pm')\n"
        "3. The slot is no longer available\n\n"
        "Suggestion: Use calendly_slots tool to see currently available times for this date."
    )
}


def format_required_fields_error(missing_fields: list, event_url: str, date: str, time: str, 
                                 name: str, email: str) -> str:
    """Format a helpful error message for missing required fields."""
    
    # Create numbered list of fields
    field_list = "\n".join([f"  {i+1}. {field}" for i, field in enumerate(missing_fields)])
    
    # Create example retry call
    example_fields = {}
    for field in missing_fields[:2]:  # Show example for first 2
        # Suggest a reasonable key
        if "title" in field.lower():
            example_fields["title the meeting"] = "My Meeting Title"
        elif "company" in field.lower():
            example_fields["company"] = "Acme Corp"
        else:
            # Use first few words as key suggestion
            key_suggestion = " ".join(field.split()[:3]).lower()
            example_fields[key_suggestion] = "Your Answer Here"
    
    example = json.dumps({
        "url": event_url,
        "date": date,
        "time": time,
        "name": name,
        "email": email,
        "custom_fields": example_fields
    }, indent=2)
    
    return ERROR_MESSAGES["required_fields_missing"].format(
        count=len(missing_fields),
        field_list=field_list,
        example=example
    )


# For the call_tool implementation:
async def handle_booking_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle calendly_book_slot with intelligent field discovery and error guidance.
    """
    # Extract and validate arguments
    url = arguments.get("url")
    date = arguments.get("date")
    time = arguments.get("time")
    name = arguments.get("name")
    email = arguments.get("email")
    timezone = arguments.get("timezone", "America/New_York")
    guests = arguments.get("guests", [])
    custom_fields = arguments.get("custom_fields", {})
    dry_run = arguments.get("dry_run", True)  # Safe by default!
    
    # ... validation ...
    
    # Call the booking function
    result = await book_slot(
        event_url=url,
        date_iso=date,
        time_str=time,
        invitee_name=name,
        invitee_email=email,
        timezone=timezone,
        answers=custom_fields,
        guests=guests,
        dry_run=dry_run,
        headless=True,
        click_months_ahead=6,
        settle_ms=1000,
        screenshot_dir="/tmp"
    )
    
    # Enhanced error handling for LLM guidance
    if not result.get("ok"):
        reason = result.get("reason", "")
        
        # Required fields missing - provide detailed guidance
        if "required_fields_missing" in reason:
            missing = result.get("steps", {}).get("required_field_validation", {}).get("missing_required_fields", [])
            if missing:
                error_msg = format_required_fields_error(missing, url, date, time, name, email)
                raise ValueError(error_msg)
        
        # Date not found
        elif "date_not_found" in reason:
            steps = result.get("steps", {}).get("date_selection", {})
            raise ValueError(ERROR_MESSAGES["date_not_found"].format(
                date=date,
                day=steps.get("target_day", "?"),
                months=steps.get("months_navigated", 0) + 1
            ))
        
        # Time not found  
        elif "time_not_found" in reason:
            steps = result.get("steps", {}).get("time_selection", {})
            raise ValueError(ERROR_MESSAGES["time_not_found"].format(
                time=time,
                date=date,
                variants=steps.get("time_variants_tried", [])
            ))
        
        # Generic error
        else:
            raise ValueError(f"Booking failed: {reason}. Details: {result.get('message', 'No additional details')}")
    
    return result
```

## Key Benefits of This Approach:

1. **Single tool** - Simpler for LLM to understand
2. **Auto-discovery** - No separate discovery call needed
3. **Intelligent errors** - Guide LLM to retry correctly
4. **Try-and-learn pattern** - LLM learns requirements on first attempt
5. **Safe by default** - dry_run=true unless explicitly disabled

Want me to implement this into the MCP server now?
