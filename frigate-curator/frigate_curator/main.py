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

from . import classifier, curator, db, deep_dive, notify, sss_client
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
        "SSS_BASE_URL", "SSS_USER", "SSS_PASS",
        "SSS_CAM_ID_FOX_DEN_1", "SSS_CAM_ID_FOX_DEN_2",
        "SSS_CAM_ID_FOX_DEN_3", "SSS_CAM_ID_FOX_DEN_4",
        "DEEP_DIVE_CACHE_ROOT",
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

# Deep-dive cache root — where we save SSS-sourced clip windows.
# Defaults under HIGHLIGHTS_ROOT so backups capture both highlights and
# deep-dive cache in one filesystem snapshot.
DEEP_DIVE_CACHE_ROOT = Path(os.environ.get(
    "DEEP_DIVE_CACHE_ROOT", str(HIGHLIGHTS_ROOT / "deep-dive-cache")
))


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
    bucket: str = Query(default="pending", regex="^(pending|all|favorites|demoted|mine|shared|remixes)$"),
    time_of_day: str = Query(default="any", regex="^(any|day|night)$"),
    status: str = Query(default="active", regex="^(any|active|archived)$"),
    email: str | None = Query(default=None, description="viewer email for 'mine' bucket"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    # Day = 6am–6pm local; Night = 6pm–6am local (wraps midnight)
    hour_from = hour_to = None
    if time_of_day == "day":
        hour_from, hour_to = 6, 18
    elif time_of_day == "night":
        hour_from, hour_to = 18, 6

    # Special buckets that come from the per-user actions table:
    #  - 'mine'   : highlights this user has favorited (newest first)
    #  - 'shared' : highlights favorited by 2+ family members
    rows: list[dict[str, Any]]
    if bucket == "mine":
        if not email:
            raise HTTPException(status_code=400, detail="bucket=mine requires email")
        ids = db.list_my_favorites(DB_PATH, email, limit=limit, offset=offset)
        rows = [r for r in (db.get_highlight(DB_PATH, eid) for eid in ids) if r]
    elif bucket == "shared":
        pairs = db.list_shared_favorites(DB_PATH, limit=limit, offset=offset)
        rows = []
        for eid, _n in pairs:
            r = db.get_highlight(DB_PATH, eid)
            if r:
                rows.append(r)
    elif bucket == "remixes":
        # Highlights that have at least one remix. Newest-clip-first.
        with db.connect(DB_PATH) as conn:
            ids = [r["event_id"] for r in conn.execute(
                "SELECT DISTINCT event_id FROM remixes "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [limit, offset],
            ).fetchall()]
        rows = [r for r in (db.get_highlight(DB_PATH, eid) for eid in ids) if r]
    else:
        rows = db.list_highlights(
            DB_PATH,
            camera=camera, since=since, until=until,
            min_score=min_score, bucket=bucket,
            hour_from=hour_from, hour_to=hour_to,
            limit=limit, offset=offset,
        )

    # Attach per-user vote data + remix counts to every card, then
    # apply the per-user status filter (active = not archived by me;
    # archived = archived by me; any = no filter).
    if rows:
        ids = [r["event_id"] for r in rows]
        votes = db.list_user_actions_bulk(DB_PATH, ids)
        remix_counts = db.remix_counts_bulk(DB_PATH, ids)
        for r in rows:
            v = votes.get(r["event_id"], {})
            favorites = v.get("favorites", [])
            archives = v.get("archives", [])
            r["favorite_voters"] = favorites
            r["favorite_count"] = len(favorites)
            r["my_favorited"] = bool(email and email in favorites)
            r["my_demoted"] = bool(email and email in v.get("demotes", []))
            r["my_archived"] = bool(email and email in archives)
            r["archive_count"] = len(archives)
            r["remix_count"] = remix_counts.get(r["event_id"], 0)
        if status == "active":
            rows = [r for r in rows if not r.get("my_archived")]
        elif status == "archived":
            rows = [r for r in rows if r.get("my_archived")]
        # status == "any" → keep everything

    return {"items": rows, "count": len(rows)}


@app.get("/highlights/{event_id}")
def get_highlight(event_id: str, email: str | None = None) -> dict[str, Any]:
    h = db.get_highlight(DB_PATH, event_id)
    if not h:
        raise HTTPException(status_code=404, detail="not found")
    state = db.get_user_state(DB_PATH, event_id, email or "")
    h.update({
        "my_favorited": state["my_favorited"] if email else False,
        "my_demoted": state["my_demoted"] if email else False,
        "favorite_voters": state["voters"],
        "favorite_count": state["favorite_count"],
    })
    # Attach remixes so the clip page can list them; also include the
    # count as a top-level field for parity with /highlights list rows.
    h["remixes"] = db.remix_list_for_event(DB_PATH, event_id)
    h["remix_count"] = len(h["remixes"])
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
# Per-user viewer state — "new highlights since you last visited" badging.
# Identity is the user's email, set by fox-cam-public from CF Access.
# ---------------------------------------------------------------------------

@app.get("/viewer/state")
def get_viewer_state(email: str | None = None) -> dict[str, Any]:
    if not email:
        # Anonymous viewer — return current count from epoch 0 = all unseen.
        new_count = db.count_new_since(DB_PATH, 0.0)
        return {"email": None, "last_seen_at": None, "new_count": new_count}
    state = db.get_viewer_state(DB_PATH, email)
    last_seen = state["last_seen_at"] if state else 0.0
    new_count = db.count_new_since(DB_PATH, last_seen)
    return {"email": email, "last_seen_at": last_seen, "new_count": new_count}


class SeenBody(BaseModel):
    email: str | None = None
    last_seen_at: float | None = None  # default = now


@app.post("/viewer/seen")
def mark_viewer_seen(body: SeenBody) -> dict[str, Any]:
    if not body.email:
        return {"status": "ignored", "reason": "anonymous"}
    import time as _time
    ts = body.last_seen_at if body.last_seen_at is not None else _time.time()
    db.update_viewer_state(DB_PATH, body.email, ts)
    return {"status": "ok", "email": body.email, "last_seen_at": ts}


# ---------------------------------------------------------------------------
# Write endpoint — only one. Manual promotion of a Frigate event.
# ---------------------------------------------------------------------------

@app.post("/promote/{event_id}")
def promote_event(event_id: str) -> dict[str, Any]:
    return curator.promote(_client, HIGHLIGHTS_ROOT, DB_PATH, event_id)


# ---------------------------------------------------------------------------
# Deep-dive — fetch a window from SSS for a given highlight.
#
# Usage: family clicks "+30s" / "+1m" on a highlight card. Viewer POSTs
# /highlights/<event_id>/deep-dive with desired window. We cache the
# result keyed by (event_id, before, after) so repeat requests are
# instant.
# ---------------------------------------------------------------------------

class DeepDiveBody(BaseModel):
    before_s: float = 15.0
    after_s: float = 30.0


@app.post("/highlights/{event_id}/deep-dive")
def deep_dive_event(event_id: str, body: DeepDiveBody) -> dict[str, Any]:
    h = db.get_highlight(DB_PATH, event_id)
    if not h:
        raise HTTPException(status_code=404, detail="not found")
    try:
        result = deep_dive.fetch_window(
            DEEP_DIVE_CACHE_ROOT,
            camera=h["camera"],
            target_ts=h["start_time"],
            before_s=body.before_s,
            after_s=body.after_s,
        )
    except deep_dive.DeepDiveError as e:
        msg = str(e)
        if "past retention" in msg:
            raise HTTPException(status_code=410, detail=msg)
        if "not configured" in msg:
            raise HTTPException(status_code=503, detail=msg)
        raise HTTPException(status_code=502, detail=msg)
    return {
        "event_id": event_id,
        "url": f"/deep-dive/{event_id}/{int(body.before_s)}_{int(body.after_s)}.mp4",
        "duration_s": result.duration_s,
        "cache_hit": result.cache_hit,
        "chunk_id": result.chunk_id,
    }


@app.get("/deep-dive/{event_id}/{spec}.mp4")
def serve_deep_dive_clip(event_id: str, spec: str) -> FileResponse:
    """Serve a previously-fetched deep-dive clip. spec format is
    '<before>_<after>' matching the fetch_window cache key."""
    h = db.get_highlight(DB_PATH, event_id)
    if not h:
        raise HTTPException(status_code=404, detail="not found")
    try:
        before_s, after_s = spec.split("_")
        before_s, after_s = float(before_s), float(after_s)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad spec")
    camera = h["camera"]
    key = f"{camera}_{int(h['start_time'])}_{int(before_s)}_{int(after_s)}"
    cache_path = DEEP_DIVE_CACHE_ROOT / camera / f"{key}.mp4"
    if not cache_path.exists():
        raise HTTPException(status_code=404, detail="window not yet fetched")
    return FileResponse(cache_path, media_type="video/mp4")


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
    if not body.by:
        raise HTTPException(status_code=400, detail="favorites require a 'by' email")
    if not db.get_highlight(DB_PATH, event_id):
        raise HTTPException(status_code=404, detail="not found")
    db.user_action_set(DB_PATH, event_id, body.by, "favorite")
    return {"status": "favorited", "highlight": _highlight_with_state(event_id, body.by)}


@app.post("/highlights/{event_id}/demote")
def demote_event(event_id: str, body: ActionBody) -> dict[str, Any]:
    if not body.by:
        raise HTTPException(status_code=400, detail="demotes require a 'by' email")
    if not db.get_highlight(DB_PATH, event_id):
        raise HTTPException(status_code=404, detail="not found")
    db.user_action_set(DB_PATH, event_id, body.by, "demote")
    return {"status": "demoted", "highlight": _highlight_with_state(event_id, body.by)}


@app.post("/highlights/{event_id}/archive")
def archive_event(event_id: str, body: ActionBody) -> dict[str, Any]:
    if not body.by:
        raise HTTPException(status_code=400, detail="archive requires a 'by' email")
    if not db.get_highlight(DB_PATH, event_id):
        raise HTTPException(status_code=404, detail="not found")
    db.user_action_set(DB_PATH, event_id, body.by, "archive")
    return {"status": "archived", "highlight": _highlight_with_state(event_id, body.by)}


@app.post("/highlights/{event_id}/unarchive")
def unarchive_event(event_id: str, body: ActionBody) -> dict[str, Any]:
    if not body.by:
        raise HTTPException(status_code=400, detail="unarchive requires a 'by' email")
    if not db.get_highlight(DB_PATH, event_id):
        raise HTTPException(status_code=404, detail="not found")
    db.user_action_clear_one(DB_PATH, event_id, body.by, "archive")
    return {"status": "unarchived", "highlight": _highlight_with_state(event_id, body.by)}


@app.post("/highlights/{event_id}/clear")
def clear_event(event_id: str, body: ActionBody) -> dict[str, Any]:
    if not body.by:
        raise HTTPException(status_code=400, detail="clear requires a 'by' email")
    if not db.get_highlight(DB_PATH, event_id):
        raise HTTPException(status_code=404, detail="not found")
    db.user_action_clear(DB_PATH, event_id, body.by)
    return {"status": "cleared", "highlight": _highlight_with_state(event_id, body.by)}


def _highlight_with_state(event_id: str, email: str) -> dict[str, Any]:
    h = db.get_highlight(DB_PATH, event_id)
    if not h:
        return {}
    state = db.get_user_state(DB_PATH, event_id, email)
    h.update({
        "my_favorited": state["my_favorited"],
        "my_demoted": state["my_demoted"],
        "my_archived": state.get("my_archived", False),
        "favorite_voters": state["voters"],
        "favorite_count": state["favorite_count"],
    })
    return h


# ---------------------------------------------------------------------------
# Featured — admin-curated highlights shown on the public landing page.
#
# Authorization is the caller's responsibility (fox-cam-public checks
# ADMIN_EMAILS before forwarding). The curator just records what was
# requested and trusts the upstream proxy.
# ---------------------------------------------------------------------------

class FeaturedBody(BaseModel):
    by: str | None = None      # admin email
    caption: str | None = None  # optional short blurb (≤140 chars)


@app.get("/featured")
def list_featured_endpoint(limit: int = Query(default=6, ge=1, le=24)) -> dict[str, Any]:
    """Public list of featured highlights for the landing page.

    Returns the same row shape as /highlights so card.js can render
    them without a parallel code path.
    """
    return {"highlights": db.list_featured(DB_PATH, limit=limit)}


@app.post("/highlights/{event_id}/feature")
def feature_event(event_id: str, body: FeaturedBody) -> dict[str, Any]:
    if not body.by:
        raise HTTPException(status_code=400, detail="feature requires a 'by' email")
    caption = (body.caption or "").strip() or None
    if caption and len(caption) > 140:
        raise HTTPException(status_code=400, detail="caption max 140 chars")
    h = db.set_featured(DB_PATH, event_id, featured=True, by=body.by, caption=caption)
    if h is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "featured", "highlight": h}


@app.post("/highlights/{event_id}/unfeature")
def unfeature_event(event_id: str, body: FeaturedBody) -> dict[str, Any]:
    if not body.by:
        raise HTTPException(status_code=400, detail="unfeature requires a 'by' email")
    h = db.set_featured(DB_PATH, event_id, featured=False)
    if h is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "unfeatured", "highlight": h}


# ---------------------------------------------------------------------------
# Remixes — user-defined sub-clips with optional zoom region.
# ---------------------------------------------------------------------------

class RemixCreateBody(BaseModel):
    by: str | None = None
    title: str | None = None
    start_offset_s: float
    end_offset_s: float
    zoom_x: float | None = None
    zoom_y: float | None = None
    zoom_scale: float = 1.0
    notes: str | None = None


class RemixUpdateBody(BaseModel):
    title: str | None = None
    start_offset_s: float | None = None
    end_offset_s: float | None = None
    zoom_x: float | None = None
    zoom_y: float | None = None
    zoom_scale: float | None = None
    notes: str | None = None


@app.post("/highlights/{event_id}/remix")
def create_remix(event_id: str, body: RemixCreateBody) -> dict[str, Any]:
    if not db.get_highlight(DB_PATH, event_id):
        raise HTTPException(status_code=404, detail="highlight not found")
    if body.end_offset_s <= body.start_offset_s:
        raise HTTPException(status_code=400, detail="end_offset_s must exceed start_offset_s")
    remix_id = db.remix_create(
        DB_PATH,
        event_id=event_id, created_by=body.by, title=body.title,
        start_offset_s=body.start_offset_s, end_offset_s=body.end_offset_s,
        zoom_x=body.zoom_x, zoom_y=body.zoom_y, zoom_scale=body.zoom_scale,
        notes=body.notes,
    )
    return {"remix_id": remix_id, "remix": db.remix_get(DB_PATH, remix_id)}


@app.get("/remixes/{remix_id}")
def get_remix(remix_id: str) -> dict[str, Any]:
    r = db.remix_get(DB_PATH, remix_id)
    if not r:
        raise HTTPException(status_code=404, detail="remix not found")
    h = db.get_highlight(DB_PATH, r["event_id"])
    return {"remix": r, "highlight": h}


@app.get("/remixes")
def list_remixes(email: str | None = None,
                  event_id: str | None = None,
                  limit: int = Query(default=100, ge=1, le=1000),
                  offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    if event_id:
        items = db.remix_list_for_event(DB_PATH, event_id)
    elif email:
        items = db.remix_list_for_user(DB_PATH, email, limit=limit, offset=offset)
    else:
        items = db.remix_list_recent(DB_PATH, limit=limit, offset=offset)
    return {"items": items, "count": len(items)}


@app.patch("/remixes/{remix_id}")
def update_remix(remix_id: str, body: RemixUpdateBody) -> dict[str, Any]:
    if not db.remix_get(DB_PATH, remix_id):
        raise HTTPException(status_code=404, detail="remix not found")
    db.remix_update(
        DB_PATH, remix_id,
        title=body.title, start_offset_s=body.start_offset_s,
        end_offset_s=body.end_offset_s,
        zoom_x=body.zoom_x, zoom_y=body.zoom_y,
        zoom_scale=body.zoom_scale, notes=body.notes,
    )
    return {"remix": db.remix_get(DB_PATH, remix_id)}


@app.delete("/remixes/{remix_id}")
def delete_remix(remix_id: str, by: str | None = None) -> dict[str, Any]:
    r = db.remix_get(DB_PATH, remix_id)
    if not r:
        raise HTTPException(status_code=404, detail="remix not found")
    # Creator-only delete (any logged-in family member can delete their
    # own remixes; not a moderator path yet).
    only_creator = r.get("created_by") if by else None
    if r.get("created_by") and by != r["created_by"]:
        raise HTTPException(status_code=403, detail="only creator may delete")
    db.remix_delete(DB_PATH, remix_id, only_creator=only_creator)
    return {"status": "deleted", "remix_id": remix_id}
