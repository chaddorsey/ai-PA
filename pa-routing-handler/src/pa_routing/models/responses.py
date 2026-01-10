"""Pydantic response models for the routing API."""

from typing import Optional

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
