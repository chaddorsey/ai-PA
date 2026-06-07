"""Freshness monitor for signals/current/schedule.md. Exits non-zero (and
prints an alert line) if the cell is staler than allowed for the time of day.
Data-only: HTTP to Gitea, no host deps — safe to run from anywhere.
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
