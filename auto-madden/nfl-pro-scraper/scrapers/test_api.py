"""Quick test to check API response structure."""

import asyncio
import json
import ssl
import certifi
from pathlib import Path

import aiohttp

CREDENTIALS_PATH = Path('../credentials')
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'


async def test_week_api(season: int, week: int):
    """Test the week games API."""
    state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
    
    with open(state_file) as f:
        state = json.load(f)
    
    cookies = {}
    for cookie in state.get('cookies', []):
        if 'nfl.com' in cookie.get('domain', ''):
            cookies[cookie['name']] = cookie['value']
    
    # Create SSL context with certifi certificates
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(
        cookies=cookies,
        connector=connector,
        headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': 'https://pro.nfl.com/',
        }
    ) as session:
        # First get the games
        games_url = f"https://pro.nfl.com/api/scores/live/games"
        params = {'season': season, 'seasonType': 'REG', 'week': week}
        
        async with session.get(games_url, params=params) as resp:
            print(f"Games Status: {resp.status}")
            data = await resp.json()
            
            print(f"\nGames count: {len(data.get('games', []))}")
            
            if data.get('games'):
                print("\nFirst game structure:")
                game = data['games'][0]
                print(json.dumps(game, indent=2, default=str)[:1500])
                
                # Now fetch plays for first game
                game_id = game['gameId']
                print(f"\n\n--- Fetching plays for {game_id} ---")
                
                plays_url = f"https://pro.nfl.com/api/secured/plays/playlist/game"
                plays_params = {'gameId': game_id}
                
                async with session.get(plays_url, params=plays_params) as plays_resp:
                    print(f"Plays Status: {plays_resp.status}")
                    plays_data = await plays_resp.json()
                    
                    print(f"Plays count: {len(plays_data.get('plays', []))}")
                    
                    # Show top-level keys
                    print(f"\nTop-level keys: {list(plays_data.keys())}")
                    
                    # Check for team info
                    if 'homeTeamAbbr' in plays_data:
                        print(f"Home: {plays_data.get('homeTeamAbbr')}")
                        print(f"Away: {plays_data.get('visitorTeamAbbr')}")
                    
                    # First play
                    if plays_data.get('plays'):
                        print("\nFirst play:")
                        play = plays_data['plays'][0]
                        print(json.dumps(play, indent=2, default=str)[:2000])


if __name__ == '__main__':
    asyncio.run(test_week_api(2024, 1))

