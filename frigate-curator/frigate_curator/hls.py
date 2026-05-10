"""HLS segmentation for clip playback.

Rationale:
  iOS Safari over Cloudflare Tunnel paid 30+ s for the first frame of a
  modal-opened clip even after the streaming proxy was fixed. The
  fragmented MP4 + Range-request pattern through CF tunnel hits HTTP/1.1
  RTT amortization limits — every Range needs a round-trip, and a 30 MB
  clip needs ~20 of them. HLS sidesteps this entirely: the player
  fetches a small text manifest, then 4-sec self-contained segments,
  pipelined and individually small. iOS Safari plays HLS natively (no
  JS library), other browsers use hls.js as a polyfill.

  Critically we use `-c:v copy` so the segments contain the *source*
  bitstream — no resolution loss, no quality loss, full pinch-zoom
  fidelity in the modal. The HLS path is a re-mux, not a transcode,
  which keeps both the storage cost (~same as source) and the ffmpeg
  cost (~2-5s per 30s clip) modest.

Layout:
  highlights_root/
    {day}/
      {event_id}.mp4          (source, kept as fallback for non-HLS clients)
      {event_id}.jpg          (thumbnail)
      {event_id}_hls/         (this module's output — atomic via tmp rename)
        index.m3u8            (manifest listing the segments)
        seg_000.ts            (mpegts fragments, ~1-3 MB each)
        seg_001.ts
        ...

Idempotency:
  ensure_hls_rendered() returns the cached dir if index.m3u8 already
  exists. The first call segments + writes; subsequent calls are a
  stat() check. Build is atomic via a `_hls.tmp/` working directory
  that gets renamed to `_hls/` on success — interrupted builds leave
  the working dir behind for cleanup but never publish a partial
  manifest.

Failures (corrupted source, unsupported codec, etc.):
  Logged + the working dir is removed. The endpoint that would have
  served the manifest 404s; the client's <video> falls through to its
  next <source> (the original .mp4). Self-healing.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


# Cap concurrent ffmpeg invocations across the whole process. ffmpeg's
# output is many small files on the same volume as the SQLite DB; two
# or more racing ffmpegs saturate disk I/O and starve the API path.
# A semaphore of 1 means each new render queues behind the previous
# one — slower throughput on bulk renders but the API stays
# responsive. Backfill scripts that want concurrency should use their
# own out-of-band ffmpeg pool (with `nice -n 19` ideally), not this
# module's prewarm helper.
_render_semaphore = threading.Semaphore(1)


def hls_dir_for(highlights_root: Path, clip_relpath: str) -> Path:
    """Output directory that holds index.m3u8 + seg_*.ts for the clip
    at clip_relpath (a path relative to highlights_root, which is what
    the highlights table stores). Sits next to the source .mp4 so
    backups + retention sweeps treat the bundle as a unit."""
    src = highlights_root / clip_relpath
    return src.with_name(src.stem + "_hls")


def is_rendered(highlights_root: Path, clip_relpath: str) -> bool:
    """True iff the HLS bundle for this clip is fully written."""
    return (hls_dir_for(highlights_root, clip_relpath) / "index.m3u8").exists()


def ensure_hls_rendered(
    highlights_root: Path,
    clip_relpath: str,
    *,
    segment_seconds: float = 4.0,
    audio_bitrate: str = "96k",
) -> Optional[Path]:
    """Render HLS for the clip at clip_relpath. Idempotent: returns
    immediately if already rendered. Returns the path to the HLS dir
    on success, or None on failure (logged).

    The ffmpeg command does NOT re-encode video (`-c:v copy`) so source
    resolution + bitrate are preserved — pinch-zoom in the modal stays
    sharp. Audio is re-encoded to AAC because manual-recovery clips
    carry pcm_alaw which mpegts can't carry; AAC re-encode is fast and
    a no-op pass for AAC inputs and clips with no audio stream.

    Segment boundaries are constrained by source keyframe positions
    when using -c:v copy. Frigate clips have ~2s keyframe interval, so
    4-sec segments work cleanly. SSS/manual-recovery clips also use
    short keyframe intervals.
    """
    src = highlights_root / clip_relpath
    if not src.exists():
        logger.warning("hls: source clip missing: %s", src)
        return None

    out_dir = hls_dir_for(highlights_root, clip_relpath)
    manifest = out_dir / "index.m3u8"
    if manifest.exists():
        return out_dir

    # Hold the semaphore across the *entire* tmp_dir lifecycle, not
    # just the ffmpeg call. The earlier draft put tmp_dir setup
    # outside the semaphore, which let two concurrent prewarms race:
    # both saw `if not is_rendered`, both did `shutil.rmtree(tmp_dir)`
    # + `tmp_dir.mkdir()`, both queued for the semaphore. Whichever
    # acquired second would `rmtree` the first's freshly-renamed
    # `_hls/` *during* ffmpeg's writes — surfaced as exit status 254
    # with "Failed to open file '..._hls.tmp/seg_000.ts'" in today's
    # logs. Inside the semaphore, only one thread ever touches
    # tmp_dir at a time.
    with _render_semaphore:
        # Re-check the published manifest now that we've serialized.
        # A previous queued thread may have rendered while we waited.
        if (out_dir / "index.m3u8").exists():
            return out_dir

        # Atomic rename: build into a sibling tmp dir, swap on success.
        # If a previous run was interrupted, the tmp dir may still
        # exist with partial output — wipe so this run starts clean.
        tmp_dir = out_dir.with_name(out_dir.name + ".tmp")
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir(parents=True, exist_ok=False)

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src),
            # Stream-copy video (preserves resolution/quality, fast).
            "-c:v", "copy",
            # Audio: re-encode to AAC. Tolerates AAC inputs (re-pass),
            # pcm_alaw inputs (the SSS-sourced manual recoveries),
            # and sources with no audio stream (ffmpeg skips silently).
            "-c:a", "aac", "-b:a", audio_bitrate,
            "-hls_time", str(segment_seconds),
            "-hls_playlist_type", "vod",
            "-hls_segment_type", "mpegts",
            # independent_segments lets iOS Safari decode each .ts
            # on its own without backreferencing the previous one —
            # required for the pipelined-fetch performance HLS is
            # meant to deliver.
            "-hls_flags", "independent_segments",
            "-hls_segment_filename", str(tmp_dir / "seg_%03d.ts"),
            "-f", "hls", str(tmp_dir / "index.m3u8"),
        ]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.exception("hls: ffmpeg failed for %s: %s", clip_relpath, e)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None

        # Atomic publish. os.replace is the POSIX atomic rename on
        # the same filesystem — no reader can ever see a half-written
        # manifest. Done inside the semaphore so the next queued
        # thread sees the published manifest immediately on its
        # is_rendered re-check above and skips its own render.
        try:
            os.replace(tmp_dir, out_dir)
        except OSError as e:
            logger.exception("hls: rename %s -> %s failed: %s",
                             tmp_dir, out_dir, e)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None

    n_segs = sum(1 for p in out_dir.iterdir()
                 if p.name.startswith("seg_") and p.suffix == ".ts")
    logger.info("hls: rendered %s into %d segments at %s",
                clip_relpath, n_segs, out_dir)
    return out_dir


def prewarm_hls_async(highlights_root: Path, clip_relpath: str) -> None:
    """Fire-and-forget: spawn a daemon thread to render HLS if not
    already cached. Called from curator's _process_event so new clips
    have HLS by the time someone opens their modal. Swallows
    exceptions — best-effort; the on-demand render path serves any
    clip that didn't pre-warm.
    """
    if is_rendered(highlights_root, clip_relpath):
        return

    def run():
        try:
            ensure_hls_rendered(highlights_root, clip_relpath)
        except Exception:
            logger.exception("hls: prewarm thread failed for %s", clip_relpath)

    threading.Thread(
        target=run,
        name=f"hls-prewarm-{Path(clip_relpath).stem[:24]}",
        daemon=True,
    ).start()
