"""Scheduler orchestration using APScheduler."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from scheduler_service.database import AsyncSessionFactory
from scheduler_service.logging_config import get_logger
from scheduler_service.models.job import (
    Execution,
    ExecutionOutput,
    ExecutionStatus,
    Job,
    JobStatus,
    ScheduleType,
)
from scheduler_service.settings import settings
from scheduler_service.services.logs import job_logger, execution_logger
from scheduler_service.services.metrics import record_execution
from scheduler_service.services.actions import execute_action, ActionExecutionError

logger = get_logger(__name__)


class SchedulerService:
    """Manage job scheduling lifecycle."""

    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)

    async def start(self) -> None:
        logger.info("Starting APScheduler")
        await self._load_existing_jobs()
        self.scheduler.start()

    async def shutdown(self) -> None:
        logger.info("Shutting down APScheduler")
        await self.scheduler.shutdown(wait=False)

    async def _load_existing_jobs(self) -> None:
        async with AsyncSessionFactory() as session:
            result = await session.execute(
                select(Job).where(Job.status == JobStatus.SCHEDULED.value)
            )
            jobs = result.scalars().all()
            for job in jobs:
                if job.next_run_at is not None:
                    self._schedule_job(job)
                else:
                    logger.warning(
                        "Job has no next_run_at; skipping scheduling",
                        job_id=str(job.job_id),
                    )
        logger.info("Loaded jobs into scheduler", count=len(jobs))

    def _schedule_job(self, job: Job) -> None:
        trigger = self._create_trigger(job)
        if trigger is None:
            logger.info(
                "Skipping scheduling; no next trigger",
                job_id=str(job.job_id),
            )
            return

        self.scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            id=str(job.job_id),
            args=[job.job_id],
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=120,
        )
        job_logger(str(job.job_id)).info("Scheduled job", trigger=str(trigger))

    def _create_trigger(self, job: Job):
        if job.next_run_at is None and job.schedule_type != ScheduleType.ONE_OFF.value:
            return None

        if job.schedule_type == ScheduleType.CRON.value:
            cron_expr = job.schedule_expression.get("cron")
            if not cron_expr:
                return None
            return CronTrigger.from_crontab(cron_expr, timezone=settings.scheduler_timezone)
        if job.schedule_type == ScheduleType.INTERVAL.value:
            interval_seconds = job.schedule_expression.get("seconds")
            if not interval_seconds:
                return None
            return IntervalTrigger(seconds=interval_seconds, timezone=settings.scheduler_timezone)
        if job.schedule_type == ScheduleType.ONE_OFF.value:
            run_date = job.schedule_expression.get("run_at") or job.next_run_at
            if not run_date:
                return None
            return DateTrigger(run_date=run_date)
        raise ValueError(f"Unsupported schedule type: {job.schedule_type}")

    async def refresh_job(self, job_id: uuid.UUID) -> None:
        async with AsyncSessionFactory() as session:
            job: Optional[Job] = await session.get(Job, job_id)
            if not job or job.status != JobStatus.SCHEDULED.value:
                self.remove_job(job_id)
                return
            self._schedule_job(job)

    async def remove_job(self, job_id: uuid.UUID) -> None:
        try:
            self.scheduler.remove_job(str(job_id))
            logger.info("Removed job from scheduler", job_id=str(job_id))
        except Exception:  # pragma: no cover - APScheduler raises JobLookupError
            logger.debug("Job not present in scheduler", job_id=str(job_id))
    
    async def trigger_job(self, job_id: uuid.UUID) -> uuid.UUID:
        """Manually trigger a job execution immediately, bypassing the schedule."""
        logger.info("Manually triggering job", job_id=str(job_id))
        
        # Create execution record immediately
        async with AsyncSessionFactory() as session:
            execution = Execution(
                job_id=job_id,
                scheduled_at=datetime.now(timezone.utc),
                status=ExecutionStatus.RUNNING.value,
            )
            session.add(execution)
            await session.commit()
            await session.refresh(execution)
            execution_id = execution.execution_id
        
        # Schedule immediate one-off execution
        self.scheduler.add_job(
            self._execute_job,
            trigger=DateTrigger(run_date=datetime.now(timezone.utc)),
            id=f"manual-trigger-{execution_id}",
            args=[job_id],
            max_instances=1,
        )
        
        return execution_id

    async def _execute_job(self, job_id: uuid.UUID) -> None:
        log = execution_logger(str(job_id), "pending")
        log.info("Executing job")
        async with AsyncSessionFactory() as session:
            # Eagerly load actions to avoid lazy-loading issues in async context
            stmt = (
                select(Job)
                .where(Job.job_id == job_id)
                .options(selectinload(Job.actions))
            )
            result = await session.execute(stmt)
            job = result.scalar_one_or_none()
            
            if not job:
                log.warning("Job not found, removing from scheduler")
                self.scheduler.remove_job(str(job_id))
                return

            execution = Execution(
                job_id=job.job_id,
                scheduled_at=datetime.now(timezone.utc),
                status=ExecutionStatus.RUNNING.value,
            )
            session.add(execution)
            await session.commit()

            log = execution_logger(str(job.job_id), str(execution.execution_id))

            try:
                for action in job.actions:
                    # action_type is already a string from DB, no need for .value
                    action_type_str = action.action_type if isinstance(action.action_type, str) else action.action_type.value
                    result = await execute_action(action_type_str, action.config)
                    # result is a dict with 'status' and 'output' keys
                    output = ExecutionOutput(
                        execution_id=execution.execution_id,
                        action_id=action.action_id,
                        output_type=result.get("status", "unknown"),
                        output_data=result.get("output", {}),
                    )
                    session.add(output)
                    await session.commit()
                    log.info("Action completed", action_id=str(action.action_id), status=result.get("status"))

                execution.status = ExecutionStatus.SUCCEEDED.value
                log.info("Execution succeeded")
            except ActionExecutionError as exc:
                execution.status = ExecutionStatus.FAILED.value
                execution.log_summary = str(exc)
                log.warning("Execution failed", error=str(exc))
            finally:
                execution.completed_at = datetime.now(timezone.utc)
                
                # For one-off jobs, mark as COMPLETED after execution
                if job.schedule_type == ScheduleType.ONE_OFF.value:
                    job.status = JobStatus.COMPLETED.value
                    job.updated_at = datetime.now(timezone.utc)
                    # Remove from scheduler since it won't run again
                    await scheduler_service.remove_job(job.job_id)
                    log.info("One-off job marked as completed")
                
                await session.commit()
                record_execution("success" if execution.status == ExecutionStatus.SUCCEEDED.value else "failed")


scheduler_service = SchedulerService()


async def shutdown_scheduler() -> None:
    """Gracefully shutdown the scheduler service."""

    await scheduler_service.shutdown()


