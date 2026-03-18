#!/usr/bin/env python3
"""Laptop Presence Service — receives online signals from the laptop,
checks for pending tasks in Rover's tasks block, and notifies MC.

Runs on the server on port 8891.
"""

import http.server
import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime

PORT = int(os.environ.get("PRESENCE_PORT", "8891"))
LETTA_URL = os.environ.get("LETTA_URL", "http://localhost:8283")
MC_AGENT_ID = os.environ.get("MC_AGENT_ID", "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef")
ROVER_AGENT_ID = os.environ.get("ROVER_AGENT_ID", "agent-76ee5448-68ec-4fdd-b102-d4895d44e090")
LAPTOP_SSH = "chaddorsey@100.95.213.46"
DEBOUNCE_SECS = 30

last_signal_time = 0


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def check_ssh():
    """Verify SSH connectivity to laptop."""
    try:
        r = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=3", "-o", "StrictHostKeyChecking=no",
             LAPTOP_SSH, "echo", "ok"],
            capture_output=True, text=True, timeout=5
        )
        return r.returncode == 0
    except Exception:
        return False


def check_pending_tasks():
    """Check if Rover's tasks block has pending work."""
    try:
        resp = urllib.request.urlopen(
            f"{LETTA_URL}/v1/agents/{ROVER_AGENT_ID}/core-memory/", timeout=5
        )
        data = json.loads(resp.read())
        for v in data.values():
            if isinstance(v, list):
                for b in v:
                    if isinstance(b, dict) and b.get("label") == "tasks":
                        content = b.get("value", "").strip()
                        if content and "No pending" not in content and len(content) > 20:
                            return True, content[:200]
        return False, ""
    except Exception as e:
        log(f"Error checking tasks: {e}")
        return False, ""


def notify_mc():
    """Tell MC the laptop is online and tasks are pending."""
    try:
        payload = json.dumps({
            "messages": [{
                "role": "system",
                "content": (
                    "[SYSTEM] The laptop just came online and SSH is available. "
                    "There are pending tasks in Rover's tasks block. "
                    "Please review and instruct Rover to process them."
                )
            }]
        }).encode()
        req = urllib.request.Request(
            f"{LETTA_URL}/v1/agents/{MC_AGENT_ID}/messages",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=30)
        log("MC notified of pending tasks")
    except Exception as e:
        log(f"Failed to notify MC: {e}")


def handle_online_signal():
    """Process a laptop online signal."""
    global last_signal_time
    now = time.time()

    if now - last_signal_time < DEBOUNCE_SECS:
        log(f"Debounced ({int(now - last_signal_time)}s since last)")
        return
    last_signal_time = now

    log("Laptop online signal received")

    if not check_ssh():
        log("SSH not ready yet, skipping")
        return
    log("SSH connectivity verified")

    has_tasks, preview = check_pending_tasks()
    if has_tasks:
        log(f"Pending tasks found: {preview}...")
        notify_mc()
    else:
        log("No pending tasks")


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/laptop-online":
            handle_online_signal()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default access logs


if __name__ == "__main__":
    log(f"Laptop presence service listening on port {PORT}")
    log(f"  Letta: {LETTA_URL}")
    log(f"  MC: {MC_AGENT_ID}")
    log(f"  Rover: {ROVER_AGENT_ID}")
    log(f"  SSH: {LAPTOP_SSH}")
    httpd = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    httpd.serve_forever()
