"""Web Push delivery (VAPID).

Wraps pywebpush so the rest of the codebase only sees `send_to_user`,
`send_to_subscription`, and the broadcast helper. The encryption +
JWT-signing details live here.

Auto-cleanup: when the browser endpoint reports the subscription has
expired (404 Gone or 410 Gone), we delete that row so we don't keep
hammering it. The pywebpush WebPushException carries the response on
its `response` attribute (or `.status_code` on newer versions).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Iterable

from pywebpush import WebPushException, webpush

from . import db


logger = logging.getLogger(__name__)


# Module-level config. Read once at import time from env. Curator's
# launchd plist (or the .env loaded into the venv) supplies these.
_VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
_VAPID_PUBLIC_KEY  = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
_VAPID_SUBJECT     = os.environ.get("VAPID_SUBJECT", "").strip() or "mailto:admin@example.com"


def is_configured() -> bool:
    """True iff both VAPID keys are present. Endpoints that need to
    short-circuit before doing work check this so a misconfigured
    deploy fails loudly with 503 instead of silently dropping pushes."""
    return bool(_VAPID_PRIVATE_KEY) and bool(_VAPID_PUBLIC_KEY)


def vapid_public_key() -> str:
    """Public-key getter — exposed at the HTTP layer so the client can
    fetch it once and call pushManager.subscribe with it."""
    return _VAPID_PUBLIC_KEY


def _claims() -> dict[str, str]:
    return {"sub": _VAPID_SUBJECT}


def send_to_subscription(db_path: Path, sub: dict[str, Any],
                          payload: dict[str, Any], *, ttl: int = 86400
                          ) -> bool:
    """Encrypt + send one push. Returns True on 200/201/202.

    On 404/410 (subscription gone), drop the row and return False.
    Other errors are logged but not raised — push delivery is
    best-effort, never blocks the call site that triggered it.
    """
    if not is_configured():
        logger.warning("web_push: VAPID not configured — skipping send")
        return False
    try:
        webpush(
            subscription_info={
                "endpoint": sub["endpoint"],
                "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
            },
            data=json.dumps(payload),
            vapid_private_key=_VAPID_PRIVATE_KEY,
            vapid_claims=_claims(),
            ttl=ttl,
        )
        return True
    except WebPushException as e:
        # Some pywebpush versions surface .response (a requests Response);
        # newer ones expose .status_code directly.
        status = getattr(e, "status_code", None)
        if status is None and getattr(e, "response", None) is not None:
            status = getattr(e.response, "status_code", None)
        if status in (404, 410):
            logger.info(
                "web_push: subscription gone (%s); deleting endpoint=%s…",
                status, sub["endpoint"][:60],
            )
            db.push_sub_delete_by_endpoint(db_path, sub["endpoint"])
        else:
            logger.warning("web_push: send failed status=%s err=%s", status, e)
        return False
    except Exception:
        logger.exception("web_push: unexpected send failure")
        return False


def _user_filters_pass(db_path: Path, email: str) -> bool:
    """Pause + quiet-hours gate. Both checks short-circuit BEFORE we
    iterate subscriptions so a paused user costs one DB hit, not one
    per device."""
    if db.push_pause_active(db_path, email):
        return False
    if db.push_schedule_active(db_path, email):
        return False
    return True


def _severity_passes(db_path: Path, email: str, kind: str,
                      payload: dict[str, Any]) -> bool:
    """new_highlight has a per-user severity radio — all / clusters /
    high. Other kinds skip this check.

    Thresholds tuned against 7 days of fox + raccoon events from the
    den cameras: ~85% of intra-visit gaps are < 60s, so a 2-minute
    window cleanly catches "they're still around / just back" without
    pulling in stale events from a prior visit (which are typically
    ≥30 minutes earlier). All paths decide within 2 minutes so live
    viewers can still catch the action.
    """
    if kind != "new_highlight":
        return True
    severity = db.push_pref_value_for(db_path, email, "new_highlight") or "all"
    if severity == "all":
        return True

    # Both "clusters" and "high" need a recent-events count for the
    # same camera. Compute once.
    import time as _time
    cam = payload.get("camera")
    likelihood = float(payload.get("fox_likelihood") or 0.0)
    duration = float(payload.get("duration_s") or 0.0)

    def recent_count(window_s: float) -> int:
        if not cam:
            return 0
        with db.connect(db_path) as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM highlights "
                "WHERE camera = ? AND start_time >= ?",
                [cam, _time.time() - window_s],
            ).fetchone()["n"]
        return int(n)

    if severity == "clusters":
        # "Notify me when the fox comes back out" — ≥2 events on the
        # same camera within the last 2 minutes. Fires on the second
        # event of a visit (this one + ≥1 prior in the window). At
        # typical intra-visit gaps (<60s), this lands within ~1 min
        # of arrival.
        return recent_count(120) >= 2
    if severity == "high":
        # "Really out and playing" — three short signals, any of
        # which qualifies, all evaluable within 2 minutes:
        #   ≥3 events same cam in 2 min  → sustained burst pattern
        #   duration ≥ 45s               → one long active sighting
        #   fox_likelihood ≥ 0.9         → very confident heuristic
        if recent_count(120) >= 3:
            return True
        if duration >= 45.0:
            return True
        if likelihood >= 0.9:
            return True
        return False
    return True


def send_to_user(db_path: Path, email: str, kind: str,
                  payload: dict[str, Any]) -> int:
    """Send `payload` to all of `email`'s subscribed devices, IFF the
    user has `kind` enabled, isn't paused, isn't in a quiet-hours
    window, and the severity filter passes for this kind. Returns the
    count of successful deliveries.

    Recommended payload shape:
        {"title": "...", "body": "...", "url": "/...", "tag": "..."}
    `payload` may also carry `camera` / `duration_s` / `fox_likelihood`
    so the severity filter has the data it needs.
    """
    if not is_configured():
        return 0
    if not db.push_pref_enabled_for(db_path, email, kind):
        return 0
    if not _user_filters_pass(db_path, email):
        return 0
    if not _severity_passes(db_path, email, kind, payload):
        return 0
    subs = db.push_sub_list_for_email(db_path, email)
    sent = 0
    for s in subs:
        if send_to_subscription(db_path, s, payload):
            sent += 1
    return sent


def broadcast_kind(db_path: Path, kind: str,
                    payload: dict[str, Any]) -> int:
    """Fan-out broadcast that respects every per-user filter:
    pause, quiet hours, kind enabled, severity. Delivers to a device
    iff its owner clears all gates."""
    if not is_configured():
        return 0
    subs = db.push_sub_list_all_with_kind(db_path, kind)
    # Group subs by owner so we apply user-level filters once per user
    # rather than once per device.
    by_email: dict[str, list[dict]] = {}
    for s in subs:
        by_email.setdefault(s["email"], []).append(s)
    sent = 0
    for email, devices in by_email.items():
        if not _user_filters_pass(db_path, email):
            continue
        if not _severity_passes(db_path, email, kind, payload):
            continue
        for s in devices:
            if send_to_subscription(db_path, s, payload):
                sent += 1
    return sent
