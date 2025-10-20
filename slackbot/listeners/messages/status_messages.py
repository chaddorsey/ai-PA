# listeners/messages/status_messages.py
"""Mapping of Letta tool calls to user-friendly status messages."""

from typing import Dict, List


# Map tool names to status messages
TOOL_STATUS_MESSAGES: Dict[str, Dict[str, any]] = {
    "find_shared_meeting_slots": {
        "status": "Checking schedules…",
        "loading_messages": [
            "Checking calendars…",
            "Comparing schedules…",
            "Identifying shared slots…",
        ],
    },
    "search_email": {
        "status": "Searching emails…",
        "loading_messages": [
            "Searching through your emails…",
            "Looking for relevant messages…",
        ],
    },
    "get_calendar_events": {
        "status": "Checking calendar…",
        "loading_messages": [
            "Looking at your calendar…",
            "Fetching upcoming events…",
        ],
    },
    "create_calendar_event": {
        "status": "Creating event…",
        "loading_messages": [
            "Adding event to calendar…",
            "Setting up the meeting…",
        ],
    },
}

# Default status when no specific tool is detected
DEFAULT_STATUS = {
    "status": "Working on a response…",
    "loading_messages": [
        "Thinking through your request…",
        "Gathering information…",
        "Crafting a response…",
    ],
}


def get_status_for_tool(tool_name: str) -> Dict[str, any]:
    """Get status message configuration for a specific tool call."""
    return TOOL_STATUS_MESSAGES.get(tool_name, DEFAULT_STATUS)


def get_default_status() -> Dict[str, any]:
    """Get the default status configuration."""
    return DEFAULT_STATUS

