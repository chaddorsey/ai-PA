"""FastAPI app factory for scheduler MCP server."""

from __future__ import annotations

from scheduler_mcp.server_simple import create_app as create_simple_app


def create_app():
    """Create FastAPI app with simple HTTP JSON-RPC for Letta compatibility."""
    return create_simple_app()

