"""Event-loop logic: poll Frigate, evaluate, copy clips.

Designed to be embarrassingly idempotent. We track the highest event
end_time we've seen and only ask Frigate for events after that. If the
service crashes mid-copy, the next iteration sees the event again and
re-copies (overwriting). SQLite UPSERT means duplicate processing is a
no-op.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from . import db
from .frigate_client import FrigateClient
from .heuristics import fox_likelihood


logger = logging.getLogger(__name__)


# Labels we care about. COCO-80 has no "fox", so we copy dog/cat events
# at all hours and tag with fox_likelihood. The viewer can filter.
INTERESTING_LABELS = {"dog", "cat"}

# Always-copy threshold. Even daytime "probably a pet" events still get
# saved because the user can re-classify (or we'll add a person-with-dog
# discriminator later). Set to 0.0 to keep everything; raise to 0.5 if
# you only want clear fox candidates.
SAVE_THRESHOLD = 0.0


def run_loop(
    client: FrigateClient,
    highlights_root: Path,
    db_path: Path,
    poll_interval_s: float = 5.0,
    bootstrap_lookback_s: float = 3600,
) -> None:
    """Forever-loop. Caller wraps in a thread or runs as the main process."""
    db.init(db_path)

    # On startup, look back 1 hour so we don't miss events emitted during
    # a brief restart, but don't dredge up the entire database.
    since = time.time() - bootstrap_lookback_s
    logger.info("Curator starting; bootstrap since=%s", _fmt(since))

    while True:
        try:
            since = _tick(client, highlights_root, db_path, since)
        except Exception:
            logger.exception("Tick failed; will retry")
        time.sleep(poll_interval_s)


def _tick(client: FrigateClient, highlights_root: Path, db_path: Path, since: float) -> float:
    events = client.list_events(after=since, labels=list(INTERESTING_LABELS))
    if not events:
        return since

    new_max = since
    for event in events:
        end = event.get("end_time")
        if end is None:
            # Still in progress; we'll see it again next tick when ended.
            continue
        new_max = max(new_max, end)
        try:
            _process_event(client, highlights_root, db_path, event)
        except Exception:
            logger.exception("Failed to process event %s", event.get("id"))
    return new_max


def _process_event(client: FrigateClient, highlights_root: Path, db_path: Path, event: dict) -> None:
    event_id: str = event["id"]
    if db.get_highlight(db_path, event_id):
        return  # already curated

    label = event.get("label") or ""
    camera = event.get("camera") or "unknown"
    start_time = float(event["start_time"])
    end_time = float(event["end_time"])
    score = float(event.get("top_score") or event.get("score") or 0.0)
    likelihood = fox_likelihood(start_time, label, score)

    if likelihood < SAVE_THRESHOLD:
        return

    day = datetime.fromtimestamp(start_time, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")
    day_dir = highlights_root / day
    clip_dest = day_dir / f"{event_id}.mp4"
    thumb_dest = day_dir / f"{event_id}.jpg"

    if not client.download_clip(event_id, clip_dest):
        logger.warning("No clip available for event %s", event_id)
        return
    client.download_thumbnail(event_id, thumb_dest)

    db.upsert_highlight(db_path, {
        "event_id": event_id,
        "camera": camera,
        "label": label,
        "start_time": start_time,
        "end_time": end_time,
        "duration_s": end_time - start_time,
        "score": score,
        "fox_likelihood": likelihood,
        "clip_path": str(clip_dest.relative_to(highlights_root)),
        "thumb_path": str(thumb_dest.relative_to(highlights_root)) if thumb_dest.exists() else None,
        "promoted": 0,
        "promoted_at": None,
        "notes": None,
    })
    logger.info(
        "Saved %s [%s] camera=%s label=%s likelihood=%.2f duration=%.1fs",
        event_id, _fmt(start_time), camera, label, likelihood, end_time - start_time,
    )


def promote(client: FrigateClient, highlights_root: Path, db_path: Path, event_id: str) -> dict:
    """Manually copy a Frigate event into highlights, regardless of heuristic."""
    existing = db.get_highlight(db_path, event_id)
    if existing:
        db.mark_promoted(db_path, event_id, time.time())
        return {"status": "already_present", "highlight": db.get_highlight(db_path, event_id)}

    event = client.get_event(event_id)
    if event is None:
        return {"status": "not_found"}

    # Force-process bypassing the threshold by inflating likelihood to 1.0
    # only for the storage call. The heuristic value we record stays honest.
    label = event.get("label") or ""
    camera = event.get("camera") or "unknown"
    start_time = float(event["start_time"])
    end_time = float(event.get("end_time") or start_time)
    score = float(event.get("top_score") or event.get("score") or 0.0)
    likelihood = fox_likelihood(start_time, label, score)

    day = datetime.fromtimestamp(start_time, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")
    day_dir = highlights_root / day
    clip_dest = day_dir / f"{event_id}.mp4"
    thumb_dest = day_dir / f"{event_id}.jpg"

    if not client.download_clip(event_id, clip_dest):
        return {"status": "no_clip"}
    client.download_thumbnail(event_id, thumb_dest)

    now = time.time()
    db.upsert_highlight(db_path, {
        "event_id": event_id,
        "camera": camera,
        "label": label,
        "start_time": start_time,
        "end_time": end_time,
        "duration_s": end_time - start_time,
        "score": score,
        "fox_likelihood": likelihood,
        "clip_path": str(clip_dest.relative_to(highlights_root)),
        "thumb_path": str(thumb_dest.relative_to(highlights_root)) if thumb_dest.exists() else None,
        "promoted": 1,
        "promoted_at": now,
        "notes": None,
    })
    return {"status": "promoted", "highlight": db.get_highlight(db_path, event_id)}


def _fmt(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")
