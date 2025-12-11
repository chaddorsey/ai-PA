"""FastAPI app factory for scheduler MCP server."""

from __future__ import annotations

from scheduler_mcp.server import create_app as create_mcp_app


def create_app():
    """Create FastAPI app with FastMCP server."""
    return create_mcp_app()

