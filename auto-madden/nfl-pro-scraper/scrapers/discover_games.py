"""
Discover all game UUIDs for an NFL season.

This script navigates through the NFL Pro schedule pages to find all game IDs
for a given season, which can then be used by the season scraper.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
import os

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '../credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'
DATA_PATH = Path(os.environ.get('DATA_PATH', '../data'))


async def discover_games(season: int = 2025, weeks: list = None, headless: bool = False):
    """
    Discover all game UUIDs for a season by navigating the schedule.
    """
    state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
    
    if not state_file.exists():
        print("❌ No NFL Pro session found. Run nfl_pro_login.py first.")
        return []
    
    if weeks is None:
        weeks = list(range(1, 18))
    
    all_games = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            storage_state=str(state_file),
            viewport={'width': 1400, 'height': 900},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        )
        page = await context.new_page()
        
        try:
            for week in weeks:
                print(f"\n📅 Week {week}...")
                games_data = None
                
                # Capture API responses - specifically for the week we're requesting
                async def capture_response(response):
                    nonlocal games_data
                    url = response.url
                    if response.status == 200:
                        try:
                            # Look for the specific week's games
                            if f'week={week}' in url and 'games' in url:
                                data = await response.json()
                                if 'games' in data:
                                    games_data = data
                                    logger.info(f"Captured games for week {week} from {url}")
                        except:
                            pass
                
                page.on('response', capture_response)
                
                # Navigate to schedule
                url = f"https://pro.nfl.com/games?season={season}&seasonType=REG&week={week}"
                await page.goto(url, wait_until='networkidle')
                await asyncio.sleep(3)
                
                # Try to find game links in the DOM if API didn't work
                if not games_data:
                    # Look for game links in the page
                    links = await page.query_selector_all('a[href*="/games/game/"]')
                    for link in links:
                        href = await link.get_attribute('href')
                        if href and '/games/game/' in href:
                            # Extract UUID from URL
                            parts = href.split('/games/game/')
                            if len(parts) > 1:
                                uuid = parts[1].split('/')[0]
                                if uuid and len(uuid) == 36:  # UUID format
                                    # Try to get team info from link text or parent
                                    all_games.append({
                                        'game_uuid': uuid,
                                        'week': week,
                                        'season': season,
                                    })
                                    print(f"  Found: {uuid}")
                
                elif games_data and 'games' in games_data:
                    for game in games_data['games']:
                        # gameId could be an int or UUID string depending on endpoint
                        game_id = game.get('gameId')
                        game_uuid = game.get('uuid') or game.get('gameUuid') or str(game_id)
                        
                        game_entry = {
                            'game_id': game_id,
                            'game_uuid': game_uuid,
                            'week': week,
                            'season': season,
                            'season_type': game.get('seasonType', 'REG'),
                            'home_team': game.get('homeTeam', {}).get('abbr', ''),
                            'away_team': game.get('awayTeam', {}).get('abbr', ''),
                            'home_score': game.get('homeScore', 0),
                            'away_score': game.get('awayScore', 0),
                            'game_date': game.get('startTime', ''),
                        }
                        all_games.append(game_entry)
                        uuid_display = game_uuid[:8] if len(str(game_uuid)) > 8 else game_uuid
                        print(f"  {game_entry['away_team']} @ {game_entry['home_team']} ({uuid_display}...)")
                
                # Remove response listener for next iteration
                page.remove_listener('response', capture_response)
                
                await asyncio.sleep(2)
        
        finally:
            await page.close()
            await context.close()
            await browser.close()
    
    # Save to file
    DATA_PATH.mkdir(parents=True, exist_ok=True)
    output_file = DATA_PATH / f"game_schedule_{season}.json"
    with open(output_file, 'w') as f:
        json.dump({
            'season': season,
            'discovered_at': datetime.now().isoformat(),
            'games': all_games,
        }, f, indent=2)
    
    print(f"\n✅ Discovered {len(all_games)} games")
    print(f"📁 Saved to {output_file}")
    
    return all_games


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Discover NFL Pro game IDs')
    parser.add_argument('--season', type=int, default=2025, help='Season year')
    parser.add_argument('--weeks', type=str, default='1-17', help='Weeks to discover')
    parser.add_argument('--visible', action='store_true', help='Show browser')
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    # Parse weeks
    if '-' in args.weeks:
        start, end = args.weeks.split('-')
        weeks = list(range(int(start), int(end) + 1))
    else:
        weeks = [int(w) for w in args.weeks.split(',')]
    
    await discover_games(
        season=args.season,
        weeks=weeks,
        headless=not args.visible
    )


if __name__ == '__main__':
    asyncio.run(main())

