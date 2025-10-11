"""Tool schemas and helper conversions for MCP layer."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ScheduleModel(BaseModel):
    type: str = Field(..., description="Schedule type: cron, interval, or one_off")
    expression: Dict[str, Any] = Field(..., description="Schedule expression payload")
    next_run_at: Optional[datetime] = Field(None, description="Next run timestamp")


class MetadataModel(BaseModel):
    key: str = Field(..., max_length=128)
    value: Dict[str, Any]


class ActionModel(BaseModel):
    action_type: str
    config: Dict[str, Any]
    allow_list_tag: Optional[str] = None


class JobCreateModel(BaseModel):
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    created_by: str = Field(..., max_length=128)
    schedule: ScheduleModel
    metadata: Optional[List[MetadataModel]] = None
    actions: Optional[List[ActionModel]] = None


class JobUpdateModel(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = Field(default=None, description="scheduled|paused|cancelled|completed")
    schedule: Optional[ScheduleModel] = None
    metadata: Optional[List[MetadataModel]] = None
    actions: Optional[List[ActionModel]] = None


class JobResponseModel(BaseModel):
    job_id: str
    title: str
    description: Optional[str]
    status: str
    schedule_type: str
    schedule_expression: Dict[str, Any]
    next_run_at: Optional[datetime]
    metadata: List[MetadataModel] = Field(default_factory=list)
    actions: List[ActionModel] = Field(default_factory=list)
    created_at: datetime
    created_by: str
    updated_at: datetime


class ExecutionResponseModel(BaseModel):
    execution_id: str
    job_id: str
    scheduled_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    status: str
    retry_count: int
    log_summary: Optional[str]
    result_reference: Optional[str]


