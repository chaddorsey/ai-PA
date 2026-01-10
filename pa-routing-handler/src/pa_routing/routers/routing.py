"""Routing API endpoints."""

import time
from datetime import datetime

import structlog
from fastapi import APIRouter, Query

from pa_routing.database import get_db_session
from pa_routing.models.requests import AgentSelectRequest, RouteRequest
from pa_routing.models.responses import AgentInfo, AgentListResponse, RouteResponse
from pa_routing.models.routing_decision import RoutingDecision
from pa_routing.services.agent_selector import (
    AGENT_MAP,
    AGENT_NAMES,
    ContextInfo,
    TieredAgentSelector,
)
from pa_routing.services.session_store import session_store
from pa_routing.services.summary_parser import clean_response_for_user, extract_summary
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
    4. Contextual follow-up to previous agent (confidence: 0.75)
    5. [Phase 1.5] Semantic embedding (confidence: 0.6-0.8)
    6. Default fallback (confidence: 0.5)
    """
    start_time = time.perf_counter()

    # Get or create session context
    user_id = request.user_id or str(request.session_id)
    session_ctx = session_store.get_or_create(user_id)

    # Create or get thread for this request
    thread = None
    if request.request_id:
        thread = session_ctx.get_thread(request.request_id)
    if not thread:
        thread = session_ctx.create_thread(request.message, request.request_id)

    # Build context for contextual routing
    context = None
    if session_ctx.last_responding_agent_id:
        context = ContextInfo(
            last_agent_id=session_ctx.last_responding_agent_id,
            last_agent_name=session_ctx.last_responding_agent_name,
        )

    # Use tiered agent selector with context
    result = _selector.select_detailed(request.message, request.agent_id, context)

    # Calculate processing time
    processing_time_ms = int((time.perf_counter() - start_time) * 1000)

    # Determine routing method from tier
    tier_methods = {
        1: "explicit",
        2: "domain_keyword",
        3: "action_keyword",
        4: "contextual",
        5: "semantic",
        6: "default",
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
        request_id=thread.request_id if thread else None,
    )


@router.get("/agents", response_model=AgentListResponse)
async def list_agents() -> AgentListResponse:
    """
    List available agents for routing.

    Phase 1: Returns from AGENT_MAP.
    Phase 2: Fetches from Letta API.
    """
    from pa_routing.services.agent_selector import DEFAULT_AGENT_ID

    # Start with auto-route option (empty ID lets routing decide)
    agents = [
        AgentInfo(
            id="",
            name="Auto (Recommended)",
            description="Automatically route to the best agent based on your message",
            keywords=["auto", "smart"],
        )
    ]

    # Add Main Agent with correct ID
    agents.append(
        AgentInfo(
            id=settings.default_agent_id or DEFAULT_AGENT_ID,
            name="Main Agent",
            description="General-purpose assistant",
            keywords=["help", "general"],
        )
    )

    # Add unique agents from AGENT_MAP (avoid duplicates like Pulse)
    seen_ids = {agents[1].id}  # Main agent ID already added
    for domain, agent_id in AGENT_MAP.items():
        if agent_id not in seen_ids:
            agents.append(
                AgentInfo(
                    id=agent_id,
                    name=AGENT_NAMES.get(domain, domain),
                    description=f"{AGENT_NAMES.get(domain, domain)} for {domain} tasks",
                    keywords=[domain],
                )
            )
            seen_ids.add(agent_id)

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


# ========== Thread Management Endpoints ==========


@router.get("/sessions/{session_id}/threads")
async def get_session_threads(session_id: str, limit: int = 10) -> dict:
    """
    Get recent conversation threads for a session.

    Returns threads ordered by creation time (newest last).
    """
    session_ctx = session_store.get(session_id)
    if not session_ctx:
        return {"threads": [], "count": 0}

    threads = session_ctx.get_recent_threads(limit=limit)
    return {
        "threads": threads,
        "count": len(threads),
        "last_responding_agent_id": session_ctx.last_responding_agent_id,
        "last_responding_agent_name": session_ctx.last_responding_agent_name,
    }


@router.get("/sessions/{session_id}/threads/{request_id}")
async def get_thread(session_id: str, request_id: str) -> dict:
    """Get a specific thread by request ID."""
    session_ctx = session_store.get(session_id)
    if not session_ctx:
        return {"error": "Session not found", "thread": None}

    thread = session_ctx.get_thread(request_id)
    if not thread:
        return {"error": "Thread not found", "thread": None}

    return {"thread": thread.to_dict()}


@router.post("/sessions/{session_id}/threads")
async def create_thread(session_id: str, user_message: str, request_id: str = None) -> dict:
    """
    Create a new conversation thread.

    Called when a user sends a new message.
    """
    session_ctx = session_store.get_or_create(session_id)
    thread = session_ctx.create_thread(user_message, request_id)

    logger.info(
        "thread_created",
        session_id=session_id,
        request_id=thread.request_id,
        message_preview=user_message[:50] if user_message else None,
    )

    return {
        "status": "ok",
        "request_id": thread.request_id,
        "thread": thread.to_dict(),
    }


@router.post("/sessions/{session_id}/threads/{request_id}/complete")
async def complete_thread(
    session_id: str,
    request_id: str,
    agent_id: str,
    agent_name: str,
    response_content: str = "",
    tool_calls: list[str] = Query(default=None),
) -> dict:
    """
    Mark a thread as complete.

    Called when an agent finishes responding. Updates the last-responding
    agent for contextual routing and extracts SUMMARY for cross-agent awareness.
    """
    session_ctx = session_store.get(session_id)
    if not session_ctx:
        return {"error": "Session not found", "thread": None}

    # Extract summary from response for cross-agent context (Pattern 2)
    # Priority: SUMMARY line > tool name > truncated first line
    summary = extract_summary(response_content, agent_name, tool_calls)
    cleaned_response = clean_response_for_user(response_content)

    # Append to session context for cross-agent awareness
    session_ctx.append(agent=agent_name, action=summary)

    # Complete the thread with the original response (caller may use cleaned version)
    thread = session_ctx.complete_thread(request_id, agent_id, agent_name, response_content)
    if not thread:
        return {"error": "Thread not found", "thread": None}

    logger.info(
        "thread_completed",
        session_id=session_id,
        request_id=request_id,
        agent_id=agent_id,
        agent_name=agent_name,
        summary=summary,
    )

    return {
        "status": "ok",
        "thread": thread.to_dict(),
        "last_responding_agent_id": session_ctx.last_responding_agent_id,
        "last_responding_agent_name": session_ctx.last_responding_agent_name,
        "summary": summary,
        "cleaned_response": cleaned_response,
    }


@router.get("/sessions/{session_id}/context-agent")
async def get_contextual_agent(session_id: str) -> dict:
    """
    Get the agent that should handle contextual follow-ups.

    Used by the routing tier to determine if a brief message should
    go to the last-responding agent.
    """
    session_ctx = session_store.get(session_id)
    if not session_ctx:
        return {"has_context": False, "agent_id": None, "agent_name": None}

    context = session_ctx.get_contextual_agent()
    if not context:
        return {"has_context": False, "agent_id": None, "agent_name": None}

    agent_id, agent_name = context
    return {
        "has_context": True,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "last_response_time": session_ctx.last_response_time.isoformat() if session_ctx.last_response_time else None,
    }
