#!/usr/bin/env python3
"""
NFL Pro Manual Login Session Capture Tool

Opens a visible browser window for manual login to pro.nfl.com.
After login, saves the browser state (cookies, localStorage) for use by the scraper.

Usage:
    python nfl_pro_login.py
    
The browser will open to the NFL Pro login page. Log in with your NFL+ credentials,
then navigate to any game page to confirm access. The session will be saved automatically.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

# Configuration
CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '../credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'

NFL_PRO_CONFIG = {
    'name': 'NFL Pro',
    # Use the direct sign-in URL
    'login_url': 'https://id.nfl.com/account/sign-in?redirectURL=https://pro.nfl.com/',
    'success_indicator': 'pro.nfl.com',
    'wait_for_selector': '[class*="game-card"], [class*="GameCard"], [class*="schedule"], [class*="Game"]',
    'login_page_indicators': ['/sign-in', '/signin', '/login', 'id.nfl.com', 'auth.nfl.com', '/account/'],
    'instructions': 'Log in with your NFL+ credentials. After login, you will be redirected to pro.nfl.com.',
}


async def capture_nfl_pro_session() -> bool:
    """
    Open a browser for manual login to NFL Pro and capture the session.
    
    Returns:
        True if session was captured successfully
    """
    print(f"\n{'='*60}")
    print(f"🏈 NFL Pro Login Session Capture")
    print(f"{'='*60}\n")
    
    # Ensure directories exist
    CREDENTIALS_PATH.mkdir(parents=True, exist_ok=True)
    BROWSER_STATES_PATH.mkdir(parents=True, exist_ok=True)
    
    state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
    
    async with async_playwright() as p:
        # Use persistent context to avoid automation detection overlay
        user_data_dir = CREDENTIALS_PATH / 'chrome_profile_nfl'
        user_data_dir.mkdir(parents=True, exist_ok=True)
        
        print("🚀 Launching browser...")
        print(f"   Using persistent profile: {user_data_dir}")
        print("   (A browser window will open - please log in manually)\n")
        
        # Launch persistent context - behaves more like real Chrome
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--start-maximized',
            ],
            viewport={'width': 1400, 'height': 900},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
            ignore_default_args=['--enable-automation'],
        )
        
        # Use existing page or create new one
        page = context.pages[0] if context.pages else await context.new_page()
        
        # First, try navigating directly to NFL Pro to check if already logged in
        print(f"📍 Checking if already logged in to pro.nfl.com...")
        await page.goto('https://pro.nfl.com/', wait_until='domcontentloaded')
        await asyncio.sleep(3)
        
        current_url = page.url
        login_successful = False
        
        # Check if already authenticated (not redirected to login)
        on_login_page = any(
            ind in current_url.lower() 
            for ind in NFL_PRO_CONFIG['login_page_indicators']
        )
        
        if 'pro.nfl.com' in current_url and not on_login_page:
            # Already logged in! Just capture the session
            print(f"\n✅ Already logged in! (URL: {current_url[:50]}...)")
            login_successful = True
        else:
            # Need to log in - navigate to login page
            print(f"   Not logged in. Redirecting to login page...")
            await page.goto(NFL_PRO_CONFIG['login_url'], wait_until='domcontentloaded')
            await asyncio.sleep(3)
            
            print("\n" + "="*60)
            print("👆 PLEASE LOG IN WITH YOUR NFL+ CREDENTIALS")
            print("="*60)
            print(f"\n📝 Note: {NFL_PRO_CONFIG['instructions']}")
            print("\nWaiting for you to complete login...")
            print("(The browser will stay open until you're logged in)")
            print("(Press Ctrl+C to cancel)\n")
            
            # Wait for login to complete
            max_wait_minutes = 15
            check_interval_seconds = 5
            max_checks = (max_wait_minutes * 60) // check_interval_seconds
            
            print("   You have up to 15 minutes to complete login.")
            print("   Take your time with 2FA or any verification steps.\n")
            
            for i in range(max_checks):
                try:
                    current_url = page.url
                    
                    # Check if still on login page
                    still_on_login = any(
                        ind in current_url.lower() 
                        for ind in NFL_PRO_CONFIG['login_page_indicators']
                    )
                    
                    if still_on_login:
                        if i % 4 == 0:
                            print(f"   ⏳ On login page - please log in... ({i * check_interval_seconds}s)")
                        await asyncio.sleep(check_interval_seconds)
                        continue
                    
                    # Check for success - on pro.nfl.com and not on login page
                    if 'pro.nfl.com' in current_url and not still_on_login:
                        login_successful = True
                        print(f"\n✅ Login detected! (URL: {current_url[:50]}...)")
                        break
                    
                    if i % 5 == 0:
                        print(f"   ⏳ Still waiting... ({i * check_interval_seconds}s)")
                    
                    await asyncio.sleep(check_interval_seconds)
                    
                except Exception as e:
                    print(f"   ⚠️ Check error: {e}")
                    await asyncio.sleep(check_interval_seconds)
        
        if login_successful:
            # Wait a moment to ensure all cookies are set
            print("\n📦 Saving session state...")
            await asyncio.sleep(3)
            
            # Save browser state
            state = await context.storage_state()
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
            
            # Extract cookies for separate storage
            cookies = await context.cookies()
            cred_file = CREDENTIALS_PATH / 'nfl_pro_credentials.json'
            
            credentials = {
                'cookies': cookies,
                'captured_at': datetime.now().isoformat(),
                'source': 'manual_login',
                'browser_state_file': str(state_file),
            }
            
            # Extract any NFL-specific tokens
            for cookie in cookies:
                if 'nfl' in cookie.get('domain', '').lower():
                    if 'token' in cookie['name'].lower() or 'auth' in cookie['name'].lower():
                        credentials[f"nfl_{cookie['name']}"] = cookie['value']
            
            with open(cred_file, 'w') as f:
                json.dump(credentials, f, indent=2)
            
            print(f"✅ Session saved to: {state_file}")
            print(f"✅ Credentials saved to: {cred_file}")
            print(f"   ({len(cookies)} cookies captured)")
            
            # Keep browser open briefly to verify
            print("\n🔍 Keeping browser open for 5 seconds to verify...")
            await asyncio.sleep(5)
            
        else:
            print("\n❌ Login not detected within timeout.")
            print("   Please try again and make sure you complete the login.")
        
        await context.close()
        
        return login_successful


async def verify_session() -> bool:
    """Verify that a saved session is still valid."""
    state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
    
    if not state_file.exists():
        print("❌ No saved session found. Run login first.")
        return False
    
    print("🔍 Verifying saved session...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        context = await browser.new_context(
            storage_state=str(state_file),
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        )
        
        page = await context.new_page()
        
        try:
            await page.goto('https://pro.nfl.com/games', wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)
            
            current_url = page.url
            
            # Check if redirected to login
            if any(ind in current_url.lower() for ind in NFL_PRO_CONFIG['login_page_indicators']):
                print("❌ Session expired. Please run login again.")
                await browser.close()
                return False
            
            # Look for game content
            game_content = await page.query_selector('[class*="game"], [class*="Game"]')
            if game_content:
                print("✅ Session is valid!")
                await browser.close()
                return True
            else:
                print("⚠️ Session may be valid but no game content found")
                await browser.close()
                return True
            
        except Exception as e:
            print(f"❌ Error verifying session: {e}")
            await browser.close()
            return False


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'verify':
        asyncio.run(verify_session())
    else:
        success = asyncio.run(capture_nfl_pro_session())
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

