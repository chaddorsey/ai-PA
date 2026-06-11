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
