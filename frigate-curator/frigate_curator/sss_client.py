"""Synology Surveillance Station Web API client.

Wraps the small subset of SSS endpoints we need for fetching arbitrary
time-windowed clips from the NVR's continuous archive. Designed for the
F17 deep-dive feature: when an event fires, fetch a window from SS so
the viewer can show 30 seconds of context before/after, at full main-
stream resolution (which Frigate no longer records since option A).

Endpoints used (all on DSM port 5000, /webapi/):
- SYNO.API.Auth                        login → SID
- SYNO.SurveillanceStation.Camera      List cameras (one-time discovery)
- SYNO.SurveillanceStation.Event       List recording chunks by time range
- SYNO.SurveillanceStation.Recording   Download a chunk by id

DSM 6.2.4 quirk: the events list returns 30-min recording CHUNKS, not
discrete motion events. Each chunk is tagged with trigger_label[]
indicating whether it contains motion. To fetch a small window we
locate the chunk containing target_ts, then slice with ffmpeg.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional

import httpx


logger = logging.getLogger(__name__)


class SSSError(RuntimeError):
    pass


class SSSClient:
    def __init__(self, base_url: str, user: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.user = user
        self.password = password
        self._sid: Optional[str] = None
        self._sid_obtained_at: float = 0.0
        # SIDs typically last ~12h; refresh after 11h.
        self._sid_max_age_s: float = 11 * 3600
        self._lock = threading.Lock()

    # ---- auth ----------------------------------------------------------

    def _login(self) -> str:
        r = httpx.get(
            f"{self.base_url}/webapi/auth.cgi",
            params={
                "api": "SYNO.API.Auth", "version": 6, "method": "login",
                "account": self.user, "passwd": self.password,
                "session": "SurveillanceStation", "format": "sid",
            },
            timeout=15.0,
        )
        r.raise_for_status()
        body = r.json()
        if not body.get("success"):
            raise SSSError(f"login failed: {body}")
        sid = body["data"]["sid"]
        self._sid = sid
        self._sid_obtained_at = time.time()
        logger.info("SSS login OK (sid len=%d)", len(sid))
        return sid

    def _sid_or_login(self) -> str:
        with self._lock:
            if (self._sid is None or
                    time.time() - self._sid_obtained_at > self._sid_max_age_s):
                self._login()
            return self._sid  # type: ignore[return-value]

    def _get(self, params: dict[str, Any], *, retry_on_auth: bool = True,
             timeout: float = 30.0) -> dict[str, Any]:
        params = {**params, "_sid": self._sid_or_login()}
        r = httpx.get(f"{self.base_url}/webapi/entry.cgi",
                      params=params, timeout=timeout)
        r.raise_for_status()
        body = r.json()
        if not body.get("success"):
            err_code = (body.get("error") or {}).get("code")
            # 105 = "permission denied" — usually means SID expired.
            if err_code in (105, 106, 107) and retry_on_auth:
                logger.info("SSS SID stale (code %s); re-logging in", err_code)
                self._sid = None
                return self._get(params, retry_on_auth=False, timeout=timeout)
            raise SSSError(f"SSS API error: {body}")
        return body.get("data", {})

    # ---- camera discovery ---------------------------------------------

    def list_cameras(self) -> list[dict[str, Any]]:
        """Return camera metadata. id is the SSS-internal numeric id."""
        return self._get({
            "api": "SYNO.SurveillanceStation.Camera",
            "version": 9, "method": "List",
        }).get("cameras", [])

    # ---- event / recording listing ------------------------------------

    def find_chunk(self, camera_id: int, target_ts: float,
                   *, search_window_s: int = 3600) -> Optional[dict[str, Any]]:
        """Return the SSS Event chunk whose [startTime, stopTime] contains
        target_ts. Searches a ±search_window_s window around target_ts.
        Returns None if no chunk covers the timestamp (e.g. past retention)."""
        target_ts = int(target_ts)
        events = self._get({
            "api": "SYNO.SurveillanceStation.Event",
            "version": 5, "method": "List",
            "cameraIds": str(camera_id),
            "fromTime": target_ts - search_window_s,
            "toTime": target_ts + search_window_s,
            "limit": 50,
        }).get("events", [])
        for e in events:
            if e["startTime"] <= target_ts < e["stopTime"]:
                return e
        return None

    def list_motion_events(self, camera_ids: list[int],
                            start_ts: float, end_ts: float,
                            *, motion_only: bool = True) -> list[dict[str, Any]]:
        """Return Event chunks in the range. If motion_only, filter to those
        SSS tagged as containing motion (trigger_label includes 257)."""
        events = self._get({
            "api": "SYNO.SurveillanceStation.Event",
            "version": 5, "method": "List",
            "cameraIds": ",".join(str(i) for i in camera_ids),
            "fromTime": int(start_ts), "toTime": int(end_ts),
            "limit": 1000,
        }).get("events", [])
        if motion_only:
            events = [e for e in events if e.get("trigger_label") == [257]]
        return events

    # ---- chunk download -----------------------------------------------

    def download_chunk(self, event_id: int, dest: Path) -> Path:
        """Download a recording chunk by its SSS event id. Streams to disk
        so we don't buffer 200-700MB in memory.

        Kept as a fallback / diagnostic path. Prefer range_export() for
        time-windowed extracts: full chunks are 700MB-1.5GB and SSS
        regularly drops connections mid-stream, while RangeExport gives
        the server-side cut and only ships ~tens of MB."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            return dest
        sid = self._sid_or_login()
        with httpx.stream(
            "GET", f"{self.base_url}/webapi/entry.cgi",
            params={
                "api": "SYNO.SurveillanceStation.Recording",
                "version": 6, "method": "Download",
                "id": event_id, "_sid": sid,
            },
            timeout=600.0,
        ) as r:
            r.raise_for_status()
            tmp = dest.with_suffix(dest.suffix + ".part")
            with tmp.open("wb") as f:
                for c in r.iter_bytes(chunk_size=1024 * 1024):
                    f.write(c)
            tmp.rename(dest)
        return dest

    # ---- range export (preferred) -------------------------------------
    #
    # Three-step async flow that asks SSS to cut a server-side window
    # spanning chunk boundaries. Replaces the "download whole 1.5GB
    # chunk + ffmpeg cut" path: we transfer ~tens of MB instead, and
    # the server handles cross-chunk stitching. Required because SSS
    # consistently drops large-chunk downloads at 3-30% completion.
    #
    # Server-side constraints:
    # - GetRangeExportProgress must be polled at least every 20s (acts
    #   as keepalive); skipping it past that purges the dlid.
    # - OnRangeExportDone must be fetched within ~1 minute of progress
    #   reaching 100, or the export is GC'd.
    # - Returns MP4 in the common case, ZIP of segments if the codec
    #   or resolution changed mid-window. Caller handles both.

    def range_export(
        self,
        camera_id: int,
        from_ts: float,
        to_ts: float,
        dest: Path,
        *,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        poll_interval_s: float = 4.0,
        kickoff_timeout_s: float = 60.0,
        download_timeout_s: float = 300.0,
        export_timeout_s: float = 600.0,
    ) -> tuple[Path, str]:
        """Export a time window via RangeExport, splitting into smaller
        sub-windows if the requested duration exceeds the segment
        threshold. Single-shot path is used for short windows; longer
        windows are split + ffmpeg-concat'd to keep each individual
        download under the size threshold where SSS reliably finishes.

        See _range_export_one for the underlying 3-step protocol.
        """
        duration = to_ts - from_ts
        # Tunable via env: SSS_SEGMENT_THRESHOLD_S = window above which
        # we segment; SSS_SEGMENT_SIZE_S = nominal sub-window length.
        # Defaults of 90 / 60 keep each sub-export ≲50 MB on our cams,
        # well under the size where SSS streams start dropping.
        threshold_s = float(os.environ.get("SSS_SEGMENT_THRESHOLD_S", "90"))
        segment_s = float(os.environ.get("SSS_SEGMENT_SIZE_S", "60"))
        if duration <= threshold_s:
            return self._range_export_one(
                camera_id, from_ts, to_ts, dest,
                progress_callback=progress_callback,
                poll_interval_s=poll_interval_s,
                kickoff_timeout_s=kickoff_timeout_s,
                download_timeout_s=download_timeout_s,
                export_timeout_s=export_timeout_s,
            )

        # Build segment list. Last segment absorbs any remainder rather
        # than producing a tiny tail piece.
        bounds: list[tuple[float, float]] = []
        t = from_ts
        while t < to_ts:
            sub_to = min(t + segment_s, to_ts)
            # If the remaining tail would be < segment_s/2, fold it
            # into the current segment instead of creating a runt.
            if to_ts - sub_to < segment_s / 2:
                sub_to = to_ts
            bounds.append((t, sub_to))
            t = sub_to
        n_segments = len(bounds)
        logger.info(
            "RangeExport segmenting: %.0fs window cam=%d → %d sub-exports "
            "(~%.0fs each)",
            duration, camera_id, n_segments, duration / n_segments,
        )

        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f"sss_seg_{camera_id}_",
            dir=str(dest.parent),
        ) as td:
            td_path = Path(td)
            seg_paths: list[Path] = []
            for i, (sf, st) in enumerate(bounds):
                seg_dest = td_path / f"seg_{i:03d}.mp4"
                seg_idx = i  # capture for closure

                def wrap_cb(stage: str, percent: int,
                            _i: int = seg_idx) -> None:
                    # Aggregate per-segment progress into overall %.
                    # Each segment contributes 1/n; within a segment,
                    # exporting is first half (0-50%), downloading is
                    # second half (50-100%) of segment-internal work.
                    if progress_callback is None:
                        return
                    if stage == "exporting":
                        seg_internal = percent * 0.5
                    elif stage == "downloading":
                        seg_internal = 50.0 + percent * 0.5
                    else:
                        seg_internal = float(percent)
                    overall = int((_i * 100.0 + seg_internal) / n_segments)
                    overall = max(0, min(99, overall))
                    try:
                        progress_callback(stage, overall)
                    except Exception:
                        pass

                seg_path, seg_ext = self._range_export_one(
                    camera_id, sf, st, seg_dest,
                    progress_callback=wrap_cb,
                    poll_interval_s=poll_interval_s,
                    kickoff_timeout_s=kickoff_timeout_s,
                    download_timeout_s=download_timeout_s,
                    export_timeout_s=export_timeout_s,
                )
                # Sub-segment ZIP (codec change mid-segment) — extract
                # the inner MP4s into the concat list. Rare but real.
                if seg_ext == "zip":
                    extract_dir = td_path / f"seg_{i:03d}_zip"
                    extract_dir.mkdir()
                    with zipfile.ZipFile(seg_path) as zf:
                        zf.extractall(extract_dir)
                    inner = sorted(
                        p for p in extract_dir.iterdir()
                        if p.suffix.lower() == ".mp4"
                    )
                    if not inner:
                        raise SSSError(
                            f"RangeExport segment {i} zip had no MP4s"
                        )
                    seg_paths.extend(inner)
                else:
                    seg_paths.append(seg_path)

            # Concat all segments into the final MP4. -c copy is
            # stream-copy (no re-encode) — fast and lossless when the
            # codecs match across segments (always true for us since
            # all sub-windows came from the same camera in the same
            # short timeframe).
            list_file = td_path / "concat.txt"
            list_file.write_text(
                "\n".join(f"file '{p.as_posix()}'" for p in seg_paths) + "\n"
            )
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "concat", "-safe", "0", "-i", str(list_file),
                # Drop audio (SSS PCM_alaw doesn't repackage cleanly).
                "-an", "-c", "copy", str(dest),
            ]
            t0 = time.monotonic()
            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                raise SSSError(
                    f"ffmpeg concat of {n_segments} segments failed: {e}"
                ) from e
            logger.info(
                "RangeExport concat done: %d segments → %dMB in %.1fs",
                n_segments, dest.stat().st_size // 1_000_000,
                time.monotonic() - t0,
            )
        return dest, "mp4"

    def _range_export_one(
        self,
        camera_id: int,
        from_ts: float,
        to_ts: float,
        dest: Path,
        *,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        poll_interval_s: float = 4.0,
        kickoff_timeout_s: float = 60.0,
        download_timeout_s: float = 300.0,
        export_timeout_s: float = 600.0,
    ) -> tuple[Path, str]:
        """Single-window RangeExport (no segmentation). Returns
        (output_path, file_ext) where file_ext is 'mp4' (common) or
        'zip' (codec/resolution change mid-window).

        progress_callback receives (stage, percent) where stage is one
        of 'exporting' (server building the file) or 'downloading'
        (transferring it to us). Used to update UI status indicators.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        # SSS uses fileName for the on-server temp filename; no extension.
        file_name = f"fox_{camera_id}_{int(from_ts)}"

        # Step 1: kick off the export, get a download id.
        kickoff = self._get(
            {
                "api": "SYNO.SurveillanceStation.Recording",
                "version": 6, "method": "RangeExport",
                "camId": camera_id,
                "fromTime": int(from_ts),
                "toTime": int(to_ts),
                "fileName": file_name,
            },
            timeout=kickoff_timeout_s,
        )
        dlid = kickoff.get("dlid")
        if dlid is None:
            raise SSSError(f"RangeExport: no dlid in response {kickoff!r}")
        logger.info(
            "SSS RangeExport kickoff: dlid=%s cam=%d window=%d-%d (%ds)",
            dlid, camera_id, int(from_ts), int(to_ts),
            int(to_ts - from_ts),
        )

        # Step 2: poll until progress=100. Server purges if we go >20s
        # without polling; we use 4s default and re-login transparently
        # via _get on SID expiry (long exports could exceed 11h).
        file_ext = "mp4"
        started = time.monotonic()
        last_reported = -2
        while True:
            prog = self._get(
                {
                    "api": "SYNO.SurveillanceStation.Recording",
                    "version": 6, "method": "GetRangeExportProgress",
                    "dlid": dlid,
                },
                timeout=15.0,
            )
            progress = prog.get("progress", -2)
            ext = prog.get("fileExt")
            if ext:
                file_ext = ext
            if progress == -1:
                raise SSSError(
                    f"RangeExport failed server-side (dlid={dlid}, data={prog!r})"
                )
            if progress != last_reported and progress_callback:
                try:
                    progress_callback("exporting", max(0, int(progress)))
                except Exception:  # callback errors must never abort export
                    logger.warning("range_export progress_callback raised", exc_info=True)
                last_reported = progress
            if progress >= 100:
                break
            if time.monotonic() - started > export_timeout_s:
                raise SSSError(
                    f"RangeExport timed out at {progress}% after "
                    f"{export_timeout_s:.0f}s (dlid={dlid})"
                )
            time.sleep(poll_interval_s)
        export_dt = time.monotonic() - started
        logger.info(
            "SSS RangeExport ready: dlid=%s ext=%s in %.1fs",
            dlid, file_ext, export_dt,
        )

        # Step 3: fetch the result. Server purges within ~60s of progress
        # hitting 100, so do this immediately. SSS regularly drops the
        # connection mid-stream (we routinely saw 1.5GB chunk downloads
        # die at 3-30%; even ~250MB exports can drop at ~30%). We
        # mitigate with HTTP Range resume — on RemoteProtocolError /
        # ReadTimeout / ReadError, retry the GET with `Range: bytes=N-`
        # picking up where we left off. Capped at 3 attempts because
        # SSS server-side purges the export ~60s after progress=100,
        # so longer retry windows would just hit "file gone" anyway.
        target = dest if file_ext == "mp4" else dest.with_suffix(".zip")
        tmp = target.with_suffix(target.suffix + ".part")
        if tmp.exists():
            # Stale .part from a prior failure — discard.
            tmp.unlink()
        sid = self._sid_or_login()
        download_url = f"{self.base_url}/webapi/entry.cgi"
        download_params = {
            "api": "SYNO.SurveillanceStation.Recording",
            "version": 6, "method": "OnRangeExportDone",
            "dlid": dlid, "fileName": file_name, "_sid": sid,
        }
        if progress_callback:
            try:
                progress_callback("downloading", 0)
            except Exception:
                pass
        max_attempts = 3
        per_attempt_timeout = min(download_timeout_s, 120.0)
        bytes_written = 0
        total_bytes: Optional[int] = None
        last_callback = 0.0
        t0 = time.monotonic()

        attempt = 0
        while True:
            attempt += 1
            headers: dict[str, str] = {}
            if bytes_written > 0:
                headers["Range"] = f"bytes={bytes_written}-"
            try:
                with httpx.stream(
                    "GET", download_url,
                    params=download_params, headers=headers,
                    timeout=per_attempt_timeout,
                ) as r:
                    r.raise_for_status()
                    # Defensive: SSS returns JSON (not binary) when the
                    # dlid was purged or the export is gone. Detect
                    # before we start writing it to a .mp4 file.
                    ctype = (r.headers.get("Content-Type") or "").lower()
                    if "application/json" in ctype or ctype.startswith("text/"):
                        body = r.read().decode("utf-8", errors="replace")[:500]
                        raise SSSError(
                            f"OnRangeExportDone returned non-binary "
                            f"({ctype}): {body}"
                        )
                    # If we asked for Range but server returned 200, it
                    # ignored the header — discard partial, restart 0.
                    if headers.get("Range") and r.status_code == 200:
                        logger.warning(
                            "SSS RangeExport: server ignored Range; "
                            "restarting from 0 (had %d bytes)",
                            bytes_written,
                        )
                        if tmp.exists():
                            tmp.unlink()
                        bytes_written = 0
                    # Pick up Content-Length on the first 200 (full
                    # body) and Content-Range / total on a 206.
                    if total_bytes is None:
                        if r.status_code == 200:
                            cl = r.headers.get("Content-Length")
                            if cl:
                                try: total_bytes = int(cl)
                                except ValueError: pass
                        elif r.status_code == 206:
                            cr = r.headers.get("Content-Range") or ""
                            if "/" in cr:
                                try: total_bytes = int(cr.rsplit("/", 1)[-1])
                                except ValueError: pass
                    mode = "ab" if r.status_code == 206 else "wb"
                    with tmp.open(mode) as f:
                        for c in r.iter_bytes(chunk_size=1024 * 1024):
                            f.write(c)
                            bytes_written += len(c)
                            now = time.monotonic()
                            if (progress_callback and total_bytes
                                    and now - last_callback >= 1.0):
                                # Cap at 99 during streaming; the final
                                # 100 fires after rename succeeds.
                                pct = min(99, int(bytes_written * 100 / total_bytes))
                                try:
                                    progress_callback("downloading", pct)
                                except Exception:
                                    pass
                                last_callback = now
                    # Underrun (clean stream end before total_bytes) —
                    # treat as a drop and retry-with-Range.
                    if total_bytes is not None and bytes_written < total_bytes:
                        raise httpx.RemoteProtocolError(
                            f"underrun: {bytes_written}/{total_bytes}",
                            request=r.request,
                        )
                # Done — atomic rename out of .part.
                tmp.rename(target)
                break
            except (httpx.RemoteProtocolError, httpx.ReadTimeout,
                    httpx.ReadError) as e:
                if attempt >= max_attempts:
                    raise SSSError(
                        f"RangeExport download failed after "
                        f"{max_attempts} attempts at "
                        f"{bytes_written}/{total_bytes or '?'} bytes: {e}"
                    ) from e
                logger.warning(
                    "SSS RangeExport drop at %d/%s bytes "
                    "(attempt %d/%d, will resume): %s",
                    bytes_written,
                    str(total_bytes) if total_bytes else "?",
                    attempt, max_attempts, e,
                )
                # Brief backoff. Server purge clock is ~60s post
                # progress=100 so don't dawdle.
                time.sleep(2.0)
        if progress_callback:
            try:
                progress_callback("downloading", 100)
            except Exception:
                pass
        logger.info(
            "SSS RangeExport download done: dlid=%s %dMB in %.1fs (%d attempt%s)",
            dlid, bytes_written // 1_000_000, time.monotonic() - t0,
            attempt, "s" if attempt != 1 else "",
        )
        return target, file_ext


# ---------------------------------------------------------------------------
# Configuration helpers — read SSS_BASE_URL/USER/PASS from env at startup.
# ---------------------------------------------------------------------------

_singleton: Optional[SSSClient] = None
_singleton_lock = threading.Lock()


def get_client() -> Optional[SSSClient]:
    """Return a process-wide SSSClient if SSS_BASE_URL/USER/PASS are set,
    else None. Lazy-initialized; safe to call from many threads."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            base_url = os.environ.get("SSS_BASE_URL")
            user = os.environ.get("SSS_USER")
            password = os.environ.get("SSS_PASS")
            if not all([base_url, user, password]):
                return None
            _singleton = SSSClient(base_url, user, password)  # type: ignore[arg-type]
        return _singleton


# Camera-name → SSS camera-id map. The SSS ids are sequential as cameras
# are added; ours happen to be 10/11/12/14 (cam 4 was added later).
# This is loaded lazily from env vars (SSS_CAM_ID_FOX_DEN_*) with sane
# defaults matching the current install.
def camera_id_map() -> dict[str, int]:
    return {
        "fox_den_1": int(os.environ.get("SSS_CAM_ID_FOX_DEN_1", "10")),
        "fox_den_2": int(os.environ.get("SSS_CAM_ID_FOX_DEN_2", "11")),
        "fox_den_3": int(os.environ.get("SSS_CAM_ID_FOX_DEN_3", "12")),
        "fox_den_4": int(os.environ.get("SSS_CAM_ID_FOX_DEN_4", "14")),
    }
