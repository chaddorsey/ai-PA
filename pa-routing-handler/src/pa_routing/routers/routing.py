"""Routing API endpoints."""

import time

import structlog
from fastapi import APIRouter, HTTPException

from pa_routing.models.requests import AgentSelectRequest, RouteRequest
from pa_routing.models.responses import AgentInfo, AgentListResponse, RouteResponse
from pa_routing.services.session_store import session_store
from pa_routing.settings import settings

logger = structlog.get_logger()

router = APIRouter(tags=["routing"])


@router.post("/route", response_model=RouteResponse)
async def route_message(request: RouteRequest) -> RouteResponse:
    """
    Route a message to the appropriate agent.

    Routing priority:
    1. Explicit agent_id in request
    2. Domain keyword matching (Phase 1)
    3. Default agent fallback
    """
    start_time = time.perf_counter()

    # Get or create session context
    user_id = request.user_id or str(request.session_id)
    session_ctx = session_store.get_or_create(user_id)

    # Routing decision
    if request.agent_id:
        # Explicit agent override
        agent_id = request.agent_id
        routing_method = "explicit"
        routing_reason = "Agent explicitly specified in request"
        confidence = 1.0
    else:
        # Default routing (Task 30-6 will add tiered routing)
        agent_id = settings.default_agent_id or "default"
        routing_method = "default"
        routing_reason = "No routing rules matched, using default agent"
        confidence = 0.5

    # Calculate processing time
    processing_time_ms = int((time.perf_counter() - start_time) * 1000)

    logger.info(
        "route_decision",
        session_id=str(request.session_id),
        agent_id=agent_id,
        routing_method=routing_method,
        processing_time_ms=processing_time_ms,
    )

    return RouteResponse(
        agent_id=agent_id,
        agent_name=agent_id,  # Will be resolved from Letta in Task 30-7
        routing_method=routing_method,
        routing_reason=routing_reason,
        confidence=confidence,
        processing_time_ms=processing_time_ms,
        session_context_entries=session_ctx.entry_count,
    )


@router.get("/agents", response_model=AgentListResponse)
async def list_agents() -> AgentListResponse:
    """
    List available agents for routing.

    Phase 1: Returns static list.
    Phase 2: Fetches from Letta API.
    """
    # Placeholder - Task 30-7 will fetch from Letta
    agents = [
        AgentInfo(
            id="default",
            name="Default Assistant",
            description="General-purpose assistant",
            keywords=["help", "general"],
        ),
    ]

    return AgentListResponse(agents=agents, count=len(agents))


@router.post("/agents/select")
async def select_agent(request: AgentSelectRequest) -> dict:
    """
    Manually select an agent for a session.

    Used when user explicitly wants to talk to a specific agent.
    """
    user_id = str(request.session_id)
    session_ctx = session_store.get_or_create(user_id)

    # Record the manual selection in context
    session_ctx.append(
        agent="user",
        action=f"Manually selected agent: {request.agent_id}"
        + (f" ({request.reason})" if request.reason else ""),
    )

    logger.info(
        "agent_selected",
        session_id=str(request.session_id),
        agent_id=request.agent_id,
        reason=request.reason,
    )

    return {
        "status": "ok",
        "agent_id": request.agent_id,
        "session_context_entries": session_ctx.entry_count,
    }


@router.delete("/sessions/{session_id}/context")
async def clear_session_context(session_id: str) -> dict:
    """Clear the session context for a user."""
    session_store.clear(session_id)

    logger.info("session_context_cleared", session_id=session_id)

    return {"status": "ok", "session_id": session_id}
