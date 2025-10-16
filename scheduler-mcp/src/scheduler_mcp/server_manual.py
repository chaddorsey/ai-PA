"""Scheduler MCP server with manual schema definition for Letta compatibility."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Dict

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    TextContent,
    Tool,
)
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from scheduler_mcp.client import SchedulerClient, SchedulerClientError
from scheduler_mcp.settings import settings

# Context variable to track current agent
current_agent_id = ContextVar[str]("current_agent_id", default="unknown")


class AgentIdentityMiddleware(BaseHTTPMiddleware):
    """Extract agent ID from request headers or query params."""

    async def dispatch(self, request: Request, call_next):
        # Extract agent ID from custom header (preferred)
        agent_id = request.headers.get("X-Agent-ID")

        # Fallback to query param (for development/testing)
        if not agent_id:
            agent_id = request.query_params.get("agent_id")

        # Store in context for this request
        if agent_id:
            token = current_agent_id.set(agent_id)
        else:
            token = current_agent_id.set("system")

        try:
            response = await call_next(request)
            return response
        finally:
            if agent_id:
                current_agent_id.reset(token)


def get_current_agent() -> str:
    """Get current agent ID from context."""
    agent_id = current_agent_id.get()
    return agent_id if agent_id != "unknown" else "system"


async def _get_client() -> SchedulerClient:
    """Get scheduler service client."""
    return SchedulerClient(base_url=settings.scheduler_base_url, api_key=settings.api_key)


# Define tool schemas manually in JSON Schema format for Letta compatibility
TOOL_SCHEMAS = [
    Tool(
        name="schedule_reminder",
        description="Schedule a message/reminder to be delivered to an agent at a specific time. Use this for reminders, prompts, or scheduled notifications.",
        inputSchema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The reminder message text to deliver to the agent",
                },
                "when": {
                    "type": "string",
                    "description": "When to send the reminder (Eastern Time unless timezone specified). Examples: 'in 30 minutes', 'tomorrow at 9am', 'every day at 8am'",
                },
                "title": {
                    "type": "string",
                    "description": "Short title for this reminder (e.g., 'Morning check-in', 'Meeting prep')",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent to receive the reminder. Defaults to the requesting agent (you).",
                },
                "category": {
                    "type": "string",
                    "description": "Category for organization (e.g., 'daily_routine', 'meeting_prep', 'follow_up')",
                },
                "timezone": {
                    "type": "string",
                    "description": "Timezone for schedule. Defaults to 'America/New_York' (Eastern Time).",
                },
            },
            "required": ["message", "when", "title"],
        },
    ),
    Tool(
        name="schedule_action",
        description="Schedule a script or HTTP/API call to run at a specific time. Use this for automated tasks like data scraping, backups, API triggers, etc.",
        inputSchema={
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "enum": ["script", "http"],
                    "description": "Type of action: 'script' to run a file, 'http' to make an API call",
                },
                "target": {
                    "type": "string",
                    "description": "For 'script': filename in /app/scripts/ (e.g., 'download_news.py'). For 'http': full URL (e.g., 'https://api.example.com/webhook')",
                },
                "when": {
                    "type": "string",
                    "description": "When to run (Eastern Time unless timezone specified). Examples: 'in 5 minutes', 'every day at 2am', 'every hour'",
                },
                "title": {
                    "type": "string",
                    "description": "Short title for this action (e.g., 'Daily news scraper', 'Trigger data sync')",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    "description": "HTTP method (only for action_type='http'). Defaults to POST.",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command-line arguments for scripts (e.g., ['--source', 'nyt', '--limit', '50'])",
                },
                "body": {
                    "type": "object",
                    "description": "JSON body for HTTP POST/PUT/PATCH requests (only for action_type='http')",
                },
                "headers": {
                    "type": "object",
                    "description": "HTTP headers (only for action_type='http'). Example: {'Authorization': 'Bearer token123'}",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of what this action does and why it's scheduled",
                },
                "timezone": {
                    "type": "string",
                    "description": "Timezone for schedule. Defaults to 'America/New_York' (Eastern Time).",
                },
            },
            "required": ["action_type", "target", "when", "title"],
        },
    ),
    Tool(
        name="list_scheduled_jobs",
        description="List scheduled jobs with filtering options. Times are shown in Eastern Time by default. Use filters to narrow results.",
        inputSchema={
            "type": "object",
            "properties": {
                "filters": {
                    "type": "object",
                    "description": "Filter criteria (all conditions are AND-ed together)",
                    "properties": {
                        "created_by": {
                            "type": "string",
                            "description": "Filter by creator. Use 'me' or 'self' for your own jobs.",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["scheduled", "paused", "cancelled", "completed"],
                            "description": "Filter by job status",
                        },
                        "event_type": {
                            "type": "string",
                            "enum": ["reminder", "script", "http"],
                            "description": "Filter by type of event",
                        },
                        "category": {
                            "type": "string",
                            "description": "Filter by category (for reminders)",
                        },
                    },
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of jobs to return. Defaults to 20, max 100.",
                    "minimum": 1,
                    "maximum": 100,
                },
                "show_utc": {
                    "type": "boolean",
                    "description": "Show times in UTC instead of Eastern Time. Defaults to false.",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="manage_scheduled_job",
        description="Update, pause, resume, or cancel an existing scheduled job.",
        inputSchema={
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "ID of the job to manage (obtained from schedule_* tools or list_scheduled_jobs)",
                },
                "operation": {
                    "type": "string",
                    "enum": ["update", "pause", "resume", "cancel"],
                    "description": "What to do: 'update' to modify details, 'pause' to stop temporarily, 'resume' to re-activate, 'cancel' to delete permanently",
                },
                "updates": {
                    "type": "object",
                    "description": "Fields to update (only for operation='update'). Can include: 'title', 'description', 'when', 'message', etc.",
                },
            },
            "required": ["job_id", "operation"],
        },
    ),
]


async def handle_schedule_reminder(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle schedule_reminder tool call."""
    try:
        client = await _get_client()
        creator = get_current_agent()
        recipient = arguments.get("agent_id") or creator

        job_data = {
            "title": arguments["title"],
            "description": f"Reminder: {arguments['message']}",
            "created_by": creator,
            "schedule": {
                "type": "natural",
                "expression": arguments["when"],
                "timezone": arguments.get("timezone", "America/New_York"),
            },
            "actions": [
                {
                    "action_type": "agent_message",
                    "config": {
                        "agent_id": recipient,
                        "message": arguments["message"],
                        "category": arguments.get("category"),
                    },
                }
            ],
        }

        if arguments.get("category"):
            job_data["metadata"] = [{"key": "category", "value": {"category": arguments["category"]}}]

        response = await client.create_job(job_data)

        return {
            "success": True,
            "job_id": response["job_id"],
            "message": f"Scheduled '{arguments['title']}' to run {arguments['when']}",
            "next_run_at": response.get("next_run_at"),
            "created_by": creator,
            "recipient": recipient,
        }

    except SchedulerClientError as e:
        return {"success": False, "error": "SchedulerServiceError", "message": str(e)}
    except Exception as e:
        return {"success": False, "error": "UnexpectedError", "message": str(e)}


async def handle_schedule_action(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle schedule_action tool call."""
    try:
        action_type = arguments.get("action_type")
        if action_type not in ["script", "http"]:
            return {
                "success": False,
                "error": "InvalidActionType",
                "message": f"action_type must be 'script' or 'http', got '{action_type}'",
            }

        # Validate parameter combinations
        if action_type == "script":
            if arguments.get("body") is not None:
                return {
                    "success": False,
                    "error": "InvalidParameterCombination",
                    "message": "The 'body' parameter is only valid for HTTP requests, not scripts. Use 'args' instead.",
                }

        client = await _get_client()
        creator = get_current_agent()

        # Build action config
        if action_type == "script":
            action_config = {
                "action_type": "script",
                "config": {
                    "script_path": arguments["target"],
                    "args": arguments.get("args", []),
                    "timeout_seconds": (arguments.get("timeout_minutes", 5)) * 60,
                },
            }
        else:  # http
            action_config = {
                "action_type": "http",
                "config": {
                    "url": arguments["target"],
                    "method": arguments.get("method", "POST"),
                    "headers": arguments.get("headers", {}),
                    "body": arguments.get("body", {}),
                    "timeout_seconds": (arguments.get("timeout_minutes", 1)) * 60,
                },
            }

        job_data = {
            "title": arguments["title"],
            "description": arguments.get("description", f"{action_type.upper()} action: {arguments['target']}"),
            "created_by": creator,
            "schedule": {
                "type": "natural",
                "expression": arguments["when"],
                "timezone": arguments.get("timezone", "America/New_York"),
            },
            "actions": [action_config],
        }

        response = await client.create_job(job_data)

        return {
            "success": True,
            "job_id": response["job_id"],
            "message": f"Scheduled '{arguments['title']}' to run {arguments['when']}",
            "next_run_at": response.get("next_run_at"),
            "created_by": creator,
        }

    except SchedulerClientError as e:
        return {"success": False, "error": "SchedulerServiceError", "message": str(e)}
    except Exception as e:
        return {"success": False, "error": "UnexpectedError", "message": str(e)}


async def handle_list_scheduled_jobs(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle list_scheduled_jobs tool call."""
    try:
        client = await _get_client()
        current_agent = get_current_agent()

        filters = arguments.get("filters", {})
        if filters.get("created_by") in ["me", "self"]:
            filters["created_by"] = current_agent

        query_params = {
            **filters,
            "limit": min(arguments.get("limit", 20), 100),
            "show_utc": arguments.get("show_utc", False),
        }

        jobs = await client.list_jobs(query_params)

        return {
            "success": True,
            "count": len(jobs),
            "timezone": "UTC" if arguments.get("show_utc") else "America/New_York (ET)",
            "jobs": jobs,
        }

    except SchedulerClientError as e:
        return {"success": False, "error": "SchedulerServiceError", "message": str(e)}
    except Exception as e:
        return {"success": False, "error": "UnexpectedError", "message": str(e)}


async def handle_manage_scheduled_job(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle manage_scheduled_job tool call."""
    try:
        operation = arguments["operation"]
        if operation not in ["update", "pause", "resume", "cancel"]:
            return {
                "success": False,
                "error": "InvalidOperation",
                "message": f"operation must be one of: update, pause, resume, cancel. Got '{operation}'",
            }

        client = await _get_client()
        job_id = arguments["job_id"]

        if operation == "update":
            if not arguments.get("updates"):
                return {
                    "success": False,
                    "error": "MissingRequiredParameter",
                    "message": "The 'updates' parameter is required for operation='update'",
                }
            response = await client.update_job(job_id, arguments["updates"])
            message = f"Updated job '{job_id}'"
            updated_fields = list(arguments["updates"].keys())
        elif operation == "pause":
            response = await client.update_job(job_id, {"status": "paused"})
            message = f"Paused job '{job_id}'"
            updated_fields = ["status"]
        elif operation == "resume":
            response = await client.update_job(job_id, {"status": "scheduled"})
            message = f"Resumed job '{job_id}'"
            updated_fields = ["status"]
        else:  # cancel
            await client.delete_job(job_id)
            return {
                "success": True,
                "job_id": job_id,
                "operation": "cancel",
                "message": f"Cancelled (deleted) job '{job_id}'",
            }

        return {
            "success": True,
            "job_id": job_id,
            "operation": operation,
            "message": message,
            "updated_fields": updated_fields,
        }

    except SchedulerClientError as e:
        return {"success": False, "error": "SchedulerServiceError", "message": str(e)}
    except Exception as e:
        return {"success": False, "error": "UnexpectedError", "message": str(e)}


def create_server() -> Server:
    """Create MCP server with manual tool schemas."""
    from mcp.server import Server as MCPServer
    from mcp.shared.exceptions import McpError
    import json

    server = MCPServer("scheduler-tools")

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        """Return the list of available tools."""
        return TOOL_SCHEMAS

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle tool calls."""
        try:
            if name == "schedule_reminder":
                result = await handle_schedule_reminder(arguments)
            elif name == "schedule_action":
                result = await handle_schedule_action(arguments)
            elif name == "list_scheduled_jobs":
                result = await handle_list_scheduled_jobs(arguments)
            elif name == "manage_scheduled_job":
                result = await handle_manage_scheduled_job(arguments)
            else:
                result = {"success": False, "error": "UnknownTool", "message": f"Unknown tool: {name}"}

            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as e:
            raise McpError(f"Tool execution failed: {e}")

    return server


async def health(_request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(
        {
            "status": "healthy",
            "service": settings.app_name,
            "scheduler_base_url": str(settings.scheduler_base_url),
        }
    )


def create_app() -> Starlette:
    """Create Starlette app with MCP server and HTTP transport."""
    server = create_server()

    # Create SSE transport
    from mcp.server.sse import SseServerTransport

    sse = SseServerTransport("/mcp")

    async def handle_sse(request: Request) -> Response:
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(
                streams[0], streams[1], server.create_initialization_options()
            )
        return Response()

    async def handle_messages(request: Request) -> Response:
        await sse.handle_post_message(request.scope, request.receive, request._send)
        return Response()

    routes = [
        Route("/mcp", endpoint=handle_sse, methods=["GET"]),
        Route("/mcp", endpoint=handle_messages, methods=["POST"]),
        Route("/health", endpoint=health, methods=["GET"]),
    ]

    app = Starlette(routes=routes)
    app.add_middleware(AgentIdentityMiddleware)

    return app

