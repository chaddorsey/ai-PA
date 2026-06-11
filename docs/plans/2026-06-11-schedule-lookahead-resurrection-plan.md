# Schedule Lookahead Resurrection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pre-write the next ~2 weeks of daily schedule cells and add a cross-tab "when am I free" query, reusing the now-pure-Python `generate_daily_briefing`.

**Architecture:** A daily 5 AM launchd job loops `generate_daily_briefing(target_date)` over D+2…D+13 weekdays (it already writes `signals/{date}/schedule.md` to the agents-canonical Gitea repo as a pure-Python side effect — no LLM, no agent). A separate CLI parses the rendered "Available Time Remaining" bullets from those dated cells and answers free-time queries across a date range, regenerating any missing/stale day on demand. Stale failure-marker files from the old (abandoned) lookahead are deleted.

**Tech Stack:** Python 3.13 (`~/.letta/pa-tools-venv`), pytest 9, stdlib `urllib` against the Gitea HTTP API, macOS launchd. No new dependencies.

---

## Background facts (verified 2026-06-11 — do not re-derive)

- **`generate_daily_briefing(calendar_id=None, timezone=None, target_date=None, include_troop_meetings=None) -> Dict`** lives in `letta/daily_briefing/generate_daily_briefing.py`. It is pure Python (no LLM). For a non-today `target_date` it computes the full 8 AM–5 PM day (start point is 8 AM, not "now"). It returns `{"status": "ok"|"error", "briefing": "<VERBATIM-wrapped markdown>", "signal_written": bool, "error_message"?: str, ...}` and, as a side effect, **upserts `signals/{target_date}/schedule.md`** into the `agents/agents-canonical` Gitea repo. Requires env: `GITEA_MEMFS_TOKEN`, `GITEA_BASE_URL`, `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`.
- **Dated cell frontmatter** written by that function (clean body, NOT VERBATIM-wrapped in the file):
  ```
  ---
  description: Daily schedule + available time for {date}
  source: daily-schedule-agent
  attention_level: routine
  mentioned_entities: []
  date: {date}
  last_refreshed_at: {ISO8601 with tz}
  ---
  ```
- **Rendered free-block bullet format** (the parser target), produced by `generate_daily_briefing.py`:
  - Header line: `**Available Time Remaining** — 4h, 50 min remaining`
  - Each block: `• **8:00 AM–10:00 AM** - (2h)` — the separator between the two times is an EN DASH `–` (U+2013); the duration is in `- (...)`. Times are 12-hour (`H:MM AM/PM`).
  - Fully-booked day: `*No available time blocks*` (no bullets). `workday over (0 min remaining)` only ever appears for *today*, never a future date.
- **Wrapper pattern** to clone: `letta/daily_briefing/refresh-current-briefing.sh` — sources `~/.letta/pa-tools.env`, runs `~/.letta/pa-tools-venv/bin/python -m daily_briefing.<module>`, sets `PYTHONPATH=/Volumes/main-drive/ai-PA/letta/pulse-tools:/Volumes/main-drive/ai-PA/letta`.
- **launchd** live plists in `~/Library/LaunchAgents/`, tracked copies in `deployment/launchd/`. **Logs MUST go under `~/Library/Logs/`** (never `/Volumes` — launchd EX_CONFIG/78 trap).
- **Tests** live in `letta/daily_briefing/tests/`, import as `from daily_briefing.X import Y`, run with:
  ```bash
  cd /Volumes/main-drive/ai-PA/letta && PYTHONPATH="$PWD" ~/.letta/pa-tools-venv/bin/python -m pytest daily_briefing/tests/ -q
  ```
- **Stale markers to delete:** `signals/{date}/mc-lookahead-{date}.md` and `signals/{date}/mc-daily-briefing-lookahead-{date}.md` (failure markers from the abandoned lookahead, `source: mc`, last written 06-05/06-07).

## File Structure

| File | Responsibility |
|------|----------------|
| `letta/daily_briefing/availability.py` (new) | Pure parser: rendered briefing markdown → list of free blocks (24h). No network. |
| `letta/daily_briefing/lookahead_prewrite.py` (new) | Date math + loop calling `generate_daily_briefing` per future weekday; aggregate result; failure health signal. |
| `letta/daily_briefing/query_available_time.py` (new) | Cross-tab CLI: fetch dated cells over a range, parse via `availability`, filter, output text/JSON; lazy-regen missing/stale days. |
| `letta/daily_briefing/lookahead-prewrite.sh` (new) | launchd wrapper for the daily pre-write run. |
| `letta/daily_briefing/query-available-time.sh` (new) | env-loading wrapper so MC can call the query via Bash. |
| `deployment/launchd/com.ai-pa.schedule-lookahead.plist` (new) | Tracked launchd plist, daily 5:00 AM ET. |
| `scripts/cleanup-lookahead-markers.py` (new) | Delete the stale `mc-lookahead-*` / `mc-daily-briefing-lookahead-*` markers via Gitea API. |
| `letta/daily_briefing/tests/test_availability.py` (new) | Unit tests for the parser. |
| `letta/daily_briefing/tests/test_lookahead_prewrite.py` (new) | Unit tests for date math + loop (mocked tool). |
| `letta/daily_briefing/tests/test_query_available_time.py` (new) | Unit tests for filter/format + lazy-refresh (mocked fetch/tool). |

---

### Task 1: Pure availability parser

**Files:**
- Create: `letta/daily_briefing/availability.py`
- Test: `letta/daily_briefing/tests/test_availability.py`

- [ ] **Step 1: Write the failing test**

```python
# letta/daily_briefing/tests/test_availability.py
from daily_briefing.availability import (
    parse_available_blocks, filter_blocks, _to_minutes_12h,
)

SAMPLE = """**Friday's Schedule** (updated Jun. 11 at 6:30 PM)

• **9:00 AM–11:00 AM** — *Email & Tasks*

**Available Time Remaining** — 4h, 50 min remaining
• **8:00 AM–10:00 AM** - (2h)
• **10:50 AM–11:00 AM** - (10 min)
• **1:30 PM–3:00 PM** - (1h 30 min)
• **4:00 PM–5:00 PM** - (1h)

**Schedule JSON** (for time-remaining.py): {"work_end":"17:00"}
"""

def test_to_minutes_12h():
    assert _to_minutes_12h("8:00 AM") == 480
    assert _to_minutes_12h("12:00 PM") == 720
    assert _to_minutes_12h("12:30 AM") == 30
    assert _to_minutes_12h("1:30 PM") == 810

def test_parse_blocks_from_sample():
    blocks = parse_available_blocks(SAMPLE)
    assert blocks == [
        {"start": "08:00", "end": "10:00", "duration_min": 120},
        {"start": "10:50", "end": "11:00", "duration_min": 10},
        {"start": "13:30", "end": "15:00", "duration_min": 90},
        {"start": "16:00", "end": "17:00", "duration_min": 60},
    ]

def test_fully_booked_returns_empty():
    md = "**Available Time Remaining** — 0 min remaining\n*No available time blocks*\n"
    assert parse_available_blocks(md) == []

def test_workday_over_returns_empty():
    md = "**Available Time Remaining** — workday over (0 min remaining)\n"
    assert parse_available_blocks(md) == []

def test_filter_blocks_by_min():
    blocks = parse_available_blocks(SAMPLE)
    assert filter_blocks(blocks, 90) == [
        {"start": "08:00", "end": "10:00", "duration_min": 120},
        {"start": "13:30", "end": "15:00", "duration_min": 90},
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/main-drive/ai-PA/letta && PYTHONPATH="$PWD" ~/.letta/pa-tools-venv/bin/python -m pytest daily_briefing/tests/test_availability.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'daily_briefing.availability'`

- [ ] **Step 3: Write minimal implementation**

```python
# letta/daily_briefing/availability.py
"""Pure parser: rendered daily-briefing markdown -> free blocks (24h). No I/O."""
import re
from typing import Dict, List

# Matches: "• **8:00 AM–10:00 AM** - (2h)"  (en-dash between the times)
_BULLET_RE = re.compile(r"^[•\-\*]\s*\*\*(.+?)\*\*\s*-\s*\(.+?\)\s*$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*(AM|PM)$")


def _to_minutes_12h(s: str) -> int:
    """'8:00 AM' -> 480, '1:30 PM' -> 810, '12:00 AM' -> 0, '12:00 PM' -> 720."""
    m = _TIME_RE.match(s.strip().upper().replace(".", ""))
    if not m:
        raise ValueError(f"bad 12h time: {s!r}")
    h, mm, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap == "AM":
        h = 0 if h == 12 else h
    else:
        h = 12 if h == 12 else h + 12
    return h * 60 + mm


def _fmt_hhmm(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def parse_available_blocks(markdown: str) -> List[Dict]:
    """Return [{'start':'HH:MM','end':'HH:MM','duration_min':int}, ...] in 24h.

    Empty list if the day is fully booked / has no bullets. Duration is computed
    from start/end (the rendered '(2h)' string is ignored for robustness).
    """
    blocks: List[Dict] = []
    for line in markdown.splitlines():
        m = _BULLET_RE.match(line.strip())
        if not m:
            continue
        inside = m.group(1)
        parts = re.split(r"\s*–\s*", inside)  # split on en-dash U+2013
        if len(parts) != 2:
            continue
        try:
            start, end = _to_minutes_12h(parts[0]), _to_minutes_12h(parts[1])
        except ValueError:
            continue
        if end <= start:
            continue
        blocks.append({"start": _fmt_hhmm(start), "end": _fmt_hhmm(end),
                       "duration_min": end - start})
    return blocks


def filter_blocks(blocks: List[Dict], min_minutes: int) -> List[Dict]:
    """Keep only blocks at least `min_minutes` long."""
    return [b for b in blocks if b["duration_min"] >= min_minutes]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Volumes/main-drive/ai-PA/letta && PYTHONPATH="$PWD" ~/.letta/pa-tools-venv/bin/python -m pytest daily_briefing/tests/test_availability.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add letta/daily_briefing/availability.py letta/daily_briefing/tests/test_availability.py
git commit -m "feat(lookahead): pure parser for available-time blocks"
```

---

### Task 2: Lookahead pre-write loop

**Files:**
- Create: `letta/daily_briefing/lookahead_prewrite.py`
- Test: `letta/daily_briefing/tests/test_lookahead_prewrite.py`

- [ ] **Step 1: Write the failing test**

```python
# letta/daily_briefing/tests/test_lookahead_prewrite.py
from datetime import date
import daily_briefing.lookahead_prewrite as lp

def test_lookahead_dates_weekdays_only():
    # 2026-06-11 is a Thursday. D+2..D+13, weekdays only.
    got = lp.lookahead_dates(date(2026, 6, 11))
    assert date(2026, 6, 13) not in got  # Sat
    assert date(2026, 6, 14) not in got  # Sun
    assert date(2026, 6, 15) in got      # Mon
    assert got[0] == date(2026, 6, 15)   # first weekday at/after D+2
    assert all(d.weekday() < 5 for d in got)

def test_lookahead_dates_includes_weekends_when_disabled():
    got = lp.lookahead_dates(date(2026, 6, 11), weekdays_only=False)
    assert date(2026, 6, 13) in got
    assert len(got) == 12  # D+2..D+13 inclusive

def test_prewrite_aggregates_ok_and_fail(monkeypatch):
    calls = []
    def fake_tool(target_date=None, **kw):
        calls.append(target_date)
        if target_date == "2026-06-16":
            return {"status": "error", "error_message": "boom", "signal_written": False}
        return {"status": "ok", "signal_written": True}
    monkeypatch.setattr(lp, "generate_daily_briefing", fake_tool)
    results = lp.prewrite_lookahead(today=date(2026, 6, 11))
    by_date = {r["date"]: r for r in results}
    assert by_date["2026-06-15"]["ok"] is True
    assert by_date["2026-06-16"]["ok"] is False
    assert by_date["2026-06-16"]["error"] == "boom"
    assert "2026-06-15" in calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/main-drive/ai-PA/letta && PYTHONPATH="$PWD" ~/.letta/pa-tools-venv/bin/python -m pytest daily_briefing/tests/test_lookahead_prewrite.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'daily_briefing.lookahead_prewrite'`

- [ ] **Step 3: Write minimal implementation**

```python
# letta/daily_briefing/lookahead_prewrite.py
"""Stage-1 lookahead pre-write, pure-Python edition.

Loops generate_daily_briefing(target_date) over D+2..D+13 weekdays. The tool
itself upserts signals/{date}/schedule.md, so this is just date math + a loop +
an aggregate failure health signal. Run once daily at ~5 AM ET via launchd.
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from daily_briefing.generate_daily_briefing import generate_daily_briefing

ET = ZoneInfo("America/New_York")
DEFAULT_OFFSETS = range(2, 14)  # D+2 .. D+13 (today/tomorrow owned by the refresher)
HEALTH_PATH_TMPL = "signals/{date}/schedule-lookahead-health.md"


def lookahead_dates(today, offsets=DEFAULT_OFFSETS, weekdays_only=True):
    """Return the list of target dates to pre-write."""
    out = []
    for off in offsets:
        d = today + timedelta(days=off)
        if weekdays_only and d.weekday() >= 5:
            continue
        out.append(d)
    return out


def prewrite_lookahead(today=None, weekdays_only=True):
    """Generate each lookahead day. Returns a list of per-day result dicts."""
    if today is None:
        today = datetime.now(ET).date()
    results = []
    for d in lookahead_dates(today, weekdays_only=weekdays_only):
        ds = d.strftime("%Y-%m-%d")
        try:
            r = generate_daily_briefing(target_date=ds)
            ok = r.get("status") == "ok" and bool(r.get("signal_written"))
            results.append({"date": ds, "ok": ok,
                            "error": None if ok else (r.get("error_message") or "signal not written")})
        except Exception as e:  # fail loud per-day, keep going
            results.append({"date": ds, "ok": False, "error": str(e)})
    return results


def _write_health_signal(today, failures):
    """Upsert one aggregate health signal listing failed days (urgent)."""
    token = os.environ.get("GITEA_MEMFS_TOKEN", "")
    base = os.environ.get("GITEA_BASE_URL", "http://127.0.0.1:3030").rstrip("/")
    if not token:
        return
    path = HEALTH_PATH_TMPL.format(date=today.strftime("%Y-%m-%d"))
    now_iso = datetime.now(ET).isoformat()
    lines = [
        "---",
        "description: Schedule lookahead pre-write failures",
        "source: schedule-lookahead",
        "attention_level: urgent",
        "mentioned_entities: []",
        f"date: {today.strftime('%Y-%m-%d')}",
        f"last_refreshed_at: {now_iso}",
        "---",
        "",
        f"Lookahead pre-write failed for {len(failures)} day(s):",
        "",
    ]
    lines += [f"- {f['date']}: {f['error']}" for f in failures]
    content = "\n".join(lines) + "\n"
    url = f"{base}/api/v1/repos/agents/agents-canonical/contents/{path}"
    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}
    sha = None
    try:
        req = urllib.request.Request(url + "?ref=main", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            sha = json.loads(r.read().decode("utf-8")).get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    body = {"branch": "main",
            "content": base64.b64encode(content.encode()).decode("ascii"),
            "message": f"signals: lookahead health {today} ({len(failures)} failed)"}
    if sha:
        body["sha"] = sha
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers=headers, method="PUT" if sha else "POST")
    urllib.request.urlopen(req, timeout=15)


def main():
    today = datetime.now(ET).date()
    results = prewrite_lookahead(today=today)
    ok = [r for r in results if r["ok"]]
    failures = [r for r in results if not r["ok"]]
    for r in results:
        print(f"  {'ok  ' if r['ok'] else 'FAIL'} {r['date']}" + ("" if r["ok"] else f"  {r['error']}"))
    print(f"\nLookahead: {len(ok)}/{len(results)} pre-written")
    if failures:
        try:
            _write_health_signal(today, failures)
        except Exception as e:
            print(f"  ! could not write health signal: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Volumes/main-drive/ai-PA/letta && PYTHONPATH="$PWD" ~/.letta/pa-tools-venv/bin/python -m pytest daily_briefing/tests/test_lookahead_prewrite.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add letta/daily_briefing/lookahead_prewrite.py letta/daily_briefing/tests/test_lookahead_prewrite.py
git commit -m "feat(lookahead): pure-Python D+2..D+13 pre-write loop + health signal"
```

---

### Task 3: Cross-tab query (with lazy refresh)

**Files:**
- Create: `letta/daily_briefing/query_available_time.py`
- Test: `letta/daily_briefing/tests/test_query_available_time.py`

- [ ] **Step 1: Write the failing test**

```python
# letta/daily_briefing/tests/test_query_available_time.py
from datetime import date
import daily_briefing.query_available_time as q

CANNED = {
    "2026-06-15": "**Available Time Remaining** — 2h remaining\n• **8:00 AM–10:00 AM** - (2h)\n",
    "2026-06-16": "**Available Time Remaining** — 0 min remaining\n*No available time blocks*\n",
}

def test_query_filters_and_skips_empty(monkeypatch):
    monkeypatch.setattr(q, "_fetch_schedule_md",
                        lambda d: (CANNED.get(d), "2099-01-01T00:00:00-05:00"))  # never stale
    out = q.query(date(2026, 6, 15), date(2026, 6, 16), min_minutes=60,
                  weekdays_only=True, allow_refresh=False)
    assert len(out) == 1
    assert out[0]["date"] == "2026-06-15"
    assert out[0]["blocks"][0]["duration_min"] == 120

def test_query_skips_weekends(monkeypatch):
    monkeypatch.setattr(q, "_fetch_schedule_md",
                        lambda d: ("**Available Time Remaining** — 8h remaining\n• **9:00 AM–5:00 PM** - (8h)\n",
                                   "2099-01-01T00:00:00-05:00"))
    # 2026-06-13 = Sat, 2026-06-14 = Sun
    out = q.query(date(2026, 6, 13), date(2026, 6, 14), min_minutes=30, allow_refresh=False)
    assert out == []

def test_lazy_refresh_on_missing(monkeypatch):
    state = {"generated": False}
    def fake_fetch(d):
        if not state["generated"]:
            return (None, None)            # first call: missing
        return ("**Available Time Remaining** — 1h remaining\n• **4:00 PM–5:00 PM** - (1h)\n",
                "2099-01-01T00:00:00-05:00")
    def fake_gen(target_date=None, **kw):
        state["generated"] = True
        return {"status": "ok", "signal_written": True}
    monkeypatch.setattr(q, "_fetch_schedule_md", fake_fetch)
    monkeypatch.setattr(q, "generate_daily_briefing", fake_gen)
    blocks = q.get_day_blocks("2026-06-15", allow_refresh=True)
    assert state["generated"] is True
    assert blocks == [{"start": "16:00", "end": "17:00", "duration_min": 60}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/main-drive/ai-PA/letta && PYTHONPATH="$PWD" ~/.letta/pa-tools-venv/bin/python -m pytest daily_briefing/tests/test_query_available_time.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'daily_briefing.query_available_time'`

- [ ] **Step 3: Write minimal implementation**

```python
# letta/daily_briefing/query_available_time.py
"""Cross-tab free-time query over pre-written signals/{date}/schedule.md cells.

Usage:
  query_available_time.py --start 2026-06-15 --end 2026-06-26 --min 120 [--include-weekends] [--json]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

from daily_briefing.availability import filter_blocks, parse_available_blocks
from daily_briefing.generate_daily_briefing import generate_daily_briefing

STALE_HOURS = 24


def _gitea_base():
    return os.environ.get("GITEA_BASE_URL", "http://127.0.0.1:3030").rstrip("/")


def _fetch_schedule_md(date_str):
    """Return (markdown, last_refreshed_at_iso) or (None, None) on 404."""
    base = _gitea_base()
    token = os.environ.get("GITEA_MEMFS_TOKEN", "")
    url = f"{base}/api/v1/repos/agents/agents-canonical/raw/signals/{date_str}/schedule.md"
    req = urllib.request.Request(url, headers={"Authorization": f"token {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            text = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        raise
    refreshed = None
    in_fm = False
    for line in text.splitlines():
        if line.strip() == "---":
            if in_fm:
                break
            in_fm = True
            continue
        if in_fm and line.startswith("last_refreshed_at:"):
            refreshed = line.split(":", 1)[1].strip()
    return text, refreshed


def _is_stale(refreshed_iso):
    if not refreshed_iso:
        return True
    try:
        dt = datetime.fromisoformat(refreshed_iso)
    except ValueError:
        return True
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    return (now - dt).total_seconds() > STALE_HOURS * 3600


def get_day_blocks(date_str, allow_refresh=True):
    """Free blocks for one day; regenerate the cell if missing/stale."""
    md, refreshed = _fetch_schedule_md(date_str)
    if allow_refresh and (md is None or _is_stale(refreshed)):
        generate_daily_briefing(target_date=date_str)
        md, refreshed = _fetch_schedule_md(date_str)
    if md is None:
        return []
    return parse_available_blocks(md)


def query(start, end, min_minutes=30, weekdays_only=True, allow_refresh=True):
    """Return [{'date','weekday','blocks':[...]}] for days with qualifying free time."""
    out = []
    d = start
    while d <= end:
        if not (weekdays_only and d.weekday() >= 5):
            blocks = filter_blocks(get_day_blocks(d.isoformat(), allow_refresh), min_minutes)
            if blocks:
                out.append({"date": d.isoformat(), "weekday": d.strftime("%a"), "blocks": blocks})
        d += timedelta(days=1)
    return out


def _to_12h(hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    ap = "AM" if h < 12 else "PM"
    dh = h % 12 or 12
    return f"{dh}:{m:02d} {ap}"


def _render_text(rows, min_minutes):
    if not rows:
        return f"No open blocks ≥ {min_minutes} min in range."
    lines = []
    for r in rows:
        slots = ", ".join(f"{_to_12h(b['start'])}–{_to_12h(b['end'])} ({b['duration_min']} min)"
                          for b in r["blocks"])
        lines.append(f"{r['weekday']} {r['date']}: {slots}")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description="Query open work-time across a date range.")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--min", type=int, default=30, help="minimum block minutes (default 30)")
    p.add_argument("--include-weekends", action="store_true")
    p.add_argument("--no-refresh", action="store_true", help="do not regenerate missing/stale days")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    start = date.fromisoformat(a.start)
    end = date.fromisoformat(a.end)
    rows = query(start, end, min_minutes=a.min,
                 weekdays_only=not a.include_weekends, allow_refresh=not a.no_refresh)
    print(json.dumps(rows, indent=2) if a.json else _render_text(rows, a.min))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Volumes/main-drive/ai-PA/letta && PYTHONPATH="$PWD" ~/.letta/pa-tools-venv/bin/python -m pytest daily_briefing/tests/test_query_available_time.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full suite to confirm nothing regressed**

Run: `cd /Volumes/main-drive/ai-PA/letta && PYTHONPATH="$PWD" ~/.letta/pa-tools-venv/bin/python -m pytest daily_briefing/tests/ -q`
Expected: PASS (all prior + new; ~20 passed)

- [ ] **Step 6: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add letta/daily_briefing/query_available_time.py letta/daily_briefing/tests/test_query_available_time.py
git commit -m "feat(lookahead): cross-tab free-time query with lazy day refresh"
```

---

### Task 4: launchd wrapper + plist for the daily pre-write

**Files:**
- Create: `letta/daily_briefing/lookahead-prewrite.sh`
- Create: `deployment/launchd/com.ai-pa.schedule-lookahead.plist`

- [ ] **Step 1: Write the wrapper script**

```bash
# letta/daily_briefing/lookahead-prewrite.sh
#!/usr/bin/env bash
# Host launchd entry for the daily schedule lookahead pre-write (D+2..D+13).
# Sources pa-tools env, runs the pinned-venv module. Exits non-zero on any
# per-day failure (the module also writes an urgent health signal).
set -euo pipefail

ENV_FILE="/Users/dorseyhomeserver/.letta/pa-tools.env"
VENV_PY="/Users/dorseyhomeserver/.letta/pa-tools-venv/bin/python"
REPO="/Volumes/main-drive/ai-PA"

set -a; . "$ENV_FILE"; set +a
export PATH="/Users/dorseyhomeserver/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"
export PYTHONPATH="${REPO}/letta/pulse-tools:${REPO}/letta"

exec "$VENV_PY" -m daily_briefing.lookahead_prewrite
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x /Volumes/main-drive/ai-PA/letta/daily_briefing/lookahead-prewrite.sh`
Expected: no output

- [ ] **Step 3: Write the plist (daily 5:00 AM ET)**

```xml
<!-- deployment/launchd/com.ai-pa.schedule-lookahead.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ai-pa.schedule-lookahead</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Volumes/main-drive/ai-PA/letta/daily_briefing/lookahead-prewrite.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>5</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>RunAtLoad</key>
    <false/>
    <key>ProcessType</key>
    <string>Background</string>
    <key>StandardOutPath</key>
    <string>/Users/dorseyhomeserver/Library/Logs/schedule-lookahead/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/dorseyhomeserver/Library/Logs/schedule-lookahead/stderr.log</string>
    <key>WorkingDirectory</key>
    <string>/Volumes/main-drive/ai-PA</string>
</dict>
</plist>
```

- [ ] **Step 4: Commit (do not load yet — loading happens in Task 7 after a manual dry run)**

```bash
cd /Volumes/main-drive/ai-PA
chmod +x letta/daily_briefing/lookahead-prewrite.sh
git add letta/daily_briefing/lookahead-prewrite.sh deployment/launchd/com.ai-pa.schedule-lookahead.plist
git commit -m "feat(lookahead): launchd wrapper + plist (daily 5 AM pre-write)"
```

---

### Task 5: Cleanup script for stale failure markers

**Files:**
- Create: `scripts/cleanup-lookahead-markers.py`

- [ ] **Step 1: Write the cleanup script**

```python
#!/usr/bin/env python3
# scripts/cleanup-lookahead-markers.py
"""Delete stale failure-marker files from the abandoned lookahead:
   signals/<date>/mc-lookahead-<date>.md
   signals/<date>/mc-daily-briefing-lookahead-<date>.md
Idempotent. Use --dry-run to preview. Env: GITEA_BASE_URL, GITEA_MEMFS_TOKEN.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("GITEA_BASE_URL", "http://127.0.0.1:3030").rstrip("/")
TOKEN = os.environ["GITEA_MEMFS_TOKEN"]
REPO = f"{BASE}/api/v1/repos/agents/agents-canonical"
MARKER_RE = re.compile(r"^(mc-lookahead-|mc-daily-briefing-lookahead-)\d{4}-\d{2}-\d{2}\.md$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{REPO}/{path}", data=data, method=method,
                                 headers={"Authorization": f"token {TOKEN}",
                                          "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=20)


def main():
    dry = "--dry-run" in sys.argv
    dates = [e["name"] for e in json.load(_req("GET", "contents/signals"))
             if e["type"] == "dir" and DATE_RE.match(e["name"])]
    deleted = 0
    for d in dates:
        try:
            entries = json.load(_req("GET", f"contents/signals/{d}"))
        except urllib.error.HTTPError:
            continue
        for e in entries:
            if e["type"] == "file" and MARKER_RE.match(e["name"]):
                path = f"signals/{d}/{e['name']}"
                if dry:
                    print(f"  would delete {path}")
                else:
                    _req("DELETE", f"contents/{path}",
                         {"branch": "main", "sha": e["sha"],
                          "message": f"cleanup: remove stale lookahead marker {e['name']}"})
                    print(f"  deleted {path}")
                deleted += 1
    print(f"\n{'Would delete' if dry else 'Deleted'} {deleted} marker file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Dry-run to confirm it only targets markers**

Run:
```bash
cd /Volumes/main-drive/ai-PA
set -a; . ~/.letta/pa-tools.env; set +a
python3 scripts/cleanup-lookahead-markers.py --dry-run
```
Expected: lists only `mc-lookahead-*.md` / `mc-daily-briefing-lookahead-*.md` paths (e.g. for 2026-06-12), and a count. NO `schedule.md` lines.

- [ ] **Step 3: Execute the cleanup**

Run:
```bash
cd /Volumes/main-drive/ai-PA
set -a; . ~/.letta/pa-tools.env; set +a
python3 scripts/cleanup-lookahead-markers.py
```
Expected: `deleted signals/.../mc-...md` lines + a final count ≥ 1.

- [ ] **Step 4: Verify markers are gone**

Run: `curl -s -H "Authorization: token $GITEA_MEMFS_TOKEN" "$GITEA_BASE_URL/api/v1/repos/agents/agents-canonical/contents/signals/2026-06-12" | python3 -c "import sys,json;print([e['name'] for e in json.load(sys.stdin)])"`
Expected: list contains `schedule.md` but NOT any `mc-lookahead*`/`mc-daily-briefing-lookahead*`.

- [ ] **Step 5: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add scripts/cleanup-lookahead-markers.py
git commit -m "chore(lookahead): script to purge stale abandoned-lookahead failure markers"
```

---

### Task 6: MC query wrapper + recipe note

**Files:**
- Create: `letta/daily_briefing/query-available-time.sh`
- Modify: `~/.letta/lc-local-backend/memfs/agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d/memory/system/mc_cli_recipes.md` (MC's Gitea-backed memfs)

- [ ] **Step 1: Write the query wrapper (so MC calls one entrypoint with env loaded)**

```bash
# letta/daily_briefing/query-available-time.sh
#!/usr/bin/env bash
# Entrypoint for MC: query open work-time across a date range. Loads pa-tools
# env (Gitea token + gws creds for lazy refresh) and forwards all args.
set -euo pipefail
ENV_FILE="/Users/dorseyhomeserver/.letta/pa-tools.env"
VENV_PY="/Users/dorseyhomeserver/.letta/pa-tools-venv/bin/python"
REPO="/Volumes/main-drive/ai-PA"
set -a; . "$ENV_FILE"; set +a
export PATH="/Users/dorseyhomeserver/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"
export PYTHONPATH="${REPO}/letta/pulse-tools:${REPO}/letta"
exec "$VENV_PY" -m daily_briefing.query_available_time "$@"
```

- [ ] **Step 2: Make executable + smoke-test the wrapper**

Run:
```bash
chmod +x /Volumes/main-drive/ai-PA/letta/daily_briefing/query-available-time.sh
/Volumes/main-drive/ai-PA/letta/daily_briefing/query-available-time.sh --start 2026-06-15 --end 2026-06-19 --min 60 --no-refresh
```
Expected: either day/slot lines, or `No open blocks ≥ 60 min in range.` (depending on what's pre-written) — and a zero exit code. No traceback.

- [ ] **Step 3: Add a recipe section to MC's memfs (read the file first)**

Read `~/.letta/lc-local-backend/memfs/agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d/memory/system/mc_cli_recipes.md`, then insert after the "Daily kickoff" block:

```markdown
### Free-time lookahead ("when am I free", "do I have 2h next Tuesday")

Open work-time across a date range, read from the pre-written `signals/<date>/schedule.md`
cells (refreshed daily at 5 AM ET; missing/stale days regenerate on demand).

```bash
# All open blocks >= 90 min over the next two weeks (weekdays):
/Volumes/main-drive/ai-PA/letta/daily_briefing/query-available-time.sh \
  --start 2026-06-15 --end 2026-06-26 --min 90

# A single day, JSON:
/Volumes/main-drive/ai-PA/letta/daily_briefing/query-available-time.sh \
  --start 2026-06-16 --end 2026-06-16 --min 30 --json
```
Flags: `--min <minutes>` (default 30), `--include-weekends`, `--no-refresh`, `--json`.
```

- [ ] **Step 4: Commit the wrapper (repo) and push the recipe (memfs Gitea)**

```bash
cd /Volumes/main-drive/ai-PA
git add letta/daily_briefing/query-available-time.sh
git commit -m "feat(lookahead): MC query wrapper entrypoint"

cd ~/.letta/lc-local-backend/memfs/agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d/memory
git pull --rebase --autostash
git add system/mc_cli_recipes.md
git commit -m "recipe: free-time lookahead query"
git push
```
Expected: repo commit + a successful `git push` to the Gitea memfs remote.

---

### Task 7: Deploy + end-to-end verification

**Files:** none (operational)

- [ ] **Step 1: Manual dry run of the real pre-write (writes real cells)**

Run:
```bash
cd /Volumes/main-drive/ai-PA
set -a; . ~/.letta/pa-tools.env; set +a
export PYTHONPATH="$PWD/letta/pulse-tools:$PWD/letta"
~/.letta/pa-tools-venv/bin/python -m daily_briefing.lookahead_prewrite
```
Expected: `ok   <date>` lines for each lookahead weekday, then `Lookahead: N/N pre-written` and exit 0.

- [ ] **Step 2: Verify dated cells now exist for a far day**

Run:
```bash
D=$(~/.letta/pa-tools-venv/bin/python -c "from datetime import date,timedelta; print((date(2026,6,11)+timedelta(days=7)).isoformat())")
curl -s -H "Authorization: token $GITEA_MEMFS_TOKEN" "$GITEA_BASE_URL/api/v1/repos/agents/agents-canonical/raw/signals/$D/schedule.md" | sed -n '1,12p'
```
Expected: frontmatter with `date: <that date>` + a `**...'s Schedule**` header.

- [ ] **Step 3: End-to-end query against the freshly pre-written window**

Run:
```bash
/Volumes/main-drive/ai-PA/letta/daily_briefing/query-available-time.sh \
  --start 2026-06-15 --end 2026-06-26 --min 60
```
Expected: one line per weekday with qualifying free blocks (e.g. `Mon 2026-06-15: 8:00 AM–10:00 AM (120 min), ...`). No traceback, exit 0.

- [ ] **Step 4: Install + load the launchd job**

Run:
```bash
mkdir -p ~/Library/Logs/schedule-lookahead
cp /Volumes/main-drive/ai-PA/deployment/launchd/com.ai-pa.schedule-lookahead.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.ai-pa.schedule-lookahead.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.ai-pa.schedule-lookahead.plist
launchctl list | grep com.ai-pa.schedule-lookahead
```
Expected: a line showing the label loaded (status `-` or `0`).

- [ ] **Step 5: Force one launchd run + check its log**

Run:
```bash
launchctl start com.ai-pa.schedule-lookahead
sleep 60
tail -n 20 ~/Library/Logs/schedule-lookahead/stdout.log
```
Expected: the `Lookahead: N/N pre-written` summary; empty/clean stderr.log.

- [ ] **Step 6: Update memory**

Append to `/Users/dorseyhomeserver/.claude/projects/-Volumes-main-drive-ai-PA/memory/project_current_briefing_materialized_view.md` a note that the lookahead is live: daily 5 AM `com.ai-pa.schedule-lookahead` pre-writes D+2..D+13 weekday `signals/<date>/schedule.md` via pure-Python `lookahead_prewrite`; query via `query-available-time.sh`; lazy-refresh on missing/stale; stale `mc-lookahead-*` markers purged. Add a one-line pointer in `MEMORY.md`.

- [ ] **Step 7: Final commit (any doc/memory changes tracked in-repo)**

```bash
cd /Volumes/main-drive/ai-PA
git add docs/plans/2026-06-11-schedule-lookahead-resurrection-plan.md
git commit -m "docs(lookahead): mark resurrection plan complete"
```

---

## Notes / decisions baked in
- **Weekdays-only, D+2…D+13** (decisions #1, #2). Today + tomorrow stay owned by the 15-min `current-briefing-refresh` job.
- **Cross-tab parses rendered bullets** (decision #3) via the pure `availability` module — frontmatter `free_blocks` format deferred.
- **One aggregate health signal** on failure (decision #4), not per-day markers.
- **Lazy refresh** in the query tool regenerates missing/stale days (decision #5).
- **Cleanup** of the abandoned `mc-lookahead-*` markers (Task 5).
- Reuses `generate_daily_briefing` as-is — the deterministic builder Stage 2.A wanted is already here.
