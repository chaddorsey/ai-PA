#!/usr/bin/env python3
"""Delete stale failure-marker files from the abandoned lookahead:
   signals/<date>/mc-lookahead-<date>.md
   signals/<date>/mc-daily-briefing-lookahead-<date>.md
Idempotent. Use --dry-run to preview. Env: GITEA_BASE_URL, GITEA_MEMFS_TOKEN.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("GITEA_BASE_URL", "http://127.0.0.1:3030").rstrip("/")
TOKEN = os.environ["GITEA_MEMFS_TOKEN"]
REPO = f"{BASE}/api/v1/repos/agents/agents-canonical"
MARKER_RE = re.compile(r"^(mc-lookahead-|mc-daily-briefing-lookahead-)\d{4}-\d{2}-\d{2}\.md$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{REPO}/{path}", data=data, method=method,
                                 headers={"Authorization": f"token {TOKEN}",
                                          "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=20)


def main():
    dry = "--dry-run" in sys.argv
    dates = [e["name"] for e in json.load(_req("GET", "contents/signals"))
             if e["type"] == "dir" and DATE_RE.match(e["name"])]
    deleted = 0
    for d in dates:
        try:
            entries = json.load(_req("GET", f"contents/signals/{d}"))
        except urllib.error.HTTPError:
            continue
        for e in entries:
            if e["type"] == "file" and MARKER_RE.match(e["name"]):
                path = f"signals/{d}/{e['name']}"
                if dry:
                    print(f"  would delete {path}")
                else:
                    _req("DELETE", f"contents/{path}",
                         {"branch": "main", "sha": e["sha"],
                          "message": f"cleanup: remove stale lookahead marker {e['name']}"})
                    print(f"  deleted {path}")
                deleted += 1
    print(f"\n{'Would delete' if dry else 'Deleted'} {deleted} marker file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
