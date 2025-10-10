#!/usr/bin/env python3
"""
Book (claim) a Calendly slot by automating the event page.

Usage examples:
  python calendly_book_slot.py \
    "https://calendly.com/zarek-drozda/30min" \
    --date 2025-10-29 --time "3:30pm" \
    --name "Ada Lovelace" --email "ada@example.com" \
    --tz America/New_York \
    --answer "Company=Analytical Engines, Ltd" \
    --guest babbage@example.com \
    --json

  # 24h time works too:
  python calendly_book_slot.py "https://calendly.com/zarek-drozda/30min" \
    --date 2025-10-29 --time 15:30 --name "Ada" --email "ada@example.com"
"""

from __future__ import annotations
import asyncio, argparse, re, sys, json, time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime as _dt
from urllib.parse import urlparse
# ---- helpers to make async callable from sync ----
def _run(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            loop.close()

# ---------------------------------------------
# Core automation
# ---------------------------------------------
async def book_slot(
    event_url: str,
    date_iso: str,
    time_str: str,
    invitee_name: str,
    invitee_email: str,
    timezone: str,
    answers: Dict[str, str],
    guests: List[str],
    headless: bool,
    click_months_ahead: int,
    settle_ms: int,
) -> Dict[str, Any]:
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        return {"ok": False, "reason": "playwright_not_installed", "detail": str(e)}

    target_day = str(_dt.fromisoformat(date_iso).day)

    # Normalize input time and generate variants that may appear in buttons
    def _time_variants(t: str) -> List[str]:
        t = t.strip().lower()
        out = {t}
        try:
            if "am" in t or "pm" in t:
                dt = _dt.strptime(t.replace(" ", ""), "%I:%M%p")
                out.add(dt.strftime("%H:%M"))                  # 24h
            else:
                dt = _dt.strptime(t, "%H:%M")
                # Linux/OSX: %-I drops leading zero; on Windows %I keeps it
                out.add(dt.strftime("%-I:%M%p").lower()) if "%" in "%-I" else None
                out.add(dt.strftime("%I:%M%p").lower().lstrip("0"))
        except Exception:
            pass
        return [x for x in out if x]

    needles = _time_variants(time_str)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(timezone_id=timezone, locale="en-US")
        page = await ctx.new_page()

        await page.goto(event_url, wait_until="domcontentloaded")

        # Dismiss cookie/GDPR banners if present
        for sel in [
            '#onetrust-accept-btn-handler',
            'button:has-text("Accept")',
            'button:has-text("Got it")',
            'button:has-text("I agree")',
        ]:
            try:
                loc = page.locator(sel)
                if await loc.count():
                    await loc.click(timeout=1500)
                    break
            except Exception:
                pass

        # Helper: click desired day (first try aria-label contains "Times available", fallback to day text)
        async def click_day() -> bool:
            try:
                day_btn = page.locator('button[aria-label*="Times available"]').filter(has_text=target_day).first
                if await day_btn.count():
                    await day_btn.click(timeout=3000)
                    return True
            except Exception:
                pass
            try:
                day_btn2 = page.get_by_role("button", name=re.compile(rf"^\s*{re.escape(target_day)}\s*$"))
                if await day_btn2.count():
                    await day_btn2.first.click(timeout=3000)
                    return True
            except Exception:
                pass
            return False

        # Try clicking current month
        found_day = await click_day()

        # If not visible, click next month up to N times
        if not found_day:
            for _ in range(max(0, click_months_ahead)):
                try:
                    # standard Calendly "Next" or "Next month"
                    next_btn = page.get_by_role("button", name=re.compile("(Next|Next month)", re.I))
                    if await next_btn.count():
                        await next_btn.click(timeout=2500)
                        await page.wait_for_timeout(350)
                        if await click_day():
                            found_day = True
                            break
                except Exception:
                    break

        if not found_day:
            await browser.close()
            return {"ok": False, "reason": "date_not_found", "event_url": event_url, "date": date_iso, "time_requested": time_str}

        # Click target time
        clicked_time = False
        # (1) Fast path: data attribute
        for n in needles:
            try:
                btn = page.locator(f'[data-container="time-button"][data-start-time*="{n}"]').first
                if await btn.count():
                    await btn.click(timeout=3000)
                    clicked_time = True
                    break
            except Exception:
                pass
        # (2) Fallback: visible text search
        if not clicked_time:
            for n in needles:
                try:
                    btn = page.locator('[data-container="time-button"]').filter(has_text=re.compile(re.escape(n), re.I)).first
                    if await btn.count():
                        await btn.click(timeout=3000)
                        clicked_time = True
                        break
                except Exception:
                    pass

        if not clicked_time:
            await browser.close()
            return {"ok": False, "reason": "time_not_found", "event_url": event_url, "date": date_iso, "time_requested": time_str}

        # Form filling helpers
        async def fill_if_present(selectors: List[str], value: str) -> bool:
            for sel in selectors:
                try:
                    el = page.locator(sel).first
                    if await el.count():
                        await el.fill(value, timeout=2500)
                        return True
                except Exception:
                    pass
            return False

        async def fill_by_label(pattern: str, value: str) -> bool:
            try:
                el = page.get_by_label(re.compile(pattern, re.I))
                if await el.count():
                    await el.first.fill(value, timeout=2500)
                    return True
            except Exception:
                pass
            return False

        # Name & Email (common variants + label-based)
        ok_name = await fill_if_present(['input[name="name"]','input[name="full_name"]','input[name="first_name"]'], invitee_name) \
                  or await fill_by_label(r"(name|your name|full name|first name)", invitee_name)
        ok_mail = await fill_if_present(['input[name="email"]'], invitee_email) \
                  or await fill_by_label(r"(email)", invitee_email)

        # Optional: Add Guests if the event supports it
        if guests:
            try:
                add = page.get_by_role("button", name=re.compile("Add Guests", re.I))
                if await add.count():
                    await add.click(timeout=1500)
                    gi = page.locator('input[type="email"], input[autocomplete="email"]').first
                    for g in guests:
                        try:
                            if await gi.count():
                                await gi.fill(g)
                                await page.keyboard.press("Enter")
                        except Exception:
                            pass
            except Exception:
                pass

        # Optional: Custom questions (answers dict: label-substring -> value)
        if answers:
            labels = page.locator('[data-component="form"], [data-container="form-question"], form').locator("label")
            count = await labels.count()
            for i in range(count):
                try:
                    lab = (await labels.nth(i).text_content() or "").strip()
                except Exception:
                    continue
                for key, val in answers.items():
                    if key.lower() in lab.lower():
                        try:
                            container = labels.nth(i).locator("xpath=..")
                            inp = container.locator("input, textarea, select").first
                            if await inp.count():
                                tag = (await inp.evaluate("e => e.tagName")).lower()
                                if tag == "select":
                                    await inp.select_option(label=val)
                                else:
                                    await inp.fill(val)
                        except Exception:
                            pass

        # Submit
        submitted = False
        for name in ["Schedule", "Confirm", "Book", "Schedule Event", "Schedule now"]:
            try:
                btn = page.get_by_role("button", name=re.compile(name, re.I))
                if await btn.count():
                    await btn.first.click(timeout=5000)
                    submitted = True
                    break
            except Exception:
                pass

        if not submitted:
            await browser.close()
            return {"ok": False, "reason": "submit_button_not_found"}

        await page.wait_for_timeout(settle_ms)

        # Confirmation heuristics
        ok = False
        try:
            conf = page.get_by_text(re.compile("You (are|’re|re) scheduled|Event scheduled|You’re all set", re.I))
            ok = (await conf.count()) > 0
        except Exception:
            pass

        # Harvest details (URL + optional ICS link)
        current_url = page.url
        ics = None
        try:
            ics_link = page.locator('a[href$=".ics"], a[href*=".ics?"]').first
            if await ics_link.count():
                ics = await ics_link.get_attribute("href")
        except Exception:
            pass

        await browser.close()
        return {
            "ok": bool(ok),
            "event_url": event_url,
            "date": date_iso,
            "time_requested": time_str,
            "invitee_name": invitee_name,
            "invitee_email": invitee_email,
            "confirmation_url": current_url,
            "ics_url": ics,
            "reason": None if ok else "unknown_failure_after_submit"
        }

# ---------------------------------------------
# CLI
# ---------------------------------------------
def parse_kv_list(kv_list: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in kv_list or []:
        if "=" in item:
            k, v = item.split("=", 1)
            out[k.strip()] = v.strip()
    return out

def main():
    ap = argparse.ArgumentParser(
        description="Book (claim) a Calendly slot by selecting a date/time and submitting the form."
    )
    ap.add_argument("event_url", help="Calendly event URL, e.g. https://calendly.com/<owner>/<slug>")
    ap.add_argument("--date", required=True, help="Target date (YYYY-MM-DD) in host’s timezone.")
    ap.add_argument("--time", required=True, help='Target start time as "HH:MM" (24h) or "h:mma" (e.g., "3:30pm").')
    ap.add_argument("--name", required=True, dest="invitee_name", help="Invitee full name.")
    ap.add_argument("--email", required=True, dest="invitee_email", help="Invitee email.")
    ap.add_argument("--tz", default="America/New_York", dest="timezone", help="Browser timezone (IANA), e.g., America/New_York.")
    ap.add_argument("--answer", action="append", default=[], help='Custom Q&A in the form "LabelSubstring=Answer". Repeatable.')
    ap.add_argument("--guest", action="append", default=[], help="Guest email(s). Repeatable.")
    ap.add_argument("--months-ahead", type=int, default=4, help="How many months to advance if date not visible.")
    ap.add_argument("--headful", action="store_true", help="Run headed (visible) browser for debugging.")
    ap.add_argument("--settle-ms", type=int, default=800, help="Wait after submit before checking confirmation.")
    ap.add_argument("--json", action="store_true", help="Output JSON to stdout.")
    args = ap.parse_args()

    answers = parse_kv_list(args.answer)
    guests = args.guest or []

    result = _run(book_slot(
        event_url=args.event_url,
        date_iso=args.date,
        time_str=args.time,
        invitee_name=args.invitee_name,
        invitee_email=args.invitee_email,
        timezone=args.timezone,
        answers=answers,
        guests=guests,
        headless=not args.headful,
        click_months_ahead=args.months_ahead,
        settle_ms=args.settle_ms
    ))

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result.get("ok"):
            print("✅ Booked successfully!")
            print(f"  Confirmation URL: {result.get('confirmation_url')}")
            if result.get("ics_url"):
                print(f"  ICS: {result['ics_url']}")
        else:
            print("❌ Booking failed.")
            print(f"  Reason: {result.get('reason')}")
            if result.get("confirmation_url"):
                print(f"  URL: {result['confirmation_url']}")

    sys.exit(0 if result.get("ok") else 2)

if __name__ == "__main__":
    main()
