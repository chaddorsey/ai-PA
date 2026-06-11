#!/usr/bin/env python3
"""Materialize a 'current' (date-less) canonical signal cell from the latest
dated source — so MC can read a stable path (like signals/current/schedule.md)
instead of guessing the data-lagged date.

Usage:
  materialize-current-signal.py analytics   # latest signals/<date>/analytics-morning.md -> signals/current/analytics-morning.md
  materialize-current-signal.py vibe        # latest pulse-memfs daily_vibe_check_<date>.md -> signals/current/slack-vibe.md

Env: GITEA_BASE_URL (default 127.0.0.1:3030), GITEA_MEMFS_TOKEN.
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("GITEA_BASE_URL", "http://127.0.0.1:3030").rstrip("/")
TOKEN = os.environ.get("GITEA_MEMFS_TOKEN", "")
REPO = f"{BASE}/api/v1/repos/agents/agents-canonical"
PULSE_MEMFS = os.path.expanduser(
    "~/.letta/lc-local-backend/memfs/"
    "agent-local-d48b128a-b3a8-4930-a27f-b4127c96fe3a/memory/system"
)


def _req(method, path, body=None):
    url = f"{REPO}/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"token {TOKEN}",
                                          "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=20)


def _raw(path):
    """Fetch raw file content (bytes) or None."""
    try:
        return _req("GET", f"raw/{path}").read()
    except urllib.error.HTTPError:
        return None


def _latest_dated_signal(filename):
    """Return (date, content_bytes) for the most recent signals/<date>/<filename>."""
    listing = json.load(_req("GET", "contents/signals"))
    dates = sorted(e["name"] for e in listing
                   if e["type"] == "dir" and re.match(r"^\d{4}-\d{2}-\d{2}$", e["name"]))
    for d in reversed(dates):
        c = _raw(f"signals/{d}/{filename}")
        if c:
            return d, c
    return None, None


def _latest_pulse_vibe():
    """Return (date, content_bytes) for the newest pulse-memfs daily_vibe_check."""
    files = sorted(f for f in os.listdir(PULSE_MEMFS)
                   if re.match(r"^daily_vibe_check_\d{4}-\d{2}-\d{2}\.md$", f))
    if not files:
        return None, None
    newest = files[-1]
    d = newest[len("daily_vibe_check_"):-len(".md")]
    with open(os.path.join(PULSE_MEMFS, newest), "rb") as fh:
        return d, fh.read()


def _put_current(target_name, content_bytes, src_date):
    path = f"signals/current/{target_name}"
    # prepend a provenance line so readers know the source date
    header = f"<!-- materialized from signals/{src_date}/ (data date {src_date}) -->\n".encode()
    payload = header + content_bytes
    # get existing sha (update) or create
    sha = None
    try:
        cur = json.load(_req("GET", f"contents/{path}"))
        sha = cur.get("sha")
    except urllib.error.HTTPError:
        pass
    body = {"message": f"materialize current/{target_name} from {src_date}",
            "content": base64.b64encode(payload).decode(), "branch": "main"}
    if sha:
        body["sha"] = sha
    _req("PUT", f"contents/{path}", body)
    print(f"  materialized signals/{path.split('/')[-1]} <- {src_date} ({len(payload)} bytes)")


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    if which == "analytics":
        d, c = _latest_dated_signal("analytics-morning.md")
        if not c:
            print("  no analytics-morning.md found in canonical"); return 1
        _put_current("analytics-morning.md", c, d)
    elif which == "vibe":
        d, c = _latest_pulse_vibe()
        if not c:
            print("  no daily_vibe_check found in pulse memfs"); return 1
        _put_current("slack-vibe.md", c, d)
    else:
        print("usage: materialize-current-signal.py <analytics|vibe>"); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
