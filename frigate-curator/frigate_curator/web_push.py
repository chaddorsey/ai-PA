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


def send_to_user(db_path: Path, email: str, kind: str,
                  payload: dict[str, Any]) -> int:
    """Send `payload` to all of `email`'s subscribed devices, IFF the
    user has `kind` enabled in their preferences. Returns the count of
    successful deliveries.

    The payload is the JSON the service worker will see in its `push`
    event handler — recommended shape:
        {"title": "...", "body": "...", "url": "/...", "tag": "..."}
    """
    if not is_configured():
        return 0
    if not db.push_pref_enabled_for(db_path, email, kind):
        return 0
    subs = db.push_sub_list_for_email(db_path, email)
    sent = 0
    for s in subs:
        if send_to_subscription(db_path, s, payload):
            sent += 1
    return sent


def broadcast_kind(db_path: Path, kind: str,
                    payload: dict[str, Any]) -> int:
    """Send `payload` to every subscription whose owner has `kind`
    enabled. Used by the new-highlight broadcast path (replaces the
    old single-topic ntfy.sh fan-out). Returns delivery count."""
    if not is_configured():
        return 0
    subs = db.push_sub_list_all_with_kind(db_path, kind)
    sent = 0
    for s in subs:
        if send_to_subscription(db_path, s, payload):
            sent += 1
    return sent
