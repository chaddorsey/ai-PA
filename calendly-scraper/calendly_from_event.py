#!/usr/bin/env python3
import argparse, json, re, sys, time
from datetime import date, datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List
from urllib.parse import urlparse, parse_qs

import requests

try:
    from zoneinfo import ZoneInfo  # py>=3.9
except Exception:
    ZoneInfo = None

UUID_RE  = re.compile(r"event_types/([0-9a-fA-F-]{36})")
NEXT_RE  = re.compile(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(?P<json>.*?)</script>', re.S)

def build_session(ref: Optional[str]) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": ref or "https://calendly.com/",
    })
    # Warm like the browser (ignore failures)
    try:
        s.get("https://calendly.com/api/booking/initial_settings", timeout=15)
    except requests.RequestException:
        pass
    return s

def parse_event_url(u: str) -> Tuple[str, str, str]:
    p = urlparse(u)
    parts = [x for x in p.path.split("/") if x]
    if len(parts) < 2:
        raise SystemExit(f"Not an event URL: {u}\nExpected https://calendly.com/<owner>/<slug>")
    origin = f"{p.scheme}://{p.netloc}"
    return origin, parts[0], parts[1]  # origin, owner, slug

def lookup_uuid(owner: str, slug: str, s: requests.Session) -> Optional[str]:
    """Try the undocumented frontend lookup. Returns UUID or None."""
    try:
        s.get("https://calendly.com/api/booking/initial_settings", timeout=15)
        r = s.get("https://calendly.com/api/booking/event_types/lookup",
                  params={"owner": owner, "event_type_slug": slug}, timeout=20)
        if not r.ok:
            return None
        j = r.json()
        et = j.get("event_type") or {}
        u = (et.get("uuid") or "").lower()
        return u or None
    except requests.RequestException:
        return None

def slug_variants(slug: str) -> List[str]:
    """Generate a few smart variants: 30min -> 30-min / 30-minute, etc."""
    out = [slug]
    m = re.fullmatch(r"(\d+)(min|mins|minute|minutes|hr|hour|hours)", slug)
    if m:
        n, unit = m.groups()
        if unit.startswith("min"):
            out += [f"{n}-min", f"{n}-minute", f"{n}min", f"{n}-minutes"]
        elif unit in ("hr", "hour", "hours"):
            out += [f"{n}-hour", f"{n}hr", f"{n}-hours"]
    # generic helpers
    if slug.endswith("min") and not slug.endswith("-min"):
        out.append(slug.replace("min", "-min"))
    if slug.endswith("mins") and not slug.endswith("-mins"):
        out.append(slug.replace("mins", "-mins"))
    if slug == "30-min":
        out.append("30min")
    if slug == "30min":
        out.append("30-min")
    # de-dupe preserve order
    seen = set()
    dedup = []
    for s in out:
        if s not in seen:
            dedup.append(s); seen.add(s)
    return dedup

def fetch_html(url: str, s: requests.Session) -> Optional[str]:
    try:
        r = s.get(url, allow_redirects=True, timeout=30)
        if r.ok:
            return r.text
    except requests.RequestException:
        pass
    return None

def discover_uuid_from_html(html: str) -> Optional[str]:
    # Prefer __NEXT_DATA__ scan
    m = NEXT_RE.search(html or "")
    if m:
        try:
            data = json.loads(m.group("json"))
            txt = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
            m2 = UUID_RE.search(txt)
            if m2:
                return m2.group(1).lower()
        except Exception:
            pass
    # Fallback: raw HTML regex
    m = UUID_RE.search(html or "")
    return m.group(1).lower() if m else None

def fetch_range(origin: str, uuid: str, tz: str, start: str, end: str,
                s: requests.Session, scheduling_link_uuid: Optional[str] = None) -> Dict[str, Any]:
    base = f"{origin}/api/booking/event_types/{uuid}/calendar/range"
    params = {"timezone": tz, "diagnostics": "false", "range_start": start, "range_end": end}
    if scheduling_link_uuid:
        params["scheduling_link_uuid"] = scheduling_link_uuid
    r = s.get(base, params=params, timeout=30)
    j = r.json() if r.headers.get("content-type","").startswith("application/json") else {"_text": r.text}
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code}: {json.dumps(j)[:400]}")
    return j

def available_days(payload: Dict[str, Any]) -> List[str]:
    return [d.get("date") for d in payload.get("days", []) if d.get("status") == "available"]

def iso_to_hhmm(ts: str, tzname: Optional[str]) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if tzname and ZoneInfo:
            dt = dt.astimezone(ZoneInfo(tzname))
        return dt.strftime("%H:%M")
    except Exception:
        return ts[11:16] if len(ts) >= 16 else ts

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

def main():
    ap = argparse.ArgumentParser(description="Calendly event → UUID → dates → hours (no DevTools)")
    ap.add_argument("event_url", help="https://calendly.com/<owner>/<slug>[?...]")
    ap.add_argument("--tz", default="America/New_York", help="IANA timezone for output")
    ap.add_argument("--start", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--end", help="YYYY-MM-DD (default: start+21d)")
    ap.add_argument("--date", help="Fetch hours only for this date (YYYY-MM-DD)")
    ap.add_argument("--hours", action="store_true", help="Fetch hours for each available day in the range")
    ap.add_argument("--sleep", type=float, default=0.35, help="Delay between per-day requests")
    ap.add_argument("--show-json", action="store_true", help="Dump JSON payloads")
    args = ap.parse_args()

    today = date.today()
    start = args.start or today.isoformat()
    end   = args.end or (today + timedelta(days=21)).isoformat()

    origin, owner, slug = parse_event_url(args.event_url)
    s = build_session(args.event_url)

    # 1) Resolve UUID via lookup, trying smart variants if needed
    uuid = None
    for candidate in slug_variants(slug):
        uuid = lookup_uuid(owner, candidate, s)
        if uuid:
            slug = candidate
            break

    # 2) If lookup failed, parse the event page HTML for a UUID
    if not uuid:
        html = fetch_html(args.event_url, s)
        uuid = discover_uuid_from_html(html) if html else None

    if not uuid:
        print(f"Could not discover event_type UUID from {owner}/{slug}", file=sys.stderr)
        sys.exit(2)

    # Single-day fetch?
    if args.date:
        d0, d1 = one_day_window(args.date)
        day = fetch_range(origin, uuid, args.tz, d0, d1, s)
        if args.show_json:
            print("\n=== DAY RAW JSON ===")
            print(json.dumps(day, indent=2))
        times = times_from_range(day, args.tz)
        print(f"{args.date}: {', '.join(times.get(args.date, [])) or '(no time slots)'}")
        return

    # Range fetch
    rng = fetch_range(origin, uuid, args.tz, start, end, s)
    if args.show_json:
        print("\n=== RANGE RAW JSON ===")
        print(json.dumps(rng, indent=2))

    days = available_days(rng)
    print(f"Event: {owner}/{slug}")
    print(f"UUID:  {uuid}")
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

    if args.hours and days:
        print("\nTimes (per-day windows):")
        for d in sorted(days):
            d0, d1 = one_day_window(d)
            day = fetch_range(origin, uuid, args.tz, d0, d1, s)
            if args.show_json:
                print("\n=== DAY RAW JSON ===")
                print(json.dumps(day, indent=2))
            t = times_from_range(day, args.tz)
            print(f"  {d}: {', '.join(t.get(d, [])) or '(no time slots)'}")
            time.sleep(args.sleep)

if __name__ == "__main__":
    main()
