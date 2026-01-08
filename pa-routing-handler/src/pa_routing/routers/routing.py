"""Routing API endpoints."""

import time
from datetime import datetime

import structlog
from fastapi import APIRouter

from pa_routing.database import get_db_session
from pa_routing.models.requests import AgentSelectRequest, RouteRequest
from pa_routing.models.responses import AgentInfo, AgentListResponse, RouteResponse
from pa_routing.models.routing_decision import RoutingDecision
from pa_routing.services.agent_selector import (
    AGENT_MAP,
    AGENT_NAMES,
    TieredAgentSelector,
)
from pa_routing.services.session_store import session_store
from pa_routing.settings import settings

logger = structlog.get_logger()

router = APIRouter(tags=["routing"])

# Initialize tiered agent selector
_selector = TieredAgentSelector()


@router.post("/route", response_model=RouteResponse)
async def route_message(request: RouteRequest) -> RouteResponse:
    """
    Route a message to the appropriate agent.

    Routing priority (tiered):
    1. Explicit agent_id in request (confidence: 1.0)
    2. Domain keyword matching (confidence: 0.9)
    3. Action keyword matching (confidence: 0.7)
    4. [Phase 1.5] Semantic embedding (confidence: 0.6-0.8)
    5. Default fallback (confidence: 0.5)
    """
    start_time = time.perf_counter()

    # Get or create session context
    user_id = request.user_id or str(request.session_id)
    session_ctx = session_store.get_or_create(user_id)

    # Use tiered agent selector
    result = _selector.select_detailed(request.message, request.agent_id)

    # Calculate processing time
    processing_time_ms = int((time.perf_counter() - start_time) * 1000)

    # Determine routing method from tier
    tier_methods = {
        1: "explicit",
        2: "domain_keyword",
        3: "action_keyword",
        4: "semantic",
        5: "default",
    }
    routing_method = tier_methods.get(result.tier, "unknown")

    # Log routing decision to database (async, non-blocking)
    try:
        async with get_db_session() as session:
            decision = RoutingDecision(
                session_id=request.session_id,
                message_preview=request.message[:255] if request.message else None,
                selected_agent_id=result.agent_id,
                routing_method=routing_method,
                routing_confidence=result.confidence,
                processing_time_ms=processing_time_ms,
                created_at=datetime.utcnow(),
            )
            session.add(decision)
    except Exception as e:
        logger.warning("routing_decision_log_failed", error=str(e))

    logger.info(
        "route_decision",
        session_id=str(request.session_id),
        agent_id=result.agent_id,
        agent_name=result.agent_name,
        routing_method=routing_method,
        tier=result.tier,
        confidence=result.confidence,
        processing_time_ms=processing_time_ms,
    )

    return RouteResponse(
        agent_id=result.agent_id,
        agent_name=result.agent_name,
        routing_method=routing_method,
        routing_reason=result.reason,
        confidence=result.confidence,
        processing_time_ms=processing_time_ms,
        session_context_entries=session_ctx.entry_count,
    )


@router.get("/agents", response_model=AgentListResponse)
async def list_agents() -> AgentListResponse:
    """
    List available agents for routing.

    Phase 1: Returns from AGENT_MAP.
    Phase 2: Fetches from Letta API.
    """
    agents = [
        AgentInfo(
            id=agent_id,
            name=AGENT_NAMES.get(domain, domain),
            description=f"{AGENT_NAMES.get(domain, domain)} for {domain} tasks",
            keywords=[domain],
        )
        for domain, agent_id in AGENT_MAP.items()
    ]

    # Add default agent
    agents.append(
        AgentInfo(
            id=settings.default_agent_id or "default",
            name="Main Agent",
            description="General-purpose assistant",
            keywords=["help", "general"],
        )
    )

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
