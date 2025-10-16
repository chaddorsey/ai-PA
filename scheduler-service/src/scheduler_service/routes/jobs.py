"""Job management endpoints."""

import json
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
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
from scheduler_service.services.embeddings import embed_texts
from scheduler_service.services.scheduler import scheduler_service
from scheduler_service.services.actions import execute_action, ActionExecutionError
from scheduler_service.services.schedule_parser import parse_schedule, ScheduleParseError

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = get_logger(__name__)


def _parse_job_id(job_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job ID") from exc


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
                status_code=400,
                detail=f"Invalid schedule expression: {e.reason}"
            )
        except Exception as e:
            logger.error(f"Unexpected error parsing schedule: {e}", exc_info=True)
            raise HTTPException(
                status_code=400,
                detail=f"Failed to parse schedule: {str(e)}"
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
    status_filter: JobStatus | None = None,
    session: AsyncSession = Depends(get_session),
) -> List[job_schemas.JobResponse]:
    query = (
        select(Job)
        .options(selectinload(Job.metadata_entries), selectinload(Job.actions))
        .order_by(Job.next_run_at)
    )
    if status_filter:
        query = query.where(Job.status == status_filter.value)
    result = await session.execute(query)
    jobs = result.scalars().all()
    return [job_schemas.JobResponse.from_model(job) for job in jobs]


@router.get("/{job_id}", response_model=job_schemas.JobResponse)
async def get_job(job_id: str, session: AsyncSession = Depends(get_session)) -> job_schemas.JobResponse:
    job_uuid = _parse_job_id(job_id)
    job = await _load_job(session, job_uuid)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
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
        job.status = payload.status.value
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


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str, session: AsyncSession = Depends(get_session)) -> None:
    job_uuid = _parse_job_id(job_id)
    job = await session.get(Job, job_uuid)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    
    # Trigger the job immediately via the scheduler service
    execution_id = await scheduler_service.trigger_job(job_uuid)
    
    # Return the execution details
    execution = await session.get(Execution, execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Execution not created")
    
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid execution ID") from exc

    execution = await session.get(Execution, execution_uuid)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return job_schemas.ExecutionResponse.from_model(execution)


