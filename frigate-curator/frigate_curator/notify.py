"""ntfy.sh push notifications for fox-likely events.

Threshold-gated: only fox_likelihood >= NOTIFY_THRESHOLD fires. The
ntfy topic name is the only auth — pick a long unguessable string and
share it with family by having them subscribe in the ntfy iOS/Android
app. Public-permalink URLs in the notification still go through
Cloudflare Access for the actual viewing, so leaking the topic only
exposes "a fox event happened at HH:MM" metadata, not the clip itself.

Disabled (no-op) if NTFY_TOPIC is empty.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx


logger = logging.getLogger(__name__)

# Module-level config — set by main.py at startup.
_BASE_URL: str = "https://ntfy.sh"
_TOPIC: Optional[str] = None
_PUBLIC_BASE: str = "https://foxes.cd-ai-pa.work"
_THRESHOLD: float = 0.55


def configure(base_url: str, topic: Optional[str], public_base: str, threshold: float) -> None:
    global _BASE_URL, _TOPIC, _PUBLIC_BASE, _THRESHOLD
    _BASE_URL = base_url.rstrip("/")
    _TOPIC = topic or None
    _PUBLIC_BASE = public_base.rstrip("/")
    _THRESHOLD = threshold


def maybe_notify(highlight: dict) -> bool:
    """Send a push if the highlight clears the threshold. Returns True if sent."""
    if not _TOPIC:
        return False
    likelihood = float(highlight.get("fox_likelihood") or 0.0)
    if likelihood < _THRESHOLD:
        return False

    event_id = highlight["event_id"]
    camera = highlight.get("camera", "unknown")
    label = highlight.get("label", "?")
    duration = float(highlight.get("duration_s") or 0.0)
    pct = int(round(likelihood * 100))

    clip_url = f"{_PUBLIC_BASE}/clip/{event_id}"
    thumb_url = f"{_PUBLIC_BASE}/api/highlights/{event_id}/thumbnail"

    headers = {
        "Title": f"Fox Cam - {camera} ({pct}%)",
        "Click": clip_url,
        "Attach": thumb_url,
        "Tags": "fox",
        "Priority": "high" if likelihood >= 0.75 else "default",
    }
    body = f"{label} - {duration:.0f}s"

    try:
        r = httpx.post(f"{_BASE_URL}/{_TOPIC}", headers=headers, content=body.encode("utf-8"), timeout=5.0)
        r.raise_for_status()
        logger.info("Notified ntfy for %s likelihood=%.2f", event_id, likelihood)
        return True
    except Exception:
        logger.exception("ntfy push failed for %s", event_id)
        return False
