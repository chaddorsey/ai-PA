"""Pydantic request models for the routing API."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    """Request to route a message to an agent."""

    session_id: UUID
    message: str = Field(min_length=1)
    agent_id: Optional[str] = Field(default=None, description="Explicit agent ID override")
    user_id: Optional[str] = Field(default=None, description="User identifier for context")
    context: Optional[dict] = Field(default=None, description="Additional context")


class AgentSelectRequest(BaseModel):
    """Request to manually select an agent for a session."""

    session_id: UUID
    agent_id: str
    reason: Optional[str] = Field(default=None, description="Reason for manual selection")
