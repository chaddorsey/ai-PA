"""Job models and enumerations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, TIMESTAMP, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from scheduler_service.models.base import Base


class JobStatus(str, Enum):
    """Lifecycle status for scheduled jobs."""

    SCHEDULED = "scheduled"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ScheduleType(str, Enum):
    """Supported schedule expression types."""

    CRON = "cron"
    INTERVAL = "interval"
    ONE_OFF = "one_off"
    NATURAL = "natural"  # Natural language expression, parsed on creation


class Job(Base):
    """Authoritative job definition."""

    __tablename__ = "jobs"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        String(32), default=JobStatus.SCHEDULED.value, nullable=False
    )
    schedule_type: Mapped[ScheduleType] = mapped_column(String(32), nullable=False)
    schedule_expression: Mapped[dict] = mapped_column(JSON, nullable=False)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    category: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    vector_embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(384))

    metadata_entries: Mapped[List["JobMetadata"]] = relationship(
        "JobMetadata", back_populates="job", cascade="all, delete-orphan"
    )
    actions: Mapped[List["Action"]] = relationship(
        "Action", back_populates="job", cascade="all, delete-orphan"
    )
    executions: Mapped[List["Execution"]] = relationship(
        "Execution", back_populates="job", cascade="all, delete-orphan"
    )
    callbacks: Mapped[List["Callback"]] = relationship(
        "Callback", back_populates="job", cascade="all, delete-orphan"
    )


Index("jobs_next_run_idx", Job.next_run_at)
Index("jobs_status_idx", Job.status)
Index("jobs_category_idx", Job.category)
Index(
    "jobs_embedding_idx",
    Job.vector_embedding,
    postgresql_using="ivfflat",
    postgresql_ops={"vector_embedding": "vector_cosine_ops"},
)


class JobMetadata(Base):
    """Key-value metadata associated with a job."""

    __tablename__ = "job_metadata"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scheduler.jobs.job_id"), nullable=False
    )
    meta_key: Mapped[str] = mapped_column(String(128), nullable=False)
    meta_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(384))

    job: Mapped[Job] = relationship("Job", back_populates="metadata_entries")


Index("job_metadata_job_idx", JobMetadata.job_id)
Index(
    "job_metadata_embedding_idx",
    JobMetadata.embedding,
    postgresql_using="ivfflat",
    postgresql_ops={"embedding": "vector_cosine_ops"},
)


class ActionType(str, Enum):
    """Supported action types."""

    HTTP = "http"
    WEBHOOK = "webhook"
    SCRIPT = "script"
    AGENT_MESSAGE = "agent_message"  # Send message to Letta agent (sync, configurable route)
    LETTABOT_HEARTBEAT = "lettabot_heartbeat"  # Fire-and-forget via LettaBot (async, silent, full tools)


class Action(Base):
    """Action configuration linked to a job."""

    __tablename__ = "actions"

    action_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scheduler.jobs.job_id"), nullable=False
    )
    action_type: Mapped[ActionType] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    allow_list_tag: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    job: Mapped[Job] = relationship("Job", back_populates="actions")


Index("actions_job_idx", Action.job_id)


class ExecutionStatus(str, Enum):
    """Status for an execution record."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Execution(Base):
    """Individual job execution history."""

    __tablename__ = "executions"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scheduler.jobs.job_id"), nullable=False
    )
    scheduled_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[ExecutionStatus] = mapped_column(String(32), nullable=False)
    retry_count: Mapped[int] = mapped_column(default=0)
    log_summary: Mapped[Optional[str]] = mapped_column(Text)
    result_reference: Mapped[Optional[str]] = mapped_column(String(255))
    vector_embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(384))

    job: Mapped[Job] = relationship("Job", back_populates="executions")
    outputs: Mapped[List["ExecutionOutput"]] = relationship(
        "ExecutionOutput", back_populates="execution", cascade="all, delete-orphan"
    )


Index(
    "executions_job_scheduled_idx",
    Execution.job_id,
    Execution.scheduled_at.desc(),
)
Index(
    "executions_embedding_idx",
    Execution.vector_embedding,
    postgresql_using="ivfflat",
    postgresql_ops={"vector_embedding": "vector_cosine_ops"},
)


class ExecutionOutput(Base):
    """Structured output tied to an execution and action."""

    __tablename__ = "execution_outputs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scheduler.executions.execution_id"), nullable=False
    )
    action_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scheduler.actions.action_id"), nullable=False
    )
    output_type: Mapped[str] = mapped_column(String(32), nullable=False)
    output_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    artifact_uri: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    execution: Mapped[Execution] = relationship("Execution", back_populates="outputs")
    action: Mapped[Action] = relationship("Action")


class Callback(Base):
    """Callback target configuration for notifications."""

    __tablename__ = "callbacks"

    callback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scheduler.jobs.job_id"), nullable=False
    )
    callback_url: Mapped[str] = mapped_column(Text, nullable=False)
    secret_token: Mapped[Optional[str]] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    job: Mapped[Job] = relationship("Job", back_populates="callbacks")


class AuditLog(Base):
    """Change history for scheduler entities."""

    __tablename__ = "audit_log"

    audit_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False
    )
    details: Mapped[dict] = mapped_column(JSON, nullable=False)


class DistributedLock(Base):
    """Model used to maintain scheduler ownership."""

    __tablename__ = "distributed_lock"

    lock_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


