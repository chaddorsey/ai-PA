"""Scheduler MCP server with simple HTTP JSON-RPC (Letta-compatible)."""

from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from scheduler_mcp.client import SchedulerClient, SchedulerClientError
from scheduler_mcp.settings import settings

logger = logging.getLogger(__name__)

# Context variable to hold the current agent ID
current_agent_id: ContextVar[Optional[str]] = ContextVar("current_agent_id", default=None)


class AgentIdentityMiddleware(BaseHTTPMiddleware):
    """Middleware to extract agent identity from headers or query parameters."""

    async def dispatch(self, request: Request, call_next):
        agent_id = request.headers.get("X-Agent-ID") or request.query_params.get("agent_id")
        if agent_id:
            current_agent_id.set(agent_id)
        response = await call_next(request)
        return response


# Define tool schemas in JSON Schema format (matching working servers)
CALENDLY_STYLE_TOOLS = [
    {
        "name": "schedule_reminder",
        "description": "Schedule a message/reminder to be delivered to an agent at a specific time. Use this for reminders, prompts, or scheduled notifications.",
        "inputSchema": {
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
                    "description": "Agent to receive the reminder. Defaults to the requesting agent.",
                },
                "category": {
                    "type": "string",
                    "description": "Category for organization (e.g., 'daily_routine', 'meeting_prep')",
                },
            },
            "required": ["message", "when", "title"],
        },
    },
    {
        "name": "schedule_action",
        "description": "Schedule a script or HTTP/API call to run at a specific time. Use for automated tasks like data scraping, backups, API triggers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "enum": ["script", "http"],
                    "description": "Type of action: 'script' to run a file, 'http' to make an API call",
                },
                "target": {
                    "type": "string",
                    "description": "For 'script': filename in /app/scripts/. For 'http': full URL",
                },
                "when": {
                    "type": "string",
                    "description": "When to run (Eastern Time). Examples: 'every day at 2am', 'every hour'",
                },
                "title": {
                    "type": "string",
                    "description": "Short title for this action",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    "description": "HTTP method (only for action_type='http'). Defaults to POST.",
                },
                "body": {
                    "type": "object",
                    "description": "JSON body for HTTP requests (only for action_type='http')",
                },
            },
            "required": ["action_type", "target", "when", "title"],
        },
    },
    {
        "name": "list_scheduled_jobs",
        "description": "List scheduled jobs with filtering. Times shown in Eastern Time by default.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "created_by": {
                    "type": "string",
                    "description": "Filter by creator. Use 'me' for your own jobs.",
                },
                "status": {
                    "type": "string",
                    "enum": ["scheduled", "paused", "cancelled"],
                    "description": "Filter by job status",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum jobs to return (default 20, max 100)",
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": [],
        },
    },
    {
        "name": "manage_scheduled_job",
        "description": "Update, pause, resume, or cancel an existing scheduled job.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "ID of the job to manage",
                },
                "operation": {
                    "type": "string",
                    "enum": ["update", "pause", "resume", "cancel"],
                    "description": "'update' to modify, 'pause'/'resume' to control, 'cancel' to delete",
                },
                "updates": {
                    "type": "object",
                    "description": "Fields to update (only for operation='update')",
                },
            },
            "required": ["job_id", "operation"],
        },
    },
]


async def handle_mcp_request(method: str, params: Any) -> Dict[str, Any]:
    """Handle MCP JSON-RPC requests."""
    
    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "scheduler-tools",
                "version": "1.0.0"
            }
        }
    
    elif method == "tools/list":
        return {"tools": CALENDLY_STYLE_TOOLS}
    
    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        try:
            if tool_name == "schedule_reminder":
                result = await handle_schedule_reminder(arguments)
            elif tool_name == "schedule_action":
                result = await handle_schedule_action(arguments)
            elif tool_name == "list_scheduled_jobs":
                result = await handle_list_jobs(arguments)
            elif tool_name == "manage_scheduled_job":
                result = await handle_manage_job(arguments)
            else:
                raise ValueError(f"Unknown tool: {tool_name}")
            
            # Return in MCP format
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2)
                    }
                ]
            }
        
        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            raise ValueError(f"Tool execution failed: {e}")
    
    else:
        raise ValueError(f"Unknown method: {method}")


async def handle_schedule_reminder(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle schedule_reminder tool."""
    try:
        client = SchedulerClient(base_url=settings.scheduler_base_url, api_key=settings.api_key)
        
        # Parse natural language schedule
        when = arguments["when"]
        timezone = arguments.get("timezone", "America/New_York")
        
        # Get current agent ID from context
        current_agent = current_agent_id.get() or "system"
        
        # Resolve agent_id - use provided agent_id, or default to current agent
        # Also resolve "self" or "me" to current agent
        provided_agent_id = arguments.get("agent_id")
        if provided_agent_id and provided_agent_id.lower() in ["self", "me"]:
            agent_id = current_agent
        elif provided_agent_id:
            agent_id = provided_agent_id
        else:
            agent_id = current_agent
        
        # Call scheduler-service endpoint that will parse the schedule
        # We'll send the natural language "when" and let the backend parse it
        job_data = {
            "title": arguments["title"],
            "description": f"Reminder: {arguments['message']}",
            "created_by": agent_id,
            "category": arguments.get("category"),
            "schedule": {
                "type": "natural",  # Signal to backend to parse
                "expression": when,
                "timezone": timezone,
            },
            "actions": [
                {
                    "action_type": "agent_message",
                    "config": {
                        "agent_id": agent_id,
                        "message": arguments["message"],
                        "category": arguments.get("category"),
                    },
                }
            ],
        }
        
        response = await client.create_job(job_data)
        
        return {
            "success": True,
            "job_id": response["job_id"],
            "message": f"Scheduled '{arguments['title']}' for {when}",
            "next_run_at": response.get("next_run_at"),
        }
    
    except SchedulerClientError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"Failed to schedule reminder: {e}", exc_info=True)
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


async def handle_schedule_action(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle schedule_action tool."""
    try:
        client = SchedulerClient(base_url=settings.scheduler_base_url, api_key=settings.api_key)
        
        job_data = {
            "title": arguments["title"],
            "description": f"{arguments['action_type'].upper()} action: {arguments['target']}",
            "created_by": "system",
            "schedule": {
                "type": "one_off",
                "expression": {"run_at": "2025-10-14T12:00:00Z"}  # Placeholder
            },
        }
        
        response = await client.create_job(job_data)
        
        return {
            "success": True,
            "job_id": response["job_id"],
            "message": f"Scheduled '{arguments['title']}'",
        }
    
    except SchedulerClientError as e:
        return {"success": False, "error": str(e)}


async def handle_list_jobs(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle list_scheduled_jobs tool."""
    try:
        client = SchedulerClient(base_url=settings.scheduler_base_url, api_key=settings.api_key)
        
        # Extract filter parameters
        status_filter = arguments.get("status")
        created_by_filter = arguments.get("created_by")
        category_filter = arguments.get("category")
        
        # Resolve "me"/"self" aliases for created_by
        if created_by_filter and created_by_filter.lower() in ["me", "self"]:
            # Get agent ID from context (if available)
            created_by_filter = current_agent_id.get() or "system"
        
        jobs = await client.list_jobs(
            status_filter=status_filter,
            created_by_filter=created_by_filter,
            category_filter=category_filter,
        )
        
        # Apply limit if specified
        limit = arguments.get("limit", 20)
        jobs_list = jobs if isinstance(jobs, list) else []
        
        return {
            "success": True,
            "count": len(jobs_list),
            "jobs": jobs_list[:limit],
        }
    
    except SchedulerClientError as e:
        return {"success": False, "error": str(e)}


async def handle_manage_job(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle manage_scheduled_job tool."""
    try:
        client = SchedulerClient(base_url=settings.scheduler_base_url, api_key=settings.api_key)
        
        operation = arguments["operation"]
        job_id = arguments["job_id"]
        
        if operation == "cancel":
            await client.delete_job(job_id)
            return {"success": True, "message": f"Cancelled job {job_id}"}
        else:
            updates = arguments.get("updates", {})
            if operation == "pause":
                updates["status"] = "paused"
            elif operation == "resume":
                updates["status"] = "scheduled"
            
            await client.update_job(job_id, updates)
            return {"success": True, "message": f"{operation.title()}d job {job_id}"}
    
    except SchedulerClientError as e:
        return {"success": False, "error": str(e)}


def create_app() -> FastAPI:
    """Create FastAPI app with simple HTTP JSON-RPC endpoint."""
    
    app = FastAPI(
        title="scheduler-tools",
        description="HTTP Streamable transport for scheduler service",
        version="1.0.0",
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add agent identity middleware
    app.add_middleware(AgentIdentityMiddleware)
    
    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "scheduler-tools",
            "version": "1.0.0",
            "scheduler_base_url": str(settings.scheduler_base_url),
        }
    
    @app.post("/mcp")
    async def mcp_endpoint(request: Request, response: Response):
        """Main MCP endpoint for HTTP Streamable transport."""
        try:
            # Handle session ID (required for Letta)
            session_id = request.headers.get("mcp-session-id")
            if not session_id:
                session_id = str(uuid.uuid4())
                logger.debug(f"Generated new session ID: {session_id}")
            
            response.headers["mcp-session-id"] = session_id
            
            # Parse JSON-RPC request
            body = await request.body()
            try:
                rpc_request = json.loads(body.decode('utf-8'))
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
                raise HTTPException(status_code=400, detail="Invalid JSON")
            
            method = rpc_request.get("method", "")
            params = rpc_request.get("params")
            request_id = rpc_request.get("id")
            
            logger.info(f"[{session_id}] Request: method={method}, id={request_id}")
            
            # Handle the request
            try:
                result = await handle_mcp_request(method, params)
                
                rpc_response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": result
                }
                
                logger.info(f"[{session_id}] Success: method={method}")
                return rpc_response
            
            except ValueError as e:
                logger.error(f"[{session_id}] Error: {e}")
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": str(e)
                    }
                }
            
            except Exception as e:
                logger.error(f"[{session_id}] Unexpected error: {e}", exc_info=True)
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {str(e)}"
                    }
                }
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    
    return app

