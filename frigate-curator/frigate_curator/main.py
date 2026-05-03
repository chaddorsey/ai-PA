"""Entry point: FastAPI app + background curator loop.

Run with:
    poetry run uvicorn frigate_curator.main:app --host 127.0.0.1 --port 5141

Or via launchd: see deployment/launchd/com.ai-pa.frigate-curator.plist.

The HTTP API exposes only read endpoints + the manual promotion endpoint.
It binds to 127.0.0.1 — public exposure happens later via the Phase 11
viewer service, which talks to this on the loopback.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import classifier, curator, db, notify
from .frigate_client import FrigateClient


def _load_dotenv(path: Path = Path("/Volumes/main-drive/ai-PA/.env")) -> None:
    """Pull a small allowlist of vars from .env into the process env.

    launchd doesn't auto-source .env files. Rather than commit secrets
    into the plist's EnvironmentVariables (which is gitignored only by
    convention), read them at startup. Only specific keys are taken so
    that an unrelated .env entry can't shadow something we care about.
    """
    if not path.is_file():
        return
    allow = {
        "FRIGATE_PASS", "FRIGATE_USER", "FRIGATE_BASE_URL",
        "NTFY_TOPIC", "NTFY_BASE_URL", "FOX_PUBLIC_BASE_URL", "NOTIFY_THRESHOLD",
        "LITELLM_BASE_URL", "LITELLM_MASTER_KEY",
        "CLASSIFIER_ENABLED", "CLASSIFIER_MODEL", "CLASSIFIER_FRAMES",
    }
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k in allow and not os.environ.get(k):
            os.environ[k] = v


_load_dotenv()


# ---------------------------------------------------------------------------
# Config — env-driven so launchd / docker-compose can tune without code edits.
# ---------------------------------------------------------------------------

FRIGATE_BASE_URL = os.environ.get("FRIGATE_BASE_URL", "https://localhost:8971")
FRIGATE_USER = os.environ.get("FRIGATE_USER", "admin")
FRIGATE_PASS = os.environ.get("FRIGATE_PASS", "")  # set in .env
HIGHLIGHTS_ROOT = Path(os.environ.get("HIGHLIGHTS_ROOT", "/Volumes/main-filestore/frigate-highlights"))
DB_PATH = Path(os.environ.get("CURATOR_DB", str(HIGHLIGHTS_ROOT / "index.db")))
POLL_INTERVAL_S = float(os.environ.get("POLL_INTERVAL_S", "5"))

# Notification config. NTFY_TOPIC empty disables all push (default).
# Set in .env to a long unguessable string; share with family in the
# ntfy iOS/Android app. Threshold is fox_likelihood; 0.55 ≈ "above
# baseline noise" given heuristics' time/confidence weighting.
NTFY_BASE_URL = os.environ.get("NTFY_BASE_URL", "https://ntfy.sh")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
FOX_PUBLIC_BASE_URL = os.environ.get("FOX_PUBLIC_BASE_URL", "https://foxes.cd-ai-pa.work")
NOTIFY_THRESHOLD = float(os.environ.get("NOTIFY_THRESHOLD", "0.55"))

# Classifier (Track 1) — vision-model species ID via litellm. Calibrated
# on a 22-clip spike (2026-05-03): gpt-4o-mini at 91% accuracy with
# 100% wildlife recall and 100% empty-frame specificity. Gemini 2.0
# Flash is 86%/100%/78% — cheaper but more false-positive-prone.
LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000")
LITELLM_API_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
CLASSIFIER_ENABLED = os.environ.get("CLASSIFIER_ENABLED", "false").lower() == "true"
CLASSIFIER_MODEL = os.environ.get("CLASSIFIER_MODEL", "gpt-4o-mini/fox-cam")
CLASSIFIER_FRAMES = int(os.environ.get("CLASSIFIER_FRAMES", "5"))


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("frigate_curator")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Frigate Curator", version="0.1.0")
_client = FrigateClient(FRIGATE_BASE_URL, FRIGATE_USER, FRIGATE_PASS)


@app.on_event("startup")
def _startup() -> None:
    HIGHLIGHTS_ROOT.mkdir(parents=True, exist_ok=True)
    db.init(DB_PATH)
    notify.configure(NTFY_BASE_URL, NTFY_TOPIC or None, FOX_PUBLIC_BASE_URL, NOTIFY_THRESHOLD)
    if NTFY_TOPIC:
        logger.info("ntfy push enabled: %s/%s threshold=%.2f", NTFY_BASE_URL, NTFY_TOPIC, NOTIFY_THRESHOLD)
    else:
        logger.info("ntfy push disabled (NTFY_TOPIC not set)")

    classifier.configure(
        LITELLM_BASE_URL, LITELLM_API_KEY, CLASSIFIER_MODEL,
        CLASSIFIER_FRAMES, CLASSIFIER_ENABLED,
    )
    if CLASSIFIER_ENABLED:
        logger.info("Classifier enabled: model=%s frames=%d via %s",
                    CLASSIFIER_MODEL, CLASSIFIER_FRAMES, LITELLM_BASE_URL)
    else:
        logger.info("Classifier disabled (set CLASSIFIER_ENABLED=true to turn on)")
    if not FRIGATE_PASS:
        logger.error("FRIGATE_PASS not set; curator will fail to authenticate. Set it in .env.")
        return
    t = threading.Thread(
        target=curator.run_loop,
        kwargs={
            "client": _client,
            "highlights_root": HIGHLIGHTS_ROOT,
            "db_path": DB_PATH,
            "poll_interval_s": POLL_INTERVAL_S,
        },
        name="curator-loop",
        daemon=True,
    )
    t.start()
    logger.info("Curator loop thread started; polling every %.1fs", POLL_INTERVAL_S)


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "ok", "highlights_root": str(HIGHLIGHTS_ROOT), "db": str(DB_PATH)}


@app.get("/highlights")
def list_highlights(
    camera: str | None = None,
    since: float | None = Query(default=None, description="unix epoch seconds"),
    until: float | None = Query(default=None, description="unix epoch seconds"),
    min_score: float = Query(default=0.0, ge=0.0, le=1.0),
    bucket: str = Query(default="pending", regex="^(pending|all|favorites|demoted)$"),
    time_of_day: str = Query(default="any", regex="^(any|day|night)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    # Day = 6am–6pm local; Night = 6pm–6am local (wraps midnight)
    hour_from = hour_to = None
    if time_of_day == "day":
        hour_from, hour_to = 6, 18
    elif time_of_day == "night":
        hour_from, hour_to = 18, 6

    rows = db.list_highlights(
        DB_PATH,
        camera=camera, since=since, until=until,
        min_score=min_score, bucket=bucket,
        hour_from=hour_from, hour_to=hour_to,
        limit=limit, offset=offset,
    )
    return {"items": rows, "count": len(rows)}


@app.get("/highlights/{event_id}")
def get_highlight(event_id: str) -> dict[str, Any]:
    h = db.get_highlight(DB_PATH, event_id)
    if not h:
        raise HTTPException(status_code=404, detail="not found")
    return h


@app.get("/highlights/{event_id}/clip")
def get_highlight_clip(event_id: str) -> FileResponse:
    h = db.get_highlight(DB_PATH, event_id)
    if not h:
        raise HTTPException(status_code=404, detail="not found")
    path = HIGHLIGHTS_ROOT / h["clip_path"]
    if not path.exists():
        raise HTTPException(status_code=410, detail="clip file missing")
    return FileResponse(path, media_type="video/mp4")


@app.get("/highlights/{event_id}/thumbnail")
def get_highlight_thumb(event_id: str) -> FileResponse:
    h = db.get_highlight(DB_PATH, event_id)
    if not h or not h.get("thumb_path"):
        raise HTTPException(status_code=404, detail="no thumbnail")
    path = HIGHLIGHTS_ROOT / h["thumb_path"]
    if not path.exists():
        raise HTTPException(status_code=410, detail="thumbnail file missing")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/stats")
def get_stats() -> dict[str, Any]:
    return db.stats(DB_PATH)


# ---------------------------------------------------------------------------
# Write endpoint — only one. Manual promotion of a Frigate event.
# ---------------------------------------------------------------------------

@app.post("/promote/{event_id}")
def promote_event(event_id: str) -> dict[str, Any]:
    return curator.promote(_client, HIGHLIGHTS_ROOT, DB_PATH, event_id)


@app.post("/classify/{event_id}")
def classify_event(event_id: str) -> dict[str, Any]:
    """Run the classifier on an existing highlight (manual trigger).

    Useful for back-filling clips saved before the classifier existed,
    or re-classifying after a prompt/model change.
    """
    h = db.get_highlight(DB_PATH, event_id)
    if not h:
        raise HTTPException(status_code=404, detail="not found")
    path = HIGHLIGHTS_ROOT / h["clip_path"]
    if not path.exists():
        raise HTTPException(status_code=410, detail="clip file missing")
    # Force-enable for manual call even if env says disabled.
    was_enabled = classifier._ENABLED
    classifier._ENABLED = True
    try:
        verdict = classifier.classify_clip(path)
    finally:
        classifier._ENABLED = was_enabled
    if verdict is None:
        raise HTTPException(status_code=503, detail="classifier not configured")
    raw = "; ".join(f"{f.species}/{f.confidence}: {f.description}"
                    for f in verdict.frames)
    import time as _time
    db.update_classification(
        DB_PATH, event_id, verdict.species, verdict.confidence,
        classifier._MODEL, _time.time(), raw,
    )
    return {
        "event_id": event_id,
        "species": verdict.species,
        "confidence": verdict.confidence,
        "is_wildlife": verdict.is_wildlife,
        "frames": [{"species": f.species, "confidence": f.confidence,
                    "description": f.description} for f in verdict.frames],
    }


@app.post("/notify/test")
def notify_test() -> dict[str, Any]:
    """Send a synthetic ntfy push to confirm config + family subscriptions."""
    if not NTFY_TOPIC:
        raise HTTPException(status_code=400, detail="NTFY_TOPIC not configured")
    fake = {
        "event_id": "test-" + str(int(__import__("time").time())),
        "camera": "test",
        "label": "test",
        "duration_s": 1.0,
        "fox_likelihood": 0.99,
    }
    sent = notify.maybe_notify(fake)
    return {"sent": sent, "topic": NTFY_TOPIC, "threshold": NOTIFY_THRESHOLD}


# ---------------------------------------------------------------------------
# Family-vote actions. Each action is attributed to whoever's logged in via
# Cloudflare Access (their email is forwarded by fox-cam-public from the
# cf-access-authenticated-user-email header).
# ---------------------------------------------------------------------------

class ActionBody(BaseModel):
    by: str | None = None  # email; optional for now (will always be set in production)


@app.post("/highlights/{event_id}/favorite")
def favorite_event(event_id: str, body: ActionBody) -> dict[str, Any]:
    row = db.set_action(DB_PATH, event_id, "favorite", body.by)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "favorited", "highlight": row}


@app.post("/highlights/{event_id}/demote")
def demote_event(event_id: str, body: ActionBody) -> dict[str, Any]:
    row = db.set_action(DB_PATH, event_id, "demote", body.by)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "demoted", "highlight": row}


@app.post("/highlights/{event_id}/clear")
def clear_event(event_id: str, body: ActionBody) -> dict[str, Any]:
    row = db.set_action(DB_PATH, event_id, "clear", body.by)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "cleared", "highlight": row}
