"""
NFL Pro Season Play-by-Play Scraper

Scrapes all play-by-play data for a full NFL season.
Designed to be respectful of rate limits and resumable.

Features:
- Rate limiting with random delays (60-90s between games)
- Checkpointing for resumability
- SQLite storage for queries
- CSV export capability
"""

import asyncio
import json
import logging
import os
import random
import sqlite3
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '../credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'
DATA_PATH = Path(os.environ.get('DATA_PATH', '../data'))


class SeasonScraper:
    """Scrapes all play-by-play data for an NFL season."""
    
    BASE_URL = "https://pro.nfl.com"
    
    # Rate limiting settings (be respectful)
    MIN_DELAY_SECONDS = 60
    MAX_DELAY_SECONDS = 90
    
    def __init__(self, season: int = 2025, headless: bool = True):
        self.season = season
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
        
        # Database setup
        DATA_PATH.mkdir(parents=True, exist_ok=True)
        self.db_path = DATA_PATH / f"nfl_plays_{season}.db"
        self._init_database()
        
        # Checkpoint file
        self.checkpoint_path = DATA_PATH / f"scrape_checkpoint_{season}.json"
    
    def _init_database(self):
        """Initialize SQLite database with schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Games table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                game_id INTEGER PRIMARY KEY,
                game_uuid TEXT UNIQUE,
                season INTEGER,
                season_type TEXT,
                week INTEGER,
                home_team TEXT,
                away_team TEXT,
                home_score INTEGER,
                away_score INTEGER,
                game_date TEXT,
                scraped_at TEXT
            )
        ''')
        
        # Plays table with all the detailed fields
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS plays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER,
                game_uuid TEXT,
                play_id INTEGER,
                sequence INTEGER,
                quarter INTEGER,
                down INTEGER,
                yards_to_go INTEGER,
                yard_line TEXT,
                possession_team TEXT,
                
                -- Clock
                start_clock TEXT,
                end_clock TEXT,
                
                -- Scores
                home_score INTEGER,
                visitor_score INTEGER,
                
                -- Play details
                play_type TEXT,
                play_description TEXT,
                
                -- Flags
                is_scoring INTEGER,
                is_big_play INTEGER,
                is_redzone INTEGER,
                is_special_teams INTEGER,
                
                -- Offense
                off_formation TEXT,
                off_personnel TEXT,
                
                -- Defense
                def_personnel TEXT,
                defenders_in_box INTEGER,
                pass_rushers INTEGER,
                coverage_type TEXT,
                man_zone TEXT,
                
                -- Pass info
                air_yards REAL,
                time_to_throw REAL,
                was_pressure INTEGER,
                route TEXT,
                
                -- Player stats (JSON)
                player_stats TEXT,
                
                FOREIGN KEY (game_id) REFERENCES games(game_id)
            )
        ''')
        
        # Index for faster queries
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
            raise FileNotFoundError("No NFL Pro session. Run nfl_pro_login.py first.")
        
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            storage_state=str(state_file),
            viewport={'width': 1400, 'height': 900},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        )
        logger.info("Browser initialized")
    
    async def close(self):
        """Clean up resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    async def get_season_games(self, weeks: List[int] = None) -> List[Dict]:
        """Get all games for the season."""
        if weeks is None:
            weeks = list(range(1, 18))  # Weeks 1-17
        
        all_games = []
        page = await self._context.new_page()
        
        try:
            for week in weeks:
                games_data = None
                
                async def capture_schedule(response):
                    nonlocal games_data
                    if f'scores/live/games' in response.url and response.status == 200:
                        try:
                            games_data = await response.json()
                        except:
                            pass
                
                page.on('response', capture_schedule)
                
                # Navigate to schedule page for the week
                url = f"{self.BASE_URL}/games?season={self.season}&seasonType=REG&week={week}"
                await page.goto(url, wait_until='networkidle')
                await asyncio.sleep(3)
                
                if games_data and 'games' in games_data:
                    for game in games_data['games']:
                        all_games.append({
                            'game_id': game.get('gameId'),
                            'game_uuid': game.get('gameId'),  # They use same ID in API
                            'week': week,
                            'home_team': game.get('homeTeam', {}).get('abbr', ''),
                            'away_team': game.get('awayTeam', {}).get('abbr', ''),
                            'home_score': game.get('homeScore', 0),
                            'away_score': game.get('awayScore', 0),
                        })
                
                logger.info(f"Week {week}: Found {len(games_data.get('games', [])) if games_data else 0} games")
                
                # Small delay between weeks
                await asyncio.sleep(random.uniform(2, 5))
        
        finally:
            await page.close()
        
        logger.info(f"Total games found: {len(all_games)}")
        return all_games
    
    def load_checkpoint(self) -> Dict:
        """Load scraping checkpoint."""
        if self.checkpoint_path.exists():
            with open(self.checkpoint_path) as f:
                return json.load(f)
        return {'completed_games': [], 'last_updated': None}
    
    def save_checkpoint(self, checkpoint: Dict):
        """Save scraping checkpoint."""
        checkpoint['last_updated'] = datetime.now().isoformat()
        with open(self.checkpoint_path, 'w') as f:
            json.dump(checkpoint, f, indent=2)
    
    def is_game_scraped(self, game_uuid: str) -> bool:
        """Check if a game has already been scraped."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM games WHERE game_uuid = ?', (game_uuid,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    async def scrape_game_plays(self, game_uuid: str) -> Tuple[Dict, List[Dict]]:
        """Scrape plays for a single game."""
        page = await self._context.new_page()
        plays_raw = None
        game_info = None
        
        async def capture_data(response):
            nonlocal plays_raw, game_info
            url = response.url
            if response.status == 200:
                try:
                    if 'plays/playlist' in url:
                        plays_raw = await response.json()
                    elif 'schedules/game' in url:
                        game_info = await response.json()
                except:
                    pass
        
        page.on('response', capture_data)
        
        try:
            await page.goto(
                f"{self.BASE_URL}/games/game/{game_uuid}/play-by-play",
                wait_until='networkidle'
            )
            await asyncio.sleep(5)
        finally:
            await page.close()
        
        # Process game info
        game_data = {}
        if game_info:
            game_data = {
                'game_id': game_info.get('gameId'),
                'game_uuid': game_uuid,
                'season': game_info.get('season', self.season),
                'season_type': game_info.get('seasonType', 'REG'),
                'week': game_info.get('week'),
                'home_team': game_info.get('homeTeamAbbr', ''),
                'away_team': game_info.get('visitorTeamAbbr', ''),
                'home_score': game_info.get('homeScore', 0),
                'away_score': game_info.get('visitorScore', 0),
                'game_date': game_info.get('gameDate', ''),
            }
        
        # Process plays
        plays = []
        if plays_raw and 'plays' in plays_raw:
            for p in plays_raw['plays']:
                yard_line = ""
                if p.get('yardlineSide') and p.get('yardlineNumber'):
                    yard_line = f"{p['yardlineSide']} {p['yardlineNumber']}"
                
                offense = p.get('offense', {})
                defense = p.get('defense', {})
                pass_info = p.get('passInfo', {})
                rec_info = p.get('recInfo', {})
                
                play = {
                    'game_id': plays_raw.get('gameId'),
                    'game_uuid': game_uuid,
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
                    'play_type': p.get('playType', '').replace('play_type_', ''),
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
                }
                plays.append(play)
        
        return game_data, plays
    
    def save_game_to_db(self, game_data: Dict, plays: List[Dict]):
        """Save game and plays to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Insert game
        cursor.execute('''
            INSERT OR REPLACE INTO games 
            (game_id, game_uuid, season, season_type, week, home_team, away_team, 
             home_score, away_score, game_date, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            game_data.get('game_id'),
            game_data.get('game_uuid'),
            game_data.get('season'),
            game_data.get('season_type'),
            game_data.get('week'),
            game_data.get('home_team'),
            game_data.get('away_team'),
            game_data.get('home_score'),
            game_data.get('away_score'),
            game_data.get('game_date'),
            datetime.now().isoformat(),
        ))
        
        # Insert plays
        for play in plays:
            cursor.execute('''
                INSERT INTO plays 
                (game_id, game_uuid, play_id, sequence, quarter, down, yards_to_go,
                 yard_line, possession_team, start_clock, end_clock, home_score, visitor_score,
                 play_type, play_description, is_scoring, is_big_play, is_redzone, is_special_teams,
                 off_formation, off_personnel, def_personnel, defenders_in_box, pass_rushers,
                 coverage_type, man_zone, air_yards, time_to_throw, was_pressure, route, player_stats)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                play['game_id'], play['game_uuid'], play['play_id'], play['sequence'],
                play['quarter'], play['down'], play['yards_to_go'], play['yard_line'],
                play['possession_team'], play['start_clock'], play['end_clock'],
                play['home_score'], play['visitor_score'], play['play_type'],
                play['play_description'], play['is_scoring'], play['is_big_play'],
                play['is_redzone'], play['is_special_teams'], play['off_formation'],
                play['off_personnel'], play['def_personnel'], play['defenders_in_box'],
                play['pass_rushers'], play['coverage_type'], play['man_zone'],
                play['air_yards'], play['time_to_throw'], play['was_pressure'],
                play['route'], play['player_stats'],
            ))
        
        conn.commit()
        conn.close()
        logger.info(f"Saved {len(plays)} plays for game {game_data.get('game_uuid')}")
    
    async def scrape_season(self, weeks: List[int] = None, dry_run: bool = False):
        """Scrape all games for specified weeks."""
        if weeks is None:
            weeks = list(range(1, 18))
        
        await self.start()
        checkpoint = self.load_checkpoint()
        
        try:
            # Get all games
            print(f"\n{'='*60}")
            print(f"NFL Pro Season Scraper - {self.season}")
            print(f"{'='*60}")
            print(f"Weeks: {weeks[0]}-{weeks[-1]}")
            print(f"Database: {self.db_path}")
            print(f"Rate limit: {self.MIN_DELAY_SECONDS}-{self.MAX_DELAY_SECONDS}s between games")
            print(f"{'='*60}\n")
            
            print("Fetching game schedule...")
            all_games = await self.get_season_games(weeks)
            
            # Filter out already scraped games
            games_to_scrape = []
            for game in all_games:
                game_uuid = game['game_uuid']
                if game_uuid and not self.is_game_scraped(game_uuid):
                    games_to_scrape.append(game)
            
            print(f"\nTotal games: {len(all_games)}")
            print(f"Already scraped: {len(all_games) - len(games_to_scrape)}")
            print(f"To scrape: {len(games_to_scrape)}")
            
            if dry_run:
                print("\n[DRY RUN] Would scrape:")
                for g in games_to_scrape[:10]:
                    print(f"  Week {g['week']}: {g['away_team']} @ {g['home_team']}")
                if len(games_to_scrape) > 10:
                    print(f"  ... and {len(games_to_scrape) - 10} more")
                return
            
            # Estimate time
            total_time_min = len(games_to_scrape) * (self.MIN_DELAY_SECONDS + 10) / 60
            total_time_max = len(games_to_scrape) * (self.MAX_DELAY_SECONDS + 10) / 60
            print(f"Estimated time: {total_time_min:.0f}-{total_time_max:.0f} minutes")
            print(f"\nStarting scrape at {datetime.now().strftime('%H:%M:%S')}...\n")
            
            # Scrape each game
            for i, game in enumerate(games_to_scrape):
                game_uuid = game['game_uuid']
                
                print(f"[{i+1}/{len(games_to_scrape)}] Week {game['week']}: {game['away_team']} @ {game['home_team']}...", end=' ', flush=True)
                
                try:
                    game_data, plays = await self.scrape_game_plays(game_uuid)
                    
                    if plays:
                        self.save_game_to_db(game_data, plays)
                        print(f"✓ {len(plays)} plays")
                        
                        # Update checkpoint
                        checkpoint['completed_games'].append(game_uuid)
                        self.save_checkpoint(checkpoint)
                    else:
                        print("⚠ No plays found")
                    
                except Exception as e:
                    print(f"✗ Error: {e}")
                    logger.error(f"Error scraping {game_uuid}: {e}")
                
                # Rate limiting with random delay
                if i < len(games_to_scrape) - 1:
                    delay = random.uniform(self.MIN_DELAY_SECONDS, self.MAX_DELAY_SECONDS)
                    print(f"    Waiting {delay:.0f}s before next game...")
                    await asyncio.sleep(delay)
            
            print(f"\n{'='*60}")
            print(f"Scraping complete!")
            print(f"{'='*60}")
            
        finally:
            await self.close()
    
    def export_to_csv(self, output_path: str = None):
        """Export all data to CSV."""
        if output_path is None:
            output_path = DATA_PATH / f"nfl_plays_{self.season}.csv"
        
        conn = sqlite3.connect(self.db_path)
        
        # Query with game info joined
        query = '''
            SELECT 
                g.game_id,
                g.game_uuid,
                g.season,
                g.week,
                g.home_team,
                g.away_team,
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
        
        # Write CSV
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header
            columns = [desc[0] for desc in cursor.description]
            writer.writerow(columns)
            
            # Data
            row_count = 0
            for row in cursor:
                writer.writerow(row)
                row_count += 1
        
        conn.close()
        logger.info(f"Exported {row_count} plays to {output_path}")
        print(f"Exported {row_count} plays to {output_path}")
        return output_path
    
    def get_stats(self) -> Dict:
        """Get statistics about scraped data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM games')
        game_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM plays')
        play_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT week, COUNT(*) FROM games GROUP BY week ORDER BY week')
        games_by_week = dict(cursor.fetchall())
        
        cursor.execute('SELECT play_type, COUNT(*) FROM plays GROUP BY play_type ORDER BY COUNT(*) DESC')
        plays_by_type = dict(cursor.fetchall())
        
        conn.close()
        
        return {
            'total_games': game_count,
            'total_plays': play_count,
            'games_by_week': games_by_week,
            'plays_by_type': plays_by_type,
        }


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='NFL Pro Season Scraper')
    parser.add_argument('--season', type=int, default=2025, help='Season year')
    parser.add_argument('--weeks', type=str, default='1-17', help='Weeks to scrape (e.g., "1-17" or "1,2,3")')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be scraped')
    parser.add_argument('--export', action='store_true', help='Export to CSV only')
    parser.add_argument('--stats', action='store_true', help='Show database stats')
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
    
    scraper = SeasonScraper(season=args.season, headless=not args.visible)
    
    if args.stats:
        stats = scraper.get_stats()
        print(f"\n{'='*40}")
        print(f"Database Stats - {args.season}")
        print(f"{'='*40}")
        print(f"Total games: {stats['total_games']}")
        print(f"Total plays: {stats['total_plays']}")
        print(f"\nGames by week:")
        for week, count in sorted(stats['games_by_week'].items()):
            print(f"  Week {week}: {count} games")
        print(f"\nPlays by type:")
        for ptype, count in list(stats['plays_by_type'].items())[:10]:
            print(f"  {ptype}: {count:,}")
        return
    
    if args.export:
        scraper.export_to_csv()
        return
    
    await scraper.scrape_season(weeks=weeks, dry_run=args.dry_run)


if __name__ == '__main__':
    asyncio.run(main())

