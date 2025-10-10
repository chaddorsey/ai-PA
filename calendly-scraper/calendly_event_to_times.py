#!/usr/bin/env python3
import argparse, json, re, sys, time
from datetime import date, datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

try:
    from zoneinfo import ZoneInfo  # py>=3.9
except Exception:
    ZoneInfo = None

UUID_RE  = re.compile(r"event_types/([0-9a-fA-F-]{36})")
NEXT_RE  = re.compile(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(?P<json>.*?)</script>', re.S)

def build_session(referer: Optional[str]) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": referer or "https://calendly.com/",
    })
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

def lookup_uuid(owner: str, slug: str, s: requests.Session, referer: str) -> Optional[str]:
    try:
        old_ref = s.headers.get("Referer"); s.headers["Referer"] = referer
        s.get("https://calendly.com/api/booking/initial_settings", timeout=15)
        r = s.get("https://calendly.com/api/booking/event_types/lookup",
                  params={"owner": owner, "event_type_slug": slug}, timeout=20)
        s.headers["Referer"] = old_ref or "https://calendly.com/"
        if not r.ok:
            return None
        j = r.json()
        et = j.get("event_type") or {}
        u = (et.get("uuid") or "").lower()
        return u or None
    except requests.RequestException:
        return None

def fetch_text(url: str, s: requests.Session) -> str:
    r = s.get(url, allow_redirects=True, timeout=30)
    r.raise_for_status()
    return r.text

def discover_uuid_from_html(html: str) -> Optional[str]:
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
    m = UUID_RE.search(html or "")
    return m.group(1).lower() if m else None

def find_script_urls(html: str, base: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    urls = []
    for tag in soup.find_all(["script","link"]):
        src = tag.get("src") or tag.get("href")
        if not src: continue
        full = urljoin(base + "/", src.lstrip("/"))
        # only same-host assets, and probably Next static chunks
        if "calendly.com" in urlparse(full).netloc and "/_next/static/" in full:
            urls.append(full)
    # de-dupe preserve order
    seen = set(); out=[]
    for u in urls:
        if u not in seen:
            out.append(u); seen.add(u)
    return out[:20]  # safety cap

def discover_uuid_from_assets(event_url: str, html: str, s: requests.Session) -> Optional[str]:
    origin = f"{urlparse(event_url).scheme}://{urlparse(event_url).netloc}"
    for asset in find_script_urls(html, origin):
        try:
            txt = fetch_text(asset, s)
            m = UUID_RE.search(txt)
            if m:
                return m.group(1).lower()
        except Exception:
            continue
    return None

def fetch_range(origin: str, uuid: str, tz: str, start: str, end: str,
                s: requests.Session, scheduling_short: Optional[str] = None) -> Dict[str, Any]:
    base = f"{origin}/api/booking/event_types/{uuid}/calendar/range"
    params = {"timezone": tz, "diagnostics": "false", "range_start": start, "range_end": end}
    if scheduling_short:
        params["scheduling_link_uuid"] = scheduling_short
    r = s.get(base, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def available_days(payload: Dict[str, Any]) -> List[str]:
    return [d.get("date") for d in payload.get("days", []) if d.get("status") == "available"]

def iso_to_hhmm(iso: str, tzname: Optional[str]) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if tzname and ZoneInfo:
            dt = dt.astimezone(ZoneInfo(tzname))
        return dt.strftime("%H:%M")
    except Exception:
        return iso[11:16] if len(iso) >= 16 else iso

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
    ap = argparse.ArgumentParser(description="Calendly event → UUID → dates & hours (robust, no headless)")
    ap.add_argument("event_url", help="https://calendly.com/<owner>/<slug>[?...]")
    ap.add_argument("--tz", default="America/New_York")
    ap.add_argument("--start", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--end", help="YYYY-MM-DD (default: start+21d)")
    ap.add_argument("--hours", action="store_true", help="Fetch hours for every available day")
    ap.add_argument("--date", help="Fetch hours for a single date (YYYY-MM-DD)")
    ap.add_argument("--sleep", type=float, default=0.35)
    ap.add_argument("--show-json", action="store_true")
    args = ap.parse_args()

    today = date.today()
    start = args.start or today.isoformat()
    end   = args.end or (today + timedelta(days=21)).isoformat()

    origin, owner, slug = parse_event_url(args.event_url)
    s = build_session(args.event_url)

    # 1) Resolve UUID (three passes)
    uuid = lookup_uuid(owner, slug, s, referer=args.event_url)
    if not uuid:
        html = fetch_text(args.event_url, s)
        uuid = discover_uuid_from_html(html)
        if not uuid:
            uuid = discover_uuid_from_assets(args.event_url, html, s)

    if not uuid:
        print(f"Could not resolve UUID for {owner}/{slug}.", file=sys.stderr)
        sys.exit(2)

    # 2) Single-day hours?
    if args.date:
        d0, d1 = one_day_window(args.date)
        day = fetch_range(origin, uuid, args.tz, d0, d1, s)
        if args.show-json:
            print("\n=== DAY RAW JSON ==="); print(json.dumps(day, indent=2))
        t = times_from_range(day, args.tz)
        print(f"{args.date}: {', '.join(t.get(args.date, [])) or '(no time slots)'}")
        return

    # 3) Range → days (+ optional per-day hours)
    rng = fetch_range(origin, uuid, args.tz, start, end, s)
    if args.show-json:
        print("\n=== RANGE RAW JSON ==="); print(json.dumps(rng, indent=2))

    days = available_days(rng)
    print(f"Event: {owner}/{slug}")
    print(f"UUID:  {uuid}")
    print(f"\nAvailable days [{start} .. {end}):")
    if days:
        for d in sorted(days): print("  ", d)
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
            if direct.get(d):
                print(f"  {d}: {', '.join(direct[d])}")
                continue
            d0, d1 = one_day_window(d)
            day = fetch_range(origin, uuid, args.tz, d0, d1, s)
            t = times_from_range(day, args.tz)
            print(f"  {d}: {', '.join(t.get(d, [])) or '(no time slots)'}")
            time.sleep(args.sleep)

if __name__ == "__main__":
    main()
