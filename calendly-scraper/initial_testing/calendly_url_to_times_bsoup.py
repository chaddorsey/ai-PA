#!/usr/bin/env python3
import argparse, json, re, sys, time
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse, urljoin, urlunparse, parse_qs

import requests
from bs4 import BeautifulSoup

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

UUID_RE  = re.compile(r"event_types/([0-9a-fA-F-]{36})")
NEXT_RE  = re.compile(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(?P<json>.*?)</script>', re.S)

def build_session(ref: Optional[str] = None) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": ref or "https://calendly.com/",
    })
    # warm like browser (ignore failures)
    try: s.get("https://calendly.com/api/booking/initial_settings", timeout=15)
    except requests.RequestException: pass
    return s

def get_text(url: str, s: requests.Session) -> Tuple[str, str]:
    r = s.get(url, allow_redirects=True, timeout=30)
    r.raise_for_status()
    return r.text, r.url

def owner_from_url(u: str) -> Tuple[str, str]:
    p = urlparse(u); origin = f"{p.scheme}://{p.netloc}"
    parts = [x for x in p.path.split("/") if x]
    if not parts: raise SystemExit(f"Not a Calendly profile URL: {u}")
    owner = parts[0] if parts[0] != "s" else parts[1]
    return origin, owner

def strip_query(u: str) -> str:
    p = urlparse(u); return urlunparse((p.scheme,p.netloc,p.path,p.params,"",p.fragment))

def find_event_links_and_titles(profile_html: str, origin: str, owner: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(profile_html, "lxml")
    out: List[Tuple[str,str]] = []
    for a in soup.select('a[data-id="event-type"]'):
        href = a.get("href")
        if not href: continue
        full = urljoin(origin + "/", href.lstrip("/"))
        pp = urlparse(full); parts = [x for x in pp.path.split("/") if x]
        if len(parts) >= 2 and pp.netloc.endswith("calendly.com") and parts[0] == owner:
            title_el = a.select_one('[data-id="event-type-header-title"]')
            title = title_el.get_text(strip=True) if title_el else a.get_text(" ", strip=True)
            out.append((strip_query(f"{pp.scheme}://{pp.netloc}/{parts[0]}/{parts[1]}"), title))
    # de-dupe, keep first title
    seen = set(); dedup = []
    for url, title in out:
        if url not in seen:
            dedup.append((url, title)); seen.add(url)
    return dedup

def parse_next_json(html: str) -> Optional[Dict[str, Any]]:
    m = NEXT_RE.search(html or "")
    if not m: return None
    try: return json.loads(m.group("json"))
    except Exception: return None

def uuid_from_event_html(html: str) -> Optional[str]:
    j = parse_next_json(html)
    if j:
        txt = json.dumps(j, separators=(",", ":"), ensure_ascii=False)
        m = UUID_RE.search(txt)
        if m: return m.group(1).lower()
    m = UUID_RE.search(html or "")
    return m.group(1).lower() if m else None

def lookup_uuid(owner: str, slug: str, s: requests.Session, referer: str) -> Optional[str]:
    try:
        # set referer to the event page for this call (some stacks check it)
        old_ref = s.headers.get("Referer"); s.headers["Referer"] = referer
        s.get("https://calendly.com/api/booking/initial_settings", timeout=15)
        r = s.get("https://calendly.com/api/booking/event_types/lookup",
                  params={"owner": owner, "event_type_slug": slug}, timeout=20)
        s.headers["Referer"] = old_ref or "https://calendly.com/"
        if not r.ok: return None
        j = r.json(); et = j.get("event_type") or {}
        u = (et.get("uuid") or "").lower()
        return u or None
    except requests.RequestException:
        return None

def fetch_range(origin: str, uuid: str, tz: str, start: str, end: str,
                s: requests.Session, scheduling_short: Optional[str] = None) -> Dict[str, Any]:
    base = f"{origin}/api/booking/event_types/{uuid}/calendar/range"
    params = {"timezone": tz, "diagnostics": "false", "range_start": start, "range_end": end}
    if scheduling_short: params["scheduling_link_uuid"] = scheduling_short
    r = s.get(base, params=params, timeout=30); r.raise_for_status()
    return r.json()

def available_days(payload: Dict[str, Any]) -> List[str]:
    return [d.get("date") for d in payload.get("days", []) if d.get("status") == "available"]

def iso_to_hhmm(iso: str, tzname: Optional[str]) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if tzname and ZoneInfo: dt = dt.astimezone(ZoneInfo(tzname))
        return dt.strftime("%H:%M")
    except Exception:
        return iso[11:16] if len(iso) >= 16 else iso

def times_from_range(payload: Dict[str, Any], tzname: Optional[str]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for day in payload.get("days", []):
        if day.get("status") != "available": continue
        slots = []
        for spot in day.get("spots", []) or []:
            if isinstance(spot, dict):
                iso = spot.get("start_time") or spot.get("start") or spot.get("start_time_utc")
                if isinstance(iso, str): slots.append(iso_to_hhmm(iso, tzname))
        if slots: out[day["date"]] = sorted(set(slots))
    return dict(sorted(out.items()))

def day_window(d: str) -> Tuple[str, str]:
    x = date.fromisoformat(d); return x.isoformat(), (x + timedelta(days=1)).isoformat()

def main():
    ap = argparse.ArgumentParser(description="Calendly profile → meeting types → dates & hours (BS4)")
    ap.add_argument("profile_url", help="https://calendly.com/<owner>")
    ap.add_argument("--tz", default="America/New_York")
    ap.add_argument("--start", help="YYYY-MM-DD")
    ap.add_argument("--end", help="YYYY-MM-DD")
    ap.add_argument("--hours", action="store_true", help="Fetch hours for each available day via 1-day windows")
    ap.add_argument("--sleep", type=float, default=0.35)
    ap.add_argument("--show-json", action="store_true")
    args = ap.parse_args()

    today = date.today()
    start = args.start or today.isoformat()
    end   = args.end or (today + timedelta(days=21)).isoformat()

    origin, owner = owner_from_url(args.profile_url)
    s = build_session(args.profile_url)

    # 1) Pull profile and extract event links + titles
    html, final = get_text(f"{origin}/{owner}", s)
    events = find_event_links_and_titles(html, origin, owner)

    if not events:
        print("No event links were discoverable on the profile page.")
        print("If events are secret, provide a known event URL (/owner/slug) or short link.")
        sys.exit(2)

    print(f"Found {len(events)} event type(s):")
    for ev_url, title in events:
        print(f"  {title}  ->  {ev_url}")

    print("\nCollecting availability…")
    for ev_url, title in events:
        pp = urlparse(ev_url); parts = [x for x in pp.path.split("/") if x]
        slug = parts[1] if len(parts) >= 2 else None
        if not slug:
            print(f"\n[WARN] Could not parse slug from {ev_url}; skipping."); continue

        # 2) Resolve UUID: lookup first (with event referer), else parse event page
        uuid = lookup_uuid(owner, slug, s, referer=ev_url)
        if not uuid:
            ev_html, _ = get_text(ev_url, s)
            uuid = uuid_from_event_html(ev_html)

        if not uuid:
            print(f"\n[WARN] Could not resolve UUID for {ev_url}. Skipping.")
            continue

        # 3) Range fetch
        try:
            rng = fetch_range(origin, uuid, args.tz, start, end, s)
        except Exception as e:
            print(f"\n[ERROR] range fetch failed for {ev_url}: {e}")
            continue

        if args.show-json:
            print("\n=== RANGE RAW JSON ===")
            print(json.dumps(rng, indent=2))

        days = available_days(rng)
        print(f"\nEvent: {title}  ({ev_url})")
        print(f"UUID:  {uuid}")
        if days:
            print("Available days:")
            for d in sorted(days): print("  ", d)
        else:
            print("  (no available days)")

        times_map = times_from_range(rng, args.tz)

        # 4) Optional: 1-day windows to coax times
        if args.hours and days:
            for d in sorted(days):
                if times_map.get(d): continue
                d0, d1 = day_window(d)
                try:
                    day = fetch_range(origin, uuid, args.tz, d0, d1, s)
                    if args.show-json:
                        print("\n=== DAY RAW JSON ===")
                        print(json.dumps(day, indent=2))
                    t = times_from_range(day, args.tz)
                    if t.get(d): times_map[d] = t[d]
                    else: times_map.setdefault(d, [])
                except Exception as e:
                    print(f"  {d}: ERROR -> {e}", file=sys.stderr)
                time.sleep(args.sleep)

        if times_map:
            print("Times:")
            for d in sorted(times_map):
                if times_map[d]:
                    print(f"  {d}: {', '.join(times_map[d])}")
                else:
                    print(f"  {d}: (no time slots)")

if __name__ == "__main__":
    main()
