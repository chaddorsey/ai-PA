"""MCP server for Gmail watch tools."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from gmail_watch.database import get_session
from gmail_watch.services.registry import ThreadRegistry

router = APIRouter(prefix="/mcp", tags=["mcp"])


class WatchThreadRequest(BaseModel):
    """Request to watch a thread."""

    thread_id: str = Field(..., description="Gmail thread ID to monitor")
    subject: str | None = Field(None, description="Thread subject (for display)")
    recipients: str | None = Field(
        None, description="Original recipients (comma-separated)"
    )
    followup_days: int | None = Field(
        None, description="Days to wait before follow-up reminder"
    )
    context: str | None = Field(
        None, description="Additional context about this thread"
    )


class UnwatchThreadRequest(BaseModel):
    """Request to stop watching a thread."""

    thread_id: str = Field(..., description="Gmail thread ID to stop watching")


class ListWatchedRequest(BaseModel):
    """Request to list watched threads."""

    include_inactive: bool = Field(
        False, description="Include manually deactivated watches"
    )
    include_replied: bool = Field(
        False, description="Include threads that received replies"
    )


class GetWatchStatusRequest(BaseModel):
    """Request to get watch status."""

    thread_id: str = Field(..., description="Gmail thread ID to check")


# Tool definitions for MCP
TOOLS = [
    {
        "name": "watch_thread",
        "description": (
            "Start monitoring a Gmail thread for replies. "
            "Use this after sending an important email that needs follow-up tracking."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "thread_id": {
                    "type": "string",
                    "description": "Gmail thread ID to monitor",
                },
                "subject": {
                    "type": "string",
                    "description": "Thread subject (for display)",
                },
                "recipients": {
                    "type": "string",
                    "description": "Original recipients (comma-separated)",
                },
                "followup_days": {
                    "type": "integer",
                    "description": "Days to wait before follow-up reminder",
                },
                "context": {
                    "type": "string",
                    "description": "Additional context about this thread",
                },
            },
            "required": ["thread_id"],
        },
    },
    {
        "name": "unwatch_thread",
        "description": (
            "Stop monitoring a Gmail thread. "
            "Use when a thread no longer needs tracking."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "thread_id": {
                    "type": "string",
                    "description": "Gmail thread ID to stop watching",
                },
            },
            "required": ["thread_id"],
        },
    },
    {
        "name": "list_watched_threads",
        "description": "List all Gmail threads currently being monitored for replies.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_inactive": {
                    "type": "boolean",
                    "description": "Include deactivated watches",
                },
                "include_replied": {
                    "type": "boolean",
                    "description": "Include threads with replies",
                },
            },
        },
    },
    {
        "name": "get_watch_status",
        "description": "Get detailed status of a specific watched thread.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "thread_id": {
                    "type": "string",
                    "description": "Gmail thread ID to check",
                },
            },
            "required": ["thread_id"],
        },
    },
]


@router.get("")
async def list_tools() -> dict[str, Any]:
    """List available MCP tools."""
    return {"tools": TOOLS}


@router.post("")
async def call_tool(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Handle MCP tool calls."""
    body = await request.json()

    tool_name = body.get("name")
    arguments = body.get("arguments", {})

    registry = ThreadRegistry(session)

    try:
        if tool_name == "watch_thread":
            thread_id = arguments.get("thread_id")
            if not thread_id:
                result = {"status": "error", "error": "thread_id is required"}
            else:
                recipients = arguments.get("recipients")
                if recipients:
                    recipients = [r.strip() for r in recipients.split(",")]

                result = await registry.watch_thread(
                    thread_id=thread_id,
                    subject=arguments.get("subject"),
                    recipients=recipients,
                    followup_days=arguments.get("followup_days"),
                    context=arguments.get("context"),
                )

        elif tool_name == "unwatch_thread":
            thread_id = arguments.get("thread_id")
            if not thread_id:
                result = {"status": "error", "error": "thread_id is required"}
            else:
                result = await registry.unwatch_thread(thread_id)

        elif tool_name == "list_watched_threads":
            result = await registry.list_watched(
                include_inactive=arguments.get("include_inactive", False),
                include_replied=arguments.get("include_replied", False),
            )

        elif tool_name == "get_watch_status":
            thread_id = arguments.get("thread_id")
            if not thread_id:
                result = {"status": "error", "error": "thread_id is required"}
            else:
                result = await registry.get_watch_status(thread_id)

        else:
            result = {"status": "error", "error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        result = {"status": "error", "error": str(e)}

    return {"content": [{"type": "text", "text": json.dumps(result)}]}
