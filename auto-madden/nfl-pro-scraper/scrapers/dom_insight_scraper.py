"""
NFL Pro DOM-based Insight Scraper

Uses DOM extraction instead of API capture since the insights API 
returns 500 errors for historical games. Handles intermittent loading
with retries, scrolling, and flexible waits.

Usage:
    python dom_insight_scraper.py <game_uuid> [--visible]
    python dom_insight_scraper.py --batch --season 2025 --weeks 1-17
"""

import asyncio
import aiohttp
import hashlib
import json
import logging
import os
import random
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from playwright.async_api import async_playwright, Page, BrowserContext

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Paths
CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '/Volumes/main-drive/ai-PA/auto-madden/credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'
DATA_PATH = Path(os.environ.get('DATA_PATH', '/Volumes/main-drive/ai-PA/auto-madden/data'))


class DOMInsightScraper:
    """
    Scrapes insights from NFL Pro using DOM extraction.
    
    Handles intermittent loading with:
    - Multiple wait strategies
    - Scrolling to trigger lazy loading
    - Retries with backoff
    - Content verification before extraction
    """
    
    BASE_URL = "https://pro.nfl.com"
    
    # Wait configuration
    INITIAL_WAIT = 10  # seconds after page load
    SCROLL_WAIT = 3    # seconds between scrolls
    MAX_WAIT = 90      # maximum total wait time
    RETRY_ATTEMPTS = 3
    
    # Rate limiting
    MIN_GAME_DELAY = 15
    MAX_GAME_DELAY = 30
    
    def __init__(self, season: int = 2025, headless: bool = True, download_images: bool = True):
        self.season = season
        self.headless = headless
        self.download_images = download_images
        self._playwright = None
        self._browser = None
        self._context: Optional[BrowserContext] = None
        
        # Database
        self.db_path = DATA_PATH / f"nfl_insights_{season}.db"
        self._init_database()
        
        # Image storage
        self.image_dir = DATA_PATH / "insight_images"
        self.image_dir.mkdir(parents=True, exist_ok=True)
    
    def _init_database(self):
        """Initialize SQLite database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                insight_id TEXT UNIQUE,
                game_id TEXT,
                season INTEGER,
                week INTEGER,
                title TEXT,
                sub_note TEXT,
                sub_note2 TEXT,
                player_name TEXT,
                position TEXT,
                team_abbr TEXT,
                jersey_number INTEGER,
                second_player_name TEXT,
                second_position TEXT,
                second_team_abbr TEXT,
                second_team_type TEXT,
                image_url TEXT,
                headshot_url TEXT,
                image_cached INTEGER DEFAULT 0,
                tags TEXT,
                date_created TEXT,
                scraped_at TEXT,
                times_served INTEGER DEFAULT 0,
                last_served_game TEXT
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_insights_game ON insights(game_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_insights_player ON insights(player_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_insights_team ON insights(team_abbr)')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scrape_status (
                game_id TEXT PRIMARY KEY,
                insight_count INTEGER,
                scraped_at TEXT,
                method TEXT DEFAULT 'dom'
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized: {self.db_path}")
    
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
        logger.info("Browser initialized")
    
    async def close(self):
        """Clean up resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    async def _wait_for_insights(self, page: Page) -> bool:
        """
        Wait for insight cards to appear with multiple strategies.
        
        Returns True if insights detected, False otherwise.
        """
        total_waited = 0
        
        # Strategy 1: Wait for insight-related elements
        logger.info("  Waiting for insight elements...")
        try:
            await page.wait_for_selector('[class*="insight-card"]', timeout=30000)
            logger.info("  ✓ Found insight-card elements")
            return True
        except:
            pass
        
        total_waited += 30
        
        # Strategy 2: Scroll and wait for lazy loading
        logger.info("  Scrolling to trigger lazy loading...")
        for i in range(5):
            await page.evaluate('window.scrollBy(0, 400)')
            await asyncio.sleep(self.SCROLL_WAIT)
            
            # Check after each scroll
            count = await page.evaluate('document.querySelectorAll("[class*=insight-card]").length')
            if count > 0:
                logger.info(f"  ✓ Found {count} insight-card elements after scroll")
                return True
            
            total_waited += self.SCROLL_WAIT
        
        # Strategy 3: Click on Insights tab if we're on wrong tab
        logger.info("  Trying to click Insights tab...")
        try:
            tab = await page.query_selector('a[href*="insights"], button:has-text("Insights")')
            if tab:
                await tab.click()
                await asyncio.sleep(10)
                count = await page.evaluate('document.querySelectorAll("[class*=insight-card]").length')
                if count > 0:
                    logger.info(f"  ✓ Found {count} after clicking tab")
                    return True
        except Exception as e:
            logger.debug(f"  Tab click failed: {e}")
        
        # Strategy 4: Extended wait
        logger.info("  Extended wait for graphics loading...")
        remaining = self.MAX_WAIT - total_waited
        if remaining > 0:
            await asyncio.sleep(min(remaining, 30))
            count = await page.evaluate('document.querySelectorAll("[class*=insight-card]").length')
            if count > 0:
                logger.info(f"  ✓ Found {count} after extended wait")
                return True
        
        # Check for any insight-related content
        insight_count = await page.evaluate('document.querySelectorAll("[class*=insight]").length')
        logger.info(f"  Final check: {insight_count} insight-related elements")
        
        return insight_count > 2  # More than just containers
    
    async def _extract_insights_js(self, page: Page) -> List[Dict]:
        """Extract insights using JavaScript DOM traversal."""
        
        js_code = """
            (() => {
                const insights = [];
                const seenTitles = new Set();
                
                // Find all insight card containers
                const containers = document.querySelectorAll('[class*="insight-card-container"]');
                
                containers.forEach((container, idx) => {
                    const insight = { id: idx + 1 };
                    
                    // Extract player info from header
                    const headers = container.querySelectorAll('[class*="bg-t-player-team"]');
                    if (headers.length >= 1) {
                        const headerText = headers[0].innerText.trim().split('\\n');
                        insight.player_name = headerText[0] || '';
                        
                        if (headerText[1] && headerText[1].includes(' - ')) {
                            const parts = headerText[1].split(' - ');
                            insight.position = parts[0].trim();
                            insight.team = parts[1].trim();
                        } else if (headerText[1]) {
                            insight.position = headerText[1].trim();
                        }
                    }
                    
                    // Extract secondary entity (opponent/matchup)
                    if (headers.length >= 2) {
                        const secText = headers[1].innerText.trim().split('\\n');
                        insight.secondary_entity = secText[0] || '';
                        insight.secondary_type = secText[1] || '';
                    }
                    
                    // Extract title (main insight text)
                    const title = container.querySelector('[class*="insight-card__title"]');
                    if (title) {
                        insight.title = title.innerText.trim().replace(/\\.\\.\\.$/,'');
                    }
                    
                    // Extract secondary note
                    const note = container.querySelector('[class*="insight-card__note"]');
                    if (note) {
                        insight.sub_note = note.innerText.trim().replace(/\\.\\.\\.$/,'');
                    }
                    
                    // Extract images
                    const imgs = container.querySelectorAll('img');
                    const imageSrcs = [];
                    imgs.forEach(img => {
                        if (img.src && img.src.includes('nflngs.com')) {
                            imageSrcs.push(img.src);
                        }
                    });
                    if (imageSrcs.length > 0) {
                        insight.image_url = imageSrcs[0];
                    }
                    
                    // Extract week/date info
                    const meta = container.querySelector('[class*="insight-card__meta"]');
                    if (meta) {
                        insight.meta = meta.innerText.trim();
                    }
                    
                    // Only add if we have meaningful content
                    if (insight.title && !seenTitles.has(insight.title)) {
                        seenTitles.add(insight.title);
                        insights.push(insight);
                    }
                });
                
                return insights;
            })()
        """
        
        try:
            insights = await page.evaluate(js_code)
            return insights or []
        except Exception as e:
            logger.error(f"JS extraction failed: {e}")
            return []
    
    async def _extract_insights_fallback(self, page: Page) -> List[Dict]:
        """Fallback extraction using element queries."""
        insights = []
        
        try:
            # Get all elements with insight-related content
            elements = await page.query_selector_all('[class*="insight-card-container"]')
            
            for i, el in enumerate(elements):
                insight = {'id': i + 1}
                
                # Get text content
                try:
                    text = await el.inner_text()
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    
                    # First line is usually player name
                    if lines:
                        insight['player_name'] = lines[0]
                    
                    # Look for longer text (the actual insight)
                    for line in lines:
                        if len(line) > 60:
                            insight['title'] = line
                            break
                except:
                    pass
                
                # Get images
                try:
                    imgs = await el.query_selector_all('img')
                    for img in imgs:
                        src = await img.get_attribute('src')
                        if src and 'nflngs.com' in src:
                            insight['image_url'] = src
                            break
                except:
                    pass
                
                if insight.get('title'):
                    insights.append(insight)
        
        except Exception as e:
            logger.error(f"Fallback extraction failed: {e}")
        
        return insights
    
    async def scrape_game(self, game_id: str, week: int = 0) -> List[Dict]:
        """
        Scrape insights for a single game with retry logic.
        
        Key: Load main game page first, then navigate to insights.
        This triggers proper lazy loading of insight content.
        
        Args:
            game_id: NFL Pro game UUID
            week: Week number (for metadata)
        
        Returns:
            List of insight dicts
        """
        insights = []
        
        for attempt in range(self.RETRY_ATTEMPTS):
            page = await self._context.new_page()
            
            try:
                # CRITICAL: Load main game page first to establish session/state
                main_url = f"{self.BASE_URL}/games/game/{game_id}"
                logger.info(f"Attempt {attempt + 1}: Loading main game page...")
                await page.goto(main_url, wait_until='networkidle', timeout=60000)
                await asyncio.sleep(3)
                
                # Now navigate to insights tab
                insights_url = f"{self.BASE_URL}/games/game/{game_id}/insights"
                logger.info(f"  Loading insights tab...")
                await page.goto(insights_url, wait_until='networkidle', timeout=60000)
                
                # Wait for content to load
                logger.info(f"  Waiting 15s for content...")
                await asyncio.sleep(15)
                
                # Scroll to trigger lazy loading
                for i in range(3):
                    await page.evaluate('window.scrollBy(0, 300)')
                    await asyncio.sleep(1)
                
                # Extract using simple Playwright queries (more reliable than JS eval)
                insights = await self._extract_insights_playwright(page)
                
                if insights:
                    logger.info(f"  ✓ Extracted {len(insights)} insights")
                    break
                else:
                    logger.warning(f"  No insights found on attempt {attempt + 1}")
                
            except Exception as e:
                logger.error(f"  Attempt {attempt + 1} error: {e}")
            
            finally:
                await page.close()
            
            # Backoff before retry
            if attempt < self.RETRY_ATTEMPTS - 1:
                wait = (attempt + 1) * 10
                logger.info(f"  Waiting {wait}s before retry...")
                await asyncio.sleep(wait)
        
        # Add metadata to insights
        for insight in insights:
            insight['game_id'] = game_id
            insight['season'] = self.season
            insight['week'] = week
            insight['scraped_at'] = datetime.now().isoformat()
        
        return insights
    
    async def _extract_insights_playwright(self, page: Page) -> List[Dict]:
        """Extract insights using Playwright queries (more reliable than JS eval).
        
        Extracts insights grouped by category (postgame vs preview) by finding
        section headers and their associated insight cards.
        """
        insights = []
        
        # First, try to extract insights by category sections
        categorized_insights = await self._extract_insights_by_category(page)
        if categorized_insights:
            return categorized_insights
        
        # Fallback: extract without category (legacy behavior)
        logger.info("  Falling back to uncategorized extraction")
        containers = await page.query_selector_all('[class*="insight-card-container"]')
        logger.info(f"  Found {len(containers)} insight-card-container elements")
        
        for i, container in enumerate(containers):
            try:
                insight = {'id': i + 1, 'insight_category': None}
                
                # Get full text
                text = await container.inner_text()
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                
                # First line is player/team name
                if lines:
                    insight['player_name'] = lines[0]
                
                # Find the actual insight (longer text)
                for line in lines:
                    if len(line) > 60:
                        insight['title'] = line
                        break
                
                # Get images
                imgs = await container.query_selector_all('img')
                for img in imgs:
                    src = await img.get_attribute('src')
                    if src and 'nflngs.com' in src:
                        insight['image_url'] = src
                        break
                
                if insight.get('title'):
                    insights.append(insight)
            except Exception as e:
                logger.debug(f"Error extracting insight {i}: {e}")
        
        return insights
    
    async def _extract_insights_by_category(self, page: Page) -> List[Dict]:
        """Extract insights grouped by category (postgame/preview).
        
        Uses JavaScript to correctly associate each insight card with its
        parent section header (Postgame Insights vs Game Preview Insights).
        """
        # Use JavaScript to extract insights with correct category association
        extraction_result = await page.evaluate('''
            () => {
                const insights = [];
                let insightId = 0;
                
                // Find all insight card containers
                const cards = document.querySelectorAll('.insight-card-container');
                
                for (const card of cards) {
                    insightId++;
                    const insight = { id: insightId };
                    
                    // Get the title
                    const titleEl = card.querySelector('.insight-card__title');
                    if (titleEl) {
                        insight.title = titleEl.innerText.trim();
                    }
                    
                    // Get the note
                    const noteEl = card.querySelector('.insight-card__note');
                    if (noteEl) {
                        insight.sub_note = noteEl.innerText.trim();
                    }
                    
                    // Get player name
                    const nameEl = card.querySelector('.name a');
                    if (nameEl) {
                        insight.player_name = nameEl.innerText.trim();
                    }
                    
                    // Get position and team from meta
                    const metaEl = card.querySelector('.meta');
                    if (metaEl) {
                        const metaText = metaEl.innerText.trim();
                        const parts = metaText.split(' - ');
                        if (parts.length >= 2) {
                            insight.team = parts[parts.length - 1].trim();
                            const posParts = parts[0].trim().split(' ');
                            if (posParts.length > 0) {
                                insight.position = posParts[0];
                            }
                        }
                    }
                    
                    // Get image URL
                    const imgs = card.querySelectorAll('img');
                    for (const img of imgs) {
                        const src = img.src;
                        if (src && (src.includes('nfl.com') || src.includes('nflngs.com'))) {
                            insight.image_url = src;
                            break;
                        }
                    }
                    
                    // Determine category by traversing up to find section header
                    let parent = card.parentElement;
                    let category = null;
                    
                    while (parent && !category) {
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
                    
                    // Fallback: check all sections
                    if (!category) {
                        const sections = document.querySelectorAll('[data-v-a943ccb2]');
                        for (const section of sections) {
                            const header = section.querySelector('.page-title-season');
                            if (!header) continue;
                            
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
                    
                    insight.insight_category = category;
                    
                    if (insight.title) {
                        insights.push(insight);
                    }
                }
                
                return insights;
            }
        ''')
        
        if not extraction_result:
            logger.debug("  No insights extracted via JS")
            return []
        
        # Count by category for logging
        postgame_count = sum(1 for i in extraction_result if i.get('insight_category') == 'postgame')
        preview_count = sum(1 for i in extraction_result if i.get('insight_category') == 'preview')
        
        logger.info(f"  Extracted {len(extraction_result)} insights (postgame: {postgame_count}, preview: {preview_count})")
        
        return extraction_result
    
    async def download_image(self, url: str, insight_id: str) -> Optional[str]:
        """Download an image and return the local filename."""
        if not url:
            return None
        
        try:
            # Create filename from URL hash
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            ext = '.png' if '.png' in url else '.jpg'
            filename = f"{insight_id}_{url_hash}{ext}"
            filepath = self.image_dir / filename
            
            if filepath.exists():
                return filename
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        with open(filepath, 'wb') as f:
                            f.write(content)
                        logger.debug(f"Downloaded image: {filename}")
                        return filename
        except Exception as e:
            logger.debug(f"Could not download image {url[:50]}: {e}")
        
        return None
    
    async def save_insights(self, insights: List[Dict], game_id: str) -> int:
        """Save insights to database, optionally downloading images."""
        if not insights:
            return 0
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Add local_image column if not exists
        try:
            cursor.execute('ALTER TABLE insights ADD COLUMN local_image TEXT')
            conn.commit()
        except:
            pass
        
        # Add insight_category column if not exists
        try:
            cursor.execute('ALTER TABLE insights ADD COLUMN insight_category TEXT')
            conn.commit()
        except:
            pass
        
        saved = 0
        
        for insight in insights:
            try:
                insight_id = f"{game_id[:8]}_{insight.get('id', 0)}"
                
                # Download image if enabled
                local_image = None
                if self.download_images and insight.get('image_url'):
                    local_image = await self.download_image(insight['image_url'], insight_id)
                
                cursor.execute('''
                    INSERT OR REPLACE INTO insights (
                        insight_id, game_id, season, week, title, sub_note,
                        player_name, position, team_abbr,
                        second_player_name, second_team_type,
                        image_url, local_image, image_cached, scraped_at,
                        insight_category
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    insight_id,
                    insight.get('game_id', ''),
                    insight.get('season', self.season),
                    insight.get('week', 0),
                    insight.get('title', ''),
                    insight.get('sub_note', ''),
                    insight.get('player_name', ''),
                    insight.get('position', ''),
                    insight.get('team', ''),
                    insight.get('secondary_entity', ''),
                    insight.get('secondary_type', ''),
                    insight.get('image_url', ''),
                    local_image,
                    1 if local_image else 0,
                    insight.get('scraped_at', datetime.now().isoformat()),
                    insight.get('insight_category')
                ))
                saved += 1
            except Exception as e:
                logger.warning(f"Error saving insight: {e}")
        
        # Update scrape status
        cursor.execute('''
            INSERT OR REPLACE INTO scrape_status (game_id, insight_count, scraped_at, method)
            VALUES (?, ?, ?, 'dom')
        ''', (game_id, saved, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        return saved
    
    def get_games_to_scrape(self, weeks: List[int] = None) -> List[Dict]:
        """Get games from plays database that haven't been scraped for insights."""
        plays_db = DATA_PATH / f"nfl_plays_{self.season}.db"
        
        if not plays_db.exists():
            raise FileNotFoundError(f"Plays database not found: {plays_db}")
        
        # Get all games
        conn = sqlite3.connect(plays_db)
        cursor = conn.cursor()
        
        week_filter = ""
        if weeks:
            week_filter = f"AND week IN ({','.join(map(str, weeks))})"
        
        cursor.execute(f'''
            SELECT game_id, week, home_team, away_team
            FROM games
            WHERE season = ? {week_filter}
            ORDER BY week, game_id
        ''', (self.season,))
        
        games = [{'game_id': r[0], 'week': r[1], 'home_team': r[2], 'away_team': r[3]} 
                 for r in cursor.fetchall()]
        conn.close()
        
        # Filter out already scraped
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT game_id FROM scrape_status')
        scraped = {r[0] for r in cursor.fetchall()}
        conn.close()
        
        to_scrape = [g for g in games if g['game_id'] not in scraped]
        
        return to_scrape, len(games), len(scraped)
    
    async def scrape_batch(self, weeks: List[int] = None, reverse: bool = True):
        """Scrape insights for multiple games.
        
        Args:
            weeks: Specific weeks to scrape
            reverse: If True, scrape week 18 first down to week 1
        """
        await self.start()
        
        try:
            to_scrape, total, already_scraped = self.get_games_to_scrape(weeks)
            
            # Sort by week (descending if reverse=True)
            to_scrape.sort(key=lambda g: g['week'], reverse=reverse)
            
            print(f"\n{'='*60}")
            print(f"NFL Pro DOM Insight Scraper (with image download)")
            print(f"Season: {self.season}")
            print(f"Order: {'Week 18 → 1' if reverse else 'Week 1 → 18'}")
            print(f"Total games: {total}")
            print(f"Already scraped: {already_scraped}")
            print(f"To scrape: {len(to_scrape)}")
            print(f"Image download: {'Enabled' if self.download_images else 'Disabled'}")
            print(f"{'='*60}\n")
            
            if not to_scrape:
                print("✅ All games already scraped!")
                return
            
            total_insights = 0
            total_images = 0
            successful = 0
            
            for i, game in enumerate(to_scrape, 1):
                game_id = game['game_id']
                week = game['week']
                teams = f"{game['away_team']} @ {game['home_team']}"
                
                print(f"[{i}/{len(to_scrape)}] Week {week}: {teams}...", flush=True)
                
                insights = await self.scrape_game(game_id, week)
                saved = await self.save_insights(insights, game_id)
                
                # Count images downloaded
                images = sum(1 for ins in insights if ins.get('image_url'))
                
                if saved > 0:
                    print(f"  ✓ {saved} insights, {images} images")
                    total_insights += saved
                    total_images += images
                    successful += 1
                else:
                    print(f"  ⚠ No insights")
                
                # Rate limit
                if i < len(to_scrape):
                    delay = random.uniform(self.MIN_GAME_DELAY, self.MAX_GAME_DELAY)
                    print(f"  Waiting {delay:.0f}s...")
                    await asyncio.sleep(delay)
            
            print(f"\n{'='*60}")
            print(f"✅ Complete!")
            print(f"   Games scraped: {successful}/{len(to_scrape)}")
            print(f"   Total insights: {total_insights}")
            print(f"   Total images: {total_images}")
            print(f"{'='*60}\n")
        
        finally:
            await self.close()


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='NFL Pro DOM Insight Scraper')
    parser.add_argument('game_uuid', nargs='?', help='Single game UUID to scrape')
    parser.add_argument('--batch', action='store_true', help='Batch scrape mode')
    parser.add_argument('--season', type=int, default=2025, help='Season year')
    parser.add_argument('--weeks', type=str, default=None, help='Weeks (e.g., "1-17")')
    parser.add_argument('--visible', action='store_true', help='Show browser')
    parser.add_argument('--forward', action='store_true', help='Scrape week 1 to 18 (default is 18 to 1)')
    parser.add_argument('--no-images', action='store_true', help='Skip image downloads')
    
    args = parser.parse_args()
    
    # Parse weeks
    weeks = None
    if args.weeks:
        if '-' in args.weeks:
            start, end = args.weeks.split('-')
            weeks = list(range(int(start), int(end) + 1))
        else:
            weeks = [int(w) for w in args.weeks.split(',')]
    
    scraper = DOMInsightScraper(
        season=args.season, 
        headless=not args.visible,
        download_images=not args.no_images
    )
    
    if args.batch:
        await scraper.scrape_batch(weeks=weeks, reverse=not args.forward)
    elif args.game_uuid:
        await scraper.start()
        try:
            insights = await scraper.scrape_game(args.game_uuid, week=0)
            saved = await scraper.save_insights(insights, args.game_uuid)
            images = sum(1 for ins in insights if ins.get('image_url'))
            print(f"\n✅ Scraped {len(insights)} insights, saved {saved}, {images} images")
            
            for i, insight in enumerate(insights[:5], 1):
                print(f"{i}. {insight.get('player_name', 'N/A')}: {insight.get('title', '')[:60]}...")
                if insight.get('image_url'):
                    print(f"   📸 {insight['image_url'][:60]}...")
        finally:
            await scraper.close()
    else:
        parser.print_help()


if __name__ == '__main__':
    asyncio.run(main())

