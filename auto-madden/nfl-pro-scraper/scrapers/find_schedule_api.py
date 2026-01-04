"""Find an API that returns historical season schedules."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

CREDENTIALS_PATH = Path('../credentials')
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'


async def find_schedule_api():
    state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            storage_state=str(state_file),
            viewport={'width': 1400, 'height': 900},
        )
        page = await context.new_page()
        
        # Capture all API calls
        api_responses = []
        
        async def log_response(response):
            url = response.url
            if 'pro.nfl.com/api' in url and response.status == 200:
                try:
                    data = await response.json()
                    api_responses.append({
                        'url': url,
                        'data': data,
                    })
                except:
                    pass
        
        page.on('response', log_response)
        
        # Navigate to games page first
        print("=== Loading games page ===")
        await page.goto('https://pro.nfl.com/games')
        await asyncio.sleep(5)
        
        # Look for and click season dropdown
        print("\n=== Looking for season selector ===")
        
        # Find dropdown buttons
        dropdowns = await page.query_selector_all('button[class*="dropdown"], [class*="Dropdown"], [role="button"]')
        print(f"Found {len(dropdowns)} potential dropdowns")
        
        # Look for one with "2025" text (current season)
        for i, dropdown in enumerate(dropdowns):
            text = await dropdown.text_content()
            if text and '2025' in text:
                print(f"  Found season dropdown: {text.strip()}")
                # Click it
                await dropdown.click()
                await asyncio.sleep(2)
                
                # Look for 2024 option
                options = await page.query_selector_all('[role="option"], [class*="option"], li')
                for opt in options:
                    opt_text = await opt.text_content()
                    if opt_text and '2024' in opt_text:
                        print(f"  Clicking 2024 option: {opt_text.strip()}")
                        await opt.click()
                        await asyncio.sleep(5)
                        break
                break
        
        print("\n=== API calls after season change ===")
        for resp in api_responses[-10:]:
            print(f"  {resp['url'][:80]}...")
            if 'games' in resp['data'] if isinstance(resp['data'], dict) else False:
                games = resp['data']['games']
                print(f"    -> {len(games)} games")
                if games:
                    g = games[0]
                    print(f"    -> First: {g.get('gameId', 'no id')[:20]}...")
        
        # Keep browser open for inspection
        print("\n=== Browser open for 20 seconds ===")
        await asyncio.sleep(20)
        
        await browser.close()


if __name__ == '__main__':
    asyncio.run(find_schedule_api())

