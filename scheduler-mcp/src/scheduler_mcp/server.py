"""Scheduler MCP server implementation using FastMCP."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

from scheduler_mcp.client import SchedulerClient
from scheduler_mcp.tools import (
    ExecutionResponseModel,
    JobCreateModel,
    JobResponseModel,
    JobUpdateModel,
    ScheduleModel,
)
from scheduler_mcp.settings import settings


async def _get_client() -> SchedulerClient:
    return SchedulerClient(base_url=settings.scheduler_base_url, api_key=settings.api_key)


def create_mcp_server() -> FastMCP:
    mcp = FastMCP("scheduler-tools")

    @mcp.tool(description="List jobs managed by the scheduler service with optional filtering.")
    async def scheduler_list_jobs(
        status_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        created_by_filter: Optional[str] = None,
    ):
        """List jobs with optional filters for status, category, or creator.
        
        Args:
            status_filter: Filter by status. Valid values:
                - "scheduled" or "active" - jobs that are scheduled to run
                - "paused" - jobs that are paused
                - "cancelled" - jobs that are cancelled
                - "completed" - jobs that are completed
                - "archived" - jobs that are archived (hidden from default listings)
                - "all" - include all statuses including archived
                If not specified, defaults to excluding archived jobs.
            category_filter: Filter by category string
            created_by_filter: Filter by creator identifier
        """
        client = await _get_client()
        return await client.list_jobs(
            status_filter=status_filter,
            category_filter=category_filter,
            created_by_filter=created_by_filter,
        )

    @mcp.tool(description="Fetch a single job by id.")
    async def scheduler_get_job(job_id: str):
        client = await _get_client()
        response = await client.get_job(job_id)
        return JobResponseModel(**response).model_dump()

    @mcp.tool(description="Create a new scheduled job.")
    async def scheduler_create_job(
        title: str,
        created_by: str,
        schedule_type: str,
        schedule_expression: Dict[str, Any],
        description: Optional[str] = None,
        category: Optional[str] = None,
        next_run_at: Optional[str] = None,
    ):
        """Create a new scheduled job.
        
        Args:
            title: Job title
            created_by: Creator identifier
            schedule_type: Schedule type (cron, interval, one_off, natural)
            schedule_expression: Schedule expression (dict format: {"cron": "..."} or {"seconds": 3600} or natural language string)
            description: Optional description
            category: Optional category
            next_run_at: Optional ISO timestamp for next run
        """
        from datetime import datetime
        
        schedule_data = ScheduleModel(
            type=schedule_type,
            expression=schedule_expression,
            next_run_at=datetime.fromisoformat(next_run_at.replace('Z', '+00:00')) if next_run_at else None
        )
        
        job_data = JobCreateModel(
            title=title,
            description=description,
            created_by=created_by,
            schedule=schedule_data,
            category=category,
        )
        
        client = await _get_client()
        response = await client.create_job(job_data.model_dump())
        return JobResponseModel(**response).model_dump()

    @mcp.tool(description="Update an existing job.")
    async def scheduler_update_job(
        job_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
    ):
        """Update basic job fields (title, description, status).
        
        For updating schedule, metadata, or actions, use the REST API directly or create a new job.
        
        Args:
            job_id: The job ID to update
            title: Optional new title
            description: Optional new description  
            status: Optional status (scheduled|paused|cancelled|completed|archived)
        """
        update_data = JobUpdateModel(
            title=title,
            description=description,
            status=status,
        )
        
        client = await _get_client()
        response = await client.update_job(job_id, update_data.model_dump(exclude_none=True))
        return JobResponseModel(**response).model_dump()

    @mcp.tool(description="Archive one or more jobs (marks them as archived, hiding them from default listings).")
    async def scheduler_archive_job(job_id: str):
        """Archive one or more jobs.
        
        Archiving jobs marks them as archived, which hides them from default job listings
        and search results. Archived jobs can still be retrieved by explicitly filtering
        for archived status or setting include_archived=true.
        
        Args:
            job_id: The job ID(s) to archive. Can be a single job ID or comma-separated job IDs
                   (e.g., "job-id-1" or "job-id-1,job-id-2,job-id-3")
        
        Returns:
            For a single job ID: The archived job response
            For multiple job IDs: Batch archive result with archived/failed lists
        """
        client = await _get_client()
        
        # Check if job_id contains commas (multiple job IDs)
        if "," in job_id:
            # Split by comma and strip whitespace
            job_ids = [jid.strip() for jid in job_id.split(",") if jid.strip()]
            if len(job_ids) == 0:
                raise ValueError("No valid job IDs provided")
            # Use batch archive for multiple jobs
            return await client.batch_archive_jobs(job_ids)
        else:
            # Single job ID - use regular archive
            update_data = JobUpdateModel(status="archived")
            response = await client.update_job(job_id.strip(), update_data.model_dump(exclude_none=True))
            return JobResponseModel(**response).model_dump()

    @mcp.tool(description="Archive multiple jobs at once.")
    async def scheduler_batch_archive_jobs(job_ids: List[str]):
        """Archive multiple jobs in a single operation.
        
        Archiving jobs marks them as archived, which hides them from default job listings
        and search results. Archived jobs can still be retrieved by explicitly filtering
        for archived status or setting include_archived=true.
        
        Args:
            job_ids: List of job IDs to archive
            
        Returns:
            Dictionary with:
            - archived: List of successfully archived job IDs
            - failed: List of dicts with 'job_id' and 'error' for failed operations
            - total: Total number of job IDs provided
            - archived_count: Number successfully archived
            - failed_count: Number that failed
        """
        client = await _get_client()
        response = await client.batch_archive_jobs(job_ids)
        return response

    @mcp.tool(description="Cancel a scheduled job.")
    async def scheduler_delete_job(job_id: str):
        client = await _get_client()
        await client.delete_job(job_id)
        return {"status": "deleted", "job_id": job_id}

    @mcp.tool(description="List execution history for a job.")
    async def scheduler_list_executions(job_id: str):
        client = await _get_client()
        return await client.list_executions(job_id)

    @mcp.tool(description="Retrieve a specific execution record.")
    async def scheduler_get_execution(execution_id: str):
        client = await _get_client()
        response = await client.get_execution(execution_id)
        return ExecutionResponseModel(**response).model_dump()

    @mcp.tool(description="Search jobs using semantic similarity on title and description embeddings.")
    async def scheduler_search_jobs(
        query_text: str,
        limit: int = 10,
        min_score: float = 0.5,
        status_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
    ):
        """Search for jobs using natural language queries with semantic similarity.
        
        Args:
            query_text: Natural language query for semantic search
            limit: Maximum number of results (1-100, default: 10)
            min_score: Minimum similarity score 0.0-1.0 (default: 0.5)
            status_filter: Optional status filter. Valid values:
                - "scheduled" or "active" - jobs that are scheduled to run
                - "paused" - jobs that are paused
                - "cancelled" - jobs that are cancelled
                - "completed" - jobs that are completed
                - "archived" - jobs that are archived (hidden from default listings)
                - "all" - include all statuses including archived
            category_filter: Optional category filter
        
        Returns jobs whose title/description embeddings are most similar to the query.
        Results are ordered by similarity score (highest first).
        """
        client = await _get_client()
        response = await client.search_jobs(
            query_text=query_text,
            limit=limit,
            min_score=min_score,
            status_filter=status_filter,
            category_filter=category_filter,
        )
        # Response is a list of jobs, convert each to JobResponseModel
        return [JobResponseModel(**job).model_dump() for job in response]

    # Add health endpoint using FastMCP custom route
    from fastapi import Request
    from fastapi.responses import JSONResponse
    
    @mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "healthy", "service": settings.app_name})

    return mcp


def create_app():
    server = create_mcp_server()
    app = server.streamable_http_app()
    return app


