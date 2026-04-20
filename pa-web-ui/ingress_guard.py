"""HTTP ingress guard for pa-web-ui.

Implements three layered checks on every inbound request, running before
route dispatch:

1. Host-header allowlist (DNS-rebind mitigation)
2. Origin/Referer allowlist (CSRF origin check)
3. CSRF double-submit token match (CSRF token check)

The guard runs in Flask's before_request pipeline. A failing check returns
an early response (403 or 421) and the route handler is never invoked.

Exemptions (the "open" list):
- GET/HEAD requests to /health (Docker healthcheck).
- GET requests to /static/* (browser loads assets on page load).
- OPTIONS preflight (Flask-CORS handles these; the guard short-circuits).

Design notes:
- The CSRF token is a HMAC of the device cookie with a server-side secret.
  This way we do not need server-side session storage — token validity is
  provable from the request alone.
- The token is emitted via GET /api/csrf-token which sets the cookie and
  returns the token in the JSON body. Clients include the token on state-
  changing requests via X-CSRF-Token header OR a csrf_token body field.
- A missing Origin header fails the check for any non-safe method. curl and
  server-to-server callers that need write access must either set a valid
  Origin or use an internal-only route (not guarded).

See docs/security/pa-web-ui-threat-model.md for the full posture.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Iterable
from urllib.parse import urlparse

from flask import Flask, Response, g, jsonify, make_response, request


# -------------------- configuration helpers --------------------

def _parse_csv_env(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _load_secret() -> bytes:
    """Load or mint the server-side CSRF-signing secret.

    Prefers PA_WEB_UI_CSRF_SECRET from env (set in docker-compose). Falls
    back to a per-process random value so dev restarts don't crash; the
    fallback invalidates outstanding tokens on restart, which is acceptable
    because clients re-fetch on every page load anyway.
    """
    env_val = os.environ.get("PA_WEB_UI_CSRF_SECRET", "").strip()
    if env_val:
        return env_val.encode("utf-8")
    return secrets.token_bytes(32)


# Resolved once at import; app init calls configure_ingress_guard() to wire
# these into the Flask app.
_ALLOWED_ORIGINS: list[str] = _parse_csv_env("PA_WEB_UI_ALLOWED_ORIGINS")
_ALLOWED_HOSTS: list[str] = _parse_csv_env("PA_WEB_UI_ALLOWED_HOSTS")
_INTERNAL_HOSTS: list[str] = _parse_csv_env(
    "PA_WEB_UI_INTERNAL_HOSTS",
    default="pa-web-ui:5200,localhost:5200,127.0.0.1:5200",
)
_CSRF_SECRET: bytes = _load_secret()
_DEVICE_COOKIE_NAME = "pa_device_id"
_CSRF_COOKIE_NAME = "pa_csrf_cookie"

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
EXEMPT_PATHS = {"/health"}
EXEMPT_PATH_PREFIXES = ("/static/",)


# -------------------- CSRF token derivation --------------------

def _derive_token(device_id: str) -> str:
    """HMAC(secret, device_id) — the canonical CSRF token for this device."""
    mac = hmac.new(_CSRF_SECRET, device_id.encode("utf-8"), hashlib.sha256)
    return mac.hexdigest()


def _get_or_set_device_id(resp_setter) -> str:
    """Return the device id from the cookie; mint+set on the response if missing.

    `resp_setter` is a callable that takes (cookie_name, cookie_value,
    kwargs) and sets a cookie on the outgoing response. This indirection
    keeps the function usable from both before_request (no response yet)
    and explicit token-emission endpoints (response in hand).
    """
    existing = request.cookies.get(_DEVICE_COOKIE_NAME, "").strip()
    if existing:
        return existing
    minted = secrets.token_urlsafe(32)
    resp_setter(
        _DEVICE_COOKIE_NAME,
        minted,
        {
            "samesite": "Strict",
            "httponly": True,
            "secure": False,  # Tailscale is the transport; we are not TLS-terminating here
            "max_age": 60 * 60 * 24 * 365,
        },
    )
    return minted


# -------------------- request-level decisions --------------------

def _origin_ok(header_origin: str | None, header_referer: str | None) -> bool:
    """True if the request's Origin (or Referer if absent) is allowlisted."""
    candidate = header_origin
    if not candidate and header_referer:
        # Reduce Referer down to scheme+host
        try:
            p = urlparse(header_referer)
            if p.scheme and p.netloc:
                candidate = f"{p.scheme}://{p.netloc}"
        except Exception:
            candidate = None
    if not candidate:
        return False
    return candidate in _ALLOWED_ORIGINS


def _host_ok(host_header: str | None) -> bool:
    if not host_header:
        return False
    return host_header in _ALLOWED_HOSTS or host_header in _INTERNAL_HOSTS


def _is_exempt_path(path: str) -> bool:
    if path in EXEMPT_PATHS:
        return True
    for prefix in EXEMPT_PATH_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _extract_csrf_claim() -> str | None:
    """Client-supplied CSRF token — header first, then body."""
    header = request.headers.get("X-CSRF-Token", "").strip()
    if header:
        return header
    if request.is_json:
        try:
            body = request.get_json(silent=True) or {}
            val = body.get("csrf_token")
            if isinstance(val, str) and val.strip():
                return val.strip()
        except Exception:
            pass
    form_val = request.form.get("csrf_token", "").strip()
    if form_val:
        return form_val
    return None


# -------------------- the actual Flask hooks --------------------

def _before_request_guard() -> Response | None:
    """Flask before_request callback; returns an early Response on rejection."""
    # Host check runs for every request — it's cheap and shuts down
    # DNS-rebind attempts before anything else.
    if not _host_ok(request.host):
        return make_response(
            jsonify({"error": "host_not_allowed", "host": request.host}),
            421,
        )

    # Exempt routes bypass Origin + CSRF.
    if _is_exempt_path(request.path):
        return None

    # OPTIONS preflight is handled by Flask-CORS; let it through.
    if request.method == "OPTIONS":
        return None

    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")
    origin_allowed = _origin_ok(origin, referer)

    # GETs: Origin is preferred but not strictly required (browser top-level
    # nav has no Origin). We only enforce Origin on state-changing methods.
    if request.method in SAFE_METHODS:
        # If Origin IS present and is wrong, reject — that's a cross-site read.
        if (origin or referer) and not origin_allowed:
            return make_response(
                jsonify({"error": "origin_not_allowed", "origin": origin or referer}),
                403,
            )
        return None

    # State-changing method: require Origin allowlisted AND CSRF token match.
    if not origin_allowed:
        return make_response(
            jsonify({"error": "origin_required_or_not_allowed", "origin": origin}),
            403,
        )

    device_id = request.cookies.get(_DEVICE_COOKIE_NAME, "").strip()
    if not device_id:
        return make_response(
            jsonify({"error": "missing_device_cookie"}),
            403,
        )
    cookie_token = request.cookies.get(_CSRF_COOKIE_NAME, "").strip()
    claimed_token = _extract_csrf_claim()
    expected_token = _derive_token(device_id)
    if not cookie_token or not claimed_token:
        return make_response(
            jsonify({"error": "missing_csrf_token"}),
            403,
        )
    # Compare both sides against the expected HMAC — rejects stale tokens from
    # a prior server secret, and rejects tokens that were tampered with.
    if not (
        hmac.compare_digest(cookie_token, expected_token)
        and hmac.compare_digest(claimed_token, expected_token)
    ):
        return make_response(
            jsonify({"error": "csrf_mismatch"}),
            403,
        )

    # Stash the device id on `g` for downstream handlers.
    g.device_id = device_id
    return None


def _csrf_token_endpoint():
    """GET /api/csrf-token — mint or refresh the device-scoped CSRF token.

    Sets the double-submit cookie and returns the same token in the JSON
    body. Frontend stashes it in sessionStorage and includes it on every
    state-changing POST/PATCH/DELETE.
    """
    resp = make_response(jsonify({"csrf_token": "", "device_id": ""}))
    cookie_writes: list[tuple[str, str, dict]] = []

    def _set(name: str, value: str, kwargs: dict) -> None:
        cookie_writes.append((name, value, kwargs))

    device_id = _get_or_set_device_id(_set)
    token = _derive_token(device_id)

    # Apply deferred cookie writes now that we have a response object.
    for name, value, kwargs in cookie_writes:
        resp.set_cookie(name, value, **kwargs)

    resp.set_cookie(
        _CSRF_COOKIE_NAME,
        token,
        samesite="Strict",
        httponly=False,  # Readable by JS for the double-submit mirror
        secure=False,
        max_age=60 * 60 * 24 * 30,
    )
    resp.set_data(
        jsonify({"csrf_token": token, "device_id": device_id}).get_data()
    )
    return resp


# -------------------- public API --------------------

def configure_ingress_guard(app: Flask) -> None:
    """Register the before-request hook and the CSRF token endpoint."""
    app.before_request(_before_request_guard)
    app.add_url_rule(
        "/api/csrf-token",
        view_func=_csrf_token_endpoint,
        methods=["GET"],
    )


# -------------------- test-visible helpers --------------------
# These are imported by pa-web-ui/tests/test_ingress_guard.py. They are NOT
# part of the runtime public surface.

def _test_helpers():
    return {
        "derive_token": _derive_token,
        "allowed_origins": list(_ALLOWED_ORIGINS),
        "allowed_hosts": list(_ALLOWED_HOSTS),
        "internal_hosts": list(_INTERNAL_HOSTS),
        "device_cookie_name": _DEVICE_COOKIE_NAME,
        "csrf_cookie_name": _CSRF_COOKIE_NAME,
    }
