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

from . import curator, db
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
    allow = {"FRIGATE_PASS", "FRIGATE_USER", "FRIGATE_BASE_URL"}
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
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    rows = db.list_highlights(
        DB_PATH, camera=camera, since=since, until=until,
        min_score=min_score, limit=limit, offset=offset,
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
