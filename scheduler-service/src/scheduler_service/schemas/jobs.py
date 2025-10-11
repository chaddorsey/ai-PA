"""Pydantic schemas for job endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from scheduler_service.models.job import ActionType, JobStatus, ScheduleType


class SchedulePayload(BaseModel):
    """Base schedule description."""

    type: ScheduleType
    expression: dict[str, object]
    next_run_at: Optional[datetime] = None


class MetadataEntry(BaseModel):
    """Metadata key/value pair."""

    key: str = Field(..., max_length=128)
    value: dict[str, object]

    def to_model(self):
        from scheduler_service.models.job import JobMetadata

        return JobMetadata(meta_key=self.key, meta_value=self.value)


class ActionConfig(BaseModel):
    """Action configuration."""

    action_type: ActionType
    config: dict[str, object]
    allow_list_tag: Optional[str] = None

    def to_model(self):
        from scheduler_service.models.job import Action

        return Action(
            action_type=self.action_type.value,
            config=self.config,
            allow_list_tag=self.allow_list_tag,
        )


class MetadataResponse(BaseModel):
    key: str
    value: dict[str, object]

    class Config:
        orm_mode = True


class ActionResponse(BaseModel):
    action_id: str
    action_type: ActionType
    config: dict[str, object]
    allow_list_tag: Optional[str]

    class Config:
        orm_mode = True


class ExecutionResponse(BaseModel):
    execution_id: str
    job_id: str
    scheduled_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    status: JobStatus | str
    retry_count: int
    log_summary: Optional[str]
    result_reference: Optional[str]

    class Config:
        orm_mode = True

    @classmethod
    def from_model(cls, model):
        return cls(
            execution_id=str(model.execution_id),
            job_id=str(model.job_id),
            scheduled_at=model.scheduled_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            status=model.status,
            retry_count=model.retry_count,
            log_summary=model.log_summary,
            result_reference=model.result_reference,
        )


class JobCreate(BaseModel):
    """Schema for job creation."""

    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    created_by: str = Field(..., max_length=128)
    schedule: SchedulePayload
    metadata: Optional[list[MetadataEntry]] = None
    actions: Optional[list[ActionConfig]] = None


class JobUpdate(BaseModel):
    """Schema for partial job updates."""

    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    status: Optional[JobStatus] = None
    schedule: Optional[SchedulePayload] = None
    metadata: Optional[list[MetadataEntry]] = None
    actions: Optional[list[ActionConfig]] = None


class JobResponse(BaseModel):
    """API response schema for jobs."""

    job_id: str
    title: str
    description: Optional[str]
    status: JobStatus
    schedule_type: ScheduleType
    schedule_expression: dict[str, object]
    next_run_at: Optional[datetime]
    metadata: list[MetadataResponse] = Field(default_factory=list)
    actions: list[ActionResponse] = Field(default_factory=list)
    created_at: datetime
    created_by: str
    updated_at: datetime

    class Config:
        orm_mode = True

    @classmethod
    def from_model(cls, model):
        return cls(
            job_id=str(model.job_id),
            title=model.title,
            description=model.description,
            status=JobStatus(model.status),
            schedule_type=ScheduleType(model.schedule_type),
            schedule_expression=model.schedule_expression,
            next_run_at=model.next_run_at,
            created_at=model.created_at,
            created_by=model.created_by,
            updated_at=model.updated_at,
            metadata=[MetadataResponse(key=m.meta_key, value=m.meta_value) for m in model.metadata_entries],
            actions=[
                ActionResponse(
                    action_id=str(action.action_id),
                    action_type=ActionType(action.action_type),
                    config=action.config,
                    allow_list_tag=action.allow_list_tag,
                )
                for action in model.actions
            ],
        )


