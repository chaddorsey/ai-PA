#!/usr/bin/env python3
"""
Backfill pulse-monitor-slack-vibe.md signals for historical weekdays.

For each missing date in the requested range:
  1. Send pulse-monitor an agent_message asking it to compose a vibe check
     for that specific historical date.
  2. The agent uses run_slack conversations.history per top channel to
     pull message context for the target date, summarizes per-channel,
     and emits a Layer-5 signal via emit_canonical_signal with the
     historical date.
  3. Wait for the run to complete (poll runs API) before sending next.

Slack message history is unbounded — historical days work fine.
The bottleneck is agent wall-clock time, not data availability.

Usage:
    python3 scripts/backfill-slack-vibe-checks.py --start 2026-04-14 --end 2026-04-28
    python3 scripts/backfill-slack-vibe-checks.py --since-days 14 --dry-run
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta

LETTA_URL = "http://localhost:8283"
GITEA_URL = "http://localhost:3030"
PULSE_AGENT_ID = "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"
SLACK_VIBE_PATH_TMPL = (
    f"{GITEA_URL}/api/v1/repos/agents/agents-canonical/contents/"
    "signals/{date}/pulse-monitor-slack-vibe.md"
)


def gitea_token():
    return os.popen(
        "grep -E '^GITEA_(MEMFS_)?TOKEN' /Volumes/main-drive/ai-PA/.env | head -1 | cut -d= -f2- | tr -d '\"'"
    ).read().strip()


def has_vibe_signal(d):
    url = SLACK_VIBE_PATH_TMPL.format(date=d.isoformat())
    req = urllib.request.Request(url, headers={"Authorization": f"token {gitea_token()}"})
    try:
        urllib.request.urlopen(req, timeout=5)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def is_weekday(d):
    return d.weekday() < 5


def send_compose_request(target_date):
    prompt = f"""[BACKFILL] Compose Slack vibe check for {target_date.isoformat()} ({target_date.strftime('%A')}).

This is a backfill pass — the date is in the past, not yesterday. Use the same methodology as the daily vibe-check cron, but parameterized to the historical date:

1. Identify the top monitoring channels per system/slack_channels_list.md.
2. For each top channel, fetch messages from {target_date.isoformat()} 00:00 ET through {target_date.isoformat()} 23:59 ET via run_slack conversations.history (use oldest/latest as Unix timestamps for that ET day).
3. For each channel, write a 2-4 sentence narrative summary capturing: notable threads, who was active, anything that looks decision-relevant, anything that looks like an unresolved question.
4. Compose a combined markdown body with one section per channel ('### #<channel-name>' headers) plus a top-line "Daily Slack Vibe Check for {target_date.isoformat()}" header.
5. Determine attention_level: 'elevated' if any channel showed notable threads involving Sue Brau, Leslie Bondaryk, Kiley Brown, Helen Quinn, Bronwyn Bevan, or any @nsf.gov participant; or if 'letter request', 'advisory', 'deadline' came up. Otherwise 'routine'.
6. mentioned_entities: comma-separated list of channel names with '#' prefix.
7. Call: emit_canonical_signal(slug='slack-vibe', source='pulse-monitor', body=<combined summary>, description='Daily Slack vibe check for {target_date.isoformat()} ({target_date.strftime('%A')}) — backfilled', attention_level=<computed>, mentioned_entities=<list>, date='{target_date.isoformat()}')

If a channel has zero messages for the target date, note that briefly in its section. If ALL top channels are empty for that date, emit a routine signal with body explaining no activity was captured.

Do NOT also write to system/daily_vibe_check_<DATE>.md for backfill — only emit the canonical signal. Reply briefly: 'Vibe check for {target_date.isoformat()} composed: <N channels summarized>, attention=<level>'."""

    body = json.dumps({"messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(
        f"{LETTA_URL}/v1/agents/{PULSE_AGENT_ID}/messages",
        data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        r = urllib.request.urlopen(req, timeout=900)  # up to 15 min
        return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)[:300]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=date.fromisoformat)
    p.add_argument("--end", type=date.fromisoformat)
    p.add_argument("--since-days", type=int)
    p.add_argument("--include-weekends", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--include-existing", action="store_true",
                   help="Re-emit even if signal already exists")
    args = p.parse_args()

    today = date.today()
    if args.since_days:
        start = today - timedelta(days=args.since_days)
        end = today
    else:
        start = args.start or (today - timedelta(days=14))
        end = args.end or today

    todo = []
    cur = start
    while cur <= end:
        if not (args.include_weekends or is_weekday(cur)):
            cur += timedelta(days=1); continue
        if not args.include_existing and has_vibe_signal(cur):
            print(f"  ⏭  {cur} ({cur.strftime('%a')}) — signal exists", flush=True)
            cur += timedelta(days=1); continue
        todo.append(cur)
        cur += timedelta(days=1)

    print(f"\nbackfill plan: {len(todo)} dates from {start} to {end}", flush=True)
    for d in todo:
        print(f"  - {d.isoformat()} ({d.strftime('%a')})", flush=True)

    if args.dry_run or not todo:
        return 0

    for i, d in enumerate(todo, 1):
        print(f"\n[{i}/{len(todo)}] composing vibe check for {d.isoformat()} ({d.strftime('%a')}) ...", flush=True)
        t0 = time.time()
        res = send_compose_request(d)
        elapsed = time.time() - t0
        if isinstance(res, dict) and res.get("error"):
            print(f"  ✗ error after {elapsed:.0f}s: {res['error']}", flush=True)
        else:
            # Check whether the signal got emitted
            time.sleep(2)
            ok = has_vibe_signal(d)
            print(f"  {'✓' if ok else '✗'} {elapsed:.0f}s — signal {'created' if ok else 'NOT FOUND in canonical'}", flush=True)
        # 10s pacing between dates so we don't pile up runs on the same agent
        time.sleep(10)

    print("\n=== vibe-check backfill complete ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
