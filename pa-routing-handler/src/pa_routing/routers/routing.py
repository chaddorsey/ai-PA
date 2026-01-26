"""Routing API endpoints."""

import asyncio
import os
import time
from datetime import datetime
from typing import Optional

import httpx
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
    DEFAULT_AGENT_ID,
    TieredAgentSelector,
)
from pa_routing.services.letta_client import LettaClient
from pa_routing.services.session_store import session_store
from pa_routing.services.summary_parser import (
    clean_response_for_user,
    extract_summary,
    extract_summary_with_topics,
)
from pa_routing.settings import settings

logger = structlog.get_logger()

router = APIRouter(tags=["routing"])

# Initialize tiered agent selector
_selector = TieredAgentSelector()

# Initialize Letta client for archival operations (Patterns 3 & 4)
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
_letta_client = LettaClient(LETTA_BASE_URL)

# Main agent ID for archival writes
MAIN_AGENT_ID = settings.default_agent_id or DEFAULT_AGENT_ID

# Identity cache (simple in-memory cache for identities list)
_identities_cache: Optional[list[dict]] = None


async def _fetch_identities() -> list[dict]:
    """Fetch all identities from Letta API with simple caching."""
    global _identities_cache
    if _identities_cache is not None:
        return _identities_cache

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.get(f"{LETTA_BASE_URL}/v1/identities/")
            response.raise_for_status()
            _identities_cache = response.json()
            logger.info("identities_cache_populated", count=len(_identities_cache))
            return _identities_cache
    except Exception as e:
        logger.warning("identities_fetch_failed", error=str(e))
        return []


async def resolve_identity(
    platform: Optional[str],
    platform_id: Optional[str],
    default_identity_id: Optional[str]
) -> Optional[str]:
    """
    Resolve identity from platform credentials or fall back to default.

    For multi-modality support, looks up identity by platform-specific property
    (e.g., telegram_id, slack_id). Falls back to default_identity_id for
    single-user mode (web UI without platform context).

    Args:
        platform: Platform name ("telegram", "slack", "web", etc.)
        platform_id: Platform-specific user ID
        default_identity_id: Fallback identity for single-user mode

    Returns:
        Resolved identity_id or None if resolution fails
    """
    # Multi-modality: resolve via platform-specific property
    if platform and platform_id:
        property_key = f"{platform}_id"
        identities = await _fetch_identities()

        for identity in identities:
            properties = identity.get("properties", []) or []
            for prop in properties:
                if prop.get("key") == property_key and prop.get("value") == platform_id:
                    identity_id = identity.get("id")
                    logger.info(
                        "identity_resolved",
                        platform=platform,
                        platform_id=platform_id,
                        identity_id=identity_id
                    )
                    return identity_id

        logger.warning(
            "identity_not_found",
            platform=platform,
            platform_id=platform_id,
            property_key=property_key
        )

    # Single-user fallback (web UI, etc.)
    if default_identity_id:
        logger.debug("using_default_identity", identity_id=default_identity_id)
        return default_identity_id

    return None


def invalidate_identities_cache() -> None:
    """Clear the identities cache (call after creating/modifying identities)."""
    global _identities_cache
    _identities_cache = None
    logger.info("identities_cache_invalidated")


# Supabase client for conversation lookups (set during app startup)
_supabase_client = None


def set_supabase_client(client) -> None:
    """Set Supabase client for conversation lookups (called during app startup)."""
    global _supabase_client
    _supabase_client = client
    logger.info("routing_supabase_configured")


async def lookup_conversation(
    identity_id: str,
    agent_id: str,
    user_source: str = "web"
) -> Optional[str]:
    """
    Look up existing conversation for identity + agent pair.

    Uses the user_conversations table in Supabase to find existing
    conversation mappings. Returns None if no conversation exists.

    Args:
        identity_id: Letta identity ID for the user
        agent_id: Agent ID to find conversation for
        user_source: Platform source (web, slack, telegram, etc.)

    Returns:
        Conversation ID if found, None otherwise
    """
    if not _supabase_client:
        logger.debug("conversation_lookup_skipped", reason="no_supabase_client")
        return None

    try:
        result = (
            _supabase_client.table("user_conversations")
            .select("conversation_id")
            .eq("identity_id", identity_id)
            .eq("agent_id", agent_id)
            .execute()
        )
        if result.data:
            conversation_id = result.data[0]["conversation_id"]
            logger.info(
                "conversation_found",
                identity_id=identity_id,
                agent_id=agent_id,
                conversation_id=conversation_id
            )
            return conversation_id

        logger.debug(
            "conversation_not_found",
            identity_id=identity_id,
            agent_id=agent_id
        )
        return None

    except Exception as e:
        logger.warning(
            "conversation_lookup_failed",
            identity_id=identity_id,
            agent_id=agent_id,
            error=str(e)
        )
        return None


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

    # Resolve identity from platform credentials or use default
    identity_id = await resolve_identity(
        platform=request.platform,
        platform_id=request.platform_id,
        default_identity_id=settings.default_identity_id
    )

    # Get or create session context (keyed by identity_id when available)
    session_key = identity_id or request.user_id or str(request.session_id)
    session_ctx = session_store.get_or_create(session_key)

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

    # Look up existing conversation for this identity + agent pair
    conversation_id = None
    if identity_id:
        conversation_id = await lookup_conversation(
            identity_id=identity_id,
            agent_id=result.agent_id,
            user_source=request.platform or "web"
        )

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

    # Format session context for injection (Pattern 2)
    context_injection = session_ctx.format_for_injection()

    # Pattern 4: Briefing injection for main agent only
    briefing_injection = None
    is_main_agent = result.agent_id == MAIN_AGENT_ID
    if is_main_agent:
        try:
            # Query today's session passages
            today = datetime.utcnow().strftime("%Y-%m-%d")
            passages = await _letta_client.list_passages(
                agent_id=MAIN_AGENT_ID,
                tags=[f"session:{today}"],
                limit=5,
            )
            briefing_injection = _letta_client.format_briefing(passages)
        except Exception as e:
            logger.warning("briefing_injection_failed", error=str(e))

    logger.info(
        "route_decision",
        session_id=str(request.session_id),
        identity_id=identity_id,
        conversation_id=conversation_id,
        agent_id=result.agent_id,
        agent_name=result.agent_name,
        routing_method=routing_method,
        tier=result.tier,
        confidence=result.confidence,
        processing_time_ms=processing_time_ms,
        context_entries=session_ctx.entry_count,
        has_briefing=bool(briefing_injection),
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
        context_injection=context_injection if context_injection else None,
        briefing_injection=briefing_injection if briefing_injection else None,
        identity_id=identity_id,
        conversation_id=conversation_id,
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
    user_message: str = "",
    report_refs_json: str = "",
) -> dict:
    """
    Mark a thread as complete.

    Called when an agent finishes responding. Updates the last-responding
    agent for contextual routing, extracts SUMMARY for cross-agent awareness,
    and writes to Main Agent's archival for sub-agents (Pattern 3).

    Args:
        report_refs_json: JSON string from report_refs tool call, e.g.:
            '{"ref_type": "calendar_event", "ref_id": "abc123", "title": "Standup"}'
    """
    import json as json_module

    session_ctx = session_store.get(session_id)
    if not session_ctx:
        return {"error": "Session not found", "thread": None}

    # Extract summary with topics from response (Pattern 2)
    # Priority: SUMMARY line > tool name > truncated first line
    parsed = extract_summary_with_topics(response_content, agent_name, tool_calls)
    summary = parsed.text
    topics = parsed.topics
    cleaned_response = clean_response_for_user(response_content)

    # Get refs from report_refs tool call (preferred) or text parsing (fallback)
    refs = {}
    if report_refs_json:
        try:
            tool_refs = json_module.loads(report_refs_json)
            # Normalize to our refs format: {ref_type: ref_id, title: ..., ...}
            refs = {
                "type": tool_refs.get("ref_type", "unknown"),
                "id": tool_refs.get("ref_id", ""),
                "title": tool_refs.get("title", ""),
            }
            # Include any metadata
            if tool_refs.get("metadata"):
                refs.update(tool_refs["metadata"])
            logger.info("refs_from_tool_call", refs=refs)
        except json_module.JSONDecodeError:
            logger.warning("invalid_report_refs_json", raw=report_refs_json[:100])

    # Fallback to text-parsed refs if no tool refs
    if not refs and parsed.refs:
        refs = parsed.refs

    # Append to session context for cross-agent awareness (includes refs for follow-ups)
    session_ctx.append(agent=agent_name, action=summary, refs=refs if refs else None)

    # Pattern 3: Write to Main Agent's archival for sub-agents (fire-and-forget)
    is_sub_agent = agent_id != MAIN_AGENT_ID
    if is_sub_agent and response_content:
        # Build passage text (include refs if present for searchability)
        user_preview = user_message[:80] if user_message else "request"
        passage_text = f"User asked {agent_name}: {user_preview}. Action: {summary}"
        if refs:
            # Append refs as searchable text (e.g., "Refs: eventId=abc123, title=Standup")
            ref_str = ", ".join(f"{k}={v}" for k, v in refs.items())
            passage_text += f" Refs: {ref_str}"

        # Build tags
        tags = _letta_client.build_session_tags(
            agent_name=agent_name,
            topics=topics,
            user_id=session_id,  # Using session_id as user identifier
        )

        # Fire-and-forget archival write
        asyncio.create_task(
            _letta_client.create_passage(
                agent_id=MAIN_AGENT_ID,
                text=passage_text,
                tags=tags,
            )
        )

        logger.info(
            "archival_write_scheduled",
            session_id=session_id,
            agent_name=agent_name,
            topics=topics,
        )

    # Complete the thread with the original response (caller may use cleaned version)
    thread = session_ctx.complete_thread(request_id, agent_id, agent_name, response_content)
    if not thread:
        return {"error": "Thread not found", "thread": None}

    # Persist session state (fire-and-forget, non-blocking)
    session_store.persist_async(session_id, session_ctx)

    logger.info(
        "thread_completed",
        session_id=session_id,
        request_id=request_id,
        agent_id=agent_id,
        agent_name=agent_name,
        summary=summary,
        topics=topics,
        has_refs=bool(refs),
    )

    return {
        "status": "ok",
        "thread": thread.to_dict(),
        "last_responding_agent_id": session_ctx.last_responding_agent_id,
        "last_responding_agent_name": session_ctx.last_responding_agent_name,
        "summary": summary,
        "topics": topics,
        "refs": refs,
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
