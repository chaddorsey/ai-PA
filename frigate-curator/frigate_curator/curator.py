"""Event-loop logic: poll Frigate, evaluate, copy clips.

Designed to be embarrassingly idempotent. We track the highest event
end_time we've seen and only ask Frigate for events after that. If the
service crashes mid-copy, the next iteration sees the event again and
re-copies (overwriting). SQLite UPSERT means duplicate processing is a
no-op.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from . import classifier, db, hls, notify, web_push
from .frigate_client import FrigateClient
from .heuristics import fox_likelihood


logger = logging.getLogger(__name__)


_FFPROBE = shutil.which("ffprobe")
_FFMPEG = shutil.which("ffmpeg")


def _faststart_remux(clip_path: Path) -> bool:
    """Re-mux the MP4 with -movflags +faststart so the moov atom is at
    the front of the file. Without this, browsers use a tiny initial
    buffer for video.duration and the scrubber shows ~3s at first
    until the trailing moov is fetched. -c copy means no transcode,
    just container rewrite. Returns True on success.
    """
    if not _FFMPEG or not clip_path.exists():
        return False
    tmp = clip_path.with_suffix(".tmp.mp4")
    try:
        subprocess.run(
            [_FFMPEG, "-y", "-loglevel", "error", "-i", str(clip_path),
             "-c", "copy", "-movflags", "+faststart", str(tmp)],
            check=True, timeout=30,
        )
        tmp.replace(clip_path)
        return True
    except Exception as e:
        logger.debug("faststart remux failed on %s: %s", clip_path, e)
        try: tmp.unlink()
        except Exception: pass
        return False


def _probe_clip_duration(clip_path: Path) -> float | None:
    """Return the on-disk clip's actual duration in seconds, or None.

    Used to display the playback length on the card instead of the
    tracked-object lifetime (the saved clip is bracketed by Frigate's
    pre_capture + post_capture seconds, so a 5s tracked event lands
    in a ~55s file).
    """
    if not _FFPROBE or not clip_path.exists():
        return None
    try:
        out = subprocess.run(
            [_FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(clip_path)],
            capture_output=True, text=True, timeout=8,
        )
        v = (out.stdout or "").strip()
        return float(v) if v else None
    except Exception as e:
        logger.debug("ffprobe failed on %s: %s", clip_path, e)
        return None


# Labels we care about. COCO-80 has no "fox" so we copy dog/cat AND
# person events — at our 704x480 substream resolution YOLO regularly
# misclassifies crouched foxes (especially kits) as person. The
# gpt-4o-mini classifier downstream sorts wildlife from real humans
# (species='person' → curator filters auto-demote in default views).
INTERESTING_LABELS = {"animal", "dog", "cat", "person"}

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
    import sqlite3
    events = client.list_events(after=since, labels=list(INTERESTING_LABELS))
    if not events:
        return since

    # Frigate returns events sorted by start_time DESC (newest first).
    # Process them OLDEST-FIRST so the cursor advances chronologically
    # — if a DB error halts the loop mid-batch, the next tick picks up
    # exactly where we stopped instead of jumping past unfinished work.
    # The `2026-05-10 disconnect lost ~5h of events` incident motivated
    # this: previously the cursor advanced regardless of whether the
    # save succeeded, so a transient DB outage permanently lost any
    # events that arrived during it.
    new_max = since
    for event in reversed(events):
        end = event.get("end_time")
        if end is None:
            # Still in progress; we'll see it again next tick when ended.
            continue
        try:
            _process_event(client, highlights_root, db_path, event)
        except sqlite3.OperationalError as e:
            # DB unreachable (typical cause: main-drive or main-filestore
            # disconnect mid-tick). Halt cursor advance so this event +
            # everything newer is retried on the next tick. The outer
            # _run loop catches the broader Exception path; we return
            # the still-stale cursor so it's preserved across ticks.
            logger.error("Cursor halted at event %s: DB unavailable: %s",
                         event.get("id"), e)
            return new_max
        except Exception:
            # Per-event failure (corrupt clip, classifier API down,
            # ffmpeg edge case, etc). Advance past it — retrying the
            # same event forever is worse than skipping one bad clip.
            logger.exception("Failed to process event %s", event.get("id"))
        new_max = max(new_max, end)
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

    # Move the MP4's moov atom to the front so browsers know the
    # total duration immediately on first load. Without this the
    # scrubber initially shows ~3s and only catches up once the
    # browser fetches the trailing moov.
    _faststart_remux(clip_dest)

    # The on-disk clip's actual duration. Frigate records each event
    # with pre_capture + tracked_window + post_capture seconds of
    # video, so e.g. a 5s tracked object lands in a ~55s clip file.
    # Use the file's real duration on the card so what the user sees
    # matches the playback length.
    clip_duration = _probe_clip_duration(clip_dest) or (end_time - start_time)

    db.upsert_highlight(db_path, {
        "event_id": event_id,
        "camera": camera,
        "label": label,
        "start_time": start_time,
        "end_time": end_time,
        "duration_s": clip_duration,
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

    # NOTE: HLS prewarm at ingestion time is *intentionally* not fired
    # here. ffmpeg's segment writes contend with SQLite reads on the
    # same `main-filestore` volume, and a stream of new events can
    # serialize enough I/O behind the prewarm to time out concurrent
    # /api/highlights API requests at the 30s proxy ceiling — the
    # symptom is users seeing 500s on the gallery list.
    #
    # The lazy-render path on /highlights/{id}/hls/index.m3u8 still
    # exists, fires only when a user actually opens an HLS-aware
    # modal, and is throttled to a single concurrent ffmpeg via the
    # semaphore in hls.py. The Phase 5 backfill script does
    # explicit, throttled bulk rendering.

    # Wildlife classification (no-op if disabled). Updates DB with
    # species + confidence; notification gating below uses the result.
    verdict = classifier.classify_clip(clip_dest)
    if verdict is not None:
        raw = "; ".join(f"{f.species}/{f.confidence}: {f.description}"
                        for f in verdict.frames)
        db.update_classification(
            db_path, event_id, verdict.species, verdict.confidence,
            classifier._MODEL, time.time(), raw,
        )
        logger.info("Classified %s as %s (%s); is_wildlife=%s",
                    event_id, verdict.species, verdict.confidence,
                    verdict.is_wildlife)

    # Push notification. Two pipelines:
    #   1) Legacy ntfy.sh — uses its own NOTIFY_THRESHOLD (gated inside
    #      maybe_notify). Kept for the handful of users still
    #      subscribed via the ntfy app.
    #   2) Web Push — fires for every clip that would appear in the
    #      Active gallery (i.e. species NOT in the suppress list, or
    #      unclassified). The per-user severity filter inside
    #      web_push.broadcast_kind ("all" / "clusters" / "high") then
    #      decides whether each subscriber actually receives the push.
    #      No global likelihood threshold here — that decision moves
    #      to the user via the Notification preferences panel.
    SUPPRESS_SPECIES = {"none", "person", "vehicle", "error"}
    fresh = db.get_highlight(db_path, event_id)
    if fresh:
        species = ((verdict.species if verdict else fresh.get("species")) or "").lower()
        if species in SUPPRESS_SPECIES:
            logger.info("Skipping notification for %s (species=%s)",
                        event_id, species)
        else:
            sent_legacy = notify.maybe_notify(fresh)
            try:
                cam = fresh.get("camera", "unknown")
                likelihood = float(fresh.get("fox_likelihood") or 0.0)
                duration = float(fresh.get("duration_s") or 0.0)
                pct = int(round(likelihood * 100))
                # Title shows percentage only when the heuristic is
                # confident; otherwise just the camera name to avoid
                # parading a 0% next to a "raccoon" classification.
                title = (f"Fox Cam — {cam} ({pct}%)" if likelihood >= notify._THRESHOLD
                         else f"Our Foxes — {cam}")
                # Body prefers the classifier's species over Frigate's
                # generic label when we have one — "raccoon · 12s" beats
                # "animal · 12s".
                body_subject = species if species else (fresh.get("label") or "motion")
                payload = {
                    "title": title,
                    "body":  f"{body_subject} · {duration:.0f}s",
                    # Same-origin RELATIVE path — iOS routes a tap on a
                    # PWA-context push back into the installed PWA only
                    # when the URL is relative (or the origin matches
                    # the SW's). Absolute URLs sometimes hand off to
                    # Safari on iOS 17+, even from inside the PWA SW.
                    "url":   f"/clip/{event_id}",
                    "tag":   f"highlight-{event_id}",
                    "kind":  "new_highlight",
                    # Enrichment fields used by the per-user severity
                    # filter inside web_push.send_*.
                    "camera":         cam,
                    "fox_likelihood": likelihood,
                    "duration_s":     duration,
                }
                web_push.broadcast_kind(db_path, "new_highlight", payload)
            except Exception:
                logger.exception("web_push broadcast failed for %s", event_id)
            if sent_legacy:
                db.mark_notified(db_path, event_id, time.time())


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
    _faststart_remux(clip_dest)

    clip_duration = _probe_clip_duration(clip_dest) or (end_time - start_time)
    now = time.time()
    db.upsert_highlight(db_path, {
        "event_id": event_id,
        "camera": camera,
        "label": label,
        "start_time": start_time,
        "end_time": end_time,
        "duration_s": clip_duration,
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
