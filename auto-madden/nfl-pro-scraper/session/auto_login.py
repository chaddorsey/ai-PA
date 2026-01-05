#!/usr/bin/env python3
"""
Automated NFL Pro Login

Handles:
1. Cookie consent overlays
2. Checking if already logged in
3. Automatic login with credentials if needed
4. Session capture and saving
"""

import asyncio
import json
import logging
from pathlib import Path
from playwright.async_api import async_playwright, Page, BrowserContext

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Paths
CREDENTIALS_PATH = Path('/Volumes/main-drive/ai-PA/auto-madden/credentials')
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'
BROWSER_STATES_PATH.mkdir(parents=True, exist_ok=True)

# Login credentials
NFL_USERNAME = "cdorsey+nfltmp@concord.org"
NFL_PASSWORD = "NFLtmp01!"

# URLs
LOGIN_URL = "https://id.nfl.com/account/sign-in?redirectURL=https://pro.nfl.com/"
PRO_NFL_URL = "https://pro.nfl.com/"


async def accept_cookies(page: Page) -> bool:
    """Accept any cookie consent overlays."""
    try:
        # Common cookie consent button selectors
        cookie_selectors = [
            'button:has-text("Accept")',
            'button:has-text("Accept All")',
            'button:has-text("I Accept")',
            'button:has-text("OK")',
            'button:has-text("Got it")',
            '[data-testid="accept-cookies"]',
            '.cookie-accept',
            '#onetrust-accept-btn-handler',
            '.accept-cookies-button',
        ]
        
        for selector in cookie_selectors:
            try:
                button = page.locator(selector).first
                if await button.is_visible(timeout=1000):
                    await button.click()
                    logger.info(f"Clicked cookie consent: {selector}")
                    await asyncio.sleep(1)
                    return True
            except:
                pass
        
        return False
    except Exception as e:
        logger.debug(f"Cookie acceptance check: {e}")
        return False


async def is_logged_in(page: Page) -> bool:
    """Check if we're already logged in to pro.nfl.com."""
    current_url = page.url
    
    # If we're on pro.nfl.com and not on a login page, we're logged in
    if 'pro.nfl.com' in current_url:
        if 'sign-in' not in current_url.lower() and 'login' not in current_url.lower():
            return True
    
    return False


async def perform_login(page: Page) -> bool:
    """Perform automated login."""
    try:
        logger.info("Performing automated login...")
        
        # Wait for login form to be ready
        await asyncio.sleep(2)
        
        # Accept any cookies first
        await accept_cookies(page)
        await asyncio.sleep(1)
        
        # Find and fill email field
        email_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[name="username"]',
            'input[id="email"]',
            'input[placeholder*="email" i]',
            'input[placeholder*="Email" i]',
        ]
        
        email_filled = False
        for selector in email_selectors:
            try:
                field = page.locator(selector).first
                if await field.is_visible(timeout=2000):
                    await field.fill(NFL_USERNAME)
                    logger.info(f"Filled email using: {selector}")
                    email_filled = True
                    break
            except:
                pass
        
        if not email_filled:
            logger.error("Could not find email field")
            return False
        
        await asyncio.sleep(1)
        
        # Find and fill password field
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[id="password"]',
        ]
        
        password_filled = False
        for selector in password_selectors:
            try:
                field = page.locator(selector).first
                if await field.is_visible(timeout=2000):
                    await field.fill(NFL_PASSWORD)
                    logger.info(f"Filled password using: {selector}")
                    password_filled = True
                    break
            except:
                pass
        
        if not password_filled:
            logger.error("Could not find password field")
            return False
        
        await asyncio.sleep(1)
        
        # Find and click submit button
        submit_selectors = [
            'button[type="submit"]',
            'button:has-text("Sign In")',
            'button:has-text("Log In")',
            'button:has-text("Submit")',
            'input[type="submit"]',
        ]
        
        for selector in submit_selectors:
            try:
                button = page.locator(selector).first
                if await button.is_visible(timeout=2000):
                    await button.click()
                    logger.info(f"Clicked submit using: {selector}")
                    break
            except:
                pass
        
        # Wait for navigation
        logger.info("Waiting for login to complete...")
        await asyncio.sleep(5)
        
        # Check for additional prompts or redirects
        for _ in range(10):
            await accept_cookies(page)
            
            current_url = page.url
            logger.info(f"Current URL: {current_url[:60]}...")
            
            if 'pro.nfl.com' in current_url and 'sign-in' not in current_url.lower():
                logger.info("Login successful!")
                return True
            
            await asyncio.sleep(2)
        
        return False
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return False


async def save_session(context: BrowserContext) -> bool:
    """Save the browser session state."""
    try:
        state = await context.storage_state()
        
        state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
        
        cookie_count = len(state.get('cookies', []))
        logger.info(f"Saved {cookie_count} cookies to {state_file}")
        
        return True
    except Exception as e:
        logger.error(f"Failed to save session: {e}")
        return False


async def main():
    """Main login flow."""
    print("=" * 60)
    print("🏈 NFL Pro Automated Login (Fresh Session)")
    print("=" * 60)
    
    async with async_playwright() as p:
        # Launch browser with CLEAN context (no saved state)
        browser = await p.chromium.launch(
            headless=False,
            channel='chrome',
            args=['--start-maximized']
        )
        
        # Use fresh context - no cookies from previous sessions
        context = await browser.new_context(
            viewport={'width': 1400, 'height': 900}
        )
        page = await context.new_page()
        
        try:
            # Go DIRECTLY to login page - don't check if logged in first
            logger.info(f"Navigating to login page...")
            await page.goto(LOGIN_URL, wait_until='domcontentloaded')
            await asyncio.sleep(3)
            
            # Accept any cookies
            await accept_cookies(page)
            await asyncio.sleep(2)
            
            # Perform login
            logger.info("Starting login process...")
            if await perform_login(page):
                await save_session(context)
                await browser.close()
                print("\n✅ Login and session capture successful!")
                return True
            
            # If automated login didn't work, wait for manual
            logger.info("Automated login may have issues. Waiting for manual completion...")
            logger.info("Please complete login in the browser if needed.")
            
            for i in range(24):  # 2 minutes
                await asyncio.sleep(5)
                current_url = page.url
                logger.info(f"Check {i+1}/24: {current_url[:50]}...")
                
                # Check if we made it to pro.nfl.com (not login page)
                if 'pro.nfl.com' in current_url and 'sign-in' not in current_url.lower() and 'id.nfl.com' not in current_url:
                    logger.info("✅ Login successful!")
                    await save_session(context)
                    await browser.close()
                    print("\n✅ Session captured successfully!")
                    return True
            
            await browser.close()
            print("\n❌ Login timed out. Please try again.")
            return False
                
        except Exception as e:
            logger.error(f"Error: {e}")
            await browser.close()
            return False


if __name__ == '__main__':
    asyncio.run(main())

