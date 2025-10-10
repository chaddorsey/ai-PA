#!/usr/bin/env python3
"""
Calendly scraper for the undocumented `/api/booking/event_types/<UUID>/calendar/range` endpoint.

What it does:
- Accepts one or more full `calendar/range` URLs copied from DevTools.
- Prints available dates in each URL's range.
- Then, for each available date, re-queries the SAME endpoint with a 1-day window
  (range_start=YYYY-MM-DD, range_end=YYYY-MM-DD+1) to extract time slots from days[].spots[].
- Converts ISO timestamps to local time using the `timezone` in your URL (if present).

Usage examples:
  # Print available dates only
  python calendly_scrape.py --range "https://calendly.com/api/booking/event_types/<UUID>/calendar/range?...range_start=2025-11-01&range_end=2025-11-30&..."

  # Dates + hours (per-day re-fetch)
  python calendly_scrape.py --range "<URL>" --hours

  # Show raw JSON to verify the shape (handy if times don't appear)
  python calendly_scrape.py --range "<URL>" --show-json

Notes:
- This uses undocumented frontend endpoints; Calendly could change them.
- If days[].spots[] is missing even for 1-day windows, we can switch to a Playwright DOM scrape.
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    ZoneInfo = None


def build_session(referer: Optional[str] = None) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": referer or "https://calendly.com/",
    })
    # Warm the session like the browser (ignore failures)
    try:
        s.get("https://calendly.com/api/booking/initial_settings", timeout=20)
    except requests.RequestException:
        pass
    return s


def normalize_url(u: str) -> str:
    p = urlparse(u)
    if "calendly.com" not in p.netloc:
        raise ValueError(f"Not a Calendly URL: {u}")
    qs = parse_qs(p.query, keep_blank_values=True)
    new_query = urlencode([(k, v) for k, vals in qs.items() for v in vals])
    return urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, p.fragment))


def read_query(u: str) -> Dict[str, List[str]]:
    return parse_qs(urlparse(u).query, keep_blank_values=True)


def replace_query(u: str, **replacements: str) -> str:
    p = urlparse(u)
    qs = parse_qs(p.query, keep_blank_values=True)
    for k, v in replacements.items():
        qs[k] = [v]
    new_query = urlencode([(k, v) for k, vals in qs.items() for v in vals])
    return urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, p.fragment))


def fetch_json(url: str, session: requests.Session) -> Dict[str, Any]:
    r = session.get(url, timeout=30)
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"Non-JSON response ({r.status_code}) from {url[:120]}... -> {r.text[:200]}")
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code} for {url[:120]}... -> {json.dumps(data)[:300]}")
    return data


def extract_available_dates(payload: Dict[str, Any]) -> List[str]:
    days = payload.get("days", [])
    return [d.get("date") for d in days if d.get("status") == "available"]


def _iso_to_local_hhmm(iso: str, tz_name: Optional[str]) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if tz_name and ZoneInfo:
            dt = dt.astimezone(ZoneInfo(tz_name))
        return dt.strftime("%H:%M")
    except Exception:
        # Fallback substring if weird format
        return iso[11:16] if len(iso) >= 16 else iso


def extract_times_from_range(payload: Dict[str, Any], tz_name: Optional[str]) -> Dict[str, List[str]]:
    """
    If the /calendar/range payload includes per-day time slots under days[].spots[],
    return { 'YYYY-MM-DD': ['HH:MM', ...], ... }.
    """
    out: Dict[str, List[str]] = defaultdict(list)
    for day in payload.get("days", []):
        if day.get("status") != "available":
            continue
        spots = day.get("spots", [])
        if not isinstance(spots, list):
            continue
        d = day.get("date")
        for spot in spots:
            if not isinstance(spot, dict):
                continue
            iso = spot.get("start_time") or spot.get("start") or spot.get("start_time_utc")
            if isinstance(iso, str):
                out[d].append(_iso_to_local_hhmm(iso, tz_name))
        if out.get(d):
            out[d] = sorted(set(out[d]))
    return dict(sorted(out.items()))


def one_day_window(day_str: str) -> (str, str):
    d = date.fromisoformat(day_str)
    return d.isoformat(), (d + timedelta(days=1)).isoformat()


def main():
    ap = argparse.ArgumentParser(description="Calendly dates & hours scraper from /calendar/range")
    ap.add_argument("--range", dest="range_urls", action="append",
                    help="Full /calendar/range URL (copy from DevTools). Can be repeated.")
    ap.add_argument("--hours", action="store_true",
                    help="For each available date, re-query a 1-day window and print time slots from days[].spots[].")
    ap.add_argument("--sleep", type=float, default=0.4,
                    help="Seconds to sleep between per-day requests (default: 0.4).")
    ap.add_argument("--show-json", action="store_true",
                    help="Print raw JSON payload(s) for debugging.")
    args = ap.parse_args()

    if not args.range_urls:
        ap.print_help(sys.stderr)
        sys.exit(2)

    # Normalize & de-dupe URLs
    try:
        urls = list(dict.fromkeys(normalize_url(u) for u in args.range_urls))
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(2)

    s = build_session("https://calendly.com/")

    for url in urls:
        try:
            payload = fetch_json(url, s)
        except Exception as e:
            print(f"\nERROR fetching: {url}\n  {e}", file=sys.stderr)
            continue

        qs = read_query(url)
        tz = (qs.get("timezone") or [None])[0]

        if args.show_json:
            print("\n=== RANGE RAW JSON ===")
            print(json.dumps(payload, indent=2))

        # 1) Dates
        dates = extract_available_dates(payload)
        print(f"\n[RANGE] {url}")
        if dates:
            for d in sorted(dates):
                print("  ", d)
        else:
            print("  (no available days in range)")
            continue

        # 2) Try to print times directly if present in the range payload
        times_here = extract_times_from_range(payload, tz)
        if times_here:
            print("\n  Times present directly in range payload:")
            for d, slots in times_here.items():
                print(f"    {d}: {', '.join(slots)}")

        # 3) If requested, per-day re-fetch to coax `spots` for each day
        if args.hours:
            print("\n  Per-day re-fetch for time slots:")
            for d in sorted(dates):
                start, end = one_day_window(d)
                day_url = replace_query(url, range_start=start, range_end=end)
                try:
                    day_payload = fetch_json(day_url, s)
                    day_times = extract_times_from_range(day_payload, tz)
                    if day_times.get(d):
                        print(f"    {d}: {', '.join(day_times[d])}")
                    else:
                        print(f"    {d}: (no spots field returned)")
                except Exception as e:
                    print(f"    {d}: ERROR -> {e}", file=sys.stderr)
                time.sleep(args.sleep)


if __name__ == "__main__":
    main()
