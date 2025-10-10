#!/usr/bin/env python3
"""Test booking without guest to isolate the 400 error."""

import asyncio
import re
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(timezone_id='America/New_York')
        page = await ctx.new_page()
        page.on("console", lambda msg: print(f"[CONSOLE] {msg.type}: {msg.text}"))
        
        await page.goto('https://calendly.com/zarek-drozda/30min', wait_until='domcontentloaded')
        await page.wait_for_timeout(2000)
        
        # Cookie
        try:
            await page.locator('#onetrust-accept-btn-handler').click()
            await page.wait_for_timeout(1500)
        except:
            pass
        
        # Date
        await page.locator('button[aria-label*="Times available"]').filter(has_text='29').first.click()
        await page.wait_for_timeout(1000)
        print('✓ Date clicked')
        
        # Time
        time_btns = page.locator('[data-container="time-button"]')
        for i in range(await time_btns.count()):
            text = await time_btns.nth(i).text_content()
            if '12:30' in text:
                await time_btns.nth(i).click()
                break
        await page.wait_for_timeout(500)
        print('✓ Time clicked')
        
        # Next
        await page.locator('[data-container="selected-spot"] button[aria-label*="Next"]').first.click()
        await page.wait_for_timeout(2000)
        print('✓ Next clicked')
        
        # Wait for form
        await page.wait_for_selector('input[name="full_name"]', timeout=10000)
        print('✓ Form loaded')
        
        # Fill WITHOUT guest
        await page.locator('input[name="full_name"]').fill('TEST - Chad Dorsey - DELETE ME')
        await page.locator('input[name="email"]').fill('cdorsey@concord.org')
        await page.locator('input[name="question_0"]').fill('TEST BOOKING - DELETE ME')
        print('✓ Form filled (no guest)')
        
        await page.screenshot(path='/tmp/test_no_guest_pre_submit.png', full_page=True)
        
        # Submit
        print('\n🚨 SUBMITTING (NO GUEST)...')
        submit = page.get_by_role('button', name=re.compile('Schedule', re.I)).first
        
        try:
            async with page.expect_navigation(timeout=15000):
                await submit.click()
            print('✓✓✓ NAVIGATION OCCURRED!')
            print(f'New URL: {page.url}')
            
            if '/invitees/' in page.url:
                print('✅ SUCCESS - Confirmation page reached!')
        except Exception as e:
            print(f'✗ Navigation timeout')
            print(f'Final URL: {page.url}')
        
        await page.wait_for_timeout(2000)
        await page.screenshot(path='/tmp/test_no_guest_after_submit.png', full_page=True)
        
        await browser.close()

asyncio.run(test())

