"""
Browser-based scraper for Netflix and Prime Video watch history.

Uses Playwright for browser automation to scrape the dedicated watch history pages:
- Netflix: https://www.netflix.com/settings/viewed/{profileGUID}
- Prime Video: https://www.amazon.com/gp/video/settings/watch-history

This is more reliable than API polling for these services as the pages are 
user-facing and less likely to change unexpectedly.
"""

import os
import json
import sqlite3
import logging
import asyncio
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

try:
    from playwright.async_api import async_playwright, Page, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logging.warning("Playwright not installed. Browser scraping disabled.")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_PATH = os.environ.get('DB_PATH', '/app/data/content_database.db')
CREDENTIALS_PATH = os.environ.get('CREDENTIALS_PATH', '/app/credentials')


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


def load_cookies(service: str) -> List[Dict]:
    """Load cookies from credentials file."""
    cred_file = os.path.join(CREDENTIALS_PATH, f'{service}_credentials.json')
    if os.path.exists(cred_file):
        with open(cred_file, 'r') as f:
            data = json.load(f)
            return data.get('cookies', [])
    return []


async def scrape_netflix_history(profile_guid: str, cookies: List[Dict]) -> List[WatchHistoryEntry]:
    """
    Scrape Netflix viewing activity page.
    
    URL: https://www.netflix.com/settings/viewed/{profileGUID}
    
    The page shows a list of all watched content with dates.
    """
    entries = []
    
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("Playwright not available for Netflix scraping")
        return entries
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        
        # Add cookies
        if cookies:
            # Convert cookies to Playwright format
            playwright_cookies = []
            for cookie in cookies:
                pc = {
                    'name': cookie.get('name'),
                    'value': cookie.get('value'),
                    'domain': cookie.get('domain', '.netflix.com'),
                    'path': cookie.get('path', '/'),
                }
                if cookie.get('expirationDate'):
                    pc['expires'] = cookie.get('expirationDate')
                playwright_cookies.append(pc)
            
            await context.add_cookies(playwright_cookies)
        
        page = await context.new_page()
        
        try:
            url = f"https://www.netflix.com/settings/viewed/{profile_guid}"
            logger.info(f"Navigating to Netflix viewing activity: {url}")
            
            await page.goto(url, wait_until='networkidle', timeout=60000)
            
            # Wait for content to load
            await page.wait_for_selector('.viewing-activity-footer-item, .retableRow', timeout=30000)
            
            # Check if we need to scroll to load more
            last_count = 0
            max_scrolls = 20
            
            for _ in range(max_scrolls):
                # Get current items
                items = await page.query_selector_all('.retableRow, .viewing-activity-row')
                current_count = len(items)
                
                if current_count == last_count:
                    break
                
                last_count = current_count
                
                # Scroll to bottom
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(1)
            
            # Parse all items
            rows = await page.query_selector_all('.retableRow, .viewing-activity-row')
            logger.info(f"Found {len(rows)} viewing activity rows")
            
            for row in rows:
                try:
                    # Get title link
                    title_link = await row.query_selector('a[href*="/title/"]')
                    if not title_link:
                        continue
                    
                    href = await title_link.get_attribute('href')
                    title_text = await title_link.inner_text()
                    
                    # Extract Netflix ID from URL
                    match = re.search(r'/title/(\d+)', href or '')
                    content_id = match.group(1) if match else ''
                    
                    # Get date
                    date_elem = await row.query_selector('.col.date, .date')
                    watch_date = None
                    if date_elem:
                        date_text = await date_elem.inner_text()
                        # Parse date like "1/2/26"
                        try:
                            # Try various date formats
                            for fmt in ['%m/%d/%y', '%m/%d/%Y', '%B %d, %Y']:
                                try:
                                    dt = datetime.strptime(date_text.strip(), fmt)
                                    watch_date = dt.isoformat()
                                    break
                                except ValueError:
                                    continue
                        except Exception:
                            pass
                    
                    # Parse title for episode info
                    episode_title = None
                    season_num = None
                    episode_num = None
                    main_title = title_text
                    
                    # Check for "Show: Season X: Episode Title" pattern
                    if ': Season' in title_text or ': Series' in title_text:
                        parts = title_text.split(': ')
                        main_title = parts[0]
                        for part in parts[1:]:
                            season_match = re.search(r'Season\s*(\d+)', part)
                            if season_match:
                                season_num = int(season_match.group(1))
                            elif not season_match:
                                episode_title = part
                    
                    entry = WatchHistoryEntry(
                        service='netflix',
                        title=main_title.strip(),
                        content_type='episode' if episode_title else 'movie',
                        content_id=content_id,
                        episode_title=episode_title,
                        season_number=season_num,
                        episode_number=episode_num,
                        watch_date=watch_date,
                        deep_link_id=content_id
                    )
                    entries.append(entry)
                    
                except Exception as e:
                    logger.warning(f"Error parsing Netflix row: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Netflix scraping error: {e}")
        finally:
            await browser.close()
    
    logger.info(f"Scraped {len(entries)} entries from Netflix")
    return entries


async def scrape_prime_history(cookies: List[Dict]) -> List[WatchHistoryEntry]:
    """
    Scrape Prime Video watch history page.
    
    URL: https://www.amazon.com/gp/video/settings/watch-history
    
    The page shows watched content with accordions for episodes.
    """
    entries = []
    
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("Playwright not available for Prime scraping")
        return entries
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        
        # Add cookies
        if cookies:
            playwright_cookies = []
            for cookie in cookies:
                pc = {
                    'name': cookie.get('name'),
                    'value': cookie.get('value'),
                    'domain': cookie.get('domain', '.amazon.com'),
                    'path': cookie.get('path', '/'),
                }
                if cookie.get('expirationDate'):
                    pc['expires'] = cookie.get('expirationDate')
                playwright_cookies.append(pc)
            
            await context.add_cookies(playwright_cookies)
        
        page = await context.new_page()
        
        try:
            url = "https://www.amazon.com/gp/video/settings/watch-history"
            logger.info(f"Navigating to Prime Video watch history: {url}")
            
            await page.goto(url, wait_until='networkidle', timeout=60000)
            
            # Wait for content
            await page.wait_for_selector('[data-testid="watch-history-item"], .watch-history-item', timeout=30000)
            
            # Expand all accordions for series
            accordions = await page.query_selector_all('[data-testid="expand-button"], .accordion-trigger')
            logger.info(f"Found {len(accordions)} accordions to expand")
            
            for accordion in accordions:
                try:
                    await accordion.click()
                    await asyncio.sleep(0.5)  # Wait for expansion
                except Exception:
                    pass
            
            # Load more if available
            for _ in range(10):  # Max 10 "load more" clicks
                try:
                    load_more = await page.query_selector('[data-testid="load-more"], .load-more-button')
                    if load_more:
                        await load_more.click()
                        await asyncio.sleep(2)
                    else:
                        break
                except Exception:
                    break
            
            # Parse all items
            items = await page.query_selector_all('[data-testid="watch-history-item"], .watch-history-item, .pv-wh-item')
            logger.info(f"Found {len(items)} watch history items")
            
            for item in items:
                try:
                    # Get title
                    title_elem = await item.query_selector('.title, [data-testid="title"], a[href*="/dp/"]')
                    if not title_elem:
                        continue
                    
                    title_text = await title_elem.inner_text()
                    
                    # Get ASIN from link
                    link = await item.query_selector('a[href*="/dp/"], a[href*="/gp/product/"]')
                    content_id = ''
                    if link:
                        href = await link.get_attribute('href')
                        asin_match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', href or '')
                        if asin_match:
                            content_id = asin_match.group(1)
                    
                    # Get watch date
                    date_elem = await item.query_selector('.date, [data-testid="watch-date"]')
                    watch_date = None
                    if date_elem:
                        date_text = await date_elem.inner_text()
                        try:
                            for fmt in ['%B %d, %Y', '%m/%d/%Y', '%m/%d/%y']:
                                try:
                                    dt = datetime.strptime(date_text.strip(), fmt)
                                    watch_date = dt.isoformat()
                                    break
                                except ValueError:
                                    continue
                        except Exception:
                            pass
                    
                    # Check for episode info
                    episode_title = None
                    season_num = None
                    episode_num = None
                    
                    # Look for "S1 E1" or "Season 1, Episode 1" patterns
                    ep_match = re.search(r'S(\d+)\s*E(\d+)', title_text)
                    if not ep_match:
                        ep_match = re.search(r'Season\s*(\d+).*Episode\s*(\d+)', title_text, re.IGNORECASE)
                    
                    if ep_match:
                        season_num = int(ep_match.group(1))
                        episode_num = int(ep_match.group(2))
                        # Extract episode title if present
                        ep_title_match = re.search(r'[:-]\s*(.+)$', title_text)
                        if ep_title_match:
                            episode_title = ep_title_match.group(1).strip()
                    
                    entry = WatchHistoryEntry(
                        service='prime',
                        title=title_text.split(':')[0].strip() if ':' in title_text else title_text.strip(),
                        content_type='episode' if season_num else 'movie',
                        content_id=content_id,
                        episode_title=episode_title,
                        season_number=season_num,
                        episode_number=episode_num,
                        watch_date=watch_date,
                        deep_link_id=content_id
                    )
                    entries.append(entry)
                    
                except Exception as e:
                    logger.warning(f"Error parsing Prime row: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Prime Video scraping error: {e}")
        finally:
            await browser.close()
    
    logger.info(f"Scraped {len(entries)} entries from Prime Video")
    return entries


async def scrape_all(username: str) -> Dict[str, Any]:
    """Scrape all browser-based services."""
    results = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'username': username,
        'services': {}
    }
    
    # Netflix
    try:
        netflix_creds = load_cookies('netflix')
        if netflix_creds:
            # Get profile GUID from credentials
            cred_file = os.path.join(CREDENTIALS_PATH, 'netflix_credentials.json')
            with open(cred_file, 'r') as f:
                data = json.load(f)
                profile_guid = data.get('profile_guid', '')
            
            if profile_guid:
                entries = await scrape_netflix_history(profile_guid, netflix_creds)
                results['services']['netflix'] = {
                    'status': 'ok',
                    'items_found': len(entries)
                }
            else:
                results['services']['netflix'] = {
                    'status': 'error',
                    'reason': 'No profile GUID configured'
                }
        else:
            results['services']['netflix'] = {
                'status': 'skipped',
                'reason': 'No credentials configured'
            }
    except Exception as e:
        results['services']['netflix'] = {
            'status': 'error',
            'reason': str(e)
        }
    
    # Prime Video
    try:
        prime_creds = load_cookies('prime')
        if prime_creds:
            entries = await scrape_prime_history(prime_creds)
            results['services']['prime'] = {
                'status': 'ok',
                'items_found': len(entries)
            }
        else:
            results['services']['prime'] = {
                'status': 'skipped',
                'reason': 'No credentials configured'
            }
    except Exception as e:
        results['services']['prime'] = {
            'status': 'error',
            'reason': str(e)
        }
    
    return results


def run_browser_scrape(username: str = 'chad') -> Dict[str, Any]:
    """Synchronous wrapper for browser scraping."""
    return asyncio.run(scrape_all(username))


if __name__ == '__main__':
    results = run_browser_scrape()
    print(json.dumps(results, indent=2))

