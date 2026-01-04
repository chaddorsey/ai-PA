"""
NFL Pro API Client

Direct API access to NFL Pro data, bypassing DOM scraping.
These APIs provide richer data than what's visible in the UI.

Discovered APIs:
- Plays: /api/secured/plays/playlist/game?gameId={gameId}
- Insights: /api/content/insights/game?season={season}&limit=100&tags=...
- Game: /api/schedules/game?fapiGameId={uuid}
- Scores: /api/scores/live/games?season={season}&seasonType={type}&week={week}
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from playwright.async_api import async_playwright, BrowserContext

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '/Volumes/main-drive/ai-PA/auto-madden/credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'


@dataclass
class PlayData:
    """Enriched play data from NFL Pro API."""
    play_id: int
    sequence: int
    quarter: int
    down: int
    yards_to_go: int
    yard_line: str
    description: str
    play_type: str
    possession_team: str
    
    # Scores
    home_score: int = 0
    visitor_score: int = 0
    
    # Clock
    start_clock: str = ""
    end_clock: str = ""
    
    # Flags
    is_scoring: bool = False
    is_big_play: bool = False
    is_redzone: bool = False
    is_special_teams: bool = False
    
    # Offense details
    off_formation: str = ""
    off_personnel: str = ""
    
    # Defense details
    def_personnel: str = ""
    defenders_in_box: Optional[int] = None
    pass_rushers: Optional[int] = None
    coverage_type: str = ""
    man_zone: str = ""
    
    # Pass info
    air_yards: Optional[float] = None
    time_to_throw: Optional[float] = None
    was_pressure: Optional[bool] = None
    route: str = ""
    
    # Player stats
    player_stats: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'play_id': self.play_id,
            'sequence': self.sequence,
            'quarter': self.quarter,
            'down': self.down,
            'yards_to_go': self.yards_to_go,
            'yard_line': self.yard_line,
            'description': self.description,
            'play_type': self.play_type,
            'possession_team': self.possession_team,
            'home_score': self.home_score,
            'visitor_score': self.visitor_score,
            'start_clock': self.start_clock,
            'end_clock': self.end_clock,
            'is_scoring': self.is_scoring,
            'is_big_play': self.is_big_play,
            'is_redzone': self.is_redzone,
            'is_special_teams': self.is_special_teams,
            'off_formation': self.off_formation,
            'off_personnel': self.off_personnel,
            'def_personnel': self.def_personnel,
            'defenders_in_box': self.defenders_in_box,
            'pass_rushers': self.pass_rushers,
            'coverage_type': self.coverage_type,
            'man_zone': self.man_zone,
            'air_yards': self.air_yards,
            'time_to_throw': self.time_to_throw,
            'was_pressure': self.was_pressure,
            'route': self.route,
            'player_stats': self.player_stats,
        }


@dataclass
class InsightData:
    """Insight data from NFL Pro API."""
    insight_id: str
    game_id: int
    title: str
    sub_note: str       # Primary paragraph (subNote1)
    sub_note2: str      # Secondary paragraph (subNote2)
    date: str
    
    # Primary entity
    player_name: str = ""
    position: str = ""
    team_abbr: str = ""
    jersey_number: Optional[int] = None
    
    # Secondary entity (for matchup insights)
    second_player_name: str = ""
    second_position: str = ""
    second_team_abbr: str = ""
    second_team_type: str = ""  # "defense", "offense"
    
    # Media
    image_url: str = ""
    headshot_url: str = ""
    
    # Metadata
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'insight_id': self.insight_id,
            'game_id': self.game_id,
            'title': self.title,
            'sub_note': self.sub_note,
            'sub_note2': self.sub_note2,
            'date': self.date,
            'player_name': self.player_name,
            'position': self.position,
            'team_abbr': self.team_abbr,
            'jersey_number': self.jersey_number,
            'second_player_name': self.second_player_name,
            'second_position': self.second_position,
            'second_team_abbr': self.second_team_abbr,
            'second_team_type': self.second_team_type,
            'image_url': self.image_url,
            'headshot_url': self.headshot_url,
            'tags': self.tags,
        }
    
    def to_parser_format(self) -> Dict[str, Any]:
        """Convert to format expected by InsightParser."""
        return {
            'id': self.insight_id,
            'title': self.title,
            'subNote1': self.sub_note,
            'subNote2': self.sub_note2,
            'playerName': self.player_name,
            'position1': self.position,
            'teamAbbr': self.team_abbr,
            'playerName2': self.second_player_name,
            'position2': self.second_position,
            'teamAbbr2': self.second_team_abbr,
        }


class NFLProAPIClient:
    """Client for NFL Pro APIs using authenticated browser session."""
    
    BASE_URL = "https://pro.nfl.com"
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context: Optional[BrowserContext] = None
        self._captured_data: Dict[str, Any] = {}
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
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
        logger.info("NFL Pro API client initialized")
    
    async def close(self):
        """Clean up resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    async def get_game_id(self, game_uuid: str) -> Optional[int]:
        """Get numeric game ID from UUID."""
        page = await self._context.new_page()
        game_id = None
        
        async def capture_game_id(response):
            nonlocal game_id
            if 'schedules/game' in response.url and response.status == 200:
                try:
                    data = await response.json()
                    game_id = data.get('gameId')
                except:
                    pass
        
        page.on('response', capture_game_id)
        
        try:
            await page.goto(f"{self.BASE_URL}/games/game/{game_uuid}", wait_until='networkidle')
            await asyncio.sleep(2)
        finally:
            await page.close()
        
        return game_id
    
    async def get_plays(self, game_uuid: str) -> List[PlayData]:
        """Get all plays with enriched data for a game."""
        page = await self._context.new_page()
        plays_raw = None
        
        async def capture_plays(response):
            nonlocal plays_raw
            if 'plays/playlist' in response.url and response.status == 200:
                try:
                    plays_raw = await response.json()
                except:
                    pass
        
        page.on('response', capture_plays)
        
        try:
            await page.goto(
                f"{self.BASE_URL}/games/game/{game_uuid}/play-by-play",
                wait_until='networkidle'
            )
            await asyncio.sleep(3)
        finally:
            await page.close()
        
        if not plays_raw or 'plays' not in plays_raw:
            return []
        
        plays = []
        for p in plays_raw['plays']:
            yard_line = ""
            if p.get('yardlineSide') and p.get('yardlineNumber'):
                yard_line = f"{p['yardlineSide']} {p['yardlineNumber']}"
            
            offense = p.get('offense', {})
            defense = p.get('defense', {})
            pass_info = p.get('passInfo', {})
            rec_info = p.get('recInfo', {})
            
            play = PlayData(
                play_id=p.get('playId', 0),
                sequence=p.get('sequence', 0),
                quarter=p.get('quarter', 0),
                down=p.get('down', 0),
                yards_to_go=p.get('yardsToGo', 0),
                yard_line=yard_line,
                description=p.get('playDescription', ''),
                play_type=p.get('playType', '').replace('play_type_', ''),
                possession_team=p.get('possessionTeam', ''),
                home_score=p.get('homeScore', 0),
                visitor_score=p.get('visitorScore', 0),
                start_clock=p.get('startGameClock', ''),
                end_clock=p.get('endGameClock', ''),
                is_scoring=p.get('isScoring', False),
                is_big_play=p.get('isBigPlay', False),
                is_redzone=p.get('isRedzonePlay', False),
                is_special_teams=p.get('isSTPlay', False),
                # Offense
                off_formation=offense.get('offenseFormation', ''),
                off_personnel=offense.get('personnel', ''),
                # Defense
                def_personnel=defense.get('personnel', ''),
                defenders_in_box=defense.get('defendersInTheBox'),
                pass_rushers=defense.get('numberOfPassRushers'),
                coverage_type=defense.get('coverageType', ''),
                man_zone=defense.get('manZoneType', ''),
                # Pass info
                air_yards=pass_info.get('airYards'),
                time_to_throw=pass_info.get('timeToThrow'),
                was_pressure=pass_info.get('wasPressure'),
                route=rec_info.get('route', ''),
                # Stats
                player_stats=p.get('playStats', []),
            )
            plays.append(play)
        
        logger.info(f"Retrieved {len(plays)} plays for game {game_uuid}")
        return plays
    
    async def get_insights(self, game_uuid: str, wait_time: int = 30) -> List[InsightData]:
        """Get all insights for a game."""
        page = await self._context.new_page()
        insights_raw = None
        
        async def capture_insights(response):
            nonlocal insights_raw
            if 'insights/game' in response.url and response.status == 200:
                try:
                    insights_raw = await response.json()
                except:
                    pass
        
        page.on('response', capture_insights)
        
        try:
            await page.goto(
                f"{self.BASE_URL}/games/game/{game_uuid}/insights",
                wait_until='networkidle'
            )
            # Wait for graphics-heavy content to load
            await asyncio.sleep(wait_time)
        finally:
            await page.close()
        
        if not insights_raw:
            return []
        
        insights = []
        for i in insights_raw:
            insight = InsightData(
                insight_id=i.get('id', ''),
                game_id=i.get('gameId', 0),
                title=i.get('title', ''),
                sub_note=i.get('subNote1', ''),
                sub_note2=i.get('subNote2', ''),
                date=i.get('date', ''),
                player_name=i.get('playerName', ''),
                position=i.get('position', ''),
                team_abbr=i.get('teamAbbr', ''),
                jersey_number=i.get('jerseyNumber'),
                second_player_name=i.get('secondPlayerName') or '',
                second_position=i.get('secondPosition') or '',
                second_team_abbr=i.get('secondTeamAbbr') or '',
                second_team_type=i.get('secondTeamType') or '',
                image_url=i.get('imageUrl', ''),
                headshot_url=i.get('headshot', ''),
                tags=i.get('tags', []),
            )
            insights.append(insight)
        
        logger.info(f"Retrieved {len(insights)} insights for game {game_uuid}")
        return insights


async def main():
    """Test the API client."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python nfl_pro_api.py <game_uuid>")
        sys.exit(1)
    
    game_uuid = sys.argv[1]
    
    logging.basicConfig(level=logging.INFO)
    
    async with NFLProAPIClient(headless=True) as client:
        # Get plays
        print("\n=== FETCHING PLAYS ===")
        plays = await client.get_plays(game_uuid)
        print(f"Retrieved {len(plays)} plays")
        
        # Show sample pass and rush plays
        for play in plays:
            if play.play_type == 'pass' and play.off_formation:
                print(f"\n--- Sample PASS play ---")
                print(f"Q{play.quarter} {play.down}&{play.yards_to_go} at {play.yard_line}")
                print(f"Formation: {play.off_formation}")
                print(f"Personnel (O): {play.off_personnel}")
                print(f"Personnel (D): {play.def_personnel}")
                print(f"Pass Rushers: {play.pass_rushers}")
                print(f"In The Box: {play.defenders_in_box}")
                print(f"Coverage: {play.coverage_type}")
                print(f"Route: {play.route}")
                break
        
        for play in plays:
            if play.play_type == 'rush' and play.off_formation:
                print(f"\n--- Sample RUSH play ---")
                print(f"Q{play.quarter} {play.down}&{play.yards_to_go} at {play.yard_line}")
                print(f"Formation: {play.off_formation}")
                print(f"Personnel (O): {play.off_personnel}")
                print(f"Personnel (D): {play.def_personnel}")
                print(f"In The Box: {play.defenders_in_box}")
                break
        
        # Get insights
        print("\n=== FETCHING INSIGHTS ===")
        insights = await client.get_insights(game_uuid, wait_time=10)
        print(f"Retrieved {len(insights)} insights")
        
        for insight in insights[:3]:
            print(f"\n--- Insight ---")
            print(f"Title: {insight.title[:80]}...")
            print(f"Player: {insight.player_name} ({insight.position}, {insight.team_abbr})")
            if insight.second_team_abbr:
                print(f"vs: {insight.second_player_name or insight.second_team_abbr} {insight.second_team_type}")
        
        # Save to file
        output = {
            'game_uuid': game_uuid,
            'scraped_at': datetime.now().isoformat(),
            'plays': [p.to_dict() for p in plays],
            'insights': [i.to_dict() for i in insights],
        }
        
        output_file = f"nfl_pro_data_{game_uuid[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"\n📄 Saved to: {output_file}")


if __name__ == '__main__':
    asyncio.run(main())

