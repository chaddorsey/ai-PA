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

def find_event_links(profile_html: str, origin: str, owner: str) -> List[Tuple[str, str]]:
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
    # de-dupe, preserve order
    seen, dedup = set(), []
    for u, t in out:
        if u not in seen:
            dedup.append((u, t)); seen.add(u)
    return dedup

# =========================
# Playwright sniffers
# =========================
UUID_URL_RE = re.compile(r"/api/booking/event_types/([0-9a-fA-F-]{36})/calendar/range")

async def sniff_uuid_and_short(event_url: str, sniff_wait: float = 6.0) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (origin, event_type_uuid, scheduling_link_uuid) by watching XHR."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

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

        # Click an available date if visible to provoke XHR
        try:
            btn = page.locator('button[aria-label*="Times available"]').first
            if await btn.count():
                await btn.click(timeout=3000)
        except Exception:
            pass

        # If nothing yet, try to advance months a few times and click a bookable day
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

async def scrape_times_from_dom(event_url: str, target_date_iso: str) -> List[str]:
    """Fallback: click a day and read visible times from DOM."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(event_url, wait_until="domcontentloaded")

        day_text = str(_dt.fromisoformat(target_date_iso).day)

        try:
            # Prefer the aria-label one; otherwise any button named with the day number
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
# Range API + time parsing
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
    """Try with sched_short, then retry without it if we hit a 400."""
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

# =========================
# Orchestration
# =========================
async def run(args):
    s = build_session(args.profile_or_event)
    p = urlparse(args.profile_or_event)
    parts = [x for x in p.path.split("/") if x]

    # Determine mode: profile vs event
    if len(parts) == 1:
        origin, owner = owner_from_profile(args.profile_or_event)
        html, _ = get_text(f"{origin}/{owner}", s)
        events = find_event_links(html, origin, owner)
        if not events:
            print("No event links in profile HTML. If events are secret, use a direct event URL.")
            sys.exit(2)
    else:
        events = [(args.profile_or_event.split("?")[0], "(event)")]

    # Time window
    start = args.start or date.today().isoformat()
    end   = args.end   or (date.fromisoformat(start) + timedelta(days=21)).isoformat()

    for ev_url, title in events:
        print(f"\n=== EVENT: {title} :: {ev_url}")
        origin, uuid, sched = await sniff_uuid_and_short(ev_url, sniff_wait=args.sniff_wait)
        if not uuid:
            print("  [!] Could not sniff event_type_uuid from network. Try adding '?date=YYYY-MM-DD' to the URL or pick a month with availability.")
            continue

        print(f"  UUID: {uuid}")
        if sched:
            print(f"  scheduling_link_uuid: {sched}")

        # Range in chunks (≤30 days) with sched_short fallback
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
            for d in days:
                print(f"    {d}")

        # Any times already embedded?
        direct = times_from_range(rng, args.tz)
        if direct:
            print("  Times (from range payload):")
            for d in sorted(direct):
                print(f"    {d}: {', '.join(direct[d])}")

        # Per-day windows; DOM fallback if still empty
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
                        # DOM fallback (reads visible time buttons)
                        slots = await scrape_times_from_dom(ev_url, d)
                    print(f"    {d}: {', '.join(slots) or '(no time slots)'}")
                except Exception as e:
                    print(f"    {d}: ERROR -> {e}")
                time.sleep(args.sleep)

def main():
    ap = argparse.ArgumentParser(description="Calendly hybrid scraper: profile→events, sniff UUIDs, fetch days & hours (with fallbacks)")
    ap.add_argument("profile_or_event", help="Profile URL (https://calendly.com/<owner>) or event URL (https://calendly.com/<owner>/<slug>)")
    ap.add_argument("--tz", default="America/New_York", help="IANA timezone for output")
    ap.add_argument("--start", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--end", help="YYYY-MM-DD (default: start+21d)")
    ap.add_argument("--hours", action="store_true", help="Fetch hours by re-querying each available day; DOM fallback if needed")
    ap.add_argument("--sleep", type=float, default=0.35, help="Delay between per-day calls")
    ap.add_argument("--sniff-wait", type=float, default=6.0, help="Seconds to wait for XHRs while sniffing")
    args = ap.parse_args()
    asyncio.run(run(args))

if __name__ == "__main__":
    main()
