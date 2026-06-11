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
