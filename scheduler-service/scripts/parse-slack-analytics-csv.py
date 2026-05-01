#!/usr/local/bin/python3
"""
parse-slack-analytics-csv.py — silver layer for slack analytics.

Walks analytics_raw.raw_artifacts WHERE source='slack' AND parse_status='pending',
parses each CSV by kind, populates the appropriate silver table, marks parsed.

Privacy boundary:
  slack-channels-csv → analytics.slack_channel_daily (per-channel-per-day rows)
  slack-members-csv  → analytics.slack_member_rollup (aggregate-only, no
                        per-individual rows)

Idempotent: re-running on already-parsed artifacts is a no-op (filtered by
parse_status). Re-parsing requires explicitly resetting parse_status to
'pending'.

Designed to run as scheduler-service `script` action (07:15 ET daily, after
the 07:00 poller).
"""
import csv
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb


ENV_PATH = "/workspace/.env"


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


PG_PASSWORD = read_env("POSTGRES_PASSWORD") or ""
PG_URL = (
    read_env("PA_WEB_POSTGRES_URL")
    or f"postgresql://postgres:{PG_PASSWORD}@supabase-db:5432/postgres"
)


MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def parse_slack_date(s):
    """Slack uses 'Mon DD, YYYY' (e.g. 'Aug 26, 2015'). Returns date or None."""
    if not s:
        return None
    s = s.strip().strip('"')
    try:
        parts = s.replace(",", "").split()
        if len(parts) != 3:
            return None
        mon = MONTHS.get(parts[0])
        if not mon:
            return None
        return datetime(int(parts[2]), mon, int(parts[1])).date()
    except (ValueError, IndexError):
        return None


def to_int(s):
    if s is None or s == "":
        return None
    try:
        return int(str(s).strip().replace('"', ""))
    except (ValueError, AttributeError):
        return None


def percentile(sorted_vals, pct):
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = int(k)
    hi = lo + 1 if lo + 1 < len(sorted_vals) else lo
    weight = k - lo
    return sorted_vals[lo] * (1 - weight) + sorted_vals[hi] * weight


def hist_messages(values):
    bands = {"0": 0, "1-5": 0, "6-25": 0, "26-100": 0, "100+": 0}
    for v in values:
        if v == 0:
            bands["0"] += 1
        elif v <= 5:
            bands["1-5"] += 1
        elif v <= 25:
            bands["6-25"] += 1
        elif v <= 100:
            bands["26-100"] += 1
        else:
            bands["100+"] += 1
    return bands


def hist_days_active(values):
    bands = {"0": 0, "1-3": 0, "4-10": 0, "11-30": 0}
    for v in values:
        if v == 0:
            bands["0"] += 1
        elif v <= 3:
            bands["1-3"] += 1
        elif v <= 10:
            bands["4-10"] += 1
        else:
            bands["11-30"] += 1
    return bands


def parse_channels_csv(content):
    """Parse a Channel Analytics CSV. Returns list of row dicts ready for insert."""
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    for r in reader:
        rows.append({
            "channel_name":       (r.get("Name") or "").strip(),
            "description":        (r.get("Description") or "").strip() or None,
            "visibility":         (r.get("Visibility") or "").strip() or None,
            "channel_created":    parse_slack_date(r.get("Created") or ""),
            "total_membership":   to_int(r.get("Total membership")),
            "messages_posted":    to_int(r.get("Messages posted")),
            "members_who_posted": to_int(r.get("Members who posted")),
            "members_who_viewed": to_int(r.get("Members who viewed")),
        })
    return rows


def parse_members_csv(content):
    """Parse a Member Analytics CSV. Returns aggregate stats only (no per-row data)."""
    reader = csv.DictReader(io.StringIO(content))
    days_active_vals = []
    msgs_vals = []
    for r in reader:
        d = to_int(r.get("Days active")) or 0
        m = to_int(r.get("Messages posted")) or 0
        days_active_vals.append(d)
        msgs_vals.append(m)

    msgs_sorted = sorted(msgs_vals)
    return {
        "total_members":  len(msgs_vals),
        "members_active": sum(1 for d in days_active_vals if d > 0),
        "members_posted": sum(1 for m in msgs_vals if m > 0),
        "total_messages": sum(msgs_vals),
        "p50_messages":   percentile(msgs_sorted, 50),
        "p90_messages":   percentile(msgs_sorted, 90),
        "p99_messages":   percentile(msgs_sorted, 99),
        "histogram_messages":    hist_messages(msgs_vals),
        "histogram_days_active": hist_days_active(days_active_vals),
    }


def classify_member_window(filename):
    if "Prior" in filename and "Days" in filename:
        return "prior-30-days"
    return "single-day"


def main():
    captured = {"channels": 0, "members": 0}
    errors = 0

    with psycopg.connect(PG_URL, autocommit=False, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT artifact_id, kind, day, archive_path
                FROM analytics_raw.raw_artifacts
                WHERE source = 'slack' AND parse_status = 'pending'
                ORDER BY day, artifact_id
                """
            )
            pending = cur.fetchall()

        if not pending:
            print("parse: nothing pending")
            return 0

        for artifact_id, kind, day, archive_path in pending:
            try:
                content = Path(archive_path).read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                print(f"  ! {artifact_id} {archive_path}: read failed: {e}", file=sys.stderr)
                errors += 1
                continue

            try:
                with conn.cursor() as cur:
                    if kind == "slack-channels-csv":
                        rows = parse_channels_csv(content)
                        cur.execute(
                            "DELETE FROM analytics.slack_channel_daily WHERE snapshot_date = %s",
                            (day,),
                        )
                        cur.executemany(
                            """
                            INSERT INTO analytics.slack_channel_daily
                                (snapshot_date, channel_name, visibility, total_membership,
                                 messages_posted, members_who_posted, members_who_viewed,
                                 channel_created, description, source_artifact_id)
                            VALUES
                                (%(snapshot_date)s, %(channel_name)s, %(visibility)s, %(total_membership)s,
                                 %(messages_posted)s, %(members_who_posted)s, %(members_who_viewed)s,
                                 %(channel_created)s, %(description)s, %(source_artifact_id)s)
                            """,
                            [
                                {**r, "snapshot_date": day, "source_artifact_id": artifact_id}
                                for r in rows
                                if r["channel_name"]
                            ],
                        )
                        captured["channels"] += 1
                        print(f"  parsed channels day={day} rows={len([r for r in rows if r['channel_name']])} artifact={artifact_id}")

                    elif kind == "slack-members-csv":
                        agg = parse_members_csv(content)
                        window = classify_member_window(Path(archive_path).name)
                        cur.execute(
                            """
                            INSERT INTO analytics.slack_member_rollup
                                (snapshot_date, csv_window, csv_covers_date,
                                 total_members, members_active, members_posted, total_messages,
                                 p50_messages, p90_messages, p99_messages,
                                 histogram_messages, histogram_days_active, source_artifact_id)
                            VALUES
                                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (snapshot_date, csv_window) DO UPDATE SET
                                csv_covers_date       = EXCLUDED.csv_covers_date,
                                total_members         = EXCLUDED.total_members,
                                members_active        = EXCLUDED.members_active,
                                members_posted        = EXCLUDED.members_posted,
                                total_messages        = EXCLUDED.total_messages,
                                p50_messages          = EXCLUDED.p50_messages,
                                p90_messages          = EXCLUDED.p90_messages,
                                p99_messages          = EXCLUDED.p99_messages,
                                histogram_messages    = EXCLUDED.histogram_messages,
                                histogram_days_active = EXCLUDED.histogram_days_active,
                                source_artifact_id    = EXCLUDED.source_artifact_id,
                                captured_at           = now()
                            """,
                            (
                                day, window, day,
                                agg["total_members"], agg["members_active"], agg["members_posted"], agg["total_messages"],
                                agg["p50_messages"], agg["p90_messages"], agg["p99_messages"],
                                Jsonb(agg["histogram_messages"]), Jsonb(agg["histogram_days_active"]),
                                artifact_id,
                            ),
                        )
                        captured["members"] += 1
                        print(f"  parsed members day={day} window={window} active={agg['members_active']} posted={agg['members_posted']} total={agg['total_members']} artifact={artifact_id}")

                    else:
                        print(f"  ? skipping unknown kind={kind} artifact={artifact_id}")
                        continue

                    cur.execute(
                        "UPDATE analytics_raw.raw_artifacts SET parse_status='parsed', parsed_at=now(), parse_error=NULL WHERE artifact_id=%s",
                        (artifact_id,),
                    )
                conn.commit()

            except Exception as e:
                conn.rollback()
                errors += 1
                print(f"  ! parse failed artifact={artifact_id} kind={kind}: {e}", file=sys.stderr)
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE analytics_raw.raw_artifacts SET parse_status='failed', parse_error=%s WHERE artifact_id=%s",
                        (str(e)[:1000], artifact_id),
                    )
                conn.commit()

    print(f"\nparse: channels={captured['channels']} members={captured['members']} errors={errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
