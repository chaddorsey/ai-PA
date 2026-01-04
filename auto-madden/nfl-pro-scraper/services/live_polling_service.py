"""
NFL Pro Live Polling Service

Polls NFL Pro API for real-time play data and sends events to the insight engine.
Designed to work with a 60-90 second broadcast delay buffer for non-spoiler operation.

Usage:
    # As a CLI
    python live_polling_service.py <game_uuid> [--poll-interval 12] [--insight-engine-url http://localhost:5131]
    
    # Programmatic usage
    async with LivePollingService(game_uuid) as poller:
        await poller.run()
"""

import asyncio
import json
import logging
import os
import requests
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.nfl_pro_api import NFLProAPIClient, PlayData
from services.pre_play_service import PrePlayService, process_pre_play

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_POLL_INTERVAL = 12  # Seconds between polls
DEFAULT_INSIGHT_ENGINE_URL = os.environ.get('INSIGHT_ENGINE_URL', 'http://localhost:5131')


class LivePollingService:
    """
    Polls NFL Pro for live play data and sends events to the insight engine.
    
    Features:
    - Detects new plays
    - Identifies scoring plays, big plays, turnovers
    - Generates pre-play metadata for upcoming plays
    - Detects breaks (timeouts, commercials)
    - Sends game state updates to insight engine
    """
    
    def __init__(
        self,
        game_uuid: str,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
        insight_engine_url: str = DEFAULT_INSIGHT_ENGINE_URL,
        headless: bool = True
    ):
        self.game_uuid = game_uuid
        self.poll_interval = poll_interval
        self.insight_engine_url = insight_engine_url
        self.headless = headless
        
        self._api_client: Optional[NFLProAPIClient] = None
        self._pre_play_service = PrePlayService()
        
        # State tracking
        self._last_play_id = 0
        self._plays_seen: set = set()
        self._last_quarter = 0
        self._last_clock = "15:00"
        self._game_info: Dict[str, Any] = {}
        self._is_running = False
        
        # Callbacks
        self._on_play_callbacks: List[Callable] = []
        self._on_break_callbacks: List[Callable] = []
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
    
    async def start(self):
        """Initialize the API client."""
        self._api_client = NFLProAPIClient(headless=self.headless)
        await self._api_client.start()
        logger.info(f"Live polling service initialized for game: {self.game_uuid[:8]}...")
    
    async def stop(self):
        """Clean up resources."""
        self._is_running = False
        if self._api_client:
            await self._api_client.close()
    
    def add_play_callback(self, callback: Callable[[PlayData], None]):
        """Add a callback for when new plays are detected."""
        self._on_play_callbacks.append(callback)
    
    def add_break_callback(self, callback: Callable[[Dict], None]):
        """Add a callback for when breaks are detected."""
        self._on_break_callbacks.append(callback)
    
    async def run(self, max_iterations: Optional[int] = None):
        """
        Main polling loop.
        
        Args:
            max_iterations: Optional limit for testing; None = run forever
        """
        self._is_running = True
        iteration = 0
        
        logger.info(f"🏈 Starting live polling (interval: {self.poll_interval}s)")
        logger.info(f"   Insight Engine: {self.insight_engine_url}")
        
        while self._is_running:
            try:
                await self._poll_once()
                iteration += 1
                
                if max_iterations and iteration >= max_iterations:
                    logger.info(f"Reached max iterations: {max_iterations}")
                    break
                
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(self.poll_interval * 2)  # Back off on error
    
    async def _poll_once(self):
        """Perform one polling cycle."""
        plays = await self._api_client.get_plays(self.game_uuid)
        
        if not plays:
            logger.debug("No plays received from API")
            return
        
        # Sort by sequence/play_id to ensure order
        plays.sort(key=lambda p: (p.quarter, p.sequence))
        
        # Find new plays
        new_plays = [p for p in plays if p.play_id not in self._plays_seen]
        
        if not new_plays:
            logger.debug(f"No new plays. Total: {len(plays)}")
            return
        
        logger.info(f"📥 Detected {len(new_plays)} new play(s)")
        
        for play in new_plays:
            self._plays_seen.add(play.play_id)
            await self._process_new_play(play, plays)
        
        # Update tracking
        if plays:
            latest = plays[-1]
            self._last_play_id = latest.play_id
            self._last_quarter = latest.quarter
            self._last_clock = latest.end_clock or latest.start_clock
            
            # Store game info from plays
            self._game_info = {
                'home_score': latest.home_score,
                'away_score': latest.visitor_score,
                'quarter': latest.quarter,
                'clock': self._last_clock,
            }
    
    async def _process_new_play(self, play: PlayData, all_plays: List[PlayData]):
        """Process a newly detected play."""
        
        # Determine event type
        event_type = self._classify_play(play)
        
        # Build game state
        state = self._build_game_state(play, all_plays)
        
        # Detect breaks
        break_info = self._detect_break(play, all_plays)
        
        # Generate pre-play metadata for the NEXT play
        preplay_data = self._generate_preplay(play)
        
        # Build event payload
        event = {
            'event_type': event_type,
            'play_description': play.description,
            'state': state,
            'play_data': play.to_dict(),
            'preplay': preplay_data,
        }
        
        if break_info:
            event['break_info'] = break_info
            event['event_type'] = 'break_start'
        
        # Send to insight engine
        await self._send_event(event)
        
        # Call registered callbacks
        for callback in self._on_play_callbacks:
            try:
                callback(play)
            except Exception as e:
                logger.warning(f"Play callback error: {e}")
        
        if break_info:
            for callback in self._on_break_callbacks:
                try:
                    callback(break_info)
                except Exception as e:
                    logger.warning(f"Break callback error: {e}")
    
    def _classify_play(self, play: PlayData) -> str:
        """Classify play into event type."""
        desc_lower = play.description.lower()
        
        if play.is_scoring:
            return 'score_change'
        
        # Turnovers
        if any(kw in desc_lower for kw in ['intercepted', 'fumble', 'fumbles', 'muffed']):
            return 'turnover'
        
        if play.is_big_play:
            return 'big_play'
        
        # First down (simple heuristic)
        # TODO: Enhance with actual first down detection
        if play.play_type in ['rush', 'pass'] and play.down > 0:
            return 'play_complete'
        
        # Special teams
        if play.is_special_teams:
            return 'play_complete'
        
        return 'play_complete'
    
    def _build_game_state(self, play: PlayData, all_plays: List[PlayData]) -> Dict[str, Any]:
        """Build game state dict from play data."""
        
        # Find home/away team abbreviations from plays
        possession_teams = set(p.possession_team for p in all_plays if p.possession_team)
        teams = list(possession_teams)
        
        # Use first two distinct teams
        home_team = teams[0] if teams else 'HOME'
        away_team = teams[1] if len(teams) > 1 else 'AWAY'
        
        return {
            'game_id': self.game_uuid,
            'nfl_pro_uuid': self.game_uuid,
            'quarter': play.quarter,
            'clock': play.end_clock or play.start_clock,
            'down': play.down,
            'distance': play.yards_to_go,
            'yard_line': play.yard_line,
            'possession_team': play.possession_team,
            'is_red_zone': play.is_redzone,
            'home_team': {
                'abbreviation': home_team,
                'score': play.home_score,
            },
            'away_team': {
                'abbreviation': away_team,
                'score': play.visitor_score,
            },
            # Detailed play info
            'offense_personnel': play.off_personnel,
            'offense_formation': play.off_formation,
            'defenders_in_box': play.defenders_in_box,
            'pass_rushers': play.pass_rushers,
            'coverage_type': play.coverage_type,
        }
    
    def _detect_break(self, play: PlayData, all_plays: List[PlayData]) -> Optional[Dict]:
        """Detect if this play triggers a break."""
        desc_lower = play.description.lower()
        
        # Scoring play break
        if play.is_scoring:
            return {
                'break_type': 'post_score',
                'description': 'Break after scoring play',
                'duration': 90,
                'analysis_opportunity': 'extended',
                'points_scored': 6 if 'touchdown' in desc_lower else 3,
            }
        
        # Timeout
        if 'timeout' in desc_lower:
            team = play.possession_team
            if 'official' in desc_lower or 'tv' in desc_lower:
                return {
                    'break_type': 'official_timeout',
                    'description': 'Official TV timeout',
                    'duration': 120,
                    'analysis_opportunity': 'extended',
                }
            return {
                'break_type': 'team_timeout',
                'description': f'{team} timeout',
                'team': team,
                'duration': 60,
                'analysis_opportunity': 'brief',
            }
        
        # Two-minute warning
        if 'two-minute' in desc_lower or 'two minute warning' in desc_lower:
            return {
                'break_type': 'two_minute_warning',
                'description': 'Two-minute warning',
                'duration': 120,
                'analysis_opportunity': 'extended',
            }
        
        # Quarter break
        if self._last_quarter != play.quarter and play.quarter in [2, 3, 4]:
            if play.quarter == 3:
                return {
                    'break_type': 'halftime',
                    'description': 'Halftime break',
                    'duration': 1200,
                    'analysis_opportunity': 'extended',
                }
            return {
                'break_type': 'quarter_break',
                'description': f'End of Quarter {play.quarter - 1}',
                'new_quarter': play.quarter,
                'duration': 120,
                'analysis_opportunity': 'standard',
            }
        
        # Challenge/review
        if any(kw in desc_lower for kw in ['challenge', 'review', 'booth review']):
            return {
                'break_type': 'challenge',
                'description': 'Official review',
                'duration': 90,
                'analysis_opportunity': 'standard',
            }
        
        return None
    
    def _generate_preplay(self, play: PlayData) -> Optional[Dict]:
        """Generate pre-play metadata for display."""
        play_dict = play.to_dict()
        
        try:
            preplay = process_pre_play(play_dict)
            return preplay
        except Exception as e:
            logger.warning(f"Could not generate pre-play: {e}")
            return None
    
    async def _send_event(self, event: Dict):
        """Send event to insight engine."""
        try:
            url = f"{self.insight_engine_url}/event"
            response = requests.post(
                url,
                json=event,
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                insights = result.get('insights_generated', 0)
                logger.info(f"  → Event sent: {event['event_type']} | Insights: {insights}")
            else:
                logger.warning(f"Event send failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Could not send event to insight engine: {e}")


async def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='NFL Pro Live Polling Service')
    parser.add_argument('game_uuid', help='NFL Pro game UUID')
    parser.add_argument('--poll-interval', type=int, default=DEFAULT_POLL_INTERVAL,
                        help=f'Seconds between polls (default: {DEFAULT_POLL_INTERVAL})')
    parser.add_argument('--insight-engine-url', default=DEFAULT_INSIGHT_ENGINE_URL,
                        help=f'Insight engine URL (default: {DEFAULT_INSIGHT_ENGINE_URL})')
    parser.add_argument('--max-iterations', type=int, default=None,
                        help='Maximum polling iterations (for testing)')
    parser.add_argument('--headless', action='store_true', default=True,
                        help='Run browser in headless mode')
    
    args = parser.parse_args()
    
    print(f"\n🏈 NFL Pro Live Polling Service")
    print(f"   Game: {args.game_uuid[:8]}...")
    print(f"   Poll Interval: {args.poll_interval}s")
    print(f"   Insight Engine: {args.insight_engine_url}")
    print()
    
    async with LivePollingService(
        game_uuid=args.game_uuid,
        poll_interval=args.poll_interval,
        insight_engine_url=args.insight_engine_url,
        headless=args.headless
    ) as poller:
        await poller.run(max_iterations=args.max_iterations)


if __name__ == '__main__':
    asyncio.run(main())

