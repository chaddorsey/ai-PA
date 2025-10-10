#!/usr/bin/env python3
import re, json, asyncio, argparse, sys, time
from datetime import date, timedelta, datetime
from urllib.parse import urlparse, parse_qs
from typing import Optional, Tuple, Dict, Any, List

import requests
from playwright.async_api import async_playwright

try:
    from zoneinfo import ZoneInfo  # py>=3.9
except Exception:
    ZoneInfo = None

UUID_URL_RE = re.compile(r"/api/booking/event_types/([0-9a-fA-F-]{36})/calendar/range")

def iso_to_hhmm(iso: str, tzname: Optional[str]) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if tzname and ZoneInfo:
            dt = dt.astimezone(ZoneInfo(tzname))
        return dt.strftime("%H:%M")
    except Exception:
        return iso[11:16] if len(iso) >= 16 else iso

async def sniff_uuids(event_url: str, wait_seconds: float = 6.0) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (origin, event_type_uuid, scheduling_link_uuid) by observing XHR."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        origin = None
        found_uuid = None
        scheduling_short = None

        def on_response(resp):
            nonlocal found_uuid, scheduling_short, origin
            url = resp.url
            if ("calendly.com" in url) and ("/api/booking/event_types/" in url) and ("/calendar/range" in url):
                m = UUID_URL_RE.search(url)
                if m:
                    found_uuid = m.group(1).lower()
                    # Parse scheduling_link_uuid if present
                    q = parse_qs(urlparse(url).query)
                    scheduling_short = (q.get("scheduling_link_uuid") or [None])[0]
                    o = urlparse(url)
                    origin = f"{o.scheme}://{o.netloc}"

        page.on("response", on_response)
        await page.goto(event_url, wait_until="networkidle")

        # If the page didn’t make a range call on initial load, nudge it by clicking the given date (if any)
        # Try to click the day from query param ?date=YYYY-MM-DD or otherwise any available "button" with a number
        try:
            parsed = urlparse(event_url)
            q = parse_qs(parsed.query)
            if "date" in q:
                target_day = q["date"][0].split("-")[-1].lstrip("0")
                # Try an accessible button with the day number
                btn = page.get_by_role("button", name=target_day)
                await btn.click(timeout=2000)
        except Exception:
            pass

        # Wait a bit for network calls to fire
        await page.wait_for_timeout(int(wait_seconds * 1000))
        await browser.close()
        return origin, found_uuid, scheduling_short

def fetch_range(origin: str, uuid: str, tz: str, start: str, end: str,
                scheduling_short: Optional[str], session: Optional[requests.Session] = None) -> Dict[str, Any]:
    s = session or requests.Session()
    base = f"{origin}/api/booking/event_types/{uuid}/calendar/range"
    params = {"timezone": tz, "diagnostics": "false", "range_start": start, "range_end": end}
    if scheduling_short:
        params["scheduling_link_uuid"] = scheduling_short
    r = s.get(base, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def available_days(payload: Dict[str, Any]) -> List[str]:
    return [d.get("date") for d in payload.get("days", []) if d.get("status") == "available"]

def times_from_range(payload: Dict[str, Any], tzname: Optional[str]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for day in payload.get("days", []):
        if day.get("status") != "available":
            continue
        slots = []
        for spot in day.get("spots", []) or []:
            if isinstance(spot, dict):
                iso = spot.get("start_time") or spot.get("start") or spot.get("start_time_utc")
                if isinstance(iso, str):
                    slots.append(iso_to_hhmm(iso, tzname))
        if slots:
            out[day["date"]] = sorted(set(slots))
    return dict(sorted(out.items()))

def one_day_window(d: str) -> Tuple[str, str]:
    x = date.fromisoformat(d)
    return x.isoformat(), (x + timedelta(days=1)).isoformat()

async def main_async(args):
    # 1) Sniff UUIDs from the live page (no DevTools)
    origin, uuid, sched_short = await sniff_uuids(args.event_url, wait_seconds=args.sniff_wait)
    if not uuid:
        print("Could not sniff event_type UUID from the event page network traffic.", file=sys.stderr)
        print("Tip: include a ?date=YYYY-MM-DD in the URL, or pass a URL where the month shows availability.", file=sys.stderr)
        sys.exit(2)

    # 2) Now we can call the same endpoint you’ve been using
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": args.event_url,
    })

    start = args.start or date.today().isoformat()
    end   = args.end or (date.fromisoformat(start) + timedelta(days=21)).isoformat()

    rng = fetch_range(origin, uuid, args.tz, start, end, sched_short, s)
    if args.show_json:
        print("\n=== RANGE RAW JSON ===")
        print(json.dumps(rng, indent=2))

    days = available_days(rng)
    print(f"UUID:  {uuid}")
    if sched_short:
        print(f"Short: {sched_short}")
    print(f"\nAvailable days [{start} .. {end}):")
    if days:
        for d in sorted(days):
            print("  ", d)
    else:
        print("  (none)")

    direct = times_from_range(rng, args.tz)
    if direct:
        print("\nTimes (from range payload):")
        for d, slots in direct.items():
            print(f"  {d}: {', '.join(slots)}")

    if args.date:
        # Single-day window to fetch hours for that date
        d0, d1 = one_day_window(args.date)
        day = fetch_range(origin, uuid, args.tz, d0, d1, sched_short, s)
        t = times_from_range(day, args.tz)
        print(f"\n{args.date}: {', '.join(t.get(args.date, [])) or '(no time slots)'}")

    if args.hours and days:
        print("\nTimes (per-day windows):")
        for d in sorted(days):
            d0, d1 = one_day_window(d)
            day = fetch_range(origin, uuid, args.tz, d0, d1, sched_short, s)
            t = times_from_range(day, args.tz)
            print(f"  {d}: {', '.join(t.get(d, [])) or '(no time slots)'}")
            time.sleep(args.sleep)

def cli():
    ap = argparse.ArgumentParser(description="Sniff Calendly network → scrape dates & hours (no DevTools)")
    ap.add_argument("event_url", help="Public event URL, e.g. https://calendly.com/<owner>/<slug>[?date=YYYY-MM-DD]")
    ap.add_argument("--tz", default="America/New_York", help="IANA timezone for output")
    ap.add_argument("--start", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--end", help="YYYY-MM-DD (default: start+21d)")
    ap.add_argument("--date", help="Fetch hours only for this date (YYYY-MM-DD)")
    ap.add_argument("--hours", action="store_true", help="Fetch hours for every available day in the range")
    ap.add_argument("--sleep", type=float, default=0.35, help="Delay between per-day requests")
    ap.add_argument("--show-json", action="store_true", help="Dump raw JSON payloads")
    ap.add_argument("--sniff-wait", type=float, default=6.0, help="Seconds to wait for XHRs during sniffing")
    args = ap.parse_args()
    asyncio.run(main_async(args))

if __name__ == "__main__":
    cli()
