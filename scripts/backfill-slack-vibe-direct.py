#!/usr/bin/env python3
"""
Direct vibe-check backfill — bypasses the agent path entirely.

Pipeline per date:
  1. For each priority channel, fetch messages via Slack conversations.history
     bounded by the target ET day (00:00 → 23:59 ET).
  2. Send each channel's message bundle to Claude API for summarization.
  3. Combine per-channel summaries into the day's vibe-check markdown.
  4. Compute attention_level from priority-name / keyword matches.
  5. Emit Layer-5 signal at agents-canonical/signals/<DATE>/pulse-monitor-slack-vibe.md
     via Gitea contents API (same write contract as emit_canonical_signal).

Usage:
    python3 scripts/backfill-slack-vibe-direct.py --start 2026-04-14 --end 2026-04-28
    python3 scripts/backfill-slack-vibe-direct.py --date 2026-04-26 --dry-run
"""
import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, time as dtime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore

# --- Config ---

# Top 12 channels by recent activity (queried 2026-04-28 via users.conversations
# + conversations.history 14d window). Project + proposal channels dominate
# substantive content; refresh this list periodically.
DEFAULT_PRIORITY_CHANNELS = [
    ("proposal-dev", "CBY41RGH3"),
    ("clue-dev", "CCHKYUW3S"),
    ("pearls", "C0AM7JXGENS"),
    ("fdn-cisco-proposal-2", "C0APM4GV3AL"),
    ("proposal-plans-n-prep", "G3Q43E3CZ"),
    ("dev", "C0303QUNU"),
    ("business-dev-strategy", "C0A7BHGPJ0P"),
    ("mapping-time", "C0A7NPWDGG3"),
    ("technexus", "C0ATYBH1DJL"),
    ("fnd-gates-hackathon-proposal", "C0AS5FK4L87"),
    ("codap-v3", "C035J6RDAK0"),
    ("drk12-island", "C07S1AX2XD1"),
    ("dev-planning", "CJFQ8FXU7"),
    ("general-work-related", "C0ACYDRPW"),
]

PRIORITY_NAME_PATTERNS = [
    "sue brau", "leslie bondaryk", "kiley brown",
    "helen quinn", "bronwyn bevan",
]
PRIORITY_KEYWORDS = [
    "letter request", "advisory", "deadline", "urgent", "asap",
]

ENV_PATH = "/Volumes/main-drive/ai-PA/.env"
GITEA_HOST = "http://127.0.0.1:3030"
CANONICAL_REPO = "agents/agents-canonical"


def env(name):
    return os.popen(
        f"grep -E '^{name}=' {ENV_PATH} | head -1 | cut -d= -f2- | tr -d '\"'"
    ).read().strip()


SLACK_USER_TOKEN = env("SLACK_MCP_XOXP_TOKEN") or env("SLACK_USER_TOKEN")
LITELLM_KEY = env("LITELLM_MASTER_KEY")
LITELLM_BASE = "http://localhost:4000/v1"
LITELLM_MODEL = "gpt-4.1-mini"
GITEA_TOKEN = env("GITEA_MEMFS_TOKEN") or env("GITEA_TOKEN")


# --- Slack ---


def slack_call(method, params, retries=3):
    url = f"https://slack.com/api/{method}"
    data = urllib.parse.urlencode(params).encode() if params else None
    headers = {"Authorization": f"Bearer {SLACK_USER_TOKEN}"}
    if data:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read())
                if not d.get("ok"):
                    err = d.get("error", "unknown")
                    if err == "ratelimited":
                        retry_after = int(r.headers.get("Retry-After", "1"))
                        time.sleep(retry_after + 1)
                        continue
                    return d
                return d
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    return {"ok": False, "error": f"giveup: {last_err}"}


def fetch_day_messages(channel_id, day_d):
    """Fetch messages from a channel for the ET-day window."""
    if ZoneInfo:
        tz = ZoneInfo("America/New_York")
        oldest_dt = datetime.combine(day_d, dtime(0, 0), tzinfo=tz)
        latest_dt = datetime.combine(day_d, dtime(23, 59, 59), tzinfo=tz)
    else:
        # crude UTC fallback
        oldest_dt = datetime.combine(day_d, dtime(4, 0))  # ET≈UTC-4 during DST
        latest_dt = datetime.combine(day_d + timedelta(days=1), dtime(3, 59, 59))

    oldest = oldest_dt.timestamp()
    latest = latest_dt.timestamp()

    msgs = []
    cursor = None
    while True:
        params = {
            "channel": channel_id,
            "oldest": str(oldest),
            "latest": str(latest),
            "inclusive": "true",
            "limit": "200",
        }
        if cursor:
            params["cursor"] = cursor
        d = slack_call("conversations.history", params)
        if not d.get("ok"):
            return msgs, d.get("error", "unknown")
        msgs.extend(d.get("messages", []))
        rm = d.get("response_metadata") or {}
        cursor = rm.get("next_cursor") or None
        if not cursor:
            break
        time.sleep(0.4)
    return msgs, None


# --- User name resolution (cached) ---

_user_cache = {}


def resolve_user(uid):
    if not uid:
        return ""
    if uid in _user_cache:
        return _user_cache[uid]
    d = slack_call("users.info", {"user": uid})
    name = uid
    if d.get("ok"):
        prof = d.get("user", {}).get("profile", {})
        name = (
            prof.get("display_name")
            or prof.get("real_name")
            or d.get("user", {}).get("name")
            or uid
        )
    _user_cache[uid] = name
    return name


# --- Claude summarization ---


def summarize_channel(channel_name, day_iso, messages):
    """Use Claude to write a 2-4 sentence vibe summary for a channel-day."""
    if not messages:
        return f"(no messages in #{channel_name} on {day_iso})"

    # Build a compact transcript
    lines = []
    for m in reversed(messages):  # oldest first
        if m.get("subtype") in ("channel_join", "channel_leave"):
            continue
        if m.get("bot_id") and not m.get("user"):
            continue
        sender = resolve_user(m.get("user", ""))
        text = (m.get("text") or "").strip().replace("\n", " ")
        if not text:
            continue
        if len(text) > 400:
            text = text[:400] + "…"
        lines.append(f"{sender}: {text}")

    if not lines:
        return f"(no substantive messages in #{channel_name} on {day_iso})"

    transcript = "\n".join(lines[-120:])  # cap volume

    prompt = (
        f"You are summarizing a single day of Slack messages from #{channel_name} "
        f"on {day_iso}.\n\nWrite a tight 2-4 sentence summary that captures: "
        f"(1) what topics were active, (2) any decisions or commitments made, "
        f"(3) any unresolved questions or surfaced issues, (4) who was active "
        f"if it's notable. Use plain prose, not bullets. Do NOT add greetings, "
        f"caveats, or restate the date. If activity is light/routine, say so "
        f"briefly.\n\nTranscript:\n{transcript}"
    )

    body = json.dumps({
        "model": LITELLM_MODEL,
        "max_tokens": 400,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        f"{LITELLM_BASE}/chat/completions",
        data=body, method="POST",
        headers={
            "Authorization": f"Bearer {LITELLM_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
            choices = d.get("choices") or []
            if not choices:
                return "(no choices returned)"
            text_out = (choices[0].get("message") or {}).get("content", "") or ""
            return text_out.strip() or "(empty summary returned)"
    except urllib.error.HTTPError as e:
        return f"(summarization failed: {e.code} {e.read().decode()[:120]})"
    except Exception as e:
        return f"(summarization failed: {str(e)[:120]})"


# --- Compose + emit ---


def compute_attention(per_channel):
    blob = " ".join(s.lower() for s in per_channel.values())
    if any(p in blob for p in PRIORITY_NAME_PATTERNS):
        return "elevated"
    if any(k in blob for k in PRIORITY_KEYWORDS):
        return "elevated"
    return "routine"


def emit_signal(date_iso, channel_summaries, mentioned_channels, attention):
    body_lines = [f"# Daily Slack Vibe Check for {date_iso}\n"]
    for ch_name in mentioned_channels:
        body_lines.append(f"## #{ch_name}")
        body_lines.append(channel_summaries.get(ch_name, "(no data)").strip())
        body_lines.append("")
    body_md = "\n".join(body_lines).strip() + "\n"

    fm_lines = [
        "---",
        f"description: Daily Slack vibe check for {date_iso} — backfilled (direct API)",
        "source: pulse-monitor",
        f"attention_level: {attention}",
        "mentioned_entities: ["
        + ", ".join(json.dumps("#" + c) for c in mentioned_channels)
        + "]",
        f"composed_at: {datetime.now(tz=timezone.utc).isoformat()}",
        f"date: {date_iso}",
        "backfill_method: direct-api-script",
        "---",
        "",
    ]
    full = "\n".join(fm_lines) + body_md

    path = f"signals/{date_iso}/pulse-monitor-slack-vibe.md"
    url = f"{GITEA_HOST}/api/v1/repos/{CANONICAL_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITEA_TOKEN}", "Content-Type": "application/json"}

    sha = None
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url + "?ref=main", headers=headers), timeout=10
        ) as r:
            sha = json.loads(r.read()).get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise

    payload = {
        "branch": "main",
        "content": base64.b64encode(full.encode()).decode("ascii"),
        "message": f"signals: pulse-monitor slack-vibe for {date_iso} (direct backfill)",
    }
    if sha:
        payload["sha"] = sha
    method = "PUT" if sha else "POST"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
        return d.get("content", {}).get("html_url", "")


# --- Main ---


def is_weekday(d):
    return d.weekday() < 5


import urllib.parse  # late import for slack_call


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=date.fromisoformat)
    p.add_argument("--end", type=date.fromisoformat)
    p.add_argument("--date", type=date.fromisoformat, help="Single date (overrides --start/--end)")
    p.add_argument("--include-weekends", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--channels", default="",
                   help="Comma-separated channel names. Empty=defaults.")
    p.add_argument("--include-existing", action="store_true",
                   help="Re-emit even if signal exists.")
    args = p.parse_args()

    if not SLACK_USER_TOKEN or not LITELLM_KEY or not GITEA_TOKEN:
        print(f"missing creds: SLACK={bool(SLACK_USER_TOKEN)} LITELLM={bool(LITELLM_KEY)} GITEA={bool(GITEA_TOKEN)}", flush=True)
        return 2

    if args.date:
        dates = [args.date]
    else:
        start = args.start or (date.today() - timedelta(days=14))
        end = args.end or (date.today() - timedelta(days=1))
        dates = []
        cur = start
        while cur <= end:
            if args.include_weekends or is_weekday(cur):
                dates.append(cur)
            cur += timedelta(days=1)

    # Resolve channel list
    if args.channels:
        # User passed names; we still need IDs from defaults map
        names = [n.strip().lstrip("#") for n in args.channels.split(",") if n.strip()]
        name_to_id = {n: cid for n, cid in DEFAULT_PRIORITY_CHANNELS}
        channels = [(n, name_to_id.get(n)) for n in names]
        missing = [n for n, cid in channels if not cid]
        if missing:
            print(f"channel IDs unknown for: {missing}. Add to DEFAULT_PRIORITY_CHANNELS.", flush=True)
            return 2
    else:
        channels = list(DEFAULT_PRIORITY_CHANNELS)

    print(f"channels: {[n for n,_ in channels]}", flush=True)
    print(f"dates: {len(dates)}  ({dates[0] if dates else None} → {dates[-1] if dates else None})", flush=True)

    if args.dry_run:
        return 0

    for i, day_d in enumerate(dates, 1):
        day_iso = day_d.isoformat()

        # Skip if signal exists and not overriding
        if not args.include_existing:
            url = f"{GITEA_HOST}/api/v1/repos/{CANONICAL_REPO}/contents/signals/{day_iso}/pulse-monitor-slack-vibe.md"
            try:
                urllib.request.urlopen(
                    urllib.request.Request(url, headers={"Authorization": f"token {GITEA_TOKEN}"}),
                    timeout=5,
                )
                print(f"\n[{i}/{len(dates)}] {day_iso} ({day_d.strftime('%a')}) — exists, skipping", flush=True)
                continue
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise

        print(f"\n[{i}/{len(dates)}] {day_iso} ({day_d.strftime('%a')}) ...", flush=True)
        per_channel = {}
        for ch_name, ch_id in channels:
            t0 = time.time()
            msgs, err = fetch_day_messages(ch_id, day_d)
            if err:
                per_channel[ch_name] = f"(fetch error: {err})"
                print(f"   #{ch_name}: ERR {err} ({time.time()-t0:.1f}s)", flush=True)
                continue
            summary = summarize_channel(ch_name, day_iso, msgs)
            per_channel[ch_name] = summary
            print(f"   #{ch_name}: {len(msgs)} msgs → {len(summary)} char summary ({time.time()-t0:.1f}s)", flush=True)
            time.sleep(0.5)

        attention = compute_attention(per_channel)
        url = emit_signal(day_iso, per_channel, [n for n, _ in channels], attention)
        print(f"   ✓ emitted (attention={attention}): {url}", flush=True)

    print(f"\n=== direct vibe-check backfill complete ({len(dates)} dates) ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
