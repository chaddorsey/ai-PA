"""Flask HTTP server — the producer-facing surface.

Routes:
  POST /push   — dispatch a prompt to an agent's warm subprocess
  GET  /health — receiver self-check (always 200 if process is alive)
  GET  /status — warm pool inventory (which agents are warm, pids, etc.)
"""
from __future__ import annotations

import json
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, request

from .app_server import AppServer
from .app_server_client import AppServerClient
from .config import (
    APP_SERVER_ENABLED,
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

    app_server = None
    app_client = None
    enrich_pool = None
    if APP_SERVER_ENABLED:
        try:
            app_server = AppServer(_log)
            app_server.ensure()
            app_client = AppServerClient(app_server.base_url, _log)
            enrich_pool = ThreadPoolExecutor(max_workers=4)  # fire-and-forget; fresh conv per call = no per-agent serialization
        except Exception as e:
            # Degrade, don't crash: a failed App Server boot must not take
            # the receiver's port down with it. The /push handler's
            # `app_client is not None` guard falls through to the warm-pool
            # fallback below when these stay None.
            _log(f"WARNING: App Server failed to start, degrading to warm-pool-only mode: {e}")
            app_server = None
            app_client = None
            enrich_pool = None
    app.config["APP_SERVER"] = app_server
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

        if APP_SERVER_ENABLED and app_client is not None:
            def _run_enrich(slug=agent_slug, prompt=pr.prompt):
                try:
                    app_server.ensure()                  # restart-on-death
                    r = app_client.enrich(slug, prompt)  # slug -> friendly model (SLUG_TO_MODEL)
                    _log(f"ENRICH {slug} -> {r.status} ctx={r.context_tokens}")
                except Exception as e:
                    _log(f"ENRICH FAILED {slug}: {e}")
            enrich_pool.submit(_run_enrich)
            return jsonify({"status": "queued", "agent": agent_slug,
                            "dispatch": "app-server"}), 202
        # else: fall through to the existing pool.dispatch(agent_slug, pr.prompt) path (unchanged fallback)

        try:
            result = pool.dispatch(agent_slug, pr.prompt)
            return jsonify({
                "status": "accepted",
                "agent": agent_slug,
                "source_ref": pr.source_ref,
                **result,
            }), 202
        except Exception as e:
            _log(f"DISPATCH FAILED for {agent_slug}: {e}")
            return jsonify({
                "status": "error",
                "error_message": str(e),
            }), 502

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
        app_server = app.config.get("APP_SERVER")
        if app_server is not None:
            app_server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    _log(f"letta-push-receiver listening on {host}:{port}")
    # Single-threaded for simplicity; dispatch is fast (just a stdin
    # write). If we need concurrency, switch to gunicorn later.
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
