"""
Lightweight FastAPI wrapper for the scheduling orchestrator.

Exposes orchestrate_scheduling() as an HTTP endpoint so services
(slackbot, pa-web-ui) can call it directly without Letta LLM inference.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Scheduling Orchestrator API", version="1.0.0")
logger = logging.getLogger("scheduling_orchestrator.server")
logging.basicConfig(level=logging.INFO)

# Letta base URL for identity lookups (orchestrator uses this internally)
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")


class ScheduleRequest(BaseModel):
    """Request body for the /schedule endpoint."""
    utterance: str = Field(..., description="Natural language scheduling request")
    participant_ids: Optional[List[str]] = Field(None, description="Participant email addresses")
    user_id: Optional[str] = Field(None, description="Requester's email address")
    context_json: Optional[str] = Field(None, description="JSON string with timeframe, participants, policy")
    event_id: Optional[str] = Field(None, description="Explicit event ID for rescheduling")
    event_participant_id: Optional[str] = Field(None, description="Event participant email for rescheduling")


@app.get("/health")
def health():
    return {"status": "ok", "service": "scheduling-orchestrator-api"}


@app.post("/schedule")
def schedule(req: ScheduleRequest) -> Dict[str, Any]:
    """Call orchestrate_scheduling() directly and return the result."""
    start = time.time()
    logger.info("Schedule request: utterance=%r, participants=%s, user=%s",
                req.utterance[:80], req.participant_ids, req.user_id)

    try:
        from orchestrate_scheduling import orchestrate_scheduling
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Failed to import orchestrator: {e}")

    try:
        result = orchestrate_scheduling(
            utterance=req.utterance,
            participant_ids=req.participant_ids,
            user_id=req.user_id,
            context_json=req.context_json,
            event_id=req.event_id,
            event_participant_id=req.event_participant_id,
        )
    except Exception as e:
        logger.error("Orchestrator error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    elapsed_ms = int((time.time() - start) * 1000)
    logger.info("Schedule complete: status=%s, elapsed=%dms", result.get("status"), elapsed_ms)

    # Ensure result is JSON-serializable (convert dataclasses/pydantic models)
    return _make_serializable(result)


def _make_serializable(obj: Any) -> Any:
    """Recursively convert pydantic models and dataclasses to dicts."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if hasattr(obj, "model_dump"):
        return _make_serializable(obj.model_dump())
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses
        return _make_serializable(dataclasses.asdict(obj))
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serializable(item) for item in obj]
    # Fallback: try str
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)
