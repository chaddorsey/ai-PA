#!/usr/bin/env python3
"""
mine-canonical-bodies.py — Phase D first-pass: fill body sections from
empirical signal.

For each canonical person file:
  1. Active projects: derive [[link]]s from top_shared_channels by matching
     project-shape patterns (#proposal-*, #fnd-*, #pearls, #clue-*, etc.)
  2. Recent interaction context: if a Slack DM exists, fetch last 90 days,
     summarize via LiteLLM into 2-3 sentences. Skip if no recent DM activity.

Idempotent: only patches the two named body sections. User-edited sections
(Bio, Relationship to Chad, Communication preferences) untouched.

Usage:
    python3 scripts/mine-canonical-bodies.py             # dry-run
    python3 scripts/mine-canonical-bodies.py --commit
"""
import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


CHAD_USER_ID = "U02V91KU8"
ENV_PATH = "/Volumes/main-drive/ai-PA/.env"
GITEA_HOST = "http://127.0.0.1:3030"
CANONICAL_REPO = "agents/agents-canonical"


def env(name):
    return os.popen(
        f"grep -E '^{name}=' {ENV_PATH} | head -1 | cut -d= -f2- | tr -d '\"'"
    ).read().strip()


SLACK = env("SLACK_MCP_XOXP_TOKEN")
GITEA_TOKEN = env("GITEA_MEMFS_TOKEN")
LITELLM_KEY = env("LITELLM_MASTER_KEY")
LITELLM_BASE = "http://localhost:4000/v1"
LITELLM_MODEL = "gpt-4.1-mini"


# Channel-name patterns suggesting active projects
PROJECT_PATTERNS = [
    re.compile(r"^proposal-", re.IGNORECASE),
    re.compile(r"^fnd-.*-proposal", re.IGNORECASE),
    re.compile(r"^fdn-.*-(proposal|rfi)", re.IGNORECASE),
    re.compile(r"^cer-future", re.IGNORECASE),
    re.compile(r"^pearls$", re.IGNORECASE),
    re.compile(r"^clue-", re.IGNORECASE),
    re.compile(r"^codap", re.IGNORECASE),
    re.compile(r"^seismic", re.IGNORECASE),
    re.compile(r"^itest-", re.IGNORECASE),
    re.compile(r"^building-models", re.IGNORECASE),
    re.compile(r"^sea-\d", re.IGNORECASE),
    re.compile(r"^drk12-", re.IGNORECASE),
    re.compile(r"^esaaf-", re.IGNORECASE),
    re.compile(r"^pisa$", re.IGNORECASE),
    re.compile(r"^moda-", re.IGNORECASE),
    re.compile(r"^bds-", re.IGNORECASE),
    re.compile(r"^pc2-", re.IGNORECASE),
    re.compile(r"^geniconnect", re.IGNORECASE),
    re.compile(r"^mapping-time", re.IGNORECASE),
    re.compile(r"^cisco$", re.IGNORECASE),
    re.compile(r"^technexus", re.IGNORECASE),
    re.compile(r"^ilkmaar", re.IGNORECASE),
]


def slack(method, params=None, post=False):
    qs = "?" + urllib.parse.urlencode(params) if params and not post else ""
    url = f"https://slack.com/api/{method}{qs}"
    if post:
        data = urllib.parse.urlencode(params or {}).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Authorization": f"Bearer {SLACK}",
                     "Content-Type": "application/x-www-form-urlencoded"},
        )
    else:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {SLACK}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read())
            if d.get("error") == "ratelimited":
                time.sleep(1 + attempt)
                continue
            return d
        except Exception:
            time.sleep(1 + attempt)
    return {"ok": False}


def list_canonical_people():
    out = []
    for domain in ("work", "work-alumni", "board", "board-alumni",
                   "family", "personal", "external", "services"):
        url = f"{GITEA_HOST}/api/v1/repos/{CANONICAL_REPO}/contents/reference/people/{domain}"
        req = urllib.request.Request(url, headers={"Authorization": f"token {GITEA_TOKEN}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                listing = json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        for entry in listing:
            if entry.get("type") == "file" and entry.get("name", "").endswith(".md"):
                out.append(entry["path"])
    return out


def read_file(path):
    url = f"{GITEA_HOST}/api/v1/repos/{CANONICAL_REPO}/contents/{path}?ref=main"
    req = urllib.request.Request(url, headers={"Authorization": f"token {GITEA_TOKEN}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.loads(r.read())
    return d["sha"], base64.b64decode(d["content"]).decode()


def write_file(path, content, sha, msg):
    body = {
        "branch": "main",
        "content": base64.b64encode(content.encode()).decode(),
        "message": msg, "sha": sha,
    }
    req = urllib.request.Request(
        f"{GITEA_HOST}/api/v1/repos/{CANONICAL_REPO}/contents/{path}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"token {GITEA_TOKEN}", "Content-Type": "application/json"},
        method="PUT",
    )
    urllib.request.urlopen(req, timeout=20)


def parse_person(content):
    name_m = re.search(r"^# (.+)$", content, re.MULTILINE)
    slack_m = re.search(r"^slack:\s*\n(?:\s{2,}\S+:.*\n)*", content, re.MULTILINE)
    slack_uid = None
    if slack_m:
        sm = re.search(r"^\s+user_id:\s*(\S+)\s*$", slack_m.group(0), re.MULTILINE)
        slack_uid = sm.group(1) if sm else None
    # interaction_signal top_shared_channels
    chans = []
    chan_m = re.search(r"^\s+top_shared_channels:\s*\[(.*)\]\s*$", content, re.MULTILINE)
    if chan_m:
        chans = [c.strip().strip('"').strip("'").lstrip("#") for c in chan_m.group(1).split(",")]
    return {
        "name": name_m.group(1).strip() if name_m else None,
        "slack_user_id": slack_uid,
        "top_channels": chans,
    }


def derive_project_links(channels):
    """Map channel names to project [[link]]s where they match project patterns."""
    projects = []
    for c in channels:
        for pat in PROJECT_PATTERNS:
            if pat.match(c):
                projects.append(c)
                break
    return projects


def open_dm(slack_uid):
    """Get/open the DM channel ID for a user."""
    d = slack("conversations.open", {"users": slack_uid}, post=True)
    if d.get("ok"):
        return d.get("channel", {}).get("id")
    return None


def fetch_dm_history(channel_id, days=90):
    """Last N days of messages in a DM."""
    oldest = (datetime.now() - timedelta(days=days)).timestamp()
    d = slack("conversations.history", {"channel": channel_id, "oldest": str(oldest), "limit": "100"})
    if not d.get("ok"):
        return []
    return d.get("messages", []) or []


def llm_summarize(person_name, messages):
    """Use LiteLLM to summarize a DM history into 2-3 sentences."""
    if not LITELLM_KEY or not messages:
        return None
    transcript_lines = []
    for m in reversed(messages[-50:]):  # oldest first, last 50
        if m.get("subtype") in ("channel_join", "channel_leave"):
            continue
        sender = "Chad" if m.get("user") == CHAD_USER_ID else person_name
        text = (m.get("text") or "").strip().replace("\n", " ")
        if not text:
            continue
        transcript_lines.append(f"{sender}: {text[:300]}")
    if not transcript_lines:
        return None
    transcript = "\n".join(transcript_lines)
    prompt = (
        f"You are summarizing a Slack DM history between Chad and {person_name} "
        f"from the last 90 days. Write 2-3 plain sentences capturing: "
        f"(1) what topics they discuss, (2) any commitments or open items, "
        f"(3) overall communication frequency/cadence. Plain prose, no bullets, "
        f"no caveats. If activity is light, say so briefly.\n\n"
        f"Transcript:\n{transcript}"
    )
    body = json.dumps({
        "model": LITELLM_MODEL, "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        f"{LITELLM_BASE}/chat/completions", data=body, method="POST",
        headers={"Authorization": f"Bearer {LITELLM_KEY}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        return (d.get("choices", [{}])[0].get("message") or {}).get("content", "").strip()
    except Exception as e:
        return f"(summarization failed: {str(e)[:80]})"


def patch_section(content, section_name, new_body):
    """Replace the content under a `## <Section name>` heading until the next `## ` or EOF."""
    pat = re.compile(
        r"(^## " + re.escape(section_name) + r"\s*\n)(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    return pat.sub(lambda m: m.group(1) + "\n" + new_body.strip() + "\n\n", content, count=1)


def bump_metadata(content, by="claude-body-mining"):
    now = datetime.now(tz=timezone.utc).isoformat()
    content = re.sub(r"^updated_by:.*$", f"updated_by: {by}", content, count=1, flags=re.MULTILINE)
    content = re.sub(r"^updated_at:.*$", f"updated_at: {now}", content, count=1, flags=re.MULTILINE)
    return content


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--commit", action="store_true")
    args = p.parse_args()
    if args.commit:
        args.dry_run = False

    files = list_canonical_people()
    print(f"Scanning {len(files)} canonical person files...\n")

    updates = []
    skipped_no_signal = 0
    for path in files:
        try:
            sha, content = read_file(path)
        except Exception as e:
            print(f"  ✗ {path}: read fail: {e}")
            continue
        info = parse_person(content)
        if not info.get("name"):
            continue

        new_content = content
        changed = False

        # Section 1: Active projects from shared-channel patterns
        proj_channels = derive_project_links(info["top_channels"])
        if proj_channels:
            link_lines = [
                f"- [[reference/projects/{c}]] — *(scaffolding pending — channel `#{c}`)*"
                for c in proj_channels[:5]
            ]
            new_content = patch_section(new_content, "Active projects",
                                         "\n".join(link_lines))
            changed = True

        # Section 2: Recent interaction context from Slack DM
        if info.get("slack_user_id"):
            dm_id = open_dm(info["slack_user_id"])
            if dm_id:
                msgs = fetch_dm_history(dm_id, days=90)
                meaningful = [m for m in msgs if m.get("text")]
                if meaningful:
                    summary = llm_summarize(info["name"], msgs)
                    if summary and not summary.startswith("("):
                        # Append source attribution
                        timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
                        body = f"{summary}\n\n*(Slack DM, last 90 days as of {timestamp}; refreshed periodically.)*"
                        new_content = patch_section(new_content, "Recent interaction context", body)
                        changed = True

        if changed:
            new_content = bump_metadata(new_content)
            updates.append((path, sha, new_content, info["name"]))
            print(f"  ★ {path:60s} ({info['name']})  channels={len(proj_channels)} dm={'y' if info.get('slack_user_id') else 'n'}")
        else:
            skipped_no_signal += 1

    print(f"\nUpdates: {len(updates)}, skipped (no signal): {skipped_no_signal}")

    if args.dry_run:
        return 0

    print("\nCommitting...")
    for path, sha, content, name in updates:
        try:
            write_file(path, content, sha,
                       f"reference: {path.split('/')[-1]} body mining (Phase D — projects + DM summary)")
        except Exception as e:
            print(f"  ✗ {path}: {e}")
    print(f"  done — {len(updates)} files updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
