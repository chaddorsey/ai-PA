"""Deep-dive — fetch arbitrary time-windowed clips from SSS on demand.

Used by the family-facing 'show me 30 seconds after this clip' button
(F17 in the followups), and by the curator itself to source full-
resolution event clips now that Frigate records substream-only
(option A → B transition).

Idempotent: the cache key is (camera, target_ts, before_s, after_s).
Repeat requests for the same window return the cached MP4 instantly.
Single-flight via per-key lock so simultaneous clicks don't fan out
into duplicate SS pulls.

Latency budget for a cold fetch via RangeExport (server-side cut):
  SSS auth (cached SID):       ~0ms
  RangeExport kickoff:         ~500ms
  Server export (45-sec window): 5-30s typical
  Download windowed MP4 (~10MB): 1-3s on LAN
  Total:                       ~6-35s typical
RangeExport pays the per-request server-side encode but saves us from
shipping 700MB-1.5GB of chunk data — and SSS regularly drops large-
chunk downloads at 3-30%, while the windowed extract reliably finishes.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

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


def _zip_to_mp4(zip_path: Path, dest: Path) -> None:
    """Concat the MP4 segments inside a RangeExport ZIP into a single
    MP4 at dest. Triggered when SSS reports the window straddles a
    codec or resolution change (rare for our single-camera setup but
    documented as possible in the SSS API)."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(td_path)
        # Sort by name — SSS names segments in temporal order.
        segments = sorted(
            p for p in td_path.iterdir() if p.suffix.lower() == ".mp4"
        )
        if not segments:
            raise DeepDiveError(
                f"RangeExport zip {zip_path} contained no MP4 segments"
            )
        if len(segments) == 1:
            shutil.copy2(segments[0], dest)
            return
        list_file = td_path / "concat.txt"
        list_file.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in segments) + "\n"
        )
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            # Drop audio (SSS PCM_alaw doesn't repackage cleanly in mp4).
            "-an", "-c", "copy", str(dest),
        ]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            raise DeepDiveError(f"ffmpeg concat failed: {e}") from e


def fetch_window(
    cache_root: Path,
    camera: str,
    target_ts: float,
    before_s: float = 15.0,
    after_s: float = 30.0,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> DeepDiveResult:
    """Pull a window from SSS centered on (target_ts - before_s, +after_s).

    Cached at cache_root / <camera> / <camera>_<ts>_<before>_<after>.mp4.
    Returns the cached path on repeat requests (idempotent).

    progress_callback receives (stage, percent) updates so callers can
    feed UI status indicators. Stages emitted: "exporting" (server
    building the cut, percent = SSS-reported progress) and
    "downloading" (transferring the result). On a cache hit, no
    callbacks fire.
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

        from_ts = target_ts - before_s
        to_ts = target_ts + after_s

        # Use SSS RangeExport: server-side cut spans chunk boundaries
        # and ships ~tens of MB instead of forcing us through a 700MB-
        # 1.5GB chunk download (which SSS regularly drops mid-stream).
        # The trade-off is a per-request server encode of 5-30s for the
        # typical 45-sec deep-dive window; for short manual recoveries
        # we'd otherwise be downloading the wrong order of magnitude.
        t0 = time.monotonic()
        try:
            export_path, file_ext = client.range_export(
                camera_id=cam_id,
                from_ts=from_ts,
                to_ts=to_ts,
                dest=cache_path,
                progress_callback=progress_callback,
            )
        except sss_client.SSSError as e:
            raise DeepDiveError(f"SSS RangeExport failed: {e}") from e
        export_dt = time.monotonic() - t0

        if file_ext == "mp4":
            logger.info(
                "RangeExport window %s [%.0f, %.0f] (%dMB) in %.1fs",
                camera, from_ts, to_ts,
                cache_path.stat().st_size // 1_000_000, export_dt,
            )
        elif file_ext == "zip":
            # Codec or resolution changed mid-window. Concat the
            # segments before exposing the result via cache_path.
            logger.info(
                "RangeExport returned zip for %s [%.0f, %.0f]; concat'ing",
                camera, from_ts, to_ts,
            )
            try:
                _zip_to_mp4(export_path, cache_path)
            finally:
                try:
                    export_path.unlink()
                except FileNotFoundError:
                    pass
        else:
            raise DeepDiveError(
                f"unexpected RangeExport file_ext {file_ext!r}"
            )

        return DeepDiveResult(
            path=cache_path, cache_hit=False,
            duration_s=duration_s, chunk_id=0,
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
