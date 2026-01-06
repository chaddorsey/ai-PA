"""
NFL Pro Insight Category Backfill Script

Backfills the insight_category column for existing insights in the database.
Visits each game's insights page and matches insight titles to determine
if they are 'postgame' or 'preview' insights.

Uses the same authentication pattern as other NFL Pro scrapers.

Usage:
    python backfill_insight_category.py [--season 2025] [--visible] [--dry-run]
    python backfill_insight_category.py --game-id <game_uuid>  # Single game
"""

import asyncio
import argparse
import json
import logging
import os
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from playwright.async_api import async_playwright, Page, BrowserContext

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
CREDENTIALS_PATH = Path(os.environ.get(
    'CREDENTIALS_PATH',
    '/Volumes/main-drive/ai-PA/auto-madden/credentials'
))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'
DATA_PATH = Path(os.environ.get(
    'DATA_PATH',
    '/Volumes/main-drive/ai-PA/auto-madden/data'
))

# Rate limiting constants
MIN_GAME_DELAY_SECONDS = 10
MAX_GAME_DELAY_SECONDS = 20


class InsightCategoryBackfill:
    """
    Backfills insight_category for existing insights by scraping the DOM.
    
    Matches insights by title text to associate them with their category
    (postgame or preview) from the page structure.
    """
    
    BASE_URL = "https://pro.nfl.com"
    
    def __init__(self, season: int = 2025, headless: bool = True, dry_run: bool = False):
        """
        Initialize the backfill scraper.
        
        Args:
            season: NFL season year
            headless: Run browser in headless mode
            dry_run: If True, don't update database, just log what would happen
        """
        self.season = season
        self.headless = headless
        self.dry_run = dry_run
        self._playwright = None
        self._browser = None
        self._context: Optional[BrowserContext] = None
        
        self.db_path = DATA_PATH / f"nfl_insights_{season}.db"
    
    async def start(self):
        """Initialize browser with saved session."""
        state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
        
        if not state_file.exists():
            raise FileNotFoundError(
                f"No NFL Pro session found at {state_file}. "
                "Run session/nfl_pro_login.py first to authenticate."
            )
        
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            storage_state=str(state_file),
            viewport={'width': 1400, 'height': 900},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        )
        logger.info("Browser initialized with saved session")
    
    async def close(self):
        """Clean up resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    def get_games_needing_backfill(self) -> List[Dict]:
        """
        Get games that have insights without categories.
        
        Returns:
            List of dicts with game_id and count of uncategorized insights
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT game_id, COUNT(*) as uncategorized_count
            FROM insights
            WHERE insight_category IS NULL
            GROUP BY game_id
            ORDER BY game_id
        ''')
        
        games = []
        for row in cursor.fetchall():
            games.append({
                'game_id': row[0],
                'uncategorized_count': row[1]
            })
        
        conn.close()
        return games
    
    def get_insights_for_game(self, game_id: str) -> List[Dict]:
        """
        Get all insights for a game that need categorization.
        
        Args:
            game_id: NFL Pro game UUID
            
        Returns:
            List of insight dicts with id and title
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, insight_id, title
            FROM insights
            WHERE game_id = ? AND insight_category IS NULL
        ''', (game_id,))
        
        insights = []
        for row in cursor.fetchall():
            insights.append({
                'db_id': row[0],
                'insight_id': row[1],
                'title': row[2]
            })
        
        conn.close()
        return insights
    
    def normalize_title(self, title: str) -> str:
        """
        Normalize a title for matching by removing extra whitespace.
        
        Args:
            title: Original title text
            
        Returns:
            Normalized title string
        """
        if not title:
            return ""
        # Collapse all whitespace (including newlines) to single spaces
        return ' '.join(title.split()).strip()
    
    async def extract_categories_from_page(self, page: Page) -> Dict[str, str]:
        """
        Extract a mapping of normalized titles to categories from the page.
        
        Uses JavaScript to correctly associate each insight card with its
        parent section header (Postgame Insights vs Game Preview Insights).
        
        Args:
            page: Playwright page object
            
        Returns:
            Dict mapping normalized titles to category ('postgame' or 'preview')
        """
        # Use JavaScript to extract title->category mapping correctly
        # by finding each card's parent section
        extraction_result = await page.evaluate('''
            () => {
                const result = {
                    titleToCategory: {},
                    postgameCount: 0,
                    previewCount: 0
                };
                
                // Find all insight card containers
                const cards = document.querySelectorAll('.insight-card-container');
                
                for (const card of cards) {
                    // Get the title
                    const titleEl = card.querySelector('.insight-card__title');
                    if (!titleEl) continue;
                    
                    const title = titleEl.innerText.trim().replace(/\\s+/g, ' ');
                    if (!title) continue;
                    
                    // Traverse up to find the section header
                    let parent = card.parentElement;
                    let category = null;
                    
                    // Go up the DOM tree looking for .page-title-season
                    while (parent && !category) {
                        // Check if this parent or its children contain the section header
                        const headerEl = parent.querySelector('.page-title-season');
                        if (headerEl) {
                            const headerText = headerEl.innerText.trim();
                            if (headerText.includes('Postgame')) {
                                category = 'postgame';
                            } else if (headerText.includes('Preview')) {
                                category = 'preview';
                            }
                        }
                        parent = parent.parentElement;
                    }
                    
                    // If we couldn't find via traversal, try sibling approach
                    if (!category) {
                        // Find all section divs and their headers
                        const sections = document.querySelectorAll('[data-v-a943ccb2]');
                        for (const section of sections) {
                            const header = section.querySelector('.page-title-season');
                            if (!header) continue;
                            
                            // Check if this section contains our card
                            if (section.contains(card)) {
                                const headerText = header.innerText.trim();
                                if (headerText.includes('Postgame')) {
                                    category = 'postgame';
                                } else if (headerText.includes('Preview')) {
                                    category = 'preview';
                                }
                                break;
                            }
                        }
                    }
                    
                    if (category && title) {
                        result.titleToCategory[title] = category;
                        if (category === 'postgame') {
                            result.postgameCount++;
                        } else {
                            result.previewCount++;
                        }
                    }
                }
                
                return result;
            }
        ''')
        
        if not extraction_result:
            logger.warning("  No categories extracted from page")
            return {}
        
        title_to_category = extraction_result.get('titleToCategory', {})
        postgame_count = extraction_result.get('postgameCount', 0)
        preview_count = extraction_result.get('previewCount', 0)
        
        logger.info(f"    postgame: {postgame_count} insights")
        logger.info(f"    preview: {preview_count} insights")
        logger.info(f"  Extracted {len(title_to_category)} title->category mappings")
        
        return title_to_category
    
    async def backfill_game(self, game_id: str) -> Tuple[int, int]:
        """
        Backfill categories for a single game.
        
        Args:
            game_id: NFL Pro game UUID
            
        Returns:
            Tuple of (matched_count, total_count)
        """
        # Get insights needing categorization
        insights = self.get_insights_for_game(game_id)
        if not insights:
            logger.info(f"  No uncategorized insights for game {game_id[:8]}")
            return (0, 0)
        
        logger.info(f"  {len(insights)} insights need categorization")
        
        # Load the insights page
        page = await self._context.new_page()
        matched = 0
        
        try:
            url = f"{self.BASE_URL}/games/game/{game_id}/insights"
            logger.info(f"  Loading {url}")
            
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await asyncio.sleep(5)  # Wait for content to load
            
            # Scroll to trigger lazy loading
            for _ in range(3):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(1)
            
            # Extract title -> category mapping from the page
            title_to_category = await self.extract_categories_from_page(page)
            
            if not title_to_category:
                logger.warning(f"  No categories extracted from page")
                return (0, len(insights))
            
            logger.info(f"  Extracted {len(title_to_category)} title->category mappings")
            
            # Match insights to categories
            updates = []
            for insight in insights:
                db_title = self.normalize_title(insight['title'])
                
                if db_title in title_to_category:
                    category = title_to_category[db_title]
                    updates.append((category, insight['db_id'], db_title[:50]))
                    matched += 1
                else:
                    # Try fuzzy matching - check if DB title is contained in any page title
                    found = False
                    for page_title, category in title_to_category.items():
                        # Check if significant overlap (first 100 chars match)
                        if db_title[:100] == page_title[:100]:
                            updates.append((category, insight['db_id'], db_title[:50]))
                            matched += 1
                            found = True
                            break
                    
                    if not found:
                        logger.debug(f"    No match for: {db_title[:60]}...")
            
            # Update database
            if updates and not self.dry_run:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                for category, db_id, _ in updates:
                    cursor.execute('''
                        UPDATE insights SET insight_category = ? WHERE id = ?
                    ''', (category, db_id))
                
                conn.commit()
                conn.close()
                logger.info(f"  Updated {len(updates)} insights")
            elif updates and self.dry_run:
                logger.info(f"  [DRY RUN] Would update {len(updates)} insights:")
                for category, db_id, title_preview in updates[:5]:
                    logger.info(f"    - {category}: {title_preview}...")
                if len(updates) > 5:
                    logger.info(f"    ... and {len(updates) - 5} more")
            
        except Exception as e:
            logger.error(f"  Error processing game {game_id[:8]}: {e}")
        
        finally:
            await page.close()
        
        return (matched, len(insights))
    
    async def backfill_all(self):
        """Backfill categories for all games with uncategorized insights."""
        await self.start()
        
        try:
            games = self.get_games_needing_backfill()
            
            print(f"\n{'='*60}")
            print(f"NFL Pro Insight Category Backfill")
            print(f"Season: {self.season}")
            print(f"Games to process: {len(games)}")
            print(f"Dry run: {self.dry_run}")
            print(f"{'='*60}\n")
            
            if not games:
                print("✅ All insights already have categories!")
                return
            
            total_matched = 0
            total_insights = 0
            
            for i, game in enumerate(games, 1):
                game_id = game['game_id']
                count = game['uncategorized_count']
                
                print(f"[{i}/{len(games)}] Game {game_id[:8]}... ({count} insights)")
                
                matched, total = await self.backfill_game(game_id)
                total_matched += matched
                total_insights += total
                
                print(f"  ✓ Matched {matched}/{total}")
                
                # Rate limit between games
                if i < len(games):
                    delay = random.uniform(MIN_GAME_DELAY_SECONDS, MAX_GAME_DELAY_SECONDS)
                    logger.debug(f"  Waiting {delay:.0f}s...")
                    await asyncio.sleep(delay)
            
            print(f"\n{'='*60}")
            print(f"✅ Backfill complete!")
            print(f"   Matched: {total_matched}/{total_insights} insights")
            match_rate = (total_matched / total_insights * 100) if total_insights else 0
            print(f"   Match rate: {match_rate:.1f}%")
            print(f"{'='*60}\n")
            
        finally:
            await self.close()
    
    async def backfill_single_game(self, game_id: str):
        """Backfill categories for a single game."""
        await self.start()
        
        try:
            print(f"\nBackfilling categories for game {game_id}")
            matched, total = await self.backfill_game(game_id)
            print(f"✓ Matched {matched}/{total} insights")
            
        finally:
            await self.close()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Backfill insight_category for existing NFL Pro insights'
    )
    parser.add_argument(
        '--season', type=int, default=2025,
        help='Season year (default: 2025)'
    )
    parser.add_argument(
        '--game-id', type=str, default=None,
        help='Single game UUID to backfill'
    )
    parser.add_argument(
        '--visible', action='store_true',
        help='Show browser window'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help="Don't update database, just show what would happen"
    )
    
    args = parser.parse_args()
    
    backfill = InsightCategoryBackfill(
        season=args.season,
        headless=not args.visible,
        dry_run=args.dry_run
    )
    
    if args.game_id:
        await backfill.backfill_single_game(args.game_id)
    else:
        await backfill.backfill_all()


if __name__ == '__main__':
    asyncio.run(main())

