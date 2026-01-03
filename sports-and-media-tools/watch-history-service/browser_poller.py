"""
Browser-based Watch History Poller

Uses Playwright with saved browser states to scrape Continue Watching
from streaming services that don't have accessible APIs.

Supports: Netflix, Apple TV+, Disney+, Prime Video
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from playwright.async_api import async_playwright, BrowserContext, Page

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '/app/credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'


@dataclass
class WatchHistoryEntry:
    """Represents a single watch history entry."""
    service: str
    title: str
    content_type: str
    content_id: str
    episode_title: Optional[str] = None
    season_number: Optional[int] = None
    episode_number: Optional[int] = None
    watch_date: Optional[str] = None
    progress_percent: Optional[int] = None
    deep_link_id: Optional[str] = None


@dataclass
class WatchlistEntry:
    """Represents a single watchlist/My List entry."""
    service: str
    title: str
    content_type: str
    content_id: str
    added_at: Optional[str] = None
    deep_link_id: Optional[str] = None


@dataclass
class RecommendationEntry:
    """Represents a single recommendation from a streaming service."""
    service: str
    title: str
    content_type: str
    content_id: str
    recommendation_type: str  # 'because_you_watched', 'trending', 'new_release', 'top_pick'
    category: Optional[str] = None  # The row/shelf name
    position: Optional[int] = None  # Position in the row
    deep_link_id: Optional[str] = None


class BrowserPoller:
    """Scrapes Continue Watching using Playwright with saved browser states."""
    
    SERVICE_CONFIG = {
        'netflix': {
            'name': 'Netflix',
            'url': 'https://www.netflix.com/browse',
            'continue_watching_selector': '[data-list-context="continueWatching"] .slider-item, [data-list-context="queue"] .slider-item',
            'title_selector': '.fallback-text, .title-card-container p',
            'profile_selector': '.profile-icon',
        },
        'disney': {
            'name': 'Disney+',
            'url': 'https://www.disneyplus.com/home',
            'continue_watching_selector': '[data-testid="continue-watching"] [data-testid="set-item"]',
            'title_selector': '[data-testid="title"]',
            'profile_selector': '[data-testid="profile-avatar"]',
        },
        'apple': {
            'name': 'Apple TV+',
            'url': 'https://tv.apple.com/',
            'continue_watching_selector': '.shelf-grid__list-item, .up-next-item',
            'title_selector': '.canvas-lockup__title, .up-next-item__title',
            'profile_selector': '[data-testid="account-menu"]',
        },
        'prime': {
            'name': 'Prime Video',
            'url': 'https://www.amazon.com/gp/video/storefront',
            'continue_watching_selector': '[data-testid="card-overlay"], .DVWebNode-detail-titles-wrapper',
            'title_selector': '.av-card-title, [data-testid="title"]',
            'profile_selector': '#nav-link-accountList',
        },
        'max': {
            'name': 'Max',
            'url': 'https://play.max.com/',
            'continue_watching_selector': '[data-testid="continue-watching"] a',
            'title_selector': '[class*="title"]',
            'profile_selector': '[data-testid="profile-selector"]',
        },
        'hulu': {
            'name': 'Hulu',
            'url': 'https://www.hulu.com/hub/home',
            'continue_watching_selector': '[data-testid="tile"]',
            'title_selector': '[class*="title"]',
            'profile_selector': '[data-testid="profile-menu"]',
        },
    }
    
    def __init__(self):
        self._playwright = None
        self._browser = None
    
    async def _get_browser(self):
        """Get or create the browser instance."""
        if self._browser is None or not self._browser.is_connected():
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                ]
            )
        return self._browser
    
    async def _create_context(self, service: str) -> Optional[BrowserContext]:
        """Create a browser context with saved state."""
        state_file = BROWSER_STATES_PATH / f'{service}_state.json'
        
        if not state_file.exists():
            logger.warning(f"No browser state found for {service}")
            return None
        
        browser = await self._get_browser()
        
        try:
            context = await browser.new_context(
                storage_state=str(state_file),
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            )
            return context
        except Exception as e:
            logger.error(f"Error creating context for {service}: {e}")
            return None
    
    async def scrape_netflix(self) -> List[WatchHistoryEntry]:
        """Scrape watch history from Netflix's dedicated viewing activity page."""
        entries = []
        context = await self._create_context('netflix')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            # First go to browse to handle any profile selection
            logger.info("Netflix: Navigating to browse page...")
            await page.goto('https://www.netflix.com/browse', wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)
            
            # Check if we need to select a profile
            page_text = await page.inner_text('body')
            is_profile_page = '/profiles' in page.url or "Who's watching" in page_text
            
            if is_profile_page:
                logger.info("Netflix: Profile selection required, selecting first profile...")
                profile_selectors = ['.profile-icon', '.profile-link', 'a[href*="/browse"]', 'li.profile']
                for sel in profile_selectors:
                    profiles = await page.query_selector_all(sel)
                    if profiles:
                        await profiles[0].click()
                        logger.info(f"Netflix: Clicked profile with {sel}")
                        await asyncio.sleep(5)
                        break
            
            # Now go to the viewing activity page
            logger.info("Netflix: Navigating to viewing activity...")
            await page.goto('https://www.netflix.com/viewingactivity', wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)
            
            # Parse the viewing activity list
            logger.info("Netflix: Parsing viewing activity...")
            
            # The viewing activity page has a list of watched items
            items = await page.query_selector_all('.retableRow, .viewing-item, li.retableRow')
            logger.info(f"Netflix: Found {len(items)} history items")
            
            for item in items[:50]:  # Get more history
                try:
                    # Get title - usually in a link
                    title_elem = await item.query_selector('a, .title')
                    title = await title_elem.inner_text() if title_elem else None
                    
                    if not title:
                        continue
                    
                    # Get the link for content ID
                    link = await item.query_selector('a')
                    href = await link.get_attribute('href') if link else ''
                    
                    content_id = ''
                    if href:
                        match = re.search(r'/title/(\d+)', href)
                        if match:
                            content_id = match.group(1)
                    
                    # Get date if available
                    date_elem = await item.query_selector('.date, .col.date')
                    watch_date = await date_elem.inner_text() if date_elem else None
                    
                    # Parse episode info from title (e.g., "Show Name: Season 1: Episode Title")
                    episode_title = None
                    season_num = None
                    episode_num = None
                    
                    if ':' in title:
                        parts = title.split(':')
                        title = parts[0].strip()
                        if len(parts) > 1:
                            episode_title = ':'.join(parts[1:]).strip()
                            # Try to extract season/episode
                            season_match = re.search(r'Season (\d+)', episode_title)
                            if season_match:
                                season_num = int(season_match.group(1))
                    
                    entry = WatchHistoryEntry(
                        service='netflix',
                        title=title.strip(),
                        content_type='show',
                        content_id=content_id,
                        episode_title=episode_title,
                        season_number=season_num,
                        watch_date=watch_date,
                        deep_link_id=content_id
                    )
                    entries.append(entry)
                except Exception as e:
                    logger.debug(f"Netflix: Error parsing item: {e}")
            
            logger.info(f"Netflix: Found {len(entries)} watch history items")
            await page.close()
            
        except Exception as e:
            logger.error(f"Netflix scraping error: {e}")
        finally:
            await context.close()
        
        return entries
    
    async def scrape_disney(self) -> List[WatchHistoryEntry]:
        """Scrape Continue Watching from Disney+."""
        entries = []
        context = await self._create_context('disney')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            logger.info("Disney+: Navigating to home...")
            await page.goto('https://www.disneyplus.com/home', wait_until='networkidle', timeout=45000)
            await asyncio.sleep(5)
            
            # Check current URL
            logger.info(f"Disney+: Current URL: {page.url}")
            
            # Check for profile selection page
            if 'select-profile' in page.url or 'profile' in page.url.lower():
                logger.info("Disney+: Profile selection page detected, navigating directly to home...")
                
                # Instead of trying to click profile (which leads to avatar selection),
                # try navigating directly to home - sometimes the session has profile context
                await page.goto('https://www.disneyplus.com/home', wait_until='networkidle', timeout=30000)
                await asyncio.sleep(5)
                
                # If still on profile page, need to actually select
                if 'select-profile' in page.url or 'profile' in page.url.lower():
                    logger.info("Disney+: Still on profile page, trying to select existing profile...")
                    
                    # Wait for profiles to load
                    await asyncio.sleep(3)
                    
                    # Look for existing profiles (not "add profile")
                    # Existing profiles usually have user names/icons, not "+" signs
                    profile_selectors = [
                        # Try to find profiles with actual user content
                        '[data-testid="profile-avatar"]:not([data-testid*="add"])',
                        'button[class*="profile"]:not([class*="add"]):not([class*="new"])',
                        '[class*="ProfileCard"]:not([class*="add"])',
                        # Disney+ often uses these
                        'div[role="button"][class*="profile"]',
                        'a[href*="/home"]',
                    ]
                    
                    clicked = False
                    for sel in profile_selectors:
                        try:
                            profiles = await page.query_selector_all(sel)
                            logger.info(f"Disney+: Found {len(profiles)} elements with {sel}")
                            if profiles and len(profiles) > 0:
                                # Click the first non-add profile
                                await profiles[0].click()
                                clicked = True
                                logger.info(f"Disney+: Clicked profile with {sel}")
                                await asyncio.sleep(5)
                                break
                        except Exception as e:
                            logger.debug(f"Disney+: Profile selector {sel} failed: {e}")
                    
                    if not clicked:
                        # Try keyboard navigation
                        logger.info("Disney+: Trying keyboard navigation...")
                        await page.keyboard.press('Tab')
                        await asyncio.sleep(0.5)
                        await page.keyboard.press('Enter')
                        await asyncio.sleep(5)
            
            # Wait for navigation
            await asyncio.sleep(3)
            logger.info(f"Disney+: After profile, URL: {page.url}")
            
            # Handle avatar selection page (skip it)
            if 'select-avatar' in page.url or 'avatar' in page.url:
                logger.info("Disney+: On avatar selection, navigating to home...")
                await page.goto('https://www.disneyplus.com/home', wait_until='networkidle', timeout=30000)
                await asyncio.sleep(5)
            
            # If still on profile page, try direct navigation
            if 'profile' in page.url.lower() or 'select' in page.url.lower():
                logger.info("Disney+: Still on profile page, forcing navigation to home...")
                await page.goto('https://www.disneyplus.com/home', wait_until='networkidle', timeout=30000)
                await asyncio.sleep(5)
            
            logger.info(f"Disney+: Final URL: {page.url}")
            
            # Look for Continue Watching with multiple selectors
            logger.info("Disney+: Looking for Continue Watching section...")
            
            cw_selectors = [
                'section:has-text("Continue Watching")',
                '[data-testid="continue-watching"]',
                '[aria-label*="Continue Watching"]',
                '[class*="continue-watching"]',
                'div[class*="ContinueWatching"]',
            ]
            
            cw_section = None
            for sel in cw_selectors:
                try:
                    cw_section = await page.query_selector(sel)
                    if cw_section:
                        logger.info(f"Disney+: Found section with {sel}")
                        break
                except Exception:
                    pass
            
            if cw_section:
                # Try multiple item selectors
                item_selectors = [
                    '[data-testid="set-item"]',
                    '[data-testid="content-tile"]',
                    'a[href*="/series/"], a[href*="/movies/"]',
                    '[class*="tile"]',
                ]
                
                items = []
                for sel in item_selectors:
                    items = await cw_section.query_selector_all(sel)
                    if items:
                        logger.info(f"Disney+: Found {len(items)} items with {sel}")
                        break
                
                for item in items[:15]:
                    try:
                        # Try multiple title selectors
                        title = None
                        title_selectors = ['[data-testid="title"]', '.title', 'span', 'p']
                        for sel in title_selectors:
                            title_elem = await item.query_selector(sel)
                            if title_elem:
                                title = await title_elem.inner_text()
                                if title and title.strip():
                                    break
                        
                        if not title:
                            title = "Unknown"
                        
                        # Get content ID from href
                        content_id = ''
                        link = await item.query_selector('a') if not (await item.evaluate('el => el.tagName')) == 'A' else item
                        if link:
                            href = await link.get_attribute('href')
                            if href:
                                match = re.search(r'/(series|movies)/([^/]+)', href)
                                if match:
                                    content_id = match.group(2)
                        
                        entry = WatchHistoryEntry(
                            service='disney',
                            title=title.strip(),
                            content_type='show',
                            content_id=content_id,
                            deep_link_id=content_id
                        )
                        entries.append(entry)
                    except Exception as e:
                        logger.debug(f"Disney+: Error parsing item: {e}")
            else:
                # Debug: log what sections we can find
                sections = await page.query_selector_all('section, [class*="shelf"], [class*="row"]')
                logger.info(f"Disney+: Found {len(sections)} sections on page")
                
                # Wait longer for content to render
                await asyncio.sleep(5)
                
                # Debug: check page content
                page_text = await page.inner_text('body')
                logger.info(f"Disney+: Page text length: {len(page_text)}")
                if len(page_text) < 500:
                    logger.warning(f"Disney+: Page appears empty or errored. Content: {page_text[:200]}")
                
                # Check for any links at all
                all_links = await page.query_selector_all('a[href]')
                logger.info(f"Disney+: Total links on page: {len(all_links)}")
                
                # Analyze all link patterns on the page
                all_hrefs = []
                for link in all_links[:100]:
                    href = await link.get_attribute('href') or ''
                    if href and not href.startswith('http') and href != '/home':
                        all_hrefs.append(href)
                
                # Log unique path patterns
                path_patterns = set()
                for href in all_hrefs:
                    parts = href.split('/')
                    if len(parts) >= 2:
                        path_patterns.add(f"/{parts[1]}/...")
                logger.info(f"Disney+: URL patterns on page: {list(path_patterns)[:10]}")
                logger.info(f"Disney+: All hrefs sample: {all_hrefs[:15]}")
                
                # Get all links and filter to real content
                # Disney+ uses /browse/entity-{uuid} for content
                all_links_for_content = await page.query_selector_all('a[href*="entity-"], a[href*="/series/"], a[href*="/movies/"]')
                all_tiles = []
                seen_hrefs = set()
                for link in all_links_for_content:
                    href = await link.get_attribute('href') or ''
                    if href in seen_hrefs:
                        continue
                    seen_hrefs.add(href)
                    # Match entity IDs or content paths
                    if re.search(r'/browse/entity-[a-f0-9-]+', href) or \
                       re.search(r'/(series|movies)/[a-zA-Z0-9-]+', href):
                        all_tiles.append(link)
                        
                logger.info(f"Disney+: Found {len(all_tiles)} actual content tiles")
                
                # If still no links, try finding tiles by their container classes
                if not all_tiles:
                    # Disney+ uses various tile/card structures
                    tile_selectors = [
                        '[data-testid="set-item"] a',
                        '[class*="BasicCard"] a',
                        '[class*="tile"] a',
                        '[class*="Tile"] a', 
                        'article a',
                        '[role="link"]',
                    ]
                    for sel in tile_selectors:
                        all_tiles = await page.query_selector_all(sel)
                        if all_tiles:
                            logger.info(f"Disney+: Found {len(all_tiles)} tiles with {sel}")
                            break
                
                # Process tiles - filter for actual content links
                seen_titles = set()
                nav_words = {'live', 'watchlist', 'movies', 'series', 'originals', 'search', 
                             'disney+', 'hulu', 'espn', 'home', 'browse', 'account', 'help',
                             'star', 'marvel', 'pixar', 'national geographic'}
                
                for tile in all_tiles[:50]:  # Check more to find real content
                    try:
                        href = await tile.get_attribute('href') or ''
                        
                        # Already filtered for content links, just validate
                        if not href:
                            continue
                        
                        # Get title from aria-label or inner text
                        title = await tile.get_attribute('aria-label')
                        if not title:
                            title = await tile.inner_text()
                        
                        if not title or not title.strip():
                            continue
                        
                        # Clean up title - extract actual show/movie name
                        title = title.strip()
                        
                        # Remove common noise patterns from Disney+ aria-labels
                        noise_patterns = [
                            r'^(Disney\+ Original|Hulu Original Series?|FX|National Geographic|Marvel Studios|Pixar|Star Wars)\s+',
                            r'\s*Select for details on this title\.?$',
                            r'\s*Rated\s+TV-\w+.*$',
                            r'\s*Rated\s+\w+\s+Released\s+\d+\..*$',
                        ]
                        for pattern in noise_patterns:
                            title = re.sub(pattern, '', title, flags=re.IGNORECASE)
                        
                        title = title.strip().split('\n')[0]  # Take first line after cleanup
                        
                        # Skip navigation/category items
                        if title.lower() in nav_words or len(title) < 2:
                            continue
                        
                        if title in seen_titles:
                            continue
                        seen_titles.add(title)
                        
                        # Extract content ID from href
                        content_id = ''
                        content_type = 'show'
                        
                        # Try entity-uuid pattern first
                        entity_match = re.search(r'/browse/entity-([a-f0-9-]+)', href)
                        if entity_match:
                            content_id = entity_match.group(1)
                        else:
                            # Try /series/ or /movies/ pattern
                            match = re.search(r'/(series|movies)/([a-zA-Z0-9-]+)', href)
                            if match:
                                content_id = match.group(2)
                                content_type = 'movie' if match.group(1) == 'movies' else 'show'
                        
                        entry = WatchHistoryEntry(
                            service='disney',
                            title=title,
                            content_type=content_type,
                            content_id=content_id,
                            deep_link_id=content_id
                        )
                        entries.append(entry)
                        
                        if len(entries) >= 15:
                            break
                    except Exception as e:
                        logger.debug(f"Disney+: Error parsing tile: {e}")
            
            logger.info(f"Disney+: Found {len(entries)} continue watching items")
            await page.close()
            
        except Exception as e:
            logger.error(f"Disney+ scraping error: {e}")
        finally:
            await context.close()
        
        return entries
    
    async def scrape_apple(self) -> List[WatchHistoryEntry]:
        """Scrape Up Next from Apple TV+."""
        entries = []
        context = await self._create_context('apple')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            logger.info("Apple TV+: Navigating to home...")
            await page.goto('https://tv.apple.com/', wait_until='networkidle', timeout=45000)
            await asyncio.sleep(5)
            
            logger.info(f"Apple TV+: Current URL: {page.url}")
            
            # Check for sign-in required
            if 'sign-in' in page.url or 'auth' in page.url:
                logger.warning("Apple TV+: Not logged in")
                await page.close()
                await context.close()
                return entries
            
            # Look for Up Next section with multiple selectors
            logger.info("Apple TV+: Looking for Up Next section...")
            
            up_next_selectors = [
                '[data-testid="shelf-up-next"]',
                '.up-next-shelf',
                'section:has-text("Up Next")',
                '[aria-label*="Up Next"]',
                '.shelf--up-next',
                '[class*="upNext"]',
            ]
            
            up_next = None
            for sel in up_next_selectors:
                try:
                    up_next = await page.query_selector(sel)
                    if up_next:
                        logger.info(f"Apple TV+: Found Up Next with {sel}")
                        break
                except Exception:
                    pass
            
            if up_next:
                # Try multiple item selectors
                item_selectors = [
                    '.shelf-grid__list-item',
                    '.lockup',
                    '[class*="lockup"]',
                    'a[href*="/episode/"], a[href*="/show/"], a[href*="/movie/"]',
                ]
                
                items = []
                for sel in item_selectors:
                    items = await up_next.query_selector_all(sel)
                    if items:
                        logger.info(f"Apple TV+: Found {len(items)} items with {sel}")
                        break
                
                for item in items[:15]:
                    try:
                        # Get title
                        title = None
                        title_selectors = [
                            '.lockup__title',
                            '.canvas-lockup__title',
                            '[class*="title"]',
                            'h3', 'h4', 'span',
                        ]
                        for sel in title_selectors:
                            title_elem = await item.query_selector(sel)
                            if title_elem:
                                title = await title_elem.inner_text()
                                if title and title.strip():
                                    break
                        
                        if not title:
                            title = "Unknown"
                        
                        # Get link for content ID
                        link = await item.query_selector('a')
                        if not link:
                            tag = await item.evaluate('el => el.tagName.toLowerCase()')
                            if tag == 'a':
                                link = item
                        
                        href = await link.get_attribute('href') if link else ''
                        
                        # Extract ID from href
                        content_id = ''
                        if href:
                            match = re.search(r'/(umc\.[^/\?]+)', href)
                            if match:
                                content_id = match.group(1)
                        
                        entry = WatchHistoryEntry(
                            service='apple',
                            title=title.strip(),
                            content_type='show',
                            content_id=content_id,
                            deep_link_id=content_id
                        )
                        entries.append(entry)
                    except Exception as e:
                        logger.debug(f"Apple TV+: Error parsing item: {e}")
            else:
                # Debug: log what we can find
                logger.info("Apple TV+: Up Next section not found, debugging page structure...")
                shelves = await page.query_selector_all('section, [class*="shelf"]')
                logger.info(f"Apple TV+: Found {len(shelves)} sections/shelves")
                
                # Try to find any content on the page
                all_content = await page.query_selector_all('a[href*="/episode/"], a[href*="/show/"], a[href*="/movie/"]')
                logger.info(f"Apple TV+: Found {len(all_content)} content links")
                
                # If we found content links, try to scrape them
                if all_content:
                    seen_ids = set()
                    for item in all_content[:30]:  # Check more to filter dupes
                        try:
                            href = await item.get_attribute('href') or ''
                            
                            # Extract content ID
                            content_id = ''
                            if href:
                                match = re.search(r'/(umc\.[^/\?]+)', href)
                                if match:
                                    content_id = match.group(1)
                            
                            # Skip duplicates
                            if content_id in seen_ids:
                                continue
                            seen_ids.add(content_id)
                            
                            # Try to get title from aria-label first (usually has show name)
                            title = await item.get_attribute('aria-label')
                            
                            # If no aria-label, try to find title in parent element
                            if not title:
                                parent = await item.evaluate_handle('el => el.closest("article, section, div[class*=\"lockup\"]")')
                                if parent:
                                    title_elem = await parent.query_selector('h3, h4, [class*="title"], [class*="headline"]')
                                    if title_elem:
                                        title = await title_elem.inner_text()
                            
                            # If still no title, try link text but filter out metadata
                            if not title:
                                raw_text = await item.inner_text() or ''
                                # Filter out duration/episode metadata
                                if not re.match(r'^S\d+.*E\d+|^\d+h?\s*\d*m?$', raw_text.strip()):
                                    title = raw_text
                            
                            # Extract show name from URL if needed
                            if not title and href:
                                # URL like /show/slow-horses/umc.xxx
                                url_match = re.search(r'/show/([^/]+)/', href)
                                if url_match:
                                    title = url_match.group(1).replace('-', ' ').title()
                            
                            if title and title.strip() and len(entries) < 15:
                                entry = WatchHistoryEntry(
                                    service='apple',
                                    title=title.strip(),
                                    content_type='show',
                                    content_id=content_id,
                                    deep_link_id=content_id
                                )
                                entries.append(entry)
                        except Exception as e:
                            logger.debug(f"Apple TV+: Error parsing fallback item: {e}")
            
            logger.info(f"Apple TV+: Found {len(entries)} up next items")
            await page.close()
            
        except Exception as e:
            logger.error(f"Apple TV+ scraping error: {e}")
        finally:
            await context.close()
        
        return entries
    
    async def scrape_prime(self) -> List[WatchHistoryEntry]:
        """Scrape watch history from Prime Video's dedicated history page."""
        entries = []
        context = await self._create_context('prime')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            # Go directly to watch history page
            logger.info("Prime: Navigating to watch history...")
            await page.goto('https://www.amazon.com/gp/video/settings/watch-history', wait_until='networkidle', timeout=30000)
            await asyncio.sleep(5)
            
            # Check if we need to sign in
            if '/ap/signin' in page.url:
                logger.warning("Prime: Not logged in, session may have expired")
                await page.close()
                await context.close()
                return entries
            
            # Parse watch history items
            logger.info("Prime: Parsing watch history...")
            
            # The watch history page shows items in a list/grid
            # Try multiple selectors for different page layouts
            item_selectors = [
                '.watch-history-item',
                '[data-automation-id="watch-history-item"]',
                '.a-section.a-spacing-none',
                'div[class*="history"] > div',
            ]
            
            items = []
            for selector in item_selectors:
                items = await page.query_selector_all(selector)
                if items:
                    logger.info(f"Prime: Found {len(items)} items with selector {selector}")
                    break
            
            # If no items found, try scraping the visible content more broadly
            if not items:
                logger.info("Prime: Trying broader content scraping...")
                # Look for any title-like elements in the main content
                items = await page.query_selector_all('a[href*="/detail/"], a[href*="/dp/"]')
                logger.info(f"Prime: Found {len(items)} links")
            
            seen_titles = set()
            for item in items[:50]:
                try:
                    # Try to get title
                    title = None
                    href = None
                    
                    # If item is a link itself
                    tag = await item.evaluate('el => el.tagName.toLowerCase()')
                    if tag == 'a':
                        href = await item.get_attribute('href')
                        title = await item.inner_text()
                    else:
                        # Look for link and title within
                        link = await item.query_selector('a[href*="/detail/"], a[href*="/dp/"]')
                        if link:
                            href = await link.get_attribute('href')
                            title = await link.inner_text()
                        
                        if not title:
                            title_elem = await item.query_selector('.a-text-bold, [class*="title"]')
                            title = await title_elem.inner_text() if title_elem else None
                    
                    if not title or not title.strip():
                        continue
                    
                    title = title.strip()
                    
                    # Skip duplicates
                    if title in seen_titles:
                        continue
                    seen_titles.add(title)
                    
                    # Extract ASIN from href
                    content_id = ''
                    if href:
                        match = re.search(r'/dp/([A-Z0-9]+)', href) or re.search(r'/detail/([A-Z0-9]+)', href)
                        if match:
                            content_id = match.group(1)
                    
                    # Parse episode info
                    episode_title = None
                    season_num = None
                    episode_num = None
                    
                    # Prime often shows "S1 E5" format
                    ep_match = re.search(r'S(\d+)\s*E(\d+)', title)
                    if ep_match:
                        season_num = int(ep_match.group(1))
                        episode_num = int(ep_match.group(2))
                    
                    entry = WatchHistoryEntry(
                        service='prime',
                        title=title,
                        content_type='show',
                        content_id=content_id,
                        episode_title=episode_title,
                        season_number=season_num,
                        episode_number=episode_num,
                        deep_link_id=content_id
                    )
                    entries.append(entry)
                    
                except Exception as e:
                    logger.debug(f"Prime: Error parsing item: {e}")
            
            logger.info(f"Prime: Found {len(entries)} watch history items")
            await page.close()
            
        except Exception as e:
            logger.error(f"Prime scraping error: {e}")
        finally:
            await context.close()
        
        return entries
    
    async def scrape_service(self, service: str) -> List[WatchHistoryEntry]:
        """Scrape a specific service."""
        scrapers = {
            'netflix': self.scrape_netflix,
            'disney': self.scrape_disney,
            'apple': self.scrape_apple,
            'prime': self.scrape_prime,
        }
        
        if service not in scrapers:
            logger.warning(f"No browser scraper for {service}")
            return []
        
        return await scrapers[service]()
    
    async def scrape_all(self) -> Dict[str, List[WatchHistoryEntry]]:
        """Scrape all supported services."""
        results = {}
        
        for service in self.SERVICE_CONFIG.keys():
            try:
                results[service] = await self.scrape_service(service)
            except Exception as e:
                logger.error(f"Error scraping {service}: {e}")
                results[service] = []
        
        return results
    
    # ==================== WATCHLIST SCRAPING ====================
    
    async def scrape_netflix_watchlist(self) -> List[WatchlistEntry]:
        """Scrape My List from Netflix."""
        entries = []
        context = await self._create_context('netflix')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            # First go to browse to handle profile selection
            logger.info("Netflix: Navigating to browse for profile handling...")
            await page.goto('https://www.netflix.com/browse', wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)
            
            # Check for profile selection - multiple detection methods
            page_text = await page.inner_text('body')
            is_profile_page = (
                '/profiles' in page.url or 
                "Who's watching" in page_text or
                await page.query_selector('.profile-gate-container') or
                await page.query_selector('.choose-profile')
            )
            
            if is_profile_page:
                logger.info("Netflix: Profile selection required, selecting first profile...")
                
                # Try multiple profile selectors
                profile_selectors = [
                    '.profile-icon',
                    '.profile-link',
                    'a[href*="/browse"]',
                    '.choose-profile .profile',
                    'li.profile',
                    '[data-profile-guid]',
                ]
                
                clicked = False
                for sel in profile_selectors:
                    try:
                        profiles = await page.query_selector_all(sel)
                        logger.info(f"Netflix: Found {len(profiles)} profiles with {sel}")
                        if profiles:
                            await profiles[0].click()
                            clicked = True
                            logger.info(f"Netflix: Clicked profile with {sel}")
                            await asyncio.sleep(5)
                            break
                    except Exception as e:
                        logger.debug(f"Netflix: Profile selector {sel} failed: {e}")
                
                if not clicked:
                    logger.warning("Netflix: Could not click profile, trying keyboard nav...")
                    await page.keyboard.press('Tab')
                    await asyncio.sleep(0.3)
                    await page.keyboard.press('Enter')
                    await asyncio.sleep(5)
            
            # Now navigate to My List
            logger.info("Netflix: Navigating to My List...")
            await page.goto('https://www.netflix.com/browse/my-list', wait_until='networkidle', timeout=30000)
            await asyncio.sleep(8)  # Wait longer for JS to render
            
            logger.info(f"Netflix: My List URL: {page.url}")
            
            # Check page title to confirm we're on the right page
            page_title = await page.title()
            logger.info(f"Netflix: Page title: {page_title}")
            
            # Try multiple selectors for Netflix items
            item_selectors = [
                '.slider-item',
                '.title-card',
                '[data-list-context] .slider-item',
                '.galleryContent .slider-item',
                'a[href*="/watch/"]',
            ]
            
            items = []
            for sel in item_selectors:
                items = await page.query_selector_all(sel)
                if items:
                    logger.info(f"Netflix: Found {len(items)} items with {sel}")
                    break
            
            if not items:
                # Debug: check page content
                page_text = await page.inner_text('body')
                logger.info(f"Netflix: My List page text length: {len(page_text)}")
                logger.info(f"Netflix: Page text preview: {page_text[:200]}")
                
                all_links = await page.query_selector_all('a[href]')
                logger.info(f"Netflix: Total links on page: {len(all_links)}")
                
                # Check if the list is genuinely empty
                if 'empty' in page_text.lower() or len(page_text) < 100:
                    logger.info("Netflix: My List appears to be empty")
            
            seen_titles = set()
            for item in items[:50]:
                try:
                    # Get title
                    title = None
                    title_selectors = ['p', '.fallback-text', '.title-card-container p', 'img[alt]']
                    for sel in title_selectors:
                        title_elem = await item.query_selector(sel)
                        if title_elem:
                            if sel == 'img[alt]':
                                title = await title_elem.get_attribute('alt')
                            else:
                                title = await title_elem.inner_text()
                            if title and title.strip():
                                break
                    
                    if not title or title in seen_titles:
                        continue
                    seen_titles.add(title)
                    
                    # Get link
                    link = await item.query_selector('a')
                    if not link:
                        tag = await item.evaluate('el => el.tagName.toLowerCase()')
                        if tag == 'a':
                            link = item
                    
                    href = await link.get_attribute('href') if link else ''
                    
                    content_id = ''
                    if href:
                        match = re.search(r'/watch/(\d+)', href) or re.search(r'/title/(\d+)', href)
                        if match:
                            content_id = match.group(1)
                    
                    entries.append(WatchlistEntry(
                        service='netflix',
                        title=title.strip(),
                        content_type='show',
                        content_id=content_id,
                        deep_link_id=content_id
                    ))
                except Exception as e:
                    logger.debug(f"Netflix watchlist: Error parsing item: {e}")
            
            logger.info(f"Netflix: Found {len(entries)} watchlist items")
            await page.close()
        except Exception as e:
            logger.error(f"Netflix watchlist error: {e}")
        finally:
            await context.close()
        
        return entries
    
    async def scrape_prime_watchlist(self) -> List[WatchlistEntry]:
        """Scrape Watchlist from Prime Video."""
        entries = []
        context = await self._create_context('prime')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            logger.info("Prime: Navigating to Watchlist...")
            await page.goto('https://www.amazon.com/gp/video/watchlist', wait_until='networkidle', timeout=30000)
            await asyncio.sleep(5)
            
            # Get watchlist items
            items = await page.query_selector_all('a[href*="/detail/"], a[href*="/dp/"]')
            logger.info(f"Prime: Found {len(items)} watchlist links")
            
            seen_titles = set()
            for item in items[:50]:
                try:
                    href = await item.get_attribute('href') or ''
                    title = await item.inner_text()
                    
                    if not title or not title.strip() or title in seen_titles:
                        continue
                    seen_titles.add(title)
                    
                    content_id = ''
                    match = re.search(r'/dp/([A-Z0-9]+)', href) or re.search(r'/detail/([A-Z0-9]+)', href)
                    if match:
                        content_id = match.group(1)
                    
                    entries.append(WatchlistEntry(
                        service='prime',
                        title=title.strip(),
                        content_type='show',
                        content_id=content_id,
                        deep_link_id=content_id
                    ))
                except Exception as e:
                    logger.debug(f"Prime watchlist: Error parsing item: {e}")
            
            await page.close()
        except Exception as e:
            logger.error(f"Prime watchlist error: {e}")
        finally:
            await context.close()
        
        return entries
    
    async def scrape_disney_watchlist(self) -> List[WatchlistEntry]:
        """Scrape Watchlist from Disney+."""
        entries = []
        context = await self._create_context('disney')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            logger.info("Disney+: Navigating to Watchlist...")
            await page.goto('https://www.disneyplus.com/browse/watchlist', wait_until='networkidle', timeout=30000)
            await asyncio.sleep(5)
            
            # Get watchlist items
            items = await page.query_selector_all('a[href*="entity-"], a[href*="/series/"], a[href*="/movies/"]')
            logger.info(f"Disney+: Found {len(items)} watchlist links")
            
            seen_ids = set()
            for item in items[:50]:
                try:
                    href = await item.get_attribute('href') or ''
                    title = await item.get_attribute('aria-label') or await item.inner_text()
                    
                    # Extract content ID
                    content_id = ''
                    entity_match = re.search(r'/browse/entity-([a-f0-9-]+)', href)
                    if entity_match:
                        content_id = entity_match.group(1)
                    else:
                        match = re.search(r'/(series|movies)/([a-zA-Z0-9-]+)', href)
                        if match:
                            content_id = match.group(2)
                    
                    if content_id in seen_ids:
                        continue
                    seen_ids.add(content_id)
                    
                    # Clean title - remove network badges and metadata
                    if title:
                        title = re.sub(r'Select for details.*$', '', title, flags=re.IGNORECASE)
                        # Remove network/channel suffixes
                        title = re.sub(r'\s+(ESPN\d*|FX|ABC|National Geographic|Disney\+?\s*Original|Hulu|Freeform|Disney Channel|Disney Junior|Disney XD)\s*$', '', title, flags=re.IGNORECASE)
                        # Remove rating and release info
                        title = re.sub(r'\s+Rated\s+\w+.*$', '', title, flags=re.IGNORECASE)
                        title = title.strip()
                    
                    if title and len(title) > 2:
                        entries.append(WatchlistEntry(
                            service='disney',
                            title=title,
                            content_type='show',
                            content_id=content_id,
                            deep_link_id=content_id
                        ))
                except Exception as e:
                    logger.debug(f"Disney+ watchlist: Error parsing item: {e}")
            
            await page.close()
        except Exception as e:
            logger.error(f"Disney+ watchlist error: {e}")
        finally:
            await context.close()
        
        return entries
    
    async def scrape_apple_watchlist(self) -> List[WatchlistEntry]:
        """Scrape Watchlist/Up Next from Apple TV+."""
        entries = []
        context = await self._create_context('apple')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            # Apple TV+ uses "Up Next" as their watchlist/queue
            # This is on the main page, not a separate library page
            logger.info("Apple TV+: Navigating to home for Up Next...")
            await page.goto('https://tv.apple.com/', wait_until='networkidle', timeout=30000)
            await asyncio.sleep(5)
            
            logger.info(f"Apple TV+: URL: {page.url}")
            
            # Look for "Up Next" or "Watchlist" section
            # Apple TV+ shows your queue at the top of the home page
            up_next_selectors = [
                '[data-testid="shelf-up-next"]',
                'section:has-text("Up Next")',
                '[aria-label*="Up Next"]',
                '.shelf--up-next',
            ]
            
            up_next_section = None
            for sel in up_next_selectors:
                try:
                    up_next_section = await page.query_selector(sel)
                    if up_next_section:
                        logger.info(f"Apple TV+: Found Up Next section with {sel}")
                        break
                except Exception:
                    pass
            
            if up_next_section:
                # Get items from Up Next section
                items = await up_next_section.query_selector_all('a[href*="/show/"], a[href*="/movie/"], a[href*="/episode/"]')
                logger.info(f"Apple TV+: Found {len(items)} items in Up Next")
            else:
                # Fallback: get all content from the page
                logger.info("Apple TV+: Up Next section not found, getting all content...")
                items = await page.query_selector_all('a[href*="/show/"], a[href*="/movie/"]')
                logger.info(f"Apple TV+: Found {len(items)} content links")
            
            seen_ids = set()
            for item in items[:50]:
                try:
                    href = await item.get_attribute('href') or ''
                    
                    # Get title from aria-label first
                    title = await item.get_attribute('aria-label')
                    
                    # Try to extract from URL if no aria-label
                    if not title:
                        url_match = re.search(r'/show/([^/]+)/', href)
                        if url_match:
                            title = url_match.group(1).replace('-', ' ').title()
                    
                    # Skip metadata-like text
                    if title and re.match(r'^S\d+.*E\d+|^\d+h?\s*\d*m?$', title.strip()):
                        continue
                    
                    content_id = ''
                    match = re.search(r'/(umc\.[^/\?]+)', href)
                    if match:
                        content_id = match.group(1)
                    
                    if content_id in seen_ids:
                        continue
                    seen_ids.add(content_id)
                    
                    if title and title.strip():
                        entries.append(WatchlistEntry(
                            service='apple',
                            title=title.strip(),
                            content_type='show',
                            content_id=content_id,
                            deep_link_id=content_id
                        ))
                except Exception as e:
                    logger.debug(f"Apple TV+ watchlist: Error parsing item: {e}")
            
            logger.info(f"Apple TV+: Found {len(entries)} watchlist items")
            await page.close()
        except Exception as e:
            logger.error(f"Apple TV+ watchlist error: {e}")
        finally:
            await context.close()
        
        return entries
    
    async def scrape_max_watchlist(self) -> List[WatchlistEntry]:
        """Scrape My List from Max (HBO)."""
        entries = []
        context = await self._create_context('max')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            # First go to home to handle profile selection
            logger.info("Max: Navigating to home for profile handling...")
            await page.goto('https://play.max.com/', wait_until='networkidle', timeout=45000)
            await asyncio.sleep(5)
            
            logger.info(f"Max: Home URL: {page.url}")
            
            # Handle profile selection if needed
            if 'profile' in page.url.lower() or 'select' in page.url.lower():
                logger.info("Max: Profile selection required...")
                profile = await page.query_selector('[data-testid="profile-avatar"], [class*="profile"], button[class*="profile"]')
                if profile:
                    await profile.click()
                    await asyncio.sleep(5)
            
            # Navigate to My List - try clicking the nav link first
            logger.info("Max: Looking for My List in navigation...")
            
            # Try to find and click My List link
            my_list_link = await page.query_selector('a[href*="my-list"], a[href*="/mylist"], nav a:has-text("My List")')
            if my_list_link:
                logger.info("Max: Found My List link, clicking...")
                await my_list_link.click()
                await asyncio.sleep(5)
            else:
                # Try direct navigation with the actual domain
                current_domain = page.url.split('/')[2] if '/' in page.url else 'play.max.com'
                my_list_url = f"https://{current_domain}/my-list"
                logger.info(f"Max: Navigating directly to {my_list_url}")
                await page.goto(my_list_url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(5)
            
            logger.info(f"Max: My List URL: {page.url}")
            
            # If error page, try finding My List through menu
            if 'error' in page.url.lower():
                logger.info("Max: Hit error page, trying menu approach...")
                await page.goto(f"https://{current_domain}/", wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(3)
                
                # Try clicking menu/hamburger first
                menu_btn = await page.query_selector('[aria-label*="menu"], [class*="menu"], button[class*="nav"]')
                if menu_btn:
                    await menu_btn.click()
                    await asyncio.sleep(2)
                
                # Look for My List link
                my_list_link = await page.query_selector('a[href*="my-list"], a:has-text("My List"), [aria-label*="My List"]')
                if my_list_link:
                    await my_list_link.click()
                    await asyncio.sleep(5)
            
            # Get all content links
            items = await page.query_selector_all('a[href*="/video/watch/"], a[href*="/show/"], a[href*="/movie/"]')
            logger.info(f"Max: Found {len(items)} content links")
            
            seen_ids = set()
            for item in items[:50]:
                try:
                    href = await item.get_attribute('href') or ''
                    title = await item.get_attribute('aria-label')
                    
                    if not title:
                        title_elem = await item.query_selector('[class*="title"], h3, h4, span')
                        if title_elem:
                            title = await title_elem.inner_text()
                    
                    if not title or not title.strip():
                        continue
                    
                    # Clean up Max's unicode formatting
                    title = re.sub(r'[⁦⁨⁩\u2066\u2067\u2068\u2069]', '', title)
                    # Remove position indicators like "1 of 20"
                    title = re.sub(r'\.\s*\d+\s+of\s+\d+.*$', '', title)
                    title = title.strip()
                    
                    if not title:
                        continue
                    
                    # Extract content ID
                    content_id = ''
                    match = re.search(r'/(video/watch|show|movie)/([^/\?]+)', href)
                    if match:
                        content_id = match.group(2)
                    
                    if content_id in seen_ids:
                        continue
                    seen_ids.add(content_id)
                    
                    entries.append(WatchlistEntry(
                        service='max',
                        title=title,
                        content_type='show',
                        content_id=content_id,
                        deep_link_id=content_id
                    ))
                except Exception as e:
                    logger.debug(f"Max watchlist: Error parsing item: {e}")
            
            logger.info(f"Max: Found {len(entries)} watchlist items")
            await page.close()
        except Exception as e:
            logger.error(f"Max watchlist error: {e}")
        finally:
            await context.close()
        
        return entries
    
    async def scrape_hulu_watchlist(self) -> List[WatchlistEntry]:
        """Scrape My Stuff from Hulu."""
        entries = []
        context = await self._create_context('hulu')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            # Go to Hulu home first
            logger.info("Hulu: Navigating to home...")
            await page.goto('https://www.hulu.com/', wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(5)
            
            # Handle profile selection if needed
            if 'profiles' in page.url.lower():
                logger.info("Hulu: Profile selection required...")
                profile = await page.query_selector('[data-testid="profile-tile"], [class*="profile"]')
                if profile:
                    await profile.click()
                    await asyncio.sleep(5)
            
            # Wait for navbar to load
            await asyncio.sleep(3)
            
            # Click My Stuff in the navbar
            logger.info("Hulu: Looking for My Stuff in navbar...")
            my_stuff_nav = await page.query_selector('nav a[href*="my-stuff"], a[href*="my-stuff"], [aria-label*="My Stuff"], button:has-text("My Stuff")')
            
            if my_stuff_nav:
                logger.info("Hulu: Clicking My Stuff navbar link...")
                await my_stuff_nav.click()
                await asyncio.sleep(5)
            else:
                # Try text-based selector
                logger.info("Hulu: Trying text-based My Stuff selector...")
                await page.click('text=My Stuff', timeout=10000)
                await asyncio.sleep(5)
            
            logger.info(f"Hulu: My Stuff URL: {page.url}")
            
            # Wait for content to load
            await asyncio.sleep(5)
            
            # Get all content links from the My Stuff page
            all_items = await page.query_selector_all('a[href*="/series/"], a[href*="/movie/"]')
            logger.info(f"Hulu: Total content links: {len(all_items)}")
            
            # Filter out items that are in "Live Now" section
            items = []
            live_now_section = await page.query_selector('section:has-text("Live Now"), div:has-text("Live Now")')
            
            for item in all_items:
                href = await item.get_attribute('href') or ''
                # Skip live content
                if 'live' in href.lower():
                    continue
                    
                # Check if item is inside Live Now section (skip if so)
                is_in_live = await item.evaluate('el => { let p = el; while(p) { if(p.textContent && p.textContent.includes("Live Now") && p.tagName === "SECTION") return true; p = p.parentElement; } return false; }')
                if not is_in_live:
                    items.append(item)
            
            logger.info(f"Hulu: Found {len(items)} non-live content links")
            
            seen_ids = set()
            for item in items[:50]:
                try:
                    href = await item.get_attribute('href') or ''
                    
                    # Try multiple approaches for title
                    title = await item.get_attribute('aria-label')
                    
                    if not title:
                        # Try getting text from sibling or parent container
                        parent = await item.evaluate_handle('el => el.closest("div, article, li")')
                        if parent:
                            title_elem = await parent.query_selector('h3, h4, [class*="Title"], [class*="title"], p:first-of-type')
                            if title_elem:
                                title = await title_elem.inner_text()
                    
                    if not title:
                        # Try getting inner text of the item itself
                        title = await item.inner_text()
                    
                    if not title or not title.strip():
                        continue
                    
                    # Clean up Hulu's formatting
                    title = re.sub(r',?\s*Item\s+\d+\s+of\s+\w+', '', title)
                    title = re.sub(r'^(WATCHED|WATCH MOVIE)\s*', '', title)
                    title = title.strip()
                    
                    if not title:
                        continue
                    
                    # Extract content ID
                    content_id = ''
                    match = re.search(r'/(series|movie|watch)/([^/\?]+)', href)
                    if match:
                        content_id = match.group(2)
                    
                    if content_id in seen_ids:
                        continue
                    seen_ids.add(content_id)
                    
                    # Determine content type
                    content_type = 'movie' if '/movie/' in href else 'show'
                    
                    entries.append(WatchlistEntry(
                        service='hulu',
                        title=title,
                        content_type=content_type,
                        content_id=content_id,
                        deep_link_id=content_id
                    ))
                except Exception as e:
                    logger.debug(f"Hulu watchlist: Error parsing item: {e}")
            
            logger.info(f"Hulu: Found {len(entries)} watchlist items")
            await page.close()
        except Exception as e:
            logger.error(f"Hulu watchlist error: {e}")
        finally:
            await context.close()
        
        return entries
    
    async def scrape_watchlist(self, service: str) -> List[WatchlistEntry]:
        """Scrape watchlist from a specific service."""
        scrapers = {
            'netflix': self.scrape_netflix_watchlist,
            'prime': self.scrape_prime_watchlist,
            'disney': self.scrape_disney_watchlist,
            'apple': self.scrape_apple_watchlist,
            'max': self.scrape_max_watchlist,
            'hulu': self.scrape_hulu_watchlist,
        }
        
        if service not in scrapers:
            logger.warning(f"No watchlist scraper for {service}")
            return []
        
        return await scrapers[service]()
    
    async def scrape_all_watchlists(self) -> Dict[str, List[WatchlistEntry]]:
        """Scrape watchlists from all supported services."""
        results = {}
        for service in ['netflix', 'prime', 'disney', 'apple', 'max', 'hulu']:
            try:
                results[service] = await self.scrape_watchlist(service)
                logger.info(f"{service}: Got {len(results[service])} watchlist items")
            except Exception as e:
                logger.error(f"{service} watchlist error: {e}")
                results[service] = []
        return results
    
    # ==================== RECOMMENDATION SCRAPING ====================
    
    async def scrape_netflix_recommendations(self) -> List[RecommendationEntry]:
        """Scrape recommendation rows from Netflix home page."""
        entries = []
        context = await self._create_context('netflix')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            logger.info("Netflix: Navigating to home for recommendations...")
            await page.goto('https://www.netflix.com/browse', wait_until='networkidle', timeout=30000)
            await asyncio.sleep(5)
            
            # Handle profile selection
            page_text = await page.inner_text('body')
            is_profile_page = '/profiles' in page.url or "Who's watching" in page_text
            
            if is_profile_page:
                logger.info("Netflix: Profile selection required...")
                profile_selectors = ['.profile-icon', '.profile-link', 'a[href*="/browse"]', 'li.profile']
                for sel in profile_selectors:
                    profiles = await page.query_selector_all(sel)
                    if profiles:
                        await profiles[0].click()
                        logger.info(f"Netflix: Clicked profile with {sel}")
                        await asyncio.sleep(5)
                        break
            
            # Get all rows/shelves
            rows = await page.query_selector_all('[data-list-context]')
            logger.info(f"Netflix: Found {len(rows)} recommendation rows")
            
            seen_titles = set()  # Deduplicate by title
            
            for row in rows[:10]:  # Limit to first 10 rows
                try:
                    category = await row.get_attribute('data-list-context')
                    
                    # Skip continue watching (handled separately)
                    if category in ('continueWatching', 'queue'):
                        continue
                    
                    # Map category to recommendation type
                    rec_type = 'personalized'
                    if 'trending' in category.lower():
                        rec_type = 'trending'
                    elif 'new' in category.lower():
                        rec_type = 'new_release'
                    elif 'top' in category.lower():
                        rec_type = 'top_pick'
                    elif 'because' in category.lower():
                        rec_type = 'because_you_watched'
                    
                    items = await row.query_selector_all('.slider-item, .title-card')
                    
                    for pos, item in enumerate(items[:10]):  # Limit items per row
                        try:
                            title_elem = await item.query_selector('p, .fallback-text')
                            title = await title_elem.inner_text() if title_elem else None
                            
                            if not title or not title.strip():
                                continue
                            
                            title = title.strip()
                            
                            # Skip duplicates
                            if title in seen_titles:
                                continue
                            
                            # Skip time entries and other non-content
                            if re.match(r'^\d+\s*(AM|PM)\s*(ET|PT|CT)?$', title, re.IGNORECASE):
                                continue
                            if re.match(r'^(Today|Tomorrow|Yesterday)$', title, re.IGNORECASE):
                                continue
                            
                            seen_titles.add(title)
                            
                            link = await item.query_selector('a')
                            href = await link.get_attribute('href') if link else ''
                            
                            content_id = ''
                            if href:
                                match = re.search(r'/watch/(\d+)', href) or re.search(r'/title/(\d+)', href)
                                if match:
                                    content_id = match.group(1)
                            
                            entries.append(RecommendationEntry(
                                service='netflix',
                                title=title,
                                content_type='show',
                                content_id=content_id,
                                recommendation_type=rec_type,
                                category=category,
                                position=pos,
                                deep_link_id=content_id
                            ))
                        except Exception as e:
                            logger.debug(f"Netflix rec item error: {e}")
                except Exception as e:
                    logger.debug(f"Netflix rec row error: {e}")
            
            await page.close()
        except Exception as e:
            logger.error(f"Netflix recommendations error: {e}")
        finally:
            await context.close()
        
        logger.info(f"Netflix: Got {len(entries)} recommendations")
        return entries
    
    async def scrape_prime_recommendations(self) -> List[RecommendationEntry]:
        """Scrape recommendation rows from Prime Video home page."""
        entries = []
        context = await self._create_context('prime')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            logger.info("Prime: Navigating to home for recommendations...")
            await page.goto('https://www.amazon.com/gp/video/storefront', wait_until='networkidle', timeout=30000)
            await asyncio.sleep(5)
            
            # Get all content links with context
            all_links = await page.query_selector_all('a[href*="/detail/"], a[href*="/dp/"]')
            logger.info(f"Prime: Found {len(all_links)} recommendation links")
            
            # Skip button/action labels
            skip_titles = {'watch', 'watch now', 'play', 'resume', 'continue watching', 
                          'add to watchlist', 'remove from watchlist', 'more details',
                          'included with prime', 'free with ads', 'rent or buy'}
            
            seen = set()
            for pos, item in enumerate(all_links[:100]):
                try:
                    href = await item.get_attribute('href') or ''
                    title = await item.inner_text()
                    
                    if not title or not title.strip():
                        continue
                    
                    title = title.strip()
                    
                    # Skip button/action labels
                    if title.lower() in skip_titles or len(title) < 3:
                        continue
                    
                    # Skip if title is just a number or rating
                    if re.match(r'^[\d\.\s]+$', title) or re.match(r'^\d+h\s*\d*m?$', title):
                        continue
                    
                    if title in seen:
                        continue
                    seen.add(title)
                    
                    content_id = ''
                    match = re.search(r'/dp/([A-Z0-9]+)', href) or re.search(r'/detail/([A-Z0-9]+)', href)
                    if match:
                        content_id = match.group(1)
                    
                    entries.append(RecommendationEntry(
                        service='prime',
                        title=title,
                        content_type='show',
                        content_id=content_id,
                        recommendation_type='personalized',
                        position=pos,
                        deep_link_id=content_id
                    ))
                except Exception as e:
                    logger.debug(f"Prime rec error: {e}")
            
            await page.close()
        except Exception as e:
            logger.error(f"Prime recommendations error: {e}")
        finally:
            await context.close()
        
        logger.info(f"Prime: Got {len(entries)} recommendations")
        return entries
    
    async def scrape_disney_recommendations(self) -> List[RecommendationEntry]:
        """Scrape recommendation rows from Disney+ home page."""
        entries = []
        context = await self._create_context('disney')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            logger.info("Disney+: Navigating to home for recommendations...")
            await page.goto('https://www.disneyplus.com/home', wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(8)
            
            logger.info(f"Disney+: Current URL: {page.url}")
            
            # Check page content
            html_len = len(await page.content())
            logger.info(f"Disney+: Page HTML size: {html_len} bytes")
            
            # Navigate to home if on profile page
            if 'select-profile' in page.url or 'profile' in page.url.lower():
                logger.info("Disney+: On profile page, selecting profile...")
                profile = await page.query_selector('[data-testid="profile-avatar"], [class*="profile"]')
                if profile:
                    await profile.click()
                    await asyncio.sleep(5)
            
            # Check if logged in - look for any content container
            content_check = await page.query_selector('[class*="ContentRow"], [data-testid*="content"], [class*="shelf"]')
            if not content_check:
                logger.warning("Disney+: No content containers found - may not be logged in")
            
            # Get all content links
            all_links = await page.query_selector_all('a[href]')
            logger.info(f"Disney+: Found {len(all_links)} total links")
            
            seen_ids = set()
            nav_words = {'live', 'watchlist', 'movies', 'series', 'originals', 'search', 
                        'disney+', 'hulu', 'espn', 'home', 'browse', 'account', 'help'}
            
            for pos, item in enumerate(all_links[:200]):
                try:
                    href = await item.get_attribute('href') or ''
                    
                    # Must be a content link
                    if not re.search(r'/browse/entity-[a-f0-9-]+', href):
                        continue
                    
                    title = await item.get_attribute('aria-label') or await item.inner_text()
                    if not title:
                        continue
                    
                    # Clean title - remove metadata artifacts
                    title = re.sub(r'Select for details.*$', '', title, flags=re.IGNORECASE)
                    # Remove prefixes like "Series", "Movie", network names
                    title = re.sub(r'^(Disney\+ Original|Hulu Original|FX|Series|Movie|Film)\s+', '', title, flags=re.IGNORECASE)
                    # Also check for prefix in middle (aria-label sometimes has "Series Futurama")
                    if title.lower().startswith('series '):
                        title = title[7:]
                    if title.lower().startswith('movie '):
                        title = title[6:]
                    # Remove network/channel suffixes
                    title = re.sub(r'\s+(ESPN\d*|FX|ABC|National Geographic|Disney\+?\s*Original|Hulu|Freeform)\s*$', '', title, flags=re.IGNORECASE)
                    title = re.sub(r'\s*Rated\s+\w+.*Released\s+\d+.*$', '', title, flags=re.IGNORECASE)
                    title = re.sub(r'\s*Rated\s+TV-\w+.*$', '', title)
                    title = re.sub(r',\s*(Super Heroes|Action|Adventure|Comedy|Drama).*$', '', title, flags=re.IGNORECASE)
                    title = title.strip()
                    
                    if not title or title.lower() in nav_words:
                        continue
                    
                    content_id = ''
                    entity_match = re.search(r'/browse/entity-([a-f0-9-]+)', href)
                    if entity_match:
                        content_id = entity_match.group(1)
                    
                    if content_id in seen_ids:
                        continue
                    seen_ids.add(content_id)
                    
                    entries.append(RecommendationEntry(
                        service='disney',
                        title=title,
                        content_type='show',
                        content_id=content_id,
                        recommendation_type='personalized',
                        position=pos,
                        deep_link_id=content_id
                    ))
                except Exception as e:
                    logger.debug(f"Disney+ rec error: {e}")
            
            await page.close()
        except Exception as e:
            logger.error(f"Disney+ recommendations error: {e}")
        finally:
            await context.close()
        
        logger.info(f"Disney+: Got {len(entries)} recommendations")
        return entries
    
    async def scrape_apple_recommendations(self) -> List[RecommendationEntry]:
        """Scrape recommendation rows from Apple TV+ home page."""
        entries = []
        context = await self._create_context('apple')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            logger.info("Apple TV+: Navigating to home for recommendations...")
            await page.goto('https://tv.apple.com/', wait_until='networkidle', timeout=30000)
            await asyncio.sleep(5)
            
            # Get all content links
            all_links = await page.query_selector_all('a[href*="/show/"], a[href*="/movie/"], a[href*="/episode/"]')
            logger.info(f"Apple TV+: Found {len(all_links)} recommendation links")
            
            seen_ids = set()
            for pos, item in enumerate(all_links[:100]):
                try:
                    href = await item.get_attribute('href') or ''
                    title = await item.get_attribute('aria-label')
                    
                    if not title:
                        # Try to get from parent
                        parent = await item.evaluate_handle('el => el.closest("article, section")')
                        if parent:
                            title_elem = await parent.query_selector('h3, h4, [class*="title"]')
                            if title_elem:
                                title = await title_elem.inner_text()
                    
                    if not title:
                        # Try URL parsing
                        url_match = re.search(r'/show/([^/]+)/', href)
                        if url_match:
                            title = url_match.group(1).replace('-', ' ').title()
                    
                    if not title:
                        continue
                    
                    content_id = ''
                    match = re.search(r'/(umc\.[^/\?]+)', href)
                    if match:
                        content_id = match.group(1)
                    
                    if content_id in seen_ids:
                        continue
                    seen_ids.add(content_id)
                    
                    entries.append(RecommendationEntry(
                        service='apple',
                        title=title.strip(),
                        content_type='show',
                        content_id=content_id,
                        recommendation_type='personalized',
                        position=pos,
                        deep_link_id=content_id
                    ))
                except Exception as e:
                    logger.debug(f"Apple TV+ rec error: {e}")
            
            await page.close()
        except Exception as e:
            logger.error(f"Apple TV+ recommendations error: {e}")
        finally:
            await context.close()
        
        logger.info(f"Apple TV+: Got {len(entries)} recommendations")
        return entries
    
    async def scrape_max_recommendations(self) -> List[RecommendationEntry]:
        """Scrape recommendations from Max home page."""
        entries = []
        context = await self._create_context('max')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            logger.info("Max: Navigating to home for recommendations...")
            await page.goto('https://play.max.com/', wait_until='networkidle', timeout=45000)
            await asyncio.sleep(5)
            
            logger.info(f"Max: Home URL: {page.url}")
            
            # Handle profile selection
            if 'profile' in page.url.lower() or 'select' in page.url.lower():
                logger.info("Max: Profile selection required...")
                profile = await page.query_selector('[data-testid="profile-avatar"], [class*="profile"], button[class*="profile"]')
                if profile:
                    await profile.click()
                    await asyncio.sleep(5)
            
            # Get all content links
            items = await page.query_selector_all('a[href*="/video/watch/"], a[href*="/show/"], a[href*="/movie/"]')
            logger.info(f"Max: Found {len(items)} content links")
            
            seen_ids = set()
            for pos, item in enumerate(items[:100]):
                try:
                    href = await item.get_attribute('href') or ''
                    title = await item.get_attribute('aria-label')
                    
                    if not title:
                        title_elem = await item.query_selector('[class*="title"], h3, h4, span')
                        if title_elem:
                            title = await title_elem.inner_text()
                    
                    if not title or not title.strip():
                        continue
                    
                    # Clean up Max's unicode formatting
                    title = re.sub(r'[⁦⁨⁩\u2066\u2067\u2068\u2069]', '', title)
                    title = re.sub(r'\.\s*\d+\s+of\s+\d+.*$', '', title)
                    title = title.strip()
                    
                    if not title:
                        continue
                    
                    content_id = ''
                    match = re.search(r'/(video/watch|show|movie)/([^/\?]+)', href)
                    if match:
                        content_id = match.group(2)
                    
                    if content_id in seen_ids:
                        continue
                    seen_ids.add(content_id)
                    
                    entries.append(RecommendationEntry(
                        service='max',
                        title=title,
                        content_type='show',
                        content_id=content_id,
                        recommendation_type='personalized',
                        position=pos,
                        deep_link_id=content_id
                    ))
                except Exception as e:
                    logger.debug(f"Max rec error: {e}")
            
            logger.info(f"Max: Got {len(entries)} recommendations")
            await page.close()
        except Exception as e:
            logger.error(f"Max recommendations error: {e}")
        finally:
            await context.close()
        
        return entries
    
    async def scrape_hulu_recommendations(self) -> List[RecommendationEntry]:
        """Scrape recommendations from Hulu home page."""
        entries = []
        context = await self._create_context('hulu')
        
        if not context:
            return entries
        
        try:
            page = await context.new_page()
            
            logger.info("Hulu: Navigating to home for recommendations...")
            await page.goto('https://www.hulu.com/hub/home', wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(8)
            
            # Handle profile selection
            if 'profiles' in page.url.lower():
                profile = await page.query_selector('[data-testid="profile-tile"], [class*="profile"]')
                if profile:
                    await profile.click()
                    await asyncio.sleep(5)
            
            # Wait for content
            await asyncio.sleep(3)
            
            # Scroll down to load Movies For You section
            for _ in range(3):
                await page.evaluate('window.scrollBy(0, 800)')
                await asyncio.sleep(1)
            
            # Scroll back up
            await page.evaluate('window.scrollTo(0, 0)')
            await asyncio.sleep(1)
            
            # Target "TV For You" and "Movies For You" sections specifically
            items = []
            all_sections = await page.query_selector_all('section, [class*="collection"], div[class*="row"]')
            
            tv_count = 0
            movies_count = 0
            
            for section in all_sections:
                section_text = await section.inner_text()
                section_text_lower = section_text.lower()
                
                # Only include "TV For You" and "Movies For You" sections
                if 'tv for you' in section_text_lower:
                    section_items = await section.query_selector_all('a[href*="/series/"], a[href*="/movie/"]')
                    if section_items:
                        items.extend(section_items)
                        tv_count = len(section_items)
                elif 'movies for you' in section_text_lower:
                    section_items = await section.query_selector_all('a[href*="/series/"], a[href*="/movie/"]')
                    if section_items:
                        items.extend(section_items)
                        movies_count = len(section_items)
            
            logger.info(f"Hulu: Found {tv_count} TV For You items, {movies_count} Movies For You items")
            
            # Fall back to all non-live content if no section-specific items found
            if not items:
                logger.info("Hulu: No section-specific recommendations, falling back to all content")
                items = await page.query_selector_all('a[href*="/series/"]:not([href*="live"]), a[href*="/movie/"]')
            
            seen_ids = set()
            for pos, item in enumerate(items[:100]):
                try:
                    href = await item.get_attribute('href') or ''
                    title = await item.get_attribute('aria-label')
                    
                    if not title:
                        title_elem = await item.query_selector('[class*="title"], h3, h4')
                        if title_elem:
                            title = await title_elem.inner_text()
                    
                    if not title or not title.strip():
                        continue
                    
                    # Clean up Hulu's "Item X of many" formatting
                    title = re.sub(r',?\s*Item\s+\d+\s+of\s+\w+', '', title)
                    title = title.strip()
                    
                    if not title:
                        continue
                    
                    content_id = ''
                    match = re.search(r'/(series|movie|watch)/([^/\?]+)', href)
                    if match:
                        content_id = match.group(2)
                    
                    if content_id in seen_ids:
                        continue
                    seen_ids.add(content_id)
                    
                    entries.append(RecommendationEntry(
                        service='hulu',
                        title=title,
                        content_type='show',
                        content_id=content_id,
                        recommendation_type='personalized',
                        position=pos,
                        deep_link_id=content_id
                    ))
                except Exception as e:
                    logger.debug(f"Hulu rec error: {e}")
            
            logger.info(f"Hulu: Got {len(entries)} recommendations")
            await page.close()
        except Exception as e:
            logger.error(f"Hulu recommendations error: {e}")
        finally:
            await context.close()
        
        return entries
    
    async def scrape_recommendations(self, service: str) -> List[RecommendationEntry]:
        """Scrape recommendations from a specific service."""
        scrapers = {
            'netflix': self.scrape_netflix_recommendations,
            'prime': self.scrape_prime_recommendations,
            'disney': self.scrape_disney_recommendations,
            'apple': self.scrape_apple_recommendations,
            'max': self.scrape_max_recommendations,
            'hulu': self.scrape_hulu_recommendations,
        }
        
        if service not in scrapers:
            logger.warning(f"No recommendations scraper for {service}")
            return []
        
        return await scrapers[service]()
    
    async def scrape_all_recommendations(self) -> Dict[str, List[RecommendationEntry]]:
        """Scrape recommendations from all supported services."""
        results = {}
        for service in ['netflix', 'prime', 'disney', 'apple', 'max', 'hulu']:
            try:
                results[service] = await self.scrape_recommendations(service)
                logger.info(f"{service}: Got {len(results[service])} recommendations")
            except Exception as e:
                logger.error(f"{service} recommendations error: {e}")
                results[service] = []
        return results
    
    async def close(self):
        """Clean up resources."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


# Synchronous wrappers for Flask

def _run_async(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def scrape_service_sync(service: str) -> List[WatchHistoryEntry]:
    """Synchronous wrapper for scraping watch history from a service."""
    async def _scrape():
        poller = BrowserPoller()
        try:
            return await poller.scrape_service(service)
        finally:
            await poller.close()
    
    return _run_async(_scrape())


def scrape_watchlist_sync(service: str) -> List[WatchlistEntry]:
    """Synchronous wrapper for scraping watchlist from a service."""
    async def _scrape():
        poller = BrowserPoller()
        try:
            return await poller.scrape_watchlist(service)
        finally:
            await poller.close()
    
    return _run_async(_scrape())


def scrape_all_watchlists_sync() -> Dict[str, List[WatchlistEntry]]:
    """Synchronous wrapper for scraping all watchlists."""
    async def _scrape():
        poller = BrowserPoller()
        try:
            return await poller.scrape_all_watchlists()
        finally:
            await poller.close()
    
    return _run_async(_scrape())


def scrape_recommendations_sync(service: str) -> List[RecommendationEntry]:
    """Synchronous wrapper for scraping recommendations from a service."""
    async def _scrape():
        poller = BrowserPoller()
        try:
            return await poller.scrape_recommendations(service)
        finally:
            await poller.close()
    
    return _run_async(_scrape())


def scrape_all_recommendations_sync() -> Dict[str, List[RecommendationEntry]]:
    """Synchronous wrapper for scraping all recommendations."""
    async def _scrape():
        poller = BrowserPoller()
        try:
            return await poller.scrape_all_recommendations()
        finally:
            await poller.close()
    
    return _run_async(_scrape())

