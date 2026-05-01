#!/usr/local/bin/python3
"""
signals-heartbeat.py — produce digest/recent_signals.md in canonical.

Rolls up the last 36-48 hours of mention-relevant signals from
agents-canonical/signals/{date}/ into a single chronological digest
that MC's find_from_person_protocol Step 1 can read in one HTTP call.

Today's mentions-active sits in signals/{today}/slack-watch-mentions-active.md.
Yesterday's likewise. The digest concatenates them (newest first), with
a light header so MC can skip to "today" or "yesterday".

MVP scope: just slack-watch mentions. Future expansion (deferred):
  - analytics-snapshot headline metrics
  - slack-vibe channel-level summaries
  - calendar-derived "X had a meeting with Chad today" signals
  - anything else that surfaces "person → Chad interaction in last 48h"

Cadence (suggested via cron):
  - hourly during workdays: */60 8-18 * * 1-5 America/New_York
  - 3x off-hours daily: 0 6,21 * * * + 0 13 * * 0,6 (weekend midday)
  Idempotent overwrite.

Designed to run as scheduler-service `script` action.
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


GITEA = os.environ.get("GITEA_BASE_URL", "http://gitea:3000")
REPO = "agents/agents-canonical"
ET = ZoneInfo("America/New_York")
ENV_PATH = "/workspace/.env"

# Signal kinds to roll up. Ordered by usefulness for find-from-person lookup.
ROLLUP_KINDS = [
    "slack-watch-mentions-active.md",
]


def read_env(name):
    if name in os.environ:
        return os.environ[name]
    try:
        with open(ENV_PATH) as f:
            for line in f:
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


GITEA_TOKEN = read_env("GITEA_MEMFS_TOKEN")
if not GITEA_TOKEN:
    sys.stderr.write("FATAL: no GITEA_MEMFS_TOKEN\n")
    sys.exit(2)


def gitea_get(path):
    url = f"{GITEA}/api/v1/repos/{REPO}/{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"token {GITEA_TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def gitea_raw(path):
    url = f"{GITEA}/api/v1/repos/{REPO}/raw/main/{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"token {GITEA_TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def gitea_put(path_rel, content, msg):
    url = f"{GITEA}/api/v1/repos/{REPO}/contents/{path_rel}"
    existing = gitea_get(f"contents/{path_rel}?ref=main")
    sha = existing.get("sha") if existing else None
    body = {
        "branch": "main",
        "content": base64.b64encode(content.encode()).decode(),
        "message": msg,
    }
    method = "PUT" if sha else "POST"
    if sha:
        body["sha"] = sha
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"token {GITEA_TOKEN}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def collect_for_date(date_str):
    """Return list of (kind, body) for date_str's rollup-eligible signals."""
    out = []
    for kind in ROLLUP_KINDS:
        body = gitea_raw(f"signals/{date_str}/{kind}")
        if body:
            out.append((kind, body))
    return out


def strip_frontmatter(body):
    """Drop the leading --- ... --- block; return remaining content."""
    if not body or not body.startswith("---"):
        return body
    end = body.find("\n---", 3)
    if end == -1:
        return body
    return body[end + 4 :].lstrip("\n")


def main():
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(ET)
    today = now_et.strftime("%Y-%m-%d")
    yesterday = (now_et - timedelta(days=1)).strftime("%Y-%m-%d")

    today_signals = collect_for_date(today)
    yesterday_signals = collect_for_date(yesterday)

    total_sources = len(today_signals) + len(yesterday_signals)

    lines = [
        "---",
        "description: Rolling digest of recent person→Chad interactions (last ~48h)",
        "source: signals-heartbeat",
        "attention_level: routine",
        f"composed_at: {now_utc.isoformat()}",
        f"date: {today}",
        f"window_start: {yesterday}",
        f"window_end: {today}",
        f"sources_aggregated: {total_sources}",
        "---",
        "",
        f"# Recent signals digest — {today} {now_et.strftime('%H:%M %Z')}",
        "",
        "Use this for the first step of find-from-person lookups. Each entry includes",
        "a permalink. If the digest is stale or doesn't cover the person you're",
        "looking for, fall through to the next protocol step (Slack DM history, etc.).",
        "",
    ]

    if today_signals:
        lines += [f"## Today — {today}", ""]
        for kind, body in today_signals:
            lines.append(f"### Source: signals/{today}/{kind}")
            lines.append("")
            lines.append(strip_frontmatter(body).rstrip())
            lines.append("")
    else:
        lines += [
            f"## Today — {today}",
            "",
            "_(no slack-watch mention signals emitted yet today)_",
            "",
        ]

    if yesterday_signals:
        lines += [f"## Yesterday — {yesterday}", ""]
        for kind, body in yesterday_signals:
            lines.append(f"### Source: signals/{yesterday}/{kind}")
            lines.append("")
            lines.append(strip_frontmatter(body).rstrip())
            lines.append("")
    else:
        lines += [
            f"## Yesterday — {yesterday}",
            "",
            "_(no slack-watch mention signals from yesterday)_",
            "",
        ]

    digest = "\n".join(lines)
    gitea_put(
        "digest/recent_signals.md",
        digest,
        f"signal: digest/recent_signals.md (heartbeat refresh)",
    )

    print(
        f"digest: composed {len(digest)} chars from {total_sources} source signals "
        f"({len(today_signals)} today, {len(yesterday_signals)} yesterday)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
