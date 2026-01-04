"""
Insights Scraper for NFL Pro

Scrapes narrative insights from the NFL Pro insights tab, categorizing them
by entity type, scope, and relevance for use in the game companion.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import hashlib

from playwright.async_api import async_playwright, Page

# Import models
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from models.insights import (
    Insight, InsightEntity, InsightType, InsightScope,
    EntityType, InsightCollection
)

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '../credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'


class InsightsScraper:
    """Scrapes narrative insights from NFL Pro."""
    
    BASE_URL = "https://pro.nfl.com/games/game"
    
    # Keywords for categorization
    POSITION_KEYWORDS = {
        'quarterback': ['quarterback', 'qb', 'passer', 'throwing'],
        'receiver': ['receiver', 'wr', 'te', 'receiving', 'catches'],
        'rusher': ['running back', 'rb', 'rushing', 'carries'],
        'defense': ['defense', 'defensive', 'sack', 'interception', 'tackle'],
        'special_teams': ['kicker', 'punter', 'special teams', 'kick return'],
    }
    
    SITUATION_TAGS = {
        'red_zone': ['red zone', 'inside the 20', 'goal line'],
        'third_down': ['third down', '3rd down', 'third-down'],
        'fourth_quarter': ['fourth quarter', '4th quarter', 'late game'],
        'scoring': ['touchdown', 'field goal', 'scoring', 'points'],
        'turnover': ['interception', 'fumble', 'turnover'],
        'pressure': ['pressure', 'sack', 'hurry', 'blitz'],
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
    
    async def scrape_game(self, game_uuid: str, home_team: str = "", away_team: str = "") -> InsightCollection:
        """Scrape insights for a game."""
        url = f"{self.BASE_URL}/{game_uuid}/insights"
        
        page = await self._context.new_page()
        logger.info(f"Navigating to: {url}")
        
        try:
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await asyncio.sleep(3)
            
            # Check for auth issues
            if 'login' in page.url.lower():
                raise Exception("Session expired - please re-authenticate")
            
            # Extract teams if not provided
            if not home_team or not away_team:
                home_team, away_team = await self._extract_teams(page)
            
            # Scrape all insight cards
            insights = await self._scrape_insights(page, home_team, away_team)
            
            collection = InsightCollection(
                game_uuid=game_uuid,
                home_team=home_team,
                away_team=away_team,
                insights=insights,
                scraped_at=datetime.now(),
            )
            
            logger.info(f"Scraped {len(insights)} insights for game {game_uuid}")
            return collection
            
        finally:
            await page.close()
    
    async def _extract_teams(self, page: Page) -> tuple:
        """Extract home and away team from page."""
        # Try common selectors
        selectors = [
            '[class*="team"]',
            '[data-testid*="team"]',
        ]
        
        for selector in selectors:
            elements = await page.query_selector_all(selector)
            teams = []
            for elem in elements[:4]:
                text = await elem.inner_text()
                text = text.strip()
                if len(text) == 2 or len(text) == 3:
                    if text.isupper():
                        teams.append(text)
            
            if len(teams) >= 2:
                return teams[1], teams[0]  # home, away
        
        return "HOME", "AWAY"
    
    async def _scrape_insights(self, page: Page, home_team: str, away_team: str) -> List[Insight]:
        """Scrape all insight cards from the page."""
        insights = []
        
        # Wait for insight content
        await asyncio.sleep(2)
        
        # Try various selectors for insight cards
        card_selectors = [
            '[class*="insight-card"]',
            '[class*="InsightCard"]',
            '[class*="insight"]',
            '[data-testid*="insight"]',
            '[class*="Card"]',
            'article',
        ]
        
        cards = []
        for selector in card_selectors:
            cards = await page.query_selector_all(selector)
            if len(cards) >= 2:
                break
        
        logger.info(f"Found {len(cards)} potential insight cards")
        
        for i, card in enumerate(cards):
            try:
                insight = await self._parse_insight_card(card, i, home_team, away_team)
                if insight:
                    insights.append(insight)
            except Exception as e:
                logger.warning(f"Error parsing insight card {i}: {e}")
        
        return insights
    
    async def _parse_insight_card(
        self, 
        card, 
        index: int,
        home_team: str,
        away_team: str
    ) -> Optional[Insight]:
        """Parse a single insight card."""
        try:
            full_text = await card.inner_text()
            if not full_text or len(full_text.strip()) < 50:
                return None
            
            # Skip navigation or UI elements
            skip_patterns = ['box score', 'play-by-play', 'overview', 'insights tab']
            if any(p in full_text.lower() for p in skip_patterns):
                return None
            
            # Extract headline
            headline = ""
            headline_elem = await card.query_selector('h2, h3, h4, [class*="headline"], [class*="title"]')
            if headline_elem:
                headline = (await headline_elem.inner_text()).strip()
            
            # Extract paragraphs
            paragraphs = await card.query_selector_all('p')
            para_texts = []
            for p in paragraphs:
                text = (await p.inner_text()).strip()
                if text and len(text) > 20:
                    para_texts.append(text)
            
            if len(para_texts) < 1 and not headline:
                return None
            
            # Primary is first paragraph, secondary is rest
            primary_text = para_texts[0] if para_texts else full_text[:300]
            secondary_text = ' '.join(para_texts[1:]) if len(para_texts) > 1 else ""
            
            # Parse entities from text
            entities = self._extract_entities(full_text, home_team, away_team)
            
            # Determine insight type and scope
            insight_type = InsightType.SINGLE_ENTITY if len(entities) <= 1 else InsightType.DUAL_ENTITY
            scope = None
            if insight_type == InsightType.DUAL_ENTITY:
                teams = list(set(e.team for e in entities))
                scope = InsightScope.DUAL_TEAM if len(teams) > 1 else InsightScope.SINGLE_TEAM
            
            # Generate unique ID
            insight_id = hashlib.md5(f"{full_text[:100]}_{index}".encode()).hexdigest()[:12]
            
            # Categorize
            categories = self._categorize_insight(full_text)
            relevance_tags = self._get_relevance_tags(full_text)
            
            # Extract any statistics mentioned
            stats = self._extract_stats(full_text)
            
            return Insight(
                insight_id=insight_id,
                insight_type=insight_type,
                scope=scope,
                entities=entities,
                headline=headline,
                primary_text=primary_text,
                secondary_text=secondary_text,
                stats=stats,
                categories=categories,
                relevance_tags=relevance_tags,
                scraped_at=datetime.now(),
            )
            
        except Exception as e:
            logger.warning(f"Error in _parse_insight_card: {e}")
            return None
    
    def _extract_entities(self, text: str, home_team: str, away_team: str) -> List[InsightEntity]:
        """Extract player and team unit entities from insight text."""
        entities = []
        
        # Look for player names (First Last pattern)
        player_pattern = r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b'
        player_matches = re.findall(player_pattern, text)
        
        # Common first names to filter
        skip_names = ['The', 'This', 'That', 'These', 'When', 'Last', 'First', 'Next', 'Their']
        
        for first, last in player_matches[:4]:  # Limit to 4 potential players
            if first not in skip_names:
                # Try to determine team from context
                team = self._guess_team(f"{first} {last}", text, home_team, away_team)
                position = self._guess_position(f"{first} {last}", text)
                
                entities.append(InsightEntity(
                    name=f"{first} {last}",
                    team=team,
                    entity_type=EntityType.PLAYER,
                    position=position,
                ))
        
        # Look for team units
        unit_patterns = [
            (r'\b' + home_team + r"'?s?\s+(defense|offense|offensive line|secondary)", home_team),
            (r'\b' + away_team + r"'?s?\s+(defense|offense|offensive line|secondary)", away_team),
            (r'\b(49ers|Seahawks|Cowboys|Giants|etc)\s+(defense|offense)', None),
        ]
        
        for pattern, team in unit_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                unit_name = match if isinstance(match, str) else match[-1]
                entities.append(InsightEntity(
                    name=unit_name.title(),
                    team=team or "",
                    entity_type=EntityType.TEAM_UNIT,
                    unit_type=unit_name.lower(),
                ))
        
        return entities[:4]  # Limit to 4 entities max
    
    def _guess_team(self, player_name: str, text: str, home: str, away: str) -> str:
        """Guess which team a player belongs to based on context."""
        # Look for team mention near player name
        text_lower = text.lower()
        name_lower = player_name.lower()
        
        name_idx = text_lower.find(name_lower)
        if name_idx >= 0:
            context = text_lower[max(0, name_idx - 50):name_idx + len(name_lower) + 50]
            
            if home.lower() in context:
                return home
            if away.lower() in context:
                return away
        
        return ""
    
    def _guess_position(self, player_name: str, text: str) -> Optional[str]:
        """Guess player position from context."""
        text_lower = text.lower()
        
        position_patterns = {
            'QB': ['quarterback', 'qb ', 'passing', 'throws', 'thrown'],
            'RB': ['running back', 'rb ', 'rushes', 'carries'],
            'WR': ['receiver', 'wr ', 'receiving', 'catches', 'caught'],
            'TE': ['tight end', 'te '],
            'LB': ['linebacker', 'lb '],
            'CB': ['cornerback', 'cb '],
            'S': ['safety', ' s '],
            'DE': ['defensive end', 'de ', 'edge'],
            'DT': ['defensive tackle', 'dt '],
        }
        
        for pos, keywords in position_patterns.items():
            if any(kw in text_lower for kw in keywords):
                return pos
        
        return None
    
    def _categorize_insight(self, text: str) -> List[str]:
        """Categorize the insight by topic."""
        categories = []
        text_lower = text.lower()
        
        for category, keywords in self.POSITION_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                categories.append(category)
        
        return categories
    
    def _get_relevance_tags(self, text: str) -> List[str]:
        """Get situational relevance tags for the insight."""
        tags = []
        text_lower = text.lower()
        
        for tag, keywords in self.SITUATION_TAGS.items():
            if any(kw in text_lower for kw in keywords):
                tags.append(tag)
        
        return tags
    
    def _extract_stats(self, text: str) -> Dict[str, Any]:
        """Extract numerical statistics from the text."""
        stats = {}
        
        # Look for common stat patterns
        patterns = [
            (r'(\d+)\s+yards?', 'yards'),
            (r'(\d+)\s+touchdowns?', 'touchdowns'),
            (r'(\d+)\s+receptions?', 'receptions'),
            (r'(\d+)\s+catches?', 'catches'),
            (r'(\d+)\s+sacks?', 'sacks'),
            (r'(\d+)\s+interceptions?', 'interceptions'),
            (r'(\d+)\s+completions?', 'completions'),
            (r'(\d+)%', 'percentage'),
            (r'(\d+\.\d+)\s+(?:yards|YPC|YPA)', 'avg_yards'),
        ]
        
        for pattern, stat_name in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1))
                    stats[stat_name] = value
                except ValueError:
                    pass
        
        return stats


async def main():
    """Test the scraper."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python insights.py <game_uuid> [home_team] [away_team]")
        sys.exit(1)
    
    game_uuid = sys.argv[1]
    home = sys.argv[2] if len(sys.argv) > 2 else ""
    away = sys.argv[3] if len(sys.argv) > 3 else ""
    
    logging.basicConfig(level=logging.INFO)
    
    async with InsightsScraper(headless=False) as scraper:
        collection = await scraper.scrape_game(game_uuid, home, away)
        
        print(f"\n📊 Scraped {len(collection.insights)} insights")
        
        for insight in collection.insights[:5]:
            print(f"\n--- {insight.insight_type.value} ---")
            print(f"Headline: {insight.headline[:60]}...")
            print(f"Entities: {[e.name for e in insight.entities]}")
            print(f"Categories: {insight.categories}")
        
        # Save to file
        output_file = f"insights_{game_uuid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(collection.to_dict(), f, indent=2)
        print(f"\n📄 Saved to: {output_file}")


if __name__ == '__main__':
    asyncio.run(main())

