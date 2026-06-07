"""Refresher for the 'current' daily-briefing materialized cell.

Owns the 'which day is current' policy (rollover), calls the pure
generate_daily_briefing renderer, and writes the date-less
signals/current/schedule.md cell. The renderer call + cell write are added in
a later task; this module currently provides the pure rollover helper.
"""
from datetime import datetime, date, timedelta
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
