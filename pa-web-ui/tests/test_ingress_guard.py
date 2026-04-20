"""Unit tests for pa-web-ui/ingress_guard.py.

The guard is loaded with its module-level config frozen at import time,
so these tests monkey-patch the module's constants to simulate different
deployment environments (allowed origins, allowed hosts, signing secret).

Run: cd pa-web-ui && python -m pytest tests/test_ingress_guard.py -v
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import os
import sys
from pathlib import Path

import pytest
from flask import Flask, jsonify


# Ensure we can import `ingress_guard` from the pa-web-ui directory.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _fresh_guard(monkeypatch):
    """Reload the guard with a known config for every test."""
    monkeypatch.setenv("PA_WEB_UI_ALLOWED_ORIGINS", "http://pa-web-ui.local:5200,http://localhost:5200")
    monkeypatch.setenv("PA_WEB_UI_ALLOWED_HOSTS", "pa-web-ui.local:5200,localhost:5200")
    monkeypatch.setenv(
        "PA_WEB_UI_INTERNAL_HOSTS",
        "pa-web-ui:5200,localhost:5200,127.0.0.1:5200",
    )
    monkeypatch.setenv("PA_WEB_UI_CSRF_SECRET", "test-secret-do-not-use-in-prod")

    # Remove any stale import so module-level config re-reads env.
    sys.modules.pop("ingress_guard", None)
    import ingress_guard  # noqa: E402
    importlib.reload(ingress_guard)
    yield ingress_guard


@pytest.fixture
def app(_fresh_guard):
    """Minimal Flask app with the guard wired up and two test routes."""
    ig = _fresh_guard
    app = Flask(__name__)

    @app.route("/api/protected", methods=["POST", "GET"])
    def protected():
        return jsonify({"ok": True})

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    ig.configure_ingress_guard(app)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _mint_device_and_token(ig_module, device_id: str = "device-abc") -> tuple[str, str]:
    token = ig_module._derive_token(device_id)
    return device_id, token


# ----- Host-header allowlist -------------------------------------------------


def test_host_allowlist_rejects_unknown_host(client):
    resp = client.post(
        "/api/protected",
        headers={"Host": "evil.example.com", "Origin": "http://pa-web-ui.local:5200"},
    )
    assert resp.status_code == 421
    body = resp.get_json()
    assert body["error"] == "host_not_allowed"


def test_internal_host_allowed(client):
    """pa-web-ui:5200 is the internal docker name; CORS probes hit via this."""
    resp = client.get(
        "/api/protected",
        headers={"Host": "pa-web-ui:5200"},
    )
    assert resp.status_code == 200


# ----- Exempt paths ----------------------------------------------------------


def test_healthcheck_bypasses_guard(client):
    resp = client.get("/health", headers={"Host": "localhost:5200"})
    assert resp.status_code == 200


def test_healthcheck_allowed_even_without_origin(client):
    resp = client.get("/health", headers={"Host": "localhost:5200"})
    assert resp.status_code == 200


# ----- Origin allowlist (state-changing methods) ----------------------------


def test_post_without_origin_rejected(client):
    resp = client.post("/api/protected", headers={"Host": "localhost:5200"})
    assert resp.status_code == 403
    assert resp.get_json()["error"].startswith("origin_")


def test_post_with_bad_origin_rejected(client):
    resp = client.post(
        "/api/protected",
        headers={
            "Host": "localhost:5200",
            "Origin": "http://attacker.example.com",
        },
    )
    assert resp.status_code == 403


def test_post_with_good_origin_but_no_csrf_rejected(client):
    resp = client.post(
        "/api/protected",
        headers={
            "Host": "localhost:5200",
            "Origin": "http://localhost:5200",
        },
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] in {"missing_device_cookie", "missing_csrf_token"}


# ----- CSRF double-submit ---------------------------------------------------


def test_post_with_valid_csrf_allowed(_fresh_guard, client):
    device_id, token = _mint_device_and_token(_fresh_guard)
    client.set_cookie(_fresh_guard._DEVICE_COOKIE_NAME, device_id)
    client.set_cookie(_fresh_guard._CSRF_COOKIE_NAME, token)

    resp = client.post(
        "/api/protected",
        headers={
            "Host": "localhost:5200",
            "Origin": "http://localhost:5200",
            "X-CSRF-Token": token,
            "Content-Type": "application/json",
        },
        data=json.dumps({}),
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)


def test_post_with_mismatched_csrf_rejected(_fresh_guard, client):
    device_id, token = _mint_device_and_token(_fresh_guard)
    client.set_cookie(_fresh_guard._DEVICE_COOKIE_NAME, device_id)
    client.set_cookie(_fresh_guard._CSRF_COOKIE_NAME, token)

    # Claim a different (tampered) token.
    resp = client.post(
        "/api/protected",
        headers={
            "Host": "localhost:5200",
            "Origin": "http://localhost:5200",
            "X-CSRF-Token": "deadbeef" * 8,
            "Content-Type": "application/json",
        },
        data=json.dumps({}),
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "csrf_mismatch"


def test_post_with_stale_cookie_token_rejected(_fresh_guard, client):
    """Cookie token from a prior secret era must be rejected."""
    device_id = "device-abc"
    good_token = _fresh_guard._derive_token(device_id)
    # Simulate a stale token that doesn't match current HMAC.
    stale_token = "stale" + good_token[5:]
    client.set_cookie(_fresh_guard._DEVICE_COOKIE_NAME, device_id)
    client.set_cookie(_fresh_guard._CSRF_COOKIE_NAME, stale_token)

    resp = client.post(
        "/api/protected",
        headers={
            "Host": "localhost:5200",
            "Origin": "http://localhost:5200",
            "X-CSRF-Token": stale_token,
            "Content-Type": "application/json",
        },
        data=json.dumps({}),
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "csrf_mismatch"


def test_post_with_body_csrf_token_allowed(_fresh_guard, client):
    """Backwards-compat: some routes submit the token in the body."""
    device_id, token = _mint_device_and_token(_fresh_guard)
    client.set_cookie(_fresh_guard._DEVICE_COOKIE_NAME, device_id)
    client.set_cookie(_fresh_guard._CSRF_COOKIE_NAME, token)

    resp = client.post(
        "/api/protected",
        headers={
            "Host": "localhost:5200",
            "Origin": "http://localhost:5200",
            "Content-Type": "application/json",
        },
        data=json.dumps({"csrf_token": token}),
    )
    assert resp.status_code == 200


# ----- GET requests ---------------------------------------------------------


def test_get_with_good_origin_allowed(client):
    resp = client.get(
        "/api/protected",
        headers={"Host": "localhost:5200", "Origin": "http://localhost:5200"},
    )
    assert resp.status_code == 200


def test_get_with_bad_origin_rejected(client):
    """If Origin IS present on a GET but wrong, it's a cross-site read."""
    resp = client.get(
        "/api/protected",
        headers={"Host": "localhost:5200", "Origin": "http://attacker.example.com"},
    )
    assert resp.status_code == 403


def test_get_without_origin_allowed(client):
    """Top-level browser nav has no Origin; don't block regular page loads."""
    resp = client.get("/api/protected", headers={"Host": "localhost:5200"})
    assert resp.status_code == 200


# ----- CSRF token endpoint --------------------------------------------------


def test_csrf_token_endpoint_mints_fresh_device(client):
    resp = client.get("/api/csrf-token", headers={"Host": "localhost:5200"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["csrf_token"]
    assert body["device_id"]
    # Cookie set on response
    cookies = resp.headers.getlist("Set-Cookie")
    cookie_blob = "\n".join(cookies)
    assert "pa_device_id=" in cookie_blob
    assert "pa_csrf_cookie=" in cookie_blob


def test_csrf_token_endpoint_reuses_existing_device(_fresh_guard, client):
    client.set_cookie(_fresh_guard._DEVICE_COOKIE_NAME, "existing-device")
    resp = client.get("/api/csrf-token", headers={"Host": "localhost:5200"})
    body = resp.get_json()
    assert body["device_id"] == "existing-device"
    assert body["csrf_token"] == _fresh_guard._derive_token("existing-device")


# ----- Integration: end-to-end round-trip -----------------------------------


def test_round_trip_via_csrf_endpoint(_fresh_guard, client):
    """Real client flow: fetch token, then POST with it."""
    # 1. Fetch token
    token_resp = client.get("/api/csrf-token", headers={"Host": "localhost:5200"})
    body = token_resp.get_json()
    token = body["csrf_token"]

    # Cookies set automatically by the test client based on Set-Cookie above.
    # 2. POST with token
    post_resp = client.post(
        "/api/protected",
        headers={
            "Host": "localhost:5200",
            "Origin": "http://localhost:5200",
            "X-CSRF-Token": token,
            "Content-Type": "application/json",
        },
        data=json.dumps({}),
    )
    assert post_resp.status_code == 200
