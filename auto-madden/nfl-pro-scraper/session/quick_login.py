#!/usr/bin/env python3
"""Quick NFL Pro login script."""

import asyncio
from playwright.async_api import async_playwright
import json
from pathlib import Path

CREDS_PATH = Path('/Volumes/main-drive/ai-PA/auto-madden/credentials/browser_states')
CREDS_PATH.mkdir(parents=True, exist_ok=True)

async def login():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel='chrome')
        page = await browser.new_page(viewport={'width': 1400, 'height': 900})
        
        print('1. Opening login page...')
        await page.goto('https://id.nfl.com/account/sign-in?redirectURL=https://pro.nfl.com/', wait_until='commit', timeout=120000)
        
        print('2. Waiting for page...')
        await asyncio.sleep(10)
        
        # Click Accept Cookies button
        print('3. Accepting cookies...')
        try:
            await page.click('#onetrust-accept-btn-handler', timeout=10000)
            print('   Clicked Accept Cookies')
        except Exception as e:
            print(f'   Cookie click: {e}')
        await asyncio.sleep(2)
        
        # Fill email using the exact ID from HTML
        print('4. Filling email...')
        try:
            await page.fill('#email-input-field', 'cdorsey+nfltmp@concord.org', timeout=15000)
            print('   Email filled')
        except Exception as e:
            print(f'   Email error: {e}')
        await asyncio.sleep(1)
        
        # Click Continue
        print('5. Clicking Continue...')
        try:
            await page.click('button[aria-label="Continue"]', timeout=10000)
            print('   Clicked Continue')
        except Exception as e:
            print(f'   Continue error: {e}')
        await asyncio.sleep(4)
        
        # Click "Sign in with password" if visible
        print('6. Looking for password option...')
        try:
            await page.click('button[aria-label="Sign in with password"]', timeout=5000)
            print('   Clicked Sign in with password')
        except:
            print('   (Password field may already be visible)')
        await asyncio.sleep(2)
        
        # Fill password
        print('7. Filling password...')
        try:
            await page.fill('#password-input-field', 'NFLtmp01!', timeout=15000)
            print('   Password filled')
        except Exception as e:
            print(f'   Password error: {e}')
        await asyncio.sleep(1)
        
        # Click Sign In
        print('8. Clicking Sign In...')
        try:
            await page.click('button[aria-label="Sign In"]', timeout=10000)
            print('   Clicked Sign In')
        except Exception as e:
            print(f'   Sign In error: {e}')
        
        # Wait for redirect
        print('9. Waiting for pro.nfl.com...')
        for i in range(60):
            await asyncio.sleep(2)
            url = page.url
            print(f'   {i+1}: {url[:60]}')
            
            if 'pro.nfl.com' in url and 'id.nfl.com' not in url:
                print('\n✅ Login successful!')
                state = await page.context.storage_state()
                with open(CREDS_PATH / 'nfl_pro_state.json', 'w') as f:
                    json.dump(state, f, indent=2)
                print(f'✅ Saved {len(state.get("cookies", []))} cookies')
                await browser.close()
                return True
        
        print('\n⚠️ Timeout - check browser window')
        await asyncio.sleep(120)  # Keep open for manual intervention
        await browser.close()
        return False

if __name__ == '__main__':
    asyncio.run(login())

