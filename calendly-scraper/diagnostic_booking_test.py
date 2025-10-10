#!/usr/bin/env python3
"""
Diagnostic booking test with comprehensive logging and screenshots.
This will attempt a REAL booking with detailed step tracking.
"""

import asyncio
import re
from datetime import datetime as _dt
from playwright.async_api import async_playwright

async def diagnostic_booking():
    """Run comprehensive diagnostic booking test."""
    
    # Test parameters
    url = "https://calendly.com/zarek-drozda/30min"
    date = "2025-10-29"
    time = "12:30pm"
    name = "Chad Dorsey"
    email = "cdorsey@concord.org"
    guest = "kmiller@concord.org"
    title = "Chad - Kate - Zarek check-in"
    
    print("="*70)
    print("DIAGNOSTIC CALENDLY BOOKING TEST")
    print("="*70)
    print(f"URL: {url}")
    print(f"Date: {date}")
    print(f"Time: {time}")
    print(f"Name: {name}")
    print(f"Email: {email}")
    print(f"Guest: {guest}")
    print(f"Title: {title}")
    print("="*70)
    print()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(timezone_id='America/New_York')
        page = await ctx.new_page()
        
        # Enable console logging
        page.on("console", lambda msg: print(f"[BROWSER CONSOLE] {msg.type}: {msg.text}"))
        
        # Step 1: Navigate
        print("Step 1: Navigation...")
        await page.goto(url, wait_until='domcontentloaded')
        await page.wait_for_timeout(2000)
        print(f"  URL: {page.url}")
        print(f"  Title: {await page.title()}")
        await page.screenshot(path='/tmp/diag_01_navigate.png')
        print("  ✓ Screenshot: /tmp/diag_01_navigate.png")
        
        # Step 2: Cookie banner
        print("\nStep 2: Dismiss cookie banner...")
        try:
            banner = page.locator('#onetrust-accept-btn-handler')
            if await banner.count():
                await banner.click()
                await page.wait_for_timeout(1500)
                print("  ✓ Cookie banner dismissed")
        except Exception as e:
            print(f"  Note: {e}")
        await page.screenshot(path='/tmp/diag_02_after_cookie.png')
        
        # Step 3: Click date
        print("\nStep 3: Click date (29)...")
        day_btn = page.locator('button[aria-label*=\"Times available\"]').filter(has_text='29').first
        count = await day_btn.count()
        print(f"  Date buttons found: {count}")
        if count:
            await day_btn.click()
            await page.wait_for_timeout(1000)
            print("  ✓ Date clicked")
        await page.screenshot(path='/tmp/diag_03_after_date.png')
        
        # Step 4: Click time
        print("\nStep 4: Click time (12:30pm)...")
        time_btns = page.locator('[data-container=\"time-button\"]')
        time_count = await time_btns.count()
        print(f"  Time buttons found: {time_count}")
        
        # Find 12:30
        clicked = False
        for i in range(time_count):
            text = await time_btns.nth(i).text_content()
            if '12:30' in text:
                print(f"  Clicking: {text.strip()}")
                await time_btns.nth(i).click()
                clicked = True
                break
        
        if clicked:
            await page.wait_for_timeout(500)
            print("  ✓ Time clicked")
        await page.screenshot(path='/tmp/diag_04_after_time.png')
        
        # Step 5: Click Next
        print("\nStep 5: Click Next button...")
        next_btn = page.locator('[data-container=\"selected-spot\"] button[aria-label*=\"Next\"]').first
        if await next_btn.count():
            await next_btn.click()
            print("  ✓ Next clicked")
            await page.wait_for_timeout(2000)
        print(f"  URL: {page.url}")
        print(f"  Title: {await page.title()}")
        await page.screenshot(path='/tmp/diag_05_after_next.png')
        
        # Step 6: Wait for form and fill
        print("\nStep 6: Wait for form inputs...")
        try:
            await page.wait_for_selector('input[name=\"full_name\"]', timeout=10000)
            print("  ✓ Form appeared")
        except:
            print("  ⚠ Timeout waiting for form")
        
        # Check what inputs exist
        name_input = page.locator('input[name=\"full_name\"]').first
        email_input = page.locator('input[name=\"email\"]').first
        print(f"  Name input: {await name_input.count()}")
        print(f"  Email input: {await email_input.count()}")
        
        # Fill name
        if await name_input.count():
            await name_input.fill(name)
            value = await name_input.input_value()
            print(f"  ✓ Name filled: '{value}'")
        
        # Fill email
        if await email_input.count():
            await email_input.fill(email)
            value = await email_input.input_value()
            print(f"  ✓ Email filled: '{value}'")
        
        await page.screenshot(path='/tmp/diag_06_form_filled.png')
        
        # Step 7: Add guest
        print("\nStep 7: Add guest...")
        try:
            add_btn = page.locator('button:has-text(\"Add Guests\")').first
            if await add_btn.count():
                await add_btn.click()
                await page.wait_for_timeout(500)
                guest_input = page.locator('#invitee_guest_input')
                if await guest_input.count():
                    await guest_input.fill(guest)
                    await page.keyboard.press('Enter')
                    await page.wait_for_timeout(300)
                    print(f"  ✓ Guest added: {guest}")
        except Exception as e:
            print(f"  Note: {e}")
        await page.screenshot(path='/tmp/diag_07_guest_added.png')
        
        # Step 8: Fill title field
        print("\nStep 8: Fill custom field (title)...")
        title_input = page.locator('input[name=\"question_0\"]').first
        if await title_input.count():
            await title_input.fill(title)
            value = await title_input.input_value()
            print(f"  ✓ Title filled: '{value}'")
        await page.screenshot(path='/tmp/diag_08_title_filled.png')
        
        # Step 9: Check submit button state
        print("\nStep 9: Check submit button...")
        for pattern in ['Schedule Event', 'Schedule', 'Confirm', 'Book']:
            btn = page.get_by_role('button', name=re.compile(pattern, re.I))
            if await btn.count():
                is_disabled = await btn.first.is_disabled()
                is_visible = await btn.first.is_visible()
                text = await btn.first.text_content()
                print(f"  Found: '{text.strip()}'")
                print(f"    Disabled: {is_disabled}")
                print(f"    Visible: {is_visible}")
                
                if not is_disabled:
                    await page.screenshot(path='/tmp/diag_09_pre_submit.png', full_page=True)
                    print("  ✓ Screenshot: /tmp/diag_09_pre_submit.png")
                    
                    # ACTUAL SUBMIT
                    print("\n  🚨 ATTEMPTING REAL BOOKING...")
                    print(f"  URL before click: {page.url}")
                    
                    try:
                        async with page.expect_navigation(timeout=15000):
                            await btn.first.click()
                        print("  ✓ Navigation occurred after submit!")
                        print(f"  New URL: {page.url}")
                    except Exception as e:
                        print(f"  ✗ Navigation timeout: {str(e)[:200]}")
                        print(f"  URL after click: {page.url}")
                    
                    await page.wait_for_timeout(3000)
                    await page.screenshot(path='/tmp/diag_10_after_submit.png', full_page=True)
                    print("  ✓ Screenshot: /tmp/diag_10_after_submit.png")
                    
                    # Check confirmation
                    print("\n  Checking for confirmation...")
                    print(f"  Final URL: {page.url}")
                    print(f"  Final title: {await page.title()}")
                    
                    if '/invitees/' in page.url or '/scheduled_events/' in page.url:
                        print("  ✓✓✓ BOOKING LIKELY SUCCEEDED (confirmation URL pattern)")
                    else:
                        print("  ⚠ Still on booking page pattern")
                    
                    # Look for ICS link
                    ics = page.locator('a[href$=\".ics\"]').first
                    if await ics.count():
                        ics_href = await ics.get_attribute('href')
                        print(f"  ✓ ICS link found: {ics_href}")
                    
                break
        
        print("\n" + "="*70)
        print("Diagnostic test complete. Check screenshots in /tmp/diag_*.png")
        print("="*70)
        
        await browser.close()

asyncio.run(diagnostic_booking())

