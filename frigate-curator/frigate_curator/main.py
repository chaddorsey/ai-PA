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

from . import classifier, curator, db, deep_dive, notify, sss_client, web_push
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
        "VAPID_PRIVATE_KEY", "VAPID_PUBLIC_KEY", "VAPID_SUBJECT",
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

    # Special buckets that come from the per-user actions / remixes
    # tables. We pull a generous over-fetch (limit*4, capped) before
    # applying camera/since/until/hour filters in Python, then trim to
    # `limit`. Cheap given typical fave-set sizes (≤100s of clips).
    def _passes_filters(r: dict) -> bool:
        if camera and r.get("camera") != camera: return False
        if since is not None and (r.get("start_time") or 0) < since: return False
        if until is not None and (r.get("start_time") or 0) > until: return False
        if hour_from is not None and hour_to is not None:
            import datetime
            t = datetime.datetime.fromtimestamp(r.get("start_time") or 0)
            h = t.hour
            if hour_from <= hour_to:
                if not (hour_from <= h < hour_to): return False
            else:
                if not (h >= hour_from or h < hour_to): return False
        return True

    rows: list[dict[str, Any]]
    if bucket == "mine":
        if not email:
            raise HTTPException(status_code=400, detail="bucket=mine requires email")
        ids = db.list_my_favorites(DB_PATH, email, limit=max(limit*4, 200), offset=0)
        rows = [r for r in (db.get_highlight(DB_PATH, eid) for eid in ids) if r and _passes_filters(r)]
        rows = rows[offset:offset+limit]
    elif bucket == "shared":
        pairs = db.list_shared_favorites(DB_PATH, limit=max(limit*4, 200), offset=0)
        rows = []
        for eid, _n in pairs:
            r = db.get_highlight(DB_PATH, eid)
            if r and _passes_filters(r):
                rows.append(r)
        rows = rows[offset:offset+limit]
    elif bucket == "remixes":
        with db.connect(DB_PATH) as conn:
            ids = [r["event_id"] for r in conn.execute(
                "SELECT DISTINCT event_id FROM remixes "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [max(limit*4, 200), 0],
            ).fetchall()]
        rows = [r for r in (db.get_highlight(DB_PATH, eid) for eid in ids) if r and _passes_filters(r)]
        rows = rows[offset:offset+limit]
    else:
        rows = db.list_highlights(
            DB_PATH,
            camera=camera, since=since, until=until,
            min_score=min_score, bucket=bucket,
            hour_from=hour_from, hour_to=hour_to,
            limit=limit, offset=offset,
            email=email,
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
    rxs = db.remix_list_for_event(DB_PATH, event_id)
    rids = [r["remix_id"] for r in rxs]
    likes = db.remix_likes_bulk(DB_PATH, rids, email=email or None)
    for r in rxs:
        st = likes.get(r["remix_id"], {"like_count": 0, "my_liked": False})
        r["like_count"] = st["like_count"]
        r["my_liked"] = st["my_liked"]
    h["remixes"] = rxs
    h["remix_count"] = len(rxs)
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


@app.delete("/highlights/{event_id}")
def delete_highlight(event_id: str) -> dict[str, Any]:
    """Hard-delete a highlight: DB row, per-user actions, remixes, and
    the on-disk clip + thumbnail. Caller is responsible for auth (the
    proxy enforces admin-only).
    """
    h = db.get_highlight(DB_PATH, event_id)
    if not h:
        raise HTTPException(status_code=404, detail="not found")
    # Remove on-disk media first; even if it fails the DB cleanup
    # below proceeds so a partial state doesn't strand an orphan row.
    for sub in ("clip_path", "thumb_path"):
        rel = h.get(sub)
        if not rel: continue
        try: (HIGHLIGHTS_ROOT / rel).unlink()
        except FileNotFoundError: pass
        except Exception as e: logger.warning("delete %s: %s", rel, e)
    with db.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM remixes WHERE event_id = ?", [event_id])
        conn.execute("DELETE FROM highlight_user_actions WHERE highlight_id = ?", [event_id])
        conn.execute("DELETE FROM highlights WHERE event_id = ?", [event_id])
    return {"status": "deleted", "event_id": event_id}


@app.post("/highlights/{event_id}/unflag_no_foxes")
def unflag_no_foxes(event_id: str, body: ActionBody) -> dict[str, Any]:
    """Restore a clip from the No Foxes bucket — globally.

    "No Foxes" is shared: as soon as ANY user demotes a clip, it
    moves to the No Foxes bucket for everyone (the curator's bucket
    query keys off the aggregate `demoted=1` column). Clearing one
    user's vote isn't enough to bring it back, because other users'
    demotes still flag it. This endpoint clears ALL demote votes
    across all users for a given highlight, returning it to the
    main view for the entire family. Caller (proxy) is responsible
    for showing the user a warning before invoking.
    """
    if not body.by:
        raise HTTPException(status_code=400, detail="unflag requires a 'by' email")
    if not db.get_highlight(DB_PATH, event_id):
        raise HTTPException(status_code=404, detail="not found")
    import time as _time
    now = _time.time()
    with db.connect(DB_PATH) as conn:
        conn.execute(
            "DELETE FROM highlight_user_actions WHERE highlight_id = ? AND action = 'demote'",
            [event_id],
        )
        # _refresh_aggregate recomputes highlights.demoted from the per-user table.
        db._refresh_aggregate(conn, event_id, body.by, now)
    return {"status": "unflagged", "highlight": _highlight_with_state(event_id, body.by)}


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
def get_remix(remix_id: str, email: str | None = None) -> dict[str, Any]:
    r = db.remix_get(DB_PATH, remix_id)
    if not r:
        raise HTTPException(status_code=404, detail="remix not found")
    h = db.get_highlight(DB_PATH, r["event_id"])
    likes = db.remix_likes_for_remix(DB_PATH, remix_id, email=email)
    r = dict(r)
    r["like_count"] = likes["like_count"]
    r["my_liked"] = likes["my_liked"]
    return {"remix": r, "highlight": h}


@app.get("/remixes")
def list_remixes(email: str | None = None,
                  event_id: str | None = None,
                  created_by: str | None = None,
                  liked_by_email: str | None = None,
                  limit: int = Query(default=100, ge=1, le=1000),
                  offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    """`email` is the *viewer* — used purely for my_liked enrichment.
    `created_by` filters by remix author (legacy fox-cam-public 'mine'
    scope used to send this as `email`; the proxy now sends both).
    `liked_by_email` restricts to remixes that user has liked (powers
    the "Liked by Me" status filter on the Remix view)."""
    if event_id:
        items = db.remix_list_for_event(DB_PATH, event_id)
    elif created_by:
        items = db.remix_list_for_user(DB_PATH, created_by,
                                        limit=limit, offset=offset)
    else:
        items = db.remix_list_recent(DB_PATH, limit=limit, offset=offset)
    if liked_by_email:
        keep = db.remix_ids_liked_by(DB_PATH, liked_by_email)
        items = [it for it in items if it["remix_id"] in keep]
    # Enrich with like_count + my_liked in one bulk query (avoids N+1).
    rids = [it["remix_id"] for it in items]
    likes = db.remix_likes_bulk(DB_PATH, rids, email=email)
    for it in items:
        st = likes.get(it["remix_id"], {"like_count": 0, "my_liked": False})
        it["like_count"] = st["like_count"]
        it["my_liked"] = st["my_liked"]
    return {"items": items, "count": len(items)}


@app.post("/remixes/{remix_id}/like")
def like_remix(remix_id: str, email: str | None = None) -> dict[str, Any]:
    """Idempotent like. First-time-from-this-user generates an in-app
    notification for the remix's author (skipped when liker == author).
    """
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    r = db.remix_get(DB_PATH, remix_id)
    if not r:
        raise HTTPException(status_code=404, detail="remix not found")
    count, was_new = db.remix_like_add(DB_PATH, remix_id, email)
    if was_new:
        author = r.get("created_by") or ""
        # Don't notify yourself for liking your own remix.
        if author and author.lower() != email.lower():
            db.notif_create(
                DB_PATH,
                recipient_email=author,
                kind="remix_like",
                payload={
                    "remix_id": remix_id,
                    "remix_title": r.get("title") or "",
                    "event_id": r.get("event_id"),
                    "liker_email": email,
                },
            )
            # Best-effort Web Push to all of the author's subscribed
            # devices (gated on their remix_like preference). Errors
            # are swallowed inside web_push so the like flow never
            # blocks on push delivery.
            try:
                liker_handle = email.split("@", 1)[0] if "@" in email else email
                title = r.get("title") or "(untitled)"
                public_base = notify._PUBLIC_BASE
                web_push.send_to_user(
                    DB_PATH, author, "remix_like",
                    {
                        "title": "New like on your remix",
                        "body":  f"@{liker_handle} liked “{title}”",
                        "url":   f"{public_base}/remix/{remix_id}",
                        "tag":   f"remix-like-{remix_id}",
                        "kind":  "remix_like",
                    },
                )
            except Exception:
                logger.exception("web_push remix_like failed for %s", remix_id)
    return {
        "remix_id": remix_id,
        "like_count": count,
        "my_liked": True,
        "was_new": was_new,
    }


@app.get("/notifications")
def list_notifications(email: str | None = None,
                        unread_only: bool = False,
                        limit: int = Query(default=50, ge=1, le=200),
                        offset: int = Query(default=0, ge=0)
                        ) -> dict[str, Any]:
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    items = db.notif_list(DB_PATH, email, limit=limit, offset=offset,
                           unread_only=unread_only)
    return {"items": items, "count": len(items)}


@app.get("/notifications/unread_count")
def unread_count(email: str | None = None) -> dict[str, Any]:
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    return {"unread_count": db.notif_unread_count(DB_PATH, email)}


@app.post("/notifications/{notif_id}/read")
def mark_notification_read(notif_id: int, email: str | None = None
                            ) -> dict[str, Any]:
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    ok = db.notif_mark_read(DB_PATH, notif_id, email)
    return {"updated": ok}


@app.post("/notifications/mark_all_read")
def mark_all_read(email: str | None = None) -> dict[str, Any]:
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    n = db.notif_mark_all_read(DB_PATH, email)
    return {"updated": n}


# ---------------------------------------------------------------------------
# Web Push — VAPID keys, subscriptions, preferences, test send
# ---------------------------------------------------------------------------

class PushSubscribeBody(BaseModel):
    email: str
    endpoint: str
    keys: dict[str, str]
    user_agent: str | None = None


class PushPrefBody(BaseModel):
    email: str
    kind: str
    enabled: bool | None = None
    value: str | None = None


class PushPauseBody(BaseModel):
    email: str
    paused_until: float | None = None


class PushScheduleAddBody(BaseModel):
    email: str
    start_min: int
    end_min: int
    tz_offset_min: int = 0


@app.get("/push/vapid-public-key")
def vapid_public_key() -> dict[str, Any]:
    """Public VAPID key — meant to be public. The client fetches once
    and passes it to pushManager.subscribe."""
    if not web_push.is_configured():
        raise HTTPException(status_code=503, detail="web push not configured")
    return {"public_key": web_push.vapid_public_key()}


@app.post("/push/subscriptions")
def subscribe(body: PushSubscribeBody) -> dict[str, Any]:
    """Idempotent on endpoint — re-subscribing a known device just
    refreshes the keys + last_seen_at."""
    p256dh = body.keys.get("p256dh", "")
    auth = body.keys.get("auth", "")
    if not (body.email and body.endpoint and p256dh and auth):
        raise HTTPException(status_code=400, detail="missing fields")
    sub_id = db.push_sub_save(
        DB_PATH, email=body.email, endpoint=body.endpoint,
        p256dh=p256dh, auth=auth, user_agent=body.user_agent,
    )
    return {"id": sub_id, "ok": True}


@app.delete("/push/subscriptions")
def unsubscribe(endpoint: str) -> dict[str, Any]:
    ok = db.push_sub_delete_by_endpoint(DB_PATH, endpoint)
    return {"deleted": ok}


@app.get("/push/subscriptions")
def list_subscriptions(email: str | None = None) -> dict[str, Any]:
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    subs = db.push_sub_list_for_email(DB_PATH, email)
    # Don't leak the keys back to the client — just metadata for the
    # "your devices" listing in the settings panel.
    safe = [{"id": s["id"], "user_agent": s["user_agent"],
             "created_at": s["created_at"], "last_seen_at": s["last_seen_at"]}
            for s in subs]
    return {"items": safe, "count": len(safe)}


@app.get("/push/preferences")
def get_preferences(email: str | None = None) -> dict[str, Any]:
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    prefs = db.push_pref_get_all(DB_PATH, email)
    return {"preferences": prefs}


@app.post("/push/preferences")
def set_preference(body: PushPrefBody) -> dict[str, Any]:
    if not body.email or not body.kind:
        raise HTTPException(status_code=400, detail="email + kind required")
    if body.enabled is None and body.value is None:
        raise HTTPException(status_code=400,
                             detail="enabled or value required")
    db.push_pref_set(DB_PATH, body.email, body.kind,
                      enabled=body.enabled, value=body.value)
    return {"ok": True, "kind": body.kind,
            "enabled": body.enabled, "value": body.value}


@app.get("/push/pause")
def get_pause(email: str | None = None) -> dict[str, Any]:
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    until = db.push_pause_get(DB_PATH, email)
    return {"paused_until": until,
            "active": db.push_pause_active(DB_PATH, email)}


@app.post("/push/pause")
def set_pause(body: PushPauseBody) -> dict[str, Any]:
    if not body.email:
        raise HTTPException(status_code=400, detail="email required")
    db.push_pause_set(DB_PATH, body.email, body.paused_until)
    return {"ok": True, "paused_until": body.paused_until}


@app.get("/push/schedule")
def get_schedule(email: str | None = None) -> dict[str, Any]:
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    return {"intervals": db.push_schedule_list(DB_PATH, email)}


@app.post("/push/schedule")
def add_schedule_interval(body: PushScheduleAddBody) -> dict[str, Any]:
    if not body.email:
        raise HTTPException(status_code=400, detail="email required")
    try:
        new_id = db.push_schedule_add(
            DB_PATH, body.email,
            int(body.start_min), int(body.end_min),
            int(body.tz_offset_min),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": new_id}


@app.delete("/push/schedule/{interval_id}")
def delete_schedule_interval(interval_id: int,
                              email: str | None = None) -> dict[str, Any]:
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    return {"deleted": db.push_schedule_delete(DB_PATH, interval_id, email)}


@app.post("/push/test")
def push_test(email: str | None = None) -> dict[str, Any]:
    """Operator/dev convenience — fires a synthetic push to every
    subscribed device for `email`, regardless of preference. Used by
    the Send Test Push button in the settings panel."""
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    if not web_push.is_configured():
        raise HTTPException(status_code=503, detail="web push not configured")
    subs = db.push_sub_list_for_email(DB_PATH, email)
    sent = 0
    for s in subs:
        if web_push.send_to_subscription(
            DB_PATH, s,
            {"title": "Our Foxes — test push",
             "body":  "If you can read this, push works on this device.",
             "url":   f"{notify._PUBLIC_BASE}/highlights",
             "tag":   "push-test",
             "kind":  "test"},
        ):
            sent += 1
    return {"sent": sent, "device_count": len(subs)}


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


REMIX_DOWNLOAD_CACHE_ROOT = Path(os.environ.get(
    "REMIX_DOWNLOAD_CACHE_ROOT", str(HIGHLIGHTS_ROOT / "remix-download-cache")
))


@app.get("/remixes/{remix_id}/download")
def download_remix(remix_id: str, filename: str | None = None) -> FileResponse:
    """Render the remix as a trimmed (+ cropped, if zoomed) MP4 for download.

    Re-encodes via ffmpeg the first time and caches the result on disk
    keyed by remix_id + a hash of the trim/zoom params, so subsequent
    downloads are an instant FileResponse.
    """
    import hashlib
    import subprocess

    r = db.remix_get(DB_PATH, remix_id)
    if not r:
        raise HTTPException(status_code=404, detail="remix not found")
    h = db.get_highlight(DB_PATH, r["event_id"])
    if not h:
        raise HTTPException(status_code=404, detail="parent highlight not found")
    src = HIGHLIGHTS_ROOT / h["clip_path"]
    if not src.exists():
        raise HTTPException(status_code=410, detail="parent clip file missing")

    start_s = float(r.get("start_offset_s") or 0.0)
    end_s = float(r.get("end_offset_s") or 0.0)
    if end_s <= start_s:
        raise HTTPException(status_code=400, detail="invalid trim range")
    zoom_scale = float(r.get("zoom_scale") or 1.0)
    zoom_x = float(r.get("zoom_x") if r.get("zoom_x") is not None else 0.5)
    zoom_y = float(r.get("zoom_y") if r.get("zoom_y") is not None else 0.5)

    key_src = f"{remix_id}|{start_s:.3f}|{end_s:.3f}|{zoom_scale:.3f}|{zoom_x:.4f}|{zoom_y:.4f}"
    key_hash = hashlib.md5(key_src.encode()).hexdigest()[:12]
    cache_dir = REMIX_DOWNLOAD_CACHE_ROOT
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{remix_id}_{key_hash}.mp4"

    if not cache_path.exists():
        vf = None
        if zoom_scale > 1.01:
            # iw/ih are input frame dimensions. cw,ch = crop window;
            # cx,cy = crop top-left in pixel space, clamped to frame.
            scale_expr = f"{zoom_scale:.6f}"
            cw = f"iw/{scale_expr}"
            ch = f"ih/{scale_expr}"
            cx = f"max(0\\,min(iw-{cw}\\,iw*{zoom_x:.6f}-({cw})/2))"
            cy = f"max(0\\,min(ih-{ch}\\,ih*{zoom_y:.6f}-({ch})/2))"
            vf = f"crop={cw}:{ch}:{cx}:{cy}"

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start_s:.3f}",
            "-to", f"{end_s:.3f}",
            "-i", str(src),
        ]
        if vf:
            cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "20", "-c:a", "aac", "-b:a", "128k"]
        else:
            cmd += ["-c", "copy"]
        cmd += ["-movflags", "+faststart", str(cache_path)]

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            try: cache_path.unlink(missing_ok=True)
            except Exception: pass
            raise HTTPException(status_code=500, detail=f"ffmpeg failed: {e}") from e

    safe_name = (filename or f"remix-{remix_id}.mp4")
    safe_name = safe_name.replace('"', "").replace("\n", "").replace("\r", "")
    return FileResponse(
        cache_path, media_type="video/mp4", filename=safe_name,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


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
