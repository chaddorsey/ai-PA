"""Deep-dive — fetch arbitrary time-windowed clips from SSS on demand.

Used by the family-facing 'show me 30 seconds after this clip' button
(F17 in the followups), and by the curator itself to source full-
resolution event clips now that Frigate records substream-only
(option A → B transition).

Idempotent: the cache key is (camera, target_ts, before_s, after_s).
Repeat requests for the same window return the cached MP4 instantly.
Single-flight via per-key lock so simultaneous clicks don't fan out
into duplicate SS pulls.

Latency budget for a cold fetch (uncached):
  SSS auth (cached SID):      ~0ms
  Recording.List call:        ~500ms
  Chunk download (5min, 250MB): 1-5s on LAN
  ffmpeg cut (-c copy):       ~1-2s
  Total:                      ~3-8s typical
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import sss_client


logger = logging.getLogger(__name__)


@dataclass
class DeepDiveResult:
    path: Path                # cached MP4 with the requested window
    cache_hit: bool
    duration_s: float
    chunk_id: int             # source SSS event id, for debugging


class DeepDiveError(RuntimeError):
    pass


# Per-cache-key locks so concurrent requests for the same window
# coalesce into one fetch. The lock map itself is guarded by _lock_lock.
_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _key_for(camera: str, target_ts: float, before_s: float, after_s: float) -> str:
    return f"{camera}_{int(target_ts)}_{int(before_s)}_{int(after_s)}"


def _key_lock(key: str) -> threading.Lock:
    with _locks_lock:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def fetch_window(
    cache_root: Path,
    camera: str,
    target_ts: float,
    before_s: float = 15.0,
    after_s: float = 30.0,
) -> DeepDiveResult:
    """Pull a window from SSS centered on (target_ts - before_s, +after_s).

    Cached at cache_root / <camera> / <camera>_<ts>_<before>_<after>.mp4.
    Returns the cached path on repeat requests (idempotent).
    """
    client = sss_client.get_client()
    if client is None:
        raise DeepDiveError("SSS not configured (set SSS_BASE_URL/USER/PASS)")

    cam_map = sss_client.camera_id_map()
    cam_id = cam_map.get(camera)
    if cam_id is None:
        raise DeepDiveError(f"unknown camera {camera!r}")

    duration_s = before_s + after_s
    key = _key_for(camera, target_ts, before_s, after_s)
    cache_dir = cache_root / camera
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{key}.mp4"

    # Coalesce concurrent requests on the same key.
    with _key_lock(key):
        if cache_path.exists():
            return DeepDiveResult(
                path=cache_path, cache_hit=True,
                duration_s=duration_s, chunk_id=0,
            )

        # Locate the SSS chunk that contains the start of our window.
        start_ts = target_ts - before_s
        chunk = client.find_chunk(cam_id, start_ts)
        if chunk is None:
            raise DeepDiveError(
                f"no SSS chunk covers {start_ts} (camera {camera}); "
                "may be past retention"
            )

        # Download chunk to a per-camera scratch area. We could share
        # the chunk across windows but for v1 simplicity we keep one
        # chunk per fetch and rely on cache_path for the cut output.
        chunks_dir = cache_root / "_chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)
        chunk_path = chunks_dir / f"sss_{cam_id}_{chunk['id']}.mp4"
        t0 = time.monotonic()
        client.download_chunk(chunk["id"], chunk_path)
        dl_dt = time.monotonic() - t0
        logger.info("fetched chunk %d (%dMB) in %.1fs",
                    chunk["id"], chunk_path.stat().st_size // 1_000_000, dl_dt)

        # Compute offset within the chunk and cut.
        offset_s = max(0.0, start_ts - chunk["startTime"])
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{offset_s:.2f}", "-i", str(chunk_path),
            "-t", f"{duration_s:.2f}",
            # Drop audio (SSS PCM_alaw doesn't repackage cleanly in mp4).
            "-an", "-c:v", "copy", str(cache_path),
        ]
        t0 = time.monotonic()
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            raise DeepDiveError(f"ffmpeg cut failed: {e}") from e
        cut_dt = time.monotonic() - t0
        logger.info("cut window (%ds @ offset %.1fs) in %.1fs",
                    int(duration_s), offset_s, cut_dt)

        # Optional: keep the chunk on disk only briefly. For now we
        # leave it; subsequent windows from the same chunk are free.
        # A janitor follow-up (F22?) can prune chunks that haven't been
        # touched in N days.

        return DeepDiveResult(
            path=cache_path, cache_hit=False,
            duration_s=duration_s, chunk_id=chunk["id"],
        )


def janitor_prune(cache_root: Path, max_age_days: float = 60.0) -> int:
    """Drop cached windows + chunks older than max_age_days. Returns
    bytes freed. Safe to call from a periodic scheduler. Skipped here
    in v1; left as a hook for a follow-up cron."""
    cutoff = time.time() - max_age_days * 86400
    freed = 0
    for sub in ("_chunks",) + tuple(cache_root.glob("fox_den_*")):
        for f in cache_root.joinpath(sub).rglob("*.mp4") if cache_root.joinpath(sub).exists() else ():
            try:
                if f.stat().st_mtime < cutoff:
                    freed += f.stat().st_size
                    f.unlink()
            except FileNotFoundError:
                pass
    return freed
