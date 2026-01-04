"""Test if there's a schedule API that works for historical seasons."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, Response
import json

CREDENTIALS_PATH = Path('../credentials')
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'


async def test_schedule():
    state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=str(state_file),
        )
        page = await context.new_page()
        
        # Try various API endpoints directly
        endpoints = [
            # Schedule endpoints
            "https://pro.nfl.com/api/schedules/weeks?season=2024",
            "https://pro.nfl.com/api/scores/live/games?season=2024&seasonType=REG&week=1",
            "https://pro.nfl.com/api/schedules/season?season=2024",
            "https://pro.nfl.com/api/schedules/games?season=2024&seasonType=REG",
            "https://pro.nfl.com/api/games/season/2024",
        ]
        
        for url in endpoints:
            print(f"\n{'='*60}")
            print(f"Testing: {url}")
            
            response = await page.goto(url)
            status = response.status if response else "no response"
            
            print(f"Status: {status}")
            
            if response and response.status == 200:
                try:
                    content = await page.content()
                    # Try to parse as JSON from the pre tag
                    import re
                    match = re.search(r'<pre[^>]*>(.+?)</pre>', content, re.DOTALL)
                    if match:
                        data = json.loads(match.group(1))
                        
                        if isinstance(data, dict):
                            print(f"Keys: {list(data.keys())}")
                            
                            if 'games' in data:
                                games = data['games']
                                print(f"Games count: {len(games)}")
                                if games:
                                    g = games[0]
                                    print(f"First game ID: {g.get('gameId', 'N/A')}")
                                    home = g.get('homeTeam', {})
                                    away = g.get('awayTeam', {})
                                    print(f"Matchup: {away.get('abbr', '?')} @ {home.get('abbr', '?')}")
                            
                            if 'weeks' in data:
                                print(f"Weeks: {data['weeks'][:3]}...")
                        
                        elif isinstance(data, list):
                            print(f"List with {len(data)} items")
                            if data:
                                print(f"First item: {str(data[0])[:100]}")
                except Exception as e:
                    print(f"Parse error: {e}")
        
        await browser.close()


if __name__ == '__main__':
    asyncio.run(test_schedule())

