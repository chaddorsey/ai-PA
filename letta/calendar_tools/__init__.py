"""
Google Calendar CRUD Tools for Letta

Custom tools for creating, reading, updating, and deleting calendar events
using Google Calendar API with user OAuth authentication.
"""

from typing import Dict, Any

# Export all tool functions
from .tools import (
    create_calendar_event,
    get_calendar_events,
    get_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    list_calendars,
)

__all__ = [
    "create_calendar_event",
    "get_calendar_events",
    "get_calendar_event",
    "update_calendar_event",
    "delete_calendar_event",
    "list_calendars",
]
