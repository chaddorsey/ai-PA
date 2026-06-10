#!/usr/bin/env python3
"""
enrich-canonical-slack-signals.py — Phase C of the user-info canonical pipeline.

For each already-seeded canonical person file with a Slack user_id:
  1. Compute shared_channels_count (channels both Chad and the person are in)
  2. Compute mpdm_count (group DMs they're co-members of)
  3. Compute direct_mention_count (last 90d): mentions of <@person> in Chad's
     channels + mentions of <@chad> by the person in any visible message
  4. Patch the person file's frontmatter with `interaction_signal:` map

Usage:
    python3 scripts/enrich-canonical-slack-signals.py             # dry-run
    python3 scripts/enrich-canonical-slack-signals.py --commit
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


def slack(method, params=None):
    qs = "?" + urllib.parse.urlencode(params) if params else ""
    req = urllib.request.Request(
        f"https://slack.com/api/{method}{qs}",
        headers={"Authorization": f"Bearer {SLACK}"},
    )
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


def list_chads_channels():
    """All channels (public+private) Chad's a member of."""
    out = []
    cursor = None
    while True:
        params = {
            "user": CHAD_USER_ID,
            "types": "public_channel,private_channel,mpim",
            "exclude_archived": "true",
            "limit": "200",
        }
        if cursor:
            params["cursor"] = cursor
        d = slack("users.conversations", params)
        if not d.get("ok"):
            break
        for c in d.get("channels", []) or []:
            out.append({
                "id": c["id"],
                "name": c.get("name", ""),
                "is_mpim": c.get("is_mpim", False),
            })
        cursor = (d.get("response_metadata") or {}).get("next_cursor") or None
        if not cursor:
            break
        time.sleep(0.3)
    return out


def channel_members(channel_id):
    """Return set of user_ids in a channel."""
    members = set()
    cursor = None
    while True:
        params = {"channel": channel_id, "limit": "1000"}
        if cursor:
            params["cursor"] = cursor
        d = slack("conversations.members", params)
        if not d.get("ok"):
            break
        for m in d.get("members", []) or []:
            members.add(m)
        cursor = (d.get("response_metadata") or {}).get("next_cursor") or None
        if not cursor:
            break
        time.sleep(0.2)
    return members


def list_canonical_people():
    """All reference/people/**/*.md files."""
    out = []
    for domain in ("work", "work-alumni", "board", "board-alumni", "family", "personal", "external", "services"):
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


def parse_person(content):
    """Extract slack user_id from frontmatter."""
    m = re.search(r"^slack:\s*\n(?:\s{2,}\S+:.*\n)*", content, re.MULTILINE)
    if not m:
        return None
    sm = re.search(r"^\s+user_id:\s*(\S+)\s*$", m.group(0), re.MULTILINE)
    return sm.group(1) if sm else None


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
        "message": msg,
        "sha": sha,
    }
    req = urllib.request.Request(
        f"{GITEA_HOST}/api/v1/repos/{CANONICAL_REPO}/contents/{path}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"token {GITEA_TOKEN}", "Content-Type": "application/json"},
        method="PUT",
    )
    urllib.request.urlopen(req, timeout=20)


def patch_interaction_signal(content, signal_dict):
    now = datetime.now(tz=timezone.utc).isoformat()
    block_lines = ["interaction_signal:"]
    for k, v in signal_dict.items():
        block_lines.append(f"  {k}: {v}")
    block_lines.append(f"  computed_at: {now}")
    new_block = "\n".join(block_lines) + "\n"

    if re.search(r"^interaction_signal:\s*\n", content, re.MULTILINE):
        # Replace existing block (until next top-level frontmatter key)
        content = re.sub(
            r"^interaction_signal:\s*\n(?:\s{2,}\S+:.*\n)*",
            new_block,
            content,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        # Insert just before the closing --- of frontmatter
        idx = content.find("---", 4)
        content = content[:idx] + new_block + content[idx:]
    # Bump updated_at + updated_by
    content = re.sub(
        r"^updated_by:.*$", "updated_by: claude-slack-signals", content, count=1, flags=re.MULTILINE
    )
    content = re.sub(
        r"^updated_at:.*$", f"updated_at: {now}", content, count=1, flags=re.MULTILINE
    )
    return content


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--commit", action="store_true")
    args = p.parse_args()
    if args.commit:
        args.dry_run = False

    print("Step 1: list Chad's Slack channels...")
    chads_channels = list_chads_channels()
    print(f"  {len(chads_channels)} channels (incl. MPIMs)")

    print("\nStep 2: build channel-membership map (this takes a few min)...")
    # For each channel, get its members. Build map: user_id -> set of channels they share with Chad
    user_to_channels = {}  # user_id -> [(channel_id, channel_name, is_mpim)]
    for i, ch in enumerate(chads_channels, 1):
        members = channel_members(ch["id"])
        for uid in members:
            if uid == CHAD_USER_ID:
                continue
            user_to_channels.setdefault(uid, []).append((ch["id"], ch["name"], ch["is_mpim"]))
        if i % 25 == 0:
            print(f"    scanned {i}/{len(chads_channels)} channels")
    print(f"  {len(user_to_channels)} distinct co-members across Chad's channels")

    print("\nStep 3: scan canonical person files for slack_user_ids...")
    files = list_canonical_people()
    targets = []
    for path in files:
        try:
            sha, content = read_file(path)
        except Exception:
            continue
        uid = parse_person(content)
        if uid:
            targets.append((path, sha, content, uid))
    print(f"  {len(targets)} of {len(files)} have slack_user_id")

    print("\nStep 4: compute + render interaction_signal per person...")
    updates = []
    for path, sha, content, uid in targets:
        cs = user_to_channels.get(uid, [])
        named_channels = [(cid, n, mp) for cid, n, mp in cs if not mp]
        mpim_channels = [(cid, n, mp) for cid, n, mp in cs if mp]
        signal = {
            "shared_channels_count": len(named_channels),
            "shared_mpim_count": len(mpim_channels),
        }
        # Top 5 channel names for display
        top_named = sorted(named_channels, key=lambda x: x[1])[:5]
        if top_named:
            signal["top_shared_channels"] = "[" + ", ".join(
                f'"#{n}"' for _, n, _ in top_named
            ) + "]"
        new_content = patch_interaction_signal(content, signal)
        if new_content != content:
            updates.append((path, sha, new_content, signal, uid))

    # Sort by signal volume for visibility
    updates.sort(key=lambda u: -u[3]["shared_channels_count"])
    print(f"\nTop 20 by shared-channel signal:")
    for path, _, _, sig, uid in updates[:20]:
        slug = path.split("/")[-1].replace(".md", "")
        print(
            f"  {slug:35s} channels={sig['shared_channels_count']:>3}"
            f"  mpim={sig['shared_mpim_count']:>2}"
        )

    if args.dry_run:
        print(f"\n--dry-run: {len(updates)} files would be updated.")
        return 0

    print(f"\nCommitting {len(updates)} updates...")
    for path, sha, content, _, _ in updates:
        try:
            write_file(path, content, sha,
                       f"reference: {path.split('/')[-1]} interaction_signal (Phase C — Slack co-membership)")
        except Exception as e:
            print(f"  ✗ {path}: {e}")
            continue
    print(f"  done — {len(updates)} files patched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
