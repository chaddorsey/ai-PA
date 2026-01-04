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
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable

import yaml
import requests
from flask import Flask, jsonify, request
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
    )
    NFL_PRO_NARRATIVES_AVAILABLE = True
except ImportError:
    nfl_pro_narratives = None
    load_narrative_insights = None
    get_player_triggered_insight = None
    get_break_narrative_insights = None
    get_pregame_narrative_insights = None
    get_narrative_llm_context = None
    NFL_PRO_NARRATIVES_AVAILABLE = False

# Import pre-play metadata service
try:
    import sys
    from pathlib import Path
    # Add nfl-pro-scraper to path (resolve to absolute path)
    scraper_path = (Path(__file__).parent.parent / 'nfl-pro-scraper').resolve()
    if scraper_path.exists():
        sys.path.insert(0, str(scraper_path))
    else:
        # Fallback: try relative to workspace
        alt_path = Path('/Volumes/main-drive/ai-PA/auto-madden/nfl-pro-scraper')
        if alt_path.exists():
            sys.path.insert(0, str(alt_path))
            scraper_path = alt_path
    
    from services.pre_play_service import PrePlayService, UserPreferences, process_pre_play
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
        """Broadcast pre-play metadata to all connected clients."""
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

        # Generate post-play analysis for every new_play event
        if change_type == 'new_play':
            post_insight = self._generate_post_play_insight(change, state)
            if post_insight:
                insights.append(post_insight)
            
            # Check for player-triggered NFL Pro insights on significant plays
            if NFL_PRO_NARRATIVES_AVAILABLE and get_player_triggered_insight:
                description = change.get('description', '')
                data = change.get('data', {})
                yards = data.get('yards', 0)
                is_scoring = data.get('is_scoring', False) or 'touchdown' in description.lower()
                is_big_play = yards >= 20 or is_scoring or data.get('is_turnover', False)
                
                if is_big_play:
                    # Extract player name from description
                    import re
                    player_match = re.search(r'([A-Z]\.[A-Za-z\-\']+)', description)
                    if player_match:
                        player_name = player_match.group(1)
                        quarter = state.get('quarter', 1)
                        
                        # Determine situation for context
                        situation = None
                        if state.get('is_red_zone'):
                            situation = 'red zone'
                        elif state.get('down') == 3:
                            situation = '3rd down'
                        
                        nfl_insight = get_player_triggered_insight(player_name, quarter, situation)
                        if nfl_insight:
                            insights.append(Insight(
                                id=nfl_insight.get('id', str(uuid.uuid4())[:8]),
                                insight_type='nfl_pro_player',
                                priority=nfl_insight.get('priority', 7),
                                timing='post_play',
                                headline=f"📊 {nfl_insight.get('headline', '')[:50]}",
                                body=nfl_insight.get('body', ''),
                                ttl=30
                            ))
                            logger.debug(f"Added NFL Pro player insight for {player_name}")
            
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
            try:
                nfl_pro_insights = get_break_narrative_insights(break_type, quarter, count)
                if nfl_pro_insights:
                    logger.info(f"📊 Loaded {len(nfl_pro_insights)} NFL Pro narrative insights for break")
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


@app.route('/event', methods=['POST'])
def receive_event():
    """Receive game state change events from game-state-service or simulator."""
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
        
        # === LOAD NFL PRO NARRATIVE INSIGHTS FOR THIS GAME ===
        if NFL_PRO_NARRATIVES_AVAILABLE and load_narrative_insights:
            try:
                home_team = state.get('home_team', {}).get('abbreviation', '')
                away_team = state.get('away_team', {}).get('abbreviation', '')
                
                # Try to get NFL Pro game UUID from state, or use ESPN game ID as fallback key
                nfl_pro_uuid = state.get('nfl_pro_uuid', state.get('game_id', ''))
                
                if home_team and away_team:
                    logger.info(f"🏈 Loading NFL Pro insights for {away_team} @ {home_team}")
                    success = load_narrative_insights(
                        game_uuid=nfl_pro_uuid,
                        home_team=home_team,
                        away_team=away_team
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

    # Queue for delivery
    for insight in insights:
        delivery_manager.queue_insight(insight)
    
    # === PRE-PLAY METADATA ===
    # Generate and broadcast pre-play info for the upcoming play
    # This happens after a play completes (before next snap)
    preplay_sent = False
    if change_type in ['play_complete', 'score_change', 'turnover', 'big_play', 'first_down']:
        try:
            # First check if pre-play data was provided directly (from NFL Pro polling)
            preplay_result = data.get('preplay')
            
            if preplay_result and preplay_result.get('items'):
                # Use the provided pre-play data
                delivery_manager.broadcast_preplay(preplay_result)
                preplay_sent = True
                logger.debug("Using pre-play data from polling service")
            elif PRE_PLAY_SERVICE_AVAILABLE and pre_play_service_instance:
                # Generate from state (ESPN/simulator fallback)
                play_data = _build_preplay_data_from_state(state, change)
                
                if play_data:
                    preplay_result = process_pre_play(play_data)
                    
                    if preplay_result.get('items'):
                        delivery_manager.broadcast_preplay(preplay_result)
                        preplay_sent = True
        except Exception as e:
            logger.warning(f"Error generating pre-play metadata: {e}")

    return jsonify({
        'status': 'ok',
        'insights_generated': len(insights),
        'preplay_sent': preplay_sent
    })


def _build_preplay_data_from_state(state: Dict[str, Any], change: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Build pre-play data from ESPN/simulator state for the upcoming play.
    
    In production with NFL Pro data, this would use the detailed play API.
    For now, we generate estimated data from the game state.
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
            # Check if yard number suggests red zone
            parts = yard_line.split()
            if len(parts) >= 2:
                yard_num = int(parts[-1])
                # If we're on opponent's side and within 20
                if yard_num <= 20 and not 'own' in yard_line.lower():
                    is_redzone = True
        except (ValueError, IndexError):
            pass
    
    # Estimate personnel and formation based on situation
    # These are educated guesses - real data would come from NFL Pro
    if is_redzone and yards_to_go <= 3:
        # Goal line / short yardage - likely heavy package
        off_personnel = '2 RB, 2 TE, 1 WR'
        off_formation = 'I_FORM'
        defenders_in_box = 8
    elif down == 3 and yards_to_go >= 7:
        # 3rd and long - spread formation
        off_personnel = '1 RB, 1 TE, 3 WR'
        off_formation = 'SHOTGUN'
        defenders_in_box = 5
    elif down == 1:
        # First down - balanced
        off_personnel = '1 RB, 1 TE, 3 WR'
        off_formation = 'SHOTGUN'
        defenders_in_box = 6
    else:
        # Default
        off_personnel = '1 RB, 1 TE, 3 WR'
        off_formation = 'SHOTGUN'
        defenders_in_box = 6
    
    possession_team = state.get('possession', state.get('home_team', {}).get('abbreviation', 'OFF'))
    
    return {
        'play_id': f"pre-{time.time():.0f}",
        'game_id': state.get('game_id', ''),
        'down': down,
        'yards_to_go': yards_to_go,
        'yard_line': yard_line or f'{possession_team} 35',
        'off_personnel': off_personnel,
        'off_formation': off_formation,
        'defenders_in_box': defenders_in_box,
        'is_redzone': is_redzone,
        'possession_team': possession_team,
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


if __name__ == '__main__':
    logger.info("Starting Auto-Madden Insight Engine")
    logger.info(f"Initial broadcast delay: {delay_buffer.delay_seconds} seconds")
    app.run(host='0.0.0.0', port=5131, debug=False, threaded=True)

