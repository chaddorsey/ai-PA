"""Conversation model for storing chat history."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from pa_routing.models.base import Base


class Conversation(Base):
    """Stores individual messages in conversations."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'user' or 'assistant'
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )
