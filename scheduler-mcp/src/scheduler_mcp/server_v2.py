"""Updated scheduler MCP server with LLM-friendly tools and agent identity."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Dict

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from scheduler_mcp.client import SchedulerClient, SchedulerClientError
from scheduler_mcp.errors import (
    invalid_parameter_combination_error,
    invalid_operation_for_parameter_error,
    missing_required_parameter_error,
)
from scheduler_mcp.settings import settings
from scheduler_mcp.tools_v2 import (
    ListScheduledJobsParams,
    ManageScheduledJobParams,
    ScheduleActionParams,
    ScheduleAdvancedParams,
    ScheduleReminderParams,
)

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


def resolve_filter_aliases(filters: Dict[str, Any], current_agent: str) -> Dict[str, Any]:
    """Resolve 'me' and 'self' aliases to actual agent ID."""
    if filters.get("created_by") in ["me", "self"]:
        filters["created_by"] = current_agent
    return filters


async def _get_client() -> SchedulerClient:
    """Get scheduler service client."""
    return SchedulerClient(base_url=settings.scheduler_base_url, api_key=settings.api_key)


def create_mcp_server() -> FastMCP:
    """Create MCP server with updated LLM-friendly tools."""
    mcp = FastMCP("scheduler-tools")

    # =============================================================================
    # Tool 1: schedule_reminder
    # =============================================================================

    @mcp.tool(
        description=(
            "Schedule a message/reminder to be delivered to an agent at a specific time via REST API POST. "
            "Use this for reminders, prompts, or scheduled notifications to agents."
        )
    )
    async def schedule_reminder(params: ScheduleReminderParams) -> Dict[str, Any]:
        """Schedule an agent message/reminder."""
        try:
            client = await _get_client()
            creator = get_current_agent()
            recipient = params.agent_id or creator

            # Build job data for backend
            job_data = {
                "title": params.title,
                "description": f"Reminder: {params.message}",
                "created_by": creator,
                "schedule": {
                    "type": "natural",  # Will be parsed by backend
                    "expression": params.when,
                    "timezone": params.timezone or "America/New_York",
                },
                "actions": [
                    {
                        "action_type": "agent_message",
                        "config": {
                            "agent_id": recipient,
                            "message": params.message,
                            "category": params.category,
                        },
                    }
                ],
            }

            # Add category as metadata if provided
            if params.category:
                job_data["metadata"] = [{"key": "category", "value": {"category": params.category}}]

            response = await client.create_job(job_data)

            return {
                "success": True,
                "job_id": response["job_id"],
                "message": f"Scheduled '{params.title}' to run {params.when}",
                "next_run_at": response.get("next_run_at"),
                "created_by": creator,
                "recipient": recipient,
            }

        except SchedulerClientError as e:
            return {"success": False, "error": "SchedulerServiceError", "message": str(e)}
        except Exception as e:
            return {"success": False, "error": "UnexpectedError", "message": str(e)}

    # =============================================================================
    # Tool 2: schedule_action
    # =============================================================================

    @mcp.tool(
        description=(
            "Schedule a script or HTTP/API call to run at a specific time. "
            "Use this for automated tasks like data scraping, backups, API triggers, etc."
        )
    )
    async def schedule_action(params: ScheduleActionParams) -> Dict[str, Any]:
        """Schedule a script or HTTP action."""
        try:
            # Validate action_type
            if params.action_type not in ["script", "http"]:
                return {
                    "success": False,
                    "error": "InvalidActionType",
                    "message": f"action_type must be 'script' or 'http', got '{params.action_type}'",
                }

            # Validate parameter combinations
            if params.action_type == "script":
                if params.body is not None:
                    raise invalid_parameter_combination_error("body", "script", params.target)
                if params.method is not None:
                    raise invalid_parameter_combination_error("method", "script", params.target)
                if params.headers is not None:
                    raise invalid_parameter_combination_error("headers", "script", params.target)

            client = await _get_client()
            creator = get_current_agent()

            # Build action config based on type
            if params.action_type == "script":
                action_config = {
                    "action_type": "script",
                    "config": {
                        "script_path": params.target,
                        "args": params.args or [],
                        "timeout_seconds": (params.timeout_minutes or 5) * 60,
                    },
                }
            else:  # http
                action_config = {
                    "action_type": "http",
                    "config": {
                        "url": params.target,
                        "method": params.method or "POST",
                        "headers": params.headers or {},
                        "body": params.body or {},
                        "timeout_seconds": (params.timeout_minutes or 1) * 60,
                    },
                }

            # Build job data
            job_data = {
                "title": params.title,
                "description": params.description or f"{params.action_type.upper()} action: {params.target}",
                "created_by": creator,
                "schedule": {
                    "type": "natural",
                    "expression": params.when,
                    "timezone": params.timezone or "America/New_York",
                },
                "actions": [action_config],
            }

            response = await client.create_job(job_data)

            return {
                "success": True,
                "job_id": response["job_id"],
                "message": f"Scheduled '{params.title}' to run {params.when}",
                "next_run_at": response.get("next_run_at"),
                "created_by": creator,
            }

        except SchedulerClientError as e:
            return {"success": False, "error": "SchedulerServiceError", "message": str(e)}
        except Exception as e:
            if hasattr(e, "to_dict"):
                return e.to_dict()
            return {"success": False, "error": "UnexpectedError", "message": str(e)}

    # =============================================================================
    # Tool 3: schedule_advanced
    # =============================================================================

    @mcp.tool(
        description=(
            "Create a scheduled job with advanced options including multiple actions, custom metadata, "
            "and complex schedules. Use this when simple scheduling tools don't provide enough flexibility."
        )
    )
    async def schedule_advanced(params: ScheduleAdvancedParams) -> Dict[str, Any]:
        """Schedule with full control over all options."""
        try:
            client = await _get_client()
            creator = get_current_agent()

            # Build job data from advanced params
            job_data = {
                "title": params.title,
                "description": params.description,
                "created_by": creator,
                "schedule": {
                    "type": params.schedule.type,
                    "expression": params.schedule.expression,
                    "timezone": params.schedule.timezone or "America/New_York",
                },
                "actions": [action.model_dump() for action in params.actions],
                "metadata": params.metadata or {},
            }

            response = await client.create_job(job_data)

            return {
                "success": True,
                "job_id": response["job_id"],
                "message": f"Scheduled advanced job '{params.title}'",
                "next_run_at": response.get("next_run_at"),
                "created_by": creator,
                "enabled": params.enabled,
            }

        except SchedulerClientError as e:
            return {"success": False, "error": "SchedulerServiceError", "message": str(e)}
        except Exception as e:
            return {"success": False, "error": "UnexpectedError", "message": str(e)}

    # =============================================================================
    # Tool 4: list_scheduled_jobs
    # =============================================================================

    @mcp.tool(
        description=(
            "List scheduled jobs with filtering options. Times are shown in Eastern Time by default. "
            "Use filters to narrow results by creator, status, type, date range, or specific job ID."
        )
    )
    async def list_scheduled_jobs(params: ListScheduledJobsParams) -> Dict[str, Any]:
        """List jobs with structured filtering."""
        try:
            client = await _get_client()
            current_agent = get_current_agent()

            # Resolve filter aliases
            filters = params.filters.model_dump(exclude_none=True) if params.filters else {}
            filters = resolve_filter_aliases(filters, current_agent)

            # Query backend (backend will handle filtering and timezone display)
            query_params = {
                **filters,
                "limit": min(params.limit or 20, 100),
                "show_utc": params.show_utc,
            }

            jobs = await client.list_jobs(query_params)

            return {
                "success": True,
                "count": len(jobs),
                "timezone": "UTC" if params.show_utc else "America/New_York (ET)",
                "jobs": jobs,
            }

        except SchedulerClientError as e:
            return {"success": False, "error": "SchedulerServiceError", "message": str(e)}
        except Exception as e:
            return {"success": False, "error": "UnexpectedError", "message": str(e)}

    # =============================================================================
    # Tool 5: manage_scheduled_job
    # =============================================================================

    @mcp.tool(
        description=(
            "Update, pause, resume, or cancel an existing scheduled job. "
            "Use 'update' to modify job details, 'pause' to stop temporarily, "
            "'resume' to re-activate, or 'cancel' to delete permanently."
        )
    )
    async def manage_scheduled_job(params: ManageScheduledJobParams) -> Dict[str, Any]:
        """Manage (update/pause/resume/cancel) a scheduled job."""
        try:
            # Validate operation
            if params.operation not in ["update", "pause", "resume", "cancel"]:
                return {
                    "success": False,
                    "error": "InvalidOperation",
                    "message": f"operation must be one of: update, pause, resume, cancel. Got '{params.operation}'",
                }

            # Validate parameter requirements
            if params.operation == "update":
                if not params.updates:
                    raise missing_required_parameter_error("updates", {"operation": "update", "job_id": params.job_id})
            elif params.updates:
                raise invalid_operation_for_parameter_error(params.operation, "updates", params.job_id)

            client = await _get_client()

            # Execute operation
            if params.operation == "update":
                response = await client.update_job(params.job_id, params.updates)
                message = f"Updated job '{params.job_id}'"
                updated_fields = list(params.updates.keys())
            elif params.operation == "pause":
                response = await client.update_job(params.job_id, {"status": "paused"})
                message = f"Paused job '{params.job_id}'"
                updated_fields = ["status"]
            elif params.operation == "resume":
                response = await client.update_job(params.job_id, {"status": "scheduled"})
                message = f"Resumed job '{params.job_id}'"
                updated_fields = ["status"]
            else:  # cancel
                await client.delete_job(params.job_id)
                return {
                    "success": True,
                    "job_id": params.job_id,
                    "operation": "cancel",
                    "message": f"Cancelled (deleted) job '{params.job_id}'",
                }

            return {
                "success": True,
                "job_id": params.job_id,
                "operation": params.operation,
                "message": message,
                "updated_fields": updated_fields,
            }

        except SchedulerClientError as e:
            return {"success": False, "error": "SchedulerServiceError", "message": str(e)}
        except Exception as e:
            if hasattr(e, "to_dict"):
                return e.to_dict()
            return {"success": False, "error": "UnexpectedError", "message": str(e)}

    # Add health endpoint using custom route
    @mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "healthy",
                "service": settings.app_name,
                "scheduler_base_url": str(settings.scheduler_base_url),
            }
        )

    return mcp


def create_app():
    """Create Starlette app with MCP server and agent identity middleware."""
    server = create_mcp_server()
    app = server.streamable_http_app()

    # Add agent identity extraction middleware
    app.add_middleware(AgentIdentityMiddleware)

    return app

