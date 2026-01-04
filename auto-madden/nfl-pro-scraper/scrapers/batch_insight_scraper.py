"""
NFL Pro Batch Insight Scraper

Scrapes narrative insights for all games in the database.
Stores insights with image URLs for later display.

Usage:
    python batch_insight_scraper.py --season 2025 [--weeks 1-17] [--visible]
"""

import asyncio
import json
import logging
import os
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import aiohttp
from playwright.async_api import async_playwright

# Setup paths
CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '/Volumes/main-drive/ai-PA/auto-madden/credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'
DATA_PATH = Path(os.environ.get('DATA_PATH', '/Volumes/main-drive/ai-PA/auto-madden/data'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BatchInsightScraper:
    """
    Scrapes NFL Pro narrative insights for all games.
    
    Features:
    - Uses existing play-by-play database to find games
    - Stores insights with full metadata including images
    - Rate limiting to avoid detection
    - Checkpointing for resumability
    """
    
    BASE_URL = "https://pro.nfl.com"
    INSIGHTS_API = "https://pro.nfl.com/api/content/insights/game"
    
    # Rate limits
    MIN_GAME_DELAY = 8
    MAX_GAME_DELAY = 15
    
    def __init__(self, season: int = 2025, headless: bool = True):
        self.season = season
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
        
        # Database paths
        self.plays_db_path = DATA_PATH / f"nfl_plays_{season}.db"
        self.insights_db_path = DATA_PATH / f"nfl_insights_{season}.db"
        
        # Initialize insights database
        self._init_database()
        
        # Image cache directory
        self.image_cache_dir = DATA_PATH / "insight_images"
        self.image_cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _init_database(self):
        """Initialize SQLite database for insights."""
        conn = sqlite3.connect(self.insights_db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                insight_id TEXT UNIQUE,
                game_id TEXT,
                season INTEGER,
                week INTEGER,
                title TEXT,
                sub_note TEXT,
                sub_note2 TEXT,
                
                -- Primary entity
                player_name TEXT,
                position TEXT,
                team_abbr TEXT,
                jersey_number INTEGER,
                
                -- Secondary entity (for matchup insights)
                second_player_name TEXT,
                second_position TEXT,
                second_team_abbr TEXT,
                second_team_type TEXT,
                
                -- Media
                image_url TEXT,
                headshot_url TEXT,
                image_cached INTEGER DEFAULT 0,
                
                -- Metadata
                tags TEXT,
                date_created TEXT,
                scraped_at TEXT,
                
                -- Usage tracking
                times_served INTEGER DEFAULT 0,
                last_served_game TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_insights_game ON insights(game_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_insights_player ON insights(player_name)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_insights_team ON insights(team_abbr)
        ''')
        
        # Track which games have been scraped for insights
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scrape_status (
                game_id TEXT PRIMARY KEY,
                insight_count INTEGER,
                scraped_at TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info(f"Insights database initialized: {self.insights_db_path}")
    
    async def start(self):
        """Initialize browser with saved session."""
        state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
        
        if not state_file.exists():
            raise FileNotFoundError("No NFL Pro session. Run nfl_pro_login.py first.")
        
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            storage_state=str(state_file),
            viewport={'width': 1400, 'height': 900},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        )
        logger.info("Browser initialized with saved session")
    
    async def close(self):
        """Clean up resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    def get_games_from_plays_db(self, weeks: List[int] = None) -> List[Dict]:
        """Get list of games from plays database."""
        if not self.plays_db_path.exists():
            raise FileNotFoundError(f"Plays database not found: {self.plays_db_path}")
        
        conn = sqlite3.connect(self.plays_db_path)
        cursor = conn.cursor()
        
        if weeks:
            week_filter = f"AND week IN ({','.join(map(str, weeks))})"
        else:
            week_filter = ""
        
        cursor.execute(f'''
            SELECT game_id, week, home_team, away_team
            FROM games
            WHERE season = ? {week_filter}
            ORDER BY week, game_id
        ''', (self.season,))
        
        games = []
        for row in cursor.fetchall():
            games.append({
                'game_id': row[0],
                'week': row[1],
                'home_team': row[2],
                'away_team': row[3],
            })
        
        conn.close()
        return games
    
    def get_scraped_games(self) -> set:
        """Get set of game IDs already scraped for insights."""
        conn = sqlite3.connect(self.insights_db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT game_id FROM scrape_status')
        scraped = {row[0] for row in cursor.fetchall()}
        conn.close()
        return scraped
    
    async def scrape_game_insights(self, game_id: str, week: int) -> List[Dict]:
        """Scrape insights for a single game via API capture."""
        page = await self._context.new_page()
        insights_raw = None
        
        async def capture_insights(response):
            nonlocal insights_raw
            if 'insights/game' in response.url and response.status == 200:
                try:
                    insights_raw = await response.json()
                except:
                    pass
        
        page.on('response', capture_insights)
        
        try:
            # Navigate to insights tab
            url = f"{self.BASE_URL}/games/game/{game_id}/insights"
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(5)  # Wait for API calls
            
        except Exception as e:
            logger.warning(f"Error loading insights page: {e}")
        finally:
            await page.close()
        
        if not insights_raw:
            # Try direct API call as fallback
            insights_raw = await self._fetch_insights_api(game_id)
        
        if not insights_raw or 'data' not in insights_raw:
            return []
        
        insights = []
        for i in insights_raw.get('data', []):
            insight = {
                'insight_id': str(i.get('id', '')),
                'game_id': game_id,
                'season': self.season,
                'week': week,
                'title': i.get('title', ''),
                'sub_note': i.get('subNote1', ''),
                'sub_note2': i.get('subNote2', ''),
                'player_name': i.get('playerName', ''),
                'position': i.get('position1', ''),
                'team_abbr': i.get('teamAbbr', ''),
                'jersey_number': i.get('jerseyNumber'),
                'second_player_name': i.get('secondPlayerName', ''),
                'second_position': i.get('secondPosition', ''),
                'second_team_abbr': i.get('secondTeamAbbr', ''),
                'second_team_type': i.get('secondTeamType', ''),
                'image_url': i.get('imageUrl', ''),
                'headshot_url': i.get('headshot', ''),
                'tags': json.dumps(i.get('tags', [])),
                'date_created': i.get('date', ''),
                'scraped_at': datetime.now().isoformat(),
            }
            insights.append(insight)
        
        return insights
    
    async def _fetch_insights_api(self, game_id: str) -> Optional[Dict]:
        """Fetch insights directly from API (requires auth via browser)."""
        page = await self._context.new_page()
        result = None
        
        try:
            # First load a page to establish session
            await page.goto(f"{self.BASE_URL}/games/game/{game_id}", wait_until='networkidle')
            await asyncio.sleep(2)
            
            # Then fetch insights API directly
            api_url = f"{self.INSIGHTS_API}?season={self.season}&limit=100&gameId={game_id}"
            response = await page.evaluate(f'''
                async () => {{
                    const resp = await fetch("{api_url}");
                    return await resp.json();
                }}
            ''')
            result = response
        except Exception as e:
            logger.warning(f"Direct API fetch failed: {e}")
        finally:
            await page.close()
        
        return result
    
    def save_insights(self, insights: List[Dict], game_id: str):
        """Save insights to database."""
        if not insights:
            return
        
        conn = sqlite3.connect(self.insights_db_path)
        cursor = conn.cursor()
        
        for insight in insights:
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO insights (
                        insight_id, game_id, season, week, title, sub_note, sub_note2,
                        player_name, position, team_abbr, jersey_number,
                        second_player_name, second_position, second_team_abbr, second_team_type,
                        image_url, headshot_url, tags, date_created, scraped_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    insight['insight_id'], insight['game_id'], insight['season'], insight['week'],
                    insight['title'], insight['sub_note'], insight['sub_note2'],
                    insight['player_name'], insight['position'], insight['team_abbr'],
                    insight['jersey_number'],
                    insight['second_player_name'], insight['second_position'],
                    insight['second_team_abbr'], insight['second_team_type'],
                    insight['image_url'], insight['headshot_url'],
                    insight['tags'], insight['date_created'], insight['scraped_at']
                ))
            except Exception as e:
                logger.warning(f"Error saving insight: {e}")
        
        # Mark game as scraped
        cursor.execute('''
            INSERT OR REPLACE INTO scrape_status (game_id, insight_count, scraped_at)
            VALUES (?, ?, ?)
        ''', (game_id, len(insights), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        logger.info(f"Saved {len(insights)} insights for game {game_id[:8]}")
    
    async def cache_images(self, insights: List[Dict]):
        """Download and cache insight images."""
        async with aiohttp.ClientSession() as session:
            for insight in insights:
                for url_field in ['image_url', 'headshot_url']:
                    url = insight.get(url_field, '')
                    if not url:
                        continue
                    
                    # Create filename from URL
                    filename = url.split('/')[-1].split('?')[0]
                    cache_path = self.image_cache_dir / filename
                    
                    if cache_path.exists():
                        continue
                    
                    try:
                        async with session.get(url, timeout=10) as resp:
                            if resp.status == 200:
                                content = await resp.read()
                                with open(cache_path, 'wb') as f:
                                    f.write(content)
                                logger.debug(f"Cached image: {filename}")
                    except Exception as e:
                        logger.debug(f"Could not cache image {url}: {e}")
    
    async def scrape_all(self, weeks: List[int] = None, cache_images: bool = False):
        """Scrape insights for all games."""
        await self.start()
        
        try:
            # Get all games
            games = self.get_games_from_plays_db(weeks)
            scraped = self.get_scraped_games()
            
            # Filter to unscraped games
            to_scrape = [g for g in games if g['game_id'] not in scraped]
            
            print(f"\n{'='*60}")
            print(f"NFL Pro Insight Scraper")
            print(f"Season: {self.season}")
            print(f"Total games: {len(games)}")
            print(f"Already scraped: {len(scraped)}")
            print(f"To scrape: {len(to_scrape)}")
            print(f"{'='*60}\n")
            
            if not to_scrape:
                print("✅ All games already scraped!")
                return
            
            total_insights = 0
            for i, game in enumerate(to_scrape, 1):
                game_id = game['game_id']
                week = game['week']
                teams = f"{game['away_team']} @ {game['home_team']}"
                
                print(f"[{i}/{len(to_scrape)}] Week {week}: {teams}...", end=' ', flush=True)
                
                insights = await self.scrape_game_insights(game_id, week)
                self.save_insights(insights, game_id)
                
                if cache_images and insights:
                    await self.cache_images(insights)
                
                total_insights += len(insights)
                print(f"✓ {len(insights)} insights")
                
                # Rate limit
                if i < len(to_scrape):
                    delay = random.uniform(self.MIN_GAME_DELAY, self.MAX_GAME_DELAY)
                    await asyncio.sleep(delay)
            
            print(f"\n{'='*60}")
            print(f"✅ Complete! Scraped {total_insights} insights from {len(to_scrape)} games")
            print(f"{'='*60}\n")
            
        finally:
            await self.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get insight database statistics."""
        conn = sqlite3.connect(self.insights_db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM insights')
        total_insights = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM scrape_status')
        games_scraped = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(DISTINCT player_name) FROM insights WHERE player_name != ""')
        unique_players = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(DISTINCT team_abbr) FROM insights WHERE team_abbr != ""')
        unique_teams = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM insights WHERE image_url != ""')
        with_images = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_insights': total_insights,
            'games_scraped': games_scraped,
            'unique_players': unique_players,
            'unique_teams': unique_teams,
            'with_images': with_images,
        }


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='NFL Pro Batch Insight Scraper')
    parser.add_argument('--season', type=int, default=2025, help='Season year')
    parser.add_argument('--weeks', type=str, default=None, help='Weeks (e.g., "1-17" or "1,2,3")')
    parser.add_argument('--visible', action='store_true', help='Show browser window')
    parser.add_argument('--cache-images', action='store_true', help='Download and cache images')
    parser.add_argument('--stats', action='store_true', help='Show statistics only')
    
    args = parser.parse_args()
    
    # Parse weeks
    weeks = None
    if args.weeks:
        if '-' in args.weeks:
            start, end = args.weeks.split('-')
            weeks = list(range(int(start), int(end) + 1))
        else:
            weeks = [int(w) for w in args.weeks.split(',')]
    
    scraper = BatchInsightScraper(season=args.season, headless=not args.visible)
    
    if args.stats:
        stats = scraper.get_stats()
        print(f"\n📊 Insight Database Stats ({args.season})")
        print(f"   Total insights: {stats['total_insights']}")
        print(f"   Games scraped: {stats['games_scraped']}")
        print(f"   Unique players: {stats['unique_players']}")
        print(f"   Unique teams: {stats['unique_teams']}")
        print(f"   With images: {stats['with_images']}")
        return
    
    await scraper.scrape_all(weeks=weeks, cache_images=args.cache_images)


if __name__ == '__main__':
    asyncio.run(main())

