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
        
        print('2. Waiting for page to fully load...')
        await asyncio.sleep(5)

        # Click Accept Cookies button - try multiple selectors
        print('3. Accepting cookies...')
        cookie_selectors = [
            '#onetrust-accept-btn-handler',
            'button#onetrust-accept-btn-handler',
            '[id="onetrust-accept-btn-handler"]',
            'button:has-text("Accept")',
            'button:has-text("Accept All")',
            'button:has-text("I Accept")',
            '.onetrust-close-btn-handler',
        ]

        cookie_clicked = False
        for selector in cookie_selectors:
            try:
                # Wait for element to be visible first
                await page.wait_for_selector(selector, state='visible', timeout=3000)
                await page.click(selector, timeout=3000)
                print(f'   Clicked cookie consent: {selector}')
                cookie_clicked = True
                break
            except Exception:
                pass

        if not cookie_clicked:
            # Try pressing Escape to dismiss any overlays
            print('   No cookie button found, trying Escape key...')
            await page.keyboard.press('Escape')

        await asyncio.sleep(2)
        
        # Fill email using the exact ID from HTML
        print('4. Filling email...')
        try:
            await page.fill('#email-input-field', 'cdorsey+nfltmp@concord.org', timeout=15000)
            print('   Email filled')
        except Exception as e:
            print(f'   Email error: {e}')
        await asyncio.sleep(1)
        
        # Click Continue - use JavaScript click as fallback
        print('5. Clicking Continue...')
        try:
            continue_btn = page.locator('button[aria-label="Continue"]')
            await continue_btn.wait_for(state='visible', timeout=10000)
            # Try regular click first
            try:
                await continue_btn.click(timeout=3000)
                print('   Clicked Continue')
            except Exception:
                # Fallback to JavaScript click
                await continue_btn.evaluate('el => el.click()')
                print('   Clicked Continue (via JS)')
        except Exception as e:
            print(f'   Continue error: {e}')
        await asyncio.sleep(4)
        
        # Click "Sign in with password" if visible
        print('6. Looking for password option...')
        try:
            pwd_option = page.locator('button[aria-label="Sign in with password"]')
            await pwd_option.wait_for(state='visible', timeout=5000)
            try:
                await pwd_option.click(timeout=3000)
                print('   Clicked Sign in with password')
            except Exception:
                await pwd_option.evaluate('el => el.click()')
                print('   Clicked Sign in with password (via JS)')
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
            signin_btn = page.locator('button[aria-label="Sign In"]')
            await signin_btn.wait_for(state='visible', timeout=10000)
            try:
                await signin_btn.click(timeout=3000)
                print('   Clicked Sign In')
            except Exception:
                await signin_btn.evaluate('el => el.click()')
                print('   Clicked Sign In (via JS)')
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

