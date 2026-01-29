"""Pydantic response models for the routing API."""

from typing import Dict, List, Optional

from pydantic import BaseModel


class RouteResponse(BaseModel):
    """Response with routing decision."""

    agent_id: str
    agent_name: str
    routing_method: str
    routing_reason: str
    confidence: Optional[float] = None
    processing_time_ms: int
    session_context_entries: int = 0
    request_id: Optional[str] = None
    context_injection: Optional[str] = None  # Formatted session context to prepend to message
    briefing_injection: Optional[str] = None  # Pattern 4: Session briefing for main agent only
    # NEW: Identity and conversation resolution
    identity_id: Optional[str] = None  # Resolved Letta identity
    conversation_id: Optional[str] = None  # For caller to use with Letta


class AgentInfo(BaseModel):
    """Information about an available agent."""

    id: str
    name: str
    description: Optional[str] = None
    keywords: list[str] = []


class AgentListResponse(BaseModel):
    """Response with list of available agents."""

    agents: list[AgentInfo]
    count: int


class CoordinateResponse(BaseModel):
    """Response from multi-agent coordination."""

    status: str  # complete, partial, error
    task_id: str
    synthesis: Optional[str] = None
    findings: Optional[Dict[str, str]] = None
    agents_completed: List[str] = []
    agents_failed: List[str] = []
    agents_skipped: List[str] = []
    coordination_time_ms: Optional[int] = None
    error_message: Optional[str] = None
