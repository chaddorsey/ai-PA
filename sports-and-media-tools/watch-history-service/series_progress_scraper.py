#!/usr/bin/env python3
"""
Series Progress Scraper

Scrapes episode-level watch progress from streaming services.
Tracks which episodes are watched, in-progress, or unwatched for each series.

Supports:
- Max (HBO)
- Disney+
- Apple TV+
- Hulu
- Netflix
- Prime Video
"""

import asyncio
import logging
import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class EpisodeProgress:
    """Represents the watch progress for a single episode."""
    service: str
    series_title: str
    series_id: str
    season_number: int
    episode_number: int
    episode_title: str
    duration_minutes: Optional[int]
    status: str  # 'watched', 'in_progress', 'unwatched'
    progress_percent: int  # 0-100
    deep_link: Optional[str]
    scraped_at: str


@dataclass
class SeriesProgress:
    """Represents the overall progress for a series."""
    service: str
    series_title: str
    series_id: str
    total_seasons: int
    total_episodes: int
    watched_episodes: int
    in_progress_episodes: int
    unwatched_episodes: int
    next_episode: Optional[Dict[str, Any]]  # season, episode, title
    episodes: List[EpisodeProgress]
    scraped_at: str


class MaxSeriesProgressScraper:
    """Scraper for Max (HBO) series episode progress."""
    
    def __init__(self, browser_context):
        """
        Initialize with a Playwright browser context.
        
        Args:
            browser_context: Playwright browser context with Max cookies loaded
        """
        self.context = browser_context
    
    async def get_series_progress(self, series_url: str) -> Optional[SeriesProgress]:
        """
        Scrape episode progress for a series.
        
        Args:
            series_url: URL to the series page on Max
            
        Returns:
            SeriesProgress object with all episode data
        """
        page = await self.context.new_page()
        
        try:
            logger.info(f"Max: Navigating to series page: {series_url}")
            await page.goto(series_url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(5)
            
            # Check if we're on a login page or error page
            current_url = page.url
            logger.info(f"Max: Current URL after load: {current_url}")
            
            # Check for profile selection screen
            profile_elem = await page.query_selector('[data-testid="profile-picker"], [class*="ProfilePicker"]')
            if profile_elem:
                logger.info("Max: Profile picker detected, attempting to select first profile")
                first_profile = await page.query_selector('[data-testid="profile-tile"], [class*="ProfileTile"]')
                if first_profile:
                    await first_profile.click()
                    await asyncio.sleep(3)
                    # Re-navigate to series page
                    await page.goto(series_url, wait_until='domcontentloaded', timeout=60000)
                    await asyncio.sleep(5)
            
            # Get series title
            series_title = await self._get_series_title(page)
            if not series_title:
                logger.warning("Max: Could not find series title")
                # Take a screenshot for debugging
                try:
                    await page.screenshot(path='/tmp/max_series_debug.png')
                    logger.info("Max: Debug screenshot saved to /tmp/max_series_debug.png")
                except Exception:
                    pass
                return None
            
            logger.info(f"Max: Scraping progress for '{series_title}'")
            
            # Extract series ID from URL
            series_id = self._extract_series_id(series_url)
            
            # Get all seasons
            seasons = await self._get_seasons(page)
            logger.info(f"Max: Found {len(seasons)} seasons")
            
            all_episodes = []
            
            # Check if we have a real season dropdown or just detected from page text
            has_season_dropdown = False
            toggle_labels = await page.query_selector_all('[class*="ToggleLabel"]')
            for label in toggle_labels:
                text = await label.inner_text()
                text = re.sub(r'[\u2066\u2067\u2068\u2069\u202A-\u202E]', '', text).strip()
                if re.search(r'Season\s+\d+', text, re.IGNORECASE):
                    has_season_dropdown = True
                    break
            
            # Determine which season is currently displayed
            current_displayed = None
            if has_season_dropdown:
                current_season_label = await page.query_selector('[class*="ToggleLabel"]')
                if current_season_label:
                    current_text = await current_season_label.inner_text()
                    current_text = re.sub(r'[\u2066\u2067\u2068\u2069\u202A-\u202E]', '', current_text)
                    for sn, sl in seasons:
                        if sl in current_text or current_text in sl:
                            current_displayed = sn
                            logger.info(f"Max: Currently displaying Season {sn}")
                            break
            else:
                # No dropdown - we're showing the only/current season
                if seasons:
                    current_displayed = seasons[0][0]
                    logger.info(f"Max: No season dropdown - showing Season {current_displayed}")
            
            for season_num, season_label in seasons:
                logger.info(f"Max: Processing {season_label}")
                
                # Only try to select season if there's a dropdown
                if has_season_dropdown:
                    selected = await self._select_season(page, season_label)
                    if not selected and season_num != current_displayed:
                        logger.warning(f"Max: Could not select {season_label}, skipping")
                        continue
                    # Wait for episode list to update
                    await asyncio.sleep(2)
                else:
                    # No dropdown - episodes are already displayed
                    if season_num != current_displayed:
                        logger.info(f"Max: No dropdown to select {season_label}, skipping")
                        continue
                
                # Get episodes for this season
                episodes = await self._get_season_episodes(page, series_title, series_id, season_num)
                all_episodes.extend(episodes)
                logger.info(f"Max: Found {len(episodes)} episodes in {season_label}")
            
            # Calculate summary stats
            watched = sum(1 for e in all_episodes if e.status == 'watched')
            in_progress = sum(1 for e in all_episodes if e.status == 'in_progress')
            unwatched = sum(1 for e in all_episodes if e.status == 'unwatched')
            
            # Find next episode to watch
            next_ep = None
            for ep in all_episodes:
                if ep.status in ('unwatched', 'in_progress'):
                    next_ep = {
                        'season': ep.season_number,
                        'episode': ep.episode_number,
                        'title': ep.episode_title,
                        'progress': ep.progress_percent
                    }
                    break
            
            return SeriesProgress(
                service='max',
                series_title=series_title,
                series_id=series_id,
                total_seasons=len(seasons),
                total_episodes=len(all_episodes),
                watched_episodes=watched,
                in_progress_episodes=in_progress,
                unwatched_episodes=unwatched,
                next_episode=next_ep,
                episodes=all_episodes,
                scraped_at=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"Max: Error scraping series progress: {e}")
            return None
        finally:
            await page.close()
    
    async def _get_series_title(self, page) -> Optional[str]:
        """Extract series title from page."""
        # Wait for page to fully load
        await asyncio.sleep(3)
        
        # BEST METHOD: Extract from page title - most reliable for Max
        # HBO Max titles have format "Series Name • HBO Max" or "Series Name | HBO Max"
        try:
            page_title = await page.title()
            if page_title:
                # Clean up the title - remove HBO Max suffix
                for separator in ['•', '|', '-']:
                    if separator in page_title:
                        series_name = page_title.split(separator)[0].strip()
                        # Remove hidden unicode characters (direction markers)
                        series_name = re.sub(r'[\u2066\u2067\u2068\u2069\u202A-\u202E]', '', series_name)
                        if series_name and len(series_name) > 1:
                            logger.info(f"Max: Extracted title from page title: '{series_name}'")
                            return series_name
        except Exception as e:
            logger.debug(f"Max: Could not get page title: {e}")
        
        # FALLBACK: Try DOM selectors
        selectors = [
            '[class*="DetailHeader"] h1',
            '[class*="HeroHeader"] h1',
            '[class*="SeriesHeader"] h1',
            '[data-testid="hero-title"]',
            'header h1',
        ]
        
        for sel in selectors:
            try:
                elem = await page.query_selector(sel)
                if elem:
                    text = await elem.inner_text()
                    # Clean unicode and filter out episode titles
                    text = re.sub(r'[\u2066\u2067\u2068\u2069\u202A-\u202E]', '', text).strip()
                    if text and len(text) > 1 and not re.match(r'^S\d+\s*E\d+', text):
                        logger.info(f"Max: Found title '{text}' using selector '{sel}'")
                        return text
            except Exception as e:
                logger.debug(f"Max: Selector {sel} failed: {e}")
        
        return None
    
    def _extract_series_id(self, url: str) -> str:
        """Extract series ID from Max URL."""
        # URLs like: /show/14f9834d-bc23-41a8-ab61-5c8abdbea505
        # or: /topical/f7ebcd02-6641-4ec5-a392-07e58196808f
        match = re.search(r'/(show|topical)/([a-f0-9-]+)', url)
        if match:
            return match.group(2)
        return url
    
    async def _get_seasons(self, page) -> List[tuple]:
        """
        Get list of seasons from the dropdown.
        
        Returns:
            List of (season_number, season_label) tuples
        """
        seasons = []
        
        # Scroll up to make sure season selector is visible
        await page.evaluate('window.scrollTo(0, 0)')
        await asyncio.sleep(1)
        
        # First, look for text containing "Season X" to identify the selector
        # The season selector on Max has a ToggleLabel with "Season X" text
        season_label_elem = None
        toggle_labels = await page.query_selector_all('[class*="ToggleLabel"]')
        
        for label in toggle_labels:
            text = await label.inner_text()
            text = re.sub(r'[\u2066\u2067\u2068\u2069\u202A-\u202E]', '', text).strip()
            if re.search(r'Season\s+\d+', text, re.IGNORECASE):
                season_label_elem = label
                logger.debug(f"Max: Found season label element with text: {text}")
                break
        
        if not season_label_elem:
            # Check for "Season X" text anywhere visible on page
            body_text = await page.evaluate('document.body.innerText')
            season_match = re.search(r'Season\s+(\d+)', body_text, re.IGNORECASE)
            if season_match:
                season_num = int(season_match.group(1))
                logger.info(f"Max: Found single season {season_num} from page text (no dropdown)")
                return [(season_num, f'Season {season_num}')]
            return [(1, 'Season 1')]
        
        # Get the dropdown button from the label
        dropdown = await season_label_elem.evaluate_handle('el => el.closest("button")')
        
        if not dropdown:
            # Just use the visible season
            text = await season_label_elem.inner_text()
            text = re.sub(r'[\u2066\u2067\u2068\u2069\u202A-\u202E]', '', text).strip()
            match = re.search(r'Season\s+(\d+)', text, re.IGNORECASE)
            if match:
                return [(int(match.group(1)), text)]
            return [(1, 'Season 1')]
        
        # Click to open dropdown using JavaScript to avoid overlay issues
        try:
            await dropdown.evaluate('el => el.click()')
            await asyncio.sleep(1.5)
        except Exception as e:
            logger.warning(f"Max: Could not click dropdown: {e}")
            # Return visible season
            text = await season_label_elem.inner_text()
            match = re.search(r'Season\s+(\d+)', text, re.IGNORECASE)
            if match:
                return [(int(match.group(1)), text.strip())]
            return [(1, 'Season 1')]
        
        # Get all options from the listbox - filter for Season options only
        options = await page.query_selector_all(
            '[role="listbox"] [role="option"], '
            '[data-testid="drop-down-menu"] li, '
            'ul[role="listbox"] li'
        )
        
        for opt in options:
            try:
                text = await opt.inner_text()
                text = re.sub(r'[\u2066\u2067\u2068\u2069\u202A-\u202E]', '', text).strip()
                match = re.search(r'Season\s+(\d+)', text, re.IGNORECASE)
                if match:
                    seasons.append((int(match.group(1)), text))
            except Exception:
                pass
        
        # Close dropdown
        try:
            await page.keyboard.press('Escape')
            await asyncio.sleep(0.5)
        except Exception:
            pass
        
        if not seasons:
            # Fallback: use visible season from label
            text = await season_label_elem.inner_text()
            text = re.sub(r'[\u2066\u2067\u2068\u2069\u202A-\u202E]', '', text).strip()
            match = re.search(r'Season\s+(\d+)', text, re.IGNORECASE)
            if match:
                logger.info(f"Max: No seasons in dropdown, using visible: {text}")
                seasons = [(int(match.group(1)), text)]
            else:
                seasons = [(1, 'Season 1')]
        else:
            logger.info(f"Max: Found seasons: {seasons}")
        
        return sorted(seasons, key=lambda x: x[0])
    
    async def _select_season(self, page, season_label: str) -> bool:
        """Select a specific season from the dropdown."""
        try:
            # Check if already on correct season
            current = await page.query_selector('[class*="ToggleLabel"], [class*="SelectSort"] span')
            if current:
                current_text = await current.inner_text()
                current_text = re.sub(r'[\u2066\u2067\u2068\u2069\u202A-\u202E]', '', current_text).strip()
                if season_label == current_text or season_label in current_text:
                    logger.info(f"Max: Already on {season_label}")
                    return True
                logger.debug(f"Max: Current season is '{current_text}', need to switch to '{season_label}'")
            
            # Find and click the dropdown
            dropdown = await page.query_selector(
                'button[id*="dropdown"][class*="SelectSort"], '
                'button[aria-haspopup="true"][class*="Select"]'
            )
            
            if not dropdown:
                # Try alternate selectors
                dropdown = await page.query_selector('button[aria-haspopup="true"]')
            
            if not dropdown:
                # Try finding button near the toggle label
                label = await page.query_selector('[class*="ToggleLabel"]')
                if label:
                    parent = await label.evaluate_handle('el => el.closest("button")')
                    if parent:
                        dropdown = parent
            
            if not dropdown:
                logger.warning(f"Max: Could not find season dropdown for {season_label}")
                return False
            
            logger.debug(f"Max: Found dropdown button, clicking...")
            
            # Click using JavaScript to avoid overlay issues
            # Retry mechanism for dropdown opening
            options = []
            for attempt in range(3):
                await dropdown.evaluate('el => el.click()')
                await asyncio.sleep(1.5 + attempt * 0.5)
                
                # Find the season options
                options = await page.query_selector_all(
                    '[role="listbox"] [role="option"], '
                    '[data-testid="drop-down-menu"] li, '
                    'ul[role="listbox"] li'
                )
                
                if options:
                    break
                else:
                    logger.debug(f"Max: Dropdown attempt {attempt + 1} - no options found, retrying...")
                    # Try scrolling up to make sure dropdown is visible
                    await page.evaluate('window.scrollTo(0, 0)')
                    await asyncio.sleep(0.5)
            
            logger.debug(f"Max: Found {len(options)} dropdown options")
            
            for opt in options:
                try:
                    text = await opt.inner_text()
                    text = re.sub(r'[\u2066\u2067\u2068\u2069\u202A-\u202E]', '', text).strip()
                    if season_label in text or text in season_label:
                        logger.debug(f"Max: Clicking option '{text}' for {season_label}")
                        await opt.evaluate('el => el.click()')
                        # Wait for page to update with new season's episodes
                        await asyncio.sleep(3)
                        # Scroll to ensure episode list refreshes
                        await page.evaluate('window.scrollTo(0, 0)')
                        await asyncio.sleep(0.5)
                        await page.evaluate('window.scrollTo(0, 300)')
                        await asyncio.sleep(1)
                        logger.info(f"Max: Selected {season_label}")
                        return True
                except Exception as e:
                    logger.debug(f"Max: Error processing option: {e}")
            
            # If we get here, option wasn't found - close dropdown
            logger.warning(f"Max: Season option '{season_label}' not found in dropdown")
            await page.keyboard.press('Escape')
            return False
            
        except Exception as e:
            logger.error(f"Max: Error selecting season: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    async def _get_season_episodes(
        self, 
        page, 
        series_title: str, 
        series_id: str, 
        season_num: int
    ) -> List[EpisodeProgress]:
        """Get episode progress for the current season."""
        episodes = []
        
        # Scroll down to load episode list and ensure all episodes are visible
        await page.evaluate('window.scrollTo(0, 300)')
        await asyncio.sleep(1)
        
        # Look for episodes section and scroll to load more
        for scroll_amount in [500, 800, 1200, 1600, 2000]:
            await page.evaluate(f'window.scrollTo(0, {scroll_amount})')
            await asyncio.sleep(0.3)
        
        # Scroll back up
        await page.evaluate('window.scrollTo(0, 300)')
        await asyncio.sleep(1)
        
        # Find episode tiles in tileList container
        # Each episode is in a StyledTileWrapper with an anchor containing data-sonic-type="video"
        episode_tiles = await page.query_selector_all(
            '[data-testid="tileList"] a[data-sonic-type="video"], '
            'a[data-sonic-type="video"][href*="/video/watch/"]'
        )
        
        logger.info(f"Max: Found {len(episode_tiles)} episode tiles")
        
        for idx, tile in enumerate(episode_tiles):
            try:
                ep_data = await self._parse_episode_tile(
                    tile, series_title, series_id, season_num, idx + 1
                )
                if ep_data:
                    episodes.append(ep_data)
            except Exception as e:
                logger.debug(f"Max: Error parsing episode tile {idx + 1}: {e}")
        
        # Sort by episode number and dedupe
        seen = set()
        unique_episodes = []
        for ep in sorted(episodes, key=lambda e: e.episode_number):
            key = (ep.season_number, ep.episode_number)
            if key not in seen:
                seen.add(key)
                unique_episodes.append(ep)
        
        return unique_episodes
    
    async def _parse_episode_tile(
        self,
        tile_element,
        series_title: str,
        series_id: str,
        season_num: int,
        default_ep_num: int
    ) -> Optional[EpisodeProgress]:
        """Parse episode info from a Max tile element using aria-label and progress bar."""
        
        # Get href for deep link
        href = await tile_element.get_attribute('href')
        deep_link = None
        if href:
            deep_link = f"https://play.hbomax.com{href}" if href.startswith('/') else href
        
        # Get aria-label which contains rich episode info
        # Format: "Watch Again: Season 3, Episode 1: Same Spirits, New Forms. 1 of 8. Rated TV-MA. Runtime 1 hour 1 minute..."
        # Or: "Watch Season 3, Episode 5: Full-Moon Party. 5 of 8. 2 minutes remaining..."
        aria_label = await tile_element.get_attribute('aria-label') or ''
        aria_label = re.sub(r'[\u2066\u2067\u2068\u2069\u202A-\u202E]', '', aria_label)
        
        # Determine watch status from aria-label
        status = 'unwatched'
        progress_percent = 0
        
        if 'Watch Again' in aria_label:
            status = 'watched'
            progress_percent = 100
        elif 'remaining' in aria_label.lower():
            status = 'in_progress'
            # Progress will be determined from progress bar
        elif aria_label.startswith('Watch ') and 'Watch Again' not in aria_label:
            # "Watch Season X, Episode Y..." or "Watch November 9..." means in progress or unwatched
            # If it has "remaining", it's in progress (handled above), otherwise unwatched
            status = 'unwatched'
        
        # Parse episode number from aria-label
        # Pattern 1: "Episode 1:" or "Episode 5:" (standard shows)
        # Pattern 2: "1 of 30" (topical shows like Last Week Tonight)
        ep_num = default_ep_num
        ep_match = re.search(r'Episode\s+(\d+)[:\s]', aria_label)
        if ep_match:
            ep_num = int(ep_match.group(1))
        else:
            # Try "X of Y" pattern for topical shows
            of_match = re.search(r'(\d+)\s+of\s+\d+', aria_label)
            if of_match:
                ep_num = int(of_match.group(1))
        
        # Parse episode title from aria-label
        # Pattern 1: "Episode 1: Same Spirits, New Forms." (standard shows)
        # Pattern 2: "November 16, 2025: Public Media." (topical shows - date: title)
        ep_title = f"Episode {ep_num}"
        title_match = re.search(r'Episode\s+\d+[:\s]+([^.]+?)\.', aria_label)
        if title_match:
            ep_title = title_match.group(1).strip()
        else:
            # Try date-based format: "Watch Again: November 16, 2025: Public Media."
            # or "November 16, 2025: Public Media. 1 of 30."
            date_title_match = re.search(
                r'(?:Watch(?:\s+Again)?[:\s]+)?'  # Optional "Watch" or "Watch Again:"
                r'(?:Season\s+\d+,\s+)?'  # Optional "Season X, "
                r'(\w+\s+\d+,\s+\d+)[:\s]+([^.]+?)\.', 
                aria_label
            )
            if date_title_match:
                date_str = date_title_match.group(1)
                title_str = date_title_match.group(2).strip()
                ep_title = f"{date_str}: {title_str}"
        
        # Parse duration from aria-label
        # Pattern: "Runtime 1 hour 1 minute" or "Runtime 1 hour" or "Runtime 40 minutes"
        duration = None
        runtime_match = re.search(r'Runtime\s+(\d+)\s*hour(?:s)?\s*(?:(\d+)\s*minute)?', aria_label, re.IGNORECASE)
        if runtime_match:
            hours = int(runtime_match.group(1))
            mins = int(runtime_match.group(2)) if runtime_match.group(2) else 0
            duration = hours * 60 + mins
        else:
            mins_match = re.search(r'Runtime\s+(\d+)\s*minute', aria_label, re.IGNORECASE)
            if mins_match:
                duration = int(mins_match.group(1))
        
        # Get progress bar percentage
        try:
            # Find progress bar within the tile's parent container
            parent = await tile_element.evaluate_handle('el => el.parentElement')
            progress_bar = await parent.query_selector('[data-testid="progress-bar"] div[class*="Progress"]')
            
            if not progress_bar:
                # Try within the tile itself
                progress_bar = await tile_element.query_selector('[data-testid="progress-bar"] div[class*="Progress"]')
            
            if progress_bar:
                style = await progress_bar.get_attribute('style') or ''
                width_match = re.search(r'width:\s*([\d.]+)%', style)
                if width_match:
                    progress_percent = int(float(width_match.group(1)))
                    if progress_percent >= 95:
                        status = 'watched'
                    elif progress_percent > 0:
                        status = 'in_progress'
        except Exception as e:
            logger.debug(f"Max: Could not get progress bar: {e}")
        
        logger.debug(f"Max: Parsed E{ep_num}: {ep_title} ({status}, {progress_percent}%)")
        
        return EpisodeProgress(
            service='max',
            series_title=series_title,
            series_id=series_id,
            season_number=season_num,
            episode_number=ep_num,
            episode_title=ep_title,
            duration_minutes=duration,
            status=status,
            progress_percent=progress_percent,
            deep_link=deep_link,
            scraped_at=datetime.now(timezone.utc).isoformat()
        )
    
    async def _parse_episode_from_link(
        self,
        link_element,
        series_title: str,
        series_id: str,
        season_num: int,
        default_ep_num: int
    ) -> Optional[EpisodeProgress]:
        """Parse episode info from a link element."""
        
        # Get the link href for deep link
        href = await link_element.get_attribute('href')
        deep_link = None
        if href:
            if href.startswith('/'):
                deep_link = f"https://play.hbomax.com{href}"
            else:
                deep_link = href
        
        # Get link text - contains episode info
        # Format: "E1: Same Spirits, New Forms TV‑MA1h 1m2025 Description..."
        link_text = await link_element.inner_text()
        # Clean unicode direction markers
        link_text = re.sub(r'[\u2066\u2067\u2068\u2069\u202A-\u202E]', '', link_text)
        
        ep_num = default_ep_num
        ep_title = f"Episode {ep_num}"
        duration = None
        
        # Parse episode number and title from text like "E1: Same Spirits, New Forms TV‑MA1h2025..."
        ep_match = re.match(r'E(\d+)[:\s]+([^T]+?)(?:TV|$)', link_text)
        if ep_match:
            ep_num = int(ep_match.group(1))
            ep_title = ep_match.group(2).strip()
            # Remove trailing rating/year if captured
            ep_title = re.sub(r'\s*TV.*$', '', ep_title).strip()
        else:
            # Try alternate pattern: "1. Title" 
            num_match = re.match(r'(?:Free)?(\d+)\.\s*([^T\n]+)', link_text)
            if num_match:
                ep_num = int(num_match.group(1))
                ep_title = num_match.group(2).strip()
        
        # Extract duration from text like "1h 2m" or "45m"
        dur_match = re.search(r'(\d+)h\s*(\d+)?m', link_text)
        if dur_match:
            hours = int(dur_match.group(1))
            mins = int(dur_match.group(2)) if dur_match.group(2) else 0
            duration = hours * 60 + mins
        else:
            # Just minutes
            mins_match = re.search(r'(\d+)m(?:\d|$|\s)', link_text)
            if mins_match:
                duration = int(mins_match.group(1))
        
        # Get progress/watch status
        # Need to check parent element for progress bar
        progress_percent = 0
        status = 'unwatched'
        
        try:
            parent = await link_element.evaluate_handle(
                'el => el.parentElement?.parentElement || el.parentElement'
            )
            
            # Look for progress bar
            progress_elem = await parent.query_selector('[class*="progress"], [class*="Progress"], [style*="width"]')
            if progress_elem:
                style = await progress_elem.get_attribute('style') or ''
                width_match = re.search(r'width:\s*([\d.]+)%', style)
                if width_match:
                    progress_percent = int(float(width_match.group(1)))
                    if progress_percent >= 95:
                        status = 'watched'
                    elif progress_percent > 0:
                        status = 'in_progress'
            
            # Check for watched/complete indicator (checkmark, replay icon)
            watched_elem = await parent.query_selector(
                '[class*="watched"], [class*="complete"], [class*="replay"], '
                '[class*="Watched"], [class*="Complete"], [class*="Replay"]'
            )
            if watched_elem:
                status = 'watched'
                progress_percent = 100
        except Exception:
            pass
        
        logger.debug(f"Max: Parsed episode E{ep_num}: {ep_title} ({status}, {progress_percent}%)")
        
        return EpisodeProgress(
            service='max',
            series_title=series_title,
            series_id=series_id,
            season_number=season_num,
            episode_number=ep_num,
            episode_title=ep_title,
            duration_minutes=duration,
            status=status,
            progress_percent=progress_percent,
            deep_link=deep_link,
            scraped_at=datetime.now(timezone.utc).isoformat()
        )
    
    async def _parse_episode_card(
        self, 
        container, 
        series_title: str, 
        series_id: str, 
        season_num: int, 
        default_ep_num: int
    ) -> Optional[EpisodeProgress]:
        """Parse a single episode card for progress data."""
        
        # Get episode number
        ep_num = default_ep_num
        ep_num_elem = await container.query_selector(
            '[class*="EpisodeNumber"], '
            '[class*="episode-number"], '
            'span[class*="number"]'
        )
        if ep_num_elem:
            text = await ep_num_elem.inner_text()
            match = re.search(r'(\d+)', text)
            if match:
                ep_num = int(match.group(1))
        
        # Get episode title
        ep_title = f"Episode {ep_num}"
        title_elem = await container.query_selector(
            'h3, h4, '
            '[class*="EpisodeTitle"], '
            '[class*="episode-title"], '
            '[class*="Title"]'
        )
        if title_elem:
            text = await title_elem.inner_text()
            if text:
                # Clean up title - remove episode number prefix if present
                text = re.sub(r'^\d+\.\s*', '', text.strip())
                if text:
                    ep_title = text
        
        # Get duration
        duration = None
        duration_elem = await container.query_selector(
            '[class*="Duration"], '
            '[class*="duration"], '
            '[class*="runtime"], '
            'time'
        )
        if duration_elem:
            text = await duration_elem.inner_text()
            # Parse "29m", "1h 2m", etc.
            hours = 0
            minutes = 0
            h_match = re.search(r'(\d+)\s*h', text, re.IGNORECASE)
            m_match = re.search(r'(\d+)\s*m', text, re.IGNORECASE)
            if h_match:
                hours = int(h_match.group(1))
            if m_match:
                minutes = int(m_match.group(1))
            duration = hours * 60 + minutes if (hours or minutes) else None
        
        # Get watch progress
        # Look for progress bar
        progress_percent = 0
        status = 'unwatched'
        
        # Check for progress bar with width style
        progress_bar = await container.query_selector(
            '[class*="progress"], '
            '[class*="Progress"], '
            '[style*="width"]'
        )
        if progress_bar:
            style = await progress_bar.get_attribute('style') or ''
            width_match = re.search(r'width:\s*([\d.]+)%', style)
            if width_match:
                progress_percent = int(float(width_match.group(1)))
                if progress_percent >= 95:
                    status = 'watched'
                elif progress_percent > 0:
                    status = 'in_progress'
        
        # Check for "watched" indicator (checkmark, replay icon)
        watched_indicator = await container.query_selector(
            '[class*="watched"], '
            '[class*="Watched"], '
            '[class*="complete"], '
            '[class*="replay"], '
            'svg[class*="check"]'
        )
        if watched_indicator:
            status = 'watched'
            progress_percent = 100
        
        # Get deep link
        deep_link = None
        link_elem = await container.query_selector('a[href]')
        if link_elem:
            href = await link_elem.get_attribute('href')
            if href:
                if href.startswith('/'):
                    deep_link = f"https://play.hbomax.com{href}"
                else:
                    deep_link = href
        
        return EpisodeProgress(
            service='max',
            series_title=series_title,
            series_id=series_id,
            season_number=season_num,
            episode_number=ep_num,
            episode_title=ep_title,
            duration_minutes=duration,
            status=status,
            progress_percent=progress_percent,
            deep_link=deep_link,
            scraped_at=datetime.now(timezone.utc).isoformat()
        )


class DisneySeriesProgressScraper:
    """Scraper for Disney+ series episode progress."""
    
    def __init__(self, browser_context):
        self.context = browser_context
    
    async def get_series_progress(self, series_url: str) -> Optional[SeriesProgress]:
        """Scrape episode progress for a Disney+ series."""
        page = await self.context.new_page()
        
        try:
            logger.info(f"Disney+: Navigating to series page: {series_url}")
            await page.goto(series_url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(5)
            
            # Get series title
            series_title = await self._get_series_title(page)
            if not series_title:
                logger.warning("Disney+: Could not find series title")
                return None
            
            logger.info(f"Disney+: Scraping progress for '{series_title}'")
            
            # Extract series ID from URL
            series_id = self._extract_series_id(series_url)
            
            # Make sure we're on the EPISODES tab (not EXTRAS or SUGGESTED)
            await self._click_episodes_tab(page)
            
            # Get all seasons
            seasons = await self._get_seasons(page)
            logger.info(f"Disney+: Found {len(seasons)} seasons")
            
            all_episodes = []
            
            for season_num, season_label in seasons:
                logger.info(f"Disney+: Processing {season_label}")
                
                await self._select_season(page, season_label)
                await asyncio.sleep(2)
                
                episodes = await self._get_season_episodes(page, series_title, series_id, season_num)
                all_episodes.extend(episodes)
                logger.info(f"Disney+: Found {len(episodes)} episodes in {season_label}")
            
            # Calculate stats
            watched = sum(1 for e in all_episodes if e.status == 'watched')
            in_progress = sum(1 for e in all_episodes if e.status == 'in_progress')
            unwatched = sum(1 for e in all_episodes if e.status == 'unwatched')
            
            next_ep = None
            for ep in all_episodes:
                if ep.status in ('unwatched', 'in_progress'):
                    next_ep = {
                        'season': ep.season_number,
                        'episode': ep.episode_number,
                        'title': ep.episode_title,
                        'progress': ep.progress_percent
                    }
                    break
            
            return SeriesProgress(
                service='disney',
                series_title=series_title,
                series_id=series_id,
                total_seasons=len(seasons),
                total_episodes=len(all_episodes),
                watched_episodes=watched,
                in_progress_episodes=in_progress,
                unwatched_episodes=unwatched,
                next_episode=next_ep,
                episodes=all_episodes,
                scraped_at=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"Disney+: Error scraping series progress: {e}")
            return None
        finally:
            await page.close()
    
    async def _get_series_title(self, page) -> Optional[str]:
        """Extract series title from page."""
        # First try h1 and specific selectors
        selectors = ['h1', '[data-testid="title"]', 'header h1']
        for sel in selectors:
            elem = await page.query_selector(sel)
            if elem:
                text = await elem.inner_text()
                if text and len(text) > 1:
                    return text.strip()
        
        # Fallback: extract from page title
        # Format: "Andor | Disney+"
        page_title = await page.title()
        if page_title:
            # Remove " | Disney+" suffix
            title = re.sub(r'\s*\|\s*Disney\+.*$', '', page_title).strip()
            if title and len(title) > 1:
                logger.info(f"Disney+: Extracted title from page title: '{title}'")
                return title
        
        return None
    
    def _extract_series_id(self, url: str) -> str:
        """Extract series ID from Disney+ URL."""
        match = re.search(r'/entity-([a-f0-9-]+)', url)
        if match:
            return match.group(1)
        return url
    
    async def _click_episodes_tab(self, page) -> bool:
        """Click on the EPISODES tab to ensure we're not on EXTRAS or SUGGESTED."""
        try:
            # Find the EPISODES tab using aria-label
            episodes_tab = await page.query_selector('[data-testid="details-page-tab"][aria-label="EPISODES"]')
            if episodes_tab:
                is_selected = await episodes_tab.get_attribute('aria-selected')
                if is_selected != 'true':
                    await episodes_tab.click()
                    await asyncio.sleep(1.5)
                    logger.info("Disney+: Clicked EPISODES tab")
                else:
                    logger.debug("Disney+: Already on EPISODES tab")
                return True
            else:
                logger.debug("Disney+: No EPISODES tab found (might be a movie or single content)")
                return False
        except Exception as e:
            logger.warning(f"Disney+: Could not click EPISODES tab: {e}")
            return False
    
    async def _get_seasons(self, page) -> List[tuple]:
        """Get list of seasons from the dropdown."""
        seasons = []
        
        # Disney+ uses button with aria-haspopup="listbox"
        dropdown = await page.query_selector('button[aria-haspopup="listbox"]')
        if not dropdown:
            return [(1, 'Season 1')]
        
        await dropdown.click()
        await asyncio.sleep(1)
        
        # Get options from listbox
        options = await page.query_selector_all('[role="option"], [role="listbox"] li')
        
        for opt in options:
            text = await opt.inner_text()
            match = re.search(r'Season\s+(\d+)', text, re.IGNORECASE)
            if match:
                seasons.append((int(match.group(1)), text.strip()))
        
        await page.keyboard.press('Escape')
        await asyncio.sleep(0.5)
        
        if not seasons:
            seasons = [(1, 'Season 1')]
        
        return sorted(seasons, key=lambda x: x[0])
    
    async def _select_season(self, page, season_label: str) -> bool:
        """Select a specific season."""
        try:
            dropdown = await page.query_selector('button[aria-haspopup="listbox"]')
            if not dropdown:
                return False
            
            await dropdown.click()
            await asyncio.sleep(1)
            
            options = await page.query_selector_all('[role="option"], [role="listbox"] li')
            for opt in options:
                text = await opt.inner_text()
                if season_label in text:
                    await opt.click()
                    await asyncio.sleep(2)
                    return True
            
            await page.keyboard.press('Escape')
            return False
        except Exception as e:
            logger.error(f"Disney+: Error selecting season: {e}")
            return False
    
    async def _get_season_episodes(self, page, series_title: str, series_id: str, season_num: int) -> List[EpisodeProgress]:
        """Get episode progress for current season."""
        episodes = []
        
        # Disney+ episodes are in <a> elements with data-testid="set-item"
        # Filter to only include actual episodes (have "Episode" in aria-label)
        all_links = await page.query_selector_all('a[data-testid="set-item"]')
        episode_links = []
        for link in all_links:
            aria = await link.get_attribute('aria-label') or ''
            # Only include if it looks like an episode
            if re.search(r'(?:Season\s+\d+\s+)?Episode\s+\d+', aria, re.IGNORECASE):
                episode_links.append(link)
        
        logger.info(f"Disney+: Found {len(episode_links)} episode tiles (filtered from {len(all_links)})")
        
        for idx, link in enumerate(episode_links):
            try:
                # Get aria-label which contains all the info
                aria_label = await link.get_attribute('aria-label') or ''
                href = await link.get_attribute('href') or ''
                
                # Parse episode number and title
                # Prefer the on-page title element: "1. Kassa" or "1. That Would Be Me"
                ep_num = idx + 1
                ep_title = f"Episode {ep_num}"
                
                # First try the title element which has clean data
                title_elem = await link.query_selector('[data-testid="standard-regular-list-item-title"] div')
                if title_elem:
                    text = await title_elem.inner_text()
                    # Format: "1. Kassa" or "1. That Would Be Me"
                    num_title_match = re.match(r'(\d+)\.\s+(.+)', text.strip())
                    if num_title_match:
                        ep_num = int(num_title_match.group(1))
                        ep_title = num_title_match.group(2).strip()
                
                # Fallback: parse from aria-label if title not found
                if ep_title == f"Episode {ep_num}":
                    # Format: "Disney+ Original Season 1 Episode 1 Kassa Cassian Andor's reckless..."
                    # The title ends before the description which usually has "... Rated" or starts lowercase
                    ep_match = re.search(r'Episode\s+(\d+)\s+(.+?)(?:\s+Rated|\s+Select|$)', aria_label)
                    if ep_match:
                        ep_num = int(ep_match.group(1))
                        # Extract title by finding where description starts (after a sentence)
                        title_and_desc = ep_match.group(2)
                        # Split by common patterns where title ends
                        title_parts = re.split(r'\s+(?=[A-Z][a-z]+\s+[a-z])', title_and_desc, 1)
                        if title_parts:
                            ep_title = title_parts[0].strip()
                
                # Get progress from aria-label ("100 percent complete" or "50 percent complete")
                progress_percent = 0
                status = 'unwatched'
                
                progress_match = re.search(r'(\d+)\s*percent\s*complete', aria_label, re.IGNORECASE)
                if progress_match:
                    progress_percent = int(progress_match.group(1))
                    if progress_percent >= 95:
                        status = 'watched'
                    elif progress_percent > 0:
                        status = 'in_progress'
                else:
                    # Fallback: check <progress> element
                    progress_bar = await link.query_selector('progress')
                    if progress_bar:
                        value = await progress_bar.get_attribute('value')
                        if value:
                            progress_percent = int(float(value))
                            if progress_percent >= 95:
                                status = 'watched'
                            elif progress_percent > 0:
                                status = 'in_progress'
                
                # Get duration from metadata
                duration = None
                duration_elem = await link.query_selector('[data-testid="standard-regular-list-metadata"] span[aria-hidden="true"]')
                if duration_elem:
                    dur_text = await duration_elem.inner_text()
                    # Format: "(42m)" or "(1h 30m)"
                    dur_match = re.search(r'\((?:(\d+)h\s*)?(\d+)m\)', dur_text)
                    if dur_match:
                        hours = int(dur_match.group(1) or 0)
                        minutes = int(dur_match.group(2))
                        duration = hours * 60 + minutes
                
                # Build deep link
                deep_link = None
                if href:
                    deep_link = f"https://www.disneyplus.com{href}" if href.startswith('/') else href
                
                episodes.append(EpisodeProgress(
                    service='disney',
                    series_title=series_title,
                    series_id=series_id,
                    season_number=season_num,
                    episode_number=ep_num,
                    episode_title=ep_title,
                    duration_minutes=duration,
                    status=status,
                    progress_percent=progress_percent,
                    deep_link=deep_link,
                    scraped_at=datetime.now(timezone.utc).isoformat()
                ))
                logger.debug(f"Disney+: Parsed S{season_num}E{ep_num}: {ep_title} ({status}, {progress_percent}%)")
                
            except Exception as e:
                logger.debug(f"Disney+: Error parsing episode {idx}: {e}")
        
        return episodes


class AppleSeriesProgressScraper:
    """Scraper for Apple TV+ series episode progress."""
    
    def __init__(self, browser_context):
        self.context = browser_context
    
    async def get_series_progress(self, series_url: str) -> Optional[SeriesProgress]:
        """Scrape episode progress for an Apple TV+ series."""
        page = await self.context.new_page()
        
        try:
            logger.info(f"Apple TV+: Navigating to series page: {series_url}")
            await page.goto(series_url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(5)
            
            # Get series title
            series_title = await self._get_series_title(page)
            if not series_title:
                logger.warning("Apple TV+: Could not find series title")
                return None
            
            logger.info(f"Apple TV+: Scraping progress for '{series_title}'")
            
            series_id = self._extract_series_id(series_url)
            
            # Get all seasons
            seasons = await self._get_seasons(page)
            logger.info(f"Apple TV+: Found {len(seasons)} seasons")
            
            all_episodes = []
            
            for season_num, season_label in seasons:
                logger.info(f"Apple TV+: Processing {season_label}")
                
                await self._select_season(page, season_num)
                await asyncio.sleep(2)
                
                episodes = await self._get_season_episodes(page, series_title, series_id, season_num)
                all_episodes.extend(episodes)
                logger.info(f"Apple TV+: Found {len(episodes)} episodes in {season_label}")
            
            # Calculate stats
            watched = sum(1 for e in all_episodes if e.status == 'watched')
            in_progress = sum(1 for e in all_episodes if e.status == 'in_progress')
            unwatched = sum(1 for e in all_episodes if e.status == 'unwatched')
            
            next_ep = None
            for ep in all_episodes:
                if ep.status in ('unwatched', 'in_progress'):
                    next_ep = {
                        'season': ep.season_number,
                        'episode': ep.episode_number,
                        'title': ep.episode_title,
                        'progress': ep.progress_percent
                    }
                    break
            
            return SeriesProgress(
                service='apple',
                series_title=series_title,
                series_id=series_id,
                total_seasons=len(seasons),
                total_episodes=len(all_episodes),
                watched_episodes=watched,
                in_progress_episodes=in_progress,
                unwatched_episodes=unwatched,
                next_episode=next_ep,
                episodes=all_episodes,
                scraped_at=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"Apple TV+: Error scraping series progress: {e}")
            return None
        finally:
            await page.close()
    
    async def _get_series_title(self, page) -> Optional[str]:
        """Extract series title from page."""
        selectors = ['h1', '[data-testid="title"]']
        for sel in selectors:
            elem = await page.query_selector(sel)
            if elem:
                text = await elem.inner_text()
                if text and len(text) > 1:
                    return text.strip()
        return None
    
    def _extract_series_id(self, url: str) -> str:
        """Extract series ID from Apple TV+ URL."""
        # URL: https://tv.apple.com/us/show/murderbot/umc.cmc.5owrzntj9v1gpg31wshflud03
        match = re.search(r'/(umc\.[a-z0-9.]+)$', url)
        if match:
            return match.group(1)
        return url
    
    async def _get_seasons(self, page) -> List[tuple]:
        """Get list of seasons from select element."""
        seasons = []
        
        # Apple uses <select> element
        select = await page.query_selector('select.select, select[data-testid="accessory-button-select"]')
        if not select:
            return [(1, 'Season 1')]
        
        options = await select.query_selector_all('option')
        
        for opt in options:
            text = await opt.inner_text()
            match = re.search(r'Season\s+(\d+)', text, re.IGNORECASE)
            if match:
                seasons.append((int(match.group(1)), text.strip()))
        
        if not seasons:
            seasons = [(1, 'Season 1')]
        
        return sorted(seasons, key=lambda x: x[0])
    
    async def _select_season(self, page, season_num: int) -> bool:
        """Select a specific season."""
        try:
            select = await page.query_selector('select.select, select[data-testid="accessory-button-select"]')
            if not select:
                return False
            
            # Select by value or index
            await select.select_option(index=season_num - 1)
            await asyncio.sleep(2)
            return True
        except Exception as e:
            logger.error(f"Apple TV+: Error selecting season: {e}")
            return False
    
    async def _get_season_episodes(self, page, series_title: str, series_id: str, season_num: int) -> List[EpisodeProgress]:
        """Get episode progress for current season."""
        episodes = []
        
        # Scroll to load episodes
        await page.evaluate('window.scrollTo(0, 800)')
        await asyncio.sleep(2)
        
        # Apple TV+ episodes are in links with href containing "/episode/"
        episode_links = await page.query_selector_all('a[href*="/episode/"]')
        logger.info(f"Apple TV+: Found {len(episode_links)} episode links")
        
        for idx, link in enumerate(episode_links):
            try:
                href = await link.get_attribute('href') or ''
                text = await link.inner_text()
                
                # Parse episode number from text
                # Format: "EPISODE 1 FreeCommerce On a fresh assignment..."
                ep_num = idx + 1
                ep_title = f"Episode {ep_num}"
                
                # Try to get episode number from link text
                ep_match = re.search(r'EPISODE\s+(\d+)', text)
                if ep_match:
                    ep_num = int(ep_match.group(1))
                
                # Get title from the cleaner .title element within the link
                title_elem = await link.query_selector('.title, [class*="title"][class*="svelte"]')
                if title_elem:
                    ep_title = (await title_elem.inner_text()).strip()
                    logger.debug(f"Apple TV+: Found title element: {ep_title}")
                else:
                    # Fallback: parse from link text  
                    ep_match_full = re.search(r'EPISODE\s+(\d+)\s+(.+)', text)
                    if ep_match_full:
                        rest = ep_match_full.group(2)
                        # Extract title by finding where description begins
                        words = rest.split()
                        title_words = []
                        for i, word in enumerate(words):
                            if i > 0 and word.lower() in ['a', 'an', 'the', 'on', 'in', 'at', 'with', 'as', 'for', 'from']:
                                break
                            if i > 0 and re.match(r'^[A-Z][a-z]+$', word):
                                next_word = words[i + 1] if i + 1 < len(words) else ''
                                if next_word and next_word[0].islower():
                                    break
                            title_words.append(word)
                            if len(title_words) >= 4:
                                break
                        ep_title = ' '.join(title_words)
                
                # Get the parent container to find play-state and progress elements
                # Apple uses svelte components - look for parent with play-state
                parent = await link.evaluate_handle('el => el.closest("div") || el.parentElement')
                
                progress_percent = 0
                status = 'unwatched'
                
                # Check for replay icon (watched) - has class "replay-icon"
                replay_icon = await link.query_selector('svg.replay-icon, [class*="replay-icon"]')
                if replay_icon:
                    status = 'watched'
                    progress_percent = 100
                else:
                    # Check for progress bar with --progress-width style
                    progress_fill = await link.query_selector('.progress-fill, [class*="progress-fill"]')
                    if progress_fill:
                        style = await progress_fill.get_attribute('style') or ''
                        width_match = re.search(r'--progress-width:\s*([\d.]+)%', style)
                        if width_match:
                            progress_percent = int(float(width_match.group(1)))
                            status = 'in_progress'
                    else:
                        # Check sibling/parent for progress bar
                        # Look in play-state container nearby
                        play_state = await link.query_selector('.play-state, [class*="play-state"]')
                        if play_state:
                            # Check for replay class
                            replay_svg = await play_state.query_selector('.replay-icon')
                            if replay_svg:
                                status = 'watched'
                                progress_percent = 100
                
                # Get duration if visible
                duration = None
                duration_text = text  # From link.inner_text() above
                m_match = re.search(r'(\d+)\s*min', duration_text, re.IGNORECASE)
                if m_match:
                    duration = int(m_match.group(1))
                
                # Build deep link
                deep_link = href if href.startswith('http') else f"https://tv.apple.com{href}" if href else None
                
                episodes.append(EpisodeProgress(
                    service='apple',
                    series_title=series_title,
                    series_id=series_id,
                    season_number=season_num,
                    episode_number=ep_num,
                    episode_title=ep_title,
                    duration_minutes=duration,
                    status=status,
                    progress_percent=progress_percent,
                    deep_link=deep_link,
                    scraped_at=datetime.now(timezone.utc).isoformat()
                ))
                logger.debug(f"Apple TV+: Parsed S{season_num}E{ep_num}: {ep_title} ({status}, {progress_percent}%)")
            except Exception as e:
                logger.debug(f"Apple TV+: Error parsing episode: {e}")
        
        return episodes


class HuluSeriesProgressScraper:
    """Scraper for Hulu series episode progress."""
    
    def __init__(self, browser_context):
        self.context = browser_context
    
    async def get_series_progress(self, series_url: str, series_title_hint: Optional[str] = None) -> Optional[SeriesProgress]:
        """Scrape episode progress for a Hulu series.
        
        Args:
            series_url: The Hulu series URL
            series_title_hint: Optional series title to use if not detected from page
        """
        page = await self.context.new_page()
        
        # Capture API data for episode durations
        self._api_duration_map = {}  # Map of episode_id -> duration_seconds
        
        async def capture_api_response(response):
            # Capture both main series API and season-specific APIs
            if 'discover.hulu.com/content/v5/hubs/series' in response.url:
                try:
                    data = await response.json()
                    self._parse_api_durations(data, response.url)
                except Exception as e:
                    logger.debug(f"Hulu: Error parsing API response: {e}")
        
        page.on('response', capture_api_response)
        
        try:
            logger.info(f"Hulu: Navigating to series page: {series_url}")
            await page.goto(series_url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(8)  # Hulu needs more time to load dynamic content
            
            logger.debug(f"Hulu: Captured {len(self._api_duration_map)} episode durations from API")
            
            # Scroll down to load the episode grid
            await page.evaluate('window.scrollTo(0, 600)')
            await asyncio.sleep(3)
            
            # Get series title from page, or use hint
            series_title = await self._get_series_title(page)
            if not series_title and series_title_hint:
                series_title = series_title_hint
                logger.info(f"Hulu: Using provided title hint: '{series_title}'")
            if not series_title:
                logger.warning("Hulu: Could not find series title")
                # Continue anyway if we have episodes
                series_title = "Unknown Series"
            
            logger.info(f"Hulu: Scraping progress for '{series_title}'")
            
            series_id = self._extract_series_id(series_url)
            
            # Get all seasons
            seasons = await self._get_seasons(page)
            logger.info(f"Hulu: Found {len(seasons)} seasons")
            
            all_episodes = []
            
            for season_num, season_label in seasons:
                logger.info(f"Hulu: Processing {season_label}")
                
                # Select the season (first season is already selected after initial load)
                if season_num > 1:
                    await self._select_season(page, season_label)
                    # Wait briefly for API response with season data to be captured
                    await asyncio.sleep(1)
                
                logger.debug(f"Hulu: Duration map has {len(self._api_duration_map)} entries before parsing {season_label}")
                episodes = await self._get_season_episodes(page, series_title, series_id, season_num)
                all_episodes.extend(episodes)
                logger.info(f"Hulu: Found {len(episodes)} episodes in {season_label}")
            
            # Calculate stats
            watched = sum(1 for e in all_episodes if e.status == 'watched')
            in_progress = sum(1 for e in all_episodes if e.status == 'in_progress')
            unwatched = sum(1 for e in all_episodes if e.status == 'unwatched')
            
            next_ep = None
            for ep in all_episodes:
                if ep.status in ('unwatched', 'in_progress'):
                    next_ep = {
                        'season': ep.season_number,
                        'episode': ep.episode_number,
                        'title': ep.episode_title,
                        'progress': ep.progress_percent
                    }
                    break
            
            return SeriesProgress(
                service='hulu',
                series_title=series_title,
                series_id=series_id,
                total_seasons=len(seasons),
                total_episodes=len(all_episodes),
                watched_episodes=watched,
                in_progress_episodes=in_progress,
                unwatched_episodes=unwatched,
                next_episode=next_ep,
                episodes=all_episodes,
                scraped_at=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"Hulu: Error scraping series progress: {e}")
            return None
        finally:
            await page.close()
    
    async def _get_series_title(self, page) -> Optional[str]:
        """Extract series title from page."""
        # Primary: Look for SimpleModalNav title (series detail modal)
        # Format: <div class="SimpleModalNav__title"><span class="TruncatedTextV2">The Bear</span></div>
        modal_title = await page.query_selector('[data-testid="simple-modal-nav-title"] .TruncatedTextV2, .SimpleModalNav__title .TruncatedTextV2')
        if modal_title:
            text = await modal_title.inner_text()
            if text and len(text) > 1:
                logger.info(f"Hulu: Extracted title from modal nav: '{text}'")
                return text.strip()
        
        # Fallback: Look for other title selectors
        title_selectors = [
            '[data-testid="simple-modal-nav-title"]',
            '.SimpleModalNav__title',
            '[data-testid="DetailEntityMetadata"] h1',
            '[class*="DetailEntityMetadata"] h1',
        ]
        
        for sel in title_selectors:
            elem = await page.query_selector(sel)
            if elem:
                text = await elem.inner_text()
                if text and len(text) > 1 and 'hulu' not in text.lower():
                    logger.info(f"Hulu: Extracted title from {sel}: '{text}'")
                    return text.strip()
        
        # Try to get from og:title meta
        og_title = await page.query_selector('meta[property="og:title"]')
        if og_title:
            content = await og_title.get_attribute('content')
            if content:
                # Format: "Watch The Bear Streaming Online | Hulu (Free Trial)"
                title = re.sub(r'^Watch\s+', '', content, flags=re.IGNORECASE)
                title = re.sub(r'\s*[\|–-].*$', '', title).strip()
                if title and len(title) > 1:
                    logger.info(f"Hulu: Extracted title from og:title: '{title}'")
                    return title
        
        return None
    
    def _extract_series_id(self, url: str) -> str:
        """Extract series ID from Hulu URL."""
        # URL patterns: /series/name-uuid or /watch/uuid
        match = re.search(r'/(?:series|watch)/(?:[^/]+-)?([a-f0-9-]{36})', url)
        if match:
            return match.group(1)
        return url
    
    def _parse_api_durations(self, api_data: dict, url: str = ''):
        """Parse episode durations from Hulu's discover API response.
        
        Two URL patterns:
        1. Main series: /hubs/series/{id} - has components[0].items[season].items[episode]
        2. Season-specific: /hubs/series/{id}/season/{n} - has items directly
        """
        try:
            # Check if this is a season-specific response (URL contains /season/N)
            season_match = re.search(r'/season/(\d+)', url)
            
            if season_match:
                # Season-specific API: items are directly in the response
                season_num = int(season_match.group(1))
                episodes = api_data.get('items', [])
                
                for ep in episodes:
                    ep_id = ep.get('id')
                    bundle = ep.get('bundle', {})
                    duration_sec = bundle.get('duration')
                    ep_num = ep.get('number')
                    
                    if duration_sec:
                        duration_min = duration_sec // 60
                        if ep_id:
                            self._api_duration_map[ep_id] = duration_min
                        if ep_num:
                            key = f"S{season_num}E{ep_num}"
                            self._api_duration_map[key] = duration_min
                
                logger.debug(f"Hulu: Parsed {len(episodes)} episodes from Season {season_num} API")
            else:
                # Main series API: nested structure
                components = api_data.get('components', [])
                if not components:
                    return
                
                episodes_comp = components[0]
                seasons = episodes_comp.get('items', [])
                
                for season in seasons:
                    episodes = season.get('items', [])
                    season_name_match = re.search(r'Season\s+(\d+)', season.get('name', ''), re.IGNORECASE)
                    season_num = int(season_name_match.group(1)) if season_name_match else 0
                    
                    for ep in episodes:
                        ep_id = ep.get('id')
                        bundle = ep.get('bundle', {})
                        duration_sec = bundle.get('duration')
                        ep_num = ep.get('number')
                        
                        if duration_sec:
                            duration_min = duration_sec // 60
                            if ep_id:
                                self._api_duration_map[ep_id] = duration_min
                            if season_num and ep_num:
                                key = f"S{season_num}E{ep_num}"
                                self._api_duration_map[key] = duration_min
            
            logger.info(f"Hulu: Duration map now has {len(self._api_duration_map)} entries")
        except Exception as e:
            logger.debug(f"Hulu: Error parsing API durations: {e}")
    
    async def _get_seasons(self, page) -> List[tuple]:
        """Get list of seasons from the dropdown."""
        seasons = []
        
        # Look for the DetailsDropdown container with the Select control
        # Hulu uses: div.DetailsDropdown > div.Select > button.Select__control
        dropdown = await page.query_selector('.DetailsDropdown button.Select__control, button.Select__control')
        if not dropdown:
            # Single season or no season selector
            logger.debug("Hulu: No season dropdown found")
            return [(1, 'Season 1')]
        
        # Get current selection text from the single-value div
        current_elem = await dropdown.query_selector('.Select__single-value, [data-automationid="detailsdropdown-selectedvalue"]')
        current_text = await current_elem.inner_text() if current_elem else ''
        logger.debug(f"Hulu: Current season selection: '{current_text}'")
        
        # Click to open dropdown
        await dropdown.click()
        await asyncio.sleep(1)
        
        # Find all options in the Select menu
        options = await page.query_selector_all('[class*="Select__option"], [role="option"], [class*="Select__menu"] div[class*="option"]')
        logger.debug(f"Hulu: Found {len(options)} season options")
        
        for opt in options:
            try:
                text = await opt.inner_text()
                match = re.search(r'Season\s+(\d+)', text, re.IGNORECASE)
                if match:
                    seasons.append((int(match.group(1)), text.strip()))
            except Exception:
                pass
        
        # Close dropdown by clicking the dropdown button again (not Escape which might dismiss the modal)
        await dropdown.click()
        await asyncio.sleep(0.5)
        
        if not seasons:
            # Try to get from current selection
            match = re.search(r'Season\s+(\d+)', current_text, re.IGNORECASE)
            if match:
                seasons = [(int(match.group(1)), current_text.strip())]
            else:
                seasons = [(1, 'Season 1')]
        
        logger.info(f"Hulu: Detected seasons: {seasons}")
        return sorted(seasons, key=lambda x: x[0])
    
    async def _select_season(self, page, season_label: str) -> bool:
        """Select a specific season."""
        try:
            # Scroll down to make the dropdown visible
            await page.evaluate('window.scrollTo(0, 600)')
            await asyncio.sleep(0.5)
            
            # Extract target season number
            target_season_match = re.search(r'Season\s+(\d+)', season_label, re.IGNORECASE)
            target_season_num = int(target_season_match.group(1)) if target_season_match else 0
            
            # Find the dropdown - could be in DetailsDropdown or SimpleModalNav when scrolled
            dropdown = await page.query_selector(
                '.DetailsDropdown button.Select__control, '
                'button.Select__control, '
                '.SimpleModalNav button.Select__control'
            )
            if not dropdown:
                logger.debug("Hulu: No dropdown found for season selection")
                return False
            
            # Check if already on this season
            current = await dropdown.query_selector('.Select__single-value, [data-automationid="detailsdropdown-selectedvalue"]')
            if current:
                current_text = await current.inner_text()
                if season_label in current_text:
                    logger.debug(f"Hulu: Already on {season_label}")
                    return True
            
            # Click dropdown to open
            await dropdown.click()
            await asyncio.sleep(0.5)
            
            # Go to top of list first, then navigate down to target season
            await page.keyboard.press('Home')
            await asyncio.sleep(0.3)
            
            # Navigate down to target season with pauses
            for i in range(target_season_num - 1):
                await page.keyboard.press('ArrowDown')
                await asyncio.sleep(0.3)
            
            # Press Enter to select
            await page.keyboard.press('Enter')
            logger.debug(f"Hulu: Selected {season_label} via arrow keys + Enter")
            await asyncio.sleep(1)
            
            # Wait for grid to update - poll until correct season or timeout
            for attempt in range(10):
                first_tile = await page.query_selector('[data-testid="all-up-grid"] button[aria-label]')
                if first_tile:
                    label = await first_tile.get_attribute('aria-label') or ''
                    label_match = re.match(r'S(\d+)\s+E', label)
                    if label_match and int(label_match.group(1)) == target_season_num:
                        logger.debug(f"Hulu: Grid updated to S{target_season_num} after {attempt * 0.5}s")
                        break
                await asyncio.sleep(0.5)
            
            # Check final state
            first_tile = await page.query_selector('[data-testid="all-up-grid"] button[aria-label]')
            if first_tile:
                label = await first_tile.get_attribute('aria-label') or ''
                label_match = re.match(r'S(\d+)\s+E', label)
                if label_match and int(label_match.group(1)) != target_season_num:
                    logger.warning(f"Hulu: Grid shows S{label_match.group(1)} but expected S{target_season_num}")
            
            logger.info(f"Hulu: Selected {season_label}")
            return True
        except Exception as e:
            logger.error(f"Hulu: Error selecting season: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    async def _get_season_episodes(self, page, series_title: str, series_id: str, season_num: int) -> List[EpisodeProgress]:
        """Get episode progress for current season."""
        episodes = []
        
        # Check if the series modal is still visible
        modal = await page.query_selector('[class*="SimpleModal"], .SimpleModalNav, [data-testid="simple-modal-nav-title"]')
        if not modal:
            logger.warning("Hulu: Series modal appears to be closed - cannot get episodes")
            return episodes
        
        # Scroll within the modal to ensure episode grid is loaded
        await page.evaluate('''() => {
            const modal = document.querySelector('[class*="SimpleModal"], [class*="modal-content"]');
            if (modal) { modal.scrollTop = 400; }
            else { window.scrollTo(0, 600); }
        }''')
        await asyncio.sleep(2)
        
        # Find the AllUpGrid which contains the series episodes
        episode_tiles = []
        
        # Method 1: Look for grid with all-up-grid testid
        grid = await page.query_selector('[data-testid="all-up-grid"]')
        if grid:
            # Try different selectors for tiles
            episode_tiles = await grid.query_selector_all('figure[data-testid="seh-tile"]')
            if not episode_tiles:
                episode_tiles = await grid.query_selector_all('.AllUpGrid__generic-tile')
            if episode_tiles:
                logger.info(f"Hulu: Found {len(episode_tiles)} episode tiles in grid")
        
        # Method 2: Find grid within visible-collection-impression container
        if not episode_tiles:
            containers = await page.query_selector_all('[data-testid="visible-collection-impression"]')
            logger.debug(f"Hulu: Found {len(containers)} visible-collection-impression containers")
            for container in containers:
                grid = await container.query_selector('.AllUpGrid')
                if grid:
                    episode_tiles = await grid.query_selector_all('figure[data-testid="seh-tile"]')
                    if episode_tiles:
                        logger.info(f"Hulu: Found {len(episode_tiles)} episode tiles in container")
                        break
        
        # Method 3: Fallback - find seh-tiles within the modal area
        if not episode_tiles:
            await asyncio.sleep(2)
            # Look for tiles anywhere in the modal
            episode_tiles = await page.query_selector_all('[class*="SimpleModal"] figure[data-testid="seh-tile"]')
            if episode_tiles:
                logger.info(f"Hulu: Found {len(episode_tiles)} episode tiles in modal (fallback)")
        
        if not episode_tiles:
            logger.warning(f"Hulu: No episode tiles found for Season {season_num}")
        
        # Extra wait to ensure tiles have refreshed with current season's data
        await asyncio.sleep(1)
        
        for idx, tile in enumerate(episode_tiles):
            try:
                # PRIMARY: Get episode info from button aria-label
                # Format: "S1 E1 - System" or full description
                button = await tile.query_selector('button[aria-label], button[data-testid="standard-emphasis-tile-thumbnail"]')
                ep_num = idx + 1
                ep_title = f"Episode {ep_num}"
                
                if button:
                    aria_label = await button.get_attribute('aria-label') or ''
                    logger.debug(f"Hulu: Tile {idx} aria-label: {aria_label[:80]}...")
                    
                    # Parse "S1 E1 - Title" pattern
                    match = re.match(r'S(\d+)\s+E(\d+)\s*[-–]\s*(.+?)(?:\s*$)', aria_label.strip())
                    if match:
                        title_season = int(match.group(1))
                        ep_num = int(match.group(2))
                        ep_title = match.group(3).strip()
                        # Don't skip based on season - Hulu might show cached tiles briefly
                        # Instead, trust the tile index for the episode within current season
                        if title_season != season_num:
                            logger.debug(f"Hulu: Tile shows S{title_season} but we're on S{season_num} - using tile index for ep_num")
                            ep_num = idx + 1  # Use index-based episode number
                    else:
                        # No season pattern - extract just episode info
                        # Format might be "E1 - Title" or just "Title"
                        ep_match = re.match(r'E(\d+)\s*[-–]\s*(.+?)(?:\s*$)', aria_label.strip())
                        if ep_match:
                            ep_num = int(ep_match.group(1))
                            ep_title = ep_match.group(2).strip()
                        else:
                            # Just use the label as title if it looks reasonable
                            if aria_label and len(aria_label) < 100:
                                ep_title = aria_label.strip()
                else:
                    # Fallback: Get title from title element
                    title_elem = await tile.query_selector('[data-testid="seh-tile-content-title"]')
                    if title_elem:
                        full_title = await title_elem.inner_text()
                        match = re.match(r'S(\d+)\s+E(\d+)\s*[-–]\s*(.+)', full_title.strip())
                        if match:
                            ep_num = int(match.group(2))
                            ep_title = match.group(3).strip()
                        else:
                            ep_match = re.match(r'E(\d+)\s*[-–]\s*(.+)', full_title.strip())
                            if ep_match:
                                ep_num = int(ep_match.group(1))
                                ep_title = ep_match.group(2).strip()
                            else:
                                ep_title = full_title.strip()
                
                # Get progress from status bar or progress indicator
                progress_percent = 0
                status = 'unwatched'
                
                # Check for status bar element
                status_bar = await tile.query_selector('[data-testid="status-bar"]')
                if status_bar:
                    aria = await status_bar.get_attribute('aria-label') or ''
                    # Format: "99% progressed"
                    pct_match = re.search(r'(\d+)%\s*progress', aria, re.IGNORECASE)
                    if pct_match:
                        progress_percent = int(pct_match.group(1))
                    else:
                        # Try style width
                        style = await status_bar.get_attribute('style') or ''
                        width_match = re.search(r'width:\s*([\d.]+)%', style)
                        if width_match:
                            progress_percent = int(float(width_match.group(1)))
                
                # Determine status based on progress
                if progress_percent >= 95:
                    status = 'watched'
                elif progress_percent > 0:
                    status = 'in_progress'
                
                # Get duration from API data (most reliable)
                duration = None
                api_key = f"S{season_num}E{ep_num}"
                if hasattr(self, '_api_duration_map') and api_key in self._api_duration_map:
                    duration = self._api_duration_map[api_key]
                else:
                    # Fallback: check aria-label of the tile button
                    tile_aria = await tile.get_attribute('aria-label') or ''
                    dur_match = re.search(r'(\d+)\s*min', tile_aria, re.IGNORECASE)
                    if dur_match:
                        duration = int(dur_match.group(1))
                
                episodes.append(EpisodeProgress(
                    service='hulu',
                    series_title=series_title,
                    series_id=series_id,
                    season_number=season_num,
                    episode_number=ep_num,
                    episode_title=ep_title,
                    duration_minutes=duration,
                    status=status,
                    progress_percent=progress_percent,
                    deep_link=None,  # Would need to extract from API/click
                    scraped_at=datetime.now(timezone.utc).isoformat()
                ))
                logger.debug(f"Hulu: Parsed S{season_num}E{ep_num}: {ep_title} ({status}, {progress_percent}%)")
                
            except Exception as e:
                logger.debug(f"Hulu: Error parsing episode {idx}: {e}")
        
        return episodes


class NetflixSeriesProgressScraper:
    """Scraper for Netflix series episode progress."""
    
    def __init__(self, browser_context):
        """
        Initialize with a Playwright browser context.
        
        Args:
            browser_context: Playwright browser context with Netflix cookies loaded
        """
        self.context = browser_context
    
    async def get_series_progress(self, series_url: str) -> Optional[SeriesProgress]:
        """
        Scrape episode progress for a Netflix series.
        
        Args:
            series_url: URL to the series page on Netflix (e.g., https://www.netflix.com/title/81057282)
            
        Returns:
            SeriesProgress object with all episode data
        """
        page = await self.context.new_page()
        
        try:
            logger.info(f"Netflix: Navigating to series page: {series_url}")
            await page.goto(series_url, wait_until='networkidle', timeout=60000)
            await asyncio.sleep(6)
            
            # Check for profile selection ("Who's watching")
            content = await page.content()
            needs_profile = 'Who' in content and 'watching' in content
            
            if needs_profile:
                logger.info("Netflix: Profile selection screen detected, selecting first profile")
                # Try various profile selectors
                profile_selectors = [
                    '.profile-link',
                    '[class*="profile-icon"]',
                    '.list-profiles a',
                    'a[href*="browse"]',
                    '.profile-name',
                    'li.profile',
                    '[data-uia="profile-link"]',
                ]
                
                for sel in profile_selectors:
                    profile = await page.query_selector(sel)
                    if profile:
                        logger.info(f"Netflix: Found profile with selector: {sel}")
                        await profile.click()
                        await asyncio.sleep(4)
                        break
                
                # Re-navigate to series page
                await page.goto(series_url, wait_until='networkidle', timeout=60000)
                await asyncio.sleep(6)
            
            # Also check for older profile gate
            profile_gate = await page.query_selector('[data-uia="profile-gate-container"], .profile-gate')
            if profile_gate:
                logger.info("Netflix: Profile gate detected, selecting first profile")
                first_profile = await page.query_selector('.profile-icon, [data-uia*="profile"]')
                if first_profile:
                    await first_profile.click()
                    await asyncio.sleep(3)
                    await page.goto(series_url, wait_until='networkidle', timeout=60000)
                    await asyncio.sleep(6)
            
            # Get series title from the season dropdown button (e.g., "Stranger Things 2")
            series_title = await self._get_series_title(page)
            if not series_title:
                logger.warning("Netflix: Could not find series title")
                # Try screenshot for debugging
                try:
                    await page.screenshot(path='/tmp/netflix_debug.png')
                    logger.info("Netflix: Debug screenshot saved to /tmp/netflix_debug.png")
                except Exception:
                    pass
                return None
            
            logger.info(f"Netflix: Scraping progress for '{series_title}'")
            
            # Extract series ID from URL
            series_id = self._extract_series_id(series_url)
            
            # Click "See All Episodes" to show all seasons at once
            await self._click_see_all_episodes(page)
            
            # Get all episodes (organized by season)
            all_episodes = await self._get_all_episodes(page, series_title, series_id)
            
            # Count seasons
            season_nums = set(ep.season_number for ep in all_episodes)
            num_seasons = len(season_nums) if season_nums else 1
            logger.info(f"Netflix: Found {len(all_episodes)} episodes across {num_seasons} seasons")
            
            # Calculate summary stats
            watched = sum(1 for ep in all_episodes if ep.status == 'watched')
            in_progress = sum(1 for ep in all_episodes if ep.status == 'in_progress')
            unwatched = sum(1 for ep in all_episodes if ep.status == 'unwatched')
            
            # Find next episode to watch
            next_episode = None
            for ep in sorted(all_episodes, key=lambda e: (e.season_number, e.episode_number)):
                if ep.status in ('unwatched', 'in_progress'):
                    next_episode = {
                        'season': ep.season_number,
                        'episode': ep.episode_number,
                        'title': ep.episode_title,
                        'progress': ep.progress_percent
                    }
                    break
            
            await page.close()
            
            return SeriesProgress(
                service='netflix',
                series_title=series_title,
                series_id=series_id,
                total_seasons=num_seasons,
                total_episodes=len(all_episodes),
                watched_episodes=watched,
                in_progress_episodes=in_progress,
                unwatched_episodes=unwatched,
                next_episode=next_episode,
                episodes=all_episodes,
                scraped_at=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"Netflix: Error scraping series: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await page.close()
            return None
    
    async def _get_series_title(self, page) -> Optional[str]:
        """Extract series title from the page."""
        # First try the dropdown toggle button which shows current season
        # Format: "Stranger Things 2" -> extract base title "Stranger Things"
        dropdown = await page.query_selector('button.dropdown-toggle[aria-label="dropdown-menu-trigger-button"]')
        if dropdown:
            text = await dropdown.inner_text()
            text = text.strip()
            # Remove season number suffix (e.g., "Stranger Things 2" -> "Stranger Things")
            match = re.match(r'^(.+?)\s*\d*$', text)
            if match:
                base_title = match.group(1).strip()
                if base_title:
                    return base_title
            if text:
                return text
        
        # Try other selectors
        selectors = [
            '[data-uia="title-title"]',
            '.title-title',
            'h1.title',
            '.jawbone-title-link',
            'h1[class*="title"]',
            '.previewModal--player-titleTreatment-logo',
        ]
        
        for sel in selectors:
            elem = await page.query_selector(sel)
            if elem:
                alt = await elem.get_attribute('alt')
                if alt:
                    return alt.strip()
                text = await elem.inner_text()
                if text and len(text) > 1:
                    return text.strip()
        
        # Fallback: try to get from page title
        title = await page.title()
        if title and 'Netflix' in title:
            parts = title.split('|')
            if len(parts) >= 1:
                return parts[0].strip()
        
        return None
    
    def _extract_series_id(self, url: str) -> str:
        """Extract series ID from Netflix URL."""
        match = re.search(r'/title/(\d+)', url)
        if match:
            return match.group(1)
        return url.split('/')[-1].split('?')[0]
    
    async def _click_see_all_episodes(self, page):
        """Click 'See All Episodes' in the dropdown to show all seasons at once."""
        try:
            dropdown = await page.query_selector('button.dropdown-toggle[aria-label="dropdown-menu-trigger-button"]')
            if dropdown:
                await dropdown.click()
                await asyncio.sleep(1)
                
                menu_items = await page.query_selector_all('[role="menuitem"], [role="option"]')
                for item in menu_items:
                    text = await item.inner_text()
                    if 'See All' in text or 'All Episodes' in text:
                        logger.debug(f"Netflix: Clicking 'See All Episodes'")
                        await item.click()
                        await asyncio.sleep(2)
                        return
                
                # If no "See All" option, just close the dropdown
                await page.keyboard.press('Escape')
        except Exception as e:
            logger.debug(f"Netflix: Error clicking See All Episodes: {e}")
    
    async def _get_all_episodes(self, page, series_title: str, series_id: str) -> List[EpisodeProgress]:
        """Get all episodes from the page (after 'See All Episodes' is clicked)."""
        episodes = []
        
        # Wait briefly for episodes to load
        await asyncio.sleep(1)
        
        # Find all episode elements
        episode_elements = await page.query_selector_all('.episode-item')
        logger.info(f"Netflix: Found {len(episode_elements)} episode elements")
        
        current_season = 1
        last_ep_num = 0
        
        for idx, ep_elem in enumerate(episode_elements):
            try:
                # Get episode number from .titleCard-title_index
                ep_num_text = ""
                num_elem = await ep_elem.query_selector('.titleCard-title_index')
                if num_elem:
                    ep_num_text = await num_elem.inner_text()
                    ep_num_text = ep_num_text.strip()
                
                ep_num = idx + 1
                if ep_num_text:
                    match = re.search(r'(\d+)', ep_num_text)
                    if match:
                        ep_num = int(match.group(1))
                
                # Detect season change: if episode number resets (goes down), we're in a new season
                if ep_num <= last_ep_num and idx > 0:
                    current_season += 1
                last_ep_num = ep_num
                
                # Get episode title from .titleCard-title_text or aria-label
                ep_title = f"Episode {ep_num}"
                title_elem = await ep_elem.query_selector('.titleCard-title_text')
                if title_elem:
                    ep_title = (await title_elem.inner_text()).strip()
                else:
                    aria_label = await ep_elem.get_attribute('aria-label')
                    if aria_label:
                        ep_title = aria_label.strip()
                
                # Get duration from .titleCard-duration .duration
                duration = None
                dur_elem = await ep_elem.query_selector('.titleCard-duration .duration, .duration')
                if dur_elem:
                    dur_text = await dur_elem.inner_text()
                    match = re.search(r'(\d+)\s*m', dur_text)
                    if match:
                        duration = int(match.group(1))
                
                # Get progress from progress.titleCard-progress element (value 0-1)
                progress_percent = 0
                status = 'unwatched'
                
                progress_bar = await ep_elem.query_selector('progress.titleCard-progress')
                if progress_bar:
                    value = await progress_bar.get_attribute('value')
                    if value:
                        try:
                            progress_percent = int(float(value) * 100)
                        except ValueError:
                            pass
                
                # Determine status
                if progress_percent >= 90:
                    status = 'watched'
                elif progress_percent > 0:
                    status = 'in_progress'
                
                # Extract video ID for deep link
                video_id = None
                tracking_elem = await ep_elem.query_selector('.ptrack-content[data-ui-tracking-context]')
                if tracking_elem:
                    tracking_data = await tracking_elem.get_attribute('data-ui-tracking-context')
                    if tracking_data:
                        vid_match = re.search(r'"video_id":(\d+)', tracking_data)
                        if vid_match:
                            video_id = vid_match.group(1)
                
                deep_link = f"https://www.netflix.com/watch/{video_id}" if video_id else f"https://www.netflix.com/title/{series_id}"
                
                episodes.append(EpisodeProgress(
                    service='netflix',
                    series_title=series_title,
                    series_id=series_id,
                    season_number=current_season,
                    episode_number=ep_num,
                    episode_title=ep_title,
                    duration_minutes=duration,
                    status=status,
                    progress_percent=progress_percent,
                    deep_link=deep_link,
                    scraped_at=datetime.now(timezone.utc).isoformat()
                ))
                logger.debug(f"Netflix: S{current_season}E{ep_num}: {ep_title} ({status}, {progress_percent}%)")
                
            except Exception as e:
                logger.debug(f"Netflix: Error parsing episode {idx}: {e}")
        
        return episodes
    
    # Legacy methods kept for reference but not used
    async def _get_seasons(self, page) -> List[tuple]:
        """Get list of (season_number, season_label) tuples from dropdown."""
        seasons = []
        
        # Click the dropdown toggle to open season list
        dropdown_toggle = await page.query_selector('button.dropdown-toggle[aria-label="dropdown-menu-trigger-button"]')
        if dropdown_toggle:
            # Get current season from button text
            current_text = await dropdown_toggle.inner_text()
            logger.debug(f"Netflix: Current dropdown text: {current_text}")
            
            # Click to open dropdown
            await dropdown_toggle.click()
            await asyncio.sleep(1)
            
            # Find dropdown menu items
            menu_items = await page.query_selector_all('[role="menuitem"], .dropdown-menu-item, [role="option"]')
            if menu_items:
                for item in menu_items:
                    text = await item.inner_text()
                    text = text.strip()
                    
                    # Skip "See All Episodes" option
                    if 'See All' in text or 'All Episodes' in text:
                        continue
                    
                    # Handle multi-line format: "Stranger Things 2\n(9 Episodes)"
                    # Take only the first line for season detection
                    first_line = text.split('\n')[0].strip()
                    
                    # Look for explicit "Season X" pattern
                    season_match = re.search(r'Season\s*(\d+)', first_line, re.IGNORECASE)
                    if season_match:
                        seasons.append((int(season_match.group(1)), first_line))
                    else:
                        # Check for number at end (e.g., "Stranger Things 2")
                        num_match = re.search(r'\s(\d+)$', first_line)
                        if num_match:
                            seasons.append((int(num_match.group(1)), first_line))
                        elif len(seasons) == 0:
                            # First item without number is Season 1
                            seasons.append((1, first_line))
                
                logger.debug(f"Netflix: Detected seasons: {seasons}")
            
            # Close dropdown by clicking elsewhere or pressing Escape
            await page.keyboard.press('Escape')
            await asyncio.sleep(0.5)
        
        # Default to season 1 if none found
        if not seasons:
            seasons.append((1, "Season 1"))
        
        return sorted(seasons, key=lambda x: x[0])
    
    async def _select_season(self, page, season_num: int, season_label: str):
        """Select a season from the dropdown."""
        try:
            dropdown_toggle = await page.query_selector('button.dropdown-toggle[aria-label="dropdown-menu-trigger-button"]')
            if not dropdown_toggle:
                logger.debug("Netflix: No dropdown toggle found")
                return
            
            await dropdown_toggle.click()
            await asyncio.sleep(1)
            
            # Find menu items and identify the index to click
            menu_items = await page.query_selector_all('[role="menuitem"], .dropdown-menu-item, [role="option"]')
            target_index = None
            
            for idx, item in enumerate(menu_items):
                try:
                    text = await item.inner_text()
                    first_line = text.split('\n')[0].strip()
                    
                    # Skip "See All Episodes"
                    if 'See All' in first_line or 'All Episodes' in first_line:
                        continue
                    
                    # Match by exact label
                    if season_label == first_line:
                        target_index = idx
                        break
                    
                    # Match "Season X" pattern
                    if f"Season {season_num}" in first_line:
                        target_index = idx
                        break
                    
                    # Match by number at end (e.g., "Stranger Things 2" for season 2)
                    num_match = re.search(r'\s(\d+)$', first_line)
                    if num_match and int(num_match.group(1)) == season_num:
                        target_index = idx
                        break
                    
                    # Season 1 has no number
                    if season_num == 1 and not num_match:
                        target_index = idx
                        break
                except Exception:
                    continue
            
            if target_index is not None:
                # Re-query to get fresh reference
                menu_items = await page.query_selector_all('[role="menuitem"], .dropdown-menu-item, [role="option"]')
                if target_index < len(menu_items):
                    logger.debug(f"Netflix: Clicking season at index {target_index}")
                    await menu_items[target_index].click()
                    await asyncio.sleep(3)
                    return
            
            # Close if no match found
            await page.keyboard.press('Escape')
            
        except Exception as e:
            logger.debug(f"Netflix: Error selecting season: {e}")
            try:
                await page.keyboard.press('Escape')
            except Exception:
                pass
    
    async def _get_season_episodes(self, page, series_title: str, series_id: str, season_num: int) -> List[EpisodeProgress]:
        """Get all episodes for the current season."""
        episodes = []
        
        # Brief wait for episode list (Netflix re-renders quickly, long waits cause elements to disappear)
        await asyncio.sleep(1)
        
        # Netflix episode containers - try .episode-item first (more specific)
        episode_elements = await page.query_selector_all('.episode-item')
        if not episode_elements:
            # Wait a bit more and retry
            await asyncio.sleep(2)
            episode_elements = await page.query_selector_all('.episode-item')
        if not episode_elements:
            # Fallback to compound selector
            episode_elements = await page.query_selector_all('.titleCardList--container.episode-item')
        logger.info(f"Netflix: Found {len(episode_elements)} episode elements for season {season_num}")
        
        for idx, ep_elem in enumerate(episode_elements):
            try:
                # Get episode number from .titleCard-title_index
                ep_num = idx + 1
                num_elem = await ep_elem.query_selector('.titleCard-title_index')
                if num_elem:
                    num_text = await num_elem.inner_text()
                    match = re.search(r'(\d+)', num_text)
                    if match:
                        ep_num = int(match.group(1))
                
                # Get episode title from .titleCard-title_text
                ep_title = f"Episode {ep_num}"
                title_elem = await ep_elem.query_selector('.titleCard-title_text')
                if title_elem:
                    ep_title = (await title_elem.inner_text()).strip()
                else:
                    # Fallback: try aria-label on container
                    aria_label = await ep_elem.get_attribute('aria-label')
                    if aria_label:
                        ep_title = aria_label.strip()
                
                # Get duration from .titleCard-duration .duration
                duration = None
                dur_elem = await ep_elem.query_selector('.titleCard-duration .duration, .duration')
                if dur_elem:
                    dur_text = await dur_elem.inner_text()
                    match = re.search(r'(\d+)\s*m', dur_text)
                    if match:
                        duration = int(match.group(1))
                
                # Get progress from progress.titleCard-progress element
                # The value is 0-1 scale (e.g., value="0.9358198924731183")
                progress_percent = 0
                status = 'unwatched'
                
                progress_bar = await ep_elem.query_selector('progress.titleCard-progress')
                if progress_bar:
                    value = await progress_bar.get_attribute('value')
                    if value:
                        try:
                            progress_percent = int(float(value) * 100)
                        except ValueError:
                            pass
                
                # Determine status
                if progress_percent >= 90:
                    status = 'watched'
                elif progress_percent > 0:
                    status = 'in_progress'
                
                # Extract video ID for deep link from data-ui-tracking-context
                video_id = None
                tracking_elem = await ep_elem.query_selector('.ptrack-content[data-ui-tracking-context]')
                if tracking_elem:
                    tracking_data = await tracking_elem.get_attribute('data-ui-tracking-context')
                    if tracking_data:
                        vid_match = re.search(r'"video_id":(\d+)', tracking_data)
                        if vid_match:
                            video_id = vid_match.group(1)
                
                deep_link = f"https://www.netflix.com/watch/{video_id}" if video_id else f"https://www.netflix.com/title/{series_id}"
                
                episodes.append(EpisodeProgress(
                    service='netflix',
                    series_title=series_title,
                    series_id=series_id,
                    season_number=season_num,
                    episode_number=ep_num,
                    episode_title=ep_title,
                    duration_minutes=duration,
                    status=status,
                    progress_percent=progress_percent,
                    deep_link=deep_link,
                    scraped_at=datetime.now(timezone.utc).isoformat()
                ))
                logger.debug(f"Netflix: Parsed S{season_num}E{ep_num}: {ep_title} ({status}, {progress_percent}%)")
                
            except Exception as e:
                logger.debug(f"Netflix: Error parsing episode {idx}: {e}")
        
        return episodes


class PrimeSeriesProgressScraper:
    """Scraper for Prime Video series episode progress."""
    
    def __init__(self, browser_context):
        """
        Initialize with a Playwright browser context.
        
        Args:
            browser_context: Playwright browser context with Prime Video cookies loaded
        """
        self.context = browser_context
    
    async def get_series_progress(self, series_url: str) -> Optional[SeriesProgress]:
        """
        Scrape episode progress for a Prime Video series.
        
        Args:
            series_url: URL to the series page on Prime Video
            
        Returns:
            SeriesProgress object with all episode data
        """
        page = await self.context.new_page()
        
        try:
            logger.info(f"Prime: Navigating to series page: {series_url}")
            await page.goto(series_url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(6)
            
            # Check if we need to sign in
            if '/ap/signin' in page.url:
                logger.warning("Prime: Session expired, need to re-authenticate")
                await page.close()
                return None
            
            # First, ensure we're on the Episodes tab
            await self._click_episodes_tab(page)
            
            # Get series title
            series_title = await self._get_series_title(page)
            if not series_title:
                logger.warning("Prime: Could not find series title")
                try:
                    await page.screenshot(path='/tmp/prime_debug.png')
                    logger.info("Prime: Debug screenshot saved to /tmp/prime_debug.png")
                except Exception:
                    pass
                return None
            
            logger.info(f"Prime: Scraping progress for '{series_title}'")
            
            # Extract series ID from URL
            series_id = self._extract_series_id(series_url)
            
            # Get all seasons (returns tuples of season_num, url, label)
            seasons = await self._get_seasons(page)
            logger.info(f"Prime: Found {len(seasons)} seasons")
            
            all_episodes = []
            
            for season_data in seasons:
                season_num, season_url, season_label = season_data
                logger.info(f"Prime: Processing {season_label}")
                
                # Navigate to season page if different from current
                if len(seasons) > 1 and season_url != page.url:
                    logger.debug(f"Prime: Navigating to {season_url}")
                    await page.goto(season_url, wait_until='domcontentloaded', timeout=60000)
                    await asyncio.sleep(4)
                    # Click episodes tab again after navigation
                    await self._click_episodes_tab(page)
                
                # Get episodes for this season
                episodes = await self._get_season_episodes(page, series_title, series_id, season_num)
                all_episodes.extend(episodes)
                logger.info(f"Prime: Found {len(episodes)} episodes in {season_label}")
            
            # Calculate summary stats
            watched = sum(1 for ep in all_episodes if ep.status == 'watched')
            in_progress = sum(1 for ep in all_episodes if ep.status == 'in_progress')
            unwatched = sum(1 for ep in all_episodes if ep.status == 'unwatched')
            
            # Find next episode to watch
            next_episode = None
            for ep in all_episodes:
                if ep.status in ('unwatched', 'in_progress'):
                    next_episode = {
                        'season': ep.season_number,
                        'episode': ep.episode_number,
                        'title': ep.episode_title,
                        'progress': ep.progress_percent
                    }
                    break
            
            await page.close()
            
            return SeriesProgress(
                service='prime',
                series_title=series_title,
                series_id=series_id,
                total_seasons=len(seasons),
                total_episodes=len(all_episodes),
                watched_episodes=watched,
                in_progress_episodes=in_progress,
                unwatched_episodes=unwatched,
                next_episode=next_episode,
                episodes=all_episodes,
                scraped_at=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"Prime: Error scraping series: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await page.close()
            return None
    
    async def _click_episodes_tab(self, page):
        """Click the Episodes tab to ensure episode list is visible."""
        try:
            episodes_tab = await page.query_selector('button#tab-selector-episodes, [data-testid="btf-episodes-tab"]')
            if episodes_tab:
                await episodes_tab.click()
                await asyncio.sleep(2)
                logger.debug("Prime: Clicked Episodes tab")
        except Exception as e:
            logger.debug(f"Prime: Could not click Episodes tab: {e}")
    
    async def _get_series_title(self, page) -> Optional[str]:
        """Extract series title from the page."""
        selectors = [
            '[data-automation-id="title"]',
            'h1[data-automation-id="title"]',
            '.av-detail-section h1',
            'h1',
        ]
        
        for sel in selectors:
            elem = await page.query_selector(sel)
            if elem:
                text = await elem.inner_text()
                if text and len(text) > 1 and len(text) < 200:
                    return text.strip()
        
        # Fallback: try page title
        title = await page.title()
        if title and 'Prime Video' in title:
            # Format: "Show Name - Season 1 | Prime Video"
            parts = title.split('|')[0].split('-')
            if parts:
                return parts[0].strip()
        
        return None
    
    def _extract_series_id(self, url: str) -> str:
        """Extract series ID from Prime Video URL."""
        match = re.search(r'/detail/([A-Z0-9]+)', url)
        if match:
            return match.group(1)
        # Also try pageTypeId param
        match = re.search(r'pageTypeId=([A-Z0-9]+)', url)
        if match:
            return match.group(1)
        return url.split('/')[-1].split('?')[0]
    
    async def _get_seasons(self, page) -> List[tuple]:
        """Get list of (season_number, season_url, season_label) tuples.
        
        Prime Video uses different URLs for each season, so we return URLs too.
        """
        seasons = []
        
        # Look for season selector: label[for="av-droplist-av-atf-season-selector"]
        season_label_elem = await page.query_selector('label[for*="season-selector"]')
        if season_label_elem:
            # Click to open dropdown
            await season_label_elem.click()
            await asyncio.sleep(1)
            
            # Prime dropdown contains links to different season pages in a ul/li structure
            # Structure: <ul><li><a href="/gp/video/detail/ASIN">Season X</a></li></ul>
            season_links = await page.query_selector_all('label[for*="season-selector"] + ul li a, #av-droplist-av-atf-season-selector ~ ul li a')
            
            for link in season_links:
                try:
                    href = await link.get_attribute('href')
                    text = await link.inner_text()
                    text = text.strip()
                    match = re.search(r'Season\s*(\d+)', text, re.IGNORECASE)
                    if match and href:
                        season_num = int(match.group(1))
                        # Make full URL if relative
                        if href.startswith('/'):
                            href = f"https://www.amazon.com{href}"
                        seasons.append((season_num, href, text))
                        logger.debug(f"Prime: Found season {season_num}: {href}")
                except Exception as e:
                    logger.debug(f"Prime: Error parsing season link: {e}")
            
            # Close dropdown
            await page.keyboard.press('Escape')
            await asyncio.sleep(0.5)
        
        # If no seasons from dropdown, use current page as single season
        if not seasons:
            current_label = await page.query_selector('label[for*="season-selector"] span')
            if current_label:
                text = await current_label.inner_text()
                match = re.search(r'Season\s*(\d+)', text, re.IGNORECASE)
                if match:
                    seasons.append((int(match.group(1)), page.url, text.strip()))
            else:
                seasons.append((1, page.url, "Season 1"))
        
        return sorted(seasons, key=lambda x: x[0])
    
    async def _select_season(self, page, season_num: int, season_label: str):
        """Select a season from the dropdown."""
        # Click season selector to open dropdown
        season_selector = await page.query_selector('label[for*="season-selector"]')
        if season_selector:
            await season_selector.click()
            await asyncio.sleep(1)
            
            # Find and click matching option
            options = await page.query_selector_all('[role="option"], [role="menuitem"]')
            for opt in options:
                text = await opt.inner_text()
                if f"Season {season_num}" in text:
                    await opt.click()
                    await asyncio.sleep(2)
                    return
            
            # Close dropdown if no match
            await page.keyboard.press('Escape')
    
    async def _get_season_episodes(self, page, series_title: str, series_id: str, season_num: int) -> List[EpisodeProgress]:
        """Get all episodes for the current season."""
        episodes = []
        
        # Wait for episode list to load
        await asyncio.sleep(2)
        
        # Scroll to load all episodes
        await self._scroll_to_load_episodes(page)
        
        # Prime episode containers: li[data-testid="episode-list-item"]
        episode_elements = await page.query_selector_all('li[data-testid="episode-list-item"]')
        logger.debug(f"Prime: Found {len(episode_elements)} episode elements")
        
        for idx, ep_elem in enumerate(episode_elements):
            try:
                # Get episode title from h3 span - format: "5. The Schizoid Man"
                ep_num = idx + 1
                ep_title = f"Episode {ep_num}"
                
                title_elem = await ep_elem.query_selector('h3.AdOmdI span._36qUej, h3 span')
                if title_elem:
                    title_text = (await title_elem.inner_text()).strip()
                    # Parse "5. The Schizoid Man" format
                    match = re.match(r'^(\d+)\.\s*(.+)$', title_text)
                    if match:
                        ep_num = int(match.group(1))
                        ep_title = match.group(2).strip()
                    else:
                        ep_title = title_text
                
                # Get duration from [data-testid="episode-runtime"]
                duration = None
                dur_elem = await ep_elem.query_selector('[data-testid="episode-runtime"]')
                if dur_elem:
                    dur_text = await dur_elem.inner_text()
                    match = re.search(r'(\d+)\s*min', dur_text, re.IGNORECASE)
                    if match:
                        duration = int(match.group(1))
                    else:
                        # Try "1h 30m" format
                        h_match = re.search(r'(\d+)\s*h', dur_text)
                        m_match = re.search(r'(\d+)\s*m', dur_text)
                        if h_match or m_match:
                            hours = int(h_match.group(1)) if h_match else 0
                            mins = int(m_match.group(1)) if m_match else 0
                            duration = hours * 60 + mins
                
                # Check for watched status from data-is-watched attribute
                progress_percent = 0
                status = 'unwatched'
                
                watched_elem = await ep_elem.query_selector('[data-is-watched]')
                if watched_elem:
                    is_watched = await watched_elem.get_attribute('data-is-watched')
                    if is_watched == 'true':
                        progress_percent = 100
                        status = 'watched'
                
                # Also look for progress bar with gradient overlay
                if progress_percent == 0:
                    progress_bar = await ep_elem.query_selector('[class*="progress"], .dDns1P')
                    if progress_bar:
                        # Check for width style
                        inner = await progress_bar.query_selector('[class*="progress-fill"], ._1Arf3p')
                        if inner:
                            style = await inner.get_attribute('style') or ''
                            width_match = re.search(r'width:\s*([\d.]+)%', style)
                            if width_match:
                                progress_percent = int(float(width_match.group(1)))
                
                # Determine status based on progress
                if progress_percent >= 90:
                    status = 'watched'
                elif progress_percent > 0:
                    status = 'in_progress'
                
                # Get deep link from play button href
                deep_link = f"https://www.amazon.com/gp/video/detail/{series_id}"
                play_link = await ep_elem.query_selector('a[data-testid="episodes-playbutton"]')
                if play_link:
                    href = await play_link.get_attribute('href')
                    if href:
                        if href.startswith('/'):
                            deep_link = f"https://www.amazon.com{href}"
                        else:
                            deep_link = href
                
                episodes.append(EpisodeProgress(
                    service='prime',
                    series_title=series_title,
                    series_id=series_id,
                    season_number=season_num,
                    episode_number=ep_num,
                    episode_title=ep_title,
                    duration_minutes=duration,
                    status=status,
                    progress_percent=progress_percent,
                    deep_link=deep_link,
                    scraped_at=datetime.now(timezone.utc).isoformat()
                ))
                logger.debug(f"Prime: Parsed S{season_num}E{ep_num}: {ep_title} ({status}, {progress_percent}%, {duration}min)")
                
            except Exception as e:
                logger.debug(f"Prime: Error parsing episode {idx}: {e}")
        
        return episodes
    
    async def _scroll_to_load_episodes(self, page):
        """Scroll down to load all episodes (for lazy-loaded content)."""
        try:
            # Scroll page to load episodes
            for _ in range(3):
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(0.5)
            # Scroll back up
            await page.evaluate('window.scrollTo(0, 0)')
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.debug(f"Prime: Error scrolling: {e}")


def series_progress_to_dict(progress: SeriesProgress) -> Dict[str, Any]:
    """Convert SeriesProgress to dictionary for JSON serialization."""
    return {
        'service': progress.service,
        'series_title': progress.series_title,
        'series_id': progress.series_id,
        'total_seasons': progress.total_seasons,
        'total_episodes': progress.total_episodes,
        'watched_episodes': progress.watched_episodes,
        'in_progress_episodes': progress.in_progress_episodes,
        'unwatched_episodes': progress.unwatched_episodes,
        'next_episode': progress.next_episode,
        'episodes': [asdict(ep) for ep in progress.episodes],
        'scraped_at': progress.scraped_at
    }

