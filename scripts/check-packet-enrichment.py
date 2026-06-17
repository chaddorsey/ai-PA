#!/usr/bin/env python3
"""Backstop: flag CONFIRMED tasks whose work packet didn't gain cross-channel
resources (the cross_channel_backtrace under-delivered or never ran). Loud, not
silent. Writes enrichment.backstop; logs WARNING for thin packets.

A packet is "thin" if its resources draw from <= 1 distinct channel (host).
"""
import argparse, json, os, re, sys
from datetime import datetime, timezone
from urllib.parse import urlparse


def _host(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def is_thin(resources) -> bool:
    hosts = set()
    for line in resources or []:
        for u in re.findall(r"https?://\S+", line):
            h = _host(u.rstrip("|) "))
            if h:
                hosts.add(h)
    return len(hosts) <= 1


def _db_url() -> str:
    url = os.environ.get("PA_WEB_POSTGRES_URL")
    if url:
        return url
    pw = os.environ.get("POSTGRES_PASSWORD", "")
    return f"postgresql://postgres:{pw}@localhost:{os.environ.get('PA_WEB_POSTGRES_PORT','5433')}/postgres"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-hours", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    import psycopg
    from psycopg.rows import dict_row
    thin = 0
    with psycopg.connect(_db_url(), autocommit=True, connect_timeout=10) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT ref_id, enrichment FROM pa_web.tasks "
                "WHERE status='confirmed' AND closed_at IS NULL "
                "AND updated_at > NOW() - (%s || ' hours')::interval",
                (args.window_hours,))
            rows = cur.fetchall()
        for r in rows:
            enr = r["enrichment"]
            if isinstance(enr, str):
                try: enr = json.loads(enr)
                except Exception: enr = {}
            if not isinstance(enr, dict):
                enr = {}
            resources = (enr.get("packet_info") or {}).get("resources") or []
            t = is_thin(resources)
            if t:
                thin += 1
                print(f"[{datetime.now(timezone.utc):%FT%TZ}] [packet-backstop] WARN thin packet "
                      f"ref_id={r['ref_id']} (resources from <=1 channel)", flush=True)
            if not args.dry_run:
                with conn.cursor() as c2:
                    c2.execute(
                        "UPDATE pa_web.tasks "
                        "SET enrichment = COALESCE(enrichment, '{}'::jsonb) "
                        "    || jsonb_build_object('backstop', %s::jsonb) "
                        "WHERE ref_id = %s",
                        (json.dumps({"thin": t, "checked_at": datetime.now(timezone.utc).isoformat()}), r["ref_id"]))
    print(f"[{datetime.now(timezone.utc):%FT%TZ}] [packet-backstop] done: checked={len(rows)} thin={thin}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
