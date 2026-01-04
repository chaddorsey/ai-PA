"""Test scraping a single game."""

import asyncio
from browser_season_scraper import BrowserSeasonScraper


async def test():
    scraper = BrowserSeasonScraper(season=2024, headless=True)
    
    await scraper.start()
    
    try:
        # Get week 1 games
        games = await scraper.get_week_games(1)
        print(f"Found {len(games)} games")
        
        if games:
            # Try scraping the first game
            game = games[0]
            print(f"\nScraping game: {game['game_id']}")
            
            result = await scraper.scrape_game_plays(game['game_id'])
            
            print(f"Home team: {result['home_team']}")
            print(f"Away team: {result['away_team']}")
            print(f"Plays: {len(result['plays'])}")
            
            if result['plays']:
                play = result['plays'][0]
                print(f"\nFirst play:")
                print(f"  Type: {play['play_type']}")
                print(f"  Description: {play['play_description'][:100]}...")
                print(f"  Formation: {play['off_formation']}")
                print(f"  Personnel: {play['off_personnel']}")
    
    finally:
        await scraper.close()


if __name__ == '__main__':
    asyncio.run(test())

