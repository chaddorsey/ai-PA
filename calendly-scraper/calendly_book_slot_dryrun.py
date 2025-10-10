#!/usr/bin/env python3
"""
Dry-run test for Calendly booking automation - validates all steps WITHOUT submitting.

This script:
1. Navigates to the event page
2. Finds and clicks the target date
3. Finds and clicks the target time slot
4. Verifies form fields are present
5. STOPS before clicking the submit button (dry-run)

Usage:
  python calendly_book_slot_dryrun.py \
    "https://calendly.com/zarek-drozda/30min" \
    --date 2025-10-29 --time "3:30pm" \
    --name "Test User" --email "test@example.com" \
    --tz America/New_York
"""

from __future__ import annotations
import asyncio, argparse, re, sys, json
from typing import Dict, Any, List
from datetime import datetime as _dt
from playwright.async_api import async_playwright

async def test_booking_flow(
    event_url: str,
    date_iso: str,
    time_str: str,
    invitee_name: str,
    invitee_email: str,
    timezone: str,
    click_months_ahead: int = 4,
    headless: bool = True
) -> Dict[str, Any]:
    """Test booking flow without actually submitting."""
    
    target_day = str(_dt.fromisoformat(date_iso).day)
    
    # Time variants
    def _time_variants(t: str) -> List[str]:
        t = t.strip().lower()
        out = {t}
        try:
            if "am" in t or "pm" in t:
                dt = _dt.strptime(t.replace(" ", ""), "%I:%M%p")
                out.add(dt.strftime("%H:%M"))
            else:
                dt = _dt.strptime(t, "%H:%M")
                out.add(dt.strftime("%-I:%M%p").lower()) if "%" in "%-I" else None
                out.add(dt.strftime("%I:%M%p").lower().lstrip("0"))
        except Exception:
            pass
        return [x for x in out if x]
    
    needles = _time_variants(time_str)
    
    results = {
        "ok": False,
        "event_url": event_url,
        "date_requested": date_iso,
        "time_requested": time_str,
        "steps": {}
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(timezone_id=timezone, locale="en-US")
        page = await ctx.new_page()
        
        # Step 1: Navigate to page
        try:
            await page.goto(event_url, wait_until="domcontentloaded")
            results["steps"]["navigation"] = {"ok": True, "url": page.url}
        except Exception as e:
            results["steps"]["navigation"] = {"ok": False, "error": str(e)}
            await browser.close()
            return results
        
        # Step 2: Dismiss cookie banners
        dismissed_banner = False
        for sel in ['#onetrust-accept-btn-handler', 'button:has-text("Accept")', 
                    'button:has-text("Got it")', 'button:has-text("I agree")']:
            try:
                loc = page.locator(sel)
                if await loc.count():
                    await loc.click(timeout=1500)
                    dismissed_banner = True
                    break
            except Exception:
                pass
        results["steps"]["cookie_banner"] = {"dismissed": dismissed_banner}
        
        # Step 3: Find and click date
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
        
        found_day = await click_day()
        months_navigated = 0
        
        if not found_day:
            for i in range(max(0, click_months_ahead)):
                try:
                    next_btn = page.get_by_role("button", name=re.compile("(Next|Next month)", re.I))
                    if await next_btn.count():
                        await next_btn.click(timeout=2500)
                        await page.wait_for_timeout(350)
                        months_navigated += 1
                        if await click_day():
                            found_day = True
                            break
                except Exception:
                    break
        
        results["steps"]["date_selection"] = {
            "ok": found_day,
            "day": target_day,
            "months_navigated": months_navigated
        }
        
        if not found_day:
            results["reason"] = "date_not_found"
            await browser.close()
            return results
        
        # Step 4: Find and click time slot
        clicked_time = False
        matched_time_variant = None
        
        # Try data attribute first
        for n in needles:
            try:
                btn = page.locator(f'[data-container="time-button"][data-start-time*="{n}"]').first
                if await btn.count():
                    await btn.click(timeout=3000)
                    clicked_time = True
                    matched_time_variant = n
                    break
            except Exception:
                pass
        
        # Fallback: text search
        if not clicked_time:
            for n in needles:
                try:
                    btn = page.locator('[data-container="time-button"]').filter(has_text=re.compile(re.escape(n), re.I)).first
                    if await btn.count():
                        await btn.click(timeout=3000)
                        clicked_time = True
                        matched_time_variant = n
                        break
                except Exception:
                    pass
        
        results["steps"]["time_selection"] = {
            "ok": clicked_time,
            "time_variants_tried": needles,
            "matched_variant": matched_time_variant
        }
        
        if not clicked_time:
            results["reason"] = "time_not_found"
            await browser.close()
            return results
        
        # Step 5: Verify form fields are present (DON'T fill them in dry-run)
        await page.wait_for_timeout(500)  # Let form render
        
        form_fields = {}
        
        # Check for name field
        name_selectors = ['input[name="name"]', 'input[name="full_name"]', 'input[name="first_name"]']
        for sel in name_selectors:
            try:
                el = page.locator(sel).first
                if await el.count():
                    form_fields["name"] = {"found": True, "selector": sel}
                    break
            except Exception:
                pass
        
        if "name" not in form_fields:
            # Try label-based
            try:
                el = page.get_by_label(re.compile(r"(name|your name|full name)", re.I))
                if await el.count():
                    form_fields["name"] = {"found": True, "selector": "label-based"}
            except Exception:
                pass
        
        # Check for email field
        email_selectors = ['input[name="email"]', 'input[type="email"]']
        for sel in email_selectors:
            try:
                el = page.locator(sel).first
                if await el.count():
                    form_fields["email"] = {"found": True, "selector": sel}
                    break
            except Exception:
                pass
        
        # Check for submit button
        submit_found = False
        submit_button_text = None
        for name in ["Schedule", "Confirm", "Book", "Schedule Event", "Schedule now"]:
            try:
                btn = page.get_by_role("button", name=re.compile(name, re.I))
                if await btn.count():
                    submit_found = True
                    submit_button_text = name
                    break
            except Exception:
                pass
        
        form_fields["submit_button"] = {
            "found": submit_found,
            "text_pattern": submit_button_text
        }
        
        results["steps"]["form_validation"] = {
            "ok": form_fields.get("name", {}).get("found", False) and 
                  form_fields.get("email", {}).get("found", False) and
                  submit_found,
            "fields": form_fields
        }
        
        # Step 6: DRY-RUN - DO NOT SUBMIT
        results["steps"]["submission"] = {
            "ok": False,
            "dry_run": True,
            "message": "DRY-RUN MODE: Stopped before clicking submit button"
        }
        
        # Take screenshot for verification
        try:
            screenshot_path = f"/tmp/calendly_dryrun_{_dt.now().strftime('%Y%m%d_%H%M%S')}.png"
            await page.screenshot(path=screenshot_path)
            results["screenshot"] = screenshot_path
        except Exception:
            pass
        
        await browser.close()
        
        # Determine overall success
        all_steps_ok = all([
            results["steps"]["navigation"]["ok"],
            results["steps"]["date_selection"]["ok"],
            results["steps"]["time_selection"]["ok"],
            results["steps"]["form_validation"]["ok"]
        ])
        
        results["ok"] = all_steps_ok
        results["message"] = "DRY-RUN: All steps validated successfully, would proceed to booking" if all_steps_ok else "DRY-RUN: Some validation steps failed"
        
        return results


def main():
    ap = argparse.ArgumentParser(
        description="DRY-RUN test for Calendly booking flow - validates without submitting."
    )
    ap.add_argument("event_url", help="Calendly event URL")
    ap.add_argument("--date", required=True, help="Target date (YYYY-MM-DD)")
    ap.add_argument("--time", required=True, help='Target time "HH:MM" or "h:mma"')
    ap.add_argument("--name", default="Test User", help="Test name")
    ap.add_argument("--email", default="test@example.com", help="Test email")
    ap.add_argument("--tz", default="America/New_York", help="Timezone")
    ap.add_argument("--headful", action="store_true", help="Run visible browser")
    ap.add_argument("--json", action="store_true", help="Output JSON")
    args = ap.parse_args()
    
    result = asyncio.run(test_booking_flow(
        event_url=args.event_url,
        date_iso=args.date,
        time_str=args.time,
        invitee_name=args.name,
        invitee_email=args.email,
        timezone=args.tz,
        headless=not args.headful
    ))
    
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print("CALENDLY BOOKING DRY-RUN TEST")
        print("=" * 60)
        print(f"\n✓ Navigation: {result['steps']['navigation']['ok']}")
        print(f"✓ Date Selection: {result['steps']['date_selection']['ok']} (day {result['steps']['date_selection']['day']})")
        print(f"✓ Time Selection: {result['steps']['time_selection']['ok']} (matched: {result['steps']['time_selection'].get('matched_variant')})")
        print(f"✓ Form Validation: {result['steps']['form_validation']['ok']}")
        print(f"\nFields found: {list(result['steps']['form_validation']['fields'].keys())}")
        print(f"\n⚠️  {result['steps']['submission']['message']}")
        if result.get('screenshot'):
            print(f"📸 Screenshot: {result['screenshot']}")
        print(f"\nOverall: {'✅ PASS - Ready for booking' if result['ok'] else '❌ FAIL - Issues found'}")
    
    sys.exit(0 if result['ok'] else 1)

if __name__ == "__main__":
    main()

