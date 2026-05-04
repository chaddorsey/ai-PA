"""Backfill detection over SSS motion-tagged chunks.

Recovers a window of footage that Frigate didn't process live (e.g.,
after a restart with detection toggled off, or during downtime).
Iterates motion-tagged 30-min chunks in SSS, uses ffmpeg's scene
filter to find candidate motion bursts within each, extracts a short
clip per burst, runs it through the existing Track-1 VLM classifier,
and inserts wildlife matches into the highlights DB tagged with
source='backfill'.

Skips:
- Frigate's YOLO step (we lean on the VLM, which the spike showed at
  100% wildlife recall and 100% empty-frame specificity over 22 clips
  — better signal than YOLO + heuristic alone).
- Notification gating — backfilled events are by definition past, so
  ntfy push is suppressed.

Usage (CLI):
    python -m frigate_curator.backfill --since "18 hours ago" [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable, Optional

from . import classifier, db, sss_client


logger = logging.getLogger(__name__)


# How aggressive scenedetect is — lower = more candidate bursts.
# 0.30 is a reasonable middle ground; raise to 0.45 for fewer false
# positives or drop to 0.20 to catch subtler motion.
DEFAULT_SCENE_THRESHOLD = 0.30

# Distance (seconds) below which two scene changes are considered the
# same motion burst — we cluster them to avoid producing overlapping
# clips.
CLUSTER_GAP_S = 12.0

# Window length per candidate burst (seconds before + after the scene
# change). Wider windows help the VLM lock on; narrower means more
# discrete events.
WINDOW_PRE_S = 5.0
WINDOW_POST_S = 10.0


@dataclass
class Candidate:
    camera: str                # canonical name (fox_den_1, etc.)
    chunk_id: int              # SSS event id
    chunk_start_ts: float
    burst_offset_s: float      # offset within chunk where motion occurred
    target_ts: float           # absolute UTC ts of the burst (chunk_start + offset)


def _scene_change_timestamps(chunk_path: Path,
                              threshold: float = DEFAULT_SCENE_THRESHOLD) -> list[float]:
    """Run ffmpeg scene filter, return list of timestamps (seconds within
    the chunk) where scene changes were detected."""
    cmd = [
        "ffmpeg", "-hide_banner", "-i", str(chunk_path),
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    timestamps: list[float] = []
    for line in r.stderr.splitlines():
        if "pts_time:" not in line or "showinfo" not in line:
            continue
        for tok in line.split():
            if tok.startswith("pts_time:"):
                try:
                    timestamps.append(float(tok.split(":", 1)[1]))
                except ValueError:
                    pass
    return timestamps


def _cluster_timestamps(timestamps: list[float],
                         gap: float = CLUSTER_GAP_S) -> list[float]:
    """Collapse timestamps that are within `gap` seconds into one
    representative (the earliest in the cluster). Eliminates
    overlapping windows from rapid scene changes."""
    if not timestamps:
        return []
    sorted_ts = sorted(timestamps)
    out = [sorted_ts[0]]
    for t in sorted_ts[1:]:
        if t - out[-1] >= gap:
            out.append(t)
    return out


def _extract_clip(chunk_path: Path, start_offset_s: float, duration_s: float,
                  dest: Path) -> None:
    """ffmpeg -c copy cut. No re-encode."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start_offset_s:.2f}", "-i", str(chunk_path),
        "-t", f"{duration_s:.2f}",
        # Drop audio (PCM_alaw doesn't repackage cleanly in MP4).
        "-an", "-c:v", "copy", str(dest),
    ]
    subprocess.run(cmd, check=True)


def _extract_thumbnail(clip_path: Path, dest: Path) -> bool:
    """One JPEG from the middle of the clip, scaled for browser display."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    # ffprobe duration
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(clip_path)],
        capture_output=True, text=True, check=False,
    )
    try:
        duration = float(r.stdout.strip())
    except ValueError:
        return False
    midpoint = max(0.5, duration / 2)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{midpoint:.2f}", "-i", str(clip_path),
        "-frames:v", "1", "-vf", "scale='min(640,iw)':'-2'",
        "-q:v", "3", str(dest),
    ]
    return subprocess.run(cmd).returncode == 0


def _enumerate_candidates(
    sss: sss_client.SSSClient,
    cam_id_map: dict[str, int],
    since_ts: float,
    until_ts: float,
    chunks_dir: Path,
    *,
    scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
    cluster_gap_s: float = CLUSTER_GAP_S,
) -> Iterable[Candidate]:
    """Iterate (camera, chunk, burst_offset) tuples for motion-tagged
    chunks in the given window. Streams chunks to disk lazily."""
    inv_map = {v: k for k, v in cam_id_map.items()}
    chunks = sss.list_motion_events(
        list(cam_id_map.values()),
        since_ts, until_ts,
        motion_only=True,
    )
    logger.info("found %d motion-tagged chunks in window", len(chunks))
    for chunk in chunks:
        camera = inv_map.get(chunk["cameraId"])
        if camera is None:
            logger.warning("skipping unknown SSS camera id %s", chunk["cameraId"])
            continue
        chunk_path = chunks_dir / f"sss_{chunk['cameraId']}_{chunk['id']}.mp4"
        if not chunk_path.exists():
            logger.info("downloading chunk %d for %s (%dMB nominal)",
                         chunk["id"], camera, chunk["event_size_bytes"] // 1_000_000)
            sss.download_chunk(chunk["id"], chunk_path)
        ts_in_chunk = _scene_change_timestamps(chunk_path, threshold=scene_threshold)
        bursts = _cluster_timestamps(ts_in_chunk, gap=cluster_gap_s)
        logger.info("chunk %d (%s): %d scene changes -> %d clustered bursts",
                     chunk["id"], camera, len(ts_in_chunk), len(bursts))
        for offset in bursts:
            yield Candidate(
                camera=camera,
                chunk_id=chunk["id"],
                chunk_start_ts=chunk["startTime"],
                burst_offset_s=offset,
                target_ts=chunk["startTime"] + offset,
            )


def run_backfill(
    since_ts: float,
    until_ts: Optional[float] = None,
    *,
    highlights_root: Path,
    db_path: Path,
    chunks_dir: Optional[Path] = None,
    dry_run: bool = False,
    max_clips: Optional[int] = None,
    scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
) -> dict:
    """Main entry point. Returns a summary dict."""
    if until_ts is None:
        until_ts = time.time()
    if chunks_dir is None:
        chunks_dir = highlights_root / "deep-dive-cache" / "_chunks"

    sss = sss_client.get_client()
    if sss is None:
        raise RuntimeError("SSS not configured (set SSS_BASE_URL/USER/PASS)")
    cam_id_map = sss_client.camera_id_map()

    db.init(db_path)

    n_candidates = 0
    n_classified = 0
    n_wildlife = 0
    n_skipped = 0
    species_counts: dict[str, int] = {}

    for cand in _enumerate_candidates(
        sss, cam_id_map, since_ts, until_ts, chunks_dir,
        scene_threshold=scene_threshold,
    ):
        n_candidates += 1
        if max_clips is not None and n_classified >= max_clips:
            logger.info("hit max_clips=%d; stopping", max_clips)
            break

        # Synthesize a stable event id for this burst. Format mirrors
        # Frigate's '<unix_ts>.<frac>-<id>' so it sorts with live events.
        event_id = f"backfill-{int(cand.target_ts)}-{cand.camera}-{int(cand.burst_offset_s)}"

        # Skip if we already inserted this exact burst on a previous run.
        if db.get_highlight(db_path, event_id):
            n_skipped += 1
            continue

        # Where to put the saved clip + thumbnail (mirrors curator layout).
        day = datetime.fromtimestamp(cand.target_ts, tz=timezone.utc) \
            .astimezone().strftime("%Y-%m-%d")
        day_dir = highlights_root / day
        clip_dest = day_dir / f"{event_id}.mp4"
        thumb_dest = day_dir / f"{event_id}.jpg"

        if dry_run:
            logger.info("DRY  cam=%s ts=%s offset=%.0fs -> %s",
                         cand.camera,
                         datetime.fromtimestamp(cand.target_ts).strftime("%H:%M:%S"),
                         cand.burst_offset_s,
                         clip_dest.name)
            continue

        # Cut the burst window from the chunk.
        chunk_path = chunks_dir / f"sss_{cam_id_map[cand.camera]}_{cand.chunk_id}.mp4"
        clip_start_offset = max(0.0, cand.burst_offset_s - WINDOW_PRE_S)
        clip_duration = WINDOW_PRE_S + WINDOW_POST_S
        try:
            _extract_clip(chunk_path, clip_start_offset, clip_duration, clip_dest)
        except subprocess.CalledProcessError as e:
            logger.warning("clip extract failed for %s: %s", event_id, e)
            continue

        # Classify (this is the wildlife-ID step). Reuses the same VLM
        # path as live Track-1 — frame extraction, structured prompt,
        # JSON parse, aggregation.
        verdict = classifier.classify_clip(clip_dest)
        n_classified += 1

        if verdict is None:
            logger.warning("classifier disabled or unconfigured; aborting backfill")
            return {"error": "classifier_unconfigured"}
        species = verdict.species
        species_counts[species] = species_counts.get(species, 0) + 1

        if not verdict.is_wildlife:
            # Not-wildlife (none/person/vehicle) — drop the clip from disk
            # and skip the DB row. We don't want backfill to flood the
            # gallery with people, cars, and noise.
            try: clip_dest.unlink()
            except FileNotFoundError: pass
            logger.info("SKIP cam=%s ts=%s offset=%.0fs species=%s (%s)",
                         cand.camera,
                         datetime.fromtimestamp(cand.target_ts).strftime("%H:%M:%S"),
                         cand.burst_offset_s, species, verdict.confidence)
            continue

        n_wildlife += 1
        _extract_thumbnail(clip_dest, thumb_dest)

        # Heuristic likelihood — set to 1.0 since we have positive
        # classification (the heuristic was a stand-in for the classifier
        # in the live path; backfill skips the heuristic step).
        likelihood = 1.0

        db.upsert_highlight(db_path, {
            "event_id": event_id,
            "camera": cand.camera,
            "label": species,           # use VLM's species in 'label' for backfill
            "start_time": cand.target_ts,
            "end_time": cand.target_ts + WINDOW_POST_S,
            "duration_s": WINDOW_PRE_S + WINDOW_POST_S,
            "score": 0.0,
            "fox_likelihood": likelihood,
            "clip_path": str(clip_dest.relative_to(highlights_root)),
            "thumb_path": str(thumb_dest.relative_to(highlights_root)) if thumb_dest.exists() else None,
            "promoted": 0,
            "promoted_at": None,
            "notes": None,
            "source": "backfill",
        })
        # Persist classifier verdict on the new row.
        raw = "; ".join(f"{f.species}/{f.confidence}: {f.description}"
                        for f in verdict.frames)
        db.update_classification(
            db_path, event_id, verdict.species, verdict.confidence,
            classifier._MODEL, time.time(), raw,
        )
        logger.info("KEEP cam=%s ts=%s species=%s (%s) -> %s",
                     cand.camera,
                     datetime.fromtimestamp(cand.target_ts).strftime("%H:%M:%S"),
                     species, verdict.confidence, event_id)

    return {
        "candidates": n_candidates,
        "classified": n_classified,
        "wildlife_kept": n_wildlife,
        "already_in_db": n_skipped,
        "species_counts": species_counts,
        "since_ts": since_ts,
        "until_ts": until_ts,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_RELATIVE_RE = re.compile(r"^(\d+)\s*(seconds?|minutes?|hours?|days?)\s*ago$",
                           re.IGNORECASE)


def _parse_when(s: str) -> float:
    """Accept '18 hours ago', '2 days ago', or an ISO timestamp."""
    m = _RELATIVE_RE.match(s.strip())
    if m:
        amount = int(m.group(1))
        unit = m.group(2).rstrip("s").lower()
        delta = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}[unit] * amount
        return time.time() - delta
    # Fallback: ISO format
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError as e:
        raise SystemExit(f"can't parse --since/--until value: {s} ({e})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill detection from SSS motion chunks")
    ap.add_argument("--since", required=True, help="e.g. '18 hours ago' or ISO ts")
    ap.add_argument("--until", default=None, help="default: now")
    ap.add_argument("--dry-run", action="store_true",
                    help="enumerate candidates but don't extract or classify")
    ap.add_argument("--max-clips", type=int, default=None,
                    help="stop after N classified clips (cost guardrail)")
    ap.add_argument("--scene-threshold", type=float, default=DEFAULT_SCENE_THRESHOLD)
    ap.add_argument("--highlights-root", type=Path,
                    default=Path(os.environ.get(
                        "HIGHLIGHTS_ROOT",
                        "/Volumes/main-filestore/frigate-highlights")))
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    # Configure classifier from env (matches main.py).
    classifier.configure(
        os.environ.get("LITELLM_BASE_URL", "http://localhost:4000"),
        os.environ.get("LITELLM_MASTER_KEY", ""),
        os.environ.get("CLASSIFIER_MODEL", "gpt-4o-mini/fox-cam"),
        int(os.environ.get("CLASSIFIER_FRAMES", "5")),
        True,  # force-enable for backfill
    )

    since_ts = _parse_when(args.since)
    until_ts = _parse_when(args.until) if args.until else None
    db_path = args.highlights_root / "index.db"

    summary = run_backfill(
        since_ts=since_ts, until_ts=until_ts,
        highlights_root=args.highlights_root,
        db_path=db_path,
        dry_run=args.dry_run,
        max_clips=args.max_clips,
        scene_threshold=args.scene_threshold,
    )

    print()
    print("=== Backfill summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
