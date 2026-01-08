"""Session model for tracking user sessions."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pa_routing.models.base import Base


class Session(Base):
    """Tracks user sessions and preferences."""

    __tablename__ = "sessions"

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    current_agent_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    preferences: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    last_activity: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
