"""Slack Analytics Export Service."""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Tuple

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("slack-analytics-service")

SCRIPT_PATH = os.getenv("SLACK_ANALYTICS_SCRIPT_PATH", "/app/slack_analytics_with_dates.py")
AUTH_FILE = os.getenv("SLACK_ANALYTICS_AUTH_FILE", "/app/slack_auth_state.json")
SCREENSHOT_DIR = os.getenv("SLACK_ANALYTICS_SCREENSHOT_DIR", "/app/slack_analytics_screenshots")
PYTHON_BIN = os.getenv("SLACK_ANALYTICS_PYTHON_BIN", "python")
REQUEST_TIMEOUT = int(os.getenv("SLACK_ANALYTICS_TIMEOUT", "120"))
HEADLESS = os.getenv("SLACK_ANALYTICS_HEADLESS", "true").lower() != "false"

app = FastAPI(title="Slack Analytics Export Service")


class ExportRequest(BaseModel):
    """Incoming payload describing the desired export."""

    analytics_type: Literal["channels", "members"] = "channels"
    days_ago: int = Field(default=3, ge=0, le=60)
    date_range_days: int = Field(default=1, ge=1, le=30)


@app.on_event("startup")
async def ensure_directories() -> None:
    """Create required directories when the service boots."""

    Path(SCREENSHOT_DIR).mkdir(parents=True, exist_ok=True)
    logger.info("Slack analytics service initialized")


@app.get("/health")
async def healthcheck() -> dict:
    """Return service health information."""

    script_exists = Path(SCRIPT_PATH).exists()
    auth_present = Path(AUTH_FILE).exists()
    return {
        "status": "healthy" if script_exists else "degraded",
        "service": "slack-analytics-export",
        "script": script_exists,
        "auth_file": auth_present,
    }


def _calculate_dates(days_ago: int, range_days: int) -> Tuple[str, str]:
    """
    Translate relative offsets into concrete ISO date strings.
    
    IMPORTANT: Slack does not allow exports when start_date == end_date.
    If range_days would result in the same date, it's automatically adjusted to ensure
    at least a 1-day range.
    """

    end_date = datetime.now() - timedelta(days=days_ago)
    start_date = end_date - timedelta(days=range_days - 1)
    
    # Ensure start_date != end_date (Slack requirement)
    if start_date.date() == end_date.date():
        # If they're the same, make end_date one day later
        end_date = start_date + timedelta(days=1)
        logger.warning(
            "Date range would be same day, adjusted end_date to %s",
            end_date.strftime("%Y-%m-%d")
        )
    
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


def _build_command(request: ExportRequest) -> Tuple[list[str], dict]:
    """Prepare the CLI arguments passed to the export script."""

    start_date, end_date = _calculate_dates(request.days_ago, request.date_range_days)
    cmd = [
        PYTHON_BIN,
        SCRIPT_PATH,
        "--type",
        request.analytics_type,
        "--start-date",
        start_date,
        "--end-date",
        end_date,
        "--auth-file",
        AUTH_FILE,
        "--screenshot-dir",
        SCREENSHOT_DIR,
    ]
    if HEADLESS:
        cmd.append("--headless")

    metadata = {
        "start": start_date,
        "end": end_date,
    }
    return cmd, metadata


@app.post("/trigger-export")
async def trigger_export(request: ExportRequest) -> dict:
    """Trigger the Slack analytics export via automation script."""

    if not Path(SCRIPT_PATH).exists():
        logger.error("Slack analytics script missing at %s", SCRIPT_PATH)
        raise HTTPException(status_code=500, detail="Slack analytics script not found")

    cmd, metadata = _build_command(request)
    logger.info(
        "Triggering Slack analytics export", extra={"analytics_type": request.analytics_type, **metadata}
    )

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=REQUEST_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("Slack analytics export timed out", exc_info=True)
        raise HTTPException(status_code=504, detail=f"Export timed out after {REQUEST_TIMEOUT}s") from exc
    except FileNotFoundError as exc:
        logger.exception("Python binary not found: %s", PYTHON_BIN)
        raise HTTPException(status_code=500, detail="Python binary not available in container") from exc

    response_payload = {
        "success": completed.returncode == 0,
        "analytics_type": request.analytics_type,
        "date_range": metadata,
        "stdout": (completed.stdout or "").strip(),
        "stderr": (completed.stderr or "").strip(),
    }

    if completed.returncode == 0:
        message = (
            f"✓ Export triggered for {metadata['start']} to {metadata['end']}. "
            "CSV will be available in Slack shortly."
        )
        response_payload["message"] = message
        logger.info("Slack analytics export succeeded")
        return response_payload

    logger.error(
        "Slack analytics export failed",
        extra={
            "returncode": completed.returncode,
            "stdout_tail": (completed.stdout or "")[-200:],
            "stderr_tail": (completed.stderr or "")[-200:],
        },
    )
    raise HTTPException(status_code=500, detail=response_payload)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.app:app", host="0.0.0.0", port=int(os.getenv("SLACK_ANALYTICS_PORT", "8087")))
