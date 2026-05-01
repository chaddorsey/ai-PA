#!/usr/local/bin/python3
"""
slack-analytics-csv-poll.py — pull Slack analytics CSV exports.

Slack auto-DMs analytics CSVs to USLACKBOT (Slack's built-in bot), which is a
private DM between Chad and Slack. Our custom Slackbot has no visibility there.
Solution: poll using Chad's user token (SLACK_MCP_XOXP_TOKEN), which sees
USLACKBOT files because the API call IS Chad.

Strategy:
  1. files.list?user=USLACKBOT&ts_from=<since> with the xoxp token
  2. Filter to *.csv with "Analytics" in the name
  3. Dedup against analytics_raw.raw_artifacts on (source='slack', sha256)
  4. Download new files via url_private_download (xoxp token), archive,
     insert row with parse_status='pending'

Idempotent: re-running picks up only files we haven't archived yet.
Designed to run as scheduler-service `script` action every 15 minutes.

Filename conventions (observed):
  - "Concord Consortium Channel Analytics Apr 25, 2026 - Apr 26, 2026.csv"
  - "Concord Consortium Member Analytics Apr 25, 2026 - Apr 26, 2026.csv"

The "day" we record is the START date in the filename (the day the analytics
cover); fall back to file `created` timestamp if the regex doesn't match.
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg


ENV_PATH = "/workspace/.env"
RAW_ARCHIVE_DIR = Path(os.environ.get("RAW_ARCHIVE_DIR", "/data/raw-archive"))
ANALYTICS_DIR = RAW_ARCHIVE_DIR / "slack-analytics"
LOOKBACK_DAYS = int(os.environ.get("ANALYTICS_LOOKBACK_DAYS", "14"))


def read_env(name):
    if name in os.environ:
        return os.environ[name]
    try:
        with open(ENV_PATH) as f:
            for line in f:
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


SLACK_TOKEN = read_env("SLACK_MCP_XOXP_TOKEN")
PG_PASSWORD = read_env("POSTGRES_PASSWORD") or ""
PG_URL = (
    read_env("PA_WEB_POSTGRES_URL")
    or f"postgresql://postgres:{PG_PASSWORD}@supabase-db:5432/postgres"
)


if not SLACK_TOKEN:
    sys.stderr.write("FATAL: SLACK_MCP_XOXP_TOKEN missing\n")
    sys.exit(2)


MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
DATE_RANGE_RE = re.compile(
    r"\b([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})\s*-\s*[A-Z][a-z]{2}\s+\d{1,2},\s*\d{4}"
)


def slack_api(method, params):
    qs = urllib.parse.urlencode(params)
    url = f"https://slack.com/api/{method}?{qs}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {SLACK_TOKEN}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 + attempt * 2)
                continue
            raise
        except Exception:
            time.sleep(1 + attempt)
    return {"ok": False}


def parse_day_from_name(name):
    m = DATE_RANGE_RE.search(name)
    if not m:
        return None
    mon = MONTHS.get(m.group(1))
    day = int(m.group(2))
    year = int(m.group(3))
    if not mon:
        return None
    try:
        return datetime(year, mon, day).date()
    except ValueError:
        return None


def classify_kind(name):
    n = name.lower()
    if "channel analytics" in n or "public channel" in n:
        return "slack-channels-csv"
    if "member analytics" in n:
        return "slack-members-csv"
    if "analytics" in n:
        return "slack-analytics-csv"
    return "slack-unknown-csv"


def list_uslackbot_files(since_ts):
    files = []
    page = 1
    while True:
        d = slack_api("files.list", {
            "user": "USLACKBOT",
            "ts_from": str(since_ts),
            "count": "100",
            "page": str(page),
        })
        if not d.get("ok"):
            sys.stderr.write(f"files.list error: {d.get('error')}\n")
            break
        files.extend(d.get("files", []) or [])
        paging = d.get("paging") or {}
        if page >= (paging.get("pages") or 1):
            break
        page += 1
        time.sleep(0.3)
    return files


def already_archived(cur, sha256):
    cur.execute(
        "SELECT artifact_id FROM analytics_raw.raw_artifacts WHERE source='slack' AND sha256=%s LIMIT 1",
        (sha256,),
    )
    return cur.fetchone() is not None


def download(url, dest):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {SLACK_TOKEN}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    with open(dest, "wb") as out:
        out.write(data)
    return data


def main():
    since = int(time.time() - LOOKBACK_DAYS * 86400)
    files = list_uslackbot_files(since)

    csvs = [
        f for f in files
        if (f.get("name") or "").lower().endswith(".csv")
        and "analytics" in (f.get("name") or "").lower()
    ]

    if not csvs:
        print(f"poll: 0 analytics CSVs in last {LOOKBACK_DAYS}d (USLACKBOT files: {len(files)})")
        return 0

    captured = 0
    skipped = 0
    errors = 0

    with psycopg.connect(PG_URL, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            for f in csvs:
                file_id = f.get("id")
                name = f.get("name") or f"file-{file_id}.csv"
                created = int(f.get("created") or 0)
                url = f.get("url_private_download") or f.get("url_private")

                day = parse_day_from_name(name)
                if not day and created:
                    day = datetime.fromtimestamp(created, tz=timezone.utc).date()
                if not day:
                    day = datetime.now(timezone.utc).date()

                kind = classify_kind(name)

                # Build archive path before download so we can include it in insert
                archive_subdir = ANALYTICS_DIR / day.strftime("%Y") / day.strftime("%m") / day.strftime("%d")
                archive_subdir.mkdir(parents=True, exist_ok=True)
                safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
                dest = archive_subdir / f"{file_id}__{safe_name}"

                # If file already exists at the path AND we have a row, skip without re-downloading
                if dest.exists():
                    cur.execute(
                        "SELECT artifact_id FROM analytics_raw.raw_artifacts WHERE archive_path=%s LIMIT 1",
                        (str(dest),),
                    )
                    if cur.fetchone():
                        skipped += 1
                        continue

                try:
                    data = download(url, dest)
                except Exception as e:
                    sys.stderr.write(f"  ! download failed {file_id} {name}: {e}\n")
                    errors += 1
                    continue

                sha256 = hashlib.sha256(data).hexdigest()
                size_bytes = len(data)

                if already_archived(cur, sha256):
                    # Same content already captured under a different path; remove duplicate
                    try:
                        dest.unlink()
                    except OSError:
                        pass
                    skipped += 1
                    continue

                try:
                    cur.execute(
                        """
                        INSERT INTO analytics_raw.raw_artifacts
                            (source, kind, day, archive_path, size_bytes, sha256, parse_status)
                        VALUES ('slack', %s, %s, %s, %s, %s, 'pending')
                        ON CONFLICT (source, kind, day, archive_path) DO UPDATE
                          SET size_bytes = EXCLUDED.size_bytes,
                              sha256     = EXCLUDED.sha256
                        RETURNING artifact_id
                        """,
                        (kind, day, str(dest), size_bytes, sha256, ),
                    )
                    artifact_id = cur.fetchone()[0]
                    captured += 1
                    print(f"  captured kind={kind} day={day} bytes={size_bytes} id={artifact_id} path={dest}")
                except Exception as e:
                    errors += 1
                    sys.stderr.write(f"  ! db insert failed {file_id}: {e}\n")

    print(f"poll: captured={captured} skipped={skipped} errors={errors} (csvs seen={len(csvs)}, lookback={LOOKBACK_DAYS}d)")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
