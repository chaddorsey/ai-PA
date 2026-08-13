"""Flask HTTP server — the producer-facing surface.

Routes:
  POST /push   — dispatch a prompt to an agent's warm subprocess
  GET  /health — receiver self-check (always 200 if process is alive)
  GET  /status — warm pool inventory (which agents are warm, pids, etc.)
"""
from __future__ import annotations

import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, request

from .app_server_client import AppServerClient
from .config import (
    APP_SERVER_ENABLED,
    APP_SERVER_URL,
    DEFAULT_AGENTS,
    DEFAULT_SOURCE_ROUTING,
    listen_host,
    listen_port,
)
from .models import PushRequest
from .warm_pool import WarmPool


def _log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[{ts}] {msg}", file=sys.stdout, flush=True)


def create_app() -> Flask:
    app = Flask(__name__)
    pool = WarmPool(DEFAULT_AGENTS, _log)
    app.config["WARM_POOL"] = pool

    # The sole-owner App Server is an EXTERNAL, launchd-supervised process
    # (plan Unit 2). The receiver is a pure CLIENT of it: it no longer boots
    # or supervises a server, and it NEVER forks a local subprocess (the
    # warm-pool dispatch fallback was removed to preserve the single-writer
    # invariant on lc-local-backend). The client is always constructed — not
    # gated on a boot succeeding — so a transient App Server outage can't wedge
    # the receiver into a permanent warm-pool-fork mode (the old sticky-None bug).
    app_client = None
    enrich_pool = None
    if APP_SERVER_ENABLED:
        app_client = AppServerClient(APP_SERVER_URL, _log)
        enrich_pool = ThreadPoolExecutor(max_workers=4)  # fire-and-forget; fresh conv per call = no per-agent serialization
    app.config["APP_CLIENT"] = app_client
    app.config["ENRICH_POOL"] = enrich_pool

    # ---- routes ----

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "letta-push-receiver"})

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify({
            "agents_configured": sorted(DEFAULT_AGENTS.keys()),
            "source_routing": DEFAULT_SOURCE_ROUTING,
            "warm_subprocesses": pool.status(),
        })

    @app.route("/push", methods=["POST"])
    def push():
        try:
            body = request.get_json(force=True, silent=False) or {}
            pr = PushRequest.from_json(body)
        except Exception as e:
            return jsonify({"status": "error", "error_message": str(e)}), 400

        # Resolve agent: explicit > routed from source > error
        agent_slug = pr.agent
        if not agent_slug and pr.source:
            agent_slug = DEFAULT_SOURCE_ROUTING.get(pr.source)
        if not agent_slug:
            return jsonify({
                "status": "error",
                "error_message": (
                    "could not resolve agent — provide 'agent' "
                    "or a 'source' that's in the routing table"
                ),
                "routing": DEFAULT_SOURCE_ROUTING,
            }), 400
        if agent_slug not in DEFAULT_AGENTS:
            return jsonify({
                "status": "error",
                "error_message": f"unknown agent '{agent_slug}'",
                "valid_agents": sorted(DEFAULT_AGENTS.keys()),
            }), 400

        _log(
            f"PUSH agent={agent_slug} priority={pr.priority} "
            f"source={pr.source} source_ref={pr.source_ref} "
            f"prompt_chars={len(pr.prompt)}"
        )

        # SINGLE DISPATCH PATH: the external sole-owner App Server. The
        # receiver must never fork a local subprocess (that would open
        # lc-local-backend as a second writer → the projection-divergence race
        # this whole effort exists to eliminate). There is deliberately NO
        # warm-pool fallback here.
        if not (APP_SERVER_ENABLED and app_client is not None):
            return jsonify({
                "status": "unavailable",
                "error_message": "App Server dispatch disabled (PA_APP_SERVER_ENABLED != 1)",
            }), 503

        if not app_client.is_reachable():
            # App Server down → synchronous, retryable 503 so the producer
            # retries later — NOT a false 202, and NOT a warm-pool fork.
            _log(f"PUSH 503 app-server-unreachable agent={agent_slug}")
            return jsonify({
                "status": "unavailable",
                "error_message": "sole-owner App Server unreachable; retry",
                "agent": agent_slug,
            }), 503

        def _run_enrich(slug=agent_slug, prompt=pr.prompt):
            try:
                r = app_client.enrich(slug, prompt)  # slug -> friendly model (SLUG_TO_MODEL)
                _log(f"ENRICH {slug} -> {r.status} ctx={r.context_tokens}")
            except Exception as e:
                # Mid-flight App Server disconnect: logged as failed. Full
                # retry/idempotency (durable queue) is a deferred fast-follow
                # (plan Risks: in-flight enrichment loss on restart).
                _log(f"ENRICH FAILED {slug}: {e}")
        enrich_pool.submit(_run_enrich)
        return jsonify({"status": "queued", "agent": agent_slug,
                        "dispatch": "app-server"}), 202

    # ---- shutdown hook ----

    @app.teardown_appcontext
    def _teardown(exc):
        # No-op per-request; the pool (and the App Server, if enabled) are
        # shut down on process exit via signal handler in __main__.
        return None

    return app


def main():
    app = create_app()
    host = listen_host()
    port = listen_port()

    def _shutdown(signum, frame):
        _log(f"received signal {signum}, shutting down")
        enrich_pool = app.config.get("ENRICH_POOL")
        if enrich_pool is not None:
            enrich_pool.shutdown(wait=False, cancel_futures=True)
        pool = app.config.get("WARM_POOL")
        if pool is not None:
            pool.shutdown()
        # No App Server to shut down here — it is an external, launchd-supervised
        # process (plan Unit 2); the receiver is only a client of it.
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    _log(f"letta-push-receiver listening on {host}:{port}")
    # Single-threaded for simplicity; dispatch is fast (just a stdin
    # write). If we need concurrency, switch to gunicorn later.
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
