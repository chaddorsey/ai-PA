"""Investigate how the schedule page works for historical seasons."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

CREDENTIALS_PATH = Path('../credentials')
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'


async def investigate():
    state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            storage_state=str(state_file),
            viewport={'width': 1400, 'height': 900},
        )
        page = await context.new_page()
        
        # Capture all API calls
        api_calls = []
        
        async def log_request(response):
            url = response.url
            if 'pro.nfl.com/api' in url:
                api_calls.append({
                    'url': url,
                    'status': response.status,
                })
                print(f"API: {response.status} {url}")
        
        page.on('response', log_request)
        
        # Navigate to 2024 Week 1
        print("\n=== Navigating to 2024 Week 1 ===")
        await page.goto('https://pro.nfl.com/games?season=2024&seasonType=REG&week=1')
        await asyncio.sleep(5)
        
        # Check what's visible on the page
        print("\n=== Checking page content ===")
        
        # Look for game cards
        game_elements = await page.query_selector_all('[data-testid*="game"], [class*="game-card"], [class*="GameCard"]')
        print(f"Found {len(game_elements)} game elements")
        
        # Check if there's a season selector
        selectors = await page.query_selector_all('select, [role="combobox"], [class*="dropdown"]')
        print(f"Found {len(selectors)} dropdown/select elements")
        
        # Try clicking any season dropdown
        for selector in selectors:
            text = await selector.text_content()
            print(f"  Dropdown: {text[:50] if text else 'empty'}")
        
        # Keep browser open for manual inspection
        print("\n=== Browser open for 30 seconds ===")
        await asyncio.sleep(30)
        
        await browser.close()


if __name__ == '__main__':
    asyncio.run(investigate())

