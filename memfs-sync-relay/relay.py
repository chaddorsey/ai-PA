#!/usr/bin/env python3
"""Gitea webhook -> Letta sync-from-git relay.

Receives push webhooks from Gitea, extracts the agent_id from the repo name
(`agents/{agent_id}.git`), and POSTs to
`{LETTA_BASE_URL}/v1/agents/{agent_id}/memory/sync-from-git` to refresh the
agent's bare repo + Postgres block cache.

This closes the operational gap where letta-code's Edit tool pushes to Gitea
automatically but the server's bare repo + Postgres cache stay stale until
sync-from-git is explicitly triggered. With this relay running, every Gitea
push to an agent repo automatically refreshes the server-side state, so REST
consumers (slackbot, pa-routing-handler, pa-web-ui) see fresh content
without manual intervention.

Spec source: Ezra's recommendation in the Apr 25 defects-note exchange.
"""

import hashlib
import hmac
import http.server
import json
import logging
import os
import re
import urllib.error
import urllib.request

PORT = int(os.environ.get("RELAY_PORT", "8901"))
LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://letta:8283")
WEBHOOK_SECRET = os.environ.get("GITEA_WEBHOOK_SECRET", "")
ALLOWED_ORG = os.environ.get("ALLOWED_GITEA_ORG", "agents")
ALLOWED_BRANCHES = set((os.environ.get("ALLOWED_BRANCHES", "main").split(",")))

AGENT_ID_PATTERN = re.compile(r"^agent-[0-9a-f-]{36}$")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("memfs-sync-relay")


def verify_signature(body: bytes, header_sig: str) -> bool:
    if not WEBHOOK_SECRET:
        return True
    if not header_sig:
        return False
    mac = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, header_sig)


def trigger_sync(agent_id: str) -> tuple[int, str]:
    url = f"{LETTA_BASE_URL.rstrip('/')}/v1/agents/{agent_id}/memory/sync-from-git"
    req = urllib.request.Request(
        url,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")[:500]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")[:500]
    except urllib.error.URLError as e:
        return 0, f"URLError: {e}"


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        log.info("%s - %s", self.address_string(), format % args)

    def _respond(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "ok", "letta_base_url": LETTA_BASE_URL})
        else:
            self._respond(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/webhook":
            self._respond(404, {"error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length > 0 else b""

        sig = self.headers.get("X-Gitea-Signature", "")
        if not verify_signature(body, sig):
            log.warning("rejected: invalid HMAC signature")
            self._respond(401, {"error": "invalid_signature"})
            return

        event = self.headers.get("X-Gitea-Event", "")
        if event != "push":
            log.info("ignored event=%s", event)
            self._respond(200, {"status": "ignored", "reason": f"event={event}"})
            return

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._respond(400, {"error": "invalid_json"})
            return

        ref = payload.get("ref", "")
        branch = ref.removeprefix("refs/heads/")
        if branch not in ALLOWED_BRANCHES:
            log.info("ignored branch=%s", branch)
            self._respond(200, {"status": "ignored", "reason": f"branch={branch}"})
            return

        repo = payload.get("repository", {})
        owner = repo.get("owner", {}).get("username") or repo.get("owner", {}).get("login")
        name = repo.get("name", "")
        if owner != ALLOWED_ORG:
            log.info("ignored owner=%s (allowed=%s)", owner, ALLOWED_ORG)
            self._respond(200, {"status": "ignored", "reason": f"owner={owner}"})
            return

        if not AGENT_ID_PATTERN.match(name):
            log.warning("rejected repo name not agent-shaped: %s", name)
            self._respond(400, {"error": "bad_repo_name", "name": name})
            return

        agent_id = name
        commits = payload.get("commits", []) or []
        log.info("sync agent=%s branch=%s commits=%d", agent_id, branch, len(commits))

        code, detail = trigger_sync(agent_id)
        if 200 <= code < 300:
            log.info("sync ok agent=%s code=%d", agent_id, code)
            self._respond(200, {"status": "ok", "agent_id": agent_id, "letta_status": code})
        else:
            log.error("sync failed agent=%s code=%d detail=%s", agent_id, code, detail[:200])
            self._respond(502, {"status": "error", "agent_id": agent_id, "letta_status": code, "detail": detail[:200]})


def main():
    log.info("starting on :%d  letta=%s  org=%s  branches=%s  hmac=%s",
             PORT, LETTA_BASE_URL, ALLOWED_ORG, sorted(ALLOWED_BRANCHES),
             "configured" if WEBHOOK_SECRET else "DISABLED (no secret)")
    httpd = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
