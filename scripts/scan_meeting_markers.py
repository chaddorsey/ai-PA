#!/usr/bin/env python3
"""scan_meeting_markers.py — deterministic [c]/[;] meeting-marker → task scanner.

WHY THIS EXISTS
---------------
Chad annotates Granola meeting notes with inline markers:
    [c] <text>   → a task for Chad        (my_task)
    [;] <text>   → an action item for someone else (their_task)
    > <text>     → a pointer / expand-from-transcript hint (NOT a task)

These markers live ONLY in the user's *private notes*, which are exposed by the
Granola **MCP** (`get_meetings` → <private_notes>) — NOT by the Granola REST
Public API (whose Get Note schema returns only summary_text/summary_markdown/
transcript; confirmed against docs.granola.ai/api-reference/get-note). When the
meeting pipeline migrated from the MCP onto the REST poller (poll_granola.py),
the markers became invisible and `meeting_marker` task_queue rows stopped on
2026-04-28. This scanner restores the deterministic [c] → task path.

IMPORTANT: the MCP renders the brackets backslash-escaped (`\\[c\\]`), so the
parser un-escapes before matching — that escaping is exactly why earlier
`[c]` matchers silently found nothing.

DESIGN
------
- MCP-native: list_meetings (rolling window) → get_meetings → <private_notes>.
  Uses the Granola document UUIDs the MCP returns natively, so there is no
  fragile REST `not_*` ↔ UUID mapping.
- Rolling re-scan (default 7 days) so markers ADDED AFTER a meeting was first
  polled are still picked up. Idempotent on a content hash, so re-scanning the
  same window is a no-op for unchanged markers.
- Deterministic: one `meeting_marker` row per marker, written to
  pa_web.task_queue. The existing backup poller (process-task-queue.sh) routes
  meeting_marker → docs agent, which `task queue-claim`s and `task write`s each
  row to pa_web.tasks; enrichment then builds the work packet (the meeting
  permalink lands as a resource).

ENV
---
- POSTGRES_PASSWORD  (or PA_WEB_POSTGRES_URL) — DB auth
- PA_WEB_POSTGRES_PORT (default 5433)         — host-mapped Postgres port
- GRANOLA_MCP_URL (default http://localhost:8089/mcp) — supergateway proxy
  (the proxy handles Granola OAuth internally; no token needed here)

USAGE
-----
    python3 scan_meeting_markers.py [--window-days 7] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# The Granola MCP throttles / transiently fails under rapid get_meetings calls.
# Retry with backoff, and pace calls so a scan doesn't self-throttle.
MCP_RETRIES = 3
MCP_BACKOFF_S = 2.0
INTER_CALL_DELAY_S = 0.5

MCP_URL = os.environ.get("GRANOLA_MCP_URL", "http://localhost:8089/mcp")
DEFAULT_WINDOW_DAYS = 7

# Marker grammar (applied AFTER un-escaping markdown backslashes).
#   [c] <text>  -> my_task     (case-insensitive c)
#   [;] <text>  -> their_task
#   > <text>    -> pointer (context only; NOT turned into a task)
_RE_MY = re.compile(r"^\s*\[[cC]\]\s*(.+?)\s*$")
_RE_THEIR = re.compile(r"^\s*\[;\]\s*(.+?)\s*$")

# Marker kinds that become tasks (pointers are intentionally excluded).
TASK_KINDS = ("my_task", "their_task")


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(f"[{ts()}] [marker-scan] {msg}", flush=True)


# ─── MCP JSON-RPC over SSE (mirrors granola-ingest/ingest.py) ────────────────

_rpc_id = 0


def _mcp(method: str, params: dict) -> dict | None:
    global _rpc_id
    _rpc_id += 1
    body = {"jsonrpc": "2.0", "id": _rpc_id, "method": method, "params": params}
    req = urllib.request.Request(
        MCP_URL,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    # Catch EVERYTHING (socket.timeout on resp.read(), URLError, JSON decode
    # errors, etc.) and return None so the caller treats it as a transient
    # failure → retry → loud-degrade. A raw exception here would crash the whole
    # scan mid-meeting and silently drop every remaining meeting's markers.
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            raw = resp.read().decode()
        for line in raw.split("\n"):
            if line.startswith("data: "):
                return json.loads(line[6:])
        log(f"no SSE data line in MCP response: {raw[:160]}")
        return None
    except Exception as e:
        log(f"MCP call failed ({type(e).__name__}: {str(e)[:120]})")
        return None


def _mcp_call_text(name: str, arguments: dict) -> str | None:
    """One MCP tool call. Returns text content, or None on transport failure."""
    resp = _mcp("tools/call", {"name": name, "arguments": arguments})
    if not resp or resp.get("error"):
        return None
    content = resp.get("result", {}).get("content", [])
    if content and content[0].get("type") == "text":
        return content[0]["text"]
    return None


def _mcp_call_valid(name: str, arguments: dict) -> str | None:
    """MCP call that retries until the response contains a real <meeting> body.

    The Granola MCP intermittently returns a valid-looking but EMPTY stub
    (~47 chars, no <meeting> element) instead of the real payload — observed
    ~1-in-5 on get_meetings. A naive caller reads that stub as "no data" and
    silently drops markers. We treat any response lacking "<meeting " as a
    transient failure and retry; None means genuinely UNKNOWN after retries
    (callers must NOT treat None as "no markers").
    """
    last_len = 0
    for attempt in range(1, MCP_RETRIES + 1):
        txt = _mcp_call_text(name, arguments)
        if txt and "<meeting " in txt:
            return txt
        last_len = len(txt) if txt else 0
        if attempt < MCP_RETRIES:
            time.sleep(MCP_BACKOFF_S * attempt)
    log(f"MCP {name} returned no valid <meeting> after {MCP_RETRIES} tries "
        f"(last_len={last_len}) args={arguments}")
    return None


# ─── Parsing ─────────────────────────────────────────────────────────────────


def list_recent_meetings(window_days: int) -> list[dict]:
    """Return [{id, title, date}] for meetings in the rolling window.

    list_meetings only offers coarse ranges; we union this_week + last_week
    which covers any window_days <= 14 (the practical case), then keep the
    caller's intent informational.
    """
    seen: set[str] = set()
    out: list[dict] = []
    ranges = ["this_week"]
    if window_days > 7:
        ranges.append("last_week")
    for rng in ranges:
        txt = _mcp_call_valid("list_meetings", {"time_range": rng})
        if not txt:
            log(f"WARN: list_meetings({rng}) returned no valid data this run — "
                f"range skipped (rolling re-scan will retry next cycle)")
            continue
        for m in re.finditer(
            r'<meeting\s+id="([^"]+)"\s+title="([^"]+)"\s+date="([^"]+)"', txt
        ):
            mid, title, date = m.groups()
            if mid not in seen:
                seen.add(mid)
                out.append({"id": mid, "title": title, "date": date})
    return out


def fetch_private_notes(meeting_id: str) -> str | None:
    """Return the meeting's <private_notes> text (un-escaped).

    Tri-state return — the distinction is load-bearing, because conflating a
    throttled MCP with "no markers" would silently drop tasks:
      - None : the MCP fetch FAILED (after retries) — markers UNKNOWN this run.
      - ""   : fetch succeeded, the meeting genuinely has no private notes.
      - text : the private-notes body.
    """
    det = _mcp_call_valid("get_meetings", {"meeting_ids": [meeting_id]})
    if det is None:
        return None  # no valid <meeting> body after retries — UNKNOWN, not "no notes"
    m = re.search(r"<private_notes>\s*(.*?)\s*</private_notes>", det, re.DOTALL)
    if not m:
        return ""  # valid <meeting> body; this meeting genuinely has no private notes
    raw = m.group(1)
    # The MCP markdown-escapes brackets: "\[c\]" -> "[c]". Un-escape the
    # backslash-escaped punctuation so the marker regexes match.
    return raw.replace("\\[", "[").replace("\\]", "]").replace("\\;", ";")


def extract_markers(private_notes: str) -> list[dict]:
    """Parse private notes into [{kind, text}] for task-bearing markers."""
    markers: list[dict] = []
    for line in private_notes.splitlines():
        if not line.strip():
            continue
        mm = _RE_MY.match(line)
        if mm:
            markers.append({"kind": "my_task", "text": mm.group(1).strip()})
            continue
        tm = _RE_THEIR.match(line)
        if tm:
            markers.append({"kind": "their_task", "text": tm.group(1).strip()})
    # Drop empties / degenerate one-char captures.
    return [m for m in markers if len(m["text"]) > 1]


# ─── DB write ────────────────────────────────────────────────────────────────


def _db_url() -> str:
    url = os.environ.get("PA_WEB_POSTGRES_URL")
    if url:
        return url
    pw = os.environ.get("POSTGRES_PASSWORD", "")
    port = os.environ.get("PA_WEB_POSTGRES_PORT", "5433")
    return f"postgresql://postgres:{pw}@localhost:{port}/postgres"


def write_marker_rows(meeting: dict, markers: list[dict], dry_run: bool) -> int:
    """Write one idempotent meeting_marker task_queue row per marker.

    source_ref = mtgmarker-<meeting_uuid>-<sha1(kind+text)[:10]> so re-scanning
    the rolling window never duplicates, while a newly-typed marker yields a new
    row. Returns the count of rows newly inserted.
    """
    if not markers:
        return 0

    mid = meeting["id"]
    title = meeting.get("title", "")
    permalink = f"https://notes.granola.ai/d/{mid}"

    rows = []
    for mk in markers:
        h = hashlib.sha1(f"{mk['kind']}|{mk['text']}".encode()).hexdigest()[:10]
        source_ref = f"mtgmarker-{mid}-{h}"
        payload = {
            "raw_description": mk["text"],
            "marker_kind": mk["kind"],  # my_task | their_task
            "title": title,
            "meeting_id": mid,
            "permalink": permalink,
            "fetch_hint": f"granola:{mid}",
            "source_type": "meeting_marker",
            "occurred_at": meeting.get("date", ""),
            "captured_at": ts(),
        }
        rows.append((source_ref, payload))

    if dry_run:
        for sref, p in rows:
            log(f"  [DRY] would queue {p['marker_kind']}: {p['raw_description'][:70]!r} ({sref})")
        return 0

    import psycopg

    inserted = 0
    with psycopg.connect(_db_url(), autocommit=True, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            for sref, p in rows:
                cur.execute(
                    """
                    INSERT INTO pa_web.task_queue (source, source_ref, payload)
                    VALUES ('meeting_marker', %s, %s::jsonb)
                    ON CONFLICT (source, source_ref) DO NOTHING
                    RETURNING id
                    """,
                    (sref, json.dumps(p)),
                )
                if cur.fetchone() is not None:
                    inserted += 1
    return inserted


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="Scan Granola meetings for [c]/[;] task markers")
    ap.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS,
                    help="Rolling window to re-scan (default 7).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse + report, but do not write task_queue rows.")
    args = ap.parse_args()

    meetings = list_recent_meetings(args.window_days)
    if not meetings:
        log("no meetings returned from MCP (proxy down or empty window)")
        return 0
    log(f"scanning {len(meetings)} meeting(s) in the last ~{args.window_days}d")

    total_markers = 0
    total_inserted = 0
    meetings_with_markers = 0
    failed: list[dict] = []  # meetings whose MCP fetch failed — markers UNKNOWN
    for mtg in meetings:
        pn = fetch_private_notes(mtg["id"])
        time.sleep(INTER_CALL_DELAY_S)  # pace calls so we don't self-throttle
        if pn is None:
            failed.append(mtg)
            log(f"  WARN fetch FAILED: {mtg['title'][:45]!r} — markers UNKNOWN this run")
            continue
        if pn == "":
            continue  # fetched cleanly; genuinely no private notes
        markers = extract_markers(pn)
        if not markers:
            continue
        meetings_with_markers += 1
        total_markers += len(markers)
        ins = write_marker_rows(mtg, markers, args.dry_run)
        total_inserted += ins
        log(f"• {mtg['title'][:45]:45} markers={len(markers)} new_rows={ins}")

    log(
        f"done: meetings_with_markers={meetings_with_markers} "
        f"markers_seen={total_markers} rows_inserted={total_inserted} "
        f"fetch_failures={len(failed)}"
        + (" (dry-run)" if args.dry_run else "")
    )
    # A degraded run is LOUD and exits non-zero so launchd/monitoring notices —
    # never let a throttled MCP masquerade as a clean "0 markers" success.
    if failed:
        names = ", ".join(m["title"][:30] for m in failed)
        log(f"WARNING: {len(failed)}/{len(meetings)} meeting(s) could not be fetched "
            f"from the MCP; their [c] markers were NOT scanned and will be retried "
            f"next cycle (idempotent). Unfetched: {names}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
