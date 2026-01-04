"""
NFL Pro Direct API Season Scraper

Uses discovered API endpoints directly to build a season dataset.
More efficient than browser navigation.
"""

import asyncio
import json
import logging
import os
import random
import sqlite3
import csv
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import aiohttp

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '../credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'
DATA_PATH = Path(os.environ.get('DATA_PATH', '../data'))


class NFLProDirectAPI:
    """
    Direct API client for NFL Pro.
    Uses session cookies from browser login.
    """
    
    BASE_URL = "https://pro.nfl.com/api"
    
    # Rate limits
    MIN_DELAY = 3.0   # Seconds between API calls
    MAX_DELAY = 6.0
    GAME_DELAY_MIN = 15.0  # Longer delay between games
    GAME_DELAY_MAX = 25.0
    
    def __init__(self, season: int = 2024):
        self.season = season
        self.session: Optional[aiohttp.ClientSession] = None
        self._cookies = None
        self._load_cookies()
    
    def _load_cookies(self):
        """Load cookies from browser state file."""
        state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
        
        if not state_file.exists():
            raise FileNotFoundError(
                f"No session file found at {state_file}. "
                "Run nfl_pro_login.py first to authenticate."
            )
        
        with open(state_file) as f:
            state = json.load(f)
        
        # Convert Playwright cookies to aiohttp format
        self._cookies = {}
        for cookie in state.get('cookies', []):
            if 'nfl.com' in cookie.get('domain', ''):
                self._cookies[cookie['name']] = cookie['value']
        
        logger.info(f"Loaded {len(self._cookies)} cookies from session")
    
    async def start(self):
        """Initialize HTTP session."""
        if self.session:
            return
        
        self.session = aiohttp.ClientSession(
            cookies=self._cookies,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Referer': 'https://pro.nfl.com/',
                'Origin': 'https://pro.nfl.com',
            }
        )
    
    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def _request(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make an API request with rate limiting."""
        url = f"{self.BASE_URL}/{endpoint}"
        
        await asyncio.sleep(random.uniform(self.MIN_DELAY, self.MAX_DELAY))
        
        try:
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.warning(f"API returned {resp.status} for {url}")
                    return None
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None
    
    async def get_week_games(self, week: int, season_type: str = "REG") -> List[dict]:
        """Get all games for a specific week."""
        data = await self._request(
            "scores/live/games",
            params={
                'season': self.season,
                'seasonType': season_type,
                'week': week
            }
        )
        
        if not data or 'games' not in data:
            return []
        
        games = []
        for g in data['games']:
            # Handle nested score structure
            home_team = g.get('homeTeam', {})
            away_team = g.get('awayTeam', {})
            
            home_score = home_team.get('score', {})
            away_score = away_team.get('score', {})
            if isinstance(home_score, dict):
                home_score = home_score.get('total', 0)
            if isinstance(away_score, dict):
                away_score = away_score.get('total', 0)
            
            games.append({
                'game_id': g.get('gameId'),  # UUID format
                'week': week,
                'season': self.season,
                'home_team_id': home_team.get('teamId', ''),
                'away_team_id': away_team.get('teamId', ''),
                'home_team': '',  # Will be populated from plays API
                'away_team': '',  # Will be populated from plays API
                'home_score': home_score or 0,
                'away_score': away_score or 0,
                'game_date': g.get('startTime', ''),
                'game_state': g.get('gameState', ''),
            })
        
        return games
    
    async def get_plays(self, game_id: str) -> List[dict]:
        """Get all plays for a game."""
        data = await self._request(
            "secured/plays/playlist/game",
            params={'gameId': game_id}
        )
        
        if not data or 'plays' not in data:
            return []
        
        plays = []
        for p in data['plays']:
            offense = p.get('offense', {})
            defense = p.get('defense', {})
            pass_info = p.get('passInfo', {})
            rec_info = p.get('recInfo', {})
            
            yard_line = ""
            if p.get('yardlineSide') and p.get('yardlineNumber'):
                yard_line = f"{p['yardlineSide']} {p['yardlineNumber']}"
            
            plays.append({
                'game_id': data.get('gameId'),
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
        
        return plays


class SeasonDatasetBuilder:
    """Builds a complete season dataset."""
    
    def __init__(self, season: int = 2024):
        self.season = season
        self.api = NFLProDirectAPI(season)
        
        DATA_PATH.mkdir(parents=True, exist_ok=True)
        self.db_path = DATA_PATH / f"nfl_plays_{season}.db"
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database."""
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
        
        conn.commit()
        conn.close()
    
    def is_game_scraped(self, game_id: str) -> bool:
        """Check if game already scraped."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM games WHERE game_id = ?', (str(game_id),))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def save_game(self, game: dict, plays: List[dict]):
        """Save game and plays to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO games 
            (game_id, season, week, home_team, away_team, home_score, away_score, game_date, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(game.get('game_id')),
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
                str(play['game_id']),
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
    
    async def build_dataset(self, weeks: List[int] = None, dry_run: bool = False):
        """Build the complete season dataset."""
        if weeks is None:
            weeks = list(range(1, 18))
        
        await self.api.start()
        
        try:
            print(f"\n{'='*60}")
            print(f"NFL Pro Season Dataset Builder")
            print(f"Season: {self.season}")
            print(f"Weeks: {weeks[0]}-{weeks[-1]}")
            print(f"Database: {self.db_path}")
            print(f"{'='*60}\n")
            
            # Collect all games first
            print("📅 Discovering games...")
            all_games = []
            for week in weeks:
                games = await self.api.get_week_games(week)
                for g in games:
                    if not self.is_game_scraped(g['game_id']):
                        all_games.append(g)
                print(f"  Week {week}: {len(games)} games")
            
            print(f"\n📊 Total games to scrape: {len(all_games)}")
            
            if dry_run:
                print("\n[DRY RUN] Would scrape:")
                for g in all_games[:10]:
                    print(f"  Week {g['week']}: {g['away_team']} @ {g['home_team']}")
                if len(all_games) > 10:
                    print(f"  ... and {len(all_games) - 10} more")
                return
            
            # Estimate time
            avg_delay = (self.api.GAME_DELAY_MIN + self.api.GAME_DELAY_MAX) / 2
            total_time_min = len(all_games) * avg_delay / 60
            print(f"⏱️  Estimated time: {total_time_min:.0f} minutes")
            print(f"\n🚀 Starting at {datetime.now().strftime('%H:%M:%S')}...\n")
            
            # Scrape each game
            for i, game in enumerate(all_games):
                game_id = game['game_id']
                print(f"[{i+1}/{len(all_games)}] Week {game['week']}: {game['away_team']} @ {game['home_team']}...", end=' ', flush=True)
                
                try:
                    plays = await self.api.get_plays(game_id)
                    
                    if plays:
                        self.save_game(game, plays)
                        print(f"✓ {len(plays)} plays")
                    else:
                        print("⚠ No plays found")
                
                except Exception as e:
                    print(f"✗ Error: {e}")
                    logger.exception(f"Error scraping game {game_id}")
                
                # Rate limiting between games
                if i < len(all_games) - 1:
                    delay = random.uniform(self.api.GAME_DELAY_MIN, self.api.GAME_DELAY_MAX)
                    print(f"    Waiting {delay:.0f}s...")
                    await asyncio.sleep(delay)
            
            print(f"\n{'='*60}")
            print("✅ Dataset build complete!")
            print(f"{'='*60}")
            
        finally:
            await self.api.close()
    
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
    
    def get_stats(self):
        """Get database statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM games')
        game_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM plays')
        play_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT week, COUNT(*) FROM games GROUP BY week ORDER BY week')
        by_week = dict(cursor.fetchall())
        
        conn.close()
        
        return {
            'games': game_count,
            'plays': play_count,
            'by_week': by_week,
        }


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='NFL Pro Season Dataset Builder')
    parser.add_argument('--season', type=int, default=2024, help='Season year')
    parser.add_argument('--weeks', type=str, default='1-17', help='Weeks (e.g., "1-17" or "1,2,3")')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be scraped')
    parser.add_argument('--export', action='store_true', help='Export to CSV only')
    parser.add_argument('--stats', action='store_true', help='Show statistics')
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Parse weeks
    if '-' in args.weeks:
        start, end = args.weeks.split('-')
        weeks = list(range(int(start), int(end) + 1))
    else:
        weeks = [int(w) for w in args.weeks.split(',')]
    
    builder = SeasonDatasetBuilder(args.season)
    
    if args.stats:
        stats = builder.get_stats()
        print(f"\n📊 Database Stats ({args.season})")
        print(f"   Games: {stats['games']}")
        print(f"   Plays: {stats['plays']:,}")
        if stats['by_week']:
            print("   By week:", dict(sorted(stats['by_week'].items())))
        return
    
    if args.export:
        builder.export_csv()
        return
    
    await builder.build_dataset(weeks=weeks, dry_run=args.dry_run)


if __name__ == '__main__':
    asyncio.run(main())

