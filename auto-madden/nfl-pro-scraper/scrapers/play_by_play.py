"""
Play-by-Play Scraper for NFL Pro

Scrapes the play-by-play tab from NFL Pro games, including hidden data
accessible via dropdown filters.

The play-by-play page contains:
- Full list of plays with descriptions
- Down, distance, yard line, time, quarter
- Play result and yards gained
- Hidden data via filters: formation, personnel, pass depth, direction, etc.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from playwright.async_api import async_playwright, Page, BrowserContext

# Import models (adjust path as needed)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from models.plays import (
    Play, PlayByPlayData, DriveInfo, PlayParticipant,
    PlayType, PlayResult
)

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '../credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'


class PlayByPlayScraper:
    """Scrapes play-by-play data from NFL Pro."""
    
    BASE_URL = "https://pro.nfl.com/games/game"
    
    # Mapping of text patterns to play types
    PLAY_TYPE_PATTERNS = {
        PlayType.PASS: [r'pass', r'sacked', r'scramble'],
        PlayType.RUSH: [r'rush', r'run ', r'up the middle', r'left end', r'right end'],
        PlayType.PUNT: [r'punt'],
        PlayType.KICKOFF: [r'kickoff', r'kicks off'],
        PlayType.FIELD_GOAL: [r'field goal', r'fg attempt'],
        PlayType.EXTRA_POINT: [r'extra point', r'pat '],
        PlayType.TWO_POINT: [r'two-point', r'2pt', r'two point'],
        PlayType.KNEEL: [r'kneel', r'kneels'],
        PlayType.SPIKE: [r'spike'],
        PlayType.PENALTY: [r'penalty'],
        PlayType.TIMEOUT: [r'timeout', r'time out'],
    }
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def start(self):
        """Initialize the browser."""
        state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
        
        if not state_file.exists():
            raise FileNotFoundError("No NFL Pro session. Run nfl_pro_login.py first.")
        
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            storage_state=str(state_file),
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        )
        logger.info("Browser initialized with saved session")
    
    async def close(self):
        """Clean up browser resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    async def scrape_game(self, game_uuid: str) -> PlayByPlayData:
        """Scrape play-by-play data for a game."""
        url = f"{self.BASE_URL}/{game_uuid}/play-by-play"
        
        page = await self._context.new_page()
        logger.info(f"Navigating to: {url}")
        
        try:
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await asyncio.sleep(3)  # Wait for dynamic content
            
            # Check for auth issues
            if 'login' in page.url.lower():
                raise Exception("Session expired - please re-authenticate")
            
            # Extract team info from page
            home_team, away_team = await self._extract_teams(page)
            
            # Scrape all plays
            plays = await self._scrape_plays(page)
            
            # Organize into drives
            drives = self._organize_into_drives(plays)
            
            # Calculate summary stats
            summary = self._calculate_summary(plays, home_team, away_team)
            
            data = PlayByPlayData(
                game_uuid=game_uuid,
                home_team=home_team,
                away_team=away_team,
                total_plays=len(plays),
                plays=plays,
                drives=drives,
                home_total_yards=summary['home_yards'],
                away_total_yards=summary['away_yards'],
                home_turnovers=summary['home_turnovers'],
                away_turnovers=summary['away_turnovers'],
                scraped_at=datetime.now(),
            )
            
            logger.info(f"Scraped {len(plays)} plays for game {game_uuid}")
            return data
            
        finally:
            await page.close()
    
    async def _extract_teams(self, page: Page) -> tuple:
        """Extract home and away team abbreviations from the page."""
        # Try various selectors for team names
        selectors = [
            '[class*="team-abbreviation"]',
            '[class*="TeamAbbreviation"]',
            '[class*="team-name"]',
            '[class*="TeamName"]',
            '[data-testid*="team"]',
        ]
        
        for selector in selectors:
            elements = await page.query_selector_all(selector)
            if len(elements) >= 2:
                away = (await elements[0].inner_text()).strip()
                home = (await elements[1].inner_text()).strip()
                return home, away
        
        # Fallback: extract from URL or page title
        title = await page.title()
        match = re.search(r'(\w+)\s*[@at]+\s*(\w+)', title)
        if match:
            return match.group(2), match.group(1)  # home, away
        
        return "HOME", "AWAY"
    
    async def _scrape_plays(self, page: Page) -> List[Play]:
        """Scrape all plays from the page."""
        plays = []
        
        # Wait for play content
        await page.wait_for_selector(
            '[class*="play"], [class*="Play"], tr, [role="row"]',
            timeout=30000
        )
        
        # Scroll to load all plays
        await self._scroll_to_load_all(page)
        
        # Find all play rows
        play_rows = await page.query_selector_all(
            '[class*="play-row"], [class*="PlayRow"], tr[data-*], [data-testid*="play"]'
        )
        
        # If that didn't work, try more generic selectors
        if len(play_rows) < 5:
            play_rows = await page.query_selector_all('tbody tr, [role="row"]')
        
        logger.info(f"Found {len(play_rows)} play rows")
        
        for i, row in enumerate(play_rows):
            try:
                play = await self._parse_play_row(row, i)
                if play:
                    plays.append(play)
            except Exception as e:
                logger.warning(f"Error parsing play row {i}: {e}")
        
        return plays
    
    async def _scroll_to_load_all(self, page: Page, max_scrolls: int = 20):
        """Scroll to load all lazy-loaded content."""
        last_height = 0
        for _ in range(max_scrolls):
            # Get current scroll height
            height = await page.evaluate('document.documentElement.scrollHeight')
            if height == last_height:
                break
            
            last_height = height
            await page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)')
            await asyncio.sleep(0.5)
        
        # Scroll back to top
        await page.evaluate('window.scrollTo(0, 0)')
        await asyncio.sleep(0.5)
    
    async def _parse_play_row(self, row, index: int) -> Optional[Play]:
        """Parse a single play row into a Play object."""
        try:
            full_text = await row.inner_text()
            if not full_text or len(full_text.strip()) < 10:
                return None
            
            # Skip header rows
            if 'quarter' in full_text.lower() and 'time' in full_text.lower():
                return None
            
            # Extract components
            cells = await row.query_selector_all('td, [role="cell"], div')
            cell_texts = []
            for cell in cells:
                text = await cell.inner_text()
                cell_texts.append(text.strip())
            
            # Parse based on typical structure
            # Usually: Quarter | Time | Down & Distance | Description | Result
            play = Play(
                play_id=f"play_{index}",
                quarter=self._extract_quarter(cell_texts, full_text),
                time=self._extract_time(cell_texts, full_text),
                down=self._extract_down(cell_texts, full_text),
                distance=self._extract_distance(cell_texts, full_text),
                yard_line=self._extract_yard_line(cell_texts, full_text),
                description=self._extract_description(cell_texts, full_text),
            )
            
            # Determine play type and result
            play.play_type = self._determine_play_type(play.description)
            play.play_result = self._determine_play_result(play.description)
            play.yards_gained = self._extract_yards(play.description)
            
            # Set flags
            play.is_scoring_play = self._is_scoring(play.description)
            play.is_turnover = self._is_turnover(play.description)
            play.is_big_play = play.yards_gained >= 20 if play.play_type == PlayType.PASS else play.yards_gained >= 10
            play.is_first_down = 'first down' in play.description.lower()
            
            # Extract possession team
            play.possession_team = self._extract_possession(play.description, cell_texts)
            
            return play
            
        except Exception as e:
            logger.warning(f"Error parsing play: {e}")
            return None
    
    def _extract_quarter(self, cells: List[str], full_text: str) -> int:
        """Extract quarter from play data."""
        # Look for Q1, Q2, Q3, Q4, OT patterns
        for cell in cells:
            match = re.search(r'Q?([1-4]|OT)', cell, re.IGNORECASE)
            if match:
                val = match.group(1).upper()
                return 5 if val == 'OT' else int(val)
        
        match = re.search(r'(?:quarter|Q)\s*([1-4])', full_text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        return 1
    
    def _extract_time(self, cells: List[str], full_text: str) -> str:
        """Extract game time from play data."""
        for cell in cells:
            match = re.search(r'(\d{1,2}:\d{2})', cell)
            if match:
                return match.group(1)
        
        match = re.search(r'(\d{1,2}:\d{2})', full_text)
        if match:
            return match.group(1)
        
        return "0:00"
    
    def _extract_down(self, cells: List[str], full_text: str) -> Optional[int]:
        """Extract down from play data."""
        combined = ' '.join(cells) + ' ' + full_text
        match = re.search(r'([1-4])(?:st|nd|rd|th)?\s*(?:&|and|down)', combined, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None
    
    def _extract_distance(self, cells: List[str], full_text: str) -> Optional[int]:
        """Extract distance from play data."""
        combined = ' '.join(cells) + ' ' + full_text
        match = re.search(r'(?:&|and)\s*(\d+|goal)', combined, re.IGNORECASE)
        if match:
            val = match.group(1)
            return 0 if val.lower() == 'goal' else int(val)
        return None
    
    def _extract_yard_line(self, cells: List[str], full_text: str) -> str:
        """Extract yard line from play data."""
        combined = ' '.join(cells) + ' ' + full_text
        # Look for "at SF 25" or "NYG 40" or "50" patterns
        match = re.search(r'(?:at\s+)?([A-Z]{2,3}\s+\d{1,2}|\d{2})\s*(?:yard)?', combined, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""
    
    def _extract_description(self, cells: List[str], full_text: str) -> str:
        """Extract play description."""
        # Usually the longest cell contains the description
        if cells:
            longest = max(cells, key=len)
            if len(longest) > 20:
                return longest
        return full_text
    
    def _determine_play_type(self, description: str) -> PlayType:
        """Determine the type of play from description."""
        desc_lower = description.lower()
        
        for play_type, patterns in self.PLAY_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, desc_lower):
                    return play_type
        
        return PlayType.UNKNOWN
    
    def _determine_play_result(self, description: str) -> PlayResult:
        """Determine the result of a play from description."""
        desc_lower = description.lower()
        
        if 'touchdown' in desc_lower:
            return PlayResult.TOUCHDOWN
        if 'intercept' in desc_lower:
            return PlayResult.INTERCEPTION
        if 'fumble' in desc_lower:
            return PlayResult.FUMBLE
        if 'sack' in desc_lower:
            return PlayResult.SACK
        if 'incomplete' in desc_lower:
            return PlayResult.INCOMPLETE
        if 'first down' in desc_lower:
            return PlayResult.FIRST_DOWN
        if 'penalty' in desc_lower:
            return PlayResult.PENALTY
        if 'field goal' in desc_lower:
            if 'good' in desc_lower or 'made' in desc_lower:
                return PlayResult.FIELD_GOAL_GOOD
            else:
                return PlayResult.FIELD_GOAL_MISSED
        
        return PlayResult.UNKNOWN
    
    def _extract_yards(self, description: str) -> int:
        """Extract yards gained from description."""
        # Look for "for X yards" or "gain of X" patterns
        match = re.search(r'for\s+(-?\d+)\s+yard', description, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        match = re.search(r'gain\s+of\s+(\d+)', description, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        match = re.search(r'loss\s+of\s+(\d+)', description, re.IGNORECASE)
        if match:
            return -int(match.group(1))
        
        return 0
    
    def _is_scoring(self, description: str) -> bool:
        """Check if play resulted in a score."""
        desc_lower = description.lower()
        return any(s in desc_lower for s in ['touchdown', 'field goal good', 'safety', 'extra point good'])
    
    def _is_turnover(self, description: str) -> bool:
        """Check if play resulted in a turnover."""
        desc_lower = description.lower()
        return any(s in desc_lower for s in ['intercept', 'fumble', 'fumbled', 'turnover'])
    
    def _extract_possession(self, description: str, cells: List[str]) -> str:
        """Extract which team had possession."""
        # Look for team abbreviation at start of description
        match = re.search(r'^([A-Z]{2,3})', description)
        if match:
            return match.group(1)
        
        # Look in cells
        for cell in cells:
            if len(cell) == 2 or len(cell) == 3:
                if cell.isupper():
                    return cell
        
        return ""
    
    def _organize_into_drives(self, plays: List[Play]) -> List[DriveInfo]:
        """Organize plays into drives."""
        if not plays:
            return []
        
        drives = []
        current_drive_plays = []
        current_team = None
        drive_num = 0
        
        for play in plays:
            # New drive if possession changes (excluding special teams)
            if play.possession_team and play.possession_team != current_team:
                if current_drive_plays:
                    drives.append(self._create_drive(current_drive_plays, drive_num))
                    drive_num += 1
                
                current_drive_plays = [play]
                current_team = play.possession_team
            else:
                current_drive_plays.append(play)
        
        # Don't forget the last drive
        if current_drive_plays:
            drives.append(self._create_drive(current_drive_plays, drive_num))
        
        return drives
    
    def _create_drive(self, plays: List[Play], drive_num: int) -> DriveInfo:
        """Create a DriveInfo from a list of plays."""
        first = plays[0]
        last = plays[-1]
        
        # Determine drive result
        if last.is_scoring_play:
            if 'touchdown' in last.description.lower():
                result = 'Touchdown'
            else:
                result = 'Field Goal'
        elif last.is_turnover:
            result = 'Turnover'
        elif last.play_type == PlayType.PUNT:
            result = 'Punt'
        else:
            result = 'End of Half' if last.play_type == PlayType.END_HALF else 'Unknown'
        
        return DriveInfo(
            drive_id=f"drive_{drive_num}",
            drive_number=drive_num,
            team=first.possession_team,
            start_quarter=first.quarter,
            start_time=first.time,
            start_yard_line=first.yard_line,
            end_quarter=last.quarter,
            end_time=last.time,
            end_yard_line=last.yard_line,
            result=result,
            plays_count=len(plays),
            yards_gained=sum(p.yards_gained for p in plays),
            plays=plays,
        )
    
    def _calculate_summary(self, plays: List[Play], home: str, away: str) -> Dict[str, int]:
        """Calculate summary statistics."""
        summary = {
            'home_yards': 0,
            'away_yards': 0,
            'home_turnovers': 0,
            'away_turnovers': 0,
        }
        
        for play in plays:
            if play.possession_team == home:
                summary['home_yards'] += play.yards_gained
                if play.is_turnover:
                    summary['home_turnovers'] += 1
            elif play.possession_team == away:
                summary['away_yards'] += play.yards_gained
                if play.is_turnover:
                    summary['away_turnovers'] += 1
        
        return summary


async def main():
    """Test the scraper."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python play_by_play.py <game_uuid>")
        sys.exit(1)
    
    game_uuid = sys.argv[1]
    
    logging.basicConfig(level=logging.INFO)
    
    async with PlayByPlayScraper(headless=False) as scraper:
        data = await scraper.scrape_game(game_uuid)
        
        print(f"\n📊 Scraped {data.total_plays} plays")
        print(f"   Home ({data.home_team}): {data.home_total_yards} yards")
        print(f"   Away ({data.away_team}): {data.away_total_yards} yards")
        print(f"   Drives: {len(data.drives)}")
        
        # Save to file
        output_file = f"play_by_play_{game_uuid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(data.to_dict(), f, indent=2)
        print(f"\n📄 Saved to: {output_file}")


if __name__ == '__main__':
    asyncio.run(main())

