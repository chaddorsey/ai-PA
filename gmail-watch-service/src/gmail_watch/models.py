"""SQLAlchemy models for Gmail Watch Service."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

from gmail_watch.database import Base

# Schema name for all tables
SCHEMA_NAME = "gmail_watch"


class WatchedThread(MappedAsDataclass, Base, kw_only=True):
    """Model for tracking watched Gmail threads."""

    __tablename__ = "watched_threads"
    __table_args__ = {"schema": SCHEMA_NAME}

    # Primary key - init=False means it's not required in __init__
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        init=False,
        default_factory=uuid.uuid4,
    )

    # Thread identification (required fields first in dataclass)
    thread_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    # Optional fields with defaults
    subject: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    original_recipients: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True, default=None
    )

    # Watch configuration
    watch_type: Mapped[str] = mapped_column(String(50), default="standard")
    followup_seconds: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None
    )
    source: Mapped[str] = mapped_column(String(50), default="manual")
    bcc_address: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )
    followup_due_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    followup_notified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Reply tracking
    reply_received: Mapped[bool] = mapped_column(Boolean, default=False)
    reply_received_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    reply_message_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )

    # Timestamps and activity
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        init=False,
        default=None,
    )
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    message_count: Mapped[int] = mapped_column(Integer, default=1)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Sender filtering
    ignore_own_replies: Mapped[bool] = mapped_column(Boolean, default=True)
    external_only: Mapped[bool] = mapped_column(Boolean, default=False)
    watch_for_senders: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True, default=None
    )

    # Extensible metadata (named extra_data to avoid SQLAlchemy reserved 'metadata')
    extra_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=None
    )

    def __repr__(self) -> str:
        return (
            f"<WatchedThread(thread_id={self.thread_id!r}, "
            f"subject={self.subject!r})>"
        )


class SyncState(MappedAsDataclass, Base, kw_only=True):
    """Model for tracking Gmail sync state (history ID, watch expiration, etc.)."""

    __tablename__ = "sync_state"
    __table_args__ = {"schema": SCHEMA_NAME}

    # Single-row table pattern: always use id=1
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # Gmail history tracking (required field)
    # Using BigInteger because Gmail history IDs can exceed 32-bit range
    history_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Gmail push notification watch
    watch_expiration: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    watch_resource_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )

    # Polling state
    last_pull_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    last_notification_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Error tracking
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    def __repr__(self) -> str:
        return f"<SyncState(history_id={self.history_id})>"


class Notification(MappedAsDataclass, Base, kw_only=True):
    """Model for tracking notifications sent to the Letta agent."""

    __tablename__ = "notifications"
    __table_args__ = {"schema": SCHEMA_NAME}

    # Primary key - init=False means it's not required in __init__
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        init=False,
        default_factory=uuid.uuid4,
    )

    # Thread/message reference (required fields)
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Optional fields
    message_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )

    # Notification details
    notified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        init=False,
        default=None,
    )

    # Agent information
    agent_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )
    message_sent: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )

    # Extensible metadata (named extra_data to avoid SQLAlchemy reserved 'metadata')
    extra_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=None
    )

    def __repr__(self) -> str:
        return (
            f"<Notification(thread_id={self.thread_id!r}, "
            f"type={self.notification_type!r})>"
        )
