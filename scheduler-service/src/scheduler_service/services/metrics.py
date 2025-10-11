"""In-memory metrics for scheduler observability."""

from __future__ import annotations

from typing import Dict

_metrics: Dict[str, int] = {
    "executions_total": 0,
    "executions_success": 0,
    "executions_failed": 0,
}


def record_execution(status: str) -> None:
    _metrics["executions_total"] += 1
    if status == "success":
        _metrics["executions_success"] += 1
    elif status == "failed":
        _metrics["executions_failed"] += 1


def get_metrics() -> Dict[str, int]:
    return dict(_metrics)
