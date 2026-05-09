"""Recover a highlight from continuously-recorded SSS footage for an
arbitrary time window where Frigate's detector missed it (silent
wedge, motion filtered out, anything we noticed by eye that the
pipeline didn't catch — including failure modes that take Frigate's
own recording offline along with the detector).

Source of truth is SSS (Synology Surveillance Station), our 24/7
continuous-recording NVR. Frigate records motion-triggered substream
segments, but those gap out during the same wedges we're trying to
recover from; SSS is the resilient archive.

Implementation reuses deep_dive.fetch_window — the same primitive the
"show me 30 seconds after this clip" feature uses — and copies the
cached cut into the highlights dir as a permanent clip.

Designed to be the foundational primitive that future "deeper-dive"
review surfaces (timeline scrubber, manual mark-a-window UI, etc.)
will call. Window in, clip out.
"""
from __future__ import annotations

import logging
import secrets
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import deep_dive


logger = logging.getLogger(__name__)

_FFMPEG = shutil.which("ffmpeg")
_FFPROBE = shutil.which("ffprobe")

# Cap the max window so a typo can't ask for an hour-long render. SSS
# chunks are usually 5 min so 10 min may straddle a chunk boundary —
# deep_dive.fetch_window handles single chunks today; if we ever need
# >chunk-length recovery we'll need to teach it to stitch.
MAX_WINDOW_SEC = 600  # 10 minutes


@dataclass
class RecoverResult:
    event_id: str
    clip_path: Path             # absolute on disk (in highlights_root)
    thumb_path: Path | None     # absolute on disk (None on extract failure)
    duration_s: float
    camera: str
    start_time: float
    end_time: float
    sss_chunk_id: int           # source SSS chunk, for debugging


class RecoverError(RuntimeError):
    pass


def _generate_thumbnail(clip_path: Path, thumb_path: Path,
                         offset_s: float = 0.5) -> bool:
    """Pull a single frame at `offset_s` (or near-start if larger than
    the clip) into thumb_path. Returns True on success."""
    if not _FFMPEG:
        return False
    try:
        subprocess.run(
            [_FFMPEG, "-y", "-loglevel", "error",
             "-ss", f"{offset_s:.3f}", "-i", str(clip_path),
             "-frames:v", "1", "-q:v", "3", str(thumb_path)],
            check=True, timeout=20,
        )
        return thumb_path.exists() and thumb_path.stat().st_size > 0
    except Exception as e:
        logger.warning("manual highlight thumbnail failed: %s", e)
        return False


def _probe_duration(clip_path: Path) -> float | None:
    if not _FFPROBE:
        return None
    try:
        out = subprocess.run(
            [_FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nokey=1:noprint_wrappers=1", str(clip_path)],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return float(out.stdout.strip())
    except Exception:
        return None


def recover_window(
    deep_dive_cache_root: Path,
    highlights_root: Path,
    camera: str,
    start_time: float,
    end_time: float,
    event_id: str | None = None,
) -> RecoverResult:
    """Build a manual highlight clip from SSS for the given window.

    Pulls via deep_dive.fetch_window (which handles SSS auth, chunk
    location, single-flight locking, and ffmpeg cut), then copies the
    cached MP4 into the highlights dir as a permanent clip and
    generates a thumbnail.

    Raises RecoverError on validation failure or upstream SSS / ffmpeg
    failure. Caller is responsible for inserting the resulting paths
    into the highlights table.
    """
    if _FFMPEG is None:
        raise RecoverError("ffmpeg not available")
    if end_time <= start_time:
        raise RecoverError("end_time must exceed start_time")
    duration = end_time - start_time
    if duration > MAX_WINDOW_SEC:
        raise RecoverError(
            f"window too long ({duration:.0f}s > {MAX_WINDOW_SEC}s max)"
        )

    # deep_dive's fetch_window takes (target_ts, before_s, after_s) and
    # produces [target_ts - before_s, target_ts + after_s]. Pin
    # target_ts to the midpoint for a symmetric request.
    midpoint = (start_time + end_time) / 2
    half = duration / 2
    try:
        dd = deep_dive.fetch_window(
            cache_root=deep_dive_cache_root,
            camera=camera,
            target_ts=midpoint,
            before_s=half,
            after_s=half,
        )
    except deep_dive.DeepDiveError as e:
        raise RecoverError(f"SSS fetch failed: {e}") from e

    # Synthetic event_id: stable + filesystem-safe + unguessable so a
    # leaked URL doesn't reveal a predictable namespace. Caller can
    # supply one (the async task path generates it up-front so the
    # status-polling endpoint can reference the eventual row id).
    if event_id is None:
        event_id = (f"manual-{camera}-{int(start_time)}"
                    f"-{secrets.token_urlsafe(4).rstrip('=').replace('-','x').replace('_','y')}")

    # Mirror the day-bucketed layout that curator.promote() uses so
    # backups + retention sweeps treat manual clips like any other
    # highlight. Day bucket is LOCAL time (matches the rest of curator).
    day = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d")
    day_dir = highlights_root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    clip_path = day_dir / f"{event_id}.mp4"
    thumb_path = day_dir / f"{event_id}.jpg"

    # Copy the cached SSS cut into the highlights dir. Copy not move:
    # deep_dive's cache is shared across "show 30 sec after" usage and
    # we don't want to delete a cached window someone else might still
    # reference. The cache file is small (windowed) so the dupe is
    # cheap; janitor sweeps the deep-dive cache separately.
    try:
        shutil.copy2(dd.path, clip_path)
    except Exception as e:
        raise RecoverError(f"copy from deep-dive cache failed: {e}") from e

    actual_duration = _probe_duration(clip_path) or duration
    thumb_ok = _generate_thumbnail(
        clip_path, thumb_path, offset_s=min(actual_duration / 2, 2.0)
    )

    return RecoverResult(
        event_id=event_id,
        clip_path=clip_path,
        thumb_path=thumb_path if thumb_ok else None,
        duration_s=actual_duration,
        camera=camera,
        start_time=start_time,
        end_time=end_time,
        sss_chunk_id=dd.chunk_id,
    )
