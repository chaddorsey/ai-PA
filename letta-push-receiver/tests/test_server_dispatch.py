"""server.py dispatch: single App Server path, NEVER forks (plan Unit 2c).

The load-bearing guarantee: the receiver must never call pool.dispatch (which
forks `letta --backend local` = a second writer on lc-local-backend). An App
Server outage returns a synchronous, retryable 503 — not a false 202, not a fork.
"""
from letta_push_receiver import server as srv
from letta_push_receiver.app_server_client import AppServerClient
from letta_push_receiver.warm_pool import WarmPool


def _client(monkeypatch, *, enabled: bool, reachable: bool):
    monkeypatch.setattr(srv, "APP_SERVER_ENABLED", enabled)

    def _forbidden_fork(*a, **k):
        raise AssertionError("pool.dispatch must NEVER be called — single-writer invariant")

    monkeypatch.setattr(WarmPool, "dispatch", _forbidden_fork)
    monkeypatch.setattr(AppServerClient, "is_reachable", lambda self, timeout=2.0: reachable)
    # keep the async enrich off the network
    monkeypatch.setattr(AppServerClient, "enrich", lambda self, slug, prompt: None)
    app = srv.create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_unreachable_returns_503_and_never_forks(monkeypatch):
    c = _client(monkeypatch, enabled=True, reachable=False)
    r = c.post("/push", json={"agent": "docs", "prompt": "hi"})
    assert r.status_code == 503
    assert r.get_json()["status"] == "unavailable"
    # the AssertionError in _forbidden_fork would have surfaced if dispatch ran


def test_reachable_returns_202_app_server_dispatch(monkeypatch):
    c = _client(monkeypatch, enabled=True, reachable=True)
    r = c.post("/push", json={"agent": "docs", "prompt": "hi"})
    assert r.status_code == 202
    body = r.get_json()
    assert body["status"] == "queued"
    assert body["dispatch"] == "app-server"


def test_disabled_returns_503_and_never_forks(monkeypatch):
    c = _client(monkeypatch, enabled=False, reachable=True)
    r = c.post("/push", json={"agent": "docs", "prompt": "hi"})
    assert r.status_code == 503


def test_unknown_agent_still_400(monkeypatch):
    c = _client(monkeypatch, enabled=True, reachable=True)
    r = c.post("/push", json={"agent": "nope", "prompt": "hi"})
    assert r.status_code == 400
