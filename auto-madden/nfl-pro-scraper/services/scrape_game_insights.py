#!/usr/bin/env python3
"""
Single Game Insight Scraper

Fetches insights for a specific game from NFL Pro API and saves to database.

Usage:
    python scrape_game_insights.py --game-id 8522d92f-e9e3-11f0-9442-5911216651e2 --week 18
    python scrape_game_insights.py --game-id 8522d92f --week 18  # Short UUID works too
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests

# Add parent paths
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '/Volumes/main-drive/ai-PA/auto-madden/credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'
DATA_PATH = Path(os.environ.get('DATA_PATH', '/Volumes/main-drive/ai-PA/auto-madden/data'))

INSIGHTS_API = "https://pro.nfl.com/api/content/insights/game"
SEASON = 2025


class GameInsightScraper:
    """Scrapes insights for a single game."""

    def __init__(self):
        self._cookies = {}
        self._access_token = None
        self.insights_db_path = DATA_PATH / f"nfl_insights_{SEASON}.db"
        self._load_credentials()

    def _load_credentials(self):
        """Load cookies and Bearer token from browser state."""
        state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'

        if not state_file.exists():
            logger.warning(f"No session file at {state_file}")
            return

        try:
            with open(state_file) as f:
                state = json.load(f)

            # Load cookies
            for cookie in state.get('cookies', []):
                if 'nfl.com' in cookie.get('domain', ''):
                    self._cookies[cookie['name']] = cookie['value']

            # Extract Bearer token from localStorage
            for entry in state.get('origins', []):
                if 'nfl.com' in entry.get('origin', ''):
                    for item in entry.get('localStorage', []):
                        if 'accessToken' in item.get('name', '').lower():
                            try:
                                token_data = json.loads(item.get('value', '{}'))
                                self._access_token = token_data.get('secret')
                                if self._access_token:
                                    logger.info("Loaded NFL Pro Bearer token")
                            except:
                                pass

            logger.info(f"Loaded {len(self._cookies)} NFL Pro cookies")
        except Exception as e:
            logger.error(f"Error loading credentials: {e}")

    def fetch_insights(self, game_id: str) -> Optional[Dict]:
        """Fetch insights from NFL Pro API."""
        if not self._cookies:
            logger.error("No credentials available")
            return None

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
            'Accept': 'application/json',
            'Referer': 'https://pro.nfl.com/',
        }

        if self._access_token:
            headers['Authorization'] = f'Bearer {self._access_token}'

        # Try with full game ID first
        url = f"{INSIGHTS_API}?season={SEASON}&limit=100&gameId={game_id}"

        try:
            response = requests.get(
                url,
                headers=headers,
                cookies=self._cookies,
                timeout=15,
                verify=False
            )

            if response.status_code == 401:
                logger.error("NFL Pro session expired - need to re-authenticate")
                return None

            if response.status_code == 200:
                data = response.json()
                logger.info(f"Fetched {len(data.get('data', []))} insights for game {game_id[:8]}")
                return data

            logger.warning(f"API returned status {response.status_code}")
            return None

        except Exception as e:
            logger.error(f"Error fetching insights: {e}")
            return None

    def save_insights(self, insights_data: Dict, game_id: str, week: int):
        """Save insights to database."""
        if not insights_data or 'data' not in insights_data:
            logger.warning("No insights to save")
            return 0

        # Ensure database exists
        self._init_database()

        conn = sqlite3.connect(self.insights_db_path)
        cursor = conn.cursor()
        count = 0

        for i in insights_data.get('data', []):
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO insights (
                        insight_id, game_id, season, week, title, sub_note, sub_note2,
                        player_name, position, team_abbr, jersey_number,
                        second_player_name, second_position, second_team_abbr, second_team_type,
                        image_url, headshot_url, tags, date_created, scraped_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    str(i.get('id', '')),
                    game_id,
                    SEASON,
                    week,
                    i.get('title', ''),
                    i.get('subNote1', ''),
                    i.get('subNote2', ''),
                    i.get('playerName', ''),
                    i.get('position1', ''),
                    i.get('teamAbbr', ''),
                    i.get('jerseyNumber'),
                    i.get('secondPlayerName', ''),
                    i.get('secondPosition', ''),
                    i.get('secondTeamAbbr', ''),
                    i.get('secondTeamType', ''),
                    i.get('imageUrl', ''),
                    i.get('headshot', ''),
                    json.dumps(i.get('tags', [])),
                    i.get('date', ''),
                    datetime.now().isoformat()
                ))
                count += 1
            except Exception as e:
                logger.warning(f"Error saving insight: {e}")

        conn.commit()
        conn.close()
        logger.info(f"Saved {count} insights for game {game_id[:8]} to {self.insights_db_path}")
        return count

    def _init_database(self):
        """Ensure database table exists."""
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
                player_name TEXT,
                position TEXT,
                team_abbr TEXT,
                jersey_number INTEGER,
                second_player_name TEXT,
                second_position TEXT,
                second_team_abbr TEXT,
                second_team_type TEXT,
                image_url TEXT,
                headshot_url TEXT,
                image_cached INTEGER DEFAULT 0,
                tags TEXT,
                date_created TEXT,
                scraped_at TEXT,
                times_served INTEGER DEFAULT 0,
                last_served_game TEXT,
                local_image TEXT,
                insight_category TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def scrape_game(self, game_id: str, week: int) -> int:
        """Scrape insights for a game and save to database."""
        logger.info(f"Scraping insights for game {game_id[:8]}... (Week {week})")

        insights_data = self.fetch_insights(game_id)
        if not insights_data:
            return 0

        return self.save_insights(insights_data, game_id, week)


def main():
    parser = argparse.ArgumentParser(description='Scrape insights for a specific game')
    parser.add_argument('--game-id', required=True, help='NFL Pro game UUID')
    parser.add_argument('--week', type=int, required=True, help='Week number')
    args = parser.parse_args()

    scraper = GameInsightScraper()
    count = scraper.scrape_game(args.game_id, args.week)

    if count > 0:
        print(f"\n✅ Successfully scraped {count} insights for game {args.game_id[:8]}")
    else:
        print(f"\n❌ No insights scraped - check credentials or game ID")

    return 0 if count > 0 else 1


if __name__ == '__main__':
    sys.exit(main())
