# Twitter Bookmark Archive + Reply-Knowledge Rebuild — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken smaug pipeline with a headless-native flow that archives Twitter bookmarks (full text + media + permalinks + quoted/parent context + an LLM summary) to canonical, and selectively mines valuable deep reply chains into a separate tagged knowledge file.

**Architecture:** Fetch via our own `twitter-cli` (explicit-cookie auth, enriched to surface media/quoted/parent), dedup against a seen-IDs state file, summarize via the LiteLLM proxy (Fireworks-backed, no Anthropic), and write two canonical markdown surfaces: `reference/twitter-bookmarks.md` (every bookmark) and `reference/twitter-reply-knowledge.md` (gems from chains that pass two gates). One launchd job; smaug retired.

**Tech Stack:** Python 3.13 (`~/.letta/pa-tools-venv`), pytest, stdlib `urllib`/`subprocess`, `twitter-cli` (Poetry pkg we own), LiteLLM proxy (`127.0.0.1:4000`, OpenAI-compatible), Gitea HTTP API, macOS launchd. No new deps.

---

## Background facts (verified 2026-06-12 — do not re-derive)

**Fetch / twitter-cli**
- `twitter-cli` is our Poetry pkg at `/Volumes/main-drive/ai-PA/twitter-cli`, installed in `~/.letta/pa-tools-venv` + wrapped at `~/bin/twitter-cli` (+ symlink `/opt/homebrew/bin/twitter-cli`). Cookie auth via `TWITTER_CONFIG_PATH` (default `smaug/smaug.config.json`, keys `twitter.authToken`/`ct0`) or `AUTH_TOKEN`/`CT0`.
- Commands: `twitter-cli read bookmarks --count N --json`, `twitter-cli read tweet <id> --json` (raw X GraphQL).
- The per-tweet dict builder for bookmarks is **`_extract_instructions_tweets`** in `src/twitter_cli/client.py:520-556`. Bookmarks flow `get_bookmarks` (263) → `_extract_timeline_tweets` (439) → `_extract_instructions_tweets` (520). Current keys: `id, text, author_handle, author_name, created_at, retweet_count, favorite_count, reply_count, url`.
- Inside that method, per tweet: `tweet_result` (the `tweet_results.result` obj) and `legacy` (= `tweet_result["legacy"]`) are in scope. Rich fields live at:
  - media: `legacy["extended_entities"]["media"][i]` → `media_url_https` (photo) / `video_info.variants[].url` (video); `type` ∈ {photo, video, animated_gif}
  - quoted: `tweet_result["quoted_status_result"]["result"]` (same shape: `.legacy.full_text`, `.core.user_results.result.core.screen_name`, `.rest_id`)
  - parent (reply): `legacy["in_reply_to_status_id_str"]`, `legacy["in_reply_to_screen_name"]`
  - external links: `legacy["entities"]["urls"][i]["expanded_url"]`

**Reply chain (`read tweet --json`)**
- Path: `data.threaded_conversation_with_injections_v2.instructions`. Instruction with `type=="TimelineAddEntries"` has `entries[]`.
- Entry kinds: the MAIN tweet is `content.entryType == "TimelineTimelineItem"` (entryId `tweet-<id>`); replies are `content.entryType == "TimelineTimelineModule"` with `content.items[]`, each item `item.itemContent.tweet_results.result`.
- Per reply: `result.legacy.full_text`, `result.legacy.favorite_count`, `result.legacy.reply_count`, author at `result.core.user_results.result.core.screen_name`, urls at `result.legacy.entities.urls[].expanded_url`.
- Rank replies by `favorite_count + reply_count`, take top-N.

**Summarize (LiteLLM proxy — Fireworks)**
- Endpoint `http://127.0.0.1:4000/v1/chat/completions`, header `Authorization: Bearer <LITELLM_MASTER_KEY>` (in `.env`, format `sk-...`).
- Body `{"model": <id>, "max_tokens": N, "messages":[{"role":"user","content":...}]}`; response `choices[0].message.content`.
- **Working Fireworks models: `kimi-k2p6`, `deepseek-v4-pro`** (`gpt-oss-120b` errors via proxy; direct Fireworks API key is stale — use the proxy). Default to `kimi-k2p6`. These are *reasoning* models that may prefix chain-of-thought into `content` → parsing MUST be robust (delimited fields for the core summary; last `{...}` block for JSON). Model is env-overridable (`BOOKMARK_SUMMARY_MODEL`); switching to `gpt-4.1-mini` (cleaner output, also on the proxy) is a one-env change if needed.
- Mirror the POST helper in `scripts/backfill-slack-vibe-direct.py:120-152`.

**Canonical write (Gitea)**
- Repo `agents/agents-canonical` at `${GITEA_BASE_URL:-http://127.0.0.1:3030}`, token `GITEA_MEMFS_TOKEN` (in `pa-tools.env`). Read-modify-write via contents API: GET `…/contents/<path>?ref=main` for `sha`+content, then PUT with base64 content + `sha` (or POST if 404). Pattern in `scripts/materialize-current-signal.py` + `letta/daily_briefing/refresh_current.py:_put_current_cell`.

**Scheduling / cutover**
- launchd plists live in `~/Library/LaunchAgents/`; logs MUST go under `~/Library/Logs/`. Wrapper pattern: `letta/daily_briefing/refresh-current-briefing.sh`.
- Old pipeline `com.ai-pa.smaug` (runs `npx smaug run`) is being retired — its `bird` fetch can't get cookies headless and it's Anthropic-locked. Unload it at cutover. Leave `smaug-data/bookmarks.md` in place (historical).

**Test command** (new package): `cd /Volumes/main-drive/ai-PA/bookmark-archiver && PYTHONPATH=. ~/.letta/pa-tools-venv/bin/python -m pytest tests/ -q`
**twitter-cli tests**: `cd /Volumes/main-drive/ai-PA/twitter-cli && ~/.letta/pa-tools-venv/bin/python -m pytest tests/ -q`

## File Structure

| File | Responsibility |
|------|----------------|
| `twitter-cli/src/twitter_cli/enrich.py` (new) | Pure: `enrich_tweet(tweet_result) -> dict` — media/quoted/parent/links from a raw `tweet_results.result`. No I/O. |
| `twitter-cli/src/twitter_cli/client.py` (modify ~520-556) | Call `enrich_tweet` and merge its fields into each bookmark dict. |
| `twitter-cli/tests/test_enrich.py` (new) | Unit tests for `enrich_tweet` with inline fixtures. |
| `bookmark-archiver/bookmark_archiver/replies.py` (new) | Pure: `parse_reply_chain(graphql, top_n) -> list[dict]` from `read tweet` GraphQL. |
| `bookmark-archiver/bookmark_archiver/summarize.py` (new) | LiteLLM proxy client + prompt builders + robust parsers (core summary+gate1; reply extraction JSON). |
| `bookmark-archiver/bookmark_archiver/render.py` (new) | Pure: render a bookmark entry + a knowledge entry to markdown. |
| `bookmark-archiver/bookmark_archiver/state.py` (new) | Pure-ish: seen-IDs load/save + `new_bookmarks`. |
| `bookmark-archiver/bookmark_archiver/canonical.py` (new) | Gitea get/put file (read-modify-write append). |
| `bookmark-archiver/bookmark_archiver/archiver.py` (new) | Orchestration + `main()`. |
| `bookmark-archiver/tests/` (new) | Tests for replies, summarize-parsing, render, state. |
| `bookmark-archiver/run-bookmark-archive.sh` (new) | launchd wrapper (cookie + LITELLM key env). |
| `deployment/launchd/com.ai-pa.bookmark-archive.plist` (new) | launchd plist (daily). |

---

### Task 1: Enrich twitter-cli bookmark fields (media / quoted / parent / links)

**Files:**
- Create: `twitter-cli/src/twitter_cli/enrich.py`
- Modify: `twitter-cli/src/twitter_cli/client.py` (inside `_extract_instructions_tweets`, ~545-555)
- Test: `twitter-cli/tests/test_enrich.py`

- [ ] **Step 1: Write the failing test**

```python
# twitter-cli/tests/test_enrich.py
from twitter_cli.enrich import enrich_tweet

def _result(**legacy):
    base = {"legacy": {"full_text": "hi", **legacy}}
    return base

def test_media_photo_and_video():
    r = _result(extended_entities={"media": [
        {"type": "photo", "media_url_https": "https://pbs.twimg.com/media/a.jpg"},
        {"type": "video", "media_url_https": "https://pbs.twimg.com/x.jpg",
         "video_info": {"variants": [
             {"bitrate": 100, "url": "https://video.twimg.com/lo.mp4"},
             {"bitrate": 900, "url": "https://video.twimg.com/hi.mp4"}]}},
    ]})
    out = enrich_tweet(r)
    assert out["media"] == [
        {"type": "photo", "url": "https://pbs.twimg.com/media/a.jpg"},
        {"type": "video", "url": "https://video.twimg.com/hi.mp4"},  # highest bitrate
    ]

def test_external_links_exclude_tco_selfref():
    r = _result(entities={"urls": [
        {"expanded_url": "https://arxiv.org/pdf/123"},
        {"expanded_url": "https://twitter.com/i/web/status/1"},  # self-ref, drop
    ]})
    assert enrich_tweet(r)["links"] == ["https://arxiv.org/pdf/123"]

def test_quoted_and_parent():
    r = _result(in_reply_to_status_id_str="555", in_reply_to_screen_name="alice")
    r["quoted_status_result"] = {"result": {
        "rest_id": "999",
        "legacy": {"full_text": "quoted body"},
        "core": {"user_results": {"result": {"core": {"screen_name": "bob"}}}},
    }}
    out = enrich_tweet(r)
    assert out["in_reply_to"] == {"id": "555", "handle": "alice",
                                  "url": "https://x.com/alice/status/555"}
    assert out["quoted"] == {"id": "999", "handle": "bob", "text": "quoted body",
                             "url": "https://x.com/bob/status/999"}

def test_empty_when_absent():
    out = enrich_tweet(_result())
    assert out == {"media": [], "links": [], "in_reply_to": None, "quoted": None}
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd /Volumes/main-drive/ai-PA/twitter-cli && ~/.letta/pa-tools-venv/bin/python -m pytest tests/test_enrich.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'twitter_cli.enrich'`

- [ ] **Step 3: Implement `enrich.py`**

```python
# twitter-cli/src/twitter_cli/enrich.py
"""Pure extraction of rich fields from a raw X `tweet_results.result` object."""
from typing import Any


def _screen_name(result: dict) -> str:
    core = (((result.get("core") or {}).get("user_results") or {}).get("result") or {})
    return (core.get("core") or {}).get("screen_name") or (core.get("legacy") or {}).get("screen_name") or "_"


def _media(legacy: dict) -> list[dict]:
    out = []
    for m in (legacy.get("extended_entities") or {}).get("media", []) or []:
        mtype = m.get("type", "photo")
        if mtype in ("video", "animated_gif"):
            variants = [v for v in (m.get("video_info") or {}).get("variants", []) if v.get("url")]
            best = max(variants, key=lambda v: v.get("bitrate", 0), default=None)
            url = best["url"] if best else m.get("media_url_https", "")
        else:
            url = m.get("media_url_https", "")
        if url:
            out.append({"type": mtype, "url": url})
    return out


def _links(legacy: dict) -> list[str]:
    out = []
    for u in (legacy.get("entities") or {}).get("urls", []) or []:
        exp = u.get("expanded_url") or ""
        if exp and "twitter.com/i/web/status" not in exp and "/x.com/i/web/status" not in exp:
            out.append(exp)
    return out


def enrich_tweet(result: dict) -> dict[str, Any]:
    """Return {media, links, in_reply_to, quoted} for a tweet_results.result obj."""
    legacy = result.get("legacy") or {}
    in_reply_to = None
    rid = legacy.get("in_reply_to_status_id_str")
    if rid:
        h = legacy.get("in_reply_to_screen_name") or "_"
        in_reply_to = {"id": rid, "handle": h, "url": f"https://x.com/{h}/status/{rid}"}
    quoted = None
    qr = ((result.get("quoted_status_result") or {}).get("result") or {})
    if qr:
        qleg = qr.get("legacy") or {}
        qh = _screen_name(qr)
        qid = qr.get("rest_id") or qleg.get("id_str", "")
        quoted = {"id": qid, "handle": qh, "text": qleg.get("full_text", ""),
                  "url": f"https://x.com/{qh}/status/{qid}"}
    return {"media": _media(legacy), "links": _links(legacy),
            "in_reply_to": in_reply_to, "quoted": quoted}
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd /Volumes/main-drive/ai-PA/twitter-cli && ~/.letta/pa-tools-venv/bin/python -m pytest tests/test_enrich.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Wire `enrich_tweet` into the bookmark dict builder**

In `twitter-cli/src/twitter_cli/client.py`, at the top add `from .enrich import enrich_tweet`. Then in `_extract_instructions_tweets`, where each tweet dict is built (the `tweets.append({...})` around line 545-555), merge enrichment. Change the append to:

```python
                    tweet_dict = {
                        "id": legacy.get("id_str", tweet_result.get("rest_id", "")),
                        "text": legacy.get("full_text", ""),
                        "author_handle": user_legacy.get("screen_name") or user_core.get("screen_name", ""),
                        "author_name": user_legacy.get("name") or user_core.get("name", ""),
                        "created_at": legacy.get("created_at", ""),
                        "retweet_count": legacy.get("retweet_count", 0),
                        "favorite_count": legacy.get("favorite_count", 0),
                        "reply_count": legacy.get("reply_count", 0),
                        "url": f"https://x.com/{user_legacy.get('screen_name') or user_core.get('screen_name', '_')}/status/{legacy.get('id_str', '')}",
                    }
                    tweet_dict.update(enrich_tweet(tweet_result))
                    tweets.append(tweet_dict)
```

(Match the exact existing variable names — `tweet_result`, `legacy`, `user_legacy`, `user_core`. Read the current method first; preserve everything else.)

- [ ] **Step 6: Install editable so source edits are live + verify enriched JSON**

Run:
```bash
cd /Volumes/main-drive/ai-PA
~/.letta/pa-tools-venv/bin/pip install -e ./twitter-cli 2>&1 | tail -2
twitter-cli read bookmarks --count 3 --json | ~/.letta/pa-tools-venv/bin/python -c "import sys,json; d=json.load(sys.stdin); k=sorted(d[0].keys()); print(k); assert {'media','links','in_reply_to','quoted'} <= set(k), 'enriched keys missing'"
```
Expected: prints keys including `media, links, in_reply_to, quoted` and no assertion error.

- [ ] **Step 7: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git -C twitter-cli add src/twitter_cli/enrich.py src/twitter_cli/client.py tests/test_enrich.py
git -C twitter-cli commit -m "feat(enrich): surface media/quoted/parent/links on bookmark records

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Dedup state

**Files:**
- Create: `bookmark-archiver/bookmark_archiver/__init__.py` (empty), `bookmark-archiver/bookmark_archiver/state.py`
- Test: `bookmark-archiver/tests/test_state.py`

- [ ] **Step 1: Write the failing test**

```python
# bookmark-archiver/tests/test_state.py
import json
from bookmark_archiver import state

def test_new_bookmarks_filters_seen(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"seen_ids": ["1", "2"]}))
    items = [{"id": "1"}, {"id": "3"}, {"id": "4"}]
    fresh = state.new_bookmarks(items, p)
    assert [b["id"] for b in fresh] == ["3", "4"]

def test_mark_seen_appends_and_persists(tmp_path):
    p = tmp_path / "s.json"
    state.mark_seen(["3", "4"], p)
    state.mark_seen(["4", "5"], p)
    data = json.loads(p.read_text())
    assert sorted(data["seen_ids"]) == ["3", "4", "5"]

def test_missing_state_treats_all_new(tmp_path):
    p = tmp_path / "none.json"
    assert [b["id"] for b in state.new_bookmarks([{"id": "9"}], p)] == ["9"]
```

- [ ] **Step 2: Run, verify fail**

Run: `cd /Volumes/main-drive/ai-PA/bookmark-archiver && PYTHONPATH=. ~/.letta/pa-tools-venv/bin/python -m pytest tests/test_state.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'bookmark_archiver'`

- [ ] **Step 3: Implement**

```python
# bookmark-archiver/bookmark_archiver/state.py
"""Seen-bookmark-ID dedup state (JSON file)."""
import json
import os
from pathlib import Path


def _load(path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"seen_ids": []}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {"seen_ids": []}


def new_bookmarks(items: list[dict], path) -> list[dict]:
    """Return items whose 'id' is not in the seen set, preserving order."""
    seen = set(_load(path).get("seen_ids", []))
    return [b for b in items if b.get("id") not in seen]


def mark_seen(ids, path) -> None:
    """Add ids to the seen set and persist (atomic write)."""
    data = _load(path)
    merged = set(data.get("seen_ids", [])) | set(ids)
    data["seen_ids"] = sorted(merged)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh)
    os.replace(tmp, p)
```

- [ ] **Step 4: Run, verify pass** — same command — Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add bookmark-archiver/bookmark_archiver/__init__.py bookmark-archiver/bookmark_archiver/state.py bookmark-archiver/tests/test_state.py
git commit -m "feat(bookmarks): seen-id dedup state

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Reply-chain GraphQL parser

**Files:**
- Create: `bookmark-archiver/bookmark_archiver/replies.py`
- Test: `bookmark-archiver/tests/test_replies.py`

- [ ] **Step 1: Write the failing test**

```python
# bookmark-archiver/tests/test_replies.py
from bookmark_archiver.replies import parse_reply_chain

def _reply(text, favs, replies, handle, urls=None):
    return {"content": {"entryType": "TimelineTimelineModule", "items": [
        {"item": {"itemContent": {"tweet_results": {"result": {
            "legacy": {"full_text": text, "favorite_count": favs, "reply_count": replies,
                       "entities": {"urls": [{"expanded_url": u} for u in (urls or [])]}},
            "core": {"user_results": {"result": {"core": {"screen_name": handle}}}},
        }}}}}]}}

def _graphql(main_id, reply_entries):
    main = {"content": {"entryType": "TimelineTimelineItem",
                        "entryId": f"tweet-{main_id}"}}
    return {"data": {"threaded_conversation_with_injections_v2": {"instructions": [
        {"type": "TimelineAddEntries", "entries": [main, *reply_entries]}]}}}

def test_top_n_by_engagement_excludes_main():
    g = _graphql("100", [
        _reply("low", 1, 0, "a"),
        _reply("high", 500, 10, "b", urls=["https://github.com/x/y"]),
        _reply("mid", 50, 2, "c"),
    ])
    out = parse_reply_chain(g, top_n=2)
    assert [r["handle"] for r in out] == ["b", "c"]
    assert out[0]["text"] == "high"
    assert out[0]["links"] == ["https://github.com/x/y"]
    assert out[0]["engagement"] == 510

def test_empty_chain_returns_empty():
    assert parse_reply_chain(_graphql("1", []), top_n=5) == []

def test_handles_missing_keys_gracefully():
    g = {"data": {}}
    assert parse_reply_chain(g, top_n=5) == []
```

- [ ] **Step 2: Run, verify fail** — `cd /Volumes/main-drive/ai-PA/bookmark-archiver && PYTHONPATH=. ~/.letta/pa-tools-venv/bin/python -m pytest tests/test_replies.py -q` — Expected: FAIL (no module)

- [ ] **Step 3: Implement**

```python
# bookmark-archiver/bookmark_archiver/replies.py
"""Pure parser: `read tweet` GraphQL -> top-N replies by engagement."""


def _iter_reply_results(entries):
    for e in entries:
        content = e.get("content") or {}
        if content.get("entryType") != "TimelineTimelineModule":
            continue
        for item in content.get("items") or []:
            result = (((item.get("item") or {}).get("itemContent") or {})
                      .get("tweet_results") or {}).get("result") or {}
            if result.get("legacy"):
                yield result


def parse_reply_chain(graphql: dict, top_n: int = 25) -> list[dict]:
    """Return up to top_n replies sorted by (favorite+reply) desc.

    Each: {handle, text, engagement, favorite_count, reply_count, links}.
    """
    insts = (((graphql.get("data") or {})
              .get("threaded_conversation_with_injections_v2") or {})
             .get("instructions") or [])
    entries = []
    for i in insts:
        if i.get("type") == "TimelineAddEntries":
            entries = i.get("entries") or []
            break
    replies = []
    for r in _iter_reply_results(entries):
        legacy = r.get("legacy") or {}
        core = (((r.get("core") or {}).get("user_results") or {}).get("result") or {})
        handle = (core.get("core") or {}).get("screen_name") or "_"
        favs = legacy.get("favorite_count", 0) or 0
        reps = legacy.get("reply_count", 0) or 0
        links = [u.get("expanded_url") for u in (legacy.get("entities") or {}).get("urls", [])
                 if u.get("expanded_url")]
        replies.append({
            "handle": handle, "text": legacy.get("full_text", ""),
            "engagement": favs + reps, "favorite_count": favs,
            "reply_count": reps, "links": links,
        })
    replies.sort(key=lambda x: x["engagement"], reverse=True)
    return replies[:top_n]
```

- [ ] **Step 4: Run, verify pass** — Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add bookmark-archiver/bookmark_archiver/replies.py bookmark-archiver/tests/test_replies.py
git commit -m "feat(bookmarks): pure reply-chain GraphQL parser (top-N by engagement)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Summarizer (LiteLLM proxy + prompts + robust parsing)

**Files:**
- Create: `bookmark-archiver/bookmark_archiver/summarize.py`
- Test: `bookmark-archiver/tests/test_summarize.py`

- [ ] **Step 1: Write the failing test** (tests the pure parsers; the HTTP call is monkeypatched)

```python
# bookmark-archiver/tests/test_summarize.py
from bookmark_archiver import summarize

def test_parse_core_handles_reasoning_preamble():
    raw = ("Okay the user wants a title and summary. Let me think...\n"
           "TITLE: Intern Crashes Outlook\n"
           "SUMMARY: An intern emailed 50k people; reply-all storm crashed Outlook.\n"
           "REPLY_WORTH: no")
    out = summarize.parse_core(raw)
    assert out["title"] == "Intern Crashes Outlook"
    assert out["summary"].startswith("An intern emailed")
    assert out["reply_worth"] is False

def test_parse_core_reply_worth_yes():
    raw = "TITLE: Agent loop patterns\nSUMMARY: Thread on agent loops.\nREPLY_WORTH: yes"
    assert summarize.parse_core(raw)["reply_worth"] is True

def test_extract_json_from_noisy_output():
    raw = ('I will now produce JSON.\n{"has_durable_value": true, '
           '"group_sense": "Crowd shared repos.", '
           '"artifacts": [{"type":"repo","ref":"https://github.com/a/b","note":"agent lib"}], '
           '"topics": ["agents"]}  \nDone.')
    out = summarize.parse_reply_json(raw)
    assert out["has_durable_value"] is True
    assert out["artifacts"][0]["ref"] == "https://github.com/a/b"
    assert out["topics"] == ["agents"]

def test_extract_json_returns_none_on_garbage():
    assert summarize.parse_reply_json("no json here at all") is None

def test_call_llm_uses_monkeypatched_http(monkeypatch):
    monkeypatch.setattr(summarize, "_post", lambda body: {"choices": [{"message": {"content": "hello"}}]})
    assert summarize.call_llm("prompt", max_tokens=10) == "hello"
```

- [ ] **Step 2: Run, verify fail** — `cd /Volumes/main-drive/ai-PA/bookmark-archiver && PYTHONPATH=. ~/.letta/pa-tools-venv/bin/python -m pytest tests/test_summarize.py -q` — Expected: FAIL (no module)

- [ ] **Step 3: Implement**

```python
# bookmark-archiver/bookmark_archiver/summarize.py
"""LiteLLM-proxy summarization (Fireworks-backed) + robust output parsing.

Reasoning models can prepend chain-of-thought to `content`, so all parsing is
tolerant: delimited fields for the core summary, last-JSON-object for reply mining.
"""
import json
import os
import re
import urllib.error
import urllib.request

BASE = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1").rstrip("/")
MODEL = os.environ.get("BOOKMARK_SUMMARY_MODEL", "kimi-k2p6")
_KEY = os.environ.get("LITELLM_MASTER_KEY", "")


def _post(body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}/chat/completions", data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def call_llm(prompt: str, max_tokens: int = 500, model: str | None = None) -> str:
    """Return assistant content, or '' on failure."""
    try:
        d = _post({"model": model or MODEL, "max_tokens": max_tokens,
                   "messages": [{"role": "user", "content": prompt}]})
        choices = d.get("choices") or []
        return ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return ""


CORE_PROMPT = """You are archiving a saved tweet. Given the tweet, output EXACTLY three lines and nothing else:
TITLE: <=10 word descriptive title (no hashtags)
SUMMARY: one factual sentence on what it says/links to
REPLY_WORTH: yes only if the replies likely contain durable knowledge (links, repos, tools, techniques, expert debate); otherwise no

Tweet by @{handle} ({reply_count} replies):
{text}"""

REPLY_PROMPT = """Below are the top replies to a bookmarked tweet. Extract ONLY durable, reusable knowledge the crowd added (links, repos, tools, named techniques, expert consensus/correction). Ignore jokes, praise, and noise.

Output ONLY a JSON object (no prose) with keys:
  has_durable_value (bool), group_sense (<=2 sentences or ""),
  artifacts (list of {{type, ref, note}}; type in link|repo|tool|technique|claim),
  topics (1-3 short kebab-case tags)
If nothing durable, return has_durable_value=false with empty artifacts.

Original tweet by @{handle}: {text}

Top replies:
{replies}"""


def parse_core(raw: str) -> dict:
    """Tolerant parse of TITLE/SUMMARY/REPLY_WORTH lines from possibly-noisy output."""
    def grab(label):
        m = re.search(rf"^{label}:\s*(.+)$", raw, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else ""
    rw = grab("REPLY_WORTH").lower()
    return {"title": grab("TITLE") or "(untitled)",
            "summary": grab("SUMMARY"),
            "reply_worth": rw.startswith("y")}


def parse_reply_json(raw: str) -> dict | None:
    """Extract the last balanced {...} JSON object from raw; None if unparseable."""
    starts = [m.start() for m in re.finditer(r"\{", raw)]
    for s in reversed(starts):
        depth = 0
        for i in range(s, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[s:i + 1])
                    except json.JSONDecodeError:
                        break
    return None


def summarize_core(bm: dict) -> dict:
    raw = call_llm(CORE_PROMPT.format(handle=bm.get("author_handle", "_"),
                                      reply_count=bm.get("reply_count", 0),
                                      text=bm.get("text", "")), max_tokens=300)
    return parse_core(raw) if raw else {"title": "(untitled)", "summary": "(summary unavailable)", "reply_worth": False}


def mine_replies(bm: dict, replies: list[dict]) -> dict | None:
    corpus = "\n".join(f"- @{r['handle']} ({r['engagement']}): {r['text']}"
                       + ("  links: " + ", ".join(r["links"]) if r["links"] else "")
                       for r in replies)
    raw = call_llm(REPLY_PROMPT.format(handle=bm.get("author_handle", "_"),
                                       text=bm.get("text", ""), replies=corpus), max_tokens=700)
    out = parse_reply_json(raw) if raw else None
    if not out or not out.get("has_durable_value") or not out.get("artifacts"):
        return None
    return out
```

- [ ] **Step 4: Run, verify pass** — Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add bookmark-archiver/bookmark_archiver/summarize.py bookmark-archiver/tests/test_summarize.py
git commit -m "feat(bookmarks): LiteLLM/Fireworks summarizer with reasoning-tolerant parsing

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Markdown rendering

**Files:**
- Create: `bookmark-archiver/bookmark_archiver/render.py`
- Test: `bookmark-archiver/tests/test_render.py`

- [ ] **Step 1: Write the failing test**

```python
# bookmark-archiver/tests/test_render.py
from bookmark_archiver import render

BM = {"id": "100", "author_handle": "aaronp613", "text": "Netflix shipped a CLAUDE.md",
      "url": "https://x.com/aaronp613/status/100", "created_at": "Wed Jun 10 02:54:33 +0000 2026",
      "media": [{"type": "photo", "url": "https://pbs.twimg.com/m.jpg"}],
      "links": ["https://example.com/post"], "in_reply_to": None,
      "quoted": {"handle": "bob", "text": "orig", "url": "https://x.com/bob/status/9"}}

def test_render_bookmark_has_core_fields():
    md = render.bookmark_entry(BM, {"title": "Netflix CLAUDE.md leak",
                                    "summary": "An app shipped a config file."}, knowledge_anchor=None)
    assert "## @aaronp613 — Netflix CLAUDE.md leak" in md
    assert "https://x.com/aaronp613/status/100" in md
    assert "https://pbs.twimg.com/m.jpg" in md          # media
    assert "https://example.com/post" in md             # link
    assert "Quoting @bob" in md and "https://x.com/bob/status/9" in md
    assert "An app shipped a config file." in md

def test_render_bookmark_with_knowledge_pointer():
    md = render.bookmark_entry(BM, {"title": "T", "summary": "S"}, knowledge_anchor="twitter-reply-knowledge.md#100")
    assert "reply-chain notes" in md.lower()
    assert "twitter-reply-knowledge.md#100" in md

def test_render_knowledge_entry():
    k = {"has_durable_value": True, "group_sense": "Crowd shared repos.",
         "artifacts": [{"type": "repo", "ref": "https://github.com/a/b", "note": "agent lib"}],
         "topics": ["agents", "loops"]}
    md = render.knowledge_entry(BM, k, anchor="100")
    assert "<a id=\"100\">" in md or "#100" in md
    assert "agents" in md and "loops" in md
    assert "https://github.com/a/b" in md and "agent lib" in md
    assert "Crowd shared repos." in md
    assert "https://x.com/aaronp613/status/100" in md   # backlink to source bookmark
```

- [ ] **Step 2: Run, verify fail** — Expected: FAIL (no module)

- [ ] **Step 3: Implement**

```python
# bookmark-archiver/bookmark_archiver/render.py
"""Pure markdown rendering for the bookmark archive + reply-knowledge surfaces."""


def bookmark_entry(bm: dict, core: dict, knowledge_anchor: str | None) -> str:
    h = bm.get("author_handle", "_")
    lines = [f"## @{h} — {core.get('title', '(untitled)')}"]
    body = (bm.get("text") or "").strip().replace("\n", "\n> ")
    lines.append(f"> {body}")
    q = bm.get("quoted")
    if q:
        qt = (q.get("text") or "").strip().replace("\n", " ")
        lines.append(f"> *Quoting @{q.get('handle','_')}:* {qt[:200]}")
    p = bm.get("in_reply_to")
    lines.append("")
    lines.append(f"- **Tweet:** {bm.get('url','')}")
    if p:
        lines.append(f"- **Parent:** {p.get('url','')}")
    if q:
        lines.append(f"- **Quoted:** {q.get('url','')}")
    for m in bm.get("media", []) or []:
        lines.append(f"- **Media ({m.get('type','')}):** {m.get('url','')}")
    for ln in bm.get("links", []) or []:
        lines.append(f"- **Link:** {ln}")
    if core.get("summary"):
        lines.append(f"- **Summary:** {core['summary']}")
    if knowledge_anchor:
        lines.append(f"- ↳ **reply-chain notes:** [{knowledge_anchor}]({knowledge_anchor})")
    lines.append("")
    lines.append("---")
    return "\n".join(lines)


def knowledge_entry(bm: dict, k: dict, anchor: str) -> str:
    topics = " ".join(f"`{t}`" for t in k.get("topics", []) or [])
    lines = [f'## <a id="{anchor}"></a>@{bm.get("author_handle","_")} — reply-chain knowledge {topics}']
    lines.append(f"- **Source:** {bm.get('url','')}")
    if k.get("group_sense"):
        lines.append(f"- **Group sense:** {k['group_sense']}")
    if k.get("artifacts"):
        lines.append("- **Gems:**")
        for a in k["artifacts"]:
            lines.append(f"  - *{a.get('type','')}* — {a.get('ref','')} — {a.get('note','')}")
    lines.append("")
    lines.append("---")
    return "\n".join(lines)
```

- [ ] **Step 4: Run, verify pass** — Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add bookmark-archiver/bookmark_archiver/render.py bookmark-archiver/tests/test_render.py
git commit -m "feat(bookmarks): markdown rendering for archive + reply-knowledge

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Canonical writer (Gitea read-modify-write)

**Files:**
- Create: `bookmark-archiver/bookmark_archiver/canonical.py`
- Test: `bookmark-archiver/tests/test_canonical.py`

- [ ] **Step 1: Write the failing test** (HTTP monkeypatched; tests the prepend-under-date logic)

```python
# bookmark-archiver/tests/test_canonical.py
from bookmark_archiver import canonical

def test_prepend_entries_starts_new_file_with_frontmatter():
    out = canonical.prepend_entries("", ["## entry A\n---"], title="Twitter Bookmarks")
    assert out.startswith("---\n")
    assert "description: Twitter Bookmarks" in out
    assert "## entry A" in out

def test_prepend_entries_inserts_after_frontmatter_newest_first():
    existing = "---\ndescription: X\n---\n\n## old entry\n---\n"
    out = canonical.prepend_entries(existing, ["## new entry\n---"], title="X")
    # new entry appears before old entry, frontmatter preserved once
    assert out.count("---\ndescription") == 1
    assert out.index("## new entry") < out.index("## old entry")
```

- [ ] **Step 2: Run, verify fail** — Expected: FAIL (no module)

- [ ] **Step 3: Implement**

```python
# bookmark-archiver/bookmark_archiver/canonical.py
"""Read-modify-write of canonical markdown files via the Gitea contents API."""
import base64
import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("GITEA_BASE_URL", "http://127.0.0.1:3030").rstrip("/")
TOKEN = os.environ.get("GITEA_MEMFS_TOKEN", "")
REPO = f"{BASE}/api/v1/repos/agents/agents-canonical"

_FRONT = ("---\n"
          "description: {title}\n"
          "source: bookmark-archiver\n"
          "attention_level: routine\n"
          "mentioned_entities: []\n"
          "---\n\n")


def prepend_entries(existing: str, entries: list[str], title: str) -> str:
    """Insert entries (newest first) right after the frontmatter block."""
    block = "\n".join(entries).rstrip() + "\n"
    if not existing.strip():
        return _FRONT.format(title=title) + block
    if existing.startswith("---\n"):
        end = existing.find("\n---\n", 4)
        if end != -1:
            head = existing[:end + 5]
            rest = existing[end + 5:].lstrip("\n")
            return head + "\n" + block + "\n" + rest
    return _FRONT.format(title=title) + block + "\n" + existing


def _get(path: str):
    req = urllib.request.Request(f"{REPO}/contents/{path}?ref=main",
                                 headers={"Authorization": f"token {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
            return base64.b64decode(d["content"]).decode("utf-8"), d.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "", None
        raise


def write_entries(path: str, entries: list[str], title: str) -> str:
    """Prepend entries to the canonical file at path; return html_url."""
    existing, sha = _get(path)
    content = prepend_entries(existing, entries, title)
    body = {"branch": "main", "message": f"bookmarks: +{len(entries)} to {path}",
            "content": base64.b64encode(content.encode()).decode("ascii")}
    if sha:
        body["sha"] = sha
    req = urllib.request.Request(
        f"{REPO}/contents/{path}", data=json.dumps(body).encode(),
        method="PUT" if sha else "POST",
        headers={"Authorization": f"token {TOKEN}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return (json.loads(r.read()).get("content") or {}).get("html_url", "")
```

- [ ] **Step 4: Run, verify pass** — Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add bookmark-archiver/bookmark_archiver/canonical.py bookmark-archiver/tests/test_canonical.py
git commit -m "feat(bookmarks): canonical Gitea writer (prepend newest-first)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Orchestrator + wrapper + plist + cutover + end-to-end verify

**Files:**
- Create: `bookmark-archiver/bookmark_archiver/archiver.py`
- Create: `bookmark-archiver/run-bookmark-archive.sh`
- Create: `deployment/launchd/com.ai-pa.bookmark-archive.plist`

- [ ] **Step 1: Implement the orchestrator**

```python
# bookmark-archiver/bookmark_archiver/archiver.py
"""Bookmark archive + reply-knowledge orchestrator.

Flow: twitter-cli read bookmarks --json -> dedup -> per new bookmark:
core summary (+gate1) -> if reply_worth and reply_count>=THRESHOLD: read tweet,
parse top-N replies, mine (gate2) -> render -> write archive (+knowledge) -> mark seen.
"""
import json
import os
import subprocess
import sys

from bookmark_archiver import canonical, render, replies, state, summarize

TWITTER_CLI = os.environ.get("TWITTER_CLI_BIN", "twitter-cli")
STATE_PATH = os.environ.get("BOOKMARK_STATE",
                            "/Volumes/main-drive/ai-PA/smaug-data/.state/bookmark-archive-state.json")
ARCHIVE_PATH = "reference/twitter-bookmarks.md"
KNOWLEDGE_PATH = "reference/twitter-reply-knowledge.md"
REPLY_FLOOR = int(os.environ.get("BOOKMARK_REPLY_FLOOR", "25"))
REPLY_TOPN = int(os.environ.get("BOOKMARK_REPLY_TOPN", "25"))
FETCH_COUNT = int(os.environ.get("BOOKMARK_FETCH_COUNT", "40"))


def _twitter_json(args: list[str]) -> dict | list:
    out = subprocess.run([TWITTER_CLI, *args], capture_output=True, text=True, timeout=90)
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError(f"twitter-cli {args} failed rc={out.returncode}: {out.stderr[:200]}")
    return json.loads(out.stdout)


def run() -> dict:
    raw = _twitter_json(["read", "bookmarks", "--count", str(FETCH_COUNT), "--json"])
    items = raw if isinstance(raw, list) else raw.get("tweets", [])
    fresh = state.new_bookmarks(items, STATE_PATH)
    archive_entries, knowledge_entries, processed = [], [], []
    for bm in fresh:
        core = summarize.summarize_core(bm)
        anchor = None
        if core.get("reply_worth") and (bm.get("reply_count", 0) or 0) >= REPLY_FLOOR:
            try:
                detail = _twitter_json(["read", "tweet", bm["id"], "--json"])
                top = replies.parse_reply_chain(detail, top_n=REPLY_TOPN)
                mined = summarize.mine_replies(bm, top) if top else None
                if mined:
                    anchor = bm["id"]
                    knowledge_entries.append(render.knowledge_entry(bm, mined, anchor=anchor))
            except Exception as e:  # reply mining is best-effort; never block the archive
                print(f"  ! reply-mine failed for {bm['id']}: {e}", file=sys.stderr)
        ka = f"twitter-reply-knowledge.md#{anchor}" if anchor else None
        archive_entries.append(render.bookmark_entry(bm, core, knowledge_anchor=ka))
        processed.append(bm["id"])

    result = {"fetched": len(items), "new": len(fresh),
              "archived": len(archive_entries), "knowledge": len(knowledge_entries)}
    if archive_entries:
        canonical.write_entries(ARCHIVE_PATH, archive_entries, title="Twitter Bookmarks")
    if knowledge_entries:
        canonical.write_entries(KNOWLEDGE_PATH, knowledge_entries, title="Twitter Reply-Chain Knowledge")
    if processed:
        state.mark_seen(processed, STATE_PATH)
    return result


def main() -> int:
    try:
        r = run()
        print(json.dumps(r))
        return 0
    except Exception as e:
        import traceback
        print(json.dumps({"status": "error", "error": str(e),
                          "trace": traceback.format_exc()[-1200:]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Write the launchd wrapper**

```bash
# bookmark-archiver/run-bookmark-archive.sh
#!/usr/bin/env bash
# launchd wrapper: Twitter bookmark archive + reply-knowledge.
# Injects Twitter cookies (for twitter-cli, headless) from smaug.config.json and
# loads .env (LITELLM_MASTER_KEY) + pa-tools.env (GITEA_MEMFS_TOKEN).
set -euo pipefail
REPO="/Volumes/main-drive/ai-PA"
VENV_PY="/Users/dorseyhomeserver/.letta/pa-tools-venv/bin/python"
export PATH="/Users/dorseyhomeserver/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
set -a
. "$REPO/.env" 2>/dev/null || true
. "/Users/dorseyhomeserver/.letta/pa-tools.env" 2>/dev/null || true
set +a
CFG="$REPO/smaug/smaug.config.json"
export TWITTER_CONFIG_PATH="$CFG"
export AUTH_TOKEN="$("$VENV_PY" -c "import json;print(json.load(open('$CFG'))['twitter']['authToken'])")"
export CT0="$("$VENV_PY" -c "import json;print(json.load(open('$CFG'))['twitter']['ct0'])")"
export PYTHONPATH="$REPO/bookmark-archiver"
exec "$VENV_PY" -m bookmark_archiver.archiver
```

Then: `chmod +x /Volumes/main-drive/ai-PA/bookmark-archiver/run-bookmark-archive.sh`

- [ ] **Step 3: Write the plist (daily 6:30 AM ET)**

```xml
<!-- deployment/launchd/com.ai-pa.bookmark-archive.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.ai-pa.bookmark-archive</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Volumes/main-drive/ai-PA/bookmark-archiver/run-bookmark-archive.sh</string>
    </array>
    <key>StartCalendarInterval</key><dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>30</integer></dict>
    <key>RunAtLoad</key><false/>
    <key>ProcessType</key><string>Background</string>
    <key>StandardOutPath</key><string>/Users/dorseyhomeserver/Library/Logs/bookmark-archive/stdout.log</string>
    <key>StandardErrorPath</key><string>/Users/dorseyhomeserver/Library/Logs/bookmark-archive/stderr.log</string>
    <key>WorkingDirectory</key><string>/Volumes/main-drive/ai-PA</string>
</dict>
</plist>
```

- [ ] **Step 4: Full suite green + syntax checks**

Run:
```bash
cd /Volumes/main-drive/ai-PA/bookmark-archiver && PYTHONPATH=. ~/.letta/pa-tools-venv/bin/python -m pytest tests/ -q
~/.letta/pa-tools-venv/bin/python -m py_compile bookmark_archiver/archiver.py
bash -n run-bookmark-archive.sh && plutil -lint ../deployment/launchd/com.ai-pa.bookmark-archive.plist
chmod +x run-bookmark-archive.sh
```
Expected: all tests pass; no compile/syntax errors; plist `OK`.

- [ ] **Step 5: Live end-to-end dry run (controller-verified)**

Run the wrapper directly and inspect the JSON result + that canonical files appear:
```bash
cd /Volumes/main-drive/ai-PA
bash bookmark-archiver/run-bookmark-archive.sh
# then verify the archive exists + has entries:
set -a; . ~/.letta/pa-tools.env; set +a
curl -s -H "Authorization: token $GITEA_MEMFS_TOKEN" "$GITEA_BASE_URL/api/v1/repos/agents/agents-canonical/raw/reference/twitter-bookmarks.md" | head -30
```
Expected: stdout JSON like `{"fetched":N,"new":M,"archived":M,"knowledge":K}`; the archive file shows frontmatter + `## @handle — <title>` entries with **Tweet/Media/Summary** lines. Independently confirm `new`>0 on first run and that a re-run reports `new:0` (dedup works).

- [ ] **Step 6: Install + load launchd; cutover from smaug**

```bash
mkdir -p ~/Library/Logs/bookmark-archive
cp /Volumes/main-drive/ai-PA/deployment/launchd/com.ai-pa.bookmark-archive.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.ai-pa.bookmark-archive.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.ai-pa.bookmark-archive.plist
launchctl list | grep bookmark-archive
# Retire the old broken pipeline:
launchctl unload ~/Library/LaunchAgents/com.ai-pa.smaug.plist 2>/dev/null && echo "smaug unloaded"
```
Expected: bookmark-archive listed (status `-`/`0`); smaug unloaded.

- [ ] **Step 7: Add MC recipe + commit**

Add to MC's memfs `mc_cli_recipes.md` (read first, then insert after the Twitter section), pushing to Gitea:
```markdown
### Twitter bookmark archive + reply-chain knowledge (read)

Saved bookmarks (full text, media, permalinks, quoted/parent, summary) refresh daily into canonical:
```bash
curl -s -H "$AUTH" "$GW/reference/twitter-bookmarks.md"        # full bookmark archive
curl -s -H "$AUTH" "$GW/reference/twitter-reply-knowledge.md"  # gems mined from valuable reply chains (links/repos/techniques, tagged)
```
(`$GW`/`$AUTH` as in Daily kickoff.) Use the knowledge file for cross-connections — it's tagged meta-knowledge from deep reply threads.
```

Commit the package + wrapper + plist (repo) and push the recipe (memfs):
```bash
cd /Volumes/main-drive/ai-PA
git add bookmark-archiver deployment/launchd/com.ai-pa.bookmark-archive.plist docs/plans/2026-06-12-twitter-bookmarks-rebuild-plan.md
git commit -m "feat(bookmarks): headless bookmark archiver + reply-knowledge (retire smaug)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
cd ~/.letta/lc-local-backend/memfs/agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d/memory
git pull --rebase --autostash && git add system/mc_cli_recipes.md && git commit -m "recipe: twitter bookmark archive + reply-knowledge" && git push
```

---

## Notes / decisions baked in
- **Drop smaug entirely** (bird browser-cookies + claude-CLI are the broken/unwanted parts); unload its launchd job at cutover. Keep `smaug-data/bookmarks.md` as history.
- **Fetch via our own twitter-cli** (one verified substrate), enriched to surface media/quoted/parent on the lean bookmarks path (Task 1) — no per-tweet calls for the base archive.
- **Summarize via LiteLLM proxy, Fireworks `kimi-k2p6`** (no Anthropic), reasoning-tolerant parsing; `BOOKMARK_SUMMARY_MODEL` env-overridable (e.g. `gpt-4.1-mini` if cleaner output wanted).
- **Two gates** for reply mining: Gate-1 = `reply_worth` (piggybacked on the core summary call) AND `reply_count >= 25`; Gate-2 = miner returns `has_durable_value` + non-empty artifacts. Top-N (25) replies by engagement only.
- **Two canonical surfaces:** `reference/twitter-bookmarks.md` (every bookmark) + `reference/twitter-reply-knowledge.md` (tagged gems, backlinked); archive entries carry a pointer when knowledge exists. Agents read both via the canonical curl pattern.
- **Human override** (force-deep on specific bookmarks) deferred to v2.
- Reply mining + summary are **best-effort** — failures never block the core archive; the bookmark still lands (summary placeholder) and is marked seen.
