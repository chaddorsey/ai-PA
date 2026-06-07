# Current Daily Briefing — Materialized-View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "What's my daily briefing?" return the correct-for-the-moment schedule instantly — read from a single pre-materialized `current` cell that a host-native job keeps fresh (today during the workday; the next workday after 6 PM ET or on weekends) — with time-remaining computed precisely at read time, and with the silent-success failure mode structurally eliminated.

**Architecture:** A pure renderer (`generate_daily_briefing`, date in → briefing out) is driven by a thin host-side **refresher** that owns the "which day is current" policy. A launchd job runs the refresher every 15 min via the pinned venv (no Docker round-trip, no LLM in the loop → no silent success). The refresher writes a dated archive (`signals/{date}/schedule.md`, already produced by the tool) **and** a date-less cell (`signals/current/schedule.md`). The reader script points at `current` and recomputes time-remaining at read time when the cell is today's. A data-only freshness monitor watches the cell's age.

**Tech Stack:** Python 3.13 (pinned `~/.letta/pa-tools-venv`), bash + curl reader, Gitea HTTP API (agents-canonical repo), launchd, the scheduler-service (`:8087`) for the monitor only.

---

## Background / invariants (read before starting)

- **Tool:** `letta/daily_briefing/generate_daily_briefing.py`. Signature: `generate_daily_briefing(calendar_id=None, timezone=None, target_date=None, include_troop_meetings=None) -> Dict`. Returns `status`, `briefing` (the rendered markdown body, includes the `**Schedule JSON**` line the reader needs), `signal_written`, `signal_path`, `target_date`, etc. It already writes the dated canonical signal `signals/{target_date}/schedule.md` (with frontmatter incl. `date: {target_date}`).
- **Runner context (validated):** the tool runs under `~/.letta/pa-tools-venv/bin/python` via `letta/pulse-tools/_ext_run.py`, with env from `~/.letta/pa-tools.env` (`GITEA_BASE_URL=http://localhost:3030`, `GITEA_MEMFS_TOKEN`, `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`, `MC_AGENT_ID`, `LETTA_BASE_URL`) and `PATH` prepended with `~/bin:/opt/homebrew/bin:/usr/local/bin` (so `gws` resolves).
- **PYTHONPATH** for importing the tool as a module: `/Volumes/main-drive/ai-PA/letta` (module `daily_briefing.generate_daily_briefing`).
- **Rollover rule:** weekday before 18:00 ET → today; otherwise the next workday strictly after today (Fri/Sat/Sun → Monday).
- **Reader:** `letta-code/.scripts/schedule` (bash). Currently reads `signals/{today}/schedule.md`; recomputes Available-Time via `letta-code/.scripts/time-remaining.py --format=md` from the embedded `**Schedule JSON**` line.
- **The 3 Docker crons to disable** (scheduler `:8087`): `933b620f-9cb1-47f8-b519-7ccedf1603ab`, `f732d44c-50d1-4fd2-88b4-6102cece4fa3`, `a683f7ef-bf03-4a4b-a607-fb52399f43a4`. Pre-flip snapshot already at `docs/runbooks/rollback-snapshots/2026-06-07-schedule-briefing-crons-preflip.json`.
- **Secrets discipline:** the committed launchd plist must NOT contain secrets. Env comes from `~/.letta/pa-tools.env` via a wrapper script.
- **Branch:** `fix/pulse-analytics-briefing-local-2026-06-07`.

## File structure

| Path | Action | Responsibility |
|---|---|---|
| `letta/daily_briefing/refresh_current.py` | Create | `current_briefing_date()` helper + `refresh_current_briefing()` (compute day → call pure tool → write `current` cell). CLI entry, nonzero exit on failure. |
| `letta/daily_briefing/tests/test_current_briefing_date.py` | Create | Unit tests for the rollover rule (pure, injected `now_et`). |
| `letta/daily_briefing/generate_daily_briefing.py` | Modify (~780–959) | Remove dead MC-memfs `schedule/today.md` write; keep dated signal write; stabilize return shape. |
| `letta-code/.scripts/schedule` | Modify | Read `signals/current`; date-aware branch (today → recompute remaining; future → verbatim body). |
| `letta/daily_briefing/refresh-current-briefing.sh` | Create | launchd wrapper: source `pa-tools.env`, set PATH, hour-window guard, run venv refresher. |
| `deployment/launchd/com.ai-pa.current-briefing-refresh.plist` | Create | launchd job (`StartInterval` 900) → wrapper. No secrets. |
| `scheduler-service` job (via API) | Create | Freshness monitor: data-only check of `signals/current/schedule.md` age. |
| `docs/runbooks/2026-06-07-current-briefing-refresh-rollback.md` | Create | Rollback (re-enable Docker crons, remove launchd job, repoint reader). |

---

## Task 1: `current_briefing_date()` rollover helper

**Files:**
- Create: `letta/daily_briefing/refresh_current.py`
- Create: `letta/daily_briefing/tests/__init__.py` (empty)
- Test: `letta/daily_briefing/tests/test_current_briefing_date.py`

- [ ] **Step 1: Write the failing test**

```python
# letta/daily_briefing/tests/test_current_briefing_date.py
from datetime import datetime, date
import pytz
from daily_briefing.refresh_current import current_briefing_date

ET = pytz.timezone("America/New_York")

def _et(y, m, d, hh, mm=0):
    return ET.localize(datetime(y, m, d, hh, mm))

def test_weekday_before_6pm_is_today():
    # Tue 2026-06-09 09:00 -> today
    assert current_briefing_date(_et(2026, 6, 9, 9)) == date(2026, 6, 9)

def test_weekday_1759_is_today():
    assert current_briefing_date(_et(2026, 6, 9, 17, 59)) == date(2026, 6, 9)

def test_weekday_evening_is_tomorrow():
    # Tue 18:00 -> Wed
    assert current_briefing_date(_et(2026, 6, 9, 18)) == date(2026, 6, 10)

def test_friday_evening_is_monday():
    # Fri 2026-06-12 18:30 -> Mon 2026-06-15
    assert current_briefing_date(_et(2026, 6, 12, 18, 30)) == date(2026, 6, 15)

def test_saturday_is_monday():
    # Sat 2026-06-13 10:00 -> Mon 2026-06-15
    assert current_briefing_date(_et(2026, 6, 13, 10)) == date(2026, 6, 15)

def test_sunday_evening_is_monday():
    # Sun 2026-06-14 23:00 -> Mon 2026-06-15
    assert current_briefing_date(_et(2026, 6, 14, 23)) == date(2026, 6, 15)

def test_monday_early_is_monday():
    # Mon 2026-06-15 06:00 -> Mon
    assert current_briefing_date(_et(2026, 6, 15, 6)) == date(2026, 6, 15)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/main-drive/ai-PA && PYTHONPATH=letta ~/.letta/pa-tools-venv/bin/python -m pytest letta/daily_briefing/tests/test_current_briefing_date.py -v`
Expected: FAIL (`ModuleNotFoundError: daily_briefing.refresh_current` or `ImportError: current_briefing_date`).

- [ ] **Step 3: Write minimal implementation**

```python
# letta/daily_briefing/refresh_current.py
"""Refresher for the 'current' daily-briefing materialized cell.

Owns the 'which day is current' policy (rollover), calls the pure
generate_daily_briefing renderer, and writes the date-less
signals/current/schedule.md cell (plus the dated archive the tool already
writes). Runs host-side in the pinned pa-tools venv via launchd. CLI exits
non-zero on failure so the scheduler/launchd see a real failure (no silent
success).
"""
from datetime import datetime, date, timedelta


def current_briefing_date(now_et: datetime) -> date:
    """The schedule date that is 'current' for a given Eastern-time moment.

    Weekday before 18:00 ET -> today. Otherwise (evening on a weekday, or any
    time on a weekend) -> the next workday strictly after today
    (Fri/Sat/Sun -> Monday).
    """
    today = now_et.date()
    if today.weekday() < 5 and now_et.hour < 18:  # Mon..Fri before 6pm
        return today
    d = today + timedelta(days=1)
    while d.weekday() >= 5:  # skip Sat(5)/Sun(6)
        d += timedelta(days=1)
    return d
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Volumes/main-drive/ai-PA && PYTHONPATH=letta ~/.letta/pa-tools-venv/bin/python -m pytest letta/daily_briefing/tests/test_current_briefing_date.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add letta/daily_briefing/refresh_current.py letta/daily_briefing/tests/__init__.py letta/daily_briefing/tests/test_current_briefing_date.py
git commit -m "feat(briefing): add current_briefing_date rollover helper + tests"
```

---

## Task 2: `refresh_current_briefing()` — render + write the `current` cell

**Files:**
- Modify: `letta/daily_briefing/refresh_current.py`
- Test: `letta/daily_briefing/tests/test_refresh_current.py`

The refresher computes the target date, calls the pure tool, then upserts the rendered body to the date-less cell `signals/current/schedule.md` with frontmatter carrying the cell's date. It returns a summary dict and, as a CLI, exits non-zero if the tool failed or the cell write failed.

- [ ] **Step 1: Write the failing test (cell-write logic, tool mocked)**

```python
# letta/daily_briefing/tests/test_refresh_current.py
import json
from datetime import datetime
import pytz
import daily_briefing.refresh_current as rc

ET = pytz.timezone("America/New_York")

def test_refresh_calls_tool_with_rollover_date_and_writes_cell(monkeypatch):
    calls = {}
    def fake_tool(target_date=None, **kw):
        calls["target_date"] = target_date
        return {"status": "ok",
                "briefing": "**Wednesday's Schedule**\n\n**Schedule JSON** (x): {\"work_end\":\"17:00\",\"busy_blocks\":[]}",
                "signal_written": True}
    def fake_put_cell(date_str, body):
        calls["cell_date"] = date_str
        calls["cell_body"] = body
        return "https://example/current"
    monkeypatch.setattr(rc, "generate_daily_briefing", fake_tool)
    monkeypatch.setattr(rc, "_put_current_cell", fake_put_cell)

    # Tue 18:00 ET -> rollover to Wed
    out = rc.refresh_current_briefing(now_et=ET.localize(datetime(2026, 6, 9, 18)))

    assert calls["target_date"] == "2026-06-10"
    assert calls["cell_date"] == "2026-06-10"
    assert "Schedule JSON" in calls["cell_body"]
    assert out["status"] == "ok"
    assert out["target_date"] == "2026-06-10"

def test_refresh_raises_on_tool_error(monkeypatch):
    monkeypatch.setattr(rc, "generate_daily_briefing",
                        lambda target_date=None, **kw: {"status": "error", "error_message": "boom"})
    monkeypatch.setattr(rc, "_put_current_cell", lambda *a, **k: "")
    try:
        rc.refresh_current_briefing(now_et=ET.localize(datetime(2026, 6, 9, 9)))
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "boom" in str(e)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/main-drive/ai-PA && PYTHONPATH=letta ~/.letta/pa-tools-venv/bin/python -m pytest letta/daily_briefing/tests/test_refresh_current.py -v`
Expected: FAIL (`AttributeError`/`ImportError` — symbols not defined).

- [ ] **Step 3: Implement refresher + cell upsert + CLI**

Append to `letta/daily_briefing/refresh_current.py`:

```python
import os
import sys
import json
import base64
import urllib.request
import urllib.error
import pytz

from daily_briefing.generate_daily_briefing import generate_daily_briefing

CURRENT_CELL_PATH = "signals/current/schedule.md"
CANONICAL_REPO = "agents/agents-canonical"
ACTIVE_HOURS = range(6, 23)  # 06:00..22:59 ET; outside this the launchd wrapper no-ops


def _gitea_base() -> str:
    return os.environ.get("GITEA_BASE_URL", "http://localhost:3030").rstrip("/")


def _put_current_cell(date_str: str, body: str) -> str:
    """Idempotent upsert of the date-less current cell. Returns html_url.

    Raises on failure so the caller can exit non-zero.
    """
    token = os.environ["GITEA_MEMFS_TOKEN"]  # KeyError -> loud failure
    base = _gitea_base()
    now_iso = datetime.now(pytz.timezone("America/New_York")).isoformat()
    frontmatter = (
        "---\n"
        f"description: Current daily schedule + available time (materialized cell)\n"
        "source: current-briefing-refresh\n"
        "attention_level: routine\n"
        "mentioned_entities: []\n"
        f"date: {date_str}\n"
        f"last_refreshed_at: {now_iso}\n"
        "---\n\n"
    )
    content = frontmatter + body + "\n"
    url = f"{base}/api/v1/repos/{CANONICAL_REPO}/contents/{CURRENT_CELL_PATH}"
    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}

    sha = None
    try:
        req = urllib.request.Request(url + "?ref=main", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            sha = json.loads(r.read().decode("utf-8")).get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise

    payload = {
        "branch": "main",
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "message": f"current: refresh -> {date_str} @ {now_iso}",
    }
    method = "PUT" if sha else "POST"
    if sha:
        payload["sha"] = sha
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method=method
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        resp = json.loads(r.read().decode("utf-8"))
    return (resp.get("content") or {}).get("html_url", "")


def refresh_current_briefing(now_et: datetime = None) -> dict:
    if now_et is None:
        now_et = datetime.now(pytz.timezone("America/New_York"))
    target = current_briefing_date(now_et)
    target_str = target.strftime("%Y-%m-%d")

    result = generate_daily_briefing(target_date=target_str)
    if result.get("status") != "ok":
        raise RuntimeError(
            f"generate_daily_briefing failed for {target_str}: "
            f"{result.get('error_message', 'unknown error')}"
        )
    body = result.get("briefing") or ""
    if "Schedule JSON" not in body:
        raise RuntimeError("rendered briefing missing Schedule JSON line; aborting cell write")

    html_url = _put_current_cell(target_str, body)
    return {
        "status": "ok",
        "target_date": target_str,
        "dated_signal_written": bool(result.get("signal_written")),
        "current_cell_url": html_url,
    }


def main() -> int:
    try:
        out = refresh_current_briefing()
        sys.stdout.write(json.dumps(out))
        return 0
    except Exception as e:  # loud failure: nonzero exit + stderr JSON
        import traceback
        sys.stderr.write(json.dumps({
            "status": "error",
            "error_message": str(e),
            "trace": traceback.format_exc()[-1500:],
        }))
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Volumes/main-drive/ai-PA && PYTHONPATH=letta ~/.letta/pa-tools-venv/bin/python -m pytest letta/daily_briefing/tests/ -v`
Expected: PASS (9 passed total).

- [ ] **Step 5: Live smoke test (writes the real current cell)**

Run:
```bash
cd /Volumes/main-drive/ai-PA
set -a; . ~/.letta/pa-tools.env; set +a
export PYTHONPATH="/Volumes/main-drive/ai-PA/letta/pulse-tools:/Volumes/main-drive/ai-PA/letta"
~/.letta/pa-tools-venv/bin/python -m daily_briefing.refresh_current; echo " exit=$?"
```
Expected: prints `{"status":"ok","target_date":"...","dated_signal_written":true,"current_cell_url":"..."}` and `exit=0`.

Then confirm the cell exists:
```bash
curl -fsSL -H "Authorization: token $GITEA_MEMFS_TOKEN" \
  "$GITEA_BASE_URL/api/v1/repos/agents/agents-canonical/raw/main/signals/current/schedule.md" | head -5
```
Expected: frontmatter with a `date:` line + the briefing header.

- [ ] **Step 6: Commit**

```bash
git add letta/daily_briefing/refresh_current.py letta/daily_briefing/tests/test_refresh_current.py
git commit -m "feat(briefing): refresh_current_briefing writes the date-less current cell"
```

---

## Task 3: Drop the dead MC-memfs `today.md` write from the tool

**Files:**
- Modify: `letta/daily_briefing/generate_daily_briefing.py` (the `# ========== MC MEMFS: schedule/today.md` block, ~line 780 through the line before `# ========== (removed) deprecated memory-block write ==========` at ~line 961)

`schedule/today.md` has zero readers (confirmed). The `current` cell replaces it. Remove the block and stabilize the three return keys it set (`mc_memfs_written`, `mc_memfs_path`, `mc_memfs_html_url`).

- [ ] **Step 1: Inspect exact boundaries**

Run: `grep -n "MC MEMFS: schedule/today.md\|(removed) deprecated memory-block write" letta/daily_briefing/generate_daily_briefing.py`
Expected: two line numbers (start of memfs block ~780; start of removed-block comment ~961). Delete everything from the memfs comment up to (not including) the removed-block comment.

- [ ] **Step 2: Replace the memfs block with a stub**

Replace the entire `# ========== MC MEMFS: schedule/today.md ... ` block with:

```python
        # ========== (removed) MC memfs schedule/today.md write ==========
        # today.md had zero readers; the materialized cell signals/current/schedule.md
        # (written by refresh_current.py) replaces it. Removed 2026-06-07.
        # See docs/plans/2026-06-07-current-briefing-materialized-view-plan.md.
        mc_memfs_written = False
        mc_memfs_path = None
        mc_memfs_html_url = None
```

- [ ] **Step 3: Verify the tool still imports and runs (dated signal only)**

Run:
```bash
cd /Volumes/main-drive/ai-PA
set -a; . ~/.letta/pa-tools.env; set +a
export PYTHONPATH="/Volumes/main-drive/ai-PA/letta/pulse-tools:/Volumes/main-drive/ai-PA/letta"
~/.letta/pa-tools-venv/bin/python letta/pulse-tools/_ext_run.py \
  daily_briefing.generate_daily_briefing generate_daily_briefing '{"target_date":"2026-06-05"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('status',d['status'],'signal',d['signal_written'],'mc_memfs_written',d['mc_memfs_written'])"
```
Expected: `status ok signal True mc_memfs_written False`.

- [ ] **Step 4: Confirm no remaining references to the removed variables outside the return**

Run: `grep -n "schedule/today.md\|last_err_m\|mc_memfs_url" letta/daily_briefing/generate_daily_briefing.py`
Expected: no matches (or only the new comment). If any remain inside the deleted region's former helpers, remove them.

- [ ] **Step 5: Commit**

```bash
git add letta/daily_briefing/generate_daily_briefing.py
git commit -m "refactor(briefing): drop dead MC-memfs today.md write (current cell replaces it)"
```

---

## Task 4: Repoint the reader to `current` with a date-aware branch

**Files:**
- Modify: `letta-code/.scripts/schedule`

Read `signals/current/schedule.md`. Extract the frontmatter `date:` BEFORE stripping frontmatter. If it equals today (ET): keep current behavior (strip baked Available-Time, recompute remaining from the Schedule JSON). If it's a future day: print the body verbatim (the tool's baked full-day Available-Time is the correct view; "remaining from now" is meaningless for a future date).

- [ ] **Step 1: Replace the source + add the branch**

Replace lines 36–75 (`TODAY=...` through end of file) with:

```bash
TODAY=$(TZ=America/New_York date +%Y-%m-%d)
SIGNAL_PATH="signals/current/schedule.md"
URL="${GITEA_BASE}/api/v1/repos/agents/agents-canonical/raw/main/${SIGNAL_PATH}"

# Fetch the materialized current cell
RAW=$(curl -fsSL "$URL" -H "Authorization: token ${GITEA_TOKEN}" 2>/dev/null) || {
    echo "(no schedule available — canonical ${SIGNAL_PATH} is missing or unreachable)" >&2
    exit 1
}

# The cell's target date from frontmatter (before we strip it)
CELL_DATE=$(echo "$RAW" | sed -n 's/^date:[[:space:]]*//p' | head -1)

# Strip YAML frontmatter (everything between the first two --- markers)
BODY=$(echo "$RAW" | awk '
    BEGIN { in_fm=0; past_fm=0 }
    /^---$/ {
        if (!past_fm) {
            if (!in_fm) { in_fm=1 } else { past_fm=1; in_fm=0 }
            next
        }
    }
    !in_fm && past_fm { print }
')

# Future-day cell (evening/weekend showing the next workday): "remaining from
# now" is meaningless, so print the body verbatim (full-day available time as
# rendered by the tool).
if [[ -n "$CELL_DATE" && "$CELL_DATE" != "$TODAY" ]]; then
    echo "$BODY"
    exit 0
fi

# Today's cell: print header + event list, then recompute Available Time
# Remaining anchored to the current moment (minute-precise at read time).
echo "$BODY" | awk '
    /^\*\*Available Time Remaining\*\*/ { exit }
    /^\*\*Schedule JSON\*\*/ { exit }
    { print }
'

JSON_LINE=$(echo "$BODY" | grep -m1 '^\*\*Schedule JSON\*\*' || true)
if [[ -n "$JSON_LINE" ]]; then
    JSON=$(echo "$JSON_LINE" | sed -E 's/^\*\*Schedule JSON\*\*[^:]*:[[:space:]]*//')
    echo "$JSON" | python3 "$TIME_REMAINING" --format=md
else
    echo "**Available Time Remaining** — (Schedule JSON missing from current cell; cannot recompute)"
fi
```

Also update the header comment block (lines 2–22) to say the source is now `agents-canonical/signals/current/schedule.md` (the materialized cell) refreshed by the host launchd job `com.ai-pa.current-briefing-refresh`.

- [ ] **Step 2: Verify reader against the live cell (today path)**

Run:
```bash
cd /Volumes/main-drive/ai-PA
set -a; . ~/.letta/pa-tools.env; set +a
TIME_REMAINING_SCRIPT=/Volumes/main-drive/ai-PA/letta-code/.scripts/time-remaining.py \
  bash letta-code/.scripts/schedule
```
Expected: prints the schedule header + a freshly-computed `Available Time Remaining` section (if the cell currently holds today). `echo $?` → 0.

- [ ] **Step 3: Verify the future-day branch**

Force a future cell, then read:
```bash
cd /Volumes/main-drive/ai-PA
set -a; . ~/.letta/pa-tools.env; set +a
export PYTHONPATH="/Volumes/main-drive/ai-PA/letta/pulse-tools:/Volumes/main-drive/ai-PA/letta"
# Write a future-dated cell directly (Monday), then read
~/.letta/pa-tools-venv/bin/python -c "
import pytz; from datetime import datetime
import daily_briefing.refresh_current as rc
print(rc.refresh_current_briefing(now_et=pytz.timezone('America/New_York').localize(datetime(2026,6,13,10))))"  # Sat -> Mon
TIME_REMAINING_SCRIPT=/Volumes/main-drive/ai-PA/letta-code/.scripts/time-remaining.py \
  bash letta-code/.scripts/schedule | head -20
```
Expected: prints the Monday body verbatim including its baked `**Available Time Remaining**` section (NOT a now-anchored recompute). Afterward, re-run the refresher with real `now` to restore the correct current cell:
```bash
~/.letta/pa-tools-venv/bin/python -m daily_briefing.refresh_current
```

- [ ] **Step 4: Commit**

```bash
git add letta-code/.scripts/schedule
git commit -m "feat(schedule): read materialized current cell; verbatim for future-day, recompute remaining for today"
```

---

## Task 5: Host launchd refresh job (wrapper + plist)

**Files:**
- Create: `letta/daily_briefing/refresh-current-briefing.sh`
- Create: `deployment/launchd/com.ai-pa.current-briefing-refresh.plist`

launchd can't express `*/15 6-23`; use `StartInterval=900` (15 min) + an hour-window guard in the wrapper. The wrapper sources `~/.letta/pa-tools.env` so the committed plist holds no secrets.

- [ ] **Step 1: Create the wrapper script**

```bash
# letta/daily_briefing/refresh-current-briefing.sh
#!/usr/bin/env bash
# Host launchd entry for the current-briefing refresher. Sources pa-tools env,
# enforces the active-hours window, runs the pinned-venv refresher. Exits
# non-zero on failure (launchd records it; the freshness monitor is the SLO).
set -euo pipefail

ENV_FILE="/Users/dorseyhomeserver/.letta/pa-tools.env"
VENV_PY="/Users/dorseyhomeserver/.letta/pa-tools-venv/bin/python"
REPO="/Volumes/main-drive/ai-PA"

# Active-hours guard: only run 06:00..22:59 Eastern (cheap no-op otherwise).
HOUR=$(TZ=America/New_York date +%H)
if (( 10#$HOUR < 6 || 10#$HOUR > 22 )); then
    exit 0
fi

set -a; . "$ENV_FILE"; set +a
export PATH="/Users/dorseyhomeserver/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"
export PYTHONPATH="${REPO}/letta/pulse-tools:${REPO}/letta"

exec "$VENV_PY" -m daily_briefing.refresh_current
```

Then: `chmod +x letta/daily_briefing/refresh-current-briefing.sh`

- [ ] **Step 2: Verify the wrapper runs (inside active hours) or no-ops (outside)**

Run: `bash letta/daily_briefing/refresh-current-briefing.sh; echo " exit=$?"`
Expected (06:00–22:59 ET): JSON `{"status":"ok",...}` + `exit=0`. (Outside the window: no output, `exit=0`.)

- [ ] **Step 3: Create the plist (no secrets)**

```xml
<!-- deployment/launchd/com.ai-pa.current-briefing-refresh.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ai-pa.current-briefing-refresh</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Volumes/main-drive/ai-PA/letta/daily_briefing/refresh-current-briefing.sh</string>
    </array>
    <key>StartInterval</key>
    <integer>900</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>ProcessType</key>
    <string>Background</string>
    <key>StandardOutPath</key>
    <string>/Users/dorseyhomeserver/Library/Logs/current-briefing-refresh/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/dorseyhomeserver/Library/Logs/current-briefing-refresh/stderr.log</string>
    <key>WorkingDirectory</key>
    <string>/Volumes/main-drive/ai-PA</string>
</dict>
</plist>
```

- [ ] **Step 4: Install + load the job**

Run:
```bash
mkdir -p ~/Library/Logs/current-briefing-refresh
cp deployment/launchd/com.ai-pa.current-briefing-refresh.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.ai-pa.current-briefing-refresh.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.ai-pa.current-briefing-refresh.plist
launchctl list | grep current-briefing-refresh
```
Expected: a line with the label (exit code `0` in the middle column after it has run once).

- [ ] **Step 5: Confirm it fired (RunAtLoad) and updated the cell**

Run (wait ~10s after load):
```bash
tail -5 ~/Library/Logs/current-briefing-refresh/stdout.log
set -a; . ~/.letta/pa-tools.env; set +a
curl -fsSL -H "Authorization: token $GITEA_MEMFS_TOKEN" \
  "$GITEA_BASE_URL/api/v1/repos/agents/agents-canonical/commits?path=signals/current/schedule.md&limit=1" \
  | python3 -c "import sys,json;print('last current-cell commit:', json.load(sys.stdin)[0]['commit']['committer']['date'])"
```
Expected: stdout log shows a recent `{"status":"ok",...}`; the cell's last commit is within the last minute.

- [ ] **Step 6: Commit**

```bash
git add letta/daily_briefing/refresh-current-briefing.sh deployment/launchd/com.ai-pa.current-briefing-refresh.plist
git commit -m "feat(briefing): host launchd refresh job for the current cell (every 15 min, 6am-11pm ET)"
```

---

## Task 6: Disable the 3 Docker `agent_message` schedule crons

**Files:**
- (No repo files; scheduler API mutation. Rollback snapshot already exists.)

The host launchd job now owns refresh. Disable the old crons so they don't double-write via the LLM path (and so their silent-success can't mask a launchd failure).

- [ ] **Step 1: Confirm the disable verb the scheduler supports**

Run: `grep -nE "@router\.(patch|post|put|delete).*job|enabled|status.*=|pause|disable" scheduler-service/src/scheduler_service/routes/jobs.py | head`
Expected: identify whether jobs are disabled via `PATCH /v1/jobs/{id}` body `{"status":"paused"}` (or similar) or a dedicated endpoint. Use whichever the code exposes. (The earlier flip used `PATCH /v1/jobs/{id}` with `{"actions":[...]}`; the status field observed was `scheduled`.)

- [ ] **Step 2: Disable the three jobs**

Run (adjust the disable payload to the verb confirmed in Step 1):
```bash
python3 - <<'PY'
import json, urllib.request
ids = ["933b620f-9cb1-47f8-b519-7ccedf1603ab",
       "f732d44c-50d1-4fd2-88b4-6102cece4fa3",
       "a683f7ef-bf03-4a4b-a607-fb52399f43a4"]
for jid in ids:
    body = json.dumps({"status": "paused"}).encode()  # <-- use confirmed verb/field
    req = urllib.request.Request(f"http://localhost:8087/v1/jobs/{jid}",
                                 data=body, method="PATCH",
                                 headers={"Content-Type": "application/json"})
    print(jid, "->", urllib.request.urlopen(req).status)
PY
```
Expected: three `200`s.

- [ ] **Step 3: Verify they no longer fire**

Run:
```bash
python3 -c "
import json,urllib.request
for jid in ['933b620f-9cb1-47f8-b519-7ccedf1603ab','f732d44c-50d1-4fd2-88b4-6102cece4fa3','a683f7ef-bf03-4a4b-a607-fb52399f43a4']:
    j=json.load(urllib.request.urlopen(f'http://localhost:8087/v1/jobs/{jid}'))
    print(jid, 'status=', j.get('status'), 'next_run=', j.get('next_run_at'))
"
```
Expected: status reflects paused/disabled and `next_run_at` is null (or in the past with no scheduling).

- [ ] **Step 4: (No commit — API state.)** Record the action in the rollback runbook (Task 8).

---

## Task 7: Freshness monitor (data-only, scheduler-side)

**Files:**
- Create: `letta/daily_briefing/check_current_freshness.py`
- (Register one scheduler job via API to run it — or run it as a second launchd job if you prefer host-only. This plan uses the scheduler for centralized alerting; it has no host deps, only HTTP to Gitea.)

The monitor GETs the cell's last-commit time and alerts if older than a threshold (relaxed overnight, since the refresher sleeps 23:00–06:00).

- [ ] **Step 1: Write the failing test (threshold logic, pure)**

```python
# letta/daily_briefing/tests/test_freshness.py
from datetime import datetime, timedelta
import pytz
from daily_briefing.check_current_freshness import is_stale

ET = pytz.timezone("America/New_York")

def test_fresh_within_threshold():
    now = ET.localize(datetime(2026, 6, 9, 12, 0))
    last = now - timedelta(minutes=20)
    assert is_stale(last, now) is False  # daytime threshold 40min

def test_stale_in_daytime():
    now = ET.localize(datetime(2026, 6, 9, 12, 0))
    last = now - timedelta(minutes=60)
    assert is_stale(last, now) is True

def test_overnight_relaxed():
    # 05:30 ET, last refresh was 22:50 prior night (~6.6h) -> NOT stale overnight
    now = ET.localize(datetime(2026, 6, 9, 5, 30))
    last = ET.localize(datetime(2026, 6, 8, 22, 50))
    assert is_stale(last, now) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Volumes/main-drive/ai-PA && PYTHONPATH=letta ~/.letta/pa-tools-venv/bin/python -m pytest letta/daily_briefing/tests/test_freshness.py -v`
Expected: FAIL (module/function missing).

- [ ] **Step 3: Implement the monitor**

```python
# letta/daily_briefing/check_current_freshness.py
"""Freshness monitor for signals/current/schedule.md. Exits non-zero (and
prints an alert line) if the cell is staler than allowed for the time of day.
Data-only: HTTP to Gitea, no host deps — safe to run from the Docker scheduler.
"""
import os, sys, json, urllib.request
from datetime import datetime, timedelta
import pytz

ET = pytz.timezone("America/New_York")
DAYTIME_MAX_MIN = 40    # cadence is 15 min; allow a couple misses
OVERNIGHT_MAX_MIN = 8 * 60  # refresher sleeps 23:00-06:00


def is_stale(last_refresh, now=None) -> bool:
    if now is None:
        now = datetime.now(ET)
    age_min = (now - last_refresh).total_seconds() / 60.0
    # Overnight window (23:00-06:00) tolerates the refresher's sleep.
    limit = OVERNIGHT_MAX_MIN if (now.hour >= 23 or now.hour < 6) else DAYTIME_MAX_MIN
    return age_min > limit


def _last_commit_dt() -> datetime:
    base = os.environ.get("GITEA_BASE_URL", "http://localhost:3030").rstrip("/")
    token = os.environ["GITEA_MEMFS_TOKEN"]
    url = (f"{base}/api/v1/repos/agents/agents-canonical/commits"
           f"?path=signals/current/schedule.md&limit=1")
    req = urllib.request.Request(url, headers={"Authorization": f"token {token}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode("utf-8"))
    iso = data[0]["commit"]["committer"]["date"].replace("Z", "+00:00")
    return datetime.fromisoformat(iso).astimezone(ET)


def main() -> int:
    try:
        last = _last_commit_dt()
    except Exception as e:
        sys.stderr.write(json.dumps({"status": "error", "error_message": str(e)}))
        return 2
    now = datetime.now(ET)
    if is_stale(last, now):
        sys.stderr.write(json.dumps({
            "status": "stale",
            "last_refresh": last.isoformat(),
            "age_minutes": round((now - last).total_seconds() / 60.0, 1),
        }))
        return 1
    sys.stdout.write(json.dumps({"status": "fresh", "last_refresh": last.isoformat()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Volumes/main-drive/ai-PA && PYTHONPATH=letta ~/.letta/pa-tools-venv/bin/python -m pytest letta/daily_briefing/tests/test_freshness.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Live check + register the alerting job**

Run the check live:
```bash
cd /Volumes/main-drive/ai-PA
set -a; . ~/.letta/pa-tools.env; set +a
PYTHONPATH=letta ~/.letta/pa-tools-venv/bin/python -m daily_briefing.check_current_freshness; echo " exit=$?"
```
Expected: `{"status":"fresh",...}` + `exit=0` (the launchd refresher ran in Task 5).

Register a scheduler job that runs this every 30 min and routes a stale result to your existing alert path (mirror the analytics `pipeline-health` signal pattern — emit a `canonical signal` slug `current-briefing-stale` on non-zero, or post to the alert channel used by `com.ai-pa.slack-analytics-watchdog`). Use the scheduler action type that fails loudly (`script`/`http`), NOT `agent_message`. Confirm one run.

- [ ] **Step 6: Commit**

```bash
git add letta/daily_briefing/check_current_freshness.py letta/daily_briefing/tests/test_freshness.py
git commit -m "feat(briefing): freshness monitor for the current cell (data-only, fails loudly)"
```

---

## Task 8: End-to-end verification, rollback runbook, docs

**Files:**
- Create: `docs/runbooks/2026-06-07-current-briefing-refresh-rollback.md`
- Modify: `docs/plans/2026-06-07-schedule-briefing-local-migration.md` (note supersession by the materialized-view model)

- [ ] **Step 1: Full-loop verification**

Run and confirm each:
```bash
cd /Volumes/main-drive/ai-PA
set -a; . ~/.letta/pa-tools.env; set +a
# 1) launchd job present + last exit 0
launchctl list | grep current-briefing-refresh
# 2) current cell fresh
curl -fsSL -H "Authorization: token $GITEA_MEMFS_TOKEN" \
  "$GITEA_BASE_URL/api/v1/repos/agents/agents-canonical/commits?path=signals/current/schedule.md&limit=1" \
  | python3 -c "import sys,json;print('cell commit', json.load(sys.stdin)[0]['commit']['committer']['date'])"
# 3) reader returns correct-for-now schedule
TIME_REMAINING_SCRIPT=/Volumes/main-drive/ai-PA/letta-code/.scripts/time-remaining.py bash letta-code/.scripts/schedule
# 4) old Docker crons paused
python3 -c "import json,urllib.request;
print([ (j, json.load(urllib.request.urlopen(f'http://localhost:8087/v1/jobs/{j}')).get('status')) for j in ['933b620f-9cb1-47f8-b519-7ccedf1603ab','f732d44c-50d1-4fd2-88b4-6102cece4fa3','a683f7ef-bf03-4a4b-a607-fb52399f43a4'] ])"
# 5) monitor green
PYTHONPATH=letta ~/.letta/pa-tools-venv/bin/python -m daily_briefing.check_current_freshness; echo " monitor_exit=$?"
```
Expected: launchd listed (exit 0); cell commit recent; reader prints today's schedule with a now-anchored Available-Time; all three crons paused; monitor `fresh` exit 0.

- [ ] **Step 2: Rollover spot-check**

If practical, run the refresher with a forced evening `now` and confirm the cell flips to the next workday, then restore:
```bash
export PYTHONPATH="/Volumes/main-drive/ai-PA/letta/pulse-tools:/Volumes/main-drive/ai-PA/letta"
~/.letta/pa-tools-venv/bin/python -c "import pytz;from datetime import datetime;import daily_briefing.refresh_current as rc;print(rc.refresh_current_briefing(now_et=pytz.timezone('America/New_York').localize(datetime(2026,6,9,18))))"
# reader should now print Wednesday verbatim; then restore real current:
~/.letta/pa-tools-venv/bin/python -m daily_briefing.refresh_current
```
Expected: forced run reports `target_date` = next workday; reader shows that day verbatim; restore returns the cell to the real current day.

- [ ] **Step 3: Write the rollback runbook**

Create `docs/runbooks/2026-06-07-current-briefing-refresh-rollback.md` documenting: (a) `launchctl unload ~/Library/LaunchAgents/com.ai-pa.current-briefing-refresh.plist` to stop the refresher; (b) re-enable the three Docker crons from `docs/runbooks/rollback-snapshots/2026-06-07-schedule-briefing-crons-preflip.json` (set status back to scheduled / restore actions); (c) revert `letta-code/.scripts/schedule` to read `signals/{today}` (git revert the Task-4 commit); (d) note the dependencies the refresh path needs (`~/.letta/pa-tools.env` keys, pinned venv, gws creds).

- [ ] **Step 4: Update the prior migration doc**

Add a note at the top of `docs/plans/2026-06-07-schedule-briefing-local-migration.md`: the agent_message cron flip is **superseded** by the materialized-view model (this plan) — refresh is now host-native launchd → pure tool → `current` cell; the agent_message crons are paused.

- [ ] **Step 5: Commit**

```bash
git add docs/runbooks/2026-06-07-current-briefing-refresh-rollback.md docs/plans/2026-06-07-schedule-briefing-local-migration.md
git commit -m "docs(briefing): current-cell rollback runbook + supersede prior migration note"
```

---

## Self-review notes (coverage)

- Rollover rule → Task 1 (helper + 7 cases). Refresher + cell write → Task 2. Tool stays pure (no date logic added; dead write removed) → Task 3. Instant read + read-time precision + future-day verbatim → Task 4. Host-native deterministic scheduling (catch fix) → Task 5. Old LLM crons retired → Task 6. Freshness SLO → Task 7. E2E + rollback → Task 8.
- Time-remaining precision: preserved at read time (Task 4), independent of the 15-min refresh cadence (Task 5).
- Silent-success catch: eliminated — refresh is a direct venv invocation with non-zero exit on failure (Tasks 2, 5) plus an artifact-freshness monitor (Task 7); no `agent_message` in the path.
- Secrets: env via `pa-tools.env`/wrapper; committed plist has none (Task 5).
- Rollback: snapshot exists; runbook in Task 8; each code change is its own commit.

## Open verification dependencies (resolve during execution, don't assume)
- Task 6 Step 1: confirm the scheduler's actual disable verb/field (`status:"paused"` vs a dedicated endpoint) before mutating.
- Task 7 Step 5: confirm which existing alert channel/signal to route a stale result to (reuse the analytics `pipeline-health` / slack-analytics-watchdog path; do not invent a new one).
- Task 2: confirm the tool's returned `briefing` contains the `**Schedule JSON**` line (it should — the dated signal the reader uses today carries it); the refresher asserts this and fails loudly if absent.
