#!/usr/bin/env python3
"""
From a Calendly profile URL (https://calendly.com/<owner>), discover event links (meeting types),
resolve each event's UUID, then fetch available days and times in a requested date range.

No DevTools. No headless. Uses public frontend endpoints Calendly pages hit themselves.

Limitations:
- If a profile lists *no* public events (everything is "secret"), you won't see links to parse.
  In that case you need at least one known event URL (owner/slug) or a short link to proceed.
"""

import argparse, json, re, sys, time
from datetime import date, timedelta, datetime
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse, urljoin, parse_qs

import requests

try:
    from zoneinfo import ZoneInfo  # py>=3.9
except Exception:
    ZoneInfo = None

A_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)
UUID_RE = re.compile(r"event_types/([0-9a-fA-F-]{36})")
NEXT_RE = re.compile(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(?P<json>.*?)</script>', re.S)

def build_session(ref: Optional[str] = None) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": ref or "https://calendly.com/",
    })
    # Warm the booking session like the browser (ignore failures)
    try:
        s.get("https://calendly.com/api/booking/initial_settings", timeout=15)
    except requests.RequestException:
        pass
    return s

def get_text(url: str, s: requests.Session) -> Tuple[str, str]:
    r = s.get(url, allow_redirects=True, timeout=30)
    r.raise_for_status()
    return r.text, r.url

def owner_from_url(u: str) -> Tuple[str, str]:
    p = urlparse(u)
    origin = f"{p.scheme}://{p.netloc}"
    parts = [x for x in p.path.split("/") if x]
    if not parts:
        raise SystemExit(f"Not a Calendly profile URL: {u}")
    owner = parts[0] if parts[0] != "s" else parts[1]  # shortlinks redirect; we follow get_text() anyway
    return origin, owner

def find_event_links(profile_html: str, origin: str, owner: str) -> List[str]:
    """Extract /owner/<slug> links from the profile HTML."""
    links = set()
    for href in A_RE.findall(profile_html):
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        full = urljoin(origin + "/", href.lstrip("/"))
        p = urlparse(full)
        parts = [x for x in p.path.split("/") if x]
        if len(parts) >= 2 and p.netloc.endswith("calendly.com") and parts[0] == owner:
            # keep only canonical /owner/slug (ignore deeper paths)
            links.add(f"{p.scheme}://{p.netloc}/{parts[0]}/{parts[1]}")
    return sorted(links)

def parse_next_data(html: str) -> Optional[Dict[str, Any]]:
    m = NEXT_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group("json"))
    except Exception:
        return None

def uuid_from_event_html(html: str) -> Optional[str]:
    # Try embedded Next.js JSON first
    j = parse_next_data(html)
    if j:
        txt = json.dumps(j, separators=(",", ":"), ensure_ascii=False)
        m = UUID_RE.search(txt)
        if m:
            return m.group(1).lower()
    # Fallback: regex over raw HTML
    m = UUID_RE.search(html)
    return m.group(1).lower() if m else None

def lookup_uuid(owner: str, slug: str, s: requests.Session) -> Optional[str]:
    """Undocumented frontend lookup used by the web app."""
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

def fetch_range(origin: str, uuid: str, tz: str, start: str, end: str,
                s: requests.Session, scheduling_short: Optional[str] = None) -> Dict[str, Any]:
    base = f"{origin}/api/booking/event_types/{uuid}/calendar/range"
    params = {
        "timezone": tz,
        "diagnostics": "false",
        "range_start": start,
        "range_end": end,
    }
    if scheduling_short:
        params["scheduling_link_uuid"] = scheduling_short
    r = s.get(base, params=params, timeout=30)
    try:
        j = r.json()
    except Exception:
        raise RuntimeError(f"Non-JSON ({r.status_code}) from {base}")
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code}: {json.dumps(j)[:400]}")
    return j

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

def day_window(d: str) -> Tuple[str, str]:
    x = date.fromisoformat(d)
    return x.isoformat(), (x + timedelta(days=1)).isoformat()

def main():
    ap = argparse.ArgumentParser(description="Calendly profile → event types → dates & hours")
    ap.add_argument("profile_url", help="https://calendly.com/<owner>")
    ap.add_argument("--tz", default="America/New_York", help="IANA timezone for output")
    ap.add_argument("--start", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--end", help="YYYY-MM-DD (default: start+21d)")
    ap.add_argument("--hours", action="store_true", help="Fetch hours for each available day (1-day windows)")
    ap.add_argument("--sleep", type=float, default=0.35, help="Delay between per-day requests")
    ap.add_argument("--show-json", action="store_true", help="Dump raw JSON payloads")
    args = ap.parse_args()

    today = date.today()
    start = args.start or today.isoformat()
    end   = args.end or (today + timedelta(days=21)).isoformat()

    origin, owner = owner_from_url(args.profile_url)
    s = build_session(args.profile_url)

    # 1) Pull profile page and mine event links
    html, final = get_text(f"{origin}/{owner}", s)
    events = find_event_links(html, origin, owner)

    if not events:
        print("No event links were discoverable on the profile page.")
        print("If events are secret, you need an event URL (owner/slug) or short link to proceed.")
        sys.exit(2)

    print(f"Discovered {len(events)} event(s):")
    for ev in events:
        print("  ", ev)

    print("\nCollecting availability…")
    all_results = []  # (event_url, uuid, {day: [times...]})

    for ev in events:
        p = urlparse(ev)
        parts = [x for x in p.path.split("/") if x]
        slug = parts[1] if len(parts) >= 2 else None

        # 2) Resolve UUID: lookup first, then parse event HTML
        uuid = lookup_uuid(owner, slug, s) if slug else None
        if not uuid:
            ev_html, _ = get_text(ev, s)
            uuid = uuid_from_event_html(ev_html)

        if not uuid:
            print(f"\n[WARN] Could not resolve UUID for {ev}. Skipping.")
            continue

        # 3) Fetch range
        try:
            rng = fetch_range(origin, uuid, args.tz, start, end, s)
        except Exception as e:
            print(f"\n[ERROR] range fetch failed for {ev}: {e}")
            continue

        if args.show_json:
            print("\n=== RANGE RAW JSON ===")
            print(json.dumps(rng, indent=2))

        days = available_days(rng)
        print(f"\nEvent: {ev}")
        print(f"UUID:  {uuid}")
        if days:
            print("Available days:")
            for d in sorted(days):
                print("  ", d)
        else:
            print("  (no available days)")

        times_map = times_from_range(rng, args.tz)

        if args.hours:
            # Re-query each day as a 1-day window to coax times if needed
            for d in sorted(days):
                if times_map.get(d):
                    continue  # already have times from range payload
                d0, d1 = day_window(d)
                try:
                    day = fetch_range(origin, uuid, args.tz, d0, d1, s)
                    if args.show_json:
                        print("\n=== DAY RAW JSON ===")
                        print(json.dumps(day, indent=2))
                    t = times_from_range(day, args.tz)
                    if t.get(d):
                        times_map[d] = t[d]
                    else:
                        times_map.setdefault(d, [])
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
        all_results.append((ev, uuid, times_map))

if __name__ == "__main__":
    main()
