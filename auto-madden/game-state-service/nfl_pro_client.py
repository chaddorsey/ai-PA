#!/usr/bin/env python3
"""
NFL Pro API Client for real-time play-by-play data.

Provides rich metadata including:
- Offensive personnel and formation
- Defensive alignment and box count
- Coverage type and rushers
- Time to throw, routes, air yards
"""

import json
import logging
import os
import requests
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Configuration - supports both Docker and local paths
_default_creds = '/credentials' if Path('/credentials').exists() else '/Volumes/main-drive/ai-PA/auto-madden/credentials'
CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', _default_creds))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'
_default_engine_url = 'http://auto-madden-insight-engine:5131' if os.environ.get('DOCKER_ENV') else 'http://localhost:5131'
INSIGHT_ENGINE_URL = os.environ.get('INSIGHT_ENGINE_URL', _default_engine_url)


@dataclass
class NFLProPlay:
    """Rich play data from NFL Pro API."""
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

    # Offensive data
    personnel: str = ''  # "11", "12", "21"
    formation: str = ''  # "SHOTGUN", "SINGLEBACK"

    # Defensive data
    defenders_in_box: int = 0
    pass_rushers: int = 0
    coverage_type: str = ''  # "Cover 3 (Zone)"
    man_zone: str = ''  # "Man" or "Zone"

    # Pass play data
    time_to_throw: float = 0.0
    air_yards: float = 0.0
    route: str = ''
    was_pressure: bool = False

    # Flags
    is_redzone: bool = False
    is_big_play: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)

    def has_rich_data(self) -> bool:
        """Check if this play has NFL Pro enriched data."""
        return bool(self.formation or self.personnel or self.defenders_in_box)


class NFLProClient:
    """Client for NFL Pro real-time play-by-play API."""

    BASE_URL = "https://pro.nfl.com"
    PLAYS_API = "/api/secured/plays/playlist/game"
    SCHEDULE_API = "/api/schedules/game"

    def __init__(self):
        self._cookies: Dict[str, str] = {}
        self._access_token: Optional[str] = None
        self._available = False
        self._consecutive_failures = 0
        self._uuid_to_numeric: Dict[str, str] = {}
        self._last_token_check = 0

        self._load_credentials()

    def _load_credentials(self):
        """Load cookies and Bearer token from browser state."""
        state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'

        if not state_file.exists():
            logger.warning(f"No NFL Pro session file at {state_file}")
            self._available = False
            return

        try:
            with open(state_file) as f:
                state = json.load(f)

            # Load cookies
            self._cookies = {}
            for cookie in state.get('cookies', []):
                domain = cookie.get('domain', '')
                if 'nfl.com' in domain:
                    self._cookies[cookie['name']] = cookie['value']

            # Extract Bearer token from localStorage
            self._access_token = None
            for origin in state.get('origins', []):
                if 'nfl.com' in origin.get('origin', ''):
                    for item in origin.get('localStorage', []):
                        if item.get('name') == 'nfl.refreshableToken.v3':
                            try:
                                token_data = json.loads(item.get('value', '{}'))
                                self._access_token = token_data.get('rawData', {}).get('accessToken')
                                if self._access_token:
                                    logger.info("Loaded NFL Pro Bearer token")
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

    def _ensure_token_fresh(self):
        """Check with insight engine if token needs refresh."""
        now = datetime.now().timestamp()

        # Only check every 30 seconds
        if now - self._last_token_check < 30:
            return

        self._last_token_check = now

        try:
            # Call insight engine to check/refresh token
            resp = requests.get(f"{INSIGHT_ENGINE_URL}/api/nfl-pro/status", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('refreshed'):
                    logger.info("Token was refreshed, reloading credentials")
                    self._load_credentials()
                elif not data.get('authenticated'):
                    logger.warning("NFL Pro session not authenticated")
                    self._available = False
        except Exception as e:
            logger.debug(f"Could not check token status: {e}")

    def is_available(self) -> bool:
        """Check if NFL Pro polling is available."""
        self._ensure_token_fresh()
        return self._available and self._consecutive_failures < 5

    def get_numeric_game_id(self, game_uuid: str) -> Optional[str]:
        """Convert NFL Pro UUID to numeric game ID via schedules API."""
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
                numeric_id = data.get('game', {}).get('id')
                if numeric_id:
                    self._uuid_to_numeric[game_uuid] = str(numeric_id)
                    logger.info(f"Mapped UUID {game_uuid[:8]} to numeric ID {numeric_id}")
                    return str(numeric_id)
        except Exception as e:
            logger.warning(f"Error getting numeric game ID: {e}")

        return None

    def get_plays(self, game_uuid: str) -> List[NFLProPlay]:
        """Fetch plays from NFL Pro via insight engine proxy."""
        if not self.is_available():
            return []

        try:
            # Call insight engine which uses Playwright for authenticated access
            url = f"{INSIGHT_ENGINE_URL}/api/nfl-pro/plays/{game_uuid}"
            response = requests.get(url, timeout=45)  # Longer timeout for Playwright

            if response.status_code == 404:
                logger.debug("No plays found from NFL Pro")
                return []

            if response.status_code != 200:
                self._consecutive_failures += 1
                logger.warning(f"NFL Pro plays API error ({self._consecutive_failures}/5): {response.status_code}")
                return []

            data = response.json()

            if data.get('status') != 'ok':
                logger.warning(f"NFL Pro API returned error: {data.get('message')}")
                return []

            self._consecutive_failures = 0
            return self._parse_plays_from_insight_engine(data.get('plays', []))

        except Exception as e:
            self._consecutive_failures += 1
            logger.warning(f"NFL Pro API error ({self._consecutive_failures}/5): {e}")
            return []

    def _parse_plays_from_insight_engine(self, plays: List[Dict]) -> List[NFLProPlay]:
        """Parse plays from insight engine response."""
        result = []
        for p in plays:
            try:
                offense = p.get('offense', {})
                defense = p.get('defense', {})
                pass_info = p.get('passInfo', {})
                rec_info = p.get('recInfo', {})

                play = NFLProPlay(
                    play_id=p.get('playId', 0),
                    sequence=p.get('sequence', 0),
                    quarter=p.get('quarter', 0),
                    clock=p.get('clock', ''),
                    down=p.get('down', 0),
                    distance=p.get('distance', 0),
                    yard_line=p.get('yardLine', ''),
                    possession_team=p.get('possessionTeam', ''),
                    description=p.get('playDescription', ''),
                    yards_gained=p.get('yardsGained', 0),
                    personnel=offense.get('personnel', ''),
                    formation=offense.get('offenseFormation', ''),
                    defenders_in_box=defense.get('defendersInTheBox', 0) or 0,
                    pass_rushers=defense.get('numberOfPassRushers', 0) or 0,
                    coverage_type=defense.get('coverageType', ''),
                    man_zone=defense.get('manZoneType', ''),
                    time_to_throw=pass_info.get('timeToThrow', 0) or 0,
                    air_yards=pass_info.get('airYards', 0) or 0,
                    route=rec_info.get('route', ''),
                    was_pressure=pass_info.get('wasPressure', False),
                    is_redzone=p.get('isRedzone', False),
                    is_big_play=p.get('yardsGained', 0) >= 15
                )
                result.append(play)
            except Exception as e:
                logger.debug(f"Error parsing play: {e}")
        return result

    def _parse_plays(self, data: Dict) -> List[NFLProPlay]:
        """Parse NFL Pro API response into NFLProPlay objects."""
        plays = []

        raw_plays = data.get('plays', data.get('playlist', []))

        for raw in raw_plays:
            try:
                # Skip marker plays
                if raw.get('playType') == 'GAME':
                    continue

                # Extract nested objects
                offense = raw.get('offense', {}) or {}
                defense = raw.get('defense', {}) or {}
                pass_info = raw.get('passInfo', {}) or {}
                rec_info = raw.get('recInfo', {}) or {}

                # Format coverage type
                coverage = defense.get('coverageType', '')
                if coverage:
                    coverage = coverage.replace('COVER_', 'Cover ').replace('_', ' ')

                man_zone = defense.get('manZoneType', '')
                if man_zone:
                    man_zone = 'Man' if 'MAN' in man_zone else 'Zone' if 'ZONE' in man_zone else ''

                if coverage and man_zone:
                    coverage = f"{coverage} ({man_zone})"

                play = NFLProPlay(
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
                    personnel=offense.get('personnel', ''),
                    formation=offense.get('offenseFormation', ''),
                    defenders_in_box=defense.get('defendersInTheBox', 0) or 0,
                    pass_rushers=defense.get('numberOfPassRushers', 0) or 0,
                    coverage_type=coverage,
                    man_zone=man_zone,
                    time_to_throw=pass_info.get('timeToThrow', 0) or 0,
                    air_yards=pass_info.get('airYards', 0) or 0,
                    route=rec_info.get('route', ''),
                    was_pressure=pass_info.get('wasPressure', False),
                    is_redzone=raw.get('isRedzone', False),
                    is_big_play=raw.get('yardsGained', 0) >= 15
                )
                plays.append(play)
            except Exception as e:
                logger.debug(f"Error parsing play: {e}")

        return plays

    def get_latest_play(self, game_uuid: str) -> Optional[NFLProPlay]:
        """Get the most recent play with rich data from NFL Pro."""
        plays = self.get_plays(game_uuid)
        if plays:
            # Sort by sequence descending
            plays.sort(key=lambda p: p.sequence, reverse=True)
            # Return first play with actual data (personnel/formation)
            for play in plays:
                if play.has_rich_data():
                    return play
            # Fall back to most recent if none have data
            return plays[0]
        return None
