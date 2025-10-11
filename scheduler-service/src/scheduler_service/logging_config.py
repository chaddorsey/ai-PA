"""Logging configuration for the scheduler service."""

from __future__ import annotations

import logging
from typing import Any

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Configure standard logging and structlog."""

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(message)s",
        handlers=[logging.StreamHandler()],
    )

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger with service metadata bound."""

    logger = structlog.get_logger(name)
    return logger.bind(service="scheduler-service")


