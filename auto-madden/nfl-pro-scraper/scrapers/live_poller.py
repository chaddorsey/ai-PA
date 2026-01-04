"""
NFL Pro Live Poller

Real-time polling of NFL Pro for live play-by-play data with detailed
formation, personnel, and situational information.

This service:
1. Polls NFL Pro during live games for detailed play data
2. Enriches basic ESPN data with NFL Pro's advanced analytics
3. Provides personnel groupings, formations, coverage types
4. Enables comparison against historical data

Usage:
    python live_poller.py --game-uuid <uuid> --port 5133

    Or import and use programmatically:
    from live_poller import NFLProLivePoller
    poller = NFLProLivePoller(game_uuid)
    poller.start()
"""

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '../credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'
DATA_PATH = Path(os.environ.get('DATA_PATH', '../data'))


class NFLProLivePoller:
    """
    Polls NFL Pro for live play-by-play data.
    
    Captures detailed information not available from ESPN:
    - Offensive formation (SHOTGUN, UNDER CENTER, etc.)
    - Personnel groupings (11, 12, 21, etc.)
    - Defensive personnel
    - Defenders in box
    - Pass rushers
    - Coverage type
    """
    
    BASE_URL = "https://pro.nfl.com"
    
    def __init__(
        self,
        game_uuid: str,
        poll_interval: int = 30,
        headless: bool = True,
        emit_url: str = "http://localhost:5131/event"
    ):
        self.game_uuid = game_uuid
        self.poll_interval = poll_interval
        self.headless = headless
        self.emit_url = emit_url
        
        self._playwright = None
        self._browser = None
        self._context = None
        
        self.running = False
        self._thread: Optional[threading.Thread] = None
        
        # Track seen plays to detect new ones
        self._seen_play_ids = set()
        self._last_play_count = 0
        
        # Current game state
        self.current_plays: List[Dict] = []
        self.home_team = ""
        self.away_team = ""
        
        # Historical data for comparison
        self._historical_db = DATA_PATH / "nfl_plays_2024.db"
    
    async def _init_browser(self):
        """Initialize browser with saved session."""
        state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
        
        if not state_file.exists():
            raise FileNotFoundError(
                "No NFL Pro session. Run nfl_pro_login.py first."
            )
        
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            storage_state=str(state_file),
            viewport={'width': 1400, 'height': 900},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        )
        logger.info("NFL Pro browser initialized")
    
    async def _close_browser(self):
        """Clean up browser resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    async def fetch_plays(self) -> Dict[str, Any]:
        """
        Fetch current plays from NFL Pro.
        
        Returns dict with:
            - plays: List of play dicts
            - home_team: Home team abbreviation
            - away_team: Away team abbreviation
            - new_plays: List of newly detected plays
        """
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
            url = f"{self.BASE_URL}/games/game/{self.game_uuid}/play-by-play"
            await page.goto(url, wait_until='networkidle')
            await asyncio.sleep(3)
        finally:
            await page.close()
        
        if not plays_data:
            return {'plays': [], 'home_team': '', 'away_team': '', 'new_plays': []}
        
        # Extract team abbreviations from plays
        teams = set()
        for p in plays_data.get('plays', []):
            if p.get('possessionTeam'):
                teams.add(p['possessionTeam'])
        
        # Determine home/away
        teams = list(teams)
        if len(teams) == 2:
            # First possession is typically away team
            for p in plays_data.get('plays', []):
                if p.get('possessionTeam') and p.get('down', 0) > 0:
                    self.away_team = p['possessionTeam']
                    self.home_team = [t for t in teams if t != self.away_team][0]
                    break
        
        # Parse plays and detect new ones
        all_plays = []
        new_plays = []
        
        for p in plays_data.get('plays', []):
            if p.get('isMarkerPlay', False):
                continue
            
            play_id = p.get('playId', 0)
            
            offense = p.get('offense', {}) or {}
            defense = p.get('defense', {}) or {}
            pass_info = p.get('passInfo', {}) or {}
            
            play = {
                'play_id': play_id,
                'sequence': p.get('sequence', 0),
                'quarter': p.get('quarter', 0),
                'down': p.get('down', 0),
                'yards_to_go': p.get('yardsToGo', 0),
                'possession_team': p.get('possessionTeam', ''),
                'start_clock': p.get('startGameClock', ''),
                'end_clock': p.get('endGameClock', ''),
                'home_score': p.get('homeScore', 0),
                'visitor_score': p.get('visitorScore', 0),
                'play_type': (p.get('playType', '') or '').replace('play_type_', ''),
                'play_description': p.get('playDescription', ''),
                'is_scoring': p.get('isScoring', False),
                'is_big_play': p.get('isBigPlay', False),
                'is_redzone': p.get('isRedzonePlay', False),
                
                # Advanced data from NFL Pro
                'off_formation': offense.get('offenseFormation', ''),
                'off_personnel': offense.get('personnel', ''),
                'def_personnel': defense.get('personnel', ''),
                'defenders_in_box': defense.get('defendersInTheBox'),
                'pass_rushers': defense.get('numberOfPassRushers'),
                'coverage_type': defense.get('coverageType', ''),
                'man_zone': defense.get('manZoneType', ''),
                'air_yards': pass_info.get('airYards'),
                'time_to_throw': pass_info.get('timeToThrow'),
                'was_pressure': pass_info.get('wasPressure', False),
            }
            
            all_plays.append(play)
            
            # Check if this is a new play
            if play_id not in self._seen_play_ids:
                self._seen_play_ids.add(play_id)
                if len(self._seen_play_ids) > 1:  # Skip first load
                    new_plays.append(play)
        
        self.current_plays = all_plays
        
        return {
            'plays': all_plays,
            'home_team': self.home_team,
            'away_team': self.away_team,
            'new_plays': new_plays,
            'total_plays': len(all_plays),
        }
    
    def get_historical_comparison(self, play: Dict) -> Dict[str, Any]:
        """
        Compare a play against historical data.
        
        Returns insights like:
        - How often this formation succeeds
        - Average yards for this personnel package
        - Success rate against this defensive look
        """
        if not self._historical_db.exists():
            return {}
        
        formation = play.get('off_formation', '')
        personnel = play.get('off_personnel', '')
        play_type = play.get('play_type', '')
        defenders_in_box = play.get('defenders_in_box')
        
        if not formation or not personnel:
            return {}
        
        try:
            conn = sqlite3.connect(self._historical_db)
            cursor = conn.cursor()
            
            # Find similar plays
            cursor.execute('''
                SELECT 
                    AVG(CAST(substr(play_description, instr(play_description, 'for ') + 4, 
                        instr(substr(play_description, instr(play_description, 'for ') + 4), ' ')) AS INTEGER)) as avg_yards,
                    COUNT(*) as play_count,
                    SUM(is_scoring) as scoring_plays,
                    SUM(is_big_play) as big_plays
                FROM plays
                WHERE off_formation = ? AND play_type = ?
            ''', (formation, play_type))
            
            row = cursor.fetchone()
            conn.close()
            
            if row and row[1] > 10:  # Only if we have enough data
                return {
                    'avg_yards': row[0],
                    'sample_size': row[1],
                    'scoring_rate': (row[2] / row[1]) * 100 if row[1] else 0,
                    'big_play_rate': (row[3] / row[1]) * 100 if row[1] else 0,
                    'formation': formation,
                    'play_type': play_type,
                }
        except Exception as e:
            logger.error(f"Historical comparison error: {e}")
        
        return {}
    
    async def emit_play_event(self, play: Dict, comparison: Dict = None):
        """Emit a play event to the insight engine."""
        import aiohttp
        
        event = {
            'event_type': 'nfl_pro_play',
            'play': play,
            'historical_comparison': comparison or {},
            'source': 'nfl_pro',
            'timestamp': datetime.now().isoformat(),
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.emit_url, json=event, timeout=5) as resp:
                    if resp.status == 200:
                        logger.info(f"Emitted play: Q{play['quarter']} {play['start_clock']} - {play['play_type']}")
                    else:
                        logger.warning(f"Emit failed: {resp.status}")
        except Exception as e:
            logger.debug(f"Could not emit: {e}")
    
    async def _poll_loop(self):
        """Main polling loop."""
        await self._init_browser()
        
        logger.info(f"Starting NFL Pro live polling for {self.game_uuid}")
        logger.info(f"Poll interval: {self.poll_interval}s")
        
        poll_count = 0
        
        try:
            while self.running:
                poll_count += 1
                
                result = await self.fetch_plays()
                
                logger.info(f"Poll #{poll_count}: {result['total_plays']} plays, {len(result['new_plays'])} new")
                
                # Process new plays
                for play in result['new_plays']:
                    comparison = self.get_historical_comparison(play)
                    await self.emit_play_event(play, comparison)
                    
                    # Log the new play with details
                    logger.info(
                        f"  NEW: Q{play['quarter']} {play['start_clock']} "
                        f"{play['down']}&{play['yards_to_go']} - "
                        f"{play['off_formation']} {play['off_personnel']} - "
                        f"{play['play_type']}"
                    )
                
                await asyncio.sleep(self.poll_interval)
        
        finally:
            await self._close_browser()
    
    def _run_async_loop(self):
        """Run the async poll loop in a thread."""
        asyncio.run(self._poll_loop())
    
    def start(self):
        """Start polling in background thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("Poller already running")
            return
        
        self.running = True
        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._thread.start()
        logger.info("NFL Pro poller started")
    
    def stop(self):
        """Stop polling."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("NFL Pro poller stopped")
    
    def get_current_state(self) -> Dict[str, Any]:
        """Get current game state from latest data."""
        if not self.current_plays:
            return {}
        
        latest = self.current_plays[-1] if self.current_plays else {}
        
        return {
            'game_uuid': self.game_uuid,
            'home_team': self.home_team,
            'away_team': self.away_team,
            'quarter': latest.get('quarter', 0),
            'clock': latest.get('end_clock', ''),
            'home_score': latest.get('home_score', 0),
            'away_score': latest.get('visitor_score', 0),
            'total_plays': len(self.current_plays),
            'last_play': latest,
        }


# Flask API for external integration
from flask import Flask, jsonify, request

app = Flask(__name__)

# CORS
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# Global poller instance
active_poller: Optional[NFLProLivePoller] = None


@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'service': 'nfl-pro-live-poller',
        'polling': active_poller.running if active_poller else False,
    })


@app.route('/start', methods=['POST'])
def start_polling():
    global active_poller
    
    data = request.get_json() or {}
    game_uuid = data.get('game_uuid')
    poll_interval = data.get('interval', 30)
    
    if not game_uuid:
        return jsonify({'status': 'error', 'message': 'game_uuid required'}), 400
    
    if active_poller and active_poller.running:
        active_poller.stop()
    
    active_poller = NFLProLivePoller(
        game_uuid=game_uuid,
        poll_interval=poll_interval,
        headless=True,
    )
    active_poller.start()
    
    return jsonify({
        'status': 'ok',
        'message': f'Polling started for {game_uuid}',
        'interval': poll_interval,
    })


@app.route('/stop', methods=['POST'])
def stop_polling():
    global active_poller
    
    if active_poller:
        active_poller.stop()
        active_poller = None
    
    return jsonify({'status': 'ok', 'message': 'Polling stopped'})


@app.route('/state')
def get_state():
    if not active_poller:
        return jsonify({'status': 'error', 'message': 'No active poller'}), 404
    
    return jsonify({
        'status': 'ok',
        'state': active_poller.get_current_state(),
    })


@app.route('/plays')
def get_plays():
    if not active_poller:
        return jsonify({'status': 'error', 'message': 'No active poller'}), 404
    
    return jsonify({
        'status': 'ok',
        'plays': active_poller.current_plays,
        'count': len(active_poller.current_plays),
    })


@app.route('/compare', methods=['POST'])
def compare_play():
    """Compare a play situation against historical data."""
    if not active_poller:
        return jsonify({'status': 'error', 'message': 'No active poller'}), 404
    
    data = request.get_json() or {}
    formation = data.get('formation')
    personnel = data.get('personnel')
    play_type = data.get('play_type', 'rush')
    
    # Build a mock play for comparison
    play = {
        'off_formation': formation,
        'off_personnel': personnel,
        'play_type': play_type,
    }
    
    comparison = active_poller.get_historical_comparison(play)
    
    return jsonify({
        'status': 'ok',
        'comparison': comparison,
    })


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='NFL Pro Live Poller')
    parser.add_argument('--game-uuid', help='Game UUID to poll')
    parser.add_argument('--port', type=int, default=5133, help='API port')
    parser.add_argument('--interval', type=int, default=30, help='Poll interval (seconds)')
    parser.add_argument('--visible', action='store_true', help='Show browser')
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    if args.game_uuid:
        # Start polling immediately
        global active_poller
        active_poller = NFLProLivePoller(
            game_uuid=args.game_uuid,
            poll_interval=args.interval,
            headless=not args.visible,
        )
        active_poller.start()
    
    print(f"\n{'='*60}")
    print("NFL Pro Live Poller Service")
    print(f"{'='*60}")
    print(f"Port: {args.port}")
    print(f"Endpoints:")
    print(f"  POST /start {{game_uuid, interval}} - Start polling")
    print(f"  POST /stop - Stop polling")
    print(f"  GET  /state - Current game state")
    print(f"  GET  /plays - All plays with details")
    print(f"  POST /compare {{formation, personnel}} - Historical comparison")
    print(f"{'='*60}\n")
    
    app.run(host='0.0.0.0', port=args.port, debug=False)


if __name__ == '__main__':
    main()

