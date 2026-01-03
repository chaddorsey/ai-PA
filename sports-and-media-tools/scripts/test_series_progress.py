#!/usr/bin/env python3
"""
Test Series Progress Scraper

Tests the series progress scraping functionality for Max, Disney+, and Apple TV+.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Add watch-history-service to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'watch-history-service'))

from series_progress_scraper import (
    MaxSeriesProgressScraper,
    DisneySeriesProgressScraper,
    AppleSeriesProgressScraper,
    HuluSeriesProgressScraper,
    series_progress_to_dict
)

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path(__file__).parent.parent / 'credentials' / 'browser_states'

# Test URLs
TEST_SERIES = {
    'max': {
        'name': 'The White Lotus',
        # The White Lotus - 3 seasons, good test case
        'url': 'https://play.hbomax.com/show/14f9834d-bc23-41a8-ab61-5c8abdbea505'
    },
    'disney': {
        'name': 'Andor',
        # Andor - 2 seasons
        'url': 'https://www.disneyplus.com/browse/entity-faba988a-a9f5-45f2-a074-0775a7d6f67a'
    },
    'apple': {
        'name': 'Murderbot',
        # Murderbot - 1 season  
        'url': 'https://tv.apple.com/us/show/murderbot/umc.cmc.5owrzntj9v1gpg31wshflud03'
    },
    'hulu': {
        'name': 'The Bear',
        # Popular Hulu original - 3 seasons
        'url': 'https://www.hulu.com/series/the-bear-05eb6a8e-90ed-4947-8c0b-e6536cbddd5f'
    }
}

# Alternative test URLs
ALT_TEST_SERIES = {
    'max_lwt': {
        'name': 'Last Week Tonight',
        'url': 'https://play.hbomax.com/topical/f7ebcd02-6641-4ec5-a392-07e58196808f'
    }
}


async def test_service(service: str, headless: bool = True):
    """Test series progress scraping for a service."""
    from playwright.async_api import async_playwright
    
    if service not in TEST_SERIES:
        logger.error(f"Unknown service: {service}")
        return None
    
    test_data = TEST_SERIES[service]
    state_file = CREDENTIALS_PATH / f'{service}_state.json'
    
    if not state_file.exists():
        logger.error(f"Browser state file not found: {state_file}")
        return None
    
    logger.info(f"Testing {service} with series: {test_data['name']}")
    logger.info(f"URL: {test_data['url']}")
    
    scrapers = {
        'max': MaxSeriesProgressScraper,
        'disney': DisneySeriesProgressScraper,
        'apple': AppleSeriesProgressScraper,
        'hulu': HuluSeriesProgressScraper,
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        
        with open(state_file, 'r') as f:
            storage_state = json.load(f)
        
        context = await browser.new_context(storage_state=storage_state)
        
        try:
            scraper = scrapers[service](context)
            progress = await scraper.get_series_progress(test_data['url'])
            
            if progress:
                result = series_progress_to_dict(progress)
                
                print(f"\n{'='*60}")
                print(f"Series: {progress.series_title}")
                print(f"Service: {progress.service}")
                print(f"{'='*60}")
                print(f"Total Seasons: {progress.total_seasons}")
                print(f"Total Episodes: {progress.total_episodes}")
                print(f"  - Watched: {progress.watched_episodes}")
                print(f"  - In Progress: {progress.in_progress_episodes}")
                print(f"  - Unwatched: {progress.unwatched_episodes}")
                
                if progress.next_episode:
                    next_ep = progress.next_episode
                    print(f"\nNext Episode: S{next_ep['season']}E{next_ep['episode']} - {next_ep['title']}")
                    if next_ep.get('progress', 0) > 0:
                        print(f"  Progress: {next_ep['progress']}%")
                
                print(f"\n--- Episode Details (first 10) ---")
                for ep in progress.episodes[:10]:
                    status_icon = '✓' if ep.status == 'watched' else ('▶' if ep.status == 'in_progress' else '○')
                    progress_str = f" ({ep.progress_percent}%)" if ep.status == 'in_progress' else ""
                    duration_str = f" [{ep.duration_minutes}m]" if ep.duration_minutes else ""
                    print(f"{status_icon} S{ep.season_number}E{ep.episode_number}: {ep.episode_title}{progress_str}{duration_str}")
                
                if len(progress.episodes) > 10:
                    print(f"  ... and {len(progress.episodes) - 10} more episodes")
                
                return result
            else:
                logger.error(f"Failed to scrape series progress for {service}")
                return None
                
        finally:
            await context.close()
            await browser.close()


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Test series progress scraping')
    parser.add_argument('service', choices=['max', 'disney', 'apple', 'hulu', 'all'], 
                        help='Service to test')
    parser.add_argument('--visible', action='store_true', 
                        help='Run browser in visible mode (not headless)')
    parser.add_argument('--url', type=str, help='Custom series URL to test')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Configure logging based on args
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if args.service == 'all':
        for service in ['max', 'disney', 'apple', 'hulu']:
            await test_service(service, headless=not args.visible)
            print()
    else:
        if args.url:
            TEST_SERIES[args.service]['url'] = args.url
        await test_service(args.service, headless=not args.visible)


if __name__ == '__main__':
    asyncio.run(main())

