"""
Push handler: capture direct @-mentions of Chad in any channel the bot is in,
and emit/update the Layer-5 canonical signal in real time.

This complements the 15-min `Slack Mentions: Intra-Day Refresh` cron
(via search.messages) — push gives sub-second latency for channels the bot
sees; cron is the backstop for channels the bot is not in or for any
push-path downtime.

Signal: agents-canonical/signals/<DATE>/slack-watch-mentions-active.md
Idempotent: same path; mention_ids list de-duplicates against ts.

CHAD_USER_ID is hardcoded — this handler exists specifically to track
Chad's mentions, not arbitrary users.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:  # python <3.9 fallback
    ZoneInfo = None  # type: ignore

from slack_bolt import App
from slack_sdk import WebClient

logger = logging.getLogger(__name__)

# --- Config ---
CHAD_USER_ID = os.environ.get("CHAD_USER_ID", "U02V91KU8")
CHAD_MENTION_TOKEN = f"<@{CHAD_USER_ID}>"
GITEA_BASE_URL = os.environ.get("GITEA_BASE_URL_HOST", "http://gitea:3000").rstrip("/")
GITEA_TOKEN = os.environ.get("GITEA_MEMFS_TOKEN", "")
CANONICAL_REPO = "agents/agents-canonical"
SIGNAL_SLUG = "mentions-active"
SIGNAL_SOURCE = "slack-watch"
PRIORITY_NAMES = {
    n.strip().lower()
    for n in (
        "Sue Brau,Leslie Bondaryk,Kiley Brown,Helen Quinn,Bronwyn Bevan"
    ).split(",")
}
PRIORITY_KEYWORDS = (
    "letter request",
    "advisory",
    "deadline",
    "urgent",
    "asap",
)


def _today_et_iso() -> str:
    if ZoneInfo:
        return datetime.now(tz=ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    return datetime.utcnow().strftime("%Y-%m-%d")


def _now_utc_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _ts_to_et_hhmm(ts: str) -> str:
    try:
        epoch = float(ts.split(".")[0])
        if ZoneInfo:
            dt = datetime.fromtimestamp(epoch, tz=ZoneInfo("America/New_York"))
        else:
            dt = datetime.fromtimestamp(epoch)
        return dt.strftime("%H:%M")
    except Exception:
        return "??:??"


def _ts_to_utc_iso(ts: str) -> str:
    try:
        epoch = float(ts.split(".")[0])
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    except Exception:
        return ""


# --- Gitea I/O ---


def _gitea_get(path: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (sha, body_text) for an existing file; (None, None) if 404."""
    url = f"{GITEA_BASE_URL}/api/v1/repos/{CANONICAL_REPO}/contents/{path}?ref=main"
    req = urllib.request.Request(url, headers={"Authorization": f"token {GITEA_TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            content_b64 = data.get("content", "")
            text = base64.b64decode(content_b64).decode("utf-8") if content_b64 else ""
            return data.get("sha"), text
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        raise


def _gitea_put(path: str, content: str, message: str, sha: Optional[str]) -> None:
    url = f"{GITEA_BASE_URL}/api/v1/repos/{CANONICAL_REPO}/contents/{path}"
    body: Dict[str, Any] = {
        "branch": "main",
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "message": message,
    }
    if sha:
        body["sha"] = sha
    method = "PUT" if sha else "POST"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"token {GITEA_TOKEN}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    urllib.request.urlopen(req, timeout=15)


# --- Signal parse / compose ---

_MENTION_IDS_RE = re.compile(r"^mention_ids:\s*\[(.*)\]\s*$", re.MULTILINE)


def _parse_existing_ids(body_text: str) -> List[str]:
    if not body_text:
        return []
    m = _MENTION_IDS_RE.search(body_text)
    if not m:
        return []
    raw = m.group(1)
    return [s.strip().strip('"\'') for s in raw.split(",") if s.strip()]


def _compute_attention(
    sender_display_name: str, sender_real_name: str, text: str, prior_attention: str
) -> str:
    if prior_attention in ("urgent",):
        return "urgent"  # never demote
    name_blob = (sender_display_name + " " + sender_real_name).lower()
    if any(p in name_blob for p in PRIORITY_NAMES):
        return "elevated"
    text_low = (text or "").lower()
    if any(k in text_low for k in PRIORITY_KEYWORDS):
        return "elevated"
    return prior_attention if prior_attention == "elevated" else "routine"


def _existing_attention_level(body_text: str) -> str:
    m = re.search(r"^attention_level:\s*(\w+)\s*$", body_text or "", re.MULTILINE)
    return (m.group(1).strip().lower() if m else "routine") or "routine"


def _existing_body_section(body_text: str) -> str:
    """Return everything after the closing frontmatter '---' line."""
    if not body_text:
        return ""
    parts = body_text.split("\n---\n", 2)
    if len(parts) >= 2:
        return parts[-1]
    # fallback: empty
    return ""


def _format_mention_block(m: Dict[str, Any]) -> str:
    snippet = (m.get("text") or "").replace("\n", " ").strip()
    if len(snippet) > 100:
        snippet = snippet[:100] + "…"
    return (
        f"### [{m['hhmm_et']} ET] #{m['channel_name']} — @{m['sender_display']}\n"
        f"{snippet}\n"
        f"- channel_id: {m['channel_id']}\n"
        f"- ts: {m['ts']}\n"
        f"- thread_ts: {m.get('thread_ts') or 'null'}\n"
        f"- sender_id: {m['sender_id']}\n"
        f"- permalink: {m.get('permalink') or '(unavailable)'}\n"
    )


def _build_signal_body(
    mentions: List[Dict[str, Any]], date_str: str, last_event_at_utc: str
) -> Tuple[str, str, List[str], str]:
    """Return (body_markdown, attention_level, mentioned_entities, frontmatter_extra)."""
    sorted_m = sorted(mentions, key=lambda x: float(x["ts"]), reverse=True)
    senders = []
    seen = set()
    for m in sorted_m:
        n = m["sender_display"]
        if n and n not in seen:
            seen.add(n)
            senders.append(n)
    channels = sorted({"#" + m["channel_name"] for m in sorted_m if m.get("channel_name")})

    # Attention from the strongest signal among all today's mentions
    attn = "routine"
    for m in sorted_m:
        candidate = _compute_attention(m["sender_display"], m.get("sender_real", ""), m.get("text", ""), attn)
        if candidate == "elevated":
            attn = "elevated"

    n = len(sorted_m)
    if n == 0:
        header = f"No direct mentions today (last event seen: never)."
    else:
        header = (
            f"Direct mentions today: {n}. "
            f"Most recent: {sorted_m[0]['hhmm_et']} ET. "
            f"Senders: {', '.join(senders) if senders else '(none)'}."
        )
    body = header + "\n\n" + "\n".join(_format_mention_block(m) for m in sorted_m)

    mentioned = senders + channels
    return body, attn, mentioned, last_event_at_utc


def _emit_signal(date_str: str, mentions: List[Dict[str, Any]]) -> None:
    if not GITEA_TOKEN:
        logger.warning("chad_mention_signal: GITEA_MEMFS_TOKEN not set; skipping emission")
        return

    path = f"signals/{date_str}/{SIGNAL_SOURCE}-{SIGNAL_SLUG}.md"
    sha, existing_body = _gitea_get(path)

    last_event_at = ""
    if mentions:
        latest_ts = max(float(m["ts"]) for m in mentions)
        last_event_at = datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat()

    body_md, attn, mentioned, _ = _build_signal_body(mentions, date_str, last_event_at)

    description = (
        f"Intra-day direct mentions for {date_str} (push-driven; "
        f"updated at {_now_utc_iso()})"
    )

    # Format mention_ids as a JSON-ish list of strings inside the frontmatter
    mention_ids_str = ", ".join(json.dumps(m["ts"]) for m in mentions)
    extra_fm_lines = [
        f"last_event_at: {last_event_at}" if last_event_at else "last_event_at: ",
        f"events_today: {len(mentions)}",
        f"refreshed_at: {_now_utc_iso()}",
        f"last_push_at: {_now_utc_iso()}",
        f"mention_ids: [{mention_ids_str}]",
    ]

    fm_lines = [
        "---",
        f"description: {description}",
        f"source: {SIGNAL_SOURCE}",
        f"attention_level: {attn}",
        "mentioned_entities: [" + ", ".join(json.dumps(e) for e in mentioned) + "]",
        f"composed_at: {_now_utc_iso()}",
        f"date: {date_str}",
        *extra_fm_lines,
        "---",
        "",
    ]
    full_content = "\n".join(fm_lines) + body_md
    if not full_content.endswith("\n"):
        full_content += "\n"

    _gitea_put(
        path,
        full_content,
        f"signals: push update — {SIGNAL_SOURCE} {SIGNAL_SLUG} for {date_str}",
        sha,
    )
    logger.info(
        "chad_mention_signal: emitted %s mentions=%d attention=%s",
        path, len(mentions), attn,
    )


# --- Handler ---


def _accumulate_today_mentions(
    today_str: str, new_mention: Dict[str, Any], existing_body: Optional[str]
) -> List[Dict[str, Any]]:
    """Re-construct the day's full mention list by parsing the existing body
    and appending the new one (de-duplicated by ts).
    """
    mentions: List[Dict[str, Any]] = []
    seen_ts = set()

    if existing_body:
        # Parse the existing body for mention blocks. Pattern matches:
        #   ### [HH:MM ET] #channel — @sender
        #   <snippet line>
        #   - channel_id: C…
        #   - ts: <ts>
        #   - thread_ts: <ts or null>
        #   - sender_id: U…
        #   - permalink: <url>
        block_re = re.compile(
            r"### \[(\d\d:\d\d) ET\] #(\S+) — @([^\n]+)\n"
            r"([^\n]*)\n"
            r"- channel_id: (\S+)\n"
            r"- ts: (\S+)\n"
            r"- thread_ts: (\S+)\n"
            r"- sender_id: (\S+)\n"
            r"- permalink: (\S+)",
            re.MULTILINE,
        )
        for m in block_re.finditer(existing_body):
            hhmm, ch_name, sender, snippet, ch_id, ts, thread_ts, sender_id, perm = m.groups()
            if ts in seen_ts:
                continue
            seen_ts.add(ts)
            mentions.append({
                "hhmm_et": hhmm,
                "channel_name": ch_name,
                "sender_display": sender.strip(),
                "sender_real": "",
                "text": snippet,
                "channel_id": ch_id,
                "ts": ts,
                "thread_ts": None if thread_ts == "null" else thread_ts,
                "sender_id": sender_id,
                "permalink": None if perm == "(unavailable)" else perm,
            })

    if new_mention["ts"] not in seen_ts:
        mentions.append(new_mention)

    return mentions


def _handle_chad_mention(event: Dict[str, Any], client: WebClient, logger: logging.Logger):
    text = event.get("text") or ""
    if CHAD_MENTION_TOKEN not in text:
        return  # Not a direct mention of Chad — ignore. (channels:history fires on every msg.)

    sender_id = event.get("user")
    if not sender_id or sender_id == CHAD_USER_ID:
        return  # Chad mentioning himself, or system event without a user

    # Filter out bot messages explicitly (bot_id present and no real user)
    if event.get("bot_id") and not event.get("user"):
        return

    channel_id = event.get("channel")
    ts = event.get("ts") or ""
    thread_ts = event.get("thread_ts")
    if thread_ts == ts:
        thread_ts = None  # treat self-thread root as top-level

    try:
        # Resolve sender display name
        sender_display = sender_id
        sender_real = ""
        try:
            user_info = client.users_info(user=sender_id)
            profile = user_info["user"].get("profile", {}) if user_info.get("ok") else {}
            sender_display = (
                profile.get("display_name")
                or profile.get("real_name")
                or user_info["user"].get("name")
                or sender_id
            )
            sender_real = profile.get("real_name", "")
        except Exception as e:
            logger.warning(f"chad_mention_signal: users_info failed for {sender_id}: {e}")

        # Resolve channel name
        channel_name = channel_id
        try:
            ch_info = client.conversations_info(channel=channel_id)
            if ch_info.get("ok"):
                channel_name = ch_info["channel"].get("name") or channel_id
        except Exception as e:
            logger.warning(f"chad_mention_signal: conversations_info failed for {channel_id}: {e}")

        # Resolve permalink
        permalink: Optional[str] = None
        try:
            pl = client.chat_getPermalink(channel=channel_id, message_ts=ts)
            if pl.get("ok"):
                permalink = pl.get("permalink")
        except Exception as e:
            logger.warning(f"chad_mention_signal: getPermalink failed: {e}")

        new_mention = {
            "hhmm_et": _ts_to_et_hhmm(ts),
            "channel_name": channel_name,
            "sender_display": sender_display,
            "sender_real": sender_real,
            "text": text,
            "channel_id": channel_id,
            "ts": ts,
            "thread_ts": thread_ts,
            "sender_id": sender_id,
            "permalink": permalink,
        }

        date_str = _today_et_iso()
        path = f"signals/{date_str}/{SIGNAL_SOURCE}-{SIGNAL_SLUG}.md"
        _, existing_body = _gitea_get(path)
        all_mentions = _accumulate_today_mentions(date_str, new_mention, existing_body)
        _emit_signal(date_str, all_mentions)
    except Exception as e:
        logger.error(f"chad_mention_signal: handler failed: {e}", exc_info=True)


def register(app: App):
    @app.event("message")
    def _on_message(event, client, logger):
        # Bolt fires this on every visible message — short-circuit fast for non-mentions.
        _handle_chad_mention(event, client, logger)
