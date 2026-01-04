"""Inspect the plays API response for a historical game."""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

CREDENTIALS_PATH = Path('../credentials')
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'


async def inspect():
    state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=str(state_file),
        )
        page = await context.new_page()
        
        plays_data = None
        
        async def capture(response):
            nonlocal plays_data
            if 'plays/playlist' in response.url and response.status == 200:
                try:
                    plays_data = await response.json()
                except:
                    pass
        
        page.on('response', capture)
        
        # Navigate to the KC-BAL game from Week 1 2024
        game_id = "7d3e8f84-1312-11ef-afd1-646009f18b2e"
        url = f"https://pro.nfl.com/games/game/{game_id}/play-by-play"
        
        print(f"Navigating to: {url}")
        await page.goto(url, wait_until='networkidle')
        await asyncio.sleep(5)
        
        if plays_data:
            print("\n=== Top-level keys ===")
            print(list(plays_data.keys()))
            
            print("\n=== Team info ===")
            print(f"homeTeamAbbr: {plays_data.get('homeTeamAbbr', 'NOT FOUND')}")
            print(f"visitorTeamAbbr: {plays_data.get('visitorTeamAbbr', 'NOT FOUND')}")
            
            # Check if there are other team-related fields
            for key in plays_data.keys():
                if 'team' in key.lower():
                    print(f"{key}: {plays_data.get(key)}")
            
            print(f"\n=== Plays count: {len(plays_data.get('plays', []))} ===")
            
            if plays_data.get('plays'):
                # Skip marker plays, find a real play
                for i, play in enumerate(plays_data['plays']):
                    if play.get('playType', '') not in ['play_type_unknown', ''] and play.get('down', 0) > 0:
                        print(f"\n=== Real play #{i} (full) ===")
                        print(json.dumps(play, indent=2, default=str)[:3000])
                        break
                
                # Also check for team abbreviations in any play
                print("\n=== Checking for team abbreviations ===")
                all_teams = set()
                for play in plays_data['plays']:
                    if play.get('possessionTeam'):
                        all_teams.add(play['possessionTeam'])
                print(f"Unique possession teams: {all_teams}")
        else:
            print("No plays data captured!")
        
        await browser.close()


if __name__ == '__main__':
    asyncio.run(inspect())

