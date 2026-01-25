#!/usr/bin/env python3
"""
Auto-Madden Insight Engine.

Generates and delivers real-time game insights based on game state changes.
"""

import asyncio
import json
import logging
import os
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

import yaml
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sock import Sock

# Import game context loader
try:
    from game_context import (
        game_context_loader, load_game_context, get_break_content, 
        get_llm_context, generate_pregame_insights, ESPN_ABBR_TO_ID
    )
except ImportError:
    game_context_loader = None
    load_game_context = None
    get_break_content = None
    get_llm_context = None
    generate_pregame_insights = None
    ESPN_ABBR_TO_ID = {}

# Import NFL Pro narrative insight integration
try:
    from nfl_pro_integration import (
        nfl_pro_narratives,
        load_narrative_insights,
        get_player_triggered_insight,
        get_break_narrative_insights,
        get_pregame_narrative_insights,
        get_narrative_llm_context,
        get_contextual_narrative_insight,
    )
    NFL_PRO_NARRATIVES_AVAILABLE = True
except ImportError:
    nfl_pro_narratives = None
    load_narrative_insights = None
    get_player_triggered_insight = None
    get_break_narrative_insights = None
    get_pregame_narrative_insights = None
    get_narrative_llm_context = None
    get_contextual_narrative_insight = None
    NFL_PRO_NARRATIVES_AVAILABLE = False

# Import pre-play metadata service
try:
    import sys
    from pathlib import Path
    # Add nfl-pro-scraper to path - check multiple locations
    scraper_paths = [
        Path(__file__).parent.parent / 'nfl-pro-scraper',  # /nfl-pro-scraper
        Path(__file__).parent / 'nfl-pro-scraper',  # /app/nfl-pro-scraper
        Path('/app/nfl-pro-scraper'),  # Docker mount location
        Path('/Volumes/main-drive/ai-PA/auto-madden/nfl-pro-scraper'),  # Host path
    ]
    scraper_path = None
    for p in scraper_paths:
        if p.exists():
            scraper_path = p.resolve()
            sys.path.insert(0, str(scraper_path))
            break

    # Import directly from file to avoid services/__init__.py which needs playwright
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "pre_play_service",
        str(scraper_path / "services" / "pre_play_service.py")
    )
    pre_play_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pre_play_module)
    PrePlayService = pre_play_module.PrePlayService
    UserPreferences = pre_play_module.UserPreferences
    process_pre_play = pre_play_module.process_pre_play
    from models.pre_play_metadata import MetadataFrequency
    PRE_PLAY_SERVICE_AVAILABLE = True
except ImportError as e:
    PrePlayService = None
    UserPreferences = None
    process_pre_play = None
    MetadataFrequency = None
    PRE_PLAY_SERVICE_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)
sock = Sock(app)

# Configuration
GAME_STATE_URL = os.environ.get('GAME_STATE_URL', 'http://auto-madden-game-state:5132')
LETTA_BASE_URL = os.environ.get('LETTA_BASE_URL', 'http://letta:8283')
LETTA_MAIN_AGENT_ID = os.environ.get('LETTA_MAIN_AGENT_ID', 'agent-30ff1be2-3922-42fb-b7ee-458cb5a3bb07')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'anthropic')
LLM_MODEL = os.environ.get('LLM_MODEL', 'claude-sonnet-4-20250514')
MAX_INSIGHTS_PER_MINUTE = int(os.environ.get('MAX_INSIGHTS_PER_MINUTE', '4'))
MIN_INSIGHT_GAP_SECONDS = float(os.environ.get('MIN_INSIGHT_GAP_SECONDS', '8'))
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# ESPN API for team context
ESPN_API_BASE = 'http://site.api.espn.com/apis/site/v2/sports/football/nfl'


def fetch_team_context(team_id: str) -> Dict[str, Any]:
    """Fetch team stats and context from ESPN."""
    context = {'id': team_id}
    
    try:
        # Fetch team info with record
        team_url = f"{ESPN_API_BASE}/teams/{team_id}?enable=record"
        resp = requests.get(team_url, timeout=5)
        if resp.status_code == 200:
            data = resp.json().get('team', {})
            context['name'] = data.get('displayName', '')
            context['abbreviation'] = data.get('abbreviation', '')
            
            # Parse record
            record = data.get('record', {}).get('items', [])
            for item in record:
                if item.get('type') == 'total':
                    context['record'] = item.get('summary', '')
                    for stat in item.get('stats', []):
                        if stat.get('name') == 'avgPointsFor':
                            context['ppg'] = stat.get('value', 0)
                        if stat.get('name') == 'avgPointsAgainst':
                            context['ppg_allowed'] = stat.get('value', 0)
        
        # Fetch team statistics
        stats_url = f"{ESPN_API_BASE}/teams/{team_id}/statistics"
        resp = requests.get(stats_url, timeout=5)
        if resp.status_code == 200:
            data = resp.json().get('results', {}).get('stats', {})
            categories = data.get('categories', [])
            
            for cat in categories:
                cat_name = cat.get('name', '')
                for stat in cat.get('stats', []):
                    stat_name = stat.get('name', '')
                    value = stat.get('perGameValue', stat.get('value', 0))
                    
                    if cat_name == 'passing':
                        if stat_name == 'passingYardsPerGame':
                            context['pass_ypg'] = value
                        if stat_name == 'interceptions':
                            context['ints'] = stat.get('value', 0)
                    elif cat_name == 'rushing':
                        if stat_name == 'rushingYardsPerGame':
                            context['rush_ypg'] = value
                    elif cat_name == 'receiving':
                        if stat_name == 'receivingYardsPerGame':
                            context['recv_ypg'] = value
    
    except Exception as e:
        logger.warning(f"Error fetching team context for {team_id}: {e}")
    
    return context


def fetch_matchup_context(home_id: str, away_id: str) -> Dict[str, Any]:
    """Fetch context for both teams in a matchup."""
    home = fetch_team_context(home_id)
    away = fetch_team_context(away_id)
    
    return {
        'home': home,
        'away': away,
        'summary': generate_matchup_summary(home, away)
    }


def generate_matchup_summary(home: Dict, away: Dict) -> str:
    """Generate a text summary of the matchup."""
    parts = []
    
    home_name = home.get('abbreviation', 'HOME')
    away_name = away.get('abbreviation', 'AWAY')
    
    # Records
    home_record = home.get('record', '?-?')
    away_record = away.get('record', '?-?')
    parts.append(f"{away_name} ({away_record}) @ {home_name} ({home_record})")
    
    # Scoring comparison
    home_ppg = home.get('ppg', 0)
    away_ppg = away.get('ppg', 0)
    if home_ppg and away_ppg:
        if home_ppg > away_ppg + 5:
            parts.append(f"{home_name} averages {home_ppg:.1f} PPG vs {away_name}'s {away_ppg:.1f}")
        elif away_ppg > home_ppg + 5:
            parts.append(f"{away_name} averages {away_ppg:.1f} PPG vs {home_name}'s {home_ppg:.1f}")
    
    # Rushing comparison
    home_rush = home.get('rush_ypg', 0)
    away_rush = away.get('rush_ypg', 0)
    if home_rush > 130:
        parts.append(f"{home_name} runs the ball well ({home_rush:.0f} rush YPG)")
    if away_rush > 130:
        parts.append(f"{away_name} runs the ball well ({away_rush:.0f} rush YPG)")
    
    return ". ".join(parts) + "." if parts else ""


def ensure_game_insights(
    nfl_pro_uuid: str,
    home_team: str,
    away_team: str,
    week: int = None,
    espn_game_id: str = None
) -> int:
    """
    Check if insights exist for a game, fetch and process them if missing.

    This ensures that when any game is loaded, the system automatically
    fetches any missing insights from NFL Pro.

    Args:
        nfl_pro_uuid: NFL Pro game UUID
        home_team: Home team abbreviation (e.g., 'NE')
        away_team: Away team abbreviation (e.g., 'HOU')
        week: Week number (for processed insights lookup)
        espn_game_id: ESPN game ID (for mapping)

    Returns:
        Number of insights fetched (0 if already existed or fetch failed)
    """
    import sqlite3

    DATA_PATH = Path('/Volumes/main-drive/ai-PA/auto-madden/data')
    DB_PATH = DATA_PATH / 'nfl_insights_2025.db'
    PROCESSED_PATH = DATA_PATH / 'processed_insights'

    if not nfl_pro_uuid:
        logger.debug("No NFL Pro UUID provided, skipping insight fetch")
        return 0

    # Check if we already have insights for this game in database
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM insights WHERE game_id = ?",
            (nfl_pro_uuid,)
        )
        existing_count = cursor.fetchone()[0]
        conn.close()

        if existing_count > 0:
            logger.debug(f"Game {nfl_pro_uuid[:8]}... already has {existing_count} insights")
            return 0
    except Exception as e:
        logger.debug(f"Could not check existing insights: {e}")

    # Need to fetch insights from NFL Pro API
    logger.info(f"📥 Fetching missing insights for {away_team} @ {home_team} ({nfl_pro_uuid[:8]}...)")

    # NFL Pro team ID mapping (commonly used teams)
    TEAM_IDS = {
        'ARI': '0100', 'ATL': '0200', 'BAL': '0325', 'BUF': '0610',
        'CAR': '0750', 'CHI': '0810', 'CIN': '0920', 'CLE': '1050',
        'DAL': '1200', 'DEN': '1400', 'DET': '1540', 'GB': '1800',
        'HOU': '2120', 'IND': '2200', 'JAX': '2250', 'KC': '2310',
        'LAC': '4400', 'LAR': '2510', 'LV': '2520', 'MIA': '2700',
        'MIN': '3000', 'NE': '3200', 'NO': '3300', 'NYG': '3410',
        'NYJ': '3430', 'PHI': '3700', 'PIT': '3800', 'SEA': '4600',
        'SF': '4500', 'TB': '4900', 'TEN': '2100', 'WAS': '5110'
    }

    home_id = TEAM_IDS.get(home_team.upper(), '0000')
    away_id = TEAM_IDS.get(away_team.upper(), '0000')

    try:
        # Try using aiohttp/playwright to fetch insights
        import asyncio
        from playwright.async_api import async_playwright

        BROWSER_STATE = Path('/Volumes/main-drive/ai-PA/auto-madden/credentials/browser_states/nfl_pro_state.json')

        async def fetch_game_insights():
            if not BROWSER_STATE.exists():
                logger.warning("NFL Pro browser state not found, cannot fetch insights")
                return []

            all_insights = []
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(storage_state=str(BROWSER_STATE))
                page = await context.new_page()

                try:
                    # Load main page first
                    await page.goto("https://pro.nfl.com", wait_until='networkidle', timeout=30000)
                    await asyncio.sleep(2)

                    # Fetch pregame insights (usually has the most)
                    for tags in ['nfl-pro,pregame', 'nfl-pro,postgame', 'nfl-pro']:
                        api_url = f"https://pro.nfl.com/api/content/insights/game?season=2025&limit=100&tags={tags}&excludeTags=betting&fapiGameId={nfl_pro_uuid}&awayTeamId={away_id}&homeTeamId={home_id}"

                        response = await page.evaluate(f'''
                            async () => {{
                                try {{
                                    const resp = await fetch("{api_url}");
                                    if (!resp.ok) return [];
                                    const text = await resp.text();
                                    return text ? JSON.parse(text) : [];
                                }} catch(e) {{
                                    return [];
                                }}
                            }}
                        ''')

                        if isinstance(response, list) and len(response) > 0:
                            for i in response:
                                i['game_id'] = nfl_pro_uuid
                                # Avoid duplicates
                                if not any(x.get('id') == i.get('id') for x in all_insights):
                                    all_insights.append(i)

                except Exception as e:
                    logger.warning(f"Error fetching insights: {e}")
                finally:
                    await page.close()
                    await browser.close()

            return all_insights

        # Run async fetch
        insights = asyncio.run(fetch_game_insights())

        if not insights:
            logger.info(f"No insights found for {away_team} @ {home_team}")
            return 0

        logger.info(f"📥 Fetched {len(insights)} insights for {away_team} @ {home_team}")

        # Save to database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Determine week (default to 20 for playoffs if not specified)
        save_week = week or 20

        saved = 0
        for i in insights:
            try:
                insight_id = i.get('id', f"{nfl_pro_uuid}_{saved}")
                player = i.get('player', {}) or {}
                second_player = i.get('secondPlayer', {}) or {}

                cursor.execute('''
                    INSERT OR REPLACE INTO insights (
                        insight_id, game_id, season, week, title, sub_note, sub_note2,
                        player_name, position, team_abbr, jersey_number,
                        second_player_name, second_position, second_team_abbr, second_team_type,
                        image_url, headshot_url, scraped_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    insight_id,
                    nfl_pro_uuid,
                    2025,
                    save_week,
                    i.get('title', ''),
                    i.get('subNote', ''),
                    i.get('subNote2', ''),
                    player.get('displayName', ''),
                    player.get('position', ''),
                    player.get('teamAbbr', ''),
                    player.get('jerseyNumber'),
                    second_player.get('displayName', ''),
                    second_player.get('position', ''),
                    second_player.get('teamAbbr', ''),
                    second_player.get('teamType', ''),
                    i.get('imageUrl', ''),
                    player.get('headshotUrl', ''),
                    datetime.now().isoformat()
                ))
                saved += 1
            except Exception as e:
                logger.debug(f"Save error: {e}")

        conn.commit()
        conn.close()

        logger.info(f"💾 Saved {saved} insights to database")

        # Now process them into the processed_insights folder
        if saved > 0 and save_week:
            try:
                # Import and run the preprocessor
                import subprocess
                preprocessor_path = Path('/Volumes/main-drive/ai-PA/auto-madden/nfl-pro-scraper/services/insight_preprocessor.py')
                if preprocessor_path.exists():
                    result = subprocess.run(
                        ['python3', str(preprocessor_path), '--week', str(save_week), '--season', '2025'],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        logger.info(f"✅ Processed insights for Week {save_week}")
                    else:
                        logger.warning(f"Preprocessor warning: {result.stderr}")
            except Exception as e:
                logger.warning(f"Could not run preprocessor: {e}")

        return saved

    except ImportError:
        logger.warning("Playwright not available for insight fetching")
        return 0
    except Exception as e:
        logger.error(f"Error fetching game insights: {e}")
        return 0


# Set log level
logging.getLogger().setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

# Broadcast delay configuration
BROADCAST_DELAY_SECONDS = float(os.environ.get('BROADCAST_DELAY_SECONDS', '0'))


class BroadcastDelayBuffer:
    """
    Buffers insights to account for TV broadcast delay.
    
    Live ESPN data arrives before TV broadcast shows the play.
    This buffer delays our insights to sync with what the user sees on TV.
    """
    
    def __init__(self, delay_seconds: float = 0):
        self.delay_seconds = delay_seconds
        self.queue: List[tuple] = []  # (release_time, insight)
        self.sync_samples: List[float] = []  # delay calibration samples
        self._lock = threading.Lock()
    
    def set_delay(self, seconds: float):
        """Set the broadcast delay in seconds."""
        with self._lock:
            self.delay_seconds = max(0, seconds)
            logger.info(f"Broadcast delay set to {self.delay_seconds:.1f} seconds")
    
    def adjust_delay(self, delta: float):
        """Adjust delay by delta seconds."""
        with self._lock:
            self.delay_seconds = max(0, self.delay_seconds + delta)
            logger.info(f"Broadcast delay adjusted to {self.delay_seconds:.1f} seconds")
    
    def record_sync_point(self, event_type: str, event_time: float):
        """
        Record when user confirms they saw an event on TV.
        Helps calibrate the delay automatically.
        """
        button_time = time.time()
        measured_delay = button_time - event_time
        
        with self._lock:
            self.sync_samples.append(measured_delay)
            # Keep last 5 samples
            self.sync_samples = self.sync_samples[-5:]
            # Average them
            if self.sync_samples:
                self.delay_seconds = sum(self.sync_samples) / len(self.sync_samples)
                logger.info(f"Calibrated delay to {self.delay_seconds:.1f}s from {len(self.sync_samples)} samples")
    
    def add_insight(self, insight: 'Insight'):
        """Add an insight to the delay buffer."""
        with self._lock:
            release_time = time.time() + self.delay_seconds
            self.queue.append((release_time, insight))
            self.queue.sort(key=lambda x: x[0])  # Keep sorted by release time
    
    def get_ready_insights(self) -> List['Insight']:
        """Get insights whose delay has passed."""
        ready = []
        now = time.time()
        
        with self._lock:
            while self.queue and self.queue[0][0] <= now:
                _, insight = self.queue.pop(0)
                ready.append(insight)
        
        return ready
    
    def get_status(self) -> Dict[str, Any]:
        """Get current buffer status."""
        with self._lock:
            return {
                'delay_seconds': self.delay_seconds,
                'queued_insights': len(self.queue),
                'sync_samples': len(self.sync_samples)
            }


# Global delay buffer instance
delay_buffer = BroadcastDelayBuffer(BROADCAST_DELAY_SECONDS)


@dataclass
class Insight:
    """A generated insight ready for delivery."""
    id: str
    insight_type: str  # situation_explanation, play_explanation, etc.
    priority: int  # 1-10, higher = more important
    timing: str  # immediate, post_play, stoppage
    headline: str
    body: str
    ttl: int = 60  # Seconds until stale
    generated_at: datetime = field(default_factory=datetime.now)
    delivered: bool = False
    delivered_at: Optional[datetime] = None

    def is_expired(self) -> bool:
        """Check if insight has expired."""
        age = (datetime.now() - self.generated_at).total_seconds()
        return age > self.ttl

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'type': self.insight_type,
            'priority': self.priority,
            'timing': self.timing,
            'headline': self.headline,
            'body': self.body,
            'generated_at': self.generated_at.isoformat(),
            'delivered': self.delivered
        }

    def __lt__(self, other):
        """Comparison for priority queue."""
        return self.priority > other.priority


class InsightTemplates:
    """Load and apply insight templates."""

    def __init__(self, templates_path: str = None):
        """Initialize templates."""
        self.templates: Dict[str, Any] = {}
        
        # Try multiple paths for templates
        if templates_path is None:
            possible_paths = [
                os.path.join(os.path.dirname(__file__), '..', 'config', 'templates', 'insights.yaml'),
                '/Volumes/main-drive/ai-PA/auto-madden/config/templates/insights.yaml',
                '/app/config/templates/insights.yaml',
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    templates_path = path
                    break
            if templates_path is None:
                templates_path = possible_paths[0]  # Use default for error message
        
        self.load_templates(templates_path)

    def load_templates(self, path: str):
        """Load templates from YAML file."""
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    self.templates = yaml.safe_load(f) or {}
                logger.info(f"Loaded templates from {path}")
            else:
                logger.warning(f"Templates file not found: {path}, using defaults")
                self.templates = self._get_default_templates()
        except Exception as e:
            logger.error(f"Error loading templates: {e}")
            self.templates = self._get_default_templates()

    def _get_default_templates(self) -> Dict[str, Any]:
        """Get default insight templates."""
        return {
            'situation_templates': {
                'third_down': {
                    'short': {
                        'priority': 7,
                        'timing': 'pre_snap',
                        'ttl': 15,
                        'headline': '3rd and {distance}—short yardage',
                        'body': 'Only need {distance} yards. Run is likely, but watch for play-action.'
                    },
                    'medium': {
                        'priority': 6,
                        'timing': 'pre_snap',
                        'ttl': 15,
                        'headline': '3rd and {distance}—manageable',
                        'body': 'Need {distance} yards. Typically a passing down—watch for a quick route.'
                    },
                    'long': {
                        'priority': 6,
                        'timing': 'pre_snap',
                        'ttl': 15,
                        'headline': '3rd and {distance}—tough conversion',
                        'body': '{distance} yards is a lot. Teams convert only ~25% here. Watch for a blitz.'
                    }
                },
                'red_zone': {
                    'entry': {
                        'priority': 7,
                        'timing': 'post_play',
                        'ttl': 30,
                        'headline': 'Red zone—scoring territory',
                        'body': 'Inside the 20. Teams score TDs ~60% of the time here.'
                    }
                }
            },
            'play_templates': {
                'big_play': {
                    'priority': 8,
                    'timing': 'post_play',
                    'ttl': 20,
                    'headline': 'Big gain: {yards} yards!',
                    'body': '{description}'
                },
                'turnover': {
                    'priority': 9,
                    'timing': 'immediate',
                    'ttl': 30,
                    'headline': 'TURNOVER!',
                    'body': '{description}'
                },
                'touchdown': {
                    'priority': 9,
                    'timing': 'immediate',
                    'ttl': 45,
                    'headline': 'TOUCHDOWN!',
                    'body': '{description}'
                }
            },
            'pre_play_templates': {
                '1st_down': {
                    'priority': 4,
                    'timing': 'pre_snap',
                    'ttl': 12,
                    'headlines': [
                        'Fresh set of downs—offense has options',
                        '1st & 10: establishing the run?',
                        'New series. Watch the formation.',
                        'First down—what\'s the plan?',
                        '1st and 10 coming up',
                        'Clean slate for the offense',
                        'New set of downs',
                        'Back to 1st down'
                    ],
                    'bodies': [
                        'First down gives the offense room to be aggressive. Run sets up play-action later.',
                        'Teams run on 1st down ~45% of the time. A big gain here changes everything.',
                        'Look at personnel: extra tight ends = run, empty backfield = pass.',
                        'Four chances to get 10 yards. No pressure yet.',
                        'This is where game scripts get established.',
                        'Watch the defensive alignment for clues about the call.',
                        'Early down = less predictable play calling.',
                        'The offense can do almost anything here.'
                    ]
                },
                '2nd_short': {
                    'priority': 5,
                    'timing': 'pre_snap',
                    'ttl': 12,
                    'headlines': [
                        '2nd and short—still comfortable',
                        '2nd and {distance}—good spot',
                        'Just {distance} to go',
                        'Manageable 2nd down'
                    ],
                    'bodies': [
                        'Only {distance} yards needed. Good down to take a shot downfield.',
                        'Short yardage situation. Could run or throw here.',
                        'Offense in good shape—two more cracks at {distance} yards.',
                        'Low-risk territory. Might see something aggressive.'
                    ]
                },
                '2nd_long': {
                    'priority': 5,
                    'timing': 'pre_snap',
                    'ttl': 12,
                    'headlines': [
                        '2nd and long—need to get some of it back',
                        '2nd and {distance}—tough spot',
                        '{distance} to go, two downs left',
                        'Behind schedule on this drive'
                    ],
                    'bodies': [
                        '{distance} yards is tough. Expect a safe play to set up 3rd and medium.',
                        'Most teams try to get half of it here.',
                        'A sack or loss here puts them in 3rd and forever.',
                        'Screen pass or draw play are common calls here.'
                    ]
                },
                '4th_down': {
                    'priority': 8,
                    'timing': 'pre_snap',
                    'ttl': 15,
                    'headlines': [
                        '4th down decision time',
                        'Decision time: 4th down',
                        'Last chance for this drive',
                        '4th down—what will they do?'
                    ],
                    'bodies': [
                        'Go for it, punt, or kick? Field position and score dictate the call.',
                        'Analytics usually favor going for it more often than coaches do.',
                        'The gambler\'s down. Risk vs reward.',
                        'Punt is the conservative play. Will they be bold?'
                    ]
                }
            },
            'post_play_templates': {
                'run_gain': {
                    'priority': 4,
                    'timing': 'post_play',
                    'ttl': 10,
                    'headlines': [
                        'Run: {yards} yards',
                        '{yards}-yard gain on the ground',
                        'Ground game: +{yards}'
                    ],
                    'bodies': [
                        '{description}',
                        'Running keeps the defense honest and the clock moving.'
                    ]
                },
                'pass_complete': {
                    'priority': 4,
                    'timing': 'post_play',
                    'ttl': 10,
                    'headlines': [
                        'Complete: {yards} yards',
                        'Pass caught for {yards}',
                        '{yards}-yard reception'
                    ],
                    'bodies': ['{description}']
                },
                'incomplete': {
                    'priority': 3,
                    'timing': 'post_play',
                    'ttl': 8,
                    'headlines': ['Incomplete—clock stops'],
                    'bodies': ['Pass falls incomplete. Clock stops, preserving time.']
                },
                'sack': {
                    'priority': 6,
                    'timing': 'post_play',
                    'ttl': 12,
                    'headlines': ['SACK! {yards}-yard loss'],
                    'bodies': ['Pressure got home. {description}']
                },
                'penalty': {
                    'priority': 5,
                    'timing': 'post_play',
                    'ttl': 12,
                    'headlines': ['Flag on the play'],
                    'bodies': ['{description}']
                }
            }
        }

    def get_template(self, category: str, template_type: str, subtype: str = None) -> Optional[Dict]:
        """Get a specific template."""
        templates = self.templates.get(f'{category}_templates', {})
        if template_type not in templates:
            return None

        template = templates[template_type]
        if subtype and subtype in template:
            return template[subtype]
        elif not subtype and not isinstance(template, dict):
            return None
        elif not subtype:
            return template

        return None

    def apply_template(self, template: Dict, variables: Dict[str, Any]) -> Insight:
        """Apply variables to a template and create an Insight."""
        headline = template.get('headline', '')
        body = template.get('body', '')

        # Simple variable substitution
        for key, value in variables.items():
            headline = headline.replace('{' + key + '}', str(value))
            body = body.replace('{' + key + '}', str(value))

        return Insight(
            id=str(uuid.uuid4())[:8],
            insight_type=variables.get('type', 'general'),
            priority=template.get('priority', 5),
            timing=template.get('timing', 'post_play'),
            headline=headline,
            body=body,
            ttl=template.get('ttl', 30)
        )


class LLMClient:
    """Client for LLM-based insight generation."""

    def __init__(self, provider: str = 'anthropic', model: str = 'claude-sonnet-4-20250514'):
        """Initialize LLM client."""
        self.provider = provider
        self.model = model
        self.last_call_time = 0
        self.min_call_interval = 5.0  # Minimum seconds between LLM calls
        self.call_count = 0
        self.max_calls_per_minute = 6

    def can_call(self) -> bool:
        """Check if we can make an LLM call (rate limiting)."""
        now = time.time()

        # Check minimum interval
        if now - self.last_call_time < self.min_call_interval:
            return False

        # Reset call count every minute
        if now - self.last_call_time > 60:
            self.call_count = 0

        return self.call_count < self.max_calls_per_minute

    def generate_insight(self, context: Dict[str, Any], question: str = None) -> Optional[str]:
        """
        Generate an insight using LLM.

        Args:
            context: Game context including state and recent changes
            question: Optional user question to answer

        Returns:
            Generated insight text or None if rate limited/failed.
        """
        if not self.can_call():
            logger.debug("LLM call rate limited")
            return None

        try:
            if self.provider == 'anthropic':
                return self._call_anthropic(context, question)
            elif self.provider == 'openai':
                return self._call_openai(context, question)
            else:
                logger.error(f"Unknown LLM provider: {self.provider}")
                return None

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    def _call_anthropic(self, context: Dict[str, Any], question: str = None) -> Optional[str]:
        """Call Anthropic API."""
        if not ANTHROPIC_API_KEY:
            logger.warning("No Anthropic API key configured")
            return None

        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        prompt = self._build_prompt(context, question)

        self.last_call_time = time.time()
        self.call_count += 1

        message = client.messages.create(
            model=self.model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )

        return message.content[0].text

    def _call_openai(self, context: Dict[str, Any], question: str = None) -> Optional[str]:
        """Call OpenAI API."""
        if not OPENAI_API_KEY:
            logger.warning("No OpenAI API key configured")
            return None

        import openai

        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        prompt = self._build_prompt(context, question)

        self.last_call_time = time.time()
        self.call_count += 1

        response = client.chat.completions.create(
            model=self.model if 'gpt' in self.model else 'gpt-4o-mini',
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.choices[0].message.content

    def _build_prompt(self, context: Dict[str, Any], question: str = None) -> str:
        """Build prompt for LLM."""
        state = context.get('state', {})
        change = context.get('change', {})

        situation = f"{state.get('down', 1)} and {state.get('distance', 10)} at the {state.get('yard_line', 50)}"
        score = f"{state.get('home_team', {}).get('abbreviation', 'HOME')} {state.get('home_team', {}).get('score', 0)}, {state.get('away_team', {}).get('abbreviation', 'AWAY')} {state.get('away_team', {}).get('score', 0)}"
        clock = f"Q{state.get('quarter', 1)} - {state.get('clock', '15:00')}"

        if question:
            return f"""You are a knowledgeable football companion helping a viewer understand the game.
The viewer has intermediate knowledge—understands basic rules but wants to learn strategy.

Current situation:
- {situation}
- Clock: {clock}
- Score: {score}
- Possession: {state.get('possession_team', 'Unknown')}

User question: {question}

Give a brief, conversational answer (2-3 sentences max). Be helpful, not academic."""

        else:
            event = change.get('description', 'Unknown event')
            event_type = change.get('change_type', 'unknown')

            return f"""You are a knowledgeable football companion helping a viewer understand the game.
The viewer has intermediate knowledge—understands basic rules but wants to learn strategy.

Current situation:
- {situation}
- Clock: {clock}
- Score: {score}

Recent event: {event_type} - {event}

Generate ONE brief insight (2-3 sentences max) that helps the viewer understand:
1. What just happened and why it matters, OR
2. What to watch for on the next play

Be conversational, not academic. Use "watch for..." or "notice how..." phrasing.
Focus on the strategic "why" more than the "what."

Respond in JSON format:
{{"headline": "brief 5-8 word summary", "body": "2-3 sentence explanation"}}"""


class DeliveryManager:
    """Manage insight delivery with adaptive timing."""

    def __init__(self):
        """Initialize delivery manager."""
        self.insight_queue: queue.PriorityQueue = queue.PriorityQueue()
        self.recent_deliveries: List[float] = []
        self.last_delivery_time: float = 0
        self.delivered_ids: set = set()
        self.connected_clients: List = []

        # Game state for adaptive timing
        self.clock_running: bool = False
        self.is_stoppage: bool = True
        self.game_intensity: str = 'normal'  # low, normal, high

    def queue_insight(self, insight: Insight):
        """Add insight to priority queue."""
        if insight.id in self.delivered_ids:
            return

        # Priority queue uses negative priority for min-heap behavior
        self.insight_queue.put((-insight.priority, insight))
        logger.debug(f"Queued insight: {insight.headline} (priority {insight.priority})")

    def can_deliver_now(self) -> bool:
        """Check if we can deliver an insight now."""
        now = time.time()

        # Calculate adaptive gap
        base_gap = MIN_INSIGHT_GAP_SECONDS

        if self.clock_running and self.game_intensity == 'high':
            # During intense action, increase gap significantly
            gap = base_gap * 2.0
        elif self.is_stoppage:
            # During stoppages, can be more frequent
            gap = base_gap * 0.5
        else:
            gap = base_gap

        # Check minimum gap
        if now - self.last_delivery_time < gap:
            return False

        # Check rate limit (max per minute)
        recent = [t for t in self.recent_deliveries if now - t < 60]
        if len(recent) >= MAX_INSIGHTS_PER_MINUTE:
            return False

        return True

    def get_next_insight(self) -> Optional[Insight]:
        """Get next deliverable insight."""
        try:
            while not self.insight_queue.empty():
                _, insight = self.insight_queue.get_nowait()

                # Check if expired
                if insight.is_expired():
                    logger.debug(f"Insight expired: {insight.headline}")
                    continue

                # Check if already delivered
                if insight.id in self.delivered_ids:
                    continue

                # Check timing
                if insight.timing != 'immediate' and self.clock_running:
                    # Re-queue for later
                    self.insight_queue.put((-insight.priority, insight))
                    return None

                return insight

        except queue.Empty:
            pass

        return None

    def record_delivery(self, insight: Insight):
        """Record that an insight was delivered."""
        now = time.time()
        self.last_delivery_time = now
        self.recent_deliveries.append(now)
        self.delivered_ids.add(insight.id)
        insight.delivered = True
        insight.delivered_at = datetime.now()

        # Cleanup old records
        self.recent_deliveries = [t for t in self.recent_deliveries if now - t < 120]

        logger.info(f"Delivered insight: {insight.headline}")

    def update_game_state(self, state: Dict[str, Any]):
        """Update game state for timing decisions."""
        self.clock_running = state.get('clock_running', False)
        self.is_stoppage = not self.clock_running

        # Determine intensity
        quarter = state.get('quarter', 1)
        score_diff = abs(state.get('home_team', {}).get('score', 0) -
                        state.get('away_team', {}).get('score', 0))

        if quarter >= 4 and score_diff <= 7:
            self.game_intensity = 'high'
        elif score_diff >= 21:
            self.game_intensity = 'low'
        else:
            self.game_intensity = 'normal'

    def broadcast_insight(self, insight: Insight):
        """Broadcast insight to all connected clients."""
        message = json.dumps({
            'type': 'insight',
            'data': insight.to_dict()
        })

        for client in self.connected_clients[:]:
            try:
                client.send(message)
            except Exception as e:
                logger.error(f"Error sending to client: {e}")
                self.connected_clients.remove(client)
    
    def broadcast_preplay(self, preplay_data: dict):
        """Broadcast pre-play metadata to all connected clients (legacy format)."""
        message = json.dumps({
            'type': 'preplay',
            'data': preplay_data
        })
        
        logger.info(f"Broadcasting pre-play: {preplay_data.get('compact', '')}")
        
        for client in self.connected_clients[:]:
            try:
                client.send(message)
            except Exception as e:
                logger.error(f"Error sending preplay to client: {e}")
                self.connected_clients.remove(client)
    
    def broadcast_presnap(self, presnap_data: dict):
        """Broadcast pre-snap analysis to all connected clients."""
        message = json.dumps({
            'type': 'presnap',
            'data': presnap_data
        })
        
        off = presnap_data.get('offense', {})
        logger.info(f"Broadcasting pre-snap: {off.get('personnel', '')} {off.get('formation', '')}")
        
        for client in self.connected_clients[:]:
            try:
                client.send(message)
            except Exception as e:
                logger.error(f"Error sending presnap to client: {e}")
                self.connected_clients.remove(client)
    
    def broadcast_postsnap(self, postsnap_data: dict):
        """Broadcast post-snap analysis to all connected clients."""
        message = json.dumps({
            'type': 'postsnap',
            'data': postsnap_data
        })
        
        defense = postsnap_data.get('defense', {})
        cov = defense.get('coverage', '?')
        rushers = defense.get('rushers', 0)
        box = defense.get('box', 0)
        logger.info(f"Broadcasting post-snap: yards={postsnap_data.get('yards', '?')}, coverage={cov}, rushers={rushers}, box={box}")
        
        for client in self.connected_clients[:]:
            try:
                client.send(message)
            except Exception as e:
                logger.error(f"Error sending postsnap to client: {e}")
                self.connected_clients.remove(client)


class InsightGenerator:
    """Generate insights from game events."""

    def __init__(self, templates: InsightTemplates, llm_client: LLMClient):
        """Initialize generator."""
        self.templates = templates
        self.llm = llm_client
        # Track recently used headlines to avoid repetition
        self.recent_headlines: List[str] = []
        self.max_recent = 10  # Don't repeat last 10 headlines
        # Team context loaded at game start
        self.team_context: Optional[Dict[str, Any]] = None
        # Game flow tracking
        self.play_history: List[Dict[str, Any]] = []
        self.drive_stats = {'runs': 0, 'passes': 0, 'total_yards': 0}
        
        # === NEW: Player Spotlights ===
        self.player_stats: Dict[str, Dict[str, Any]] = {}  # player_name -> stats
        self.player_spotlight_threshold = 3  # Mentions before spotlight
        
        # === NEW: Momentum Tracking ===
        self.score_history: List[Dict[str, Any]] = []  # Track score changes
        self.momentum_state = 'neutral'  # 'home', 'away', 'neutral'
        self.momentum_plays: List[str] = []  # Key momentum moments
        
        # === NEW: Narrative Threading ===
        self.game_narrative: List[Dict[str, Any]] = []  # Key story beats
        self.narrative_themes: List[str] = []  # Emerging themes
        
        # === NEW: LLM Context from game context loader ===
        self.llm_game_context: str = ""  # Rich context prompt for LLM
    
    def reset_for_new_game(self):
        """Reset state for a new game."""
        self.recent_headlines = []
        self.team_context = None
        self.play_history = []
        self.drive_stats = {'runs': 0, 'passes': 0, 'total_yards': 0}
        # Reset new tracking
        self.player_stats = {}
        self.score_history = []
        self.momentum_state = 'neutral'
        self.momentum_plays = []
        self.game_narrative = []
        self.narrative_themes = []
    
    def track_play(self, play_description: str, yards: int):
        """Track a play for pattern detection."""
        is_run = any(word in play_description.lower() for word in ['rush', 'run', 'up the middle', 'left guard', 'right guard', 'left tackle', 'right tackle'])
        is_pass = 'pass' in play_description.lower()
        
        self.play_history.append({
            'description': play_description,
            'yards': yards,
            'is_run': is_run,
            'is_pass': is_pass,
            'timestamp': time.time()
        })
        
        # Keep last 30 plays
        if len(self.play_history) > 30:
            self.play_history.pop(0)
        
        # Update drive stats
        if is_run:
            self.drive_stats['runs'] += 1
        if is_pass:
            self.drive_stats['passes'] += 1
        self.drive_stats['total_yards'] += yards
    
    def get_game_flow_patterns(self, state: Dict[str, Any]) -> List[str]:
        """Detect patterns in game flow."""
        patterns = []
        
        if len(self.play_history) < 5:
            return patterns
        
        # Check recent plays (last 10)
        recent = self.play_history[-10:]
        runs = sum(1 for p in recent if p['is_run'])
        passes = sum(1 for p in recent if p['is_pass'])
        
        # Run-heavy pattern
        if runs > 6:
            patterns.append('run_heavy')
        # Pass-heavy pattern  
        if passes > 7:
            patterns.append('pass_heavy')
        
        # Momentum check - positive yards in last 5 plays
        last_5_yards = [p['yards'] for p in self.play_history[-5:]]
        if all(y > 0 for y in last_5_yards):
            patterns.append('hot_streak')
        if all(y <= 2 for y in last_5_yards):
            patterns.append('stalled')
        
        # Big play potential - several medium gains
        if sum(1 for y in last_5_yards if y >= 5) >= 3:
            patterns.append('moving_well')
        
        return patterns
    
    # === PLAYER SPOTLIGHT METHODS ===
    
    def track_player(self, play_description: str, yards: int):
        """Extract and track player stats from play description."""
        import re
        
        # Common patterns: "B.Young pass to D.Moore for 15 yards"
        # "J.Mixon rush for 8 yards"
        
        # Extract passer
        passer_match = re.search(r'([A-Z]\.[A-Za-z]+)\s+pass', play_description)
        if passer_match:
            name = passer_match.group(1)
            self._update_player_stat(name, 'pass_attempts', 1)
            if 'complete' in play_description.lower():
                self._update_player_stat(name, 'completions', 1)
                self._update_player_stat(name, 'pass_yards', yards)
            if 'touchdown' in play_description.lower():
                self._update_player_stat(name, 'pass_td', 1)
            if 'intercept' in play_description.lower():
                self._update_player_stat(name, 'interceptions', 1)
        
        # Extract receiver
        recv_match = re.search(r'to\s+([A-Z]\.[A-Za-z]+)', play_description)
        if recv_match and 'complete' in play_description.lower():
            name = recv_match.group(1)
            self._update_player_stat(name, 'receptions', 1)
            self._update_player_stat(name, 'recv_yards', yards)
            if 'touchdown' in play_description.lower():
                self._update_player_stat(name, 'recv_td', 1)
        
        # Extract rusher
        rush_match = re.search(r'([A-Z]\.[A-Za-z]+)\s+(?:rush|run|up the middle|left|right)', play_description)
        if rush_match:
            name = rush_match.group(1)
            self._update_player_stat(name, 'rush_attempts', 1)
            self._update_player_stat(name, 'rush_yards', yards)
            if 'touchdown' in play_description.lower():
                self._update_player_stat(name, 'rush_td', 1)
    
    def _update_player_stat(self, name: str, stat: str, value: int):
        """Update a player's stat."""
        if name not in self.player_stats:
            self.player_stats[name] = {'name': name, 'mentions': 0}
        self.player_stats[name]['mentions'] += 1
        self.player_stats[name][stat] = self.player_stats[name].get(stat, 0) + value
    
    def get_player_spotlight(self) -> Optional[Dict[str, Any]]:
        """Check if any player deserves a spotlight insight."""
        for name, stats in self.player_stats.items():
            # Check for spotlight-worthy performances
            recv_yards = stats.get('recv_yards', 0)
            rush_yards = stats.get('rush_yards', 0)
            pass_yards = stats.get('pass_yards', 0)
            total_td = stats.get('recv_td', 0) + stats.get('rush_td', 0) + stats.get('pass_td', 0)
            
            # Spotlight thresholds (checked every 5 plays)
            if recv_yards >= 75 and not stats.get('recv_spotlight'):
                stats['recv_spotlight'] = True
                return {'type': 'receiver', 'player': name, 'yards': recv_yards, 'receptions': stats.get('receptions', 0)}
            
            if rush_yards >= 60 and not stats.get('rush_spotlight'):
                stats['rush_spotlight'] = True
                return {'type': 'rusher', 'player': name, 'yards': rush_yards, 'carries': stats.get('rush_attempts', 0)}
            
            if pass_yards >= 150 and not stats.get('pass_spotlight'):
                stats['pass_spotlight'] = True
                return {'type': 'passer', 'player': name, 'yards': pass_yards, 
                        'completions': stats.get('completions', 0), 'attempts': stats.get('pass_attempts', 0)}
            
            if total_td >= 2 and not stats.get('td_spotlight'):
                stats['td_spotlight'] = True
                return {'type': 'multi_td', 'player': name, 'touchdowns': total_td}
        
        return None
    
    # === MOMENTUM TRACKING METHODS ===
    
    def track_score_change(self, state: Dict[str, Any], description: str):
        """Track score changes for momentum analysis."""
        home_score = state.get('home_team', {}).get('score', 0)
        away_score = state.get('away_team', {}).get('score', 0)
        quarter = state.get('quarter', 1)
        clock = state.get('clock', '')
        
        # Determine who scored
        if self.score_history:
            last = self.score_history[-1]
            home_scored = home_score > last.get('home', 0)
            away_scored = away_score > last.get('away', 0)
            points = (home_score - last.get('home', 0)) if home_scored else (away_score - last.get('away', 0))
        else:
            home_scored = home_score > 0
            away_scored = away_score > 0
            points = home_score if home_scored else away_score
        
        self.score_history.append({
            'home': home_score,
            'away': away_score,
            'quarter': quarter,
            'clock': clock,
            'description': description,
            'home_scored': home_scored,
            'away_scored': away_scored,
            'points': points
        })
        
        # Add to momentum plays
        self.momentum_plays.append(description[:80])
        
        # Update momentum state
        differential = home_score - away_score
        if differential >= 10:
            self.momentum_state = 'home_control'
        elif differential <= -10:
            self.momentum_state = 'away_control'
        elif len(self.score_history) >= 2:
            # Check recent scoring trend
            recent_home = sum(1 for s in self.score_history[-3:] if s.get('home_scored'))
            recent_away = sum(1 for s in self.score_history[-3:] if s.get('away_scored'))
            if recent_home >= 2:
                self.momentum_state = 'home_momentum'
            elif recent_away >= 2:
                self.momentum_state = 'away_momentum'
            else:
                self.momentum_state = 'neutral'
    
    def get_momentum_insight(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate momentum-based insight if appropriate."""
        if len(self.score_history) < 2:
            return None
        
        home_team = state.get('home_team', {}).get('abbreviation', 'HOME')
        away_team = state.get('away_team', {}).get('abbreviation', 'AWAY')
        
        templates = {
            'home_control': {
                'headline': f'{home_team} in control',
                'body': f'{home_team} has built a commanding lead. {away_team} needs to make something happen.'
            },
            'away_control': {
                'headline': f'{away_team} dominating',
                'body': f'{away_team} has taken over this game. {home_team} looking for answers.'
            },
            'home_momentum': {
                'headline': f'Momentum swinging to {home_team}',
                'body': f'{home_team} has scored on consecutive possessions. The crowd is into it.'
            },
            'away_momentum': {
                'headline': f'{away_team} building momentum',
                'body': f'{away_team} is heating up. Back-to-back scores putting pressure on {home_team}.'
            }
        }
        
        if self.momentum_state in templates:
            return templates[self.momentum_state]
        return None
    
    # === NARRATIVE THREADING METHODS ===
    
    def add_narrative_beat(self, beat_type: str, description: str, significance: int = 5):
        """Add a key moment to the game narrative."""
        self.game_narrative.append({
            'type': beat_type,
            'description': description,
            'significance': significance,
            'timestamp': time.time()
        })
        
        # Detect emerging themes
        self._update_narrative_themes()
    
    def _update_narrative_themes(self):
        """Analyze narrative beats to identify themes."""
        if len(self.game_narrative) < 3:
            return
        
        # Count beat types
        beat_types = [b['type'] for b in self.game_narrative]
        
        # Check for themes
        if beat_types.count('turnover') >= 2 and 'turnover_battle' not in self.narrative_themes:
            self.narrative_themes.append('turnover_battle')
        
        if beat_types.count('big_play') >= 3 and 'explosive_plays' not in self.narrative_themes:
            self.narrative_themes.append('explosive_plays')
        
        if beat_types.count('defensive_stop') >= 3 and 'defensive_struggle' not in self.narrative_themes:
            self.narrative_themes.append('defensive_struggle')
        
        if beat_types.count('score_change') >= 5 and 'shootout' not in self.narrative_themes:
            self.narrative_themes.append('shootout')
    
    def get_narrative_insight(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate a narrative-threading insight."""
        if not self.narrative_themes:
            return None
        
        home_team = state.get('home_team', {}).get('abbreviation', 'HOME')
        away_team = state.get('away_team', {}).get('abbreviation', 'AWAY')
        
        # Generate insight for newest theme (that hasn't been announced)
        theme = self.narrative_themes[-1]
        
        theme_insights = {
            'turnover_battle': {
                'headline': 'Turnovers defining this game',
                'body': f"Ball security has been the story. {len([b for b in self.game_narrative if b['type'] == 'turnover'])} turnovers so far."
            },
            'explosive_plays': {
                'headline': 'Big plays everywhere',
                'body': 'Both teams hitting home runs. This game is wide open.'
            },
            'defensive_struggle': {
                'headline': 'Defenses controlling the game',
                'body': 'Hard to move the ball consistently. Field position battle.'
            },
            'shootout': {
                'headline': 'Shootout in progress',
                'body': f"{home_team} and {away_team} trading blows. Defense optional today."
            }
        }
        
        return theme_insights.get(theme)
    
    def get_game_story_summary(self) -> str:
        """Get a summary of the game story so far."""
        if not self.game_narrative:
            return "Game just getting started."
        
        key_moments = [b['description'] for b in self.game_narrative if b['significance'] >= 7]
        themes = ', '.join(self.narrative_themes) if self.narrative_themes else 'competitive game'
        
        summary = f"Story so far: {themes}. "
        if key_moments:
            summary += f"Key moments: {'; '.join(key_moments[-3:])}"
        
        return summary
    
    def select_varied_headline(self, headlines: List[str], bodies: List[str], variables: Dict[str, Any]) -> tuple:
        """Select headline/body avoiding recent ones."""
        import random
        
        # Filter out recently used headlines
        available = [h for h in headlines if h not in self.recent_headlines]
        if not available:
            available = headlines  # Fall back if all used
        
        headline = random.choice(available)
        body = random.choice(bodies) if bodies else ''
        
        # Apply variable substitution
        for key, value in variables.items():
            headline = headline.replace('{' + key + '}', str(value))
            body = body.replace('{' + key + '}', str(value))
        
        # Track this headline
        self.recent_headlines.append(headline)
        if len(self.recent_headlines) > self.max_recent:
            self.recent_headlines.pop(0)
        
        return headline, body

    def generate_insights(self, change: Dict[str, Any], state: Dict[str, Any]) -> List[Insight]:
        """
        Generate insights for a game change.

        Args:
            change: The detected change
            state: Current game state

        Returns:
            List of generated insights.
        """
        insights: List[Insight] = []
        change_type = change.get('change_type', '')

        # Template-based insights (fast path)
        template_insights = self._generate_template_insights(change, state)
        insights.extend(template_insights)

        # LLM-based insights for significant events
        if self._should_use_llm(change):
            llm_insight = self._generate_llm_insight(change, state)
            if llm_insight:
                insights.append(llm_insight)

        return insights

    def _generate_template_insights(self, change: Dict[str, Any], state: Dict[str, Any]) -> List[Insight]:
        """Generate template-based insights."""
        insights = []
        change_type = change.get('change_type', '')

        # Score change
        if change_type == 'score_change':
            data = change.get('data', {})
            template = self.templates.get_template('play', 'touchdown')
            if template:
                insight = self.templates.apply_template(template, {
                    'type': 'score_change',
                    'description': change.get('description', '')
                })
                insights.append(insight)

        # Turnover
        elif change_type == 'turnover':
            template = self.templates.get_template('play', 'turnover')
            if template:
                insight = self.templates.apply_template(template, {
                    'type': 'turnover',
                    'description': change.get('description', '')
                })
                insights.append(insight)

        # Big play
        elif change_type == 'big_play':
            data = change.get('data', {})
            template = self.templates.get_template('play', 'big_play')
            if template:
                insight = self.templates.apply_template(template, {
                    'type': 'big_play',
                    'yards': data.get('yards', 0),
                    'description': change.get('description', '')
                })
                insights.append(insight)

        # Red zone entry
        elif change_type == 'red_zone_entry':
            template = self.templates.get_template('situation', 'red_zone', 'entry')
            if template:
                insight = self.templates.apply_template(template, {
                    'type': 'red_zone_entry'
                })
                insights.append(insight)

        # Two-minute warning
        elif change_type == 'two_minute_warning':
            quarter = change.get('data', {}).get('quarter', 2)
            half = 'first' if quarter == 2 else 'second'
            insights.append(Insight(
                id=str(uuid.uuid4())[:8],
                insight_type='two_minute_warning',
                priority=7,
                timing='stoppage',
                headline=f'Two-minute warning—{half} half',
                body='Automatic timeout. Every play matters now.',
                ttl=60
            ))

        # Third down situation (check state)
        down = state.get('down', 0)
        distance = state.get('distance', 0)

        if down == 3 and change_type in ['new_play', 'possession_change']:
            if distance <= 3:
                subtype = 'short'
            elif distance <= 6:
                subtype = 'medium'
            else:
                subtype = 'long'

            template = self.templates.get_template('situation', 'third_down', subtype)
            if template:
                insight = self.templates.apply_template(template, {
                    'type': 'situation_explanation',
                    'distance': distance
                })
                insights.append(insight)

        # Generate post-play analysis for every new_play or play_complete event
        if change_type in ['new_play', 'play_complete']:
            description = change.get('description', '')
            data = change.get('data', {})
            
            # === NFL PRO INSIGHTS - PRIORITIZE OVER GENERIC TEMPLATES ===
            # Trigger on: big plays, situational moments, or every ~4 plays
            nfl_insight_delivered = False
            
            if NFL_PRO_NARRATIVES_AVAILABLE and get_player_triggered_insight:
                yards = data.get('yards', 0)
                is_scoring = data.get('is_scoring', False) or 'touchdown' in description.lower()
                is_turnover = data.get('is_turnover', False) or any(x in description.lower() for x in ['intercept', 'fumble', 'turnover'])
                is_big_play = yards >= 15 or is_scoring or is_turnover
                
                # Situational triggers - these deserve context
                down = state.get('down', 1)
                is_red_zone = state.get('is_red_zone', False)
                is_third_down = down == 3
                is_fourth_down = down == 4
                is_key_moment = is_red_zone or is_third_down or is_fourth_down
                
                # Play counter for periodic insights
                play_count = len(self.play_history)
                periodic_trigger = (play_count % 4 == 0)  # Every 4th play
                
                should_trigger_nfl = is_big_play or is_key_moment or periodic_trigger
                
                if should_trigger_nfl:
                    # Extract player name from description
                    import re
                    player_match = re.search(r'([A-Z]\.[A-Za-z\-\']+)', description)
                    player_name = player_match.group(1) if player_match else None
                    quarter = state.get('quarter', 1)
                    
                    # Determine situation for context
                    situation = None
                    if is_red_zone:
                        situation = 'red zone'
                    elif is_fourth_down:
                        situation = '4th down'
                    elif is_third_down:
                        situation = '3rd down'
                    elif is_scoring:
                        situation = 'scoring'
                    
                    # Get both teams for strict filtering
                    home_team = state.get('home_team', {}).get('abbreviation', '')
                    away_team = state.get('away_team', {}).get('abbreviation', '')
                    game_teams = [t for t in [home_team, away_team] if t]
                    
                    # Try player-specific insight first (STRICT team filtering)
                    nfl_insight = None
                    if player_name:
                        nfl_insight = get_player_triggered_insight(
                            player_name, quarter, situation, 
                            game_teams=game_teams
                        )
                    
                    # Fall back to team/situation insight if no player insight (STRICT team filtering)
                    if not nfl_insight and get_contextual_narrative_insight:
                        possession = state.get('possession', home_team)
                        nfl_insight = get_contextual_narrative_insight(
                            team=possession,
                            is_redzone=is_red_zone,
                            is_third_down=is_third_down,
                            player=player_name,
                            game_teams=game_teams
                        )
                    
                    if nfl_insight:
                        insights.append(Insight(
                            id=nfl_insight.get('id', str(uuid.uuid4())[:8]),
                            insight_type='nfl_pro_narrative',
                            priority=nfl_insight.get('priority', 7),
                            timing='post_play',
                            headline=f"📊 {nfl_insight.get('headline', '')}",
                            body=nfl_insight.get('body', ''),
                            ttl=45
                        ))
                        nfl_insight_delivered = True
                        logger.info(f"📊 NFL Pro insight: {nfl_insight.get('headline', '')[:40]}...")
            
            # Only use generic template if no NFL Pro insight was delivered
            if not nfl_insight_delivered:
                post_insight = self._generate_post_play_insight(change, state)
                if post_insight:
                    insights.append(post_insight)
            
            # Generate pre-play preview for the NEXT play situation
            pre_insight = self._generate_pre_play_insight(state)
            if pre_insight:
                insights.append(pre_insight)
        
        # Break/stoppage insights - leverage downtime for deeper analysis
        elif change_type == 'break_start':
            break_insights = self._generate_break_insights(change, state)
            insights.extend(break_insights)

        return insights
    
    def _generate_break_insights(self, change: Dict[str, Any], state: Dict[str, Any]) -> List[Insight]:
        """
        Generate insights during game breaks (timeouts, halftime, commercials).
        
        This is the ideal time for deeper analysis since the viewer has downtime.
        Leverages loaded game context for richer insights.
        """
        insights = []
        break_info = change.get('data', {}).get('break_info', {})
        break_type = break_info.get('break_type', '')
        analysis_opportunity = break_info.get('analysis_opportunity', 'brief')
        break_duration = break_info.get('duration', 60)
        
        logger.info(f"🎬 Break insight generation: {break_type} ({analysis_opportunity}, ~{break_duration}s)")
        
        # Get break-appropriate content from context loader
        break_content = None
        if get_break_content:
            try:
                break_content = get_break_content(break_type, break_duration)
                if break_content.get('articles'):
                    logger.info(f"📰 Loaded {len(break_content['articles'])} articles for break")
            except Exception as e:
                logger.debug(f"Could not load break content: {e}")
        
        # Get NFL Pro narrative insights for breaks
        nfl_pro_insights = []
        if NFL_PRO_NARRATIVES_AVAILABLE and get_break_narrative_insights:
            quarter = state.get('quarter', 1)
            # Get more insights for longer breaks
            count = 4 if break_type == 'halftime' else (2 if break_duration > 90 else 1)
            
            # Get BOTH teams from current game to STRICTLY filter insights
            home_team_abbr = state.get('home_team', {}).get('abbreviation', '')
            away_team_abbr = state.get('away_team', {}).get('abbreviation', '')
            game_teams = [t for t in [home_team_abbr, away_team_abbr] if t]
            
            try:
                nfl_pro_insights = get_break_narrative_insights(
                    break_type, quarter, count, 
                    prefer_team=home_team_abbr,
                    game_teams=game_teams
                )
                if nfl_pro_insights:
                    logger.info(f"📊 Loaded {len(nfl_pro_insights)} NFL Pro narrative insights for {game_teams}")
            except Exception as e:
                logger.debug(f"Could not load NFL Pro insights: {e}")
        
        # Get current scores and game situation
        home_team = state.get('home_team', {})
        away_team = state.get('away_team', {})
        home_abbr = home_team.get('abbreviation', 'HOME') if isinstance(home_team, dict) else str(home_team)
        away_abbr = away_team.get('abbreviation', 'AWAY') if isinstance(away_team, dict) else str(away_team)
        home_score = home_team.get('score', 0) if isinstance(home_team, dict) else state.get('home_score', 0)
        away_score = away_team.get('score', 0) if isinstance(away_team, dict) else state.get('away_score', 0)
        quarter = state.get('quarter', 1)
        clock = state.get('clock', '15:00')
        
        # Build context string
        score_diff = abs(home_score - away_score)
        if home_score > away_score:
            leader = home_abbr
            trailer = away_abbr
        elif away_score > home_score:
            leader = away_abbr
            trailer = home_abbr
        else:
            leader = None
            trailer = None
        
        # === HALFTIME SPECIAL - Multiple extended insights ===
        if break_type == 'halftime':
            # INSIGHT 1: Main Halftime Report (immediate)
            insights.append(Insight(
                id=str(uuid.uuid4())[:8],
                insight_type='halftime_report',
                priority=10,
                timing='immediate',
                headline='⏸️ Halftime Report',
                body=self._generate_halftime_summary(state),
                ttl=600  # Long TTL for halftime
            ))
            
            # INSIGHT 2: First Half Analysis (after ~30 seconds)
            first_half_analysis = self._generate_first_half_analysis(state, home_abbr, away_abbr, home_score, away_score)
            insights.append(Insight(
                id=str(uuid.uuid4())[:8],
                insight_type='halftime_analysis',
                priority=9,
                timing='stoppage',
                headline='📊 First Half Breakdown',
                body=first_half_analysis,
                ttl=600
            ))
            
            # INSIGHT 3: Second Half Preview (after ~60 seconds)
            second_half_preview = self._generate_second_half_preview(state, leader, trailer, score_diff, home_abbr, away_abbr)
            insights.append(Insight(
                id=str(uuid.uuid4())[:8],
                insight_type='halftime_preview',
                priority=8,
                timing='stoppage',
                headline='🔮 Second Half Preview',
                body=second_half_preview,
                ttl=600
            ))
            
            # INSIGHT 4: Article share or key storylines (after ~90 seconds)
            if break_content and break_content.get('articles'):
                article = break_content['articles'][0]
                if article.get('headline'):
                    insights.append(Insight(
                        id=str(uuid.uuid4())[:8],
                        insight_type='article_share',
                        priority=7,
                        timing='stoppage',
                        headline=f"📰 Related Reading",
                        body=f"**{article['headline']}**\n\n{article.get('description', '')[:200]}\n\n🔗 {article.get('url', '')}",
                        ttl=600
                    ))
            elif break_content and break_content.get('analysis_points'):
                storylines = break_content['analysis_points']
                insights.append(Insight(
                    id=str(uuid.uuid4())[:8],
                    insight_type='halftime_storylines',
                    priority=7,
                    timing='stoppage',
                    headline='🎯 Key Storylines at the Half',
                    body='\n'.join(f"• {s}" for s in storylines[:4]),
                    ttl=600
                ))
            
            # Legacy: Add player spotlights if we have data
            spotlight = self._generate_halftime_spotlights(state)
            if spotlight:
                insights.append(spotlight)
            
            # Skip the old momentum and storyline code since we handle above
            # Skip to end of halftime section
            logger.info(f"🏈 Generated {len(insights)} halftime insights")
        
        # === TV TIMEOUT (extended analysis - great time for in-depth commentary) ===
        elif break_type == 'official_timeout' and analysis_opportunity == 'extended':
            # Generate rich, multi-paragraph analysis during commercial breaks
            extended_analysis = self._generate_commercial_break_analysis(
                state, leader, trailer, score_diff, quarter, clock, break_content
            )
            
            insights.append(Insight(
                id=str(uuid.uuid4())[:8],
                insight_type='break_deep_analysis',
                priority=8,
                timing='immediate',
                headline='📺 Commercial Break Deep Dive',
                body=extended_analysis,
                ttl=180  # Longer TTL for extended content
            ))
            
            # Share a relevant article if available
            if break_content and break_content.get('articles'):
                for article in break_content['articles'][:1]:
                    if article.get('headline'):
                        insights.append(Insight(
                            id=str(uuid.uuid4())[:8],
                            insight_type='article_share',
                            priority=5,
                            timing='stoppage',
                            headline=f"📰 {article['headline'][:50]}...",
                            body=f"{article.get('description', '')[:200]}\n\n🔗 {article.get('url', '')}",
                            ttl=180
                        ))
        
        # === TEAM TIMEOUT ===
        elif break_type == 'team_timeout':
            team = break_info.get('team', 'Team')
            # Brief strategic insight about why timeout might have been called
            insights.append(Insight(
                id=str(uuid.uuid4())[:8],
                insight_type='timeout_analysis',
                priority=6,
                timing='immediate',
                headline=f'⏱️ {team} Timeout',
                body=self._analyze_timeout_reason(state, team, quarter, clock),
                ttl=60
            ))
        
        # === POST-SCORE BREAK ===
        elif break_type == 'post_score':
            points = break_info.get('points_scored', 0)
            insights.append(Insight(
                id=str(uuid.uuid4())[:8],
                insight_type='post_score_analysis',
                priority=8,
                timing='immediate',
                headline='📊 Score Update Analysis',
                body=self._generate_post_score_context(state, points, leader, trailer, score_diff),
                ttl=120
            ))
        
        # === TWO-MINUTE WARNING ===
        elif break_type == 'two_minute_warning':
            half = 'first' if quarter == 2 else 'second'
            insights.append(Insight(
                id=str(uuid.uuid4())[:8],
                insight_type='two_minute_analysis',
                priority=9,
                timing='immediate',
                headline=f'⚠️ Two-Minute Warning',
                body=self._generate_two_minute_context(state, half, leader, trailer, score_diff),
                ttl=120
            ))
        
        # === QUARTER BREAK ===
        elif break_type == 'quarter_break':
            new_q = break_info.get('new_quarter', quarter)
            insights.append(Insight(
                id=str(uuid.uuid4())[:8],
                insight_type='quarter_summary',
                priority=8,
                timing='immediate',
                headline=f'📋 End of Quarter {new_q - 1}',
                body=self._generate_quarter_summary(state, new_q - 1),
                ttl=180
            ))
        
        # === CHALLENGE/REVIEW ===
        elif break_type == 'challenge':
            insights.append(Insight(
                id=str(uuid.uuid4())[:8],
                insight_type='review_analysis',
                priority=7,
                timing='immediate',
                headline='🔍 Official Review',
                body="The officials are reviewing the previous play. This could be a pivotal moment - reviews often happen on close calls that could swing momentum.",
                ttl=180
            ))
        
        # === Add NFL Pro Narrative Insights ===
        # These provide rich, pre-analyzed content from NFL Pro's content API
        if nfl_pro_insights:
            for nfl_insight in nfl_pro_insights:
                body = nfl_insight.get('body', '')
                if nfl_insight.get('extended') and break_type == 'halftime':
                    # For halftime, include extended analysis
                    body = f"{body}\n\n{nfl_insight['extended']}"
                
                insights.append(Insight(
                    id=nfl_insight.get('id', str(uuid.uuid4())[:8]),
                    insight_type='nfl_pro_narrative',
                    priority=nfl_insight.get('priority', 7),
                    timing='stoppage',
                    headline=f"📊 {nfl_insight.get('headline', 'Matchup Insight')[:50]}",
                    body=body,
                    ttl=300 if break_type == 'halftime' else 120
                ))
            logger.info(f"📈 Added {len(nfl_pro_insights)} NFL Pro narrative insights")
        
        return insights
    
    def _generate_halftime_summary(self, state: Dict[str, Any]) -> str:
        """
        Generate comprehensive halftime summary.
        
        Halftime is the longest break - provide the most extensive analysis here.
        """
        home = state.get('home_team', {})
        away = state.get('away_team', {})
        home_abbr = home.get('abbreviation', 'HOME') if isinstance(home, dict) else 'HOME'
        away_abbr = away.get('abbreviation', 'AWAY') if isinstance(away, dict) else 'AWAY'
        home_score = home.get('score', 0) if isinstance(home, dict) else state.get('home_score', 0)
        away_score = away.get('score', 0) if isinstance(away, dict) else state.get('away_score', 0)
        
        diff = abs(home_score - away_score)
        paragraphs = []
        
        # Paragraph 1: Score and Game State
        if home_score > away_score:
            if diff >= 17:
                para1 = f"HALFTIME: {home_abbr} {home_score}, {away_abbr} {away_score}\n\n"
                para1 += f"A dominant first half for the home team. {home_abbr} has built a commanding {diff}-point lead "
                para1 += f"and is in complete control of this game. {away_abbr} will need a completely different approach in the second half."
            elif diff >= 10:
                para1 = f"HALFTIME: {home_abbr} {home_score}, {away_abbr} {away_score}\n\n"
                para1 += f"{home_abbr} takes a solid {diff}-point lead into the locker room. "
                para1 += f"The first half belonged to the home team, but {away_abbr} is still within striking distance with adjustments."
            else:
                para1 = f"HALFTIME: {home_abbr} {home_score}, {away_abbr} {away_score}\n\n"
                para1 += f"A competitive first half with {home_abbr} clinging to a {diff}-point edge. "
                para1 += "This one is far from over – the second half should be entertaining."
        elif away_score > home_score:
            if diff >= 17:
                para1 = f"HALFTIME: {away_abbr} {away_score}, {home_abbr} {home_score}\n\n"
                para1 += f"The visitors have silenced the home crowd. {away_abbr} takes a commanding {diff}-point lead into the break. "
                para1 += f"{home_abbr} needs to regroup quickly or this game could get away from them."
            elif diff >= 10:
                para1 = f"HALFTIME: {away_abbr} {away_score}, {home_abbr} {home_score}\n\n"
                para1 += f"{away_abbr} is executing their game plan to perfection on the road, up {diff}. "
                para1 += f"{home_abbr} must find answers coming out of the break."
            else:
                para1 = f"HALFTIME: {away_abbr} {away_score}, {home_abbr} {home_score}\n\n"
                para1 += f"The road team {away_abbr} holds a slim {diff}-point advantage at the half. "
                para1 += "Expect the home team to make a push in the third quarter."
        else:
            para1 = f"HALFTIME: {home_abbr} {home_score}, {away_abbr} {away_score}\n\n"
            para1 += f"We're all knotted up at {home_score} apiece! An evenly matched first half with neither team able to pull away. "
            para1 += "The second half could come down to which team makes the better adjustments."
        paragraphs.append(para1)
        
        # Paragraph 2: First Half Story (based on play history)
        if self.play_history:
            plays = len(self.play_history)
            runs = sum(1 for p in self.play_history if 'rush' in str(p).lower())
            passes = plays - runs
            
            para2 = "FIRST HALF STORY: "
            if runs > passes * 1.3:
                para2 += f"Ground game has been the story – teams combined for {plays} plays with a heavy emphasis on the run. "
            elif passes > runs * 1.3:
                para2 += f"An aerial assault in the first half – both teams letting it fly through the air. "
            else:
                para2 += f"Balanced attacks from both sides through {plays} plays. "
            
            # Add momentum narrative
            if self.momentum_state == 'home':
                para2 += f"{home_abbr} has seized control and carries the momentum into halftime."
            elif self.momentum_state == 'away':
                para2 += f"{away_abbr} is riding a wave of momentum heading into the break."
            else:
                para2 += "Neither team has established clear momentum."
            
            paragraphs.append(para2)
        
        # Paragraph 3: Key Context from Pre-game
        if self.team_context:
            ctx = self.team_context
            home_ctx = ctx.get('home_team', {}) if isinstance(ctx, dict) else {}
            away_ctx = ctx.get('away_team', {}) if isinstance(ctx, dict) else {}
            
            home_ppg = home_ctx.get('ppg', 0)
            away_ppg = away_ctx.get('ppg', 0)
            
            if home_ppg > 0:
                para3 = "CONTEXT: "
                expected_home_half = home_ppg / 2
                expected_away_half = away_ppg / 2
                
                if home_score > expected_home_half * 1.3:
                    para3 += f"{home_abbr} is exceeding their season scoring pace. "
                elif home_score < expected_home_half * 0.7:
                    para3 += f"{home_abbr} is struggling to score, below their usual {home_ppg:.0f} PPG average. "
                
                if away_score > expected_away_half * 1.3:
                    para3 += f"{away_abbr} offense is clicking. "
                elif away_score < expected_away_half * 0.7:
                    para3 += f"{away_abbr}'s offense has been quiet. "
                
                if para3 != "CONTEXT: ":
                    paragraphs.append(para3)
        
        # Paragraph 4: Second Half Preview
        para4 = "SECOND HALF OUTLOOK: "
        if diff >= 14:
            leader = home_abbr if home_score > away_score else away_abbr
            trailer = away_abbr if home_score > away_score else home_abbr
            para4 += f"Historically, teams trailing by {diff}+ at halftime face long odds. "
            para4 += f"{trailer} will need to score quickly and force turnovers to get back in this."
        elif diff >= 7:
            leader = home_abbr if home_score > away_score else away_abbr
            trailer = away_abbr if home_score > away_score else home_abbr
            para4 += f"One score game – {trailer} is very much alive. "
            para4 += f"Watch for {trailer} to come out aggressive on the first drive of the second half."
        else:
            para4 += "This is shaping up to be a fourth quarter battle. "
            para4 += "Both teams will likely save their best plays for the final frame."
        paragraphs.append(para4)
        
        return "\n\n".join(paragraphs)
    
    def _generate_first_half_analysis(self, state: Dict[str, Any], 
                                       home_abbr: str, away_abbr: str,
                                       home_score: int, away_score: int) -> str:
        """
        Generate detailed first half analysis for halftime.
        Multi-paragraph breakdown of what happened in the first half.
        """
        paragraphs = []
        
        # Scoring breakdown
        total_points = home_score + away_score
        if total_points >= 35:
            para1 = f"A high-scoring first half with {total_points} combined points! "
            if home_score > away_score:
                para1 += f"{home_abbr}'s offense has been clicking, putting up {home_score} points at home."
            elif away_score > home_score:
                para1 += f"{away_abbr} has been lighting up the scoreboard on the road with {away_score}."
            else:
                para1 += "Both offenses are firing on all cylinders."
        elif total_points <= 14:
            para1 = f"A defensive struggle so far with just {total_points} total points. "
            para1 += "Both defenses are making it tough to move the ball."
        else:
            para1 = f"We've seen {total_points} points in the first half. "
            if abs(home_score - away_score) <= 3:
                para1 += "A competitive, evenly-matched contest so far."
            else:
                leader = home_abbr if home_score > away_score else away_abbr
                para1 += f"{leader} has established an edge but it's still anyone's game."
        paragraphs.append(para1)
        
        # Game flow analysis from play history
        if self.play_history:
            total_plays = len(self.play_history)
            runs = sum(1 for p in self.play_history if 'rush' in str(p).lower() or 'run' in str(p).lower())
            passes = total_plays - runs
            
            para2 = f"Through {total_plays} plays, "
            if runs > passes * 1.5:
                para2 += "this game has been dominated by the ground attack. "
                para2 += "Both teams establishing the run early and controlling the clock."
            elif passes > runs * 1.5:
                para2 += "we've seen a pass-heavy first half. "
                para2 += "Teams are pushing the ball downfield through the air."
            else:
                para2 += "we've seen a balanced mix of run and pass. "
                para2 += "Both coordinators keeping the defense guessing."
            paragraphs.append(para2)
        
        # Context comparison if available
        if self.team_context:
            ctx = self.team_context
            home_ctx = ctx.get('home_team', {}) if isinstance(ctx, dict) else {}
            away_ctx = ctx.get('away_team', {}) if isinstance(ctx, dict) else {}
            
            home_ppg = home_ctx.get('ppg', 0)
            away_ppg = away_ctx.get('ppg', 0)
            
            if home_ppg > 0:
                expected_home = home_ppg / 2
                expected_away = away_ppg / 2
                
                para3 = "COMPARED TO SEASON AVERAGES: "
                if home_score > expected_home * 1.2:
                    para3 += f"{home_abbr} is exceeding expectations (usually {home_ppg:.0f} PPG). "
                elif home_score < expected_home * 0.6:
                    para3 += f"{home_abbr} is struggling to score (avg {home_ppg:.0f} PPG). "
                
                if away_score > expected_away * 1.2:
                    para3 += f"{away_abbr}'s offense is rolling today. "
                elif away_score < expected_away * 0.6:
                    para3 += f"{away_abbr} is being held in check. "
                
                if para3 != "COMPARED TO SEASON AVERAGES: ":
                    paragraphs.append(para3)
        
        return "\n\n".join(paragraphs) if paragraphs else "First half in the books. Second half coming up!"
    
    def _generate_second_half_preview(self, state: Dict[str, Any],
                                       leader: Optional[str], trailer: Optional[str],
                                       score_diff: int, home_abbr: str, away_abbr: str) -> str:
        """
        Generate second half preview and predictions for halftime.
        """
        paragraphs = []
        
        # Situation assessment
        if leader and score_diff >= 14:
            para1 = f"SITUATION: {leader} has a commanding {score_diff}-point lead. "
            para1 += f"Historically, teams trailing by this much at halftime face an uphill battle. "
            para1 += f"{trailer} will need to score quickly and likely force turnovers to get back in this."
        elif leader and score_diff >= 7:
            para1 = f"SITUATION: {leader} takes a {score_diff}-point cushion into the break. "
            para1 += f"A one-score game means {trailer} is very much alive. "
            para1 += "Expect an aggressive start to the third quarter."
        elif leader:
            para1 = f"SITUATION: Just {score_diff} points separate these teams. "
            para1 += "This is shaping up to be a fourth quarter battle."
        else:
            para1 = "SITUATION: Tied at halftime! "
            para1 += "Neither team has been able to pull away. The second half will decide it."
        paragraphs.append(para1)
        
        # What to watch for
        para2 = "WHAT TO WATCH: "
        if trailer:
            para2 += f"Will {trailer} come out with adjustments? "
            if score_diff >= 10:
                para2 += "Look for more aggressive play-calling and potential risks. "
            para2 += f"Meanwhile, {leader} will try to maintain their momentum and close this out."
        else:
            para2 += "Both teams will be looking to land the first punch of the second half. "
            para2 += "The team that scores first out of the break often carries that momentum."
        paragraphs.append(para2)
        
        # Third quarter prediction
        para3 = "THIRD QUARTER: "
        if home_abbr == leader or (not leader):
            para3 += f"Home teams typically come out strong after halftime adjustments. "
            para3 += f"Watch for {home_abbr} to try to extend their lead or take control."
        else:
            para3 += f"The visitors {away_abbr} have seized control on the road. "
            para3 += f"Can {home_abbr} use the home crowd energy to spark a comeback?"
        paragraphs.append(para3)
        
        return "\n\n".join(paragraphs)
    
    def _generate_halftime_spotlights(self, state: Dict[str, Any]) -> Optional[Insight]:
        """Generate player spotlight insight for halftime."""
        # Use tracked player stats if available
        if not self.player_stats:
            return None
        
        # Find top performer
        top_player = None
        top_yards = 0
        for player, stats in self.player_stats.items():
            total = stats.get('rush_yards', 0) + stats.get('rec_yards', 0) + stats.get('pass_yards', 0)
            if total > top_yards:
                top_yards = total
                top_player = player
        
        if top_player and top_yards > 50:
            return Insight(
                id=str(uuid.uuid4())[:8],
                insight_type='halftime_spotlight',
                priority=7,
                timing='immediate',
                headline=f'⭐ First Half Star: {top_player}',
                body=f"{top_player} has been the standout performer with {top_yards} total yards so far.",
                ttl=300
            )
        return None
    
    def _generate_momentum_analysis(self, state: Dict[str, Any]) -> Optional[Insight]:
        """Analyze momentum heading into halftime."""
        # Check recent narrative beats
        recent = self.game_narrative[-5:] if self.game_narrative else []
        
        if not recent:
            return None
        
        # Count events by type
        home_momentum = 0
        away_momentum = 0
        for event in recent:
            # Simplified momentum tracking
            if 'touchdown' in event.get('description', '').lower():
                home_momentum += 3  # Placeholder - would need team tracking
        
        return Insight(
            id=str(uuid.uuid4())[:8],
            insight_type='momentum_analysis',
            priority=6,
            timing='immediate',
            headline='📈 Momentum Check',
            body="The momentum has been shifting throughout the half. Watch for which team comes out with more energy in the third quarter.",
            ttl=300
        )
    
    def _generate_situation_analysis(self, state: Dict[str, Any], leader: str, trailer: str, diff: int) -> str:
        """Generate analysis of current game situation."""
        quarter = state.get('quarter', 1)
        
        if leader is None:
            return "A tied ball game! Every possession matters from here."
        
        if quarter <= 2:
            if diff >= 14:
                return f"{leader} has built a comfortable {diff}-point lead in the first half. {trailer} needs to make adjustments."
            elif diff >= 7:
                return f"{leader} up by {diff}. Still early, but {trailer} needs to respond."
            else:
                return f"Close game with {leader} ahead by {diff}. This one could go either way."
        else:
            if diff >= 14:
                return f"With {leader} up {diff} in the {self._quarter_name(quarter)}, {trailer} is running out of time to mount a comeback."
            elif diff >= 7:
                return f"{leader} maintains a {diff}-point lead. {trailer} needs to start making plays."
            else:
                return f"Tight game in Q{quarter}! Just {diff} points separate these teams."
    
    def _quarter_name(self, q: int) -> str:
        names = {1: 'first quarter', 2: 'second quarter', 3: 'third quarter', 4: 'fourth quarter'}
        return names.get(q, f'quarter {q}')
    
    def _generate_key_stats_insight(self, state: Dict[str, Any]) -> Optional[Insight]:
        """Generate key stats insight during break."""
        # Would integrate with fetched box score data
        # For now, return a placeholder that could be enhanced
        return None
    
    def _generate_commercial_break_analysis(
        self, state: Dict[str, Any], leader: str, trailer: str, 
        diff: int, quarter: int, clock: str, break_content: Optional[Dict[str, Any]]
    ) -> str:
        """
        Generate rich, multi-paragraph analysis for commercial breaks.
        
        This is the prime opportunity to provide in-depth commentary since
        the viewer has time to read and isn't watching live action.
        """
        paragraphs = []
        
        # Get team context for richer analysis
        home_team = state.get('home_team', {})
        away_team = state.get('away_team', {})
        home_abbr = home_team.get('abbreviation', 'HOME') if isinstance(home_team, dict) else str(home_team)
        away_abbr = away_team.get('abbreviation', 'AWAY') if isinstance(away_team, dict) else str(away_team)
        home_score = home_team.get('score', 0) if isinstance(home_team, dict) else state.get('home_score', 0)
        away_score = away_team.get('score', 0) if isinstance(away_team, dict) else state.get('away_score', 0)
        
        # Paragraph 1: Game State Overview
        q_name = self._quarter_name(quarter)
        if leader:
            if diff >= 17:
                para1 = f"We're back from the break with {leader} firmly in control, up {diff} points in the {q_name}. "
                para1 += f"{trailer} is facing a steep uphill climb from here."
            elif diff >= 10:
                para1 = f"{leader} holds a solid {diff}-point advantage as we move through the {q_name}. "
                para1 += f"{trailer} needs to find answers on both sides of the ball."
            elif diff >= 3:
                para1 = f"Close game here in the {q_name}! {leader} leads by just {diff}. "
                para1 += "One big play could swing this either direction."
            else:
                para1 = f"We've got ourselves a ballgame! {leader} clings to a slim {diff}-point lead in the {q_name}."
        else:
            para1 = f"All tied up in the {q_name}! This is anyone's game right now."
        paragraphs.append(para1)
        
        # Paragraph 2: Team-Specific Context (if we have it)
        if self.team_context:
            ctx = self.team_context
            home_ctx = ctx.get('home_team', {}) if isinstance(ctx, dict) else {}
            away_ctx = ctx.get('away_team', {}) if isinstance(ctx, dict) else {}
            
            # Look for interesting team stats to mention
            home_ppg = home_ctx.get('ppg', 0)
            away_ppg = away_ctx.get('ppg', 0)
            
            if home_ppg > 0 and away_ppg > 0:
                if home_score > home_ppg * (quarter / 4):
                    para2 = f"{home_abbr} is outpacing their season average of {home_ppg:.1f} PPG so far. "
                elif home_score < home_ppg * (quarter / 4) * 0.5:
                    para2 = f"{home_abbr} is struggling to score, well below their {home_ppg:.1f} PPG average. "
                else:
                    para2 = f"Both teams playing close to their season averages. "
                
                # Add context about what's working or not
                if home_score > away_score + 7:
                    para2 += f"The home team is imposing their will on this game."
                elif away_score > home_score + 7:
                    para2 += f"The visitors have come in and taken control on the road."
                
                paragraphs.append(para2)
        
        # Paragraph 3: Game Flow Analysis (from our tracking)
        if self.play_history and len(self.play_history) >= 5:
            recent_plays = self.play_history[-10:]
            runs = sum(1 for p in recent_plays if 'rush' in p.get('type', '').lower() or 'run' in p.get('description', '').lower())
            passes = len(recent_plays) - runs
            
            if runs > passes * 1.5:
                para3 = f"The game has been run-heavy lately – teams are grinding it out on the ground. "
            elif passes > runs * 1.5:
                para3 = f"Teams are airing it out – we've seen a lot of passes in recent possessions. "
            else:
                para3 = f"Balanced attack from both teams so far. "
            
            # Add momentum context
            if self.momentum_state == 'home':
                para3 += f"{home_abbr} has seized momentum and looks to be in control."
            elif self.momentum_state == 'away':
                para3 += f"{away_abbr} is riding a wave of momentum right now."
            
            paragraphs.append(para3)
        
        # Paragraph 4: What to Watch Next
        if quarter < 4:
            para4 = f"As we head deeper into Q{quarter}, watch for "
            if diff < 7:
                para4 += "which team can put together a sustained drive to take control."
            elif trailer:
                para4 += f"{trailer} to see if they can chip away at this deficit before halftime." if quarter == 2 else f"{trailer}'s response to falling behind."
            else:
                para4 += "how these evenly-matched teams adjust."
        else:
            para4 = "Fourth quarter football – every play matters now. "
            if diff > 10:
                para4 += f"Can {trailer} mount a comeback, or will {leader} close this out?"
            else:
                para4 += "This one's going down to the wire."
        paragraphs.append(para4)
        
        # Paragraph 5: Key Storylines from context
        if break_content and break_content.get('analysis_points'):
            storylines = break_content.get('analysis_points', [])[:2]
            if storylines:
                para5 = "Key storylines: " + " ".join(storylines)
                paragraphs.append(para5)
        
        return "\n\n".join(paragraphs)
    
    def _analyze_timeout_reason(self, state: Dict[str, Any], team: str, quarter: int, clock: str) -> str:
        """Analyze why a team might have called timeout."""
        down = state.get('down', 1)
        distance = state.get('distance', 10)
        
        # Parse clock for time analysis
        try:
            parts = clock.split(':')
            minutes = int(parts[0])
        except:
            minutes = 15
        
        if quarter == 4 and minutes <= 2:
            return f"{team} stopping the clock in the crucial final minutes. Every second counts now."
        elif down == 4:
            return f"Timeout on 4th down - {team} is deciding whether to go for it, punt, or kick."
        elif down == 3 and distance >= 7:
            return f"3rd and long - {team} taking time to get the right play call. This is a pivotal down."
        else:
            return f"{team} regroups with a timeout. Coach likely didn't like the personnel or formation they saw."
    
    def _generate_post_score_context(self, state: Dict[str, Any], points: int, leader: str, trailer: str, diff: int) -> str:
        """Generate context after a scoring play."""
        quarter = state.get('quarter', 1)
        
        if points >= 7:  # Likely touchdown
            if leader is None:
                return "Touchdown ties the game! We've got ourselves a ballgame."
            elif diff >= 14:
                return f"That TD extends the lead to {diff}. {trailer} has their work cut out for them."
            elif diff == 7:
                return f"One score game now. {trailer} can tie it with a TD on the next possession."
            else:
                return "Score! The momentum could be shifting here."
        else:  # Field goal
            if leader is None:
                return "Field goal ties it up! Close game continues."
            elif diff <= 3:
                return f"Just {diff} points separate these teams now. Anyone's game."
            else:
                return f"Three points added. {leader} leads by {diff}."
    
    def _generate_two_minute_context(self, state: Dict[str, Any], half: str, leader: str, trailer: str, diff: int) -> str:
        """Generate context for two-minute warning."""
        if half == 'first':
            if leader is None:
                return "Two minutes left in the half, tied game. Both teams looking to take the lead into halftime."
            elif diff >= 10:
                return f"{leader} up by {diff} with two minutes left. {trailer} needs a quick score before the half."
            else:
                return f"Two minutes left in the half. {leader} leads by {diff} - can they add to it?"
        else:  # second half
            if leader is None:
                return "Two-minute warning in the fourth! Tied game - this is where legends are made."
            elif diff >= 14:
                return f"{leader} up by {diff}. Unless something dramatic happens, this one's nearly over."
            elif diff >= 7:
                return f"Two-minute warning! {trailer} down by {diff} - they need a TD and will have to go for 2."
            elif diff <= 3:
                return f"Inside two minutes, {diff}-point game! Field goal range could win it for either team."
            else:
                return f"Crunch time! {leader} up {diff}. Every play matters now."
    
    def _generate_quarter_summary(self, state: Dict[str, Any], quarter_ending: int) -> str:
        """Generate end-of-quarter summary."""
        home = state.get('home_team', {})
        away = state.get('away_team', {})
        home_abbr = home.get('abbreviation', 'HOME') if isinstance(home, dict) else 'HOME'
        away_abbr = away.get('abbreviation', 'AWAY') if isinstance(away, dict) else 'AWAY'
        home_score = home.get('score', 0) if isinstance(home, dict) else state.get('home_score', 0)
        away_score = away.get('score', 0) if isinstance(away, dict) else state.get('away_score', 0)
        
        if quarter_ending == 1:
            return f"After one quarter: {away_abbr} {away_score}, {home_abbr} {home_score}. Three quarters to go."
        elif quarter_ending == 3:
            return f"Heading into the fourth: {away_abbr} {away_score}, {home_abbr} {home_score}. Final quarter coming up."
        else:
            return f"Quarter {quarter_ending} complete. Score: {away_abbr} {away_score} - {home_abbr} {home_score}."
    
    def _generate_pre_play_insight(self, state: Dict[str, Any]) -> Optional[Insight]:
        """Generate a pre-play strategic insight based on current situation."""
        down = state.get('down', 1)
        distance = state.get('distance', 10)
        
        templates = self.templates.templates.get('pre_play_templates', {})
        
        # Select template based on down and distance
        if down == 1:
            template = templates.get('1st_down', {})
        elif down == 2:
            if distance <= 4:
                template = templates.get('2nd_short', {})
            else:
                template = templates.get('2nd_long', {})
        elif down == 4:
            template = templates.get('4th_down', {})
        else:
            return None  # 3rd down handled separately
        
        if not template:
            return None
        
        # Get headline/body options
        headlines = template.get('headlines', [template.get('headline', '')])
        bodies = template.get('bodies', [template.get('body', '')])
        
        # Use varied selection with recency avoidance
        headline, body = self.select_varied_headline(
            headlines, bodies, {'distance': distance}
        )
        
        return Insight(
            id=str(uuid.uuid4())[:8],
            insight_type='pre_play',
            priority=template.get('priority', 4),
            timing='pre_snap',
            headline=headline,
            body=body,
            ttl=template.get('ttl', 12)
        )
    
    def _generate_post_play_insight(self, change: Dict[str, Any], state: Dict[str, Any]) -> Optional[Insight]:
        """Generate a post-play analytical insight."""
        import re
        
        description = change.get('description', '').lower()
        original_desc = change.get('description', '')
        data = change.get('data', {})
        yards = data.get('yards', 0)
        
        templates = self.templates.templates.get('post_play_templates', {})
        
        # Determine play type from description
        if 'sack' in description:
            template = templates.get('sack', {})
            match = re.search(r'for (-?\d+) yard', description)
            if match:
                yards = abs(int(match.group(1)))
        elif 'incomplete' in description:
            template = templates.get('incomplete', {})
        elif 'penalty' in description or 'flag' in description:
            template = templates.get('penalty', {})
        elif 'pass' in description and ('to' in description or 'caught' in description):
            template = templates.get('pass_complete', {})
            match = re.search(r'for (\d+) yard', description)
            if match:
                yards = int(match.group(1))
        elif 'rush' in description or 'run' in description or 'up the middle' in description or 'left' in description or 'right' in description:
            template = templates.get('run_gain', {})
            match = re.search(r'for (\d+) yard', description)
            if match:
                yards = int(match.group(1))
        else:
            return None  # Skip unknown play types
        
        if not template:
            return None
        
        # Get headline/body options
        headlines = template.get('headlines', [template.get('headline', '')])
        bodies = template.get('bodies', [template.get('body', '')])
        
        # Use varied selection with recency avoidance
        headline, body = self.select_varied_headline(
            headlines, bodies, {'yards': yards, 'description': original_desc}
        )
        
        # Track this play for game flow detection
        self.track_play(original_desc, yards)
        
        return Insight(
            id=str(uuid.uuid4())[:8],
            insight_type='post_play',
            priority=template.get('priority', 4),
            timing='post_play',
            headline=headline,
            body=body,
            ttl=template.get('ttl', 10)
        )

    def _should_use_llm(self, change: Dict[str, Any]) -> bool:
        """Determine if LLM should be used for this change."""
        change_type = change.get('change_type', '')
        significance = change.get('significance', 5)

        # Use LLM for significant game events
        high_llm_types = [
            'score_change',    # Touchdowns, field goals
            'turnover',        # Interceptions, fumbles
            'momentum_shift', 
            'quarter_change', 
            'halftime', 
            'game_end'
        ]

        if change_type in high_llm_types:
            return True

        if significance >= 8:
            return True

        return False

    def _generate_llm_insight(self, change: Dict[str, Any], state: Dict[str, Any]) -> Optional[Insight]:
        """Generate LLM-based insight for significant moments."""
        change_type = change.get('change_type', '')
        description = change.get('description', '')
        
        # Build rich context including team info
        context = {
            'change': change,
            'state': state,
            'team_context': self.team_context,
            'recent_plays': self.play_history[-5:] if self.play_history else []
        }
        
        # Create a focused prompt based on event type
        if change_type == 'score_change':
            prompt = f"""A scoring play just happened in an NFL game. Generate an insightful, excited commentary.

Play: {description}

Current Score: {state.get('away_team', {}).get('abbreviation', 'AWAY')} {state.get('away_team', {}).get('score', 0)} - {state.get('home_team', {}).get('abbreviation', 'HOME')} {state.get('home_team', {}).get('score', 0)}
Quarter: Q{state.get('quarter', 1)}
Clock: {state.get('clock', '')}

Respond with JSON: {{"headline": "short exciting headline", "body": "1-2 sentence analysis"}}"""

        elif change_type == 'turnover':
            prompt = f"""A turnover just happened in an NFL game. Generate insightful commentary about the impact.

Play: {description}

Game Situation: Q{state.get('quarter', 1)} {state.get('clock', '')}
Score: {state.get('away_team', {}).get('abbreviation', 'AWAY')} {state.get('away_team', {}).get('score', 0)} - {state.get('home_team', {}).get('abbreviation', 'HOME')} {state.get('home_team', {}).get('score', 0)}

Respond with JSON: {{"headline": "short impactful headline", "body": "1-2 sentence analysis of momentum shift"}}"""

        else:
            # Generic significant event
            prompt = f"""Analyze this NFL game moment:

Event: {description}
Type: {change_type}
Game: Q{state.get('quarter', 1)} {state.get('clock', '')}

Respond with JSON: {{"headline": "short headline", "body": "brief analysis"}}"""

        result = self.llm.generate_insight(context, prompt)

        if not result:
            return None

        try:
            import re
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                insight_type = 'score_change' if change_type == 'score_change' else 'turnover' if change_type == 'turnover' else 'llm_generated'
                return Insight(
                    id=str(uuid.uuid4())[:8],
                    insight_type=insight_type,
                    priority=9 if change_type in ['score_change', 'turnover'] else 7,
                    timing='immediate',
                    headline=data.get('headline', 'Game Update'),
                    body=data.get('body', result),
                    ttl=60
                )
        except json.JSONDecodeError:
            pass

        # Fallback: use raw text
        return Insight(
            id=str(uuid.uuid4())[:8],
            insight_type='llm_generated',
            priority=7,
            timing='post_play',
            headline='Game Update',
            body=result[:200],
            ttl=45
        )


# Global instances
templates = InsightTemplates()
llm_client = LLMClient(provider=LLM_PROVIDER, model=LLM_MODEL)
delivery_manager = DeliveryManager()
insight_generator = InsightGenerator(templates, llm_client)

# Pre-play service
pre_play_service_instance = None
user_preferences = {}
if PRE_PLAY_SERVICE_AVAILABLE:
    pre_play_service_instance = PrePlayService()
    logger.info("Pre-play metadata service initialized")
else:
    logger.warning("Pre-play metadata service not available")

# Session tracking
session_data = {
    'game_id': None,
    'insights_delivered': [],
    'user_questions': [],
    'session_start': None
}


# Delivery loop thread
def delivery_loop():
    """Background loop to deliver insights with broadcast delay support."""
    while True:
        try:
            # First, check if we can pull new insights from the queue into the delay buffer
            if delivery_manager.can_deliver_now():
                insight = delivery_manager.get_next_insight()
                if insight:
                    delivery_manager.record_delivery(insight)
                    # If delay is configured, buffer the insight; otherwise deliver immediately
                    if delay_buffer.delay_seconds > 0:
                        delay_buffer.add_insight(insight)
                    else:
                        delivery_manager.broadcast_insight(insight)
                        session_data['insights_delivered'].append(insight.to_dict())
            
            # Check for delayed insights ready to be delivered
            ready_insights = delay_buffer.get_ready_insights()
            for insight in ready_insights:
                delivery_manager.broadcast_insight(insight)
                session_data['insights_delivered'].append(insight.to_dict())

            time.sleep(0.5)

        except Exception as e:
            logger.error(f"Delivery loop error: {e}")
            time.sleep(1.0)


# Start delivery loop
delivery_thread = threading.Thread(target=delivery_loop, daemon=True)
delivery_thread.start()


# Flask Routes

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'auto-madden-insight-engine',
        'connected_clients': len(delivery_manager.connected_clients),
        'queued_insights': delivery_manager.insight_queue.qsize(),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/load_matchup', methods=['POST'])
def load_matchup():
    """Load team context for a matchup at game start."""
    data = request.get_json() or {}
    home_id = data.get('home_id')
    away_id = data.get('away_id')
    game_id = data.get('game_id')
    
    if not home_id or not away_id:
        return jsonify({'status': 'error', 'message': 'home_id and away_id required'}), 400
    
    logger.info(f"Loading matchup context: {away_id} @ {home_id} (game: {game_id})")
    
    # Use new comprehensive context loader if available
    full_context = None
    if load_game_context:
        try:
            full_context = load_game_context(home_id, away_id, game_id)
            logger.info(f"📚 Loaded comprehensive context: {full_context.summary[:100]}...")
            
            # Get LLM context for later use
            llm_context = get_llm_context() if get_llm_context else ""
            insight_generator.llm_game_context = llm_context
            
        except Exception as e:
            logger.error(f"Error loading full context: {e}")
    
    # Fallback to original simple context
    context = fetch_matchup_context(home_id, away_id)
    
    # Store in generator
    insight_generator.team_context = context
    insight_generator.reset_for_new_game()
    
    # Generate welcome insight with matchup summary
    summary = full_context.summary if full_context else context.get('summary', '')
    if summary:
        welcome_insight = Insight(
            id=str(uuid.uuid4())[:8],
            insight_type='matchup_preview',
            priority=8,
            timing='immediate',
            headline='🏈 Matchup Preview',
            body=summary,
            ttl=120
        )
        delivery_manager.queue_insight(welcome_insight)
    
    # If we have key storylines, share them too
    if full_context and full_context.key_storylines:
        storyline_insight = Insight(
            id=str(uuid.uuid4())[:8],
            insight_type='key_storylines',
            priority=7,
            timing='immediate',
            headline='📋 Key Storylines to Watch',
            body='\n'.join(f"• {s}" for s in full_context.key_storylines[:5]),
            ttl=180
        )
        delivery_manager.queue_insight(storyline_insight)
    
    return jsonify({
        'status': 'ok',
        'context': full_context.to_dict() if full_context else context,
        'message': 'Matchup context loaded',
        'has_articles': bool(full_context and full_context.articles) if full_context else False,
        'article_count': len(full_context.articles) if full_context else 0
    })


@app.route('/pregame', methods=['POST'])
def start_pregame():
    """
    Start pre-game insight sequence.
    
    Called when user connects to a game before kickoff.
    Delivers a series of pre-game insights with staggered timing.
    """
    data = request.get_json() or {}
    home_id = data.get('home_id')
    away_id = data.get('away_id')
    game_id = data.get('game_id')
    
    # Try to get team IDs from abbreviations if provided
    home_abbr = data.get('home_abbr', '')
    away_abbr = data.get('away_abbr', '')
    
    if not home_id and home_abbr and ESPN_ABBR_TO_ID:
        home_id = ESPN_ABBR_TO_ID.get(home_abbr.upper())
    if not away_id and away_abbr and ESPN_ABBR_TO_ID:
        away_id = ESPN_ABBR_TO_ID.get(away_abbr.upper())
    
    if not home_id or not away_id:
        return jsonify({
            'status': 'error', 
            'message': 'home_id/away_id or home_abbr/away_abbr required'
        }), 400
    
    logger.info(f"🎬 Starting pre-game sequence: {away_abbr or away_id} @ {home_abbr or home_id}")
    
    # Load matchup context first
    full_context = None
    if load_game_context:
        try:
            full_context = load_game_context(home_id, away_id, game_id)
            logger.info(f"📚 Pre-game context loaded: {full_context.summary[:80]}...")
            
            # Store LLM context
            llm_context = get_llm_context() if get_llm_context else ""
            insight_generator.llm_game_context = llm_context
            
        except Exception as e:
            logger.error(f"Error loading pre-game context: {e}")
    
    # Generate and queue pre-game insights
    pregame_insights = []
    if generate_pregame_insights:
        try:
            pregame_data = generate_pregame_insights()
            
            # Queue each insight with appropriate delay
            for pg in pregame_data:
                insight = Insight(
                    id=str(uuid.uuid4())[:8],
                    insight_type=pg['type'],
                    priority=pg['priority'],
                    timing='pregame',
                    headline=pg['headline'],
                    body=pg['body'],
                    ttl=300  # Pre-game insights valid for 5 minutes
                )
                
                # Add to delivery queue (delivery thread will handle timing via delay buffer)
                # For now, queue all immediately - they'll be delivered in order
                delivery_manager.queue_insight(insight)
                pregame_insights.append({
                    'headline': pg['headline'],
                    'delay': pg['delay']
                })
            
            logger.info(f"📋 Queued {len(pregame_insights)} pre-game insights")
            
        except Exception as e:
            logger.error(f"Error generating pre-game insights: {e}")
    
    # Add NFL Pro narrative insights for pregame
    if NFL_PRO_NARRATIVES_AVAILABLE and get_pregame_narrative_insights:
        try:
            nfl_pro_pregame = get_pregame_narrative_insights(count=4)
            for pg in nfl_pro_pregame:
                insight = Insight(
                    id=pg.get('id', str(uuid.uuid4())[:8]),
                    insight_type='nfl_pro_pregame',
                    priority=pg.get('priority', 7),
                    timing='pregame',
                    headline=f"📊 {pg.get('headline', 'Matchup Preview')[:50]}",
                    body=pg.get('body', ''),
                    ttl=300
                )
                delivery_manager.queue_insight(insight)
                pregame_insights.append({
                    'headline': pg.get('headline', '')[:50],
                    'delay': 0  # NFL Pro insights delivered immediately
                })
            logger.info(f"📊 Added {len(nfl_pro_pregame)} NFL Pro pregame insights")
        except Exception as e:
            logger.debug(f"Could not load NFL Pro pregame insights: {e}")
    
    # Reset generator for new game
    insight_generator.reset_for_new_game()
    if full_context:
        insight_generator.team_context = full_context.to_dict()
    
    return jsonify({
        'status': 'ok',
        'message': 'Pre-game sequence started',
        'insights_queued': len(pregame_insights),
        'insight_headlines': [i['headline'] for i in pregame_insights],
        'context_summary': full_context.summary if full_context else None
    })


@app.route('/pregame', methods=['GET'])
def get_pregame_insights():
    """
    GET endpoint for fetching pregame insights (used by replay interface).
    
    Query params:
        game_id: Game identifier
        home: Home team abbreviation
        away: Away team abbreviation
    
    Returns list of pregame insights.
    """
    game_id = request.args.get('game_id')
    home_abbr = request.args.get('home', '').upper()
    away_abbr = request.args.get('away', '').upper()
    
    insights = []
    
    # Try to get NFL Pro narrative insights for these teams
    if nfl_pro_narratives and (home_abbr or away_abbr):
        try:
            # Set current game teams for filtering
            if hasattr(nfl_pro_narratives, 'set_current_game_teams'):
                nfl_pro_narratives.set_current_game_teams({home_abbr, away_abbr})
            
            pregame_insights = nfl_pro_narratives.get_pregame_insights(count=5)
            
            for pg in pregame_insights:
                insights.append({
                    'headline': pg.get('title', pg.get('headline', 'Matchup Preview')),
                    'body': pg.get('text', pg.get('body', '')),
                    'type': 'pregame'
                })
        except Exception as e:
            logger.debug(f"Could not load NFL Pro pregame insights: {e}")
    
    # Add basic matchup info if we don't have enough
    if len(insights) < 2 and home_abbr and away_abbr:
        insights.append({
            'headline': f'🏈 {away_abbr} @ {home_abbr}',
            'body': f'Welcome to the matchup between the {away_abbr} and {home_abbr}. Press Kickoff when the ball is kicked to start tracking the game.',
            'type': 'pregame'
        })
    
    response = jsonify({
        'status': 'ok',
        'insights': insights,
        'count': len(insights)
    })
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


@app.route('/game/start', methods=['POST', 'OPTIONS'])
def start_game():
    """
    Notify insight engine that a game has started (replay mode).
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    data = request.get_json() or {}
    game_id = data.get('game_id')
    home_team = data.get('home_team', '').upper()
    away_team = data.get('away_team', '').upper()
    mode = data.get('mode', 'replay')
    week = data.get('week')  # Week number for insight loading
    
    logger.info(f"🎮 Game start notification: {away_team} @ {home_team} (mode={mode}, week={week})")
    
    # Set up session data
    global session_data
    session_data['game_id'] = game_id
    session_data['home_abbr'] = home_team
    session_data['away_abbr'] = away_team
    session_data['mode'] = mode
    session_data['week'] = week
    
    # Set current game teams for insight filtering
    if nfl_pro_narratives and hasattr(nfl_pro_narratives, 'set_current_game_teams'):
        nfl_pro_narratives.set_current_game_teams({home_team, away_team})

    # Set current game ID for tiered insight selection
    if game_id and nfl_pro_narratives and hasattr(nfl_pro_narratives, 'set_current_game_id'):
        nfl_pro_narratives.set_current_game_id(game_id)

    # Look up NFL Pro UUID from mapping
    nfl_pro_uuid = data.get('nfl_pro_uuid', '')
    if not nfl_pro_uuid and game_id:
        try:
            mapping_path = Path('/Volumes/main-drive/ai-PA/auto-madden/data/espn_nfl_pro_mapping.json')
            if mapping_path.exists():
                with open(mapping_path, 'r') as f:
                    mapping = json.load(f)
                nfl_pro_uuid = mapping.get('espn_to_nfl_pro', {}).get(str(game_id), '')
                if nfl_pro_uuid:
                    logger.info(f"📊 Found NFL Pro UUID: {nfl_pro_uuid[:8]}...")
                    session_data['nfl_pro_uuid'] = nfl_pro_uuid
        except Exception as e:
            logger.debug(f"Could not load NFL Pro mapping: {e}")

    # Ensure insights exist for this game (fetch if missing)
    if nfl_pro_uuid and home_team and away_team:
        fetched = ensure_game_insights(
            nfl_pro_uuid=nfl_pro_uuid,
            home_team=home_team,
            away_team=away_team,
            week=int(week) if week else None,
            espn_game_id=game_id
        )
        if fetched > 0:
            logger.info(f"📥 Auto-fetched {fetched} insights for this game")

    # Load insights (week-specific or all weeks if week not specified)
    if NFL_PRO_NARRATIVES_AVAILABLE and load_narrative_insights:
        try:
            loaded = load_narrative_insights(
                game_uuid=nfl_pro_uuid or game_id,
                home_team=home_team,
                away_team=away_team,
                week=int(week) if week else None
            )
            session_data['nfl_pro_insights_loaded'] = loaded > 0
            if week:
                logger.info(f"✅ Loaded {loaded} NFL Pro insights for Week {week}")
            else:
                logger.info(f"✅ Loaded {loaded} NFL Pro insights (all weeks)")
        except Exception as e:
            logger.warning(f"Could not load insights: {e}")
    
    # Reset insight generator
    if insight_generator:
        insight_generator.reset_for_new_game()
    
    response = jsonify({
        'status': 'ok',
        'message': f'Game started: {away_team} @ {home_team}',
        'game_id': game_id,
        'mode': mode
    })
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


@app.route('/event', methods=['POST', 'OPTIONS'])
def receive_event():
    """Receive game state change events from game-state-service or simulator."""
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    data = request.get_json() or {}
    
    # Support both formats:
    # 1. Simulator format: {event_type: '...', state: {...}, play_description: '...'}
    # 2. Original format: {change: {change_type: '...', ...}, state: {...}}
    if 'event_type' in data:
        # Simulator format - convert to expected format
        change = {
            'change_type': data.get('event_type'),
            'description': data.get('play_description', data.get('description', '')),
            'data': data  # Includes break_info for break_start events
        }
        state = data.get('state', {})
        
        # Log break events specially
        if data.get('event_type') == 'break_start':
            break_info = data.get('break_info', {})
            logger.info(f"⏸️ Break event received: {break_info.get('break_type')} - {break_info.get('description')}")
    else:
        # Original format
        change = data.get('change', {})
        state = data.get('state', {})

    logger.info(f"Received event: {change.get('change_type')} - {change.get('description', '')[:50]}")

    # Update delivery manager with game state
    delivery_manager.update_game_state(state)

    # Update session data
    if state.get('game_id') and not session_data['game_id']:
        session_data['game_id'] = state['game_id']
        session_data['session_start'] = datetime.now().isoformat()

        # Look up NFL Pro UUID from mapping if not in state
        nfl_pro_uuid = state.get('nfl_pro_uuid')
        if not nfl_pro_uuid:
            try:
                mapping_path = Path('/Volumes/main-drive/ai-PA/auto-madden/data/espn_nfl_pro_mapping.json')
                if mapping_path.exists():
                    with open(mapping_path, 'r') as f:
                        mapping = json.load(f)
                    nfl_pro_uuid = mapping.get('espn_to_nfl_pro', {}).get(str(state['game_id']), '')
            except Exception as e:
                logger.debug(f"Could not load NFL Pro mapping: {e}")

        if nfl_pro_uuid:
            session_data['nfl_pro_uuid'] = nfl_pro_uuid
            logger.info(f"📊 NFL Pro UUID for auto-fetch: {nfl_pro_uuid[:8]}...")

        # === ENSURE INSIGHTS EXIST FOR THIS GAME (FETCH IF MISSING) ===
        home_team = state.get('home_team', {}).get('abbreviation', '')
        away_team = state.get('away_team', {}).get('abbreviation', '')
        week = session_data.get('week') or state.get('week')

        if nfl_pro_uuid and home_team and away_team:
            fetched = ensure_game_insights(
                nfl_pro_uuid=nfl_pro_uuid,
                home_team=home_team,
                away_team=away_team,
                week=int(week) if week else None,
                espn_game_id=state.get('game_id')
            )
            if fetched > 0:
                logger.info(f"📥 Auto-fetched {fetched} insights for this game")

        # === LOAD NFL PRO NARRATIVE INSIGHTS FOR THIS GAME ===
        if NFL_PRO_NARRATIVES_AVAILABLE and load_narrative_insights:
            try:
                # Use session nfl_pro_uuid or fallback to game_id
                nfl_pro_uuid = session_data.get('nfl_pro_uuid', state.get('game_id', ''))
                
                if home_team and away_team:
                    # Get week from session (set by /game/start) or state
                    week = session_data.get('week') or state.get('week')
                    logger.info(f"🏈 Loading NFL Pro insights for {away_team} @ {home_team} (Week {week})")
                    success = load_narrative_insights(
                        game_uuid=nfl_pro_uuid,
                        home_team=home_team,
                        away_team=away_team,
                        week=int(week) if week else None
                    )
                    if success:
                        logger.info("✅ NFL Pro narrative insights loaded successfully")
                        session_data['nfl_pro_insights_loaded'] = True
                    else:
                        logger.warning("⚠️ Could not load NFL Pro insights - will use templates only")
                        session_data['nfl_pro_insights_loaded'] = False
            except Exception as e:
                logger.error(f"Error loading NFL Pro insights: {e}")
                session_data['nfl_pro_insights_loaded'] = False

    # Generate insights
    insights = insight_generator.generate_insights(change, state)
    
    # Check for game flow patterns and add pattern insights
    patterns = insight_generator.get_game_flow_patterns(state)
    for pattern in patterns:
        pattern_insight = generate_pattern_insight(pattern, state, insight_generator)
        if pattern_insight:
            insights.append(pattern_insight)
    
    # === NEW: Track players from play description ===
    play_desc = change.get('description', '')
    if play_desc:
        # Extract yards from description
        import re
        yards_match = re.search(r'for (\d+) yard', play_desc)
        yards = int(yards_match.group(1)) if yards_match else 0
        insight_generator.track_player(play_desc, yards)
    
    # === NEW: Track score changes for momentum ===
    change_type = change.get('change_type', '')
    if change_type == 'score_change':
        insight_generator.track_score_change(state, play_desc)
        insight_generator.add_narrative_beat('score_change', play_desc, significance=8)
        
        # Check for momentum insight
        momentum = insight_generator.get_momentum_insight(state)
        if momentum:
            insights.append(Insight(
                id=str(uuid.uuid4())[:8],
                insight_type='momentum',
                priority=7,
                timing='post_play',
                headline=momentum['headline'],
                body=momentum['body'],
                ttl=45
            ))
    
    # === NEW: Add narrative beats for key events ===
    if change_type == 'turnover':
        insight_generator.add_narrative_beat('turnover', play_desc, significance=9)
    elif change_type == 'big_play':
        insight_generator.add_narrative_beat('big_play', play_desc, significance=7)
    
    # === NEW: Check for player spotlight (every 5 plays) ===
    if len(insight_generator.play_history) % 5 == 0:
        spotlight = insight_generator.get_player_spotlight()
        if spotlight:
            spotlight_insight = generate_spotlight_insight(spotlight, state)
            if spotlight_insight:
                insights.append(spotlight_insight)
        
        # Check for narrative theme insight
        narrative = insight_generator.get_narrative_insight(state)
        if narrative:
            insights.append(Insight(
                id=str(uuid.uuid4())[:8],
                insight_type='narrative',
                priority=6,
                timing='stoppage',
                headline=narrative['headline'],
                body=narrative['body'],
                ttl=60
            ))

    # For replay mode or direct HTTP requests, DON'T queue insights
    # (they'll be returned in the response instead to avoid doubling)
    # For live mode with WebSocket, queue them for broadcast
    mode = data.get('mode', session_data.get('mode', 'live'))
    if mode != 'replay':
        for insight in insights:
            delivery_manager.queue_insight(insight)
    
    # === PRE-PLAY / POST-SNAP ANALYSIS ===
    # Generate and broadcast analysis data
    presnap_sent = False
    postsnap_sent = False
    
    if change_type in ['play_complete', 'new_play', 'score_change', 'turnover', 'big_play', 'first_down']:
        current_down = state.get('down', 0)

        # Check if NFL Pro play data was provided (has rich pre/post data)
        nfl_pro_play = data.get('nfl_pro_play') or data.get('play_data')

        # Auto-fetch from NFL Pro if not provided and we have a session UUID
        # Fallback: look up UUID from mapping if we have game_id but no UUID
        if not session_data.get('nfl_pro_uuid') and state.get('game_id'):
            try:
                mapping_path = Path('/Volumes/main-drive/ai-PA/auto-madden/data/espn_nfl_pro_mapping.json')
                if mapping_path.exists():
                    with open(mapping_path, 'r') as f:
                        mapping = json.load(f)
                    game_uuid = mapping.get('espn_to_nfl_pro', {}).get(str(state['game_id']), '')
                    if game_uuid:
                        session_data['nfl_pro_uuid'] = game_uuid
                        logger.info(f"📊 NFL Pro UUID (fallback lookup): {game_uuid[:8]}...")
            except Exception as e:
                logger.debug(f"Could not load NFL Pro mapping: {e}")

        if not nfl_pro_play and session_data.get('nfl_pro_uuid'):
            nfl_pro_play = _get_matching_nfl_pro_play(state, change)

        if nfl_pro_play:
            logger.info(f"NFL Pro play data received: offense={nfl_pro_play.get('offense')}, defense={nfl_pro_play.get('defense')}")

        if nfl_pro_play and isinstance(nfl_pro_play, dict) and nfl_pro_play.get('offense'):
            # === NFL PRO DATA AVAILABLE - Rich analysis ===
            try:
                parsed = _parse_nfl_pro_play_data(nfl_pro_play)
                
                # Send post-snap analysis (for the COMPLETED play)
                # This includes the formation/personnel that was used AND the result
                if parsed.get('postsnap'):
                    postsnap_data = parsed['postsnap']
                    delivery_manager.broadcast_postsnap(postsnap_data)
                    postsnap_sent = True
                    logger.info(f"📊 Post-snap: {postsnap_data.get('defense', {}).get('coverage', 'N/A')}, {postsnap_data.get('yards', 0)} yards")

                # Send pre-snap data (formation/personnel for this play)
                # With the viewing delay, frontend shows this BEFORE the play text appears,
                # giving viewers a preview of what's coming. Frontend suppresses this if
                # delay is too short for it to be useful.
                if parsed.get('presnap'):
                    presnap_data = parsed['presnap']
                    off = presnap_data.get('offense', {})
                    has_presnap_data = off.get('personnel') or off.get('formation')
                    if has_presnap_data:
                        delivery_manager.broadcast_presnap(presnap_data)
                        presnap_sent = True
                        logger.info(f"📊 Pre-snap: {off.get('personnel', '')} {off.get('formation', '')}")
                    
            except Exception as e:
                logger.warning(f"Error parsing NFL Pro play data: {e}")
        
        else:
            # === FALLBACK: ESPN/Simulator data ===
            try:
                # Generate ESPN-based post-snap analysis
                description = change.get('description', '')
                if description and change_type in ['play_complete', 'new_play']:
                    espn_postsnap = _build_espn_postsnap(description, state, change)
                    if espn_postsnap:
                        delivery_manager.broadcast_postsnap(espn_postsnap)
                        postsnap_sent = True

                # NOTE: No pre-play/pre-snap broadcast here - we don't have formation
                # data for the upcoming play, only for the play that just completed.
            except Exception as e:
                logger.warning(f"Error generating analysis metadata: {e}")

    # Serialize insights for response (useful for replay mode or debugging)
    insight_data = []
    for insight in insights:
        if hasattr(insight, 'to_dict'):
            insight_data.append(insight.to_dict())
        elif isinstance(insight, dict):
            insight_data.append(insight)
        else:
            insight_data.append({
                'headline': getattr(insight, 'headline', str(insight)),
                'body': getattr(insight, 'body', ''),
                'type': getattr(insight, 'insight_type', 'info')
            })
    
    response = jsonify({
        'status': 'ok',
        'insights_generated': len(insights),
        'insights': insight_data,
        'presnap_sent': presnap_sent,
        'postsnap_sent': postsnap_sent
    })
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


def _parse_nfl_pro_play_data(play_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse NFL Pro play data into presnap and postsnap structures.
    
    NFL Pro provides rich data including:
    - offense.personnel, offense.offenseFormation
    - defense.personnel, defense.defendersInTheBox, defense.numberOfPassRushers
    - defense.coverageType, defense.manZoneType
    - passInfo.timeToThrow, passInfo.airYards, passInfo.wasPressure
    - recInfo.route
    - startGameClock, endGameClock (for play duration)
    """
    offense = play_data.get('offense', {}) or {}
    defense = play_data.get('defense', {}) or {}
    pass_info = play_data.get('passInfo', {}) or {}
    rec_info = play_data.get('recInfo', {}) or {}
    
    # Calculate play duration from game clocks
    start_clock = play_data.get('startGameClock', '')
    end_clock = play_data.get('endGameClock', '')
    play_duration = 5  # Default
    
    if start_clock and end_clock:
        try:
            def clock_to_seconds(clock_str):
                parts = clock_str.split(':')
                return int(parts[0]) * 60 + int(parts[1]) if len(parts) == 2 else 0
            
            start_secs = clock_to_seconds(start_clock)
            end_secs = clock_to_seconds(end_clock)
            play_duration = max(1, start_secs - end_secs)
        except (ValueError, IndexError):
            pass
    
    # Check for big play
    play_desc = play_data.get('playDescription', '')
    import re
    yards_match = re.search(r'for (\d+) yard', play_desc)
    yards = int(yards_match.group(1)) if yards_match else 0
    
    is_big_play = (
        play_data.get('isBigPlay', False) or
        play_data.get('isScoring', False) or
        yards >= 15
    )
    
    # Determine play type for coverage display
    play_type = play_data.get('playType', '').lower()
    is_pass_play = 'pass' in play_type
    is_run_play = 'rush' in play_type or 'run' in play_type
    is_special_teams = any(x in play_type for x in ['kick', 'punt', 'xp', 'fg', 'two_point'])

    # Format coverage type nicely
    coverage = defense.get('coverageType', '')
    if coverage:
        coverage = coverage.replace('COVER_', 'Cover ').replace('_', ' ')

    man_zone = defense.get('manZoneType', '')
    if man_zone:
        man_zone = 'Man' if 'MAN' in man_zone else 'Zone' if 'ZONE' in man_zone else ''

    # Build coverage display - show descriptive text for all play types
    if coverage:
        coverage_display = f"{coverage} ({man_zone})" if man_zone else coverage
    elif is_run_play:
        coverage_display = "Run Play"
    elif is_special_teams:
        coverage_display = "Special Teams"
    elif is_pass_play:
        # Use man/zone info if available, otherwise indicate pass play
        coverage_display = man_zone if man_zone else "Pass Play"
    else:
        # Fallback based on play description
        desc = play_data.get('playDescription', '').lower()
        if 'scramble' in desc:
            coverage_display = "Scramble"
        elif 'sack' in desc:
            coverage_display = "Sack"
        elif 'pass' in desc or 'incomplete' in desc:
            coverage_display = "Pass Play"
        else:
            coverage_display = "Run Play"

    # Skip presnap for special teams plays (field goals, punts, kickoffs)
    # These don't have meaningful offensive formation/personnel data
    presnap_data = None
    if not is_special_teams:
        presnap_data = {
            'offense': {
                'personnel': offense.get('personnel', ''),
                'formation': offense.get('offenseFormation', ''),
            },
            'defense': {
                'personnel': defense.get('personnel', ''),
                'box': defense.get('defendersInTheBox', 0),
            },
            'playDuration': play_duration,
        }

    # Also skip postsnap for special teams
    if is_special_teams:
        return {
            'presnap': None,
            'postsnap': None,
        }

    return {
        'presnap': presnap_data,
        'postsnap': {
            'offense': {
                'personnel': offense.get('personnel', ''),
                'formation': offense.get('offenseFormation', ''),
            },
            'defense': {
                'personnel': defense.get('personnel', ''),
                'coverage': coverage_display,
                'rushers': defense.get('numberOfPassRushers', 0),
                'box': defense.get('defendersInTheBox', 0),
            },
            'route': rec_info.get('route', ''),
            'timeToThrow': pass_info.get('timeToThrow', 0),
            'airYards': pass_info.get('airYards', 0),
            'wasPressure': pass_info.get('wasPressure', False),
            'yards': yards,
            'isBigPlay': is_big_play,
            'isScoring': play_data.get('isScoring', False),
            'playType': play_data.get('playType', ''),
            'playDuration': play_duration,
        }
    }


def _build_espn_postsnap(description: str, state: Dict[str, Any], change: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Build a simplified post-snap analysis from ESPN play description.
    
    ESPN doesn't have detailed coverage/route info, but we can extract:
    - Play type (run/pass)
    - Yards gained
    - Result (incomplete, sack, first down, touchdown)
    - Key player involved
    """
    import re
    
    if not description:
        return None
    
    desc_upper = description.upper()
    
    # Determine play type
    if 'PASS' in desc_upper or 'INCOMPLETE' in desc_upper or 'SACKED' in desc_upper:
        play_type = 'pass'
    elif 'PUNT' in desc_upper or 'KICKS' in desc_upper or 'FIELD GOAL' in desc_upper:
        play_type = 'special'
        return None  # Skip special teams for post-snap analysis
    else:
        play_type = 'run'
    
    # Extract yards
    yards = 0
    yards_match = re.search(r'FOR (\d+) YARD', desc_upper)
    if yards_match:
        yards = int(yards_match.group(1))
    elif 'NO GAIN' in desc_upper:
        yards = 0
    elif 'LOSS OF' in desc_upper:
        loss_match = re.search(r'LOSS OF (\d+)', desc_upper)
        if loss_match:
            yards = -int(loss_match.group(1))
    
    # Determine result
    result = 'gain'
    if 'INCOMPLETE' in desc_upper:
        result = 'incomplete'
        yards = 0
    elif 'SACKED' in desc_upper:
        result = 'sack'
    elif 'TOUCHDOWN' in desc_upper:
        result = 'touchdown'
    elif 'INTERCEPTION' in desc_upper or 'INTERCEPTED' in desc_upper:
        result = 'interception'
    elif 'FUMBLE' in desc_upper:
        result = 'fumble'
    elif 'FIRST DOWN' in desc_upper or yards >= state.get('distance', 10):
        result = 'first_down'
    
    # Check for big play
    is_big = yards >= 15 or result in ['touchdown', 'interception', 'fumble']
    
    # Get home/away for display
    home_abbr = state.get('home_team', {}).get('abbreviation', 'HOME')
    away_abbr = state.get('away_team', {}).get('abbreviation', 'AWAY')
    possession = state.get('possession', home_abbr)
    defending = away_abbr if possession == home_abbr else home_abbr
    
    # Build display-friendly result text
    result_text = {
        'gain': f"{yards} yard gain" if yards > 0 else "No gain",
        'incomplete': "Incomplete pass",
        'sack': f"Sack for {abs(yards)} yard loss" if yards < 0 else "Sack",
        'touchdown': "TOUCHDOWN!",
        'interception': "INTERCEPTION!",
        'fumble': "FUMBLE!",
        'first_down': f"{yards} yards - First down!",
    }.get(result, f"{yards} yards")

    # Extract formation from ESPN description like "(Shotgun)" or "(No Huddle, Shotgun)"
    formation = ''
    formation_match = re.search(r'\(([^)]+)\)', description)
    if formation_match:
        formation_text = formation_match.group(1)
        if any(f in formation_text.upper() for f in ['SHOTGUN', 'PISTOL', 'SINGLEBACK', 'I-FORM', 'EMPTY']):
            formation = formation_text

    return {
        'playType': play_type,
        'result': result,
        'resultText': result_text,
        'yards': yards,
        'isBigPlay': is_big,
        'isScoring': result == 'touchdown',
        'possession': possession,
        'defending': defending,
        'offense': {
            'personnel': '',  # Not available from ESPN
            'formation': formation,  # Extracted from description
            'route': '',
            'timeToThrow': 0,
        },
        'defense': {
            'personnel': '',  # Not available from ESPN
            'coverage': 'Run Play' if play_type == 'run' else '',  # ESPN doesn't have coverage data
            'rushers': 0,
        },
        'route': '',  # ESPN doesn't have route info
        'timeToThrow': 0,  # ESPN doesn't have timing data
        'description': description[:100],
    }


def _build_preplay_data_from_state(state: Dict[str, Any], change: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Build pre-play data from ESPN/simulator state for the upcoming play.
    
    Parses formation from ESPN play descriptions like "(Shotgun)" or "(No Huddle, Shotgun)".
    Personnel is estimated based on situation since ESPN doesn't provide it.
    """
    if not state:
        return None
    
    # Extract down/distance from state
    down = state.get('down', 1)
    yards_to_go = state.get('distance', 10)
    
    # Get yard line info
    yard_line = state.get('possession_yardline', '')
    if not yard_line:
        # Try to construct from other fields
        possession_team = state.get('possession', '')
        yard_number = state.get('yardline', 50)
        if possession_team and yard_number:
            yard_line = f"{possession_team} {yard_number}"
    
    # Determine if red zone
    is_redzone = state.get('in_redzone', False)
    if not is_redzone and yard_line:
        try:
            parts = yard_line.split()
            if len(parts) >= 2:
                yard_num = int(parts[-1])
                if yard_num <= 20 and not 'own' in yard_line.lower():
                    is_redzone = True
        except (ValueError, IndexError):
            pass
    
    # === PARSE FORMATION FROM PLAY DESCRIPTION ===
    # ESPN provides formation in parentheses, e.g., "(Shotgun)", "(No Huddle, Shotgun)"
    play_desc = change.get('description', '') or state.get('last_play', '')
    
    # Formation mapping from ESPN terms to our terms
    formation_map = {
        'shotgun': 'SHOTGUN',
        'under center': 'UNDER_CENTER',
        'pistol': 'PISTOL',
        'wildcat': 'WILDCAT',
        'empty': 'EMPTY',
        'i-form': 'I_FORM',
        'singleback': 'SINGLEBACK',
        'jumbo': 'JUMBO',
        'goal line': 'GOAL_LINE',
    }
    
    # Extract formation from parentheses at start of play
    off_formation = None
    no_huddle = False
    
    import re
    paren_match = re.match(r'\(([^)]+)\)', play_desc)
    if paren_match:
        paren_content = paren_match.group(1).lower()
        
        # Check for no huddle
        if 'no huddle' in paren_content:
            no_huddle = True
        
        # Find formation
        for espn_term, our_term in formation_map.items():
            if espn_term in paren_content:
                off_formation = our_term
                break
    
    # Default formation if not found
    if not off_formation:
        off_formation = 'SHOTGUN'  # Most common modern formation
    
    # === ESTIMATE PERSONNEL BASED ON SITUATION ===
    # ESPN doesn't provide personnel, so we estimate based on context
    if is_redzone and yards_to_go <= 3:
        off_personnel = '2 RB, 2 TE, 1 WR'  # 22 personnel - goal line
        defenders_in_box = 8
    elif off_formation == 'JUMBO' or off_formation == 'GOAL_LINE':
        off_personnel = '2 RB, 2 TE, 1 WR'  # Heavy package
        defenders_in_box = 8
    elif off_formation == 'EMPTY':
        off_personnel = '1 RB, 0 TE, 4 WR'  # 10 personnel
        defenders_in_box = 4
    elif down == 3 and yards_to_go >= 7:
        off_personnel = '1 RB, 1 TE, 3 WR'  # 11 personnel - passing
        defenders_in_box = 5
    elif down == 1 or yards_to_go <= 2:
        off_personnel = '1 RB, 2 TE, 2 WR'  # 12 personnel - balanced
        defenders_in_box = 7
    else:
        off_personnel = '1 RB, 1 TE, 3 WR'  # 11 personnel - default
        defenders_in_box = 6
    
    possession_team = state.get('possession', state.get('home_team', {}).get('abbreviation', 'OFF'))
    
    # Add no huddle indicator to formation if applicable
    formation_display = off_formation
    if no_huddle:
        formation_display = f"NO_HUDDLE_{off_formation}"
    
    return {
        'play_id': f"pre-{time.time():.0f}",
        'game_id': state.get('game_id', ''),
        'down': down,
        'yards_to_go': yards_to_go,
        'yard_line': yard_line or f'{possession_team} 35',
        'off_personnel': off_personnel,
        'off_formation': formation_display,
        'defenders_in_box': defenders_in_box,
        'is_redzone': is_redzone,
        'possession_team': possession_team,
        'no_huddle': no_huddle,
    }


def generate_pattern_insight(pattern: str, state: Dict[str, Any], generator) -> Optional[Insight]:
    """Generate an insight for a detected game flow pattern."""
    # Only generate pattern insights occasionally (roughly every 5 plays)
    if len(generator.play_history) % 5 != 0:
        return None
    
    templates = {
        'run_heavy': {
            'headlines': [
                'Running game taking over',
                'Ground and pound',
                'Establishing the run'
            ],
            'bodies': [
                'Heavy dose of rushing plays in this sequence.',
                'They\'re committed to running the ball right now.',
                'Running clock, controlling tempo.'
            ]
        },
        'pass_heavy': {
            'headlines': [
                'Airing it out',
                'Pass-first approach',
                'Dropping back often'
            ],
            'bodies': [
                'Lots of passing attempts recently.',
                'Attacking through the air.',
                'Could be playing from behind or building a lead quickly.'
            ]
        },
        'hot_streak': {
            'headlines': [
                'Offense is rolling',
                'Moving the chains',
                'Finding a rhythm'
            ],
            'bodies': [
                'Positive yards on every recent play.',
                'Defense can\'t get a stop.',
                'This drive has momentum.'
            ]
        },
        'stalled': {
            'headlines': [
                'Offense stalling',
                'Tough sledding',
                'Defense digging in'
            ],
            'bodies': [
                'Minimal gains on recent plays.',
                'Hard to move the ball right now.',
                'May need to change something up.'
            ]
        },
        'moving_well': {
            'headlines': [
                'Consistent gains',
                'Methodical drive',
                'Chunk plays adding up'
            ],
            'bodies': [
                'Several solid gains in a row.',
                'Moving the ball efficiently.',
                'Defense is on its heels.'
            ]
        }
    }
    
    if pattern not in templates:
        return None
    
    template = templates[pattern]
    headline, body = generator.select_varied_headline(
        template['headlines'], template['bodies'], {}
    )
    
    return Insight(
        id=str(uuid.uuid4())[:8],
        insight_type='game_flow',
        priority=5,
        timing='post_play',
        headline=headline,
        body=body,
        ttl=30
    )


def generate_spotlight_insight(spotlight: Dict[str, Any], state: Dict[str, Any]) -> Optional[Insight]:
    """Generate a player spotlight insight."""
    import random
    
    player = spotlight.get('player', 'Player')
    spotlight_type = spotlight.get('type', '')
    
    if spotlight_type == 'receiver':
        yards = spotlight.get('yards', 0)
        receptions = spotlight.get('receptions', 0)
        headlines = [
            f'🌟 {player} heating up',
            f'{player} having a game',
            f'Big day for {player}'
        ]
        bodies = [
            f'{receptions} catches for {yards} yards so far.',
            f'{player} is the go-to target today. {yards} receiving yards.',
            f'Keep an eye on {player}—already at {yards} yards.'
        ]
    elif spotlight_type == 'rusher':
        yards = spotlight.get('yards', 0)
        carries = spotlight.get('carries', 0)
        headlines = [
            f'🌟 {player} pounding the rock',
            f'{player} running hard',
            f'Ground game: {player}'
        ]
        bodies = [
            f'{carries} carries for {yards} yards.',
            f'{player} eating up yards on the ground.',
            f'The run game is going through {player}.'
        ]
    elif spotlight_type == 'passer':
        yards = spotlight.get('yards', 0)
        comp = spotlight.get('completions', 0)
        att = spotlight.get('attempts', 0)
        headlines = [
            f'🌟 {player} slinging it',
            f'{player} in rhythm',
            f'QB {player} on fire'
        ]
        bodies = [
            f'{comp}/{att} for {yards} yards.',
            f'{player} is dealing today. {yards} passing yards.',
            f'The offense is flowing through {player}\'s arm.'
        ]
    elif spotlight_type == 'multi_td':
        tds = spotlight.get('touchdowns', 0)
        headlines = [
            f'🌟 {player}: {tds} TDs!',
            f'{player} finding the end zone',
            f'Multi-score game for {player}'
        ]
        bodies = [
            f'{tds} touchdowns and counting.',
            f'{player} is the star of this game.',
            f'Fantasy owners loving {player} right now.'
        ]
    else:
        return None
    
    return Insight(
        id=str(uuid.uuid4())[:8],
        insight_type='player_spotlight',
        priority=6,
        timing='stoppage',
        headline=random.choice(headlines),
        body=random.choice(bodies),
        ttl=45
    )


@app.route('/query', methods=['POST'])
def handle_query():
    """Handle user question."""
    data = request.get_json() or {}
    question = data.get('question', '')

    if not question:
        return jsonify({
            'status': 'error',
            'message': 'No question provided'
        }), 400

    logger.info(f"User question: {question}")

    # Track question
    session_data['user_questions'].append({
        'question': question,
        'timestamp': datetime.now().isoformat()
    })

    # Get current game state for context
    try:
        state_response = requests.get(f"{GAME_STATE_URL}/state", timeout=5)
        if state_response.status_code == 200:
            state = state_response.json().get('state', {})
        else:
            state = {}
    except Exception:
        state = {}

    # Generate answer using LLM
    context = {'state': state, 'change': {}}
    answer = llm_client.generate_insight(context, question)

    if answer:
        return jsonify({
            'status': 'ok',
            'answer': answer,
            'context': ''
        })
    else:
        return jsonify({
            'status': 'ok',
            'answer': "I'm having trouble generating an answer right now. Try asking again in a moment.",
            'context': ''
        })


@app.route('/explain_play', methods=['POST'])
def explain_play():
    """Explain a specific play."""
    data = request.get_json() or {}
    play_description = data.get('play_description')

    # Get current game state
    try:
        state_response = requests.get(f"{GAME_STATE_URL}/state", timeout=5)
        if state_response.status_code == 200:
            state = state_response.json().get('state', {})
        else:
            state = {}
    except Exception:
        state = {}

    # Get most recent play if no description provided
    if not play_description:
        recent_plays = state.get('recent_plays', [])
        if recent_plays:
            play_description = recent_plays[0].get('description', '')

    if not play_description:
        return jsonify({
            'status': 'error',
            'message': 'No play to explain'
        }), 400

    # Generate explanation
    context = {
        'state': state,
        'change': {'change_type': 'explain_play', 'description': play_description}
    }

    explanation = llm_client.generate_insight(context, f"Explain this play: {play_description}")

    return jsonify({
        'status': 'ok',
        'play': play_description,
        'explanation': explanation or 'Unable to generate explanation',
        'strategic_context': '',
        'what_to_watch': ''
    })


@app.route('/session_summary', methods=['GET'])
def get_session_summary():
    """Get summary of current session."""
    return jsonify({
        'status': 'ok',
        'game_id': session_data['game_id'],
        'session_start': session_data['session_start'],
        'total_insights': len(session_data['insights_delivered']),
        'by_type': _count_by_type(session_data['insights_delivered']),
        'key_explanations': session_data['insights_delivered'][-5:],
        'concepts_introduced': [],
        'user_questions': session_data['user_questions']
    })


def _count_by_type(insights: List[Dict]) -> Dict[str, int]:
    """Count insights by type."""
    counts: Dict[str, int] = {}
    for insight in insights:
        insight_type = insight.get('type', 'unknown')
        counts[insight_type] = counts.get(insight_type, 0) + 1
    return counts


@app.route('/game/switch', methods=['POST'])
def switch_game():
    """Switch to a different game, resetting session state and loading insights."""
    global session_data

    data = request.get_json() or {}
    new_game_id = data.get('game_id')
    nfl_pro_uuid = data.get('nfl_pro_uuid', '')
    home_team = data.get('home_team', '')
    away_team = data.get('away_team', '')
    week = data.get('week')

    if not new_game_id:
        return jsonify({'status': 'error', 'message': 'game_id required'}), 400

    logger.info(f"Switching game from {session_data.get('game_id')} to {new_game_id}")

    # If team info not provided, try to fetch from ESPN API
    if not home_team or not away_team or not week:
        try:
            espn_url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={new_game_id}"
            resp = requests.get(espn_url, timeout=5, verify=False)
            if resp.status_code == 200:
                espn_data = resp.json()
                # Get teams from boxscore
                boxscore = espn_data.get('boxscore', {})
                teams_data = boxscore.get('teams', [])
                for t in teams_data:
                    team_info = t.get('team', {})
                    if t.get('homeAway') == 'home':
                        home_team = home_team or team_info.get('abbreviation', '')
                    elif t.get('homeAway') == 'away':
                        away_team = away_team or team_info.get('abbreviation', '')
                # Get week from header
                header = espn_data.get('header', {})
                week_info = header.get('week', 18)  # Default to week 18
                week = week or week_info
                logger.info(f"Fetched from ESPN: {away_team} @ {home_team}, Week {week}")
        except Exception as e:
            logger.warning(f"Could not fetch ESPN game details: {e}")

    # Try to get NFL Pro UUID from mapping file if not provided
    if not nfl_pro_uuid:
        try:
            mapping_path = Path('/data/espn_nfl_pro_mapping.json')
            if mapping_path.exists():
                with open(mapping_path, 'r') as f:
                    mapping = json.load(f)
                nfl_pro_uuid = mapping.get('espn_to_nfl_pro', {}).get(str(new_game_id), '')
                if nfl_pro_uuid:
                    logger.info(f"Found NFL Pro UUID: {nfl_pro_uuid[:8]}...")
        except Exception as e:
            logger.debug(f"Could not load mapping: {e}")

    # Reset session data for new game
    session_data = {
        'game_id': new_game_id,
        'nfl_pro_uuid': nfl_pro_uuid,
        'home_abbr': home_team.upper() if home_team else '',
        'away_abbr': away_team.upper() if away_team else '',
        'week': week,
        'session_start': datetime.now().isoformat(),
        'insights_delivered': [],
        'breaks_detected': [],
        'player_spotlights': [],
        'user_questions': [],
        'nfl_pro_insights_loaded': False
    }

    # Set current game teams for insight filtering
    if home_team and away_team and nfl_pro_narratives and hasattr(nfl_pro_narratives, 'set_current_game_teams'):
        nfl_pro_narratives.set_current_game_teams([home_team.upper(), away_team.upper()])

    # Set current game ID for tiered insight selection
    if nfl_pro_uuid and nfl_pro_narratives and hasattr(nfl_pro_narratives, 'set_current_game_id'):
        nfl_pro_narratives.set_current_game_id(nfl_pro_uuid)

    # Load NFL Pro insights for new game with proper team filtering
    insights_loaded = 0
    if NFL_PRO_NARRATIVES_AVAILABLE and load_narrative_insights:
        try:
            insights_loaded = load_narrative_insights(
                game_uuid=nfl_pro_uuid or new_game_id,
                home_team=home_team,
                away_team=away_team,
                week=int(week) if week else None
            )
            session_data['nfl_pro_insights_loaded'] = insights_loaded > 0
            logger.info(f"✅ Loaded {insights_loaded} NFL Pro insights for {away_team} @ {home_team}")
        except Exception as e:
            logger.warning(f"Could not load NFL Pro insights: {e}")

    # Reset insight generator for new game
    if insight_generator:
        insight_generator.reset_for_new_game()

    # Notify connected clients about game switch
    delivery_manager.broadcast_insight(Insight(
        id=str(uuid.uuid4())[:8],
        insight_type='system',
        priority=5,
        timing='immediate',
        headline='Game Switched',
        body=f'Now following {away_team} @ {home_team}' if away_team and home_team else f'Now following game {new_game_id}',
        ttl=30
    ))

    return jsonify({
        'status': 'ok',
        'message': f'Switched to {away_team} @ {home_team}' if away_team and home_team else f'Switched to game {new_game_id}',
        'nfl_pro_insights_loaded': session_data.get('nfl_pro_insights_loaded', False),
        'insights_count': insights_loaded,
        'home_team': home_team,
        'away_team': away_team,
        'week': week
    })


@app.route('/debug/insight-log', methods=['GET'])
def get_insight_log():
    """Get the log of served insights with tier information."""
    if not nfl_pro_narratives or not hasattr(nfl_pro_narratives, 'get_insight_log'):
        return jsonify({'status': 'error', 'message': 'No insight log available'}), 404

    log = nfl_pro_narratives.get_insight_log()
    return jsonify({
        'status': 'ok',
        'count': len(log),
        'insights': log
    })


@sock.route('/ws')
def websocket(ws):
    """WebSocket endpoint for companion UI."""
    logger.info("Client connected via WebSocket")
    delivery_manager.connected_clients.append(ws)

    # Send welcome message
    ws.send(json.dumps({
        'type': 'connected',
        'message': 'Connected to Auto-Madden Insight Engine'
    }))

    try:
        while True:
            message = ws.receive()
            if message is None:
                break

            try:
                data = json.loads(message)
                msg_type = data.get('type', '')

                if msg_type == 'start':
                    # Forward start request to game-state-service
                    query = data.get('query', '')
                    try:
                        response = requests.post(
                            f"{GAME_STATE_URL}/start",
                            json={'team': query},
                            timeout=10
                        )
                        result = response.json()
                        ws.send(json.dumps({
                            'type': 'session_started',
                            'data': result
                        }))
                    except Exception as e:
                        ws.send(json.dumps({
                            'type': 'error',
                            'message': f'Failed to start session: {e}'
                        }))

                elif msg_type == 'query':
                    # Handle user question
                    question = data.get('text', '')
                    context = {'state': {}, 'change': {}}
                    answer = llm_client.generate_insight(context, question)
                    ws.send(json.dumps({
                        'type': 'response',
                        'data': {
                            'question': question,
                            'answer': answer or 'Unable to answer right now.'
                        }
                    }))

                elif msg_type == 'stop':
                    try:
                        requests.post(f"{GAME_STATE_URL}/stop", timeout=5)
                    except Exception:
                        pass
                    ws.send(json.dumps({
                        'type': 'session_ended',
                        'message': 'Session ended'
                    }))

            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received: {message}")

    except Exception as e:
        logger.error(f"WebSocket error: {e}")

    finally:
        if ws in delivery_manager.connected_clients:
            delivery_manager.connected_clients.remove(ws)
        logger.info("Client disconnected")


# User preferences endpoint

@app.route('/preferences', methods=['GET'])
def get_preferences():
    """Get current user preferences."""
    global user_preferences
    return jsonify({
        'status': 'ok',
        'preferences': user_preferences
    })


@app.route('/preferences', methods=['POST'])
def set_preferences():
    """Set user preferences for pre-play metadata display."""
    global user_preferences, pre_play_service_instance
    
    data = request.get_json() or {}
    user_preferences = {
        'personnel': data.get('personnel', 'always'),
        'formation': data.get('formation', 'always'),
        'defense': data.get('defense', 'sometimes'),
    }
    
    # Update the pre-play service if available
    if PRE_PLAY_SERVICE_AVAILABLE and pre_play_service_instance:
        try:
            freq_map = {
                'always': MetadataFrequency.ALWAYS,
                'often': MetadataFrequency.OFTEN,
                'sometimes': MetadataFrequency.SOMETIMES,
                'never': MetadataFrequency.NEVER,
            }
            pre_play_service_instance.preferences.personnel = freq_map.get(user_preferences['personnel'], MetadataFrequency.ALWAYS)
            pre_play_service_instance.preferences.formation = freq_map.get(user_preferences['formation'], MetadataFrequency.ALWAYS)
            # Defense maps to the 'tendency' preference in the service
            pre_play_service_instance.preferences.tendency = freq_map.get(user_preferences['defense'], MetadataFrequency.SOMETIMES)
        except Exception as e:
            logger.warning(f"Could not update pre-play service preferences: {e}")
    
    logger.info(f"User preferences updated: {user_preferences}")
    return jsonify({
        'status': 'ok',
        'preferences': user_preferences
    })


# Test insight endpoint (for demos)

@app.route('/test_insight', methods=['POST'])
def test_insight():
    """Send a test insight to all connected clients."""
    data = request.get_json() or {}
    
    headline = data.get('headline', 'Test Insight')
    body = data.get('body', 'This is a test insight from the insight engine.')
    
    insight = Insight(
        id=str(uuid.uuid4())[:8],
        insight_type='test',
        priority=7,
        timing='immediate',
        headline=headline,
        body=body,
        ttl=120
    )
    
    # Broadcast immediately
    delivery_manager.broadcast_insight(insight)
    
    logger.info(f"Test insight sent: {headline}")
    return jsonify({
        'status': 'ok',
        'headline': headline
    })


# Pre-play metadata endpoint (for testing)

@app.route('/preplay/test', methods=['POST'])
def test_preplay():
    """Test endpoint to send a pre-play metadata broadcast."""
    if not PRE_PLAY_SERVICE_AVAILABLE or not pre_play_service_instance:
        return jsonify({'status': 'error', 'message': 'Pre-play service not available'}), 503
    
    data = request.get_json() or {}
    
    # Sample play data for testing
    test_play = data.get('play', {
        'play_id': 'test-1',
        'down': 2,
        'yards_to_go': 7,
        'yard_line': 'SEA 35',
        'off_personnel': '1 RB, 1 TE, 3 WR',
        'off_formation': 'SHOTGUN',
        'defenders_in_box': 6,
        'is_redzone': False,
        'possession_team': 'SEA',
    })
    
    preplay_data = process_pre_play(test_play)
    delivery_manager.broadcast_preplay(preplay_data)
    
    return jsonify({
        'status': 'ok',
        'preplay': preplay_data
    })


# Broadcast delay control endpoints

@app.route('/delay', methods=['GET'])
def get_delay():
    """Get current broadcast delay settings."""
    return jsonify({
        'status': 'ok',
        **delay_buffer.get_status()
    })


@app.route('/delay', methods=['POST'])
def set_delay():
    """Set broadcast delay in seconds."""
    data = request.get_json() or {}
    delay = data.get('delay_seconds')
    
    if delay is not None:
        delay_buffer.set_delay(float(delay))
        return jsonify({
            'status': 'ok',
            'message': f'Delay set to {delay_buffer.delay_seconds:.1f} seconds',
            **delay_buffer.get_status()
        })
    else:
        return jsonify({
            'status': 'error',
            'message': 'delay_seconds required'
        }), 400


@app.route('/delay/adjust', methods=['POST'])
def adjust_delay():
    """Adjust broadcast delay by a delta."""
    data = request.get_json() or {}
    delta = data.get('delta_seconds', 0)
    
    delay_buffer.adjust_delay(float(delta))
    return jsonify({
        'status': 'ok',
        'message': f'Delay adjusted to {delay_buffer.delay_seconds:.1f} seconds',
        **delay_buffer.get_status()
    })


@app.route('/delay/sync', methods=['POST'])
def sync_delay():
    """
    Record a sync point for delay calibration.
    User clicks when they see an event on TV.
    """
    data = request.get_json() or {}
    event_type = data.get('event_type', 'score')
    event_time = data.get('event_time', time.time())
    
    delay_buffer.record_sync_point(event_type, float(event_time))
    return jsonify({
        'status': 'ok',
        'message': f'Sync recorded. Delay calibrated to {delay_buffer.delay_seconds:.1f} seconds',
        **delay_buffer.get_status()
    })


@app.route('/insights/process', methods=['POST', 'OPTIONS'])
def process_insights():
    """
    Process insights for a specific week if not already processed.
    Called before starting a replay to ensure insights are ready.
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    data = request.get_json() or {}
    week = data.get('week')
    season = data.get('season', 2025)
    home_team = data.get('home_team', '').upper()
    away_team = data.get('away_team', '').upper()
    
    if not week:
        response = jsonify({'status': 'error', 'message': 'week required'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 400
    
    logger.info(f"📊 Processing insights for Week {week}, {away_team} @ {home_team}")
    
    # Check if processed insights exist
    import os
    processed_file = f"../data/processed_insights/week_{week}_processed.json"
    if os.path.exists(processed_file):
        # Already processed
        try:
            import json
            with open(processed_file) as f:
                data = json.load(f)
            count = len(data.get('insights', []))
            
            # Filter to game teams
            game_teams = [t for t in [home_team, away_team] if t]
            if game_teams:
                insights = data.get('insights', [])
                team_insights = [i for i in insights if any(
                    t in (i.get('teams_mentioned') or []) for t in game_teams
                )]
                count = len(team_insights)
            
            logger.info(f"✅ Week {week} already processed: {count} insights for {game_teams}")
            response = jsonify({
                'status': 'ok',
                'message': f'Week {week} insights ready',
                'count': count,
                'already_processed': True
            })
            response.headers.add('Access-Control-Allow-Origin', '*')
            return response
        except Exception as e:
            logger.warning(f"Error reading processed file: {e}")
    
    # Need to process from raw database
    try:
        if NFL_PRO_NARRATIVES_AVAILABLE and nfl_pro_narratives:
            game_teams = [t for t in [home_team, away_team] if t]
            success = nfl_pro_narratives.load_from_db_by_week(int(week), game_teams)
            
            if success:
                count = nfl_pro_narratives.get_unserved_count()
                logger.info(f"✅ Loaded {count} insights from raw DB for Week {week}")
                response = jsonify({
                    'status': 'ok',
                    'message': f'Loaded {count} insights for Week {week}',
                    'count': count,
                    'already_processed': False
                })
            else:
                response = jsonify({
                    'status': 'ok',
                    'message': f'No insights found for Week {week}',
                    'count': 0,
                    'already_processed': False
                })
        else:
            response = jsonify({
                'status': 'error',
                'message': 'NFL Pro integration not available'
            })
        
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
        
    except Exception as e:
        logger.error(f"Error processing insights: {e}")
        response = jsonify({
            'status': 'error',
            'message': str(e)
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500


@app.route('/insights/status', methods=['GET'])
def insights_status():
    """Check status of processed insights for a week."""
    week = request.args.get('week')

    if not week:
        return jsonify({'status': 'error', 'message': 'week required'}), 400

    import os
    processed_file = f"../data/processed_insights/week_{week}_processed.json"

    if os.path.exists(processed_file):
        try:
            import json
            with open(processed_file) as f:
                data = json.load(f)
            return jsonify({
                'status': 'ok',
                'processed': True,
                'count': len(data.get('insights', []))
            })
        except:
            pass

    return jsonify({
        'status': 'ok',
        'processed': False,
        'count': 0
    })


# NFL Pro Session Management
CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '/Volumes/main-drive/ai-PA/auto-madden/credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'
NFL_PRO_STATE_FILE = BROWSER_STATES_PATH / 'nfl_pro_state.json'
NFL_TOKEN_REFRESH_URL = "https://api.nfl.com/identity/v3/token/refresh"
NFL_TOKEN_REFRESH_BUFFER_SECONDS = 300  # Refresh 5 minutes before expiry
NFL_SESSION_EXPIRY_HOURS = 1  # Session valid for 1 hour


@app.route('/api/nfl-pro/status', methods=['GET'])
def nfl_pro_status():
    """Check if we have a valid NFL Pro session, auto-refreshing if needed."""
    status = _check_nfl_pro_session()

    # If expired or about to expire, try auto-refresh
    if not status.get('authenticated') or status.get('needs_refresh'):
        refresh_result = _refresh_nfl_pro_token()
        if refresh_result.get('success'):
            status = _check_nfl_pro_session()
            status['refreshed'] = True

    response = jsonify(status)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


def _get_nfl_pro_token_info() -> dict:
    """Extract token info from stored session."""
    if not NFL_PRO_STATE_FILE.exists():
        return {}

    try:
        with open(NFL_PRO_STATE_FILE) as f:
            state = json.load(f)

        token_info = {}

        for origin in state.get('origins', []):
            for item in origin.get('localStorage', []):
                name = item.get('name', '')

                if name == 'nfl.refreshableToken.v3':
                    val = json.loads(item.get('value', '{}'))
                    raw = val.get('rawData', {})
                    token_info['accessToken'] = raw.get('accessToken')
                    token_info['refreshToken'] = raw.get('refreshToken')
                    token_info['exp'] = raw.get('exp')
                    token_info['clientId'] = raw.get('clientId')
                    token_info['clientKey'] = raw.get('clientKey')
                    token_info['deviceId'] = raw.get('deviceId')

                if name == 'nfl.refreshableToken.args.v3':
                    val = json.loads(item.get('value', '{}'))
                    token_info['clientSecret'] = val.get('clientSecret')
                    # These may not be in the v3 token
                    if not token_info.get('clientId'):
                        token_info['clientId'] = val.get('clientId')
                    if not token_info.get('clientKey'):
                        token_info['clientKey'] = val.get('clientKey')
                    if not token_info.get('deviceId'):
                        token_info['deviceId'] = val.get('deviceId')

        return token_info
    except Exception as e:
        logger.error(f"Error reading NFL Pro token info: {e}")
        return {}


def _check_nfl_pro_session() -> dict:
    """Check if NFL Pro session exists and is valid."""
    if not NFL_PRO_STATE_FILE.exists():
        return {
            'authenticated': False,
            'message': 'No session file found'
        }

    try:
        token_info = _get_nfl_pro_token_info()

        if not token_info.get('accessToken'):
            return {
                'authenticated': False,
                'message': 'No access token found'
            }

        # Check token expiry from the actual token
        exp = token_info.get('exp')
        if exp:
            expiry_dt = datetime.fromtimestamp(exp)
            now = datetime.now()

            if now > expiry_dt:
                return {
                    'authenticated': False,
                    'expired': True,
                    'needs_refresh': True,
                    'message': 'Token expired',
                    'expired_ago_minutes': (now - expiry_dt).total_seconds() / 60
                }

            # Check if we need to refresh soon
            refresh_at = expiry_dt - timedelta(seconds=NFL_TOKEN_REFRESH_BUFFER_SECONDS)
            if now > refresh_at:
                return {
                    'authenticated': True,
                    'needs_refresh': True,
                    'expiry': expiry_dt.isoformat(),
                    'expires_in_minutes': (expiry_dt - now).total_seconds() / 60
                }

            return {
                'authenticated': True,
                'expiry': expiry_dt.isoformat(),
                'expires_in_minutes': (expiry_dt - now).total_seconds() / 60,
                'has_refresh_token': bool(token_info.get('refreshToken'))
            }

        # No expiry info, assume valid
        return {
            'authenticated': True,
            'message': 'Token exists but no expiry info',
            'has_refresh_token': bool(token_info.get('refreshToken'))
        }

    except Exception as e:
        logger.error(f"Error checking NFL Pro session: {e}")
        return {
            'authenticated': False,
            'message': f'Error: {str(e)}'
        }


def _refresh_nfl_pro_token() -> dict:
    """Refresh the NFL Pro access token using the refresh token."""
    try:
        token_info = _get_nfl_pro_token_info()

        refresh_token = token_info.get('refreshToken')
        client_id = token_info.get('clientId')
        client_key = token_info.get('clientKey')
        client_secret = token_info.get('clientSecret')
        device_id = token_info.get('deviceId')

        if not all([refresh_token, client_id, client_key, client_secret, device_id]):
            missing = [k for k in ['refreshToken', 'clientId', 'clientKey', 'clientSecret', 'deviceId']
                      if not token_info.get(k)]
            return {
                'success': False,
                'message': f'Missing required credentials: {missing}'
            }

        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
            'X-Domain-Id': '100'
        }
        payload = {
            'refreshToken': refresh_token,
            'clientId': client_id,
            'clientKey': client_key,
            'clientSecret': client_secret,
            'deviceId': device_id
        }

        resp = requests.post(NFL_TOKEN_REFRESH_URL, json=payload, headers=headers, timeout=15)

        if resp.status_code == 200:
            new_token_data = resp.json()

            # Update the stored session file
            _update_nfl_pro_session(new_token_data)

            logger.info("NFL Pro token refreshed successfully")
            return {
                'success': True,
                'message': 'Token refreshed',
                'new_expiry': new_token_data.get('exp')
            }
        else:
            logger.error(f"NFL Pro token refresh failed: {resp.status_code} - {resp.text[:200]}")
            return {
                'success': False,
                'message': f'Refresh failed: {resp.status_code}'
            }

    except Exception as e:
        logger.error(f"Error refreshing NFL Pro token: {e}")
        return {
            'success': False,
            'message': str(e)
        }


def _update_nfl_pro_session(new_token_data: dict):
    """Update the stored NFL Pro session with new token data."""
    try:
        with open(NFL_PRO_STATE_FILE) as f:
            state = json.load(f)

        # Update the token in localStorage
        for origin in state.get('origins', []):
            for item in origin.get('localStorage', []):
                if item.get('name') == 'nfl.refreshableToken.v3':
                    val = json.loads(item.get('value', '{}'))
                    raw = val.get('rawData', {})

                    # Update with new token data
                    raw['accessToken'] = new_token_data.get('accessToken', raw.get('accessToken'))
                    raw['exp'] = new_token_data.get('exp', raw.get('exp'))
                    raw['expiresIn'] = new_token_data.get('expiresIn', raw.get('expiresIn'))
                    if new_token_data.get('refreshToken'):
                        raw['refreshToken'] = new_token_data['refreshToken']

                    val['rawData'] = raw
                    item['value'] = json.dumps(val)
                    break

        # Update timestamp
        state['timestamp'] = datetime.now().isoformat()
        state['last_refresh'] = datetime.now().isoformat()

        # Save updated state
        with open(NFL_PRO_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)

        logger.info("Updated NFL Pro session file with refreshed token")

    except Exception as e:
        logger.error(f"Error updating NFL Pro session file: {e}")


@app.route('/api/nfl-pro/session', methods=['POST', 'OPTIONS'])
def nfl_pro_session():
    """Receive and save NFL Pro session from companion UI."""
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response

    try:
        data = request.get_json()

        if not data:
            return jsonify({'status': 'error', 'message': 'No data provided'}), 400

        cookies = data.get('cookies', [])
        access_token = data.get('accessToken')
        local_storage = data.get('localStorage', {})  # From bookmarklet
        origin = data.get('origin', 'https://pro.nfl.com')
        timestamp = data.get('timestamp', int(datetime.now().timestamp() * 1000))

        if not cookies and not access_token and not local_storage:
            return jsonify({'status': 'error', 'message': 'No cookies, token, or localStorage provided'}), 400

        # Build state file in Playwright format
        state = {
            'cookies': [],
            'origins': []
        }

        # Convert cookies to Playwright format
        for cookie in cookies:
            if cookie.get('name') and cookie.get('value'):
                state['cookies'].append({
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': cookie.get('domain', '.nfl.com'),
                    'path': cookie.get('path', '/'),
                    'expires': cookie.get('expires', -1),
                    'httpOnly': cookie.get('httpOnly', False),
                    'secure': cookie.get('secure', True),
                    'sameSite': cookie.get('sameSite', 'None')
                })

        # Handle localStorage from bookmarklet (object format)
        if local_storage and isinstance(local_storage, dict):
            ls_items = [{'name': k, 'value': v} for k, v in local_storage.items()]
            state['origins'] = [{
                'origin': origin,
                'localStorage': ls_items
            }]
            logger.info(f"Received {len(ls_items)} localStorage items from bookmarklet")
        # Handle direct access token
        elif access_token:
            state['origins'] = [{
                'origin': 'https://pro.nfl.com',
                'localStorage': [{
                    'name': 'oidc.user:https://id.nfl.com:nfl-fantasy-web',
                    'value': json.dumps({'secret': access_token})
                }]
            }]

        # Add timestamp
        state['timestamp'] = datetime.fromtimestamp(timestamp / 1000).isoformat() if timestamp > 1e12 else datetime.now().isoformat()

        # Ensure directory exists
        NFL_PRO_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Save state file
        with open(NFL_PRO_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)

        logger.info(f"Saved NFL Pro session with {len(state['cookies'])} cookies")

        response = jsonify({
            'status': 'ok',
            'message': f"Saved {len(state['cookies'])} cookies",
            'expiry': (datetime.now() + timedelta(hours=NFL_SESSION_EXPIRY_HOURS)).isoformat()
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    except Exception as e:
        logger.error(f"Error saving NFL Pro session: {e}")
        response = jsonify({'status': 'error', 'message': str(e)})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500


@app.route('/api/nfl-pro/refresh', methods=['POST', 'OPTIONS'])
def nfl_pro_refresh():
    """Explicitly trigger a token refresh for NFL Pro."""
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response

    # Force a token refresh
    refresh_result = _refresh_nfl_pro_token()

    if refresh_result.get('success'):
        status = _check_nfl_pro_session()
        response = jsonify({
            'status': 'ok',
            'message': 'Token refreshed successfully',
            **status
        })
    else:
        response = jsonify({
            'status': 'error',
            'message': refresh_result.get('message', 'Refresh failed')
        })

    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


# NFL Pro plays fetching with Playwright
_nfl_pro_plays_cache: Dict[str, tuple] = {}  # game_uuid -> (plays, timestamp)
NFL_PRO_PLAYS_CACHE_TTL = 10  # 10 seconds cache - fetch fresh data for each play


def _get_matching_nfl_pro_play(state: Dict[str, Any], change: Dict[str, Any]) -> Optional[Dict]:
    """
    Auto-fetch NFL Pro plays and match the current ESPN play.

    Uses quarter + clock time to find the matching play from NFL Pro data.
    """
    import asyncio

    # Get NFL Pro UUID from session
    nfl_pro_uuid = session_data.get('nfl_pro_uuid')
    if not nfl_pro_uuid:
        return None

    # Get plays from cache or fetch
    if nfl_pro_uuid in _nfl_pro_plays_cache:
        cached_plays, cached_time = _nfl_pro_plays_cache[nfl_pro_uuid]
        if (datetime.now() - cached_time).total_seconds() < NFL_PRO_PLAYS_CACHE_TTL:
            plays = cached_plays
        else:
            plays = None
    else:
        plays = None

    if plays is None:
        try:
            plays = asyncio.run(_fetch_nfl_pro_plays(nfl_pro_uuid))
            if plays:
                _nfl_pro_plays_cache[nfl_pro_uuid] = (plays, datetime.now())
                logger.info(f"🏈 Fetched {len(plays)} NFL Pro plays for matching")
            else:
                logger.debug("No NFL Pro plays fetched")
                return None
        except Exception as e:
            logger.debug(f"Error fetching NFL Pro plays: {e}")
            return None

    if not plays:
        return None

    # Match by quarter + clock time
    quarter = state.get('quarter', 0)
    clock = state.get('clock', '')

    # Also try to get from change data
    if not clock:
        clock = change.get('clock', '')

    if not quarter or not clock:
        # Try matching by play description
        espn_desc = change.get('description', '').lower()
        if not espn_desc:
            return None

        # Find most recent play that matches description keywords
        for play in reversed(plays):
            nfl_desc = play.get('playDescription', '').lower()
            # Check for key player names or play types
            if any(word in nfl_desc for word in espn_desc.split()[:3] if len(word) > 3):
                logger.info(f"📊 Matched NFL Pro play by description: {nfl_desc[:50]}...")
                return play
        return None

    # Parse clock to seconds for comparison
    def clock_to_seconds(clock_str: str) -> int:
        try:
            parts = clock_str.split(':')
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            return 0
        except (ValueError, IndexError):
            return 0

    espn_seconds = clock_to_seconds(clock)

    # Extract clock from playDescription if not in clock field
    # NFL Pro format: "(14:47) B.Purdy pass..."
    import re

    def extract_clock_from_desc(play: Dict) -> str:
        desc = play.get('playDescription', '')
        match = re.search(r'^\((\d+:\d+)\)', desc)
        if match:
            return match.group(1)
        return play.get('endClock') or play.get('clock') or play.get('startClock', '')

    # Find best matching play (same quarter, closest clock time)
    best_match = None
    best_diff = float('inf')

    for play in plays:
        play_quarter = play.get('quarter', 0)
        play_clock = extract_clock_from_desc(play)

        if play_quarter != quarter:
            continue

        play_seconds = clock_to_seconds(play_clock)
        diff = abs(play_seconds - espn_seconds)

        # Clock should be within 45 seconds (plays take time, ESPN may be slightly delayed)
        if diff < best_diff and diff <= 45:
            best_diff = diff
            best_match = play

    if best_match:
        rushers = best_match.get('defense', {}).get('numberOfPassRushers', 0)
        coverage = best_match.get('defense', {}).get('coverageType', '')
        logger.info(f"📊 Matched NFL Pro play: Q{quarter} {clock} -> rushers={rushers}, coverage={coverage}")
        return best_match

    # Log why no match was found
    logger.warning(f"No NFL Pro match for Q{quarter} clock={clock} ({espn_seconds}s). ESPN: '{change.get('description', '')[:40]}'")
    if plays:
        sample = plays[-1]
        sample_clock = extract_clock_from_desc(sample)
        logger.warning(f"Latest NFL Pro play: Q{sample.get('quarter')} clock={sample_clock} '{sample.get('playDescription', '')[:50]}'")

    return None


@app.route('/api/nfl-pro/plays/<game_uuid>', methods=['GET'])
def nfl_pro_plays(game_uuid: str):
    """Fetch plays from NFL Pro API using Playwright browser context."""
    import asyncio
    from datetime import datetime

    # Check cache first
    if game_uuid in _nfl_pro_plays_cache:
        cached_plays, cached_time = _nfl_pro_plays_cache[game_uuid]
        if (datetime.now() - cached_time).total_seconds() < NFL_PRO_PLAYS_CACHE_TTL:
            logger.debug(f"Returning cached plays for {game_uuid[:8]}")
            return jsonify({
                'status': 'ok',
                'plays': cached_plays,
                'cached': True
            })

    try:
        plays = asyncio.run(_fetch_nfl_pro_plays(game_uuid))

        if plays:
            # Cache the result
            _nfl_pro_plays_cache[game_uuid] = (plays, datetime.now())
            return jsonify({
                'status': 'ok',
                'plays': plays,
                'count': len(plays),
                'cached': False
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'No plays found',
                'plays': []
            }), 404

    except Exception as e:
        logger.error(f"Error fetching NFL Pro plays: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'plays': []
        }), 500


async def _fetch_nfl_pro_plays(game_uuid: str) -> List[Dict]:
    """Fetch plays using stored Bearer token or Playwright fallback."""

    # First try direct API call with Bearer token (much faster than Playwright)
    plays = await _fetch_nfl_pro_plays_direct_api(game_uuid)
    if plays:
        return plays

    logger.info("Direct API failed, falling back to Playwright")
    return await _fetch_nfl_pro_plays_playwright(game_uuid)


async def _fetch_nfl_pro_plays_direct_api(game_uuid: str) -> List[Dict]:
    """Fetch plays using direct API call with Bearer token from saved session."""
    import aiohttp

    if not NFL_PRO_STATE_FILE.exists():
        logger.debug("No NFL Pro session file for direct API")
        return []

    try:
        with open(NFL_PRO_STATE_FILE) as f:
            state = json.load(f)
    except Exception as e:
        logger.warning(f"Error loading NFL Pro session: {e}")
        return []

    # Extract Bearer token from localStorage
    access_token = None
    for origin in state.get('origins', []):
        if 'nfl.com' in origin.get('origin', ''):
            for item in origin.get('localStorage', []):
                if item.get('name') == 'nfl.refreshableToken.v3':
                    try:
                        token_data = json.loads(item.get('value', '{}'))
                        access_token = token_data.get('rawData', {}).get('accessToken')
                    except:
                        pass
                    break
            break

    if not access_token:
        logger.debug("No Bearer token found for direct API")
        return []

    # Build cookies from session
    cookies = {}
    for cookie in state.get('cookies', []):
        if cookie.get('name') and cookie.get('value'):
            cookies[cookie['name']] = cookie['value']

    # Call NFL Pro plays API directly
    url = f"https://pro.nfl.com/api/secured/plays/playlist/game?gameId={game_uuid}"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15',
        'Accept': 'application/json',
        'Referer': f'https://pro.nfl.com/games/game/{game_uuid}/play-by-play',
        'Origin': 'https://pro.nfl.com',
    }

    try:
        async with aiohttp.ClientSession(cookies=cookies) as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    plays_raw = await resp.json()
                    logger.info(f"Direct API success: got {len(plays_raw.get('plays', []))} plays")
                    return _parse_raw_plays(plays_raw)
                else:
                    logger.warning(f"Direct API returned {resp.status}")
                    return []
    except Exception as e:
        logger.warning(f"Direct API error: {e}")
        return []


async def _fetch_nfl_pro_plays_playwright(game_uuid: str) -> List[Dict]:
    """Fetch plays using Playwright with user's Chrome profile for authentication."""
    from playwright.async_api import async_playwright
    import os
    import shutil
    import tempfile

    # Use user's Chrome profile for authentication (shares login with their browser)
    chrome_profile_path = os.path.expanduser("~/Library/Application Support/Google/Chrome")

    plays_raw = None

    async with async_playwright() as p:
        # Try to use Chrome profile - if Chrome is running, copy profile to temp location
        context = None
        temp_profile = None

        try:
            # First try direct access (works if Chrome is closed)
            context = await p.chromium.launch_persistent_context(
                chrome_profile_path,
                headless=True,
                channel='chrome',
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-first-run',
                    '--no-default-browser-check',
                ],
                timeout=10000,
            )
            logger.info("Using Chrome profile directly")
        except Exception as e:
            # Chrome is likely running - try copying critical files to temp profile
            logger.info(f"Chrome profile locked ({str(e)[:50]}...), copying cookies to temp profile")
            try:
                temp_profile = tempfile.mkdtemp(prefix='chrome_profile_')
                default_profile = os.path.join(chrome_profile_path, 'Default')

                # Copy only essential files for cookies/auth
                for filename in ['Cookies', 'Login Data', 'Web Data', 'Preferences', 'Local State']:
                    src = os.path.join(default_profile if filename != 'Local State' else chrome_profile_path, filename)
                    if os.path.exists(src):
                        dst_dir = os.path.join(temp_profile, 'Default') if filename != 'Local State' else temp_profile
                        os.makedirs(dst_dir, exist_ok=True)
                        shutil.copy2(src, os.path.join(dst_dir, filename))

                context = await p.chromium.launch_persistent_context(
                    temp_profile,
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled'],
                    timeout=10000,
                )
                logger.info("Using copied Chrome profile")
            except Exception as e2:
                logger.warning(f"Could not copy Chrome profile: {e2}, falling back to session file")
                if temp_profile and os.path.exists(temp_profile):
                    shutil.rmtree(temp_profile, ignore_errors=True)
                return await _fetch_nfl_pro_plays_from_session(game_uuid)

        if not context:
            return await _fetch_nfl_pro_plays_from_session(game_uuid)

        page = context.pages[0] if context.pages else await context.new_page()

        async def capture_plays(response):
            nonlocal plays_raw
            # Log all API calls for debugging
            if '/api/' in response.url:
                logger.debug(f"API response: {response.status} {response.url[:100]}")
            if 'plays/playlist' in response.url:
                logger.info(f"Plays API response: status={response.status}, url={response.url}")
                if response.status == 200:
                    try:
                        plays_raw = await response.json()
                        logger.info(f"Captured plays response from {response.url}")
                    except Exception as e:
                        logger.warning(f"Error parsing plays response: {e}")

        page.on('response', capture_plays)

        try:
            url = f"https://pro.nfl.com/games/game/{game_uuid}/play-by-play"
            logger.info(f"Navigating to {url}")
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)  # Wait for API calls

            # Debug: Log final URL and page state
            final_url = page.url
            logger.info(f"Final URL after navigation: {final_url}")
            if 'login' in final_url.lower() or final_url != url:
                logger.warning(f"Page redirected - may need fresh login")
        except Exception as e:
            logger.warning(f"Error navigating to NFL Pro: {e}")
        finally:
            await context.close()
            # Clean up temp profile if we created one
            if temp_profile and os.path.exists(temp_profile):
                shutil.rmtree(temp_profile, ignore_errors=True)

    if not plays_raw:
        logger.warning("No plays captured from NFL Pro")
        return []

    # Parse plays into structured format
    raw_plays = plays_raw.get('plays', plays_raw.get('playlist', []))
    parsed_plays = []

    for raw in raw_plays:
        try:
            if raw.get('playType') == 'GAME' or raw.get('play_type') == 'GAME':
                continue

            # Handle both nested (camelCase) and flat (snake_case) API formats
            offense = raw.get('offense', {}) or {}
            defense = raw.get('defense', {}) or {}
            pass_info = raw.get('passInfo', {}) or {}
            rec_info = raw.get('recInfo', {}) or {}

            # Get coverage - try nested first, then flat
            coverage = (
                defense.get('coverageType') or
                raw.get('coverage_type', '') or
                raw.get('coverageType', '')
            )
            if coverage:
                coverage = coverage.replace('COVER_', 'Cover ').replace('_', ' ')

            # Get man/zone - try nested first, then flat
            man_zone = (
                defense.get('manZoneType') or
                raw.get('man_zone', '') or
                raw.get('manZoneType', '')
            )
            if man_zone:
                man_zone = 'Man' if 'MAN' in man_zone.upper() else 'Zone' if 'ZONE' in man_zone.upper() else ''

            # Get pass info fields - try nested first, then flat
            time_to_throw = (
                pass_info.get('timeToThrow') or
                raw.get('time_to_throw') or
                raw.get('timeToThrow') or 0
            )
            air_yards = (
                pass_info.get('airYards') or
                raw.get('air_yards') or
                raw.get('airYards') or 0
            )
            was_pressure = (
                pass_info.get('wasPressure') or
                raw.get('was_pressure') or
                raw.get('wasPressure') or False
            )

            # Get route - try nested first, then flat
            route = (
                rec_info.get('route') or
                raw.get('route', '')
            )

            # Get defense info - try nested first, then flat
            defenders_in_box = (
                defense.get('defendersInTheBox') or
                raw.get('defenders_in_box') or
                raw.get('defendersInTheBox') or 0
            )
            pass_rushers = (
                defense.get('numberOfPassRushers') or
                raw.get('pass_rushers') or
                raw.get('numberOfPassRushers') or 0
            )

            # Get offense info - try nested first, then flat
            off_personnel = (
                offense.get('personnel') or
                raw.get('off_personnel') or
                raw.get('personnel', '')
            )
            off_formation = (
                offense.get('offenseFormation') or
                raw.get('off_formation') or
                raw.get('offenseFormation', '')
            )
            def_personnel = (
                defense.get('personnel') or
                raw.get('def_personnel', '')
            )

            play = {
                'playId': raw.get('playId') or raw.get('play_id', 0),
                'sequence': raw.get('sequence', 0),
                'quarter': raw.get('quarter', 0),
                'clock': raw.get('endClock') or raw.get('end_clock') or raw.get('startClock') or raw.get('start_clock', ''),
                'down': raw.get('down', 0),
                'distance': raw.get('yardsToGo') or raw.get('yards_to_go', 0),
                'yardLine': raw.get('yardLine') or raw.get('yard_line', ''),
                'possessionTeam': raw.get('possessionTeam') or raw.get('possession_team', ''),
                'playDescription': raw.get('playDescription') or raw.get('description', ''),
                'yardsGained': raw.get('yardsGained') or raw.get('yards_gained', 0),
                'offense': {
                    'personnel': off_personnel,
                    'offenseFormation': off_formation,
                },
                'defense': {
                    'personnel': def_personnel,
                    'defendersInTheBox': int(defenders_in_box) if defenders_in_box else 0,
                    'numberOfPassRushers': int(pass_rushers) if pass_rushers else 0,
                    'coverageType': coverage,
                    'manZoneType': man_zone,
                },
                'passInfo': {
                    'timeToThrow': float(time_to_throw) if time_to_throw else 0,
                    'airYards': float(air_yards) if air_yards else 0,
                    'wasPressure': bool(was_pressure),
                },
                'recInfo': {
                    'route': route,
                },
                'isRedzone': raw.get('isRedzone') or raw.get('is_redzone', False),
            }
            parsed_plays.append(play)
        except Exception as e:
            logger.debug(f"Error parsing play: {e}")

    logger.info(f"Parsed {len(parsed_plays)} plays from NFL Pro")
    return parsed_plays


async def _fetch_nfl_pro_plays_from_session(game_uuid: str) -> List[Dict]:
    """Fallback: Fetch plays using saved session file (cookies + localStorage)."""
    from playwright.async_api import async_playwright

    if not NFL_PRO_STATE_FILE.exists():
        logger.warning(f"NFL Pro session file not found at {NFL_PRO_STATE_FILE}")
        return []

    try:
        with open(NFL_PRO_STATE_FILE) as f:
            state = json.load(f)
        cookies = state.get('cookies', [])
        if not cookies:
            logger.warning("No cookies in NFL Pro session file")
            return []
    except Exception as e:
        logger.warning(f"Error loading NFL Pro session: {e}")
        return []

    plays_raw = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # Build storage state for context
        storage_state = {
            'cookies': [],
            'origins': state.get('origins', [])
        }
        for c in cookies:
            pc = {
                'name': c['name'],
                'value': c['value'],
                'domain': c.get('domain', '.nfl.com'),
                'path': c.get('path', '/'),
            }
            if c.get('secure'):
                pc['secure'] = True
            if c.get('httpOnly'):
                pc['httpOnly'] = True
            if c.get('sameSite'):
                pc['sameSite'] = c['sameSite']
            storage_state['cookies'].append(pc)

        context = await browser.new_context(storage_state=storage_state)
        page = await context.new_page()

        async def capture_plays(response):
            nonlocal plays_raw
            if 'plays/playlist' in response.url and response.status == 200:
                try:
                    plays_raw = await response.json()
                    logger.info(f"Captured plays from session fallback: {response.url}")
                except:
                    pass

        page.on('response', capture_plays)

        try:
            url = f"https://pro.nfl.com/games/game/{game_uuid}/play-by-play"
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)
        except Exception as e:
            logger.warning(f"Session fallback navigation error: {e}")
        finally:
            await context.close()
            await browser.close()

    return _parse_raw_plays(plays_raw) if plays_raw else []


def _parse_raw_plays(plays_raw: Dict) -> List[Dict]:
    """Parse raw NFL Pro plays response into structured format."""
    raw_plays = plays_raw.get('plays', plays_raw.get('playlist', []))
    parsed_plays = []

    for raw in raw_plays:
        try:
            if raw.get('playType') == 'GAME' or raw.get('play_type') == 'GAME':
                continue

            offense = raw.get('offense', {}) or {}
            defense = raw.get('defense', {}) or {}
            pass_info = raw.get('passInfo', {}) or {}
            rec_info = raw.get('recInfo', {}) or {}

            coverage = defense.get('coverageType') or raw.get('coverage_type', '') or raw.get('coverageType', '')
            if coverage:
                coverage = coverage.replace('COVER_', 'Cover ').replace('_', ' ')

            man_zone = defense.get('manZoneType') or raw.get('man_zone', '') or raw.get('manZoneType', '')
            if man_zone:
                man_zone = 'Man' if 'MAN' in man_zone.upper() else 'Zone' if 'ZONE' in man_zone.upper() else ''

            time_to_throw = pass_info.get('timeToThrow') or raw.get('time_to_throw') or raw.get('timeToThrow') or 0
            air_yards = pass_info.get('airYards') or raw.get('air_yards') or raw.get('airYards') or 0
            was_pressure = pass_info.get('wasPressure') or raw.get('was_pressure') or raw.get('wasPressure') or False
            route = rec_info.get('route') or raw.get('route', '')

            defenders_in_box = defense.get('defendersInTheBox') or raw.get('defenders_in_box') or raw.get('defendersInTheBox') or 0
            pass_rushers = defense.get('numberOfPassRushers') or raw.get('pass_rushers') or raw.get('numberOfPassRushers') or 0

            off_personnel = offense.get('personnel') or raw.get('off_personnel') or raw.get('personnel', '')
            off_formation = offense.get('offenseFormation') or raw.get('off_formation') or raw.get('offenseFormation', '')
            def_personnel = defense.get('personnel') or raw.get('def_personnel', '')

            play = {
                'playId': raw.get('playId') or raw.get('play_id', 0),
                'sequence': raw.get('sequence', 0),
                'quarter': raw.get('quarter', 0),
                'clock': raw.get('endClock') or raw.get('end_clock') or raw.get('startClock') or raw.get('start_clock', ''),
                'down': raw.get('down', 0),
                'distance': raw.get('yardsToGo') or raw.get('yards_to_go', 0),
                'yardLine': raw.get('yardLine') or raw.get('yard_line', ''),
                'possessionTeam': raw.get('possessionTeam') or raw.get('possession_team', ''),
                'playDescription': raw.get('playDescription') or raw.get('description', ''),
                'yardsGained': raw.get('yardsGained') or raw.get('yards_gained', 0),
                'offense': {'personnel': off_personnel, 'offenseFormation': off_formation},
                'defense': {
                    'personnel': def_personnel,
                    'defendersInTheBox': int(defenders_in_box) if defenders_in_box else 0,
                    'numberOfPassRushers': int(pass_rushers) if pass_rushers else 0,
                    'coverageType': coverage,
                    'manZoneType': man_zone,
                },
                'passInfo': {
                    'timeToThrow': float(time_to_throw) if time_to_throw else 0,
                    'airYards': float(air_yards) if air_yards else 0,
                    'wasPressure': bool(was_pressure),
                },
                'recInfo': {'route': route},
                'isRedzone': raw.get('isRedzone') or raw.get('is_redzone', False),
            }
            parsed_plays.append(play)
        except Exception as e:
            logger.debug(f"Error parsing play: {e}")

    return parsed_plays


if __name__ == '__main__':
    logger.info("Starting Auto-Madden Insight Engine")
    logger.info(f"Initial broadcast delay: {delay_buffer.delay_seconds} seconds")
    app.run(host='0.0.0.0', port=5131, debug=False, threaded=True)

