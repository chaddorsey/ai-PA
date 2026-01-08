"""Routing decision model for analytics."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pa_routing.models.base import Base


class RoutingDecision(Base):
    """Logs routing decisions for analytics and debugging."""

    __tablename__ = "routing_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    message_preview: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    selected_agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    routing_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    routing_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
