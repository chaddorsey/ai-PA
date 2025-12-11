"""Tool schemas and helper conversions for MCP layer."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ScheduleModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "properties": {
                "expression": {
                    "type": "object",
                    "additionalProperties": False,
                    "description": "Schedule expression payload"
                }
            }
        }
    )
    
    type: str = Field(..., description="Schedule type: cron, interval, or one_off")
    expression: Dict[str, Any] = Field(..., description="Schedule expression payload")
    next_run_at: Optional[datetime] = Field(None, description="Next run timestamp")


class MetadataModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "properties": {
                "value": {
                    "type": "object",
                    "additionalProperties": False,
                    "description": "Metadata value dictionary"
                }
            }
        }
    )
    
    key: str = Field(..., max_length=128)
    value: Dict[str, Any]


class ActionModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "properties": {
                "config": {
                    "type": "object",
                    "additionalProperties": False,
                    "description": "Action configuration dictionary"
                }
            }
        }
    )
    
    action_id: str = Field(..., description="Unique identifier for the action")
    action_type: str
    config: Dict[str, Any] = Field(
        ...,
        description="Action configuration dictionary (can contain any key-value pairs)"
    )
    allow_list_tag: Optional[str] = None


class JobCreateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    created_by: str = Field(..., max_length=128)
    schedule: ScheduleModel
    metadata: Optional[List[MetadataModel]] = None
    actions: Optional[List[ActionModel]] = None


class JobUpdateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = Field(default=None, description="scheduled|paused|cancelled|completed|archived")
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


class JobSearchModel(BaseModel):
    """Parameters for semantic job search."""
    query_text: str = Field(..., description="Text query for semantic search")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results")
    min_score: float = Field(0.5, ge=0.0, le=1.0, description="Minimum similarity score (0-1)")
    status_filter: Optional[str] = Field(None, description="Filter by status: scheduled|paused|cancelled|completed")
    category_filter: Optional[str] = Field(None, description="Filter by category")


