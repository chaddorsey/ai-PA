"""FastAPI app factory for scheduler MCP server."""

from __future__ import annotations

from scheduler_mcp.server import create_mcp_server


def create_app():
    server = create_mcp_server()
    return server.streamable_http_app()

