"""Recover a highlight from raw Frigate recordings for an arbitrary
time window where Frigate's detector missed it (silent wedges, motion
filtered out, anything we noticed by eye that the pipeline didn't).

Frigate writes 10-second motion-triggered MP4 segments under
    <RECORDINGS_ROOT>/<YYYY-MM-DD>/<HH>/<camera>/MM.SS.mp4
where MM.SS is the segment's start minute and second within that hour
(LOCAL TIME — Frigate uses the host's timezone for the dir layout).
Retention is whatever's configured in Frigate; for our setup that's
14-30 days.

This module exposes recover_window() which:
  1. Locates segments overlapping the requested [start, end] window,
     potentially spanning hour boundaries.
  2. ffmpeg-concats them and trims to the exact window.
  3. Extracts a thumbnail at the midpoint.
  4. Returns paths suitable for db.upsert_highlight().

Designed to be the foundational primitive that future "deeper-dive"
review surfaces (timeline scrubber, manual mark-a-window UI, etc.)
will call. The shape is intentionally simple: window in, clip out.
"""
from __future__ import annotations

import logging
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)

_FFMPEG = shutil.which("ffmpeg")

# Cap the max window so a typo can't ask for an hour-long render.
MAX_WINDOW_SEC = 600  # 10 minutes


@dataclass
class RecoverResult:
    event_id: str
    clip_path: Path             # absolute on disk
    thumb_path: Path | None     # absolute on disk (None on extract failure)
    duration_s: float
    segment_count: int
    camera: str
    start_time: float
    end_time: float


class RecoverError(RuntimeError):
    pass


def _segments_for_window(recordings_root: Path, camera: str,
                          start_time: float, end_time: float) -> list[Path]:
    """Walk the recording dirs spanning [start, end] and return matching
    segment files, sorted by start time. A segment matches if its
    [seg_start, seg_start + ~10s] window overlaps [start, end].

    Frigate uses UTC for the dir layout (<YYYY-MM-DD>/<HH>/<camera>/),
    so we convert the epoch to UTC when building the dir path AND when
    parsing each file's MM.SS back into a wall-clock timestamp. We add
    a 1-segment grace to either side so we don't miss a segment that
    began shortly before `start` and contains the desired prefix frames.
    """
    matches: list[tuple[float, Path]] = []
    # Pad to ensure we cover the segment that BEGAN before start_time
    # (contains the prefix frames) and the one ending after end_time.
    pad_start = start_time - 12
    pad_end = end_time + 12

    # Enumerate every UTC hour bucket the padded window touches. Walking
    # by `cur += 3600` from pad_start would skip hours when pad_start
    # lands near the END of one hour (e.g. 03:59:48 → 04:59:48 jumps
    # past hour 04 entirely). Instead, step from the FLOOR of pad_start
    # to the CEILING of pad_end in 1-hour ticks.
    floor_dt = datetime.fromtimestamp(pad_start, tz=timezone.utc).replace(
        minute=0, second=0, microsecond=0)
    ceil_dt = datetime.fromtimestamp(pad_end, tz=timezone.utc).replace(
        minute=0, second=0, microsecond=0)
    h = floor_dt
    while h <= ceil_dt:
        dir_path = (recordings_root / h.strftime("%Y-%m-%d") /
                    f"{h.hour:02d}" / camera)
        if dir_path.exists():
            for f in dir_path.iterdir():
                if f.suffix != ".mp4":
                    continue
                stem = f.stem  # e.g. "35.02"
                try:
                    mm_str, ss_str = stem.split(".", 1)
                    mm, ss = int(mm_str), int(ss_str)
                except ValueError:
                    continue
                seg_start_dt = h.replace(minute=mm, second=ss, microsecond=0)
                seg_start = seg_start_dt.timestamp()
                seg_end = seg_start + 10  # Frigate's segment length
                if seg_end < start_time or seg_start > end_time:
                    continue
                matches.append((seg_start, f))
        h += timedelta(hours=1)
    matches.sort(key=lambda x: x[0])
    return [p for _, p in matches]


def _generate_thumbnail(clip_path: Path, thumb_path: Path,
                         offset_s: float = 0.5) -> bool:
    """Pull a single frame at `offset_s` (or midpoint if larger than the
    clip) into thumb_path. Returns True on success, False otherwise.
    """
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


def recover_window(
    recordings_root: Path,
    highlights_root: Path,
    camera: str,
    start_time: float,
    end_time: float,
) -> RecoverResult:
    """Build a manual highlight clip from raw recordings for the window.

    Raises RecoverError on validation failure or ffmpeg failure. Caller
    is responsible for inserting the resulting paths into the highlights
    table (see endpoint in main.py).
    """
    if _FFMPEG is None:
        raise RecoverError("ffmpeg not available")
    if not recordings_root.exists():
        raise RecoverError(f"recordings root not found: {recordings_root}")
    if end_time <= start_time:
        raise RecoverError("end_time must exceed start_time")
    duration = end_time - start_time
    if duration > MAX_WINDOW_SEC:
        raise RecoverError(
            f"window too long ({duration:.0f}s > {MAX_WINDOW_SEC}s max)"
        )

    segments = _segments_for_window(recordings_root, camera, start_time, end_time)
    if not segments:
        raise RecoverError(
            f"no recording segments found for {camera} "
            f"in {datetime.fromtimestamp(start_time).isoformat()} → "
            f"{datetime.fromtimestamp(end_time).isoformat()}"
        )

    # Synthetic event_id: stable + filesystem-safe + unguessable so
    # leaking the URL doesn't reveal a predictable namespace.
    event_id = (f"manual-{camera}-{int(start_time)}"
                f"-{secrets.token_urlsafe(4).rstrip('=').replace('-','x').replace('_','y')}")

    # Mirror the day-bucketed layout that curator.promote() uses so
    # backups + retention sweeps treat manual clips like any other
    # highlight.
    day = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d")
    day_dir = highlights_root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    clip_path = day_dir / f"{event_id}.mp4"
    thumb_path = day_dir / f"{event_id}.jpg"

    # Two-pass ffmpeg: write the concat list to a tmpfile, then run
    # ffmpeg with -f concat. Trim to the exact window with -ss/-to
    # AFTER the -i so seek is accurate (decode-and-seek). We re-encode
    # rather than -c copy because Frigate's segments may have varying
    # SPS/PPS or timestamp resets at boundaries that -c copy chokes on.
    # For a 10-min cap that's at most a few seconds of CPU; acceptable.
    # Compute the offset from the first segment's start to start_time so
    # the trim begins at exactly the requested instant. The path layout
    # is <camera>/<HH>/<YYYY-MM-DD>/<MM.SS.mp4>, all in UTC.
    first_seg_path = segments[0]
    first_seg_stem = first_seg_path.stem
    try:
        mm_str, ss_str = first_seg_stem.split(".", 1)
        seg_hour = int(first_seg_path.parent.parent.name)
        seg_date = first_seg_path.parent.parent.parent.name  # YYYY-MM-DD
        seg_dt = datetime.strptime(seg_date, "%Y-%m-%d").replace(
            hour=seg_hour, minute=int(mm_str), second=int(ss_str),
            microsecond=0, tzinfo=timezone.utc,
        )
        first_seg_start_ts = seg_dt.timestamp()
    except Exception:
        first_seg_start_ts = start_time  # fallback: trim from beginning

    seek_offset = max(0.0, start_time - first_seg_start_ts)

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as listf:
        for s in segments:
            # Single-quote escape rules for ffmpeg's concat demuxer.
            listf.write(f"file '{str(s).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n")
        listfile = listf.name

    try:
        cmd = [
            _FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", listfile,
            "-ss", f"{seek_offset:.3f}",
            "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(clip_path),
        ]
        subprocess.run(cmd, check=True, timeout=120)
    except subprocess.CalledProcessError as e:
        try: clip_path.unlink(missing_ok=True)
        except Exception: pass
        raise RecoverError(f"ffmpeg failed: {e}") from e
    except subprocess.TimeoutExpired:
        try: clip_path.unlink(missing_ok=True)
        except Exception: pass
        raise RecoverError("ffmpeg timed out (>120s)")
    finally:
        try: os.unlink(listfile)
        except Exception: pass

    # Probe the actual on-disk duration; the clip may end up slightly
    # shorter than requested if Frigate's segments don't cover the full
    # window (e.g. a brief recording gap).
    actual_duration = duration
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nokey=1:noprint_wrappers=1", str(clip_path)],
            capture_output=True, text=True, timeout=10,
        )
        actual_duration = float(out.stdout.strip())
    except Exception:
        pass

    thumb_ok = _generate_thumbnail(
        clip_path, thumb_path, offset_s=min(actual_duration / 2, 2.0)
    )

    return RecoverResult(
        event_id=event_id,
        clip_path=clip_path,
        thumb_path=thumb_path if thumb_ok else None,
        duration_s=actual_duration,
        segment_count=len(segments),
        camera=camera,
        start_time=start_time,
        end_time=end_time,
    )
