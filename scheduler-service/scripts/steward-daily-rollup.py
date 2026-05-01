#!/usr/local/bin/python3
"""
steward-daily-rollup.py — Steward MVP duty #1 (deterministic).

Aggregates pipeline-health signals from agents-canonical/signals/{today}/
and signals/{yesterday}/, writes signals/{today}/steward-daily-rollup.md.

Designed to run as a scheduler-service `script` action (no Letta involved).
After writing the rollup, posts a one-line summary to the steward agent's
conversation so it has the context for any later questions.

Idempotent: re-running on the same day overwrites the rollup file.

Exit codes:
  0 = success (rollup written)
  1 = transient failure (network, etc.)
  2 = config error
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


GITEA = os.environ.get("GITEA_BASE_URL", "http://gitea:3000")
LETTA = os.environ.get("LETTA_BASE_URL", "http://letta:8283")
STEWARD_AGENT = "agent-6349140d-a7df-4df2-9937-87ade49e8783"
REPO = "agents/agents-canonical"
ET = ZoneInfo("America/New_York")
ENV_PATH = "/workspace/.env"

# Agents we expect to see pipeline-health from
EXPECTED_AGENTS = [
    "pulse-monitor",
    "calendar-agent",
    "tasks-agent",
    "mc",
    "daily-schedule-agent",
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
    """Idempotent upsert: PUT if exists, POST if new."""
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


def parse_frontmatter(text):
    if not text or not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out = {}
    for line in text[3:end].strip().splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def list_signals_for_date(date_str):
    """Return list of (filename, frontmatter, source-agent) for pipeline-health files in signals/{date_str}/."""
    listing = gitea_get(f"contents/signals/{date_str}?ref=main")
    if not isinstance(listing, list):
        return []
    out = []
    for entry in listing:
        name = entry.get("name", "")
        if not name.endswith("-pipeline-health.md"):
            continue
        # Source = leading part before -pipeline-health.md
        source = name[: -len("-pipeline-health.md")]
        body = gitea_raw(f"signals/{date_str}/{name}")
        fm = parse_frontmatter(body or "")
        out.append((name, fm, source))
    return out


def post_to_steward(summary):
    """Best-effort: drop a memory message into steward agent. Don't fail the rollup if this fails."""
    try:
        body = {"messages": [{"role": "user", "content": f"Daily rollup posted: {summary}"}]}
        req = urllib.request.Request(
            f"{LETTA}/v1/agents/{STEWARD_AGENT}/messages/async",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
        return True
    except Exception as e:
        sys.stderr.write(f"warn: steward notify failed: {e}\n")
        return False


def main():
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(ET)
    today_str = now_et.strftime("%Y-%m-%d")
    yesterday_str = (now_et - timedelta(days=1)).strftime("%Y-%m-%d")

    # Aggregate
    signals_today = list_signals_for_date(today_str)
    signals_yest = list_signals_for_date(yesterday_str)

    # Most-recent per source within last ~36h: prefer today's, then yesterday's
    by_source = {}
    for name, fm, src in signals_today:
        by_source[src] = (name, fm, today_str)
    for name, fm, src in signals_yest:
        if src not in by_source:
            by_source[src] = (name, fm, yesterday_str)

    # Build per-agent rows
    rows = []
    counts = {"routine": 0, "elevated": 0, "urgent": 0, "stale": 0}
    for agent in EXPECTED_AGENTS:
        if agent in by_source:
            name, fm, date = by_source[agent]
            level = fm.get("attention_level", "routine")
            desc = fm.get("description", "(no description)")
            rows.append((agent, level, f"{desc} (signals/{date}/{name})"))
            counts[level] = counts.get(level, 0) + 1
        else:
            rows.append((agent, "stale", "no pipeline-health in last 36h"))
            counts["stale"] += 1

    # Detect unexpected emitters
    extras = sorted(set(by_source) - set(EXPECTED_AGENTS))
    for agent in extras:
        name, fm, date = by_source[agent]
        level = fm.get("attention_level", "routine")
        desc = fm.get("description", "(no description)")
        rows.append((agent, level, f"{desc} (signals/{date}/{name})"))
        counts[level] = counts.get(level, 0) + 1

    # Top-level attention
    if counts.get("urgent", 0) > 0 or counts["stale"] >= 2:
        top_level = "urgent"
    elif counts.get("elevated", 0) > 0 or counts["stale"] >= 1:
        top_level = "elevated"
    else:
        top_level = "routine"

    # Render rollup
    composed = now_utc.isoformat()
    lines = [
        "---",
        "description: Steward daily rollup of pipeline-health across worker agents",
        "source: steward",
        f"attention_level: {top_level}",
        "mentioned_entities: []",
        f"composed_at: {composed}",
        f"date: {today_str}",
        "---",
        "",
        f"# Daily rollup — {today_str}",
        "",
        "## Per-agent status",
    ]
    for agent, level, ctx in rows:
        lines.append(f"- **{agent}** — {level} — {ctx}")

    urgent_items = [r for r in rows if r[1] == "urgent"]
    if urgent_items:
        lines += ["", "## Urgent items"]
        for agent, level, ctx in urgent_items:
            lines.append(f"- {agent}: {ctx}")

    lines += [
        "",
        "## Counts",
        f"- routine: {counts['routine']}",
        f"- elevated: {counts['elevated']}",
        f"- urgent: {counts['urgent']}",
        f"- stale: {counts['stale']}",
        "",
    ]

    rollup = "\n".join(lines)
    target = f"signals/{today_str}/steward-daily-rollup.md"
    gitea_put(target, rollup, f"signal: {target} (steward daily rollup)")

    summary = (
        f"{counts['routine']} routine, {counts['elevated']} elevated, "
        f"{counts['urgent']} urgent, {counts['stale']} stale — "
        f"signals/{today_str}/steward-daily-rollup.md"
    )
    print(summary)
    post_to_steward(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
