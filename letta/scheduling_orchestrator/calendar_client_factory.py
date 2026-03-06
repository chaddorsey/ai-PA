"""
Factory for selecting the calendar client implementation.

When USE_DIRECT_CALENDAR=true, returns GoogleCalendarClient (direct API).
Otherwise, returns MCPCalendarClient (via n8n MCP).

Both clients expose the same interface:
  - async initialize()
  - async get_core_event_data(calendar_id, before, after)
  - async fetch_event_by_id(calendar_id, event_id, days_forward)
"""

import logging
import os

logger = logging.getLogger(__name__)


def get_calendar_client(**kwargs):
    """
    Create the appropriate calendar client based on configuration.

    When USE_DIRECT_CALENDAR is set, uses direct Google Calendar API.
    Otherwise falls back to n8n MCP client.

    Args:
        **kwargs: Passed to the client constructor.
            For MCP client: base_url, timeout, max_retries
            For Google client: timeout, max_retries (base_url ignored)

    Returns:
        Calendar client instance (GoogleCalendarClient or MCPCalendarClient)
    """
    use_direct = os.getenv("USE_DIRECT_CALENDAR", "").lower() in ("true", "1", "yes")

    if use_direct:
        try:
            from google_calendar_client import GoogleCalendarClient, MCPError
            logger.info("Using direct Google Calendar API client")
            return GoogleCalendarClient(**kwargs)
        except ImportError:
            logger.warning(
                "google_calendar_client not available, falling back to MCP client"
            )
        except Exception as e:
            logger.warning(
                "Failed to create Google Calendar client (%s), falling back to MCP", e
            )

    from mcp_client import MCPCalendarClient
    mcp_url = kwargs.get(
        "base_url",
        os.getenv(
            "MCP_CALENDAR_SERVER_URL",
            "http://n8n:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb",
        ),
    )
    logger.info("Using n8n MCP calendar client at %s", mcp_url)
    return MCPCalendarClient(
        base_url=mcp_url,
        timeout=kwargs.get("timeout", 30),
        max_retries=kwargs.get("max_retries", 3),
    )


def get_error_class():
    """Get the MCPError class for exception handling."""
    try:
        from mcp_client import MCPError
        return MCPError
    except ImportError:
        from google_calendar_client import MCPError
        return MCPError
