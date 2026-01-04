"""
NFL Pro Season Scraper - Browser-based

Uses Playwright to navigate and capture API responses.
This approach works because the browser handles authentication properly.

Features:
- Captures API responses during page navigation
- Rate limiting with random delays
- Checkpointing for resumability  
- SQLite storage + CSV export
"""

import asyncio
import json
import logging
import os
import random
import re
import sqlite3
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import aiohttp
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '../credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'
DATA_PATH = Path(os.environ.get('DATA_PATH', '../data'))


# Known team ID to abbreviation mapping
TEAM_MAPPING = {
    "10400325-48de-3d6a-be29-8f829437f4c8": "BAL",
    "10402310-a47e-10ea-7442-16b633633637": "KC",
    # Will be populated dynamically
}


class BrowserSeasonScraper:
    """
    Scrapes NFL Pro play-by-play data for an entire season.
    Uses Playwright to navigate pages and capture API responses.
    """
    
    BASE_URL = "https://pro.nfl.com"
    
    # Rate limits (be respectful)
    MIN_GAME_DELAY = 20  # seconds between games
    MAX_GAME_DELAY = 35
    
    def __init__(self, season: int = 2024, headless: bool = True):
        self.season = season
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
        
        # Database
        DATA_PATH.mkdir(parents=True, exist_ok=True)
        self.db_path = DATA_PATH / f"nfl_plays_{season}.db"
        self._init_database()
        
        # Team name cache
        self.team_names = {}
    
    def _init_database(self):
        """Initialize SQLite database with schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                season INTEGER,
                week INTEGER,
                home_team TEXT,
                away_team TEXT,
                home_score INTEGER,
                away_score INTEGER,
                game_date TEXT,
                scraped_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS plays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT,
                play_id INTEGER,
                sequence INTEGER,
                quarter INTEGER,
                down INTEGER,
                yards_to_go INTEGER,
                yard_line TEXT,
                possession_team TEXT,
                start_clock TEXT,
                end_clock TEXT,
                home_score INTEGER,
                visitor_score INTEGER,
                play_type TEXT,
                play_description TEXT,
                is_scoring INTEGER,
                is_big_play INTEGER,
                is_redzone INTEGER,
                is_special_teams INTEGER,
                off_formation TEXT,
                off_personnel TEXT,
                def_personnel TEXT,
                defenders_in_box INTEGER,
                pass_rushers INTEGER,
                coverage_type TEXT,
                man_zone TEXT,
                air_yards REAL,
                time_to_throw REAL,
                was_pressure INTEGER,
                route TEXT,
                player_stats TEXT,
                FOREIGN KEY (game_id) REFERENCES games(game_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_plays_game ON plays(game_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_plays_type ON plays(play_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_plays_team ON plays(possession_team)')
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized: {self.db_path}")
    
    async def start(self):
        """Initialize browser with saved session."""
        state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
        
        if not state_file.exists():
            raise FileNotFoundError(
                f"No NFL Pro session found. Run nfl_pro_login.py first to authenticate."
            )
        
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
    
    async def get_week_games(self, week: int) -> List[Dict]:
        """Get all games for a week by accessing the API directly."""
        page = await self._context.new_page()
        games = []
        
        try:
            # Access the API endpoint directly
            api_url = f"{self.BASE_URL}/api/scores/live/games?season={self.season}&seasonType=REG&week={week}"
            response = await page.goto(api_url)
            
            if response and response.status == 200:
                content = await page.content()
                
                # Extract JSON from the page (browser wraps it in HTML)
                match = re.search(r'<pre[^>]*>(.+?)</pre>', content, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    
                    if 'games' in data:
                        for g in data['games']:
                            home_team = g.get('homeTeam', {})
                            away_team = g.get('awayTeam', {})
                            
                            home_score = home_team.get('score', {})
                            away_score = away_team.get('score', {})
                            if isinstance(home_score, dict):
                                home_score = home_score.get('total', 0)
                            if isinstance(away_score, dict):
                                away_score = away_score.get('total', 0)
                            
                            games.append({
                                'game_id': g.get('gameId'),
                                'week': week,
                                'season': self.season,
                                'home_team_id': home_team.get('teamId', ''),
                                'away_team_id': away_team.get('teamId', ''),
                                'home_team': '',  # Populated from plays API
                                'away_team': '',  # Populated from plays API
                                'home_score': home_score or 0,
                                'away_score': away_score or 0,
                                'game_date': g.get('startTime', ''),
                                'game_state': g.get('gameState', ''),
                            })
        
        finally:
            await page.close()
        
        return games
    
    async def scrape_game_plays(self, game_id: str) -> Dict:
        """Scrape plays for a single game."""
        page = await self._context.new_page()
        plays_data = None
        
        async def capture_plays(response):
            nonlocal plays_data
            if response.status == 200 and 'plays/playlist' in response.url:
                try:
                    plays_data = await response.json()
                except:
                    pass
        
        page.on('response', capture_plays)
        
        try:
            url = f"{self.BASE_URL}/games/game/{game_id}/play-by-play"
            await page.goto(url, wait_until='networkidle')
            await asyncio.sleep(5)
        
        finally:
            await page.close()
        
        if not plays_data:
            return {'plays': [], 'home_team': '', 'away_team': ''}
        
        # Extract team abbreviations from plays (since they're not at top level)
        # The two teams are the unique possession teams
        teams = set()
        for p in plays_data.get('plays', []):
            if p.get('possessionTeam'):
                teams.add(p['possessionTeam'])
        teams = list(teams)
        
        # Determine home/away from playStats or first drive
        # Home team typically has second possession
        home_team = ''
        away_team = ''
        if len(teams) == 2:
            # Get first meaningful play to determine who had first possession (usually away)
            for p in plays_data.get('plays', []):
                if p.get('possessionTeam') and p.get('down', 0) > 0:
                    # First team with possession is typically away (receives kickoff)
                    away_team = p['possessionTeam']
                    home_team = [t for t in teams if t != away_team][0]
                    break
            
            # Fallback: just use alphabetical
            if not home_team:
                teams.sort()
                home_team, away_team = teams[0], teams[1]
        
        # Parse plays (skip marker plays)
        plays = []
        for p in plays_data.get('plays', []):
            # Skip marker plays (no real game action)
            if p.get('isMarkerPlay', False):
                continue
            
            offense = p.get('offense', {}) or {}
            defense = p.get('defense', {}) or {}
            pass_info = p.get('passInfo', {}) or {}
            rec_info = p.get('recInfo', {}) or {}
            
            yard_line = ""
            if p.get('yardlineSide') and p.get('yardlineNumber'):
                yard_line = f"{p['yardlineSide']} {p['yardlineNumber']}"
            
            plays.append({
                'game_id': game_id,
                'play_id': p.get('playId', 0),
                'sequence': p.get('sequence', 0),
                'quarter': p.get('quarter', 0),
                'down': p.get('down', 0),
                'yards_to_go': p.get('yardsToGo', 0),
                'yard_line': yard_line,
                'possession_team': p.get('possessionTeam', ''),
                'start_clock': p.get('startGameClock', ''),
                'end_clock': p.get('endGameClock', ''),
                'home_score': p.get('homeScore', 0),
                'visitor_score': p.get('visitorScore', 0),
                'play_type': (p.get('playType', '') or '').replace('play_type_', ''),
                'play_description': p.get('playDescription', ''),
                'is_scoring': 1 if p.get('isScoring') else 0,
                'is_big_play': 1 if p.get('isBigPlay') else 0,
                'is_redzone': 1 if p.get('isRedzonePlay') else 0,
                'is_special_teams': 1 if p.get('isSTPlay') else 0,
                'off_formation': offense.get('offenseFormation', ''),
                'off_personnel': offense.get('personnel', ''),
                'def_personnel': defense.get('personnel', ''),
                'defenders_in_box': defense.get('defendersInTheBox'),
                'pass_rushers': defense.get('numberOfPassRushers'),
                'coverage_type': defense.get('coverageType', ''),
                'man_zone': defense.get('manZoneType', ''),
                'air_yards': pass_info.get('airYards'),
                'time_to_throw': pass_info.get('timeToThrow'),
                'was_pressure': 1 if pass_info.get('wasPressure') else 0,
                'route': rec_info.get('route', ''),
                'player_stats': json.dumps(p.get('playStats', [])),
            })
        
        return {
            'plays': plays,
            'home_team': home_team,
            'away_team': away_team,
        }
    
    def is_game_scraped(self, game_id: str) -> bool:
        """Check if a game has already been scraped."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM games WHERE game_id = ?', (game_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def save_game(self, game: Dict, plays: List[Dict]):
        """Save game and plays to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO games 
            (game_id, season, week, home_team, away_team, home_score, away_score, game_date, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            game.get('game_id'),
            game.get('season'),
            game.get('week'),
            game.get('home_team'),
            game.get('away_team'),
            game.get('home_score'),
            game.get('away_score'),
            game.get('game_date'),
            datetime.now().isoformat(),
        ))
        
        for play in plays:
            cursor.execute('''
                INSERT INTO plays 
                (game_id, play_id, sequence, quarter, down, yards_to_go, yard_line,
                 possession_team, start_clock, end_clock, home_score, visitor_score,
                 play_type, play_description, is_scoring, is_big_play, is_redzone,
                 is_special_teams, off_formation, off_personnel, def_personnel,
                 defenders_in_box, pass_rushers, coverage_type, man_zone,
                 air_yards, time_to_throw, was_pressure, route, player_stats)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                play['game_id'],
                play['play_id'],
                play['sequence'],
                play['quarter'],
                play['down'],
                play['yards_to_go'],
                play['yard_line'],
                play['possession_team'],
                play['start_clock'],
                play['end_clock'],
                play['home_score'],
                play['visitor_score'],
                play['play_type'],
                play['play_description'],
                play['is_scoring'],
                play['is_big_play'],
                play['is_redzone'],
                play['is_special_teams'],
                play['off_formation'],
                play['off_personnel'],
                play['def_personnel'],
                play['defenders_in_box'],
                play['pass_rushers'],
                play['coverage_type'],
                play['man_zone'],
                play['air_yards'],
                play['time_to_throw'],
                play['was_pressure'],
                play['route'],
                play['player_stats'],
            ))
        
        conn.commit()
        conn.close()
        logger.info(f"Saved {len(plays)} plays for game {game.get('game_id')}")
    
    async def scrape_season(self, weeks: List[int] = None, dry_run: bool = False):
        """Scrape all games for specified weeks."""
        if weeks is None:
            weeks = list(range(1, 18))
        
        await self.start()
        
        try:
            print(f"\n{'='*60}")
            print(f"NFL Pro Season Scraper")
            print(f"Season: {self.season}")
            print(f"Weeks: {weeks[0]}-{weeks[-1]}")
            print(f"Database: {self.db_path}")
            print(f"Rate: {self.MIN_GAME_DELAY}-{self.MAX_GAME_DELAY}s between games")
            print(f"{'='*60}\n")
            
            # Collect all games
            print("📅 Discovering games...")
            all_games = []
            for week in weeks:
                games = await self.get_week_games(week)
                for g in games:
                    if not self.is_game_scraped(g['game_id']):
                        all_games.append(g)
                print(f"  Week {week}: {len(games)} games ({len([g for g in games if not self.is_game_scraped(g['game_id'])])} to scrape)")
                await asyncio.sleep(random.uniform(2, 4))
            
            print(f"\n📊 Total games to scrape: {len(all_games)}")
            
            if dry_run:
                print("\n[DRY RUN] Would scrape these games:")
                for g in all_games[:15]:
                    print(f"  Week {g['week']}: {g['game_id'][:8]}...")
                if len(all_games) > 15:
                    print(f"  ... and {len(all_games) - 15} more")
                return
            
            # Estimate time
            avg_delay = (self.MIN_GAME_DELAY + self.MAX_GAME_DELAY) / 2 + 5  # +5 for page load
            total_time_min = len(all_games) * avg_delay / 60
            total_time_hr = total_time_min / 60
            print(f"⏱️  Estimated time: {total_time_min:.0f} min ({total_time_hr:.1f} hours)")
            print(f"\n🚀 Starting at {datetime.now().strftime('%H:%M:%S')}...\n")
            
            # Scrape each game
            for i, game in enumerate(all_games):
                game_id = game['game_id']
                print(f"[{i+1}/{len(all_games)}] Week {game['week']}: {game_id[:8]}...", end=' ', flush=True)
                
                try:
                    result = await self.scrape_game_plays(game_id)
                    plays = result['plays']
                    
                    if plays:
                        # Update game with team names
                        game['home_team'] = result['home_team']
                        game['away_team'] = result['away_team']
                        
                        self.save_game(game, plays)
                        print(f"✓ {result['away_team']} @ {result['home_team']}: {len(plays)} plays")
                    else:
                        print("⚠ No plays found")
                
                except Exception as e:
                    print(f"✗ Error: {e}")
                    logger.exception(f"Error scraping game {game_id}")
                
                # Rate limiting
                if i < len(all_games) - 1:
                    delay = random.uniform(self.MIN_GAME_DELAY, self.MAX_GAME_DELAY)
                    print(f"    Waiting {delay:.0f}s...")
                    await asyncio.sleep(delay)
            
            print(f"\n{'='*60}")
            print("✅ Scraping complete!")
            print(f"{'='*60}")
            
        finally:
            await self.close()
    
    def export_csv(self, output_path: str = None):
        """Export to CSV."""
        if output_path is None:
            output_path = DATA_PATH / f"nfl_plays_{self.season}.csv"
        
        conn = sqlite3.connect(self.db_path)
        
        query = '''
            SELECT 
                g.game_id,
                g.season,
                g.week,
                g.home_team,
                g.away_team,
                g.home_score AS final_home_score,
                g.away_score AS final_away_score,
                g.game_date,
                p.play_id,
                p.sequence,
                p.quarter,
                p.down,
                p.yards_to_go,
                p.yard_line,
                p.possession_team,
                p.start_clock,
                p.end_clock,
                p.home_score,
                p.visitor_score,
                p.play_type,
                p.play_description,
                p.is_scoring,
                p.is_big_play,
                p.is_redzone,
                p.is_special_teams,
                p.off_formation,
                p.off_personnel,
                p.def_personnel,
                p.defenders_in_box,
                p.pass_rushers,
                p.coverage_type,
                p.man_zone,
                p.air_yards,
                p.time_to_throw,
                p.was_pressure,
                p.route
            FROM plays p
            JOIN games g ON p.game_id = g.game_id
            ORDER BY g.week, g.game_id, p.sequence
        '''
        
        cursor = conn.cursor()
        cursor.execute(query)
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            columns = [desc[0] for desc in cursor.description]
            writer.writerow(columns)
            
            row_count = 0
            for row in cursor:
                writer.writerow(row)
                row_count += 1
        
        conn.close()
        print(f"📁 Exported {row_count:,} plays to {output_path}")
        return output_path
    
    def get_stats(self) -> Dict:
        """Get database statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM games')
        game_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM plays')
        play_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT week, COUNT(*) FROM games GROUP BY week ORDER BY week')
        by_week = dict(cursor.fetchall())
        
        cursor.execute('''
            SELECT play_type, COUNT(*) FROM plays 
            WHERE play_type IS NOT NULL AND play_type != ""
            GROUP BY play_type ORDER BY COUNT(*) DESC LIMIT 10
        ''')
        by_type = dict(cursor.fetchall())
        
        conn.close()
        
        return {
            'games': game_count,
            'plays': play_count,
            'by_week': by_week,
            'by_type': by_type,
        }


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='NFL Pro Season Scraper')
    parser.add_argument('--season', type=int, default=2024, help='Season year')
    parser.add_argument('--weeks', type=str, default='1-17', help='Weeks (e.g., "1-17" or "1,2,3")')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be scraped')
    parser.add_argument('--export', action='store_true', help='Export to CSV only')
    parser.add_argument('--stats', action='store_true', help='Show statistics')
    parser.add_argument('--visible', action='store_true', help='Show browser window')
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Parse weeks
    if '-' in args.weeks:
        start, end = args.weeks.split('-')
        weeks = list(range(int(start), int(end) + 1))
    else:
        weeks = [int(w) for w in args.weeks.split(',')]
    
    scraper = BrowserSeasonScraper(season=args.season, headless=not args.visible)
    
    if args.stats:
        stats = scraper.get_stats()
        print(f"\n📊 Database Stats ({args.season})")
        print(f"   Games: {stats['games']}")
        print(f"   Plays: {stats['plays']:,}")
        if stats['by_week']:
            print("   Games by week:", dict(sorted(stats['by_week'].items())))
        if stats['by_type']:
            print("   Top play types:", stats['by_type'])
        return
    
    if args.export:
        scraper.export_csv()
        return
    
    await scraper.scrape_season(weeks=weeks, dry_run=args.dry_run)


if __name__ == '__main__':
    asyncio.run(main())

