#!/usr/bin/env python3
"""
Granola Meeting Ingest Trigger Service

Lightweight HTTP server that exposes a trigger endpoint for the
scheduler-service to call. Runs on the host (not in Docker) because
it needs access to the Granola MCP proxy and the shared state file.

Endpoints:
    POST /v1/trigger  — Run meeting import (last_30_days by default)
    GET  /v1/status   — Return import state (count, last check)
    GET  /health      — Health check

Usage:
    python scripts/granola_ingest_service.py              # port 8090
    python scripts/granola_ingest_service.py --port 8091  # custom port
"""

import argparse
import json
import logging
import os
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Add letta directory so we can import the ingest module
LETTA_DIR = Path(__file__).resolve().parent.parent / "letta"
sys.path.insert(0, str(LETTA_DIR))

# Set environment before importing the module
os.environ.setdefault("LETTA_BASE_URL", "http://localhost:8283")
os.environ.setdefault("GRANOLA_MCP_URL", "http://localhost:8089/mcp")

import granola_mcp_to_archival as ingest

DEFAULT_PORT = 8090

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LETTA_DIR / "logs" / "granola_ingest_service.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Guard against concurrent imports
_import_lock = threading.Lock()
_last_result = None
_last_run_time = None


def run_import(time_range: str = "last_30_days") -> dict:
    """Run the meeting import and return a result dict."""
    global _last_result, _last_run_time

    if not _import_lock.acquire(blocking=False):
        return {"status": "busy", "message": "Import already in progress"}

    try:
        state = ingest.load_state()
        imported_ids = set(state.get("imported_ids", []))
        previously_imported = len(imported_ids)

        meetings = ingest.fetch_meeting_list(time_range)
        if not meetings:
            result = {
                "status": "ok",
                "message": "No meetings returned from MCP",
                "imported": 0,
                "errors": 0,
                "total_in_state": previously_imported,
            }
            _last_result = result
            _last_run_time = time.time()
            return result

        success, errors = ingest.ingest_meetings(meetings, imported_ids, dry_run=False)

        # Save state
        if success > 0:
            state["imported_ids"] = list(imported_ids)
            ingest.save_state(state)

        result = {
            "status": "ok",
            "message": f"Imported {success} meeting(s), {errors} error(s)",
            "imported": success,
            "errors": errors,
            "meetings_checked": len(meetings),
            "total_in_state": len(imported_ids),
        }
        _last_result = result
        _last_run_time = time.time()
        return result

    except Exception as e:
        logger.error(f"Import failed: {e}", exc_info=True)
        result = {"status": "error", "message": str(e)}
        _last_result = result
        _last_run_time = time.time()
        return result

    finally:
        _import_lock.release()


class IngestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the ingest trigger service."""

    def do_POST(self):
        if self.path == "/v1/trigger":
            logger.info("Trigger received — starting import")
            result = run_import()
            self._json_response(200, result)
        else:
            self._json_response(404, {"error": "Not found"})

    def do_GET(self):
        if self.path == "/health":
            self._json_response(200, {"status": "healthy"})
        elif self.path == "/v1/status":
            state = ingest.load_state()
            self._json_response(200, {
                "status": "ok",
                "imported_count": len(state.get("imported_ids", [])),
                "last_check": state.get("last_check", "never"),
                "last_run_result": _last_result,
                "last_run_time": _last_run_time,
            })
        else:
            self._json_response(404, {"error": "Not found"})

    def _json_response(self, status_code: int, body: dict):
        payload = json.dumps(body).encode()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        # Route access logs through our logger instead of stderr
        logger.debug(f"{self.client_address[0]} - {format % args}")


def main():
    parser = argparse.ArgumentParser(description="Granola ingest trigger service")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    # Ensure log directory exists
    (LETTA_DIR / "logs").mkdir(parents=True, exist_ok=True)

    server = HTTPServer(("0.0.0.0", args.port), IngestHandler)
    logger.info(f"Granola ingest trigger service listening on port {args.port}")
    logger.info(f"  POST /v1/trigger  — run import")
    logger.info(f"  GET  /v1/status   — check state")
    logger.info(f"  GET  /health      — health check")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
        server.server_close()


if __name__ == "__main__":
    main()
