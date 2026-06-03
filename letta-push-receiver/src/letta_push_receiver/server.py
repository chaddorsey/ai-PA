"""Flask HTTP server — the producer-facing surface.

Routes:
  POST /push   — dispatch a prompt to an agent's warm subprocess
  GET  /health — receiver self-check (always 200 if process is alive)
  GET  /status — warm pool inventory (which agents are warm, pids, etc.)
"""
from __future__ import annotations

import json
import sys
import time

from flask import Flask, jsonify, request

from .config import (
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
        # No-op per-request; the pool is shut down on process exit
        # via signal handler in __main__.
        return None

    return app


def main():
    app = create_app()
    host = listen_host()
    port = listen_port()
    _log(f"letta-push-receiver listening on {host}:{port}")
    # Single-threaded for simplicity; dispatch is fast (just a stdin
    # write). If we need concurrency, switch to gunicorn later.
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
