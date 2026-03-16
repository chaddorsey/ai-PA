"""Task Completion Service.

Receives push notifications from OmniFocus completion watcher plugin,
processes completions (archival updates, follow-up routing), and notifies MC.
Also provides a reconciliation endpoint and recent completions query.
"""
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from completion_processor import (
    find_extracted_task,
    update_passage_completed,
    notify_mc,
    parse_timing_from_note,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("task-completion-service")

app = FastAPI(title="Task Completion Service", version="1.0.0")

# ── State ─────────────────────────────────────────────────────────
STATE_DIR = Path(os.environ.get("STATE_DIR", "/data"))
DEDUP_FILE = STATE_DIR / "processed_completions.json"

# In-memory dedup set: {task_id: completion_date_iso}
processed: dict[str, str] = {}
# Recent completions ring buffer
recent_completions: list[dict] = []
MAX_RECENT = 50


def load_dedup_state():
    """Load dedup state from disk, prune entries older than 30 days."""
    global processed
    if DEDUP_FILE.exists():
        try:
            data = json.loads(DEDUP_FILE.read_text())
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            processed = {k: v for k, v in data.items() if v > cutoff}
        except Exception as e:
            logger.error(f"Failed to load dedup state: {e}")
            processed = {}


def save_dedup_state():
    """Persist dedup state to disk."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DEDUP_FILE.write_text(json.dumps(processed))


@app.on_event("startup")
async def startup():
    load_dedup_state()
    logger.info(f"Loaded {len(processed)} dedup entries")


# ── Models ────────────────────────────────────────────────────────

class CompletionEvent(BaseModel):
    task_id: str
    task_name: str
    note: str = ""
    completion_date: str
    was_dropped: bool = False
    project_name: Optional[str] = None
    tags: list[str] = []


# ── Endpoints ─────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "processed_count": len(processed), "recent_count": len(recent_completions)}


@app.post("/v1/completion")
async def receive_completion(event: CompletionEvent):
    """Receive a completion notification from the OmniFocus plugin."""

    # Dedup check
    if event.task_id in processed:
        logger.info(f"Duplicate completion for {event.task_id}, skipping")
        return {"status": "ok", "action": "duplicate_skipped"}

    logger.info(f"Processing completion: {event.task_name} ({event.task_id})")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Check if this is an extracted task
        extraction_info = None
        passage = await find_extracted_task(event.task_id, client)
        if passage:
            logger.info(f"Found extracted task passage for {event.task_id}")
            extraction_info = await update_passage_completed(
                passage, event.completion_date, event.was_dropped, client
            )

        # Parse timing data from note
        timing_summary = parse_timing_from_note(event.note) if event.note else None

        # Record completion
        record = {
            "task_id": event.task_id,
            "task_name": event.task_name,
            "completion_date": event.completion_date,
            "was_dropped": event.was_dropped,
            "project_name": event.project_name,
            "timing": timing_summary,
            "is_extracted": passage is not None,
            "extraction_info": extraction_info,
        }
        recent_completions.append(record)
        if len(recent_completions) > MAX_RECENT:
            recent_completions.pop(0)

        # Mark as processed
        processed[event.task_id] = event.completion_date
        save_dedup_state()

        # Notify MC
        await notify_mc(
            event.task_name,
            event.project_name,
            event.completion_date,
            timing_summary,
            extraction_info,
            client,
        )

    action = "processed_extracted" if passage else "processed_standalone"
    return {"status": "ok", "action": action}


@app.get("/v1/completions/recent")
async def get_recent_completions(limit: int = 20):
    """Query recent completions."""
    return {"completions": recent_completions[-limit:]}
