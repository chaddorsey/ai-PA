# calendly_letta_tool.py
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import date, timedelta, datetime as _dt
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urljoin, parse_qs

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from letta_client.client import BaseTool

# -------------------------------
# Utilities
# -------------------------------

def _run_async(coro):
    """Run an async coroutine from sync context safely."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# -------------------------------
# HTTP helpers (requests)
# -------------------------------

def build_session(ref: Optional[str] = None) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": ref or "https://calendly.com/",
    })
    try:
        # warm like a browser; ignore failures
        s.get("https://calendly.com/api/booking/initial_settings", timeout=15)
    except requests.RequestException:
        pass
    return s

def get_text(url: str, s: requests.Session) -> Tuple[str, str]:
    r = s.get(url, allow_redirects=True, timeout=30)
    r.raise_for_status()
    return r.text, r.url


# -------------------------------
# Profile → event discovery
# -------------------------------

def find_event_links_static(profile_html: str, origin: str, owner: str) -> List[Tuple[str, str]]:
    """Find event anchors in static HTML (when pre-rendered)."""
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

    # de-dupe preserve order
    seen, dedup = set(), []
    for u, t in out:
        if u not in seen:
            dedup.append((u, t)); seen.add(u)
    return dedup


# -------------------------------
# Playwright helpers (rendered DOM & XHR sniff)
# -------------------------------

# Import lazily so this module can be imported on systems without playwright
def _ensure_playwright():
    try:
        from playwright.async_api import async_playwright  # noqa: F401
        return True
    except Exception:
        return False

async def _list_events_rendered(profile_url: str, wait: float = 8.0) -> List[Tuple[str, str]]:
    """Render the profile in Chromium and scrape event links & titles."""
    from playwright.async_api import async_playwright

    out: List[Tuple[str, str]] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(profile_url, wait_until="domcontentloaded")

        # Best-effort cookie banners
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


UUID_URL_RE = re.compile(r"/api/booking/event_types/([0-9a-fA-F-]{36})/calendar/range")

async def _sniff_uuid_and_short(event_url: str, sniff_wait: float = 6.0) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (origin, event_type_uuid, scheduling_link_uuid) by watching calendar/range XHR."""
    from playwright.async_api import async_playwright

    found_uuid = None
    sched_short = None
    origin = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

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

        # Click an available day to trigger the XHR
        try:
            btn = page.locator('button[aria-label*="Times available"]').first
            if await btn.count():
                await btn.click(timeout=3000)
        except Exception:
            pass

        # If nothing yet, try advancing a few months and clicking again
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


# -------------------------------
# Range API & times
# -------------------------------

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

def _fetch_range_with_fallbacks(origin: str, uuid: str, tz: str,
                                start: str, end: str,
                                s: requests.Session,
                                sched_short: Optional[str]) -> Dict[str, Any]:
    try:
        return _fetch_range_once(origin, uuid, tz, start, end, s, sched_short)
    except RuntimeError as e:
        if "HTTP 400" in str(e):
            # Retry without scheduling_link_uuid when it causes a 400
            return _fetch_range_once(origin, uuid, tz, start, end, s, None)
        raise

def _chunk_windows(start: str, end: str, max_days: int = 30) -> List[Tuple[str, str]]:
    s = _dt.fromisoformat(start).date()
    e = _dt.fromisoformat(end).date()
    out = []
    cur = s
    while cur < e:
        nxt = min(cur + timedelta(days=max_days), e)
        out.append((cur.isoformat(), nxt.isoformat()))
        cur = nxt
    return out

def _available_days(payload: Dict[str, Any]) -> List[str]:
    return [d.get("date") for d in payload.get("days", []) if d.get("status") == "available"]

def _iso_to_hhmm(iso: str, tzname: Optional[str]) -> str:
    try:
        from zoneinfo import ZoneInfo
        dt = _dt.fromisoformat(iso.replace("Z", "+00:00"))
        dt = dt.astimezone(ZoneInfo(tzname)) if tzname else dt
        return dt.strftime("%H:%M")
    except Exception:
        return iso[11:16] if len(iso) >= 16 else iso

def _times_from_range(payload: Dict[str, Any], tzname: Optional[str]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for day in payload.get("days", []):
        if day.get("status") != "available":
            continue
        slots = []
        for spot in day.get("spots", []) or []:
            if isinstance(spot, dict):
                iso = spot.get("start_time") or spot.get("start") or spot.get("start_time_utc")
                if isinstance(iso, str):
                    slots.append(_iso_to_hhmm(iso, tzname))
        if slots:
            out[day["date"]] = sorted(set(slots))
    return dict(sorted(out.items()))

def _one_day_window(d: str) -> Tuple[str, str]:
    x = date.fromisoformat(d)
    return x.isoformat(), (x + timedelta(days=1)).isoformat()


# -------------------------------
# Core coroutine used by the tool
# -------------------------------

async def _collect_slots(url: str, tz: str, start: str, end: str,
                         sniff_wait: float, sleep: float) -> Dict[str, Any]:
    """
    Given a public Calendly profile or event URL, return all available days & times.
    """
    if not _ensure_playwright():
        return {"error": "playwright_not_installed", "hint": "pip install playwright && playwright install chromium"}

    s = build_session(url)
    p = urlparse(url)
    parts = [x for x in p.path.split("/") if x]
    is_profile = (len(parts) == 1)

    # 1) Discover event URLs
    events: List[Tuple[str, str]] = []
    if is_profile:
        origin = f"{p.scheme}://{p.netloc}"
        owner = parts[0]
        html, _ = get_text(f"{origin}/{owner}", s)
        events = find_event_links_static(html, origin, owner)
        if not events:
            events = await _list_events_rendered(url)
    else:
        events = [(url.split("?")[0], "(event)")]

    if not events:
        return {"events": []}

    # 2) For each event: sniff UUID → chunked range → per-day times
    results = {"events": [], "query": {"url": url, "timezone": tz, "start": start, "end": end}}

    for ev_url, title in events:
        origin2, uuid, sched = await _sniff_uuid_and_short(ev_url, sniff_wait=sniff_wait)
        if not uuid:
            results["events"].append({"title": title, "url": ev_url, "error": "uuid_not_found"})
            continue

        merged: Dict[str, Any] = {"days": []}
        for s0, s1 in _chunk_windows(start, end, max_days=30):
            try:
                part = _fetch_range_with_fallbacks(origin2, uuid, tz, s0, s1, s, sched)
                if isinstance(part, dict) and "days" in part:
                    merged["days"].extend(part["days"])
            except Exception as e:
                merged.setdefault("_errors", []).append(f"window {s0}..{s1}: {e}")

        days = sorted(set(_available_days(merged)))
        times_direct = _times_from_range(merged, tz)

        per_day_times: Dict[str, List[str]] = dict(times_direct)
        for d in days:
            if per_day_times.get(d):
                continue
            d0, d1 = _one_day_window(d)
            try:
                day = _fetch_range_with_fallbacks(origin2, uuid, tz, d0, d1, s, sched)
                tmap = _times_from_range(day, tz)
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
            "days": days,
            "times": {d: per_day_times.get(d, []) for d in sorted(per_day_times)},
            "notes": merged.get("_errors", []),
        })
    return results


# -------------------------------
# Letta tool args & class
# -------------------------------

class CalendlySlotsArgs(BaseModel):
    url: str = Field(..., description="Calendly profile URL (https://calendly.com/<owner>) or event URL (https://calendly.com/<owner>/<slug>)")
    timezone: str = Field("America/New_York", description="IANA timezone for formatting times, e.g., America/New_York")
    start: Optional[str] = Field(None, description="Start date (YYYY-MM-DD). Defaults to today if omitted.")
    end: Optional[str] = Field(None, description="End date (YYYY-MM-DD). Defaults to start+21 days if omitted.")
    sniff_wait: float = Field(6.0, description="Seconds to wait for XHRs while sniffing UUIDs")
    per_day_delay: float = Field(0.35, description="Seconds to sleep between per-day API calls")

class CalendlySlotsTool(BaseTool):
    """
    Fetch all available Calendly slots (days & times) for a public profile or event.

    - Starts from a profile URL or event URL
    - Discovers event links (rendered DOM if needed)
    - Sniffs the page's calendar/range XHR to extract event_type UUID (+ optional scheduling_link_uuid)
    - Calls the same calendar/range endpoint in <=30-day chunks
    - For each available day, calls a 1-day window to retrieve times

    Returns:
        dict: JSON-serializable structure:
            {
              "query": { "url": ..., "timezone": ..., "start": ..., "end": ... },
              "events": [
                {
                  "title": str,
                  "url": str,
                  "uuid": str,
                  "scheduling_link_uuid": Optional[str],
                  "days": [ "YYYY-MM-DD", ... ],
                  "times": { "YYYY-MM-DD": ["HH:MM", ...], ... },
                  "notes": [ "...optional warnings..." ]
                },
                ...
              ]
            }

    Notes:
        - Requires playwright + chromium: `pip install playwright` then `playwright install chromium`
        - Respect Calendly's Terms of Service and rate limits.
    """
    name: str = "calendly_slots"
    description: str = "Get all available Calendly slots (days & times) for a public profile or event URL."
    args_schema = CalendlySlotsArgs

    def run(self,
            url: str,
            timezone: str = "America/New_York",
            start: Optional[str] = None,
            end: Optional[str] = None,
            sniff_wait: float = 6.0,
            per_day_delay: float = 0.35) -> Dict[str, Any]:

        # Default dates
        sdate = start or date.today().isoformat()
        edate = end or (date.fromisoformat(sdate) + timedelta(days=21)).isoformat()

        result = _run_async(_collect_slots(
            url=url,
            tz=timezone,
            start=sdate,
            end=edate,
            sniff_wait=sniff_wait,
            sleep=per_day_delay
        ))
        return result
