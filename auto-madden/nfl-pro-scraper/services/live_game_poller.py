"""
Live Game Poller

Polls NFL Pro API for live play-by-play data with rich metadata,
falling back to ESPN if NFL Pro is unavailable.

Features:
- Primary: NFL Pro API (personnel, formation, defenders in box)
- Fallback: ESPN API (basic play info)
- Graceful degradation when NFL Pro fails
- Event emission to insight engine
- Delay-aware (works with 60-90s viewing delay)

Usage:
    python live_game_poller.py --game-uuid <UUID> --espn-id <ID>
    python live_game_poller.py --auto  # Auto-detect live game
"""

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import requests

# Add parent paths
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'scrapers'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
INSIGHT_ENGINE_URL = os.environ.get('INSIGHT_ENGINE_URL', 'http://localhost:5131')
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
ESPN_SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary"

CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '/Volumes/main-drive/ai-PA/auto-madden/credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'


@dataclass
class PlayData:
    """Normalized play data from either source."""
    play_id: int
    sequence: int
    quarter: int
    clock: str
    down: int
    distance: int
    yard_line: str
    possession_team: str
    description: str
    yards_gained: int = 0
    home_score: int = 0
    away_score: int = 0
    
    # Rich metadata (NFL Pro only)
    play_type: str = ''
    formation: str = ''
    personnel: str = ''
    defenders_in_box: int = 0
    pass_rushers: int = 0
    coverage_type: str = ''
    is_redzone: bool = False
    
    # Source tracking
    source: str = 'unknown'  # 'nfl_pro' or 'espn'
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def has_rich_metadata(self) -> bool:
        """Check if this play has NFL Pro enriched data."""
        return bool(self.formation or self.personnel or self.defenders_in_box)


class NFLProPoller:
    """Polls NFL Pro API for live play data."""

    BASE_URL = "https://pro.nfl.com"
    PLAYS_API = "/api/secured/plays/playlist/game"
    SCHEDULE_API = "/api/schedules/game"

    def __init__(self):
        self._session = None
        self._cookies = None
        self._access_token = None
        self._last_play_id: Optional[int] = None
        self._consecutive_failures = 0
        self._available = True
        self._uuid_to_numeric: Dict[str, str] = {}  # Cache UUID -> numeric ID mapping
        self._load_session()

    def _load_session(self):
        """Load browser session for authenticated requests."""
        state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'

        if not state_file.exists():
            logger.warning("No NFL Pro session found - NFL Pro polling disabled")
            self._available = False
            return

        try:
            with open(state_file) as f:
                state = json.load(f)

            # Extract cookies - include all nfl.com cookies
            self._cookies = {}
            for cookie in state.get('cookies', []):
                domain = cookie.get('domain', '')
                # Include nfl.com, .nfl.com, auth-id.nfl.com, etc.
                if 'nfl.com' in domain:
                    self._cookies[cookie['name']] = cookie['value']

            # Extract Bearer token from localStorage
            for origin in state.get('origins', []):
                if origin.get('origin') == 'https://id.nfl.com':
                    for item in origin.get('localStorage', []):
                        if item.get('name') == 'nfl.refreshableToken.v3':
                            try:
                                token_data = json.loads(item.get('value', '{}'))
                                self._access_token = token_data.get('rawData', {}).get('accessToken')
                                if self._access_token:
                                    logger.info("Loaded NFL Pro Bearer token from localStorage")
                            except Exception as e:
                                logger.warning(f"Error parsing token: {e}")
                            break
                    break

            if self._access_token:
                logger.info(f"Loaded {len(self._cookies)} NFL Pro cookies + Bearer token")
                self._available = True
            elif self._cookies:
                logger.info(f"Loaded {len(self._cookies)} NFL Pro cookies (no Bearer token)")
                self._available = True
            else:
                logger.warning("No NFL Pro credentials found")
                self._available = False
        except Exception as e:
            logger.error(f"Error loading NFL Pro session: {e}")
            self._available = False
    
    def is_available(self) -> bool:
        """Check if NFL Pro polling is available."""
        return self._available and self._consecutive_failures < 5

    def _get_numeric_game_id(self, game_uuid: str) -> Optional[str]:
        """Convert NFL Pro UUID to numeric game ID via schedules API."""
        # Check cache first
        if game_uuid in self._uuid_to_numeric:
            return self._uuid_to_numeric[game_uuid]

        try:
            url = f"{self.BASE_URL}{self.SCHEDULE_API}?fapiGameId={game_uuid}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
                'Accept': 'application/json',
                'Referer': f'{self.BASE_URL}/'
            }
            if self._access_token:
                headers['Authorization'] = f'Bearer {self._access_token}'

            response = requests.get(url, headers=headers, cookies=self._cookies, timeout=10, verify=False)
            if response.status_code == 200:
                data = response.json()
                numeric_id = data.get('gameId')
                if numeric_id:
                    self._uuid_to_numeric[game_uuid] = str(numeric_id)
                    logger.info(f"Resolved UUID {game_uuid[:8]}... to numeric ID {numeric_id}")
                    return str(numeric_id)
        except Exception as e:
            logger.warning(f"Error resolving game UUID: {e}")
        return None

    async def get_plays(self, game_uuid: str) -> List[PlayData]:
        """Fetch plays from NFL Pro API."""
        if not self.is_available():
            return []

        try:
            # Convert UUID to numeric game ID
            numeric_id = self._get_numeric_game_id(game_uuid)
            if not numeric_id:
                logger.warning(f"Could not resolve game UUID {game_uuid[:8]}... to numeric ID")
                return []

            url = f"{self.BASE_URL}{self.PLAYS_API}?gameId={numeric_id}"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
                'Accept': 'application/json',
                'Referer': f'{self.BASE_URL}/games/game/{game_uuid}/play-by-play'
            }

            # Add Bearer token if available
            if self._access_token:
                headers['Authorization'] = f'Bearer {self._access_token}'

            response = requests.get(
                url,
                headers=headers,
                cookies=self._cookies,
                timeout=10,
                verify=False
            )

            if response.status_code == 401:
                logger.warning("NFL Pro session expired")
                self._available = False
                return []

            response.raise_for_status()
            data = response.json()

            self._consecutive_failures = 0
            return self._parse_plays(data)
            
        except Exception as e:
            self._consecutive_failures += 1
            logger.warning(f"NFL Pro API error ({self._consecutive_failures}/5): {e}")
            return []
    
    def _parse_plays(self, data: Dict) -> List[PlayData]:
        """Parse NFL Pro API response into PlayData objects."""
        plays = []

        raw_plays = data.get('plays', data.get('playlist', []))

        for raw in raw_plays:
            try:
                # Skip marker plays
                if raw.get('playType') == 'GAME':
                    continue

                # Extract nested objects - API returns offense/defense/passInfo as nested dicts
                offense = raw.get('offense', {}) or {}
                defense = raw.get('defense', {}) or {}
                pass_info = raw.get('passInfo', {}) or {}
                rec_info = raw.get('recInfo', {}) or {}

                # Format coverage type nicely
                coverage = defense.get('coverageType', '')
                if coverage:
                    coverage = coverage.replace('COVER_', 'Cover ').replace('_', ' ')
                man_zone = defense.get('manZoneType', '')
                if man_zone:
                    man_zone = 'Man' if 'MAN' in man_zone else 'Zone' if 'ZONE' in man_zone else ''
                if coverage and man_zone:
                    coverage = f"{coverage} ({man_zone})"

                play = PlayData(
                    play_id=raw.get('playId', 0),
                    sequence=raw.get('sequence', 0),
                    quarter=raw.get('quarter', 0),
                    clock=raw.get('endClock', raw.get('startClock', '')),
                    down=raw.get('down', 0),
                    distance=raw.get('yardsToGo', 0),
                    yard_line=raw.get('yardLine', ''),
                    possession_team=raw.get('possessionTeam', ''),
                    description=raw.get('playDescription', ''),
                    yards_gained=raw.get('yardsGained', 0),
                    home_score=raw.get('homeScore', 0),
                    away_score=raw.get('visitorScore', 0),
                    play_type=raw.get('playType', ''),
                    formation=offense.get('offenseFormation', ''),
                    personnel=offense.get('personnel', ''),
                    defenders_in_box=defense.get('defendersInTheBox', 0) or 0,
                    pass_rushers=defense.get('numberOfPassRushers', 0) or 0,
                    coverage_type=coverage,
                    is_redzone=raw.get('isRedzone', False),
                    source='nfl_pro'
                )
                plays.append(play)
            except Exception as e:
                logger.debug(f"Error parsing play: {e}")

        return plays


class ESPNPoller:
    """Polls ESPN API for live play data (fallback)."""
    
    def __init__(self):
        self._last_play_id: Optional[int] = None
    
    async def get_plays(self, espn_game_id: str) -> List[PlayData]:
        """Fetch plays from ESPN API."""
        try:
            url = f"{ESPN_SUMMARY_URL}?event={espn_game_id}"
            response = requests.get(url, timeout=10, verify=False)
            response.raise_for_status()
            data = response.json()
            
            return self._parse_plays(data)
        except Exception as e:
            logger.warning(f"ESPN API error: {e}")
            return []
    
    def _parse_plays(self, data: Dict) -> List[PlayData]:
        """Parse ESPN API response into PlayData objects."""
        plays = []
        
        drives = data.get('drives', {})
        all_plays = []
        
        # Get plays from current drive
        if 'current' in drives and drives['current'].get('plays'):
            all_plays.extend(drives['current']['plays'])
        
        # Get plays from previous drives
        for drive in drives.get('previous', []):
            all_plays.extend(drive.get('plays', []))
        
        for raw in all_plays:
            try:
                start = raw.get('start', {})
                end = raw.get('end', {})
                clock = raw.get('clock', {})
                period = raw.get('period', {})
                play_type = raw.get('type', {})
                
                play = PlayData(
                    play_id=raw.get('id', 0),
                    sequence=raw.get('sequenceNumber', 0),
                    quarter=period.get('number', 0),
                    clock=clock.get('displayValue', ''),
                    down=start.get('down', 0),
                    distance=start.get('distance', 0),
                    yard_line=f"{start.get('yardLine', '')}",
                    possession_team=start.get('team', {}).get('abbreviation', ''),
                    description=raw.get('text', ''),
                    yards_gained=raw.get('statYardage', 0),
                    home_score=raw.get('homeScore', 0),
                    away_score=raw.get('awayScore', 0),
                    play_type=play_type.get('text', ''),
                    source='espn'
                )
                plays.append(play)
            except Exception as e:
                logger.debug(f"Error parsing ESPN play: {e}")
        
        return plays


class LiveGamePoller:
    """
    Orchestrates live game polling from multiple sources.
    
    Tries NFL Pro first for rich metadata, falls back to ESPN.
    Emits events to the insight engine for processing.
    """
    
    def __init__(
        self,
        nfl_pro_uuid: str = None,
        espn_game_id: str = None,
        poll_interval: int = 15
    ):
        self.nfl_pro_uuid = nfl_pro_uuid
        self.espn_game_id = espn_game_id
        self.poll_interval = poll_interval
        
        self.nfl_pro = NFLProPoller()
        self.espn = ESPNPoller()
        
        self._running = False
        self._last_play_id: Optional[int] = None
        self._plays_seen: set = set()
        self._stats = {
            'nfl_pro_polls': 0,
            'nfl_pro_successes': 0,
            'espn_polls': 0,
            'espn_successes': 0,
            'plays_detected': 0,
            'events_sent': 0
        }
    
    def get_stats(self) -> Dict:
        """Get polling statistics."""
        return self._stats.copy()
    
    async def start(self):
        """Start the polling loop."""
        self._running = True
        logger.info(f"Starting live poller (NFL Pro: {self.nfl_pro_uuid[:8] if self.nfl_pro_uuid else 'N/A'}, ESPN: {self.espn_game_id or 'N/A'})")
        logger.info(f"Poll interval: {self.poll_interval}s")
        logger.info(f"NFL Pro available: {self.nfl_pro.is_available()}")
        
        while self._running:
            try:
                await self._poll_cycle()
            except Exception as e:
                logger.error(f"Poll cycle error: {e}")
            
            await asyncio.sleep(self.poll_interval)
    
    def stop(self):
        """Stop the polling loop."""
        self._running = False
        logger.info("Poller stopped")
        logger.info(f"Stats: {self._stats}")
    
    async def _poll_cycle(self):
        """Execute one polling cycle."""
        plays = []
        source = 'none'
        
        # Try NFL Pro first
        if self.nfl_pro_uuid and self.nfl_pro.is_available():
            self._stats['nfl_pro_polls'] += 1
            plays = await self.nfl_pro.get_plays(self.nfl_pro_uuid)
            if plays:
                self._stats['nfl_pro_successes'] += 1
                source = 'nfl_pro'
                logger.debug(f"NFL Pro returned {len(plays)} plays")
        
        # Fallback to ESPN
        if not plays and self.espn_game_id:
            self._stats['espn_polls'] += 1
            plays = await self.espn.get_plays(self.espn_game_id)
            if plays:
                self._stats['espn_successes'] += 1
                source = 'espn'
                logger.debug(f"ESPN returned {len(plays)} plays")
        
        if not plays:
            return
        
        # Find new plays
        new_plays = []
        for play in plays:
            if play.play_id not in self._plays_seen:
                self._plays_seen.add(play.play_id)
                new_plays.append(play)
        
        if new_plays:
            self._stats['plays_detected'] += len(new_plays)
            logger.info(f"Detected {len(new_plays)} new plays from {source}")
            
            for play in new_plays:
                await self._emit_play_event(play)
    
    async def _emit_play_event(self, play: PlayData):
        """Send play event to insight engine."""
        try:
            # Build event payload with nfl_pro_play in expected format
            event = {
                'event_type': 'play_complete',
                'description': play.description,
                'state': {
                    'quarter': play.quarter,
                    'clock': play.clock,
                    'down': play.down,
                    'distance': play.distance,
                    'home_team': {'score': play.home_score},
                    'away_team': {'score': play.away_score},
                    'possession_team': play.possession_team,
                    'last_play_id': play.play_id,
                },
                # NFL Pro play data in the format insight engine expects
                'nfl_pro_play': {
                    'playDescription': play.description,
                    'playType': play.play_type,
                    'offense': {
                        'personnel': play.personnel,
                        'offenseFormation': play.formation,
                    },
                    'defense': {
                        'defendersInTheBox': play.defenders_in_box,
                        'numberOfPassRushers': play.pass_rushers,
                        'coverageType': play.coverage_type,
                    },
                    'isRedzone': play.is_redzone,
                    'yardsGained': play.yards_gained,
                },
                # Also keep pre_play_data for backwards compatibility
                'pre_play_data': {
                    'personnel': play.personnel,
                    'formation': play.formation,
                    'defenders_in_box': play.defenders_in_box,
                    'pass_rushers': play.pass_rushers,
                    'coverage_type': play.coverage_type,
                    'is_redzone': play.is_redzone,
                    'play_type': play.play_type,
                    'source': play.source
                }
            }
            
            response = requests.post(
                f"{INSIGHT_ENGINE_URL}/event",
                json=event,
                timeout=5
            )
            
            if response.status_code == 200:
                self._stats['events_sent'] += 1
                logger.debug(f"Event sent: {play.description[:50]}...")
            else:
                logger.warning(f"Event failed: {response.status_code}")
                
        except Exception as e:
            logger.warning(f"Could not send event: {e}")


async def find_live_game() -> tuple:
    """Find a live game and return (nfl_pro_uuid, espn_id)."""
    from game_mapper import GameMapper
    mapper = GameMapper()
    
    try:
        response = requests.get(ESPN_SCOREBOARD_URL, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()
        
        for event in data.get('events', []):
            status = event.get('status', {}).get('type', {}).get('name', '')
            if status in ['STATUS_IN_PROGRESS', 'STATUS_HALFTIME']:
                espn_id = event.get('id')
                name = event.get('shortName', '')
                
                # Extract teams from event for mapping
                competitions = event.get('competitions', [{}])
                if competitions:
                    comp = competitions[0]
                    teams = comp.get('competitors', [])
                    home_team = next((t.get('team', {}).get('abbreviation') for t in teams if t.get('homeAway') == 'home'), None)
                    away_team = next((t.get('team', {}).get('abbreviation') for t in teams if t.get('homeAway') == 'away'), None)
                    
                    # Try to map to NFL Pro UUID
                    nfl_pro_uuid = mapper.get_nfl_pro_uuid(espn_id, home_team, away_team)
                    if nfl_pro_uuid:
                        logger.info(f"Found live game: {name} (ESPN: {espn_id}, NFL Pro: {nfl_pro_uuid[:8]})")
                    else:
                        logger.info(f"Found live game: {name} (ESPN: {espn_id}, NFL Pro: not mapped)")
                    
                    return (nfl_pro_uuid, espn_id)
                
                logger.info(f"Found live game: {name} (ESPN: {espn_id})")
                return (None, espn_id)
        
        # Check for upcoming
        for event in data.get('events', []):
            status = event.get('status', {}).get('type', {}).get('name', '')
            if status == 'STATUS_SCHEDULED':
                espn_id = event.get('id')
                name = event.get('shortName', '')
                logger.info(f"Found upcoming game: {name} (ESPN: {espn_id})")
                return (None, espn_id)
                
    except Exception as e:
        logger.error(f"Could not find live game: {e}")
    
    return (None, None)


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Live Game Poller')
    parser.add_argument('--game-uuid', help='NFL Pro game UUID')
    parser.add_argument('--espn-id', help='ESPN game ID')
    parser.add_argument('--auto', action='store_true', help='Auto-detect live game')
    parser.add_argument('--interval', type=int, default=15, help='Poll interval (seconds)')
    parser.add_argument('--test', action='store_true', help='Test mode - single poll')
    
    args = parser.parse_args()
    
    nfl_pro_uuid = args.game_uuid
    espn_id = args.espn_id
    
    if args.auto:
        nfl_pro_uuid, espn_id = await find_live_game()
        if not espn_id:
            logger.error("No live game found")
            return
    
    if not nfl_pro_uuid and not espn_id:
        logger.error("Must specify --game-uuid, --espn-id, or --auto")
        parser.print_help()
        return
    
    poller = LiveGamePoller(
        nfl_pro_uuid=nfl_pro_uuid,
        espn_game_id=espn_id,
        poll_interval=args.interval
    )
    
    if args.test:
        # Single poll for testing
        await poller._poll_cycle()
        print(f"\nStats: {poller.get_stats()}")
    else:
        # Run continuously
        try:
            await poller.start()
        except KeyboardInterrupt:
            poller.stop()


if __name__ == '__main__':
    asyncio.run(main())

