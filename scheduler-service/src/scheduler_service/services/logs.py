"""Logging utilities for scheduler service."""

from __future__ import annotations

from typing import Any

import structlog


logger = structlog.get_logger("scheduler-service")


def job_logger(job_id: str):
    return logger.bind(job_id=job_id)


def execution_logger(job_id: str, execution_id: str):
    return logger.bind(job_id=job_id, execution_id=execution_id)


def action_logger(job_id: str, execution_id: str, action_id: str):
    return logger.bind(job_id=job_id, execution_id=execution_id, action_id=action_id)
