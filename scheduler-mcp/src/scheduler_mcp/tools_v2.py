"""Updated tool schemas optimized for LLM usability."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Schedule Models
# ============================================================================


class ScheduleReminderParams(BaseModel):
    """Parameters for scheduling an agent message/reminder."""

    message: str = Field(
        ...,
        description="The reminder message text to deliver to the agent",
    )
    when: str = Field(
        ...,
        description=(
            "When to send the reminder (Eastern Time unless timezone specified). "
            "Examples: 'in 30 minutes', 'tomorrow at 9am', 'every day at 8am', 'every Monday at 5pm'"
        ),
    )
    title: str = Field(
        ...,
        description="Short title for this reminder (e.g., 'Morning check-in', 'Meeting prep')",
    )
    agent_id: Optional[str] = Field(
        None,
        description="Agent to receive the reminder. Defaults to the requesting agent (you).",
    )
    category: Optional[str] = Field(
        None,
        description="Category for organization (e.g., 'daily_routine', 'meeting_prep', 'follow_up')",
    )
    timezone: Optional[str] = Field(
        None,
        description="Timezone for schedule. Defaults to 'America/New_York' (Eastern Time).",
    )


class ScheduleActionParams(BaseModel):
    """Parameters for scheduling a script or HTTP action."""

    action_type: str = Field(
        ...,
        description="Type of action: 'script' to run a file, 'http' to make an API call",
    )
    target: str = Field(
        ...,
        description=(
            "For 'script': filename in /app/scripts/ (e.g., 'download_news.py')\n"
            "For 'http': full URL (e.g., 'https://api.example.com/webhook')"
        ),
    )
    when: str = Field(
        ...,
        description=(
            "When to run (Eastern Time unless timezone specified). "
            "Examples: 'in 5 minutes', 'every day at 2am', 'every hour', 'tomorrow at midnight'"
        ),
    )
    title: str = Field(
        ...,
        description="Short title for this action (e.g., 'Daily news scraper', 'Trigger data sync')",
    )
    method: Optional[str] = Field(
        None,
        description="HTTP method (only for action_type='http'). Defaults to POST. Options: GET, POST, PUT, PATCH, DELETE",
    )
    args: Optional[List[str]] = Field(
        None,
        description="Command-line arguments for scripts (e.g., ['--source', 'nyt', '--limit', '50'])",
    )
    body: Optional[Dict[str, Any]] = Field(
        None,
        description="JSON body for HTTP POST/PUT/PATCH requests (only for action_type='http')",
    )
    headers: Optional[Dict[str, str]] = Field(
        None,
        description="HTTP headers (only for action_type='http'). Example: {'Authorization': 'Bearer token123'}",
    )
    description: Optional[str] = Field(
        None,
        description="Detailed description of what this action does and why it's scheduled",
    )
    timeout_minutes: Optional[int] = Field(
        None,
        description="Maximum execution time in minutes. Defaults to 5 for scripts, 1 for HTTP calls.",
    )
    timezone: Optional[str] = Field(
        None,
        description="Timezone for schedule. Defaults to 'America/New_York' (Eastern Time).",
    )


# ============================================================================
# Advanced Scheduling
# ============================================================================


class AdvancedScheduleConfig(BaseModel):
    """Schedule configuration for advanced scheduling."""

    type: str = Field(
        ...,
        description="Schedule type: 'cron', 'interval', 'one_off', or 'natural'",
    )
    expression: str = Field(
        ...,
        description=(
            "Schedule expression based on type:\n"
            "- 'cron': cron string (e.g., '0 9 * * *' for 9am daily)\n"
            "- 'interval': duration (e.g., '15m', '2h', '1d')\n"
            "- 'one_off': ISO timestamp (e.g., '2025-10-14T09:00:00')\n"
            "- 'natural': plain language (e.g., 'every Monday at 5pm')"
        ),
    )
    timezone: Optional[str] = Field(
        None,
        description="Timezone for schedule. Defaults to 'America/New_York'.",
    )


class AdvancedActionConfig(BaseModel):
    """Action configuration for advanced scheduling."""

    type: str = Field(
        ...,
        description="Action type: 'agent_message', 'http', or 'script'",
    )
    config: Dict[str, Any] = Field(
        ...,
        description=(
            "Action-specific configuration:\n"
            "- agent_message: {agent_id, message, category}\n"
            "- http: {url, method, headers, body, timeout_seconds}\n"
            "- script: {script_path, args, timeout_seconds}"
        ),
    )


class ScheduleAdvancedParams(BaseModel):
    """Parameters for advanced scheduling with full control."""

    title: str = Field(
        ...,
        description="Short title for this scheduled job",
    )
    description: str = Field(
        ...,
        description="Detailed description of what this job does",
    )
    schedule: AdvancedScheduleConfig = Field(
        ...,
        description="Schedule definition with type and expression",
    )
    actions: List[AdvancedActionConfig] = Field(
        ...,
        description="List of actions to execute (in order) when the job runs",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Free-form metadata for categorization and search. "
            "Example: {'category': 'briefing', 'priority': 'high', 'tags': ['automation']}"
        ),
    )
    enabled: Optional[bool] = Field(
        True,
        description="Whether the job should be active immediately. Defaults to true.",
    )


# ============================================================================
# List & Query
# ============================================================================


class JobFilters(BaseModel):
    """Filter criteria for listing jobs."""

    created_by: Optional[str] = Field(
        None,
        description="Filter by creator. Use 'me' or 'self' for your own jobs.",
    )
    status: Optional[str] = Field(
        None,
        description="Filter by job status: 'scheduled', 'paused', 'cancelled', 'completed'",
    )
    event_type: Optional[str] = Field(
        None,
        description="Filter by type of event: 'reminder', 'script', 'http'",
    )
    schedule_pattern: Optional[str] = Field(
        None,
        description="Filter by pattern: 'one_off' for single execution, 'recurring' for repeating jobs",
    )
    category: Optional[str] = Field(
        None,
        description="Filter by category (for reminders)",
    )
    date_range: Optional[Dict[str, str]] = Field(
        None,
        description=(
            "Filter by when jobs will run. "
            "Example: {'start': 'today', 'end': 'next week'} or {'start': '2025-10-13', 'end': '2025-10-20'}"
        ),
    )
    job_id: Optional[str] = Field(
        None,
        description="Get a specific job by ID",
    )


class ListScheduledJobsParams(BaseModel):
    """Parameters for listing scheduled jobs."""

    filters: Optional[JobFilters] = Field(
        None,
        description="Filter criteria (all conditions are AND-ed together)",
    )
    limit: Optional[int] = Field(
        20,
        description="Maximum number of jobs to return. Defaults to 20, max 100.",
    )
    show_utc: Optional[bool] = Field(
        False,
        description="Show times in UTC instead of Eastern Time. Defaults to false.",
    )


# ============================================================================
# Management
# ============================================================================


class ManageScheduledJobParams(BaseModel):
    """Parameters for managing (update/pause/resume/cancel) a scheduled job."""

    job_id: str = Field(
        ...,
        description="ID of the job to manage (obtained from schedule_* tools or list_scheduled_jobs)",
    )
    operation: str = Field(
        ...,
        description=(
            "What to do:\n"
            "- 'update': Modify job details (title, schedule, etc.)\n"
            "- 'pause': Stop job from running but keep it (can resume later)\n"
            "- 'resume': Re-activate a paused job\n"
            "- 'cancel': Permanently delete the job"
        ),
    )
    updates: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Fields to update (only for operation='update'). "
            "Can include: 'title', 'description', 'when', 'message', 'target', 'method', 'body', etc."
        ),
    )


# ============================================================================
# Response Models
# ============================================================================


class ScheduleResponse(BaseModel):
    """Success response from scheduling operations."""

    success: bool = True
    job_id: str
    message: str
    next_run_at: Optional[str] = None
    next_run_at_et: Optional[str] = None
    created_by: Optional[str] = None
    recipient: Optional[str] = None


class JobListItem(BaseModel):
    """Single job in list response."""

    job_id: str
    title: str
    event_type: str
    status: str
    schedule_pattern: str
    next_run_at: str
    created_by: str
    created_at: str
    category: Optional[str] = None


class ListJobsResponse(BaseModel):
    """Response from list_scheduled_jobs."""

    success: bool = True
    count: int
    timezone: str
    jobs: List[JobListItem]


class ManageJobResponse(BaseModel):
    """Response from manage_scheduled_job."""

    success: bool = True
    job_id: str
    operation: str
    message: str
    updated_fields: Optional[List[str]] = None



