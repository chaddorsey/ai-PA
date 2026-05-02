"""Thin Frigate API client.

Uses the JWT-based auth introduced in Frigate 0.13+. The curator stores
admin credentials in env vars, gets a token, and refreshes on 401.

Endpoints touched (all read-only):
  POST /api/login
  GET  /api/events
  GET  /api/events/<id>/clip.mp4
  GET  /api/events/<id>/thumbnail.jpg
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import httpx


logger = logging.getLogger(__name__)


class FrigateClient:
    def __init__(self, base_url: str, user: str, password: str) -> None:
        # Frigate 0.17 ships a self-signed cert on 8971; verify=False is
        # acceptable here because we only ever talk to localhost.
        self._client = httpx.Client(base_url=base_url, verify=False, timeout=15.0)
        self._user = user
        self._password = password
        self._jwt: str | None = None
        self._jwt_expires: float = 0.0

    def _login(self) -> None:
        r = self._client.post("/api/login", json={"user": self._user, "password": self._password})
        r.raise_for_status()
        # Frigate sets the JWT as an httpOnly cookie. httpx persists it
        # automatically across the same client. We just track expiry so
        # we know when to refresh.
        self._jwt_expires = time.time() + 23 * 3600  # JWT lifetime is 24h
        logger.info("Logged in to Frigate as %s", self._user)

    def _ensure_auth(self) -> None:
        if self._jwt_expires - time.time() < 300:
            self._login()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        self._ensure_auth()
        r = self._client.request(method, path, **kwargs)
        if r.status_code == 401:
            self._login()
            r = self._client.request(method, path, **kwargs)
        return r

    def list_events(
        self,
        after: float | None = None,
        before: float | None = None,
        labels: list[str] | None = None,
        cameras: list[str] | None = None,
        has_clip: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "include_thumbnails": 0}
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before
        if labels:
            params["labels"] = ",".join(labels)
        if cameras:
            params["cameras"] = ",".join(cameras)
        if has_clip:
            params["has_clip"] = 1
        r = self._request("GET", "/api/events", params=params)
        r.raise_for_status()
        return r.json()

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        r = self._request("GET", f"/api/events/{event_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def download_clip(self, event_id: str, dest: Path) -> bool:
        return self._download(f"/api/events/{event_id}/clip.mp4", dest)

    def download_thumbnail(self, event_id: str, dest: Path) -> bool:
        return self._download(f"/api/events/{event_id}/thumbnail.jpg", dest)

    def _download(self, path: str, dest: Path) -> bool:
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = self._request("GET", path)
        if r.status_code == 404:
            return False
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_bytes(r.content)
        tmp.rename(dest)
        return True
