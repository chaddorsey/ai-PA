#!/usr/bin/env python3
"""
Manual Login Session Capture Tool

This script opens a visible browser window for you to log in to streaming services.
After login, it saves the browser state (cookies, localStorage, etc.) for use by
the automated session keeper.

Usage:
    python session_login.py <service>
    
Services:
    max       - HBO Max / Max
    netflix   - Netflix
    disney    - Disney+
    apple     - Apple TV+
    prime     - Prime Video
    hulu      - Hulu
    all       - All services sequentially

Example:
    python session_login.py max
    python session_login.py all
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

# Configuration
CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', './credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'

SERVICE_URLS = {
    'max': {
        'name': 'Max (HBO)',
        'login_url': 'https://play.max.com/',
        'success_indicator': 'play.max.com',
        'wait_for_selector': '[data-testid="profile-menu-button"], [data-testid="profiles-gate"], [data-testid="profile-avatar"]',
        'login_page_indicators': ['/sign-in', '/signin', 'auth.max.com'],
    },
    'netflix': {
        'name': 'Netflix', 
        'login_url': 'https://www.netflix.com/login',
        'success_indicator': 'netflix.com',
        'wait_for_selector': '[data-uia="profile-link"], .profile-icon, .profile-gate-container',
        'login_page_indicators': ['/login', '/LoginHelp'],
    },
    'disney': {
        'name': 'Disney+',
        'login_url': 'https://www.disneyplus.com/login',
        'success_indicator': 'disneyplus.com/home',  # Must reach actual home
        'wait_for_selector': '[data-testid="set"], section[class*="shelf"], [class*="ContinueWatching"]',
        'login_page_indicators': ['/login', '/identity', '/select-profile', '/select-avatar'],
        'instructions': 'After logging in, SELECT YOUR PROFILE and wait for HOME PAGE to fully load with content.',
    },
    'apple': {
        'name': 'Apple TV+',
        'login_url': 'https://tv.apple.com/',
        'success_indicator': 'tv.apple.com',
        'wait_for_selector': '[data-testid="account-menu"], .user-menu, .user-profile-link',
        'login_page_indicators': ['/auth/', 'idmsa.apple.com'],
    },
    'prime': {
        'name': 'Prime Video',
        'login_url': 'https://www.amazon.com/gp/video/storefront',
        'success_indicator': '/gp/video',  # Must be on Prime Video specifically
        'wait_for_selector': '#nav-link-accountList-nav-line-1',
        'login_page_indicators': ['/ap/signin', '/ap/cvf', '/ap/mfa', '/ap/forgotpassword', '/ap/register'],
        'require_url_and_selector': True,  # Must match BOTH URL and have logged-in selector
        'instructions': 'After logging in, navigate back to Prime Video if needed.',
    },
    'hulu': {
        'name': 'Hulu',
        'login_url': 'https://www.hulu.com/',
        'success_indicator': 'hulu.com',
        'wait_for_selector': '[data-testid="user-menu-button"], .user-menu, [data-automationid="user-menu"]',
        'login_page_indicators': ['/login', 'auth.hulu.com', '/welcome'],
    },
}


async def capture_session(service: str) -> bool:
    """
    Open a browser for manual login and capture the session.
    
    Args:
        service: The service to log into (max, netflix, etc.)
    
    Returns:
        True if session was captured successfully
    """
    if service not in SERVICE_URLS:
        print(f"❌ Unknown service: {service}")
        print(f"   Available: {', '.join(SERVICE_URLS.keys())}")
        return False
    
    config = SERVICE_URLS[service]
    print(f"\n{'='*60}")
    print(f"📺 {config['name']} Login Session Capture")
    print(f"{'='*60}\n")
    
    # Ensure directories exist
    BROWSER_STATES_PATH.mkdir(parents=True, exist_ok=True)
    
    state_file = BROWSER_STATES_PATH / f'{service}_state.json'
    
    async with async_playwright() as p:
        # Launch visible browser
        print("🚀 Launching browser...")
        print("   (A browser window will open - please log in manually)\n")
        
        # Use a persistent context to better simulate real browser
        browser = await p.chromium.launch(
            headless=False,  # VISIBLE browser
            args=[
                '--disable-blink-features=AutomationControlled',
                '--start-maximized',
            ]
        )
        
        # Create context with realistic settings
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
        )
        
        page = await context.new_page()
        
        # Navigate to login
        print(f"📍 Navigating to: {config['login_url']}")
        await page.goto(config['login_url'], wait_until='domcontentloaded')
        
        # Wait for page to settle before checking
        print("   Waiting for page to load...")
        await asyncio.sleep(3)
        
        print("\n" + "="*60)
        print("👆 PLEASE LOG IN TO YOUR ACCOUNT IN THE BROWSER WINDOW")
        print("="*60)
        
        # Show any service-specific instructions
        if config.get('instructions'):
            print(f"\n📝 Note: {config['instructions']}")
        
        print("\nWaiting for you to complete login...")
        print("(The browser will stay open until you're logged in)")
        print("(Press Ctrl+C to cancel)\n")
        
        # Wait for login to complete
        # We check periodically if the URL or page content indicates success
        login_successful = False
        max_wait_minutes = 10  # Increased for services with multi-step auth
        check_interval_seconds = 3  # Slightly slower to avoid rapid checks
        max_checks = (max_wait_minutes * 60) // check_interval_seconds
        
        # Track if we've ever seen a login page (to know login is required)
        seen_login_page = False
        
        for i in range(max_checks):
            try:
                current_url = page.url
                
                # Check if we're still on a login page (don't count as success)
                login_page_indicators = config.get('login_page_indicators', ['/login', '/signin', '/sign-in'])
                still_on_login = any(ind in current_url.lower() for ind in login_page_indicators)
                
                if still_on_login:
                    seen_login_page = True  # Mark that we've seen login
                    if i % 4 == 0:
                        print(f"   ⏳ On login page - please log in... ({i * check_interval_seconds}s)")
                    await asyncio.sleep(check_interval_seconds)
                    continue
                
                # For services requiring URL+selector, don't trigger on first load
                # Wait until we've seen a login page OR been waiting a while
                if config.get('require_url_and_selector') and i < 3 and not seen_login_page:
                    # First few checks - just wait for redirect to login
                    if i == 0:
                        print(f"   ⏳ Waiting for redirect to login...")
                    await asyncio.sleep(check_interval_seconds)
                    continue
                
                # Check if we're past the login page
                if config['success_indicator'] in current_url:
                    # Try to find the logged-in indicator
                    try:
                        await page.wait_for_selector(
                            config['wait_for_selector'], 
                            timeout=5000
                        )
                        login_successful = True
                        print(f"\n✅ Login detected! (URL: {current_url[:50]}...)")
                        break
                    except Exception:
                        # Selector not found, but might still be logged in
                        pass
                
                # Also check if we're on a profile selection page (counts as logged in)
                if 'profile' in current_url.lower() or 'browse' in current_url.lower():
                    login_successful = True
                    print(f"\n✅ Login detected! (URL: {current_url[:50]}...)")
                    break
                
                # For services requiring BOTH URL and selector (like Prime)
                if config.get('require_url_and_selector'):
                    if config['success_indicator'] in current_url:
                        try:
                            selector_elem = await page.query_selector(config['wait_for_selector'])
                            if selector_elem:
                                # For Prime, check the text content
                                if service == 'prime':
                                    text = await selector_elem.inner_text()
                                    if 'Hello' in text and 'Sign in' not in text:
                                        login_successful = True
                                        print(f"\n✅ Login detected on Prime Video! (Account: {text[:20]}...)")
                                        break
                                else:
                                    login_successful = True
                                    print(f"\n✅ Login detected! (URL + selector matched)")
                                    break
                        except Exception:
                            pass
                    elif i % 5 == 0:
                        print(f"   ⏳ Waiting for Prime Video page... (currently: {current_url[:40]}...)")
                
                # Visual progress indicator
                if i % 5 == 0:
                    print(f"   ⏳ Still waiting... ({i * check_interval_seconds}s)")
                
                await asyncio.sleep(check_interval_seconds)
                
            except Exception as e:
                print(f"   ⚠️ Check error: {e}")
                await asyncio.sleep(check_interval_seconds)
        
        if not login_successful:
            # Give user one more chance - maybe they're slow
            print("\n⏰ Taking a while... Giving you 2 more minutes.")
            print("   If you're logged in, navigate to the home page.\n")
            
            for i in range(60):  # 2 more minutes
                current_url = page.url
                
                # Skip if still on login page
                still_on_login = any(ind in current_url.lower() for ind in login_page_indicators)
                if still_on_login:
                    if i % 10 == 0:
                        print(f"   ⏳ Still waiting for login... ({i * 2}s)")
                    await asyncio.sleep(2)
                    continue
                
                # Check for success
                if config['success_indicator'] in current_url or 'profile' in current_url.lower():
                    # For services requiring both URL and selector
                    if config.get('require_url_and_selector'):
                        if config['success_indicator'] in current_url:
                            try:
                                selector_elem = await page.query_selector(config['wait_for_selector'])
                                if selector_elem:
                                    if service == 'prime':
                                        text = await selector_elem.inner_text()
                                        if 'Hello' in text and 'Sign in' not in text:
                                            login_successful = True
                                            print(f"\n✅ Login detected on Prime Video! (Account: {text[:20]}...)")
                                            break
                                    else:
                                        login_successful = True
                                        print(f"\n✅ Login detected!")
                                        break
                            except Exception:
                                pass
                        if i % 10 == 0:
                            print(f"   ⏳ Navigate to Prime Video when ready... ({i * 2}s)")
                    else:
                        login_successful = True
                        print(f"\n✅ Login detected! (URL: {current_url[:50]}...)")
                        break
                        
                await asyncio.sleep(2)
        
        if login_successful:
            # Wait a moment to ensure all cookies are set
            print("\n📦 Saving session state...")
            await asyncio.sleep(3)
            
            # Save browser state
            state = await context.storage_state()
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
            
            # Also extract and save credentials in our standard format
            cookies = await context.cookies()
            cred_file = CREDENTIALS_PATH / f'{service}_credentials.json'
            
            credentials = {
                'cookies': cookies,
                'captured_at': datetime.now().isoformat(),
                'source': 'manual_login',
                'browser_state_file': str(state_file),
            }
            
            # Extract specific tokens for services that need them
            if service == 'max':
                for cookie in cookies:
                    if cookie['name'] == 'st':
                        credentials['jwt_token'] = cookie['value']
                    if cookie['name'] == 'wbd-profile-context':
                        try:
                            profile_data = json.loads(cookie['value'])
                            credentials['profile_id'] = profile_data.get('profileId')
                        except Exception:
                            pass
            
            elif service == 'netflix':
                for cookie in cookies:
                    if cookie['name'] == 'NetflixId':
                        credentials['netflix_id'] = cookie['value']
            
            elif service == 'prime':
                for cookie in cookies:
                    if cookie['name'] == 'at-main':
                        credentials['at_main'] = cookie['value']
            
            with open(cred_file, 'w') as f:
                json.dump(credentials, f, indent=2)
            
            print(f"✅ Session saved to: {state_file}")
            print(f"✅ Credentials saved to: {cred_file}")
            print(f"   ({len(cookies)} cookies captured)")
            
            # Keep browser open briefly so user can verify
            print("\n🔍 Keeping browser open for 5 seconds to verify...")
            await asyncio.sleep(5)
            
        else:
            print("\n❌ Login not detected within timeout.")
            print("   Please try again and make sure you complete the login.")
        
        await context.close()
        await browser.close()
        
        return login_successful


async def capture_all_sessions():
    """Capture sessions for all services."""
    print("\n" + "="*60)
    print("📺 Capturing All Streaming Service Sessions")
    print("="*60)
    print("\nThis will open a browser for each service.")
    print("You'll need to log in to each one manually.\n")
    
    results = {}
    for service in SERVICE_URLS.keys():
        try:
            success = await capture_session(service)
            results[service] = 'success' if success else 'failed'
        except KeyboardInterrupt:
            print(f"\n⏹️ Skipped {service}")
            results[service] = 'skipped'
        except Exception as e:
            print(f"\n❌ Error with {service}: {e}")
            results[service] = 'error'
        
        if service != list(SERVICE_URLS.keys())[-1]:
            print("\n" + "-"*40)
            print("Moving to next service in 3 seconds...")
            print("-"*40)
            await asyncio.sleep(3)
    
    print("\n" + "="*60)
    print("📊 Session Capture Summary")
    print("="*60)
    for service, status in results.items():
        emoji = '✅' if status == 'success' else '❌' if status == 'failed' else '⏹️'
        print(f"   {emoji} {SERVICE_URLS[service]['name']}: {status}")
    print("="*60 + "\n")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nAvailable services:")
        for key, config in SERVICE_URLS.items():
            print(f"  {key:10} - {config['name']}")
        print(f"  {'all':10} - All services")
        sys.exit(1)
    
    service = sys.argv[1].lower()
    
    if service == 'all':
        asyncio.run(capture_all_sessions())
    elif service in SERVICE_URLS:
        success = asyncio.run(capture_session(service))
        sys.exit(0 if success else 1)
    else:
        print(f"❌ Unknown service: {service}")
        print(f"   Available: {', '.join(SERVICE_URLS.keys())}, all")
        sys.exit(1)


if __name__ == '__main__':
    main()

