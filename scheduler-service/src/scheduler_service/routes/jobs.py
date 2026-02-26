"""Job management endpoints."""

import json
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from scheduler_service.database import get_session
from scheduler_service.logging_config import get_logger
from scheduler_service.models.job import (
    Action,
    Execution,
    ExecutionOutput,
    ExecutionStatus,
    Job,
    JobMetadata,
    JobStatus,
    ScheduleType,
)
from scheduler_service.schemas import jobs as job_schemas
from scheduler_service.services.embeddings import embed_text, embed_texts
from scheduler_service.services.scheduler import scheduler_service
from scheduler_service.services.actions import execute_action, ActionExecutionError
from scheduler_service.services.schedule_parser import parse_schedule, ScheduleParseError

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = get_logger(__name__)


def _parse_job_id(job_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid job ID format: '{job_id}'. "
                f"Job IDs must be valid UUIDs (e.g., '550e8400-e29b-41d4-a716-446655440000'). "
                f"Tip: Use scheduler_list_jobs() or scheduler_search_jobs() to find job IDs."
            )
        ) from exc


async def _load_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    result = await session.execute(
        select(Job)
        .options(
            selectinload(Job.metadata_entries),
            selectinload(Job.actions),
        )
        .where(Job.job_id == job_id)
    )
    return result.scalar_one_or_none()


@router.post("", response_model=job_schemas.JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: job_schemas.JobCreate,
    session: AsyncSession = Depends(get_session),
) -> job_schemas.JobResponse:
    # Handle natural language schedule parsing
    schedule_type = payload.schedule.type.value
    schedule_expression = payload.schedule.expression
    next_run_at = payload.schedule.next_run_at
    
    if schedule_type == "natural" or (isinstance(schedule_expression, str)):
        # Parse natural language schedule
        try:
            when_expr = schedule_expression if isinstance(schedule_expression, str) else schedule_expression.get("expression", "")
            tz = schedule_expression.get("timezone", "America/New_York") if isinstance(schedule_expression, dict) else "America/New_York"
            
            parsed = parse_schedule(when_expr, tz)
            
            # Update to use parsed values
            schedule_type = parsed["type"]
            schedule_expression = parsed["expression"]
            next_run_at = parsed["next_run_at"]
            
            logger.info(f"Parsed natural language schedule: '{when_expr}' -> {schedule_type} @ {next_run_at}")
        
        except ScheduleParseError as e:
            logger.error(f"Failed to parse schedule: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid schedule expression: {e.reason}. "
                    f"Valid schedule types: 'cron', 'interval', 'one_off', or 'natural' (natural language). "
                    f"Examples: 'every 5 minutes', 'daily at 2am', '0 2 * * *' (cron), or '{{'seconds': 300}}' (interval)."
                )
            )
        except Exception as e:
            logger.error(f"Unexpected error parsing schedule: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Failed to parse schedule: {str(e)}. "
                    f"Please check the schedule expression format. "
                    f"For natural language, use phrases like 'every 5 minutes' or 'daily at 2am'. "
                    f"For cron, use standard cron syntax. For interval, use {{'seconds': number}}."
                )
            )
    
    job = Job(
        title=payload.title,
        description=payload.description,
        status=JobStatus.SCHEDULED.value,
        schedule_type=schedule_type,
        schedule_expression=schedule_expression,
        created_by=payload.created_by,
        next_run_at=next_run_at,
        category=payload.category,
    )

    if payload.metadata:
        for meta in payload.metadata:
            metadata_model = meta.to_model()
            metadata_model.embedding = embed_texts(
                [meta.key, json.dumps(meta.value, sort_keys=True)]
            )
            job.metadata_entries.append(metadata_model)

    if payload.actions:
        for action in payload.actions:
            action_model = action.to_model()
            job.actions.append(action_model)

    job.vector_embedding = embed_texts([job.title, job.description or ""])

    session.add(job)
    await session.commit()

    await scheduler_service.refresh_job(job.job_id)

    job_with_rel = await _load_job(session, job.job_id)
    assert job_with_rel is not None
    return job_schemas.JobResponse.from_model(job_with_rel)


@router.get("", response_model=List[job_schemas.JobResponse])
async def list_jobs(
    status_filter: str | None = Query(None, alias="status_filter", description="Filter by status: scheduled, paused, cancelled, completed, archived, or 'all' to include all statuses"),
    category_filter: str | None = Query(None, alias="category_filter"),
    created_by_filter: str | None = Query(None, alias="created_by_filter"),
    include_archived: bool = Query(False, alias="include_archived", description="Include archived jobs in results (only applies when status_filter is not set)"),
    session: AsyncSession = Depends(get_session),
) -> List[job_schemas.JobResponse]:
    """List jobs with optional filtering by status, category, or creator.
    
    By default, archived jobs are excluded. Set include_archived=true to include them,
    or use status_filter='all' to include all statuses including archived.
    """
    query = (
        select(Job)
        .options(selectinload(Job.metadata_entries), selectinload(Job.actions))
    )
    
    # Apply status filter
    if status_filter:
        status_lower = status_filter.lower()
        if status_lower == "all":
            # "all" means include all statuses, including archived
            # Don't apply any status filter
            pass
        elif status_lower == "active":
            # "active" is an alias for "scheduled"
            query = query.where(Job.status == JobStatus.SCHEDULED.value)
        else:
            # Try to parse as JobStatus enum
            try:
                job_status = JobStatus(status_lower)
                query = query.where(Job.status == job_status.value)
            except ValueError:
                # Provide helpful error message with suggestions
                valid_statuses = ["scheduled", "active", "paused", "cancelled", "completed", "archived", "all"]
                suggestion = ""
                status_lower = status_filter.lower()
                
                # Suggest common alternatives
                if status_lower in ["running", "active", "enabled"]:
                    suggestion = " Did you mean 'scheduled' or 'active'? These show jobs that are scheduled to run."
                elif status_lower in ["inactive", "disabled", "stopped"]:
                    suggestion = " Did you mean 'paused' or 'cancelled'?"
                elif status_lower in ["done", "finished"]:
                    suggestion = " Did you mean 'completed'?"
                
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Invalid status_filter value: '{status_filter}'. "
                        f"Valid values are: {', '.join(valid_statuses)}. "
                        f"- Use 'scheduled' or 'active' for jobs that will run. "
                        f"- Use 'paused' for temporarily stopped jobs. "
                        f"- Use 'cancelled' for cancelled jobs. "
                        f"- Use 'completed' for finished jobs. "
                        f"- Use 'archived' for archived (hidden) jobs. "
                        f"- Use 'all' to include all statuses including archived. "
                        f"{suggestion}"
                    ).strip()
                )
    else:
        # By default, exclude archived jobs unless explicitly requested
        if not include_archived:
            query = query.where(Job.status != JobStatus.ARCHIVED.value)
    
    if category_filter:
        query = query.where(Job.category == category_filter)
    if created_by_filter:
        query = query.where(Job.created_by == created_by_filter)
    
    # Order by next_run_at (nulls last for jobs without next run)
    query = query.order_by(Job.next_run_at.nulls_last(), Job.created_at.desc())
    
    result = await session.execute(query)
    jobs = result.scalars().all()
    return [job_schemas.JobResponse.from_model(job) for job in jobs]


@router.get("/search", response_model=List[job_schemas.JobResponse])
async def search_jobs(
    query_text: str = Query(..., description="Text query for semantic search"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results to return"),
    min_score: float = Query(0.5, ge=0.0, le=1.0, description="Minimum cosine similarity score"),
    status_filter: str | None = Query(None, alias="status_filter", description="Filter by status: scheduled, active (alias for scheduled), paused, cancelled, completed, archived, or 'all'"),
    category_filter: str | None = Query(None, alias="category_filter"),
    include_archived: bool = Query(False, alias="include_archived", description="Include archived jobs in results"),
    session: AsyncSession = Depends(get_session),
) -> List[job_schemas.JobResponse]:
    """Semantic search for jobs using vector embeddings.
    
    By default, archived jobs are excluded. Set include_archived=true to include them.
    """
    
    # Generate embedding for query text
    query_embedding = embed_text(query_text)
    if not query_embedding:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding model not available. Semantic search requires sentence-transformers."
        )
    
    # Build base query with filters
    base_query = select(Job).options(
        selectinload(Job.metadata_entries),
        selectinload(Job.actions)
    )
    
    # Apply status and category filters
    if status_filter:
        status_lower = status_filter.lower()
        if status_lower == "all":
            # "all" means include all statuses, including archived
            # Don't apply any status filter
            pass
        elif status_lower == "active":
            # "active" is an alias for "scheduled"
            base_query = base_query.where(Job.status == JobStatus.SCHEDULED.value)
        else:
            # Try to parse as JobStatus enum
            try:
                job_status = JobStatus(status_lower)
                base_query = base_query.where(Job.status == job_status.value)
            except ValueError:
                # Provide helpful error message with suggestions
                valid_statuses = ["scheduled", "active", "paused", "cancelled", "completed", "archived", "all"]
                suggestion = ""
                status_lower = status_filter.lower()
                
                # Suggest common alternatives
                if status_lower in ["running", "active", "enabled"]:
                    suggestion = " Did you mean 'scheduled' or 'active'? These show jobs that are scheduled to run."
                elif status_lower in ["inactive", "disabled", "stopped"]:
                    suggestion = " Did you mean 'paused' or 'cancelled'?"
                elif status_lower in ["done", "finished"]:
                    suggestion = " Did you mean 'completed'?"
                
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Invalid status_filter value: '{status_filter}'. "
                        f"Valid values are: {', '.join(valid_statuses)}. "
                        f"- Use 'scheduled' or 'active' for jobs that will run. "
                        f"- Use 'paused' for temporarily stopped jobs. "
                        f"- Use 'cancelled' for cancelled jobs. "
                        f"- Use 'completed' for finished jobs. "
                        f"- Use 'archived' for archived (hidden) jobs. "
                        f"- Use 'all' to include all statuses including archived. "
                        f"{suggestion}"
                    ).strip()
                )
    else:
        # By default, exclude archived jobs unless explicitly requested
        if not include_archived:
            base_query = base_query.where(Job.status != JobStatus.ARCHIVED.value)
    
    if category_filter:
        base_query = base_query.where(Job.category == category_filter)
    
    # Filter to only jobs with embeddings
    base_query = base_query.where(Job.vector_embedding.isnot(None))
    
    # Use raw SQL for pgvector cosine similarity search
    # pgvector uses <=> operator for cosine distance (lower is more similar)
    # We convert to similarity: 1 - distance (higher is more similar)
    
    # Build WHERE conditions as strings for raw SQL
    where_conditions = ["j.vector_embedding IS NOT NULL"]
    
    # Format vector as PostgreSQL array string for casting to vector type
    vector_str = "[" + ",".join(str(f) for f in query_embedding) + "]"
    
    # Build all query parameters
    query_params: dict = {
        "vector_str": vector_str,
        "min_score": min_score,
        "result_limit": limit,
    }
    
    if status_filter:
        status_lower = status_filter.lower()
        if status_lower == "all":
            # "all" means include all statuses, including archived
            # Don't apply any status filter in the raw SQL either
            pass
        elif status_lower == "active":
            # "active" is an alias for "scheduled"
            where_conditions.append("j.status = :status_filter")
            query_params["status_filter"] = JobStatus.SCHEDULED.value
        else:
            # Try to parse as JobStatus enum
            try:
                job_status = JobStatus(status_lower)
                where_conditions.append("j.status = :status_filter")
                query_params["status_filter"] = job_status.value
            except ValueError:
                # Provide helpful error message with suggestions
                valid_statuses = ["scheduled", "active", "paused", "cancelled", "completed", "archived", "all"]
                suggestion = ""
                status_lower = status_filter.lower()
                
                # Suggest common alternatives
                if status_lower in ["running", "active", "enabled"]:
                    suggestion = " Did you mean 'scheduled' or 'active'? These show jobs that are scheduled to run."
                elif status_lower in ["inactive", "disabled", "stopped"]:
                    suggestion = " Did you mean 'paused' or 'cancelled'?"
                elif status_lower in ["done", "finished"]:
                    suggestion = " Did you mean 'completed'?"
                
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Invalid status_filter value: '{status_filter}'. "
                        f"Valid values are: {', '.join(valid_statuses)}. "
                        f"- Use 'scheduled' or 'active' for jobs that will run. "
                        f"- Use 'paused' for temporarily stopped jobs. "
                        f"- Use 'cancelled' for cancelled jobs. "
                        f"- Use 'completed' for finished jobs. "
                        f"- Use 'archived' for archived (hidden) jobs. "
                        f"- Use 'all' to include all statuses including archived. "
                        f"{suggestion}"
                    ).strip()
                )
    elif not include_archived:
        # By default, exclude archived jobs unless explicitly requested
        where_conditions.append("j.status != :archived_status")
        query_params["archived_status"] = JobStatus.ARCHIVED.value
    
    if category_filter:
        where_conditions.append("j.category = :category_filter")
        query_params["category_filter"] = category_filter
    
    where_clause = " AND ".join(where_conditions)
    
    # Raw SQL query for vector similarity search
    # pgvector uses <=> operator for cosine distance (lower is more similar)
    # We convert to similarity: 1 - distance (higher is more similar)
    search_sql = text(f"""
        SELECT 
            j.job_id,
            1 - (j.vector_embedding <=> CAST(:vector_str AS vector)) AS similarity
        FROM scheduler.jobs j
        WHERE {where_clause}
        AND 1 - (j.vector_embedding <=> CAST(:vector_str AS vector)) >= :min_score
        ORDER BY similarity DESC
        LIMIT :result_limit
    """)
    
    result = await session.execute(search_sql, query_params)
    rows = result.all()
    
    # Extract job IDs and similarity scores
    if not rows:
        return []
    
    job_ids = [uuid.UUID(str(row[0])) for row in rows]
    
    # Load full job objects with relationships
    jobs_query = (
        select(Job)
        .options(selectinload(Job.metadata_entries), selectinload(Job.actions))
        .where(Job.job_id.in_(job_ids))
    )
    jobs_result = await session.execute(jobs_query)
    jobs = jobs_result.scalars().all()
    
    # Maintain similarity score order
    job_map = {job.job_id: job for job in jobs}
    jobs_ordered = [job_map[jid] for jid in job_ids if jid in job_map]
    
    logger.info(
        "Semantic search completed",
        query=query_text,
        results_count=len(jobs_ordered),
        limit=limit,
        min_score=min_score,
    )
    
    return [job_schemas.JobResponse.from_model(job) for job in jobs_ordered]


@router.get("/{job_id}", response_model=job_schemas.JobResponse)
async def get_job(job_id: str, session: AsyncSession = Depends(get_session)) -> job_schemas.JobResponse:
    job_uuid = _parse_job_id(job_id)
    job = await _load_job(session, job_uuid)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Job not found: '{job_id}'. "
                f"The job may have been deleted, or the ID is incorrect. "
                f"Use scheduler_list_jobs() or scheduler_search_jobs() to find valid job IDs."
            )
        )
    return job_schemas.JobResponse.from_model(job)


@router.patch("/{job_id}", response_model=job_schemas.JobResponse)
async def update_job(
    job_id: str,
    payload: job_schemas.JobUpdate,
    session: AsyncSession = Depends(get_session),
) -> job_schemas.JobResponse:
    job_uuid = _parse_job_id(job_id)
    job = await _load_job(session, job_uuid)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if payload.title is not None:
        job.title = payload.title
    if payload.description is not None:
        job.description = payload.description
    if payload.status is not None:
        new_status = payload.status.value
        job.status = new_status
        # If job is no longer scheduled, remove it from the in-memory scheduler
        if new_status != JobStatus.SCHEDULED.value:
            await scheduler_service.remove_job(job.job_id)
    if payload.schedule is not None:
        job.schedule_type = payload.schedule.type.value
        job.schedule_expression = payload.schedule.expression
        job.next_run_at = payload.schedule.next_run_at
    if payload.category is not None:
        job.category = payload.category

    if payload.metadata is not None:
        job.metadata_entries.clear()
        for meta in payload.metadata:
            metadata_model = meta.to_model()
            metadata_model.embedding = embed_texts(
                [meta.key, json.dumps(meta.value, sort_keys=True)]
            )
            job.metadata_entries.append(metadata_model)

    if payload.actions is not None:
        job.actions.clear()
        for action in payload.actions:
            job.actions.append(action.to_model())

    job.vector_embedding = embed_texts([job.title, job.description or ""])

    job.updated_at = datetime.now(timezone.utc)
    await session.commit()

    await scheduler_service.refresh_job(job.job_id)

    updated_job = await _load_job(session, job_uuid)
    assert updated_job is not None
    return job_schemas.JobResponse.from_model(updated_job)


@router.post("/batch/archive", response_model=dict)
async def batch_archive_jobs(
    job_ids: List[str],
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Archive multiple jobs at once.
    
    Args:
        job_ids: List of job IDs to archive
        
    Returns:
        Dictionary with 'archived' (list of successfully archived job IDs) and
        'failed' (list of dicts with 'job_id' and 'error' for failed operations)
    """
    archived = []
    failed = []
    
    for job_id_str in job_ids:
        try:
            job_uuid = _parse_job_id(job_id_str)
            job = await session.get(Job, job_uuid)
            
            if not job:
                failed.append({"job_id": job_id_str, "error": "Job not found"})
                continue
            
            if job.status == JobStatus.ARCHIVED.value:
                # Already archived, skip
                archived.append(job_id_str)
                continue
            
            job.status = JobStatus.ARCHIVED.value
            job.updated_at = datetime.now(timezone.utc)
            archived.append(job_id_str)
            
            # Remove from scheduler
            await scheduler_service.remove_job(job_uuid)
            
        except ValueError as exc:
            failed.append({"job_id": job_id_str, "error": f"Invalid job ID format: {str(exc)}"})
        except Exception as exc:
            failed.append({"job_id": job_id_str, "error": str(exc)})
    
    # Commit all changes at once
    if archived:
        await session.commit()
    
    logger.info(
        "Batch archive completed",
        total=len(job_ids),
        archived_count=len(archived),
        failed_count=len(failed),
    )
    
    return {
        "archived": archived,
        "failed": failed,
        "total": len(job_ids),
        "archived_count": len(archived),
        "failed_count": len(failed),
    }


@router.post("/batch/cancel", response_model=dict)
async def batch_cancel_jobs(
    job_ids: List[str],
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Cancel multiple jobs at once.
    
    Args:
        job_ids: List of job IDs to cancel
        
    Returns:
        Dictionary with 'cancelled' (list of successfully cancelled job IDs) and
        'failed' (list of dicts with 'job_id' and 'error' for failed operations)
    """
    cancelled = []
    failed = []
    
    for job_id_str in job_ids:
        try:
            job_uuid = _parse_job_id(job_id_str)
            job = await session.get(Job, job_uuid)
            
            if not job:
                failed.append({"job_id": job_id_str, "error": "Job not found"})
                continue
            
            if job.status == JobStatus.CANCELLED.value:
                # Already cancelled, skip
                cancelled.append(job_id_str)
                continue
            
            job.status = JobStatus.CANCELLED.value
            job.updated_at = datetime.now(timezone.utc)
            cancelled.append(job_id_str)
            
            # Remove from scheduler
            await scheduler_service.remove_job(job_uuid)
            
        except ValueError as exc:
            failed.append({"job_id": job_id_str, "error": f"Invalid job ID format: {str(exc)}"})
        except Exception as exc:
            failed.append({"job_id": job_id_str, "error": str(exc)})
    
    # Commit all changes at once
    if cancelled:
        await session.commit()
    
    logger.info(
        "Batch cancel completed",
        total=len(job_ids),
        cancelled_count=len(cancelled),
        failed_count=len(failed),
    )
    
    return {
        "cancelled": cancelled,
        "failed": failed,
        "total": len(job_ids),
        "cancelled_count": len(cancelled),
        "failed_count": len(failed),
    }


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str, session: AsyncSession = Depends(get_session)) -> None:
    job_uuid = _parse_job_id(job_id)
    job = await session.get(Job, job_uuid)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Job not found: '{job_id}'. "
                f"Cannot cancel a job that doesn't exist. "
                f"Use scheduler_list_jobs() or scheduler_search_jobs() to find valid job IDs."
            )
        )

    job.status = JobStatus.CANCELLED.value
    job.next_run_at = None
    job.updated_at = datetime.now(timezone.utc)
    await session.commit()

    await scheduler_service.remove_job(job_uuid)


@router.post("/{job_id}/executions", response_model=job_schemas.ExecutionResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> job_schemas.ExecutionResponse:
    """Manually trigger a job execution."""
    job_uuid = _parse_job_id(job_id)
    job = await _load_job(session, job_uuid)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Job not found: '{job_id}'. "
                f"Cannot trigger execution for a job that doesn't exist. "
                f"Use scheduler_list_jobs() or scheduler_search_jobs() to find valid job IDs."
            )
        )
    
    # Trigger the job immediately via the scheduler service
    execution_id = await scheduler_service.trigger_job(job_uuid)
    
    # Return the execution details
    execution = await session.get(Execution, execution_id)
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Execution not created for job '{job_id}'. "
                f"This is an internal error. The execution ID '{execution_id}' was returned but the execution record was not found. "
                f"Please try again or check the scheduler service logs."
            )
        )
    
    return job_schemas.ExecutionResponse.from_model(execution)


@router.get("/{job_id}/executions", response_model=List[job_schemas.ExecutionResponse])
async def list_executions(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> List[job_schemas.ExecutionResponse]:
    job_uuid = _parse_job_id(job_id)
    result = await session.execute(
        select(Execution)
        .where(Execution.job_id == job_uuid)
        .order_by(Execution.scheduled_at.desc())
    )
    executions = result.scalars().all()
    return [job_schemas.ExecutionResponse.from_model(execution) for execution in executions]


@router.get("/executions/{execution_id}", response_model=job_schemas.ExecutionResponse)
async def get_execution(
    execution_id: str,
    session: AsyncSession = Depends(get_session),
) -> job_schemas.ExecutionResponse:
    try:
        execution_uuid = uuid.UUID(execution_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid execution ID format: '{execution_id}'. "
                f"Execution IDs must be valid UUIDs (e.g., '550e8400-e29b-41d4-a716-446655440000'). "
                f"Use scheduler_list_executions(job_id) to find execution IDs for a job."
            )
        ) from exc

    execution = await session.get(Execution, execution_uuid)
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Execution not found: '{execution_id}'. "
                f"The execution may have been deleted, or the ID is incorrect. "
                f"Use scheduler_list_executions(job_id) to find valid execution IDs for a job."
            )
        )
    return job_schemas.ExecutionResponse.from_model(execution)

