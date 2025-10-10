#!/usr/bin/env python3
import asyncio, argparse, json, re, sys, time
from datetime import date, timedelta, datetime as _dt
from typing import List, Tuple, Optional, Dict, Any
from urllib.parse import urlparse, urljoin, parse_qs

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# =========================
# Requests helpers
# =========================
def build_session(ref: Optional[str] = None) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": ref or "https://calendly.com/",
    })
    try:
        s.get("https://calendly.com/api/booking/initial_settings", timeout=15)
    except requests.RequestException:
        pass
    return s

def get_text(url: str, s: requests.Session) -> Tuple[str, str]:
    r = s.get(url, allow_redirects=True, timeout=30)
    r.raise_for_status()
    return r.text, r.url

def owner_from_profile(u: str) -> Tuple[str, str]:
    p = urlparse(u)
    origin = f"{p.scheme}://{p.netloc}"
    parts = [x for x in p.path.split("/") if x]
    if not parts:
        raise SystemExit(f"Not a Calendly URL: {u}")
    owner = parts[0] if parts[0] != "s" else parts[1]
    return origin, owner

# =========================
# Discover event links (static first, then rendered DOM)
# =========================
def find_event_links_static(profile_html: str, origin: str, owner: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(profile_html, "lxml")
    out: List[Tuple[str, str]] = []
    for a in soup.select('a[data-id="event-type"]'):
        href = a.get("href")
        if not href:
            continue
        full = urljoin(origin + "/", href.lstrip("/"))
        p = urlparse(full)
        parts = [x for x in p.path.split("/") if x]
        if len(parts) >= 2 and p.netloc.endswith("calendly.com") and parts[0] == owner:
            ev_url = f"{p.scheme}://{p.netloc}/{parts[0]}/{parts[1]}"  # strip query
            title_el = a.select_one('[data-id="event-type-header-title"]')
            title = title_el.get_text(strip=True) if title_el else a.get_text(" ", strip=True)
            out.append((ev_url, title))
    # de-dupe
    seen, dedup = set(), []
    for u, t in out:
        if u not in seen:
            dedup.append((u, t)); seen.add(u)
    return dedup

async def find_event_links_rendered(profile_url: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(profile_url, wait_until="domcontentloaded")
        # Query rendered anchors
        links = page.locator('a[data-id="event-type"]')
        count = await links.count()
        for i in range(count):
            a = links.nth(i)
            href = await a.get_attribute("href")
            title_node = a.locator('[data-id="event-type-header-title"]').first
            title = (await title_node.text_content()) if await title_node.count() else (await a.text_content())
            if href:
                # make absolute, strip query
                purl = urlparse(profile_url)
                absu = urljoin(f"{purl.scheme}://{purl.netloc}/", href.lstrip("/")).split("?")[0]
                out.append((absu, (title or "").strip()))
        await browser.close()
    # de-dupe
    seen, dedup = set(), []
    for u, t in out:
        if u not in seen:
            dedup.append((u, t)); seen.add(u)
    return dedup

# =========================
# UUID resolution (lookup → HTML/JS → network sniff)
# =========================
UUID_RE  = re.compile(r"event_types/([0-9a-fA-F-]{36})")
NEXT_RE  = re.compile(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(?P<json>.*?)</script>', re.S)
UUID_URL_RE = re.compile(r"/api/booking/event_types/([0-9a-fA-F-]{36})/calendar/range")

def parse_event_url(u: str) -> Tuple[str, str, str]:
    p = urlparse(u)
    parts = [x for x in p.path.split("/") if x]
    if len(parts) < 2:
        raise SystemExit(f"Not an event URL: {u}")
    origin = f"{p.scheme}://{p.netloc}"
    return origin, parts[0], parts[1]

def lookup_uuid(owner: str, slug: str, s: requests.Session, referer: str) -> Optional[str]:
    try:
        old_ref = s.headers.get("Referer"); s.headers["Referer"] = referer
        s.get("https://calendly.com/api/booking/initial_settings", timeout=15)
        r = s.get("https://calendly.com/api/booking/event_types/lookup",
                  params={"owner": owner, "event_type_slug": slug}, timeout=20)
        s.headers["Referer"] = old_ref or "https://calendly.com/"
        if not r.ok:
            return None
        j = r.json(); et = j.get("event_type") or {}
        u = (et.get("uuid") or "").lower()
        return u or None
    except requests.RequestException:
        return None

def discover_uuid_from_event_html(event_url: str, s: requests.Session) -> Optional[str]:
    try:
        html, _ = get_text(event_url, s)
    except Exception:
        return None
    # Try __NEXT_DATA__ first
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
    # Raw HTML regex fallback
    m = UUID_RE.search(html or "")
    return m.group(1).lower() if m else None

async def sniff_uuid_and_short(event_url: str, sniff_wait: float = 6.0) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        found_uuid = None
        sched_short = None
        origin = None

        def on_response(resp):
            nonlocal found_uuid, sched_short, origin
            url = resp.url
            if ("calendly.com" in url) and ("/api/booking/event_types/" in url) and ("/calendar/range" in url):
                m = UUID_URL_RE.search(url)
                if m:
                    found_uuid = m.group(1).lower()
                    q = parse_qs(urlparse(url).query)
                    sched_short = (q.get("scheduling_link_uuid") or [None])[0]
                    o = urlparse(url)
                    origin = f"{o.scheme}://{o.netloc}"

        page.on("response", on_response)
        await page.goto(event_url, wait_until="domcontentloaded")

        # Click first available date to provoke XHR
        try:
            btn = page.locator('button[aria-label*="Times available"]').first
            if await btn.count():
                await btn.click(timeout=3000)
        except Exception:
            pass

        # Try advancing months a bit if no availability visible
        if not found_uuid:
            for _ in range(3):
                try:
                    next_btn = page.get_by_role("button", name=re.compile("Next", re.I))
                    if await next_btn.count():
                        await next_btn.click(timeout=2000)
                        await page.wait_for_timeout(500)
                        btn2 = page.locator('button[aria-label*="Times available"]').first
                        if await btn2.count():
                            await btn2.click(timeout=3000)
                            break
                except Exception:
                    break

        await page.wait_for_timeout(int(sniff_wait * 1000))
        await browser.close()
        return origin, found_uuid, sched_short

# =========================
# Range API + parsing + fallbacks
# =========================
def _fetch_range_once(origin: str, uuid: str, tz: str, start: str, end: str,
                      s: requests.Session, sched_short: Optional[str]) -> Dict[str, Any]:
    base = f"{origin}/api/booking/event_types/{uuid}/calendar/range"
    params = {"timezone": tz, "diagnostics": "false", "range_start": start, "range_end": end}
    if sched_short:
        params["scheduling_link_uuid"] = sched_short
    r = s.get(base, params=params, timeout=30)
    try:
        j = r.json()
    except Exception:
        r.raise_for_status()
        raise
    if not r.ok:
        msg = j.get("message") if isinstance(j, dict) else None
        raise RuntimeError(f"HTTP {r.status_code} for {base} details={msg or j}")
    return j

def fetch_range_with_fallbacks(origin: str, uuid: str, tz: str,
                               start: str, end: str,
                               s: requests.Session,
                               sched_short: Optional[str]) -> Dict[str, Any]:
    try:
        return _fetch_range_once(origin, uuid, tz, start, end, s, sched_short)
    except RuntimeError as e:
        if "HTTP 400" in str(e):
            return _fetch_range_once(origin, uuid, tz, start, end, s, None)
        raise

def chunk_windows(start: str, end: str, max_days: int = 30) -> List[Tuple[str, str]]:
    s = _dt.fromisoformat(start).date()
    e = _dt.fromisoformat(end).date()
    out = []
    cur = s
    while cur < e:
        nxt = min(cur + timedelta(days=max_days), e)
        out.append((cur.isoformat(), nxt.isoformat()))
        cur = nxt
    return out

def available_days(payload: Dict[str, Any]) -> List[str]:
    return [d.get("date") for d in payload.get("days", []) if d.get("status") == "available"]

def iso_to_hhmm(iso: str, tzname: Optional[str]) -> str:
    try:
        from zoneinfo import ZoneInfo
        dt = _dt.fromisoformat(iso.replace("Z", "+00:00"))
        dt = dt.astimezone(ZoneInfo(tzname)) if tzname else dt
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

async def scrape_times_from_dom(event_url: str, target_date_iso: str) -> List[str]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await p.chromium.launch_persistent_context if False else await p.chromium.launch
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(event_url, wait_until="domcontentloaded")
        day_text = str(_dt.fromisoformat(target_date_iso).day)
        try:
            btn = page.locator('button[aria-label*="Times available"]').filter(has_text=day_text).first
            if await btn.count() == 0:
                btn = page.get_by_role("button", name=day_text).first
            if await btn.count():
                await btn.click(timeout=3000)
        except Exception:
            pass
        times = []
        try:
            entries = await page.locator('[data-container="time-button"]').all_text_contents()
            times = [t.strip() for t in entries if t.strip()]
        except Exception:
            pass
        await browser.close()
        return times

# =========================
# Orchestration
# =========================
async def run(args):
    s = build_session(args.url)
    p = urlparse(args.url)
    parts = [x for x in p.path.split("/") if x]
    is_profile = (len(parts) == 1)

    # 1) Discover event links
    events: List[Tuple[str, str]] = []
    if is_profile:
        origin, owner = owner_from_profile(args.url)
        html, _ = get_text(f"{origin}/{owner}", s)
        events = find_event_links_static(html, origin, owner)
        if not events:
            print("[i] No event links in static HTML. Trying rendered DOM…")
            events = await find_event_links_rendered(args.url)
        if not events:
            print("No event links discoverable. If events are secret, you need a direct event URL.")
            sys.exit(2)
    else:
        # Direct event given
        events = [(args.url.split("?")[0], "(event)")]

    # 2) Time window
    start = args.start or date.today().isoformat()
    end   = args.end   or (date.fromisoformat(start) + timedelta(days=21)).isoformat()

    # 3) For each event, resolve uuid (lookup → html → sniff), then fetch availability
    for ev_url, title in events:
        print(f"\n=== EVENT: {title} :: {ev_url}")
        origin, owner, slug = parse_event_url(ev_url)

        # 3a) Try lightweight uuid resolution
        uuid = lookup_uuid(owner, slug, s, referer=ev_url)
        sched = None

        if not uuid:
            uuid = discover_uuid_from_event_html(ev_url, s)

        # 3b) Sniff if still missing (gets sched_short too)
        if not uuid:
            print("  [i] UUID not in lookup/HTML. Sniffing network…")
            origin2, uuid2, sched2 = await sniff_uuid_and_short(ev_url, sniff_wait=args.sniff_wait)
            if uuid2:
                uuid, sched = uuid2, sched2
                origin = origin2 or origin

        if not uuid:
            print("  [!] Could not resolve event_type_uuid. Skipping.")
            continue

        print(f"  UUID: {uuid}")
        if sched: print(f"  scheduling_link_uuid: {sched}")

        # 4) Range fetch in chunks (≤30 days) with sched_short fallback
        merged: Dict[str, Any] = {"days": []}
        for s0, s1 in chunk_windows(start, end, max_days=30):
            try:
                part = fetch_range_with_fallbacks(origin, uuid, args.tz, s0, s1, s, sched)
                if isinstance(part, dict) and "days" in part:
                    merged["days"].extend(part["days"])
            except Exception as e:
                print(f"  [WARN] window {s0}..{s1} failed: {e}")

        rng = merged
        days = sorted(set(available_days(rng)))
        if not days:
            print(f"  Days [{start}..{end}): (none)")
        else:
            print(f"  Days [{start}..{end}):")
            for d in days: print(f"    {d}")

        # 5) Any times already in the range payload?
        direct = times_from_range(rng, args.tz)
        if direct:
            print("  Times (from range payload):")
            for d in sorted(direct):
                print(f"    {d}: {', '.join(direct[d])}")

        # 6) Per-day windows; DOM fallback if API withholds slots
        if args.hours and days:
            print("  Times (per-day windows):")
            for d in days:
                if direct.get(d):
                    print(f"    {d}: {', '.join(direct[d])}")
                    continue
                d0, d1 = one_day_window(d)
                try:
                    day = fetch_range_with_fallbacks(origin, uuid, args.tz, d0, d1, s, sched)
                    tmap = times_from_range(day, args.tz)
                    slots = tmap.get(d, [])
                    if not slots:
                        # DOM fallback (scrape visible time buttons)
                        slots = await scrape_times_from_dom(ev_url, d)
                    print(f"    {d}: {', '.join(slots) or '(no time slots)'}")
                except Exception as e:
                    print(f"    {d}: ERROR -> {e}")
                time.sleep(args.sleep)

def main():
    ap = argparse.ArgumentParser(description="Calendly profile autodiscover → event URLs → UUID → dates & hours")
    ap.add_argument("url", help="Profile URL (https://calendly.com/<owner>) or specific event URL (https://calendly.com/<owner>/<slug>)")
    ap.add_argument("--tz", default="America/New_York", help="IANA timezone for output")
    ap.add_argument("--start", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--end", help="YYYY-MM-DD (default: start+21d)")
    ap.add_argument("--hours", action="store_true", help="Fetch hours by re-querying each available day; DOM fallback if needed")
    ap.add_argument("--sleep", type=float, default=0.35, help="Delay between per-day calls")
    ap.add_argument("--sniff-wait", type=float, default=6.0, help="Seconds to wait for XHRs while sniffing UUIDs")
    args = ap.parse_args()
    asyncio.run(run(args))

if __name__ == "__main__":
    main()
