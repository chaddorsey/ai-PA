#!/usr/bin/env python3
import asyncio, argparse, json, re, sys, time
from datetime import date, timedelta, datetime as _dt
from typing import List, Tuple, Optional, Dict, Any
from urllib.parse import urlparse, urljoin, parse_qs

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# ---------- Requests helpers ----------

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

# ---------- Profile → event links (rendered DOM first, static fallback) ----------

def find_event_links_static(profile_html: str, origin: str, owner: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(profile_html, "lxml")
    out: List[Tuple[str, str]] = []
    for a in soup.select('a[data-id="event-type"]'):
        href = a.get("href")
        if not href: continue
        full = urljoin(origin + "/", href.lstrip("/"))
        p = urlparse(full)
        parts = [x for x in p.path.split("/") if x]
        if len(parts) >= 2 and p.netloc.endswith("calendly.com") and parts[0] == owner:
            ev_url = f"{p.scheme}://{p.netloc}/{parts[0]}/{parts[1]}"
            title_el = a.select_one('[data-id="event-type-header-title"]')
            title = title_el.get_text(strip=True) if title_el else a.get_text(" ", strip=True)
            out.append((ev_url, title))
    # de-dupe
    seen, dedup = set(), []
    for u, t in out:
        if u not in seen:
            dedup.append((u, t)); seen.add(u)
    return dedup

async def list_events_rendered(profile_url: str, wait: float = 8.0) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(profile_url, wait_until="domcontentloaded")

        # Try to dismiss cookie/GDPR if present (best-effort)
        for sel in [
            '#onetrust-accept-btn-handler',
            'button:has-text("Accept")',
            'button:has-text("Got it")',
            'button:has-text("I agree")',
        ]:
            try:
                btn = page.locator(sel)
                if await btn.count():
                    await btn.click(timeout=1500)
                    break
            except Exception:
                pass

        anchors = page.locator('a[data-id="event-type"]')
        try:
            await anchors.first.wait_for(timeout=int(wait * 1000))
        except Exception:
            pass

        count = await anchors.count()
        for i in range(count):
            a = anchors.nth(i)
            href = await a.get_attribute("href")
            title_node = a.locator('[data-id="event-type-header-title"]').first
            title = (await title_node.text_content()) if await title_node.count() else (await a.text_content())
            if href:
                purl = urlparse(profile_url)
                absu = urljoin(f"{purl.scheme}://{purl.netloc}/", href.lstrip("/")).split("?")[0]
                out.append((absu.strip(), (title or "").strip()))
        await browser.close()

    # de-dupe
    seen, dedup = set(), []
    for u, t in out:
        if u not in seen:
            dedup.append((u, t)); seen.add(u)
    return dedup

# ---------- UUID sniff (from XHR) ----------

UUID_URL_RE = re.compile(r"/api/booking/event_types/([0-9a-fA-F-]{36})/calendar/range")

async def sniff_uuid_and_short(event_url: str, sniff_wait: float = 6.0) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (origin, event_type_uuid, scheduling_link_uuid) by watching XHR."""
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

        # Click first available day to trigger a range XHR
        try:
            btn = page.locator('button[aria-label*="Times available"]').first
            if await btn.count():
                await btn.click(timeout=3000)
        except Exception:
            pass

        # If nothing yet, try advancing a few months and clicking
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

# ---------- Range API + times ----------

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

# ---------- Orchestration ----------

async def slots_for_profile_or_event(url: str, tz: str, start: str, end: str,
                                     sniff_wait: float, sleep: float) -> Dict[str, Any]:
    s = build_session(url)
    p = urlparse(url)
    parts = [x for x in p.path.split("/") if x]
    is_profile = (len(parts) == 1)

    # 1) Discover event links
    events: List[Tuple[str, str]] = []
    if is_profile:
        origin = f"{p.scheme}://{p.netloc}"
        owner = parts[0]
        html, _ = get_text(f"{origin}/{owner}", s)
        events = find_event_links_static(html, origin, owner)
        if not events:
            events = await list_events_rendered(url)
    else:
        events = [(url.split("?")[0], "(event)")]

    if not events:
        return {"events": []}

    results = {"events": []}

    # 2) For each event: sniff uuid → chunked range → per-day times
    for ev_url, title in events:
        origin2, uuid, sched = await sniff_uuid_and_short(ev_url, sniff_wait=sniff_wait)
        if not uuid:
            results["events"].append({"title": title, "url": ev_url, "error": "uuid_not_found"})
            continue

        merged: Dict[str, Any] = {"days": []}
        for s0, s1 in chunk_windows(start, end, max_days=30):
            try:
                part = fetch_range_with_fallbacks(origin2, uuid, tz, s0, s1, s, sched)
                if isinstance(part, dict) and "days" in part:
                    merged["days"].extend(part["days"])
            except Exception as e:
                merged.setdefault("_errors", []).append(f"window {s0}..{s1}: {e}")

        days = sorted(set(available_days(merged)))
        times_direct = times_from_range(merged, tz)

        per_day_times: Dict[str, List[str]] = dict(times_direct)
        for d in days:
            if per_day_times.get(d):
                continue
            d0, d1 = one_day_window(d)
            try:
                day = fetch_range_with_fallbacks(origin2, uuid, tz, d0, d1, s, sched)
                tmap = times_from_range(day, tz)
                per_day_times[d] = tmap.get(d, [])
            except Exception as e:
                per_day_times[d] = []
                merged.setdefault("_errors", []).append(f"{d}: {e}")
            time.sleep(sleep)

        results["events"].append({
            "title": title,
            "url": ev_url,
            "uuid": uuid,
            "scheduling_link_uuid": sched,
            "date_range": {"start": start, "end": end},
            "days": sorted(days),
            "times": {d: per_day_times.get(d, []) for d in sorted(per_day_times)},
            "range_errors": merged.get("_errors", []),
        })
    return results

async def main_async(args):
    start = args.start or date.today().isoformat()
    end   = args.end   or (date.fromisoformat(start) + timedelta(days=21)).isoformat()
    out = await slots_for_profile_or_event(args.url, args.tz, start, end, args.sniff_wait, args.sleep)

    # Pretty print to stdout
    for ev in out.get("events", []):
        print(f"\n=== {ev.get('title') or '(event)'} :: {ev['url']}")
        if "error" in ev:
            print(f"  ERROR: {ev['error']}")
            continue
        print(f"  UUID: {ev['uuid']}")
        if ev.get("scheduling_link_uuid"):
            print(f"  scheduling_link_uuid: {ev['scheduling_link_uuid']}")
        if ev.get("days"):
            print("  Days:")
            for d in ev["days"]:
                print(f"    {d}")
        tmap = ev.get("times", {})
        if tmap:
            print("  Times:")
            for d in sorted(tmap):
                if tmap[d]:
                    print(f"    {d}: {', '.join(tmap[d])}")
        if ev.get("range_errors"):
            print("  Notes:")
            for e in ev["range_errors"]:
                print(f"    {e}")

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\nSaved JSON → {args.out_json}")

def main():
    ap = argparse.ArgumentParser(description="Get all possible Calendly slots from a profile or event URL.")
    ap.add_argument("url", help="Profile URL (https://calendly.com/<owner>) or event URL (https://calendly.com/<owner>/<slug>)")
    ap.add_argument("--tz", default="America/New_York", help="IANA timezone for output (e.g., America/New_York)")
    ap.add_argument("--start", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--end", help="YYYY-MM-DD (default: start+21d)")
    ap.add_argument("--sleep", type=float, default=0.35, help="Delay between per-day calls")
    ap.add_argument("--sniff-wait", type=float, default=6.0, help="Seconds to wait for XHRs while sniffing UUIDs")
    ap.add_argument("--out-json", help="Write full JSON output to this path")
    args = ap.parse_args()
    asyncio.run(main_async(args))

if __name__ == "__main__":
    main()
