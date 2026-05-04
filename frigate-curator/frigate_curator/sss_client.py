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
import threading
import time
from pathlib import Path
from typing import Any, Optional

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
        so we don't buffer 200-700MB in memory."""
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
