#!/usr/bin/env python3
"""
JustWatch Content Scraper

Scrapes JustWatch to build a local content database with deep link IDs
for the user's subscribed streaming services.

Subscribed services:
- Netflix, Hulu, Disney+, Max (HBO), Prime Video, Apple TV+, ESPN+
- YouTube (NFL Sunday Ticket), YouTube TV (NFL RedZone, DVR)

NOT subscribed: Peacock, Paramount+
"""

import json
import os
import time
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any
import requests
from urllib.parse import quote

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.environ.get('CONTENT_DB_PATH', '/app/data/content_database.db')

# JustWatch configuration
JUSTWATCH_BASE = "https://apis.justwatch.com/content"
JUSTWATCH_GRAPHQL = "https://apis.justwatch.com/graphql"

# Provider IDs for JustWatch (US market)
PROVIDER_IDS = {
    'netflix': 8,
    'hulu': 15,
    'disney': 337,
    'max': 1899,  # HBO Max / Max
    'prime': 9,   # Amazon Prime Video
    'apple': 350,  # Apple TV+
    'espn': 2303,  # ESPN+
    'youtube': 192,
}

# Services user subscribes to
SUBSCRIBED_SERVICES = ['netflix', 'hulu', 'disney', 'max', 'prime', 'apple', 'espn', 'youtube']


def init_database():
    """Initialize SQLite database for content storage."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Content table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            justwatch_id TEXT UNIQUE,
            title TEXT NOT NULL,
            content_type TEXT,  -- 'movie' or 'show'
            year INTEGER,
            imdb_id TEXT,
            tmdb_id TEXT,
            poster_url TEXT,
            description TEXT,
            genres TEXT,  -- JSON array
            rating_imdb REAL,
            rating_tmdb REAL,
            runtime_minutes INTEGER,  -- Duration in minutes (for movies, avg episode for shows)
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Add runtime_minutes column if it doesn't exist (migration for existing DBs)
    try:
        cursor.execute('ALTER TABLE content ADD COLUMN runtime_minutes INTEGER')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Streaming availability table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS streaming_availability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id INTEGER,
            service TEXT NOT NULL,  -- netflix, hulu, etc.
            content_id_for_service TEXT,  -- The deep link ID
            offer_type TEXT,  -- 'flatrate', 'rent', 'buy'
            quality TEXT,  -- 'hd', '4k', 'sd'
            deep_link_url TEXT,
            last_verified TIMESTAMP,
            FOREIGN KEY (content_id) REFERENCES content(id),
            UNIQUE(content_id, service, offer_type)
        )
    ''')
    
    # Popular/trending cache
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS popular_content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id INTEGER,
            service TEXT,
            rank INTEGER,
            category TEXT,  -- 'trending', 'new', 'top_rated'
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (content_id) REFERENCES content(id)
        )
    ''')
    
    # NFL content special table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS nfl_content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT UNIQUE,
            title TEXT,
            teams TEXT,  -- JSON: {"home": "Patriots", "away": "Bills"}
            date TEXT,
            youtube_video_id TEXT,
            youtube_tv_recording_id TEXT,
            nfl_sunday_ticket_available BOOLEAN,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_content_title ON content(title)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_streaming_service ON streaming_availability(service)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_streaming_content ON streaming_availability(content_id)')
    
    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")


def search_justwatch(query: str, content_type: str = None) -> List[Dict]:
    """
    Search JustWatch for content using their GraphQL API.
    
    Args:
        query: Search term
        content_type: 'movie' or 'show' (optional)
    
    Returns:
        List of content results
    """
    try:
        # Use JustWatch GraphQL API
        graphql_query = """
        query GetSearchTitles($country: Country!, $language: Language!, $first: Int!, $searchTitlesFilter: TitleFilter, $searchTitlesSortBy: PopularTitlesSorting! = POPULAR, $searchAfterCursor: String, $profile: PosterProfile, $backdropProfile: BackdropProfile, $format: ImageFormat) {
          popularTitles(
            country: $country
            first: $first
            filter: $searchTitlesFilter
            sortBy: $searchTitlesSortBy
            after: $searchAfterCursor
          ) {
            edges {
              node {
                id
                objectId
                objectType
                content(country: $country, language: $language) {
                  title
                  originalReleaseYear
                  shortDescription
                  runtime
                  fullPath
                  posterUrl(profile: $profile, format: $format)
                  backdrops(profile: $backdropProfile, format: $format) {
                    backdropUrl
                  }
                }
                ... on MovieOrShowOrSeason {
                  offers(country: $country, platform: WEB) {
                    monetizationType
                    presentationType
                    standardWebURL
                    package {
                      id
                      packageId
                      clearName
                    }
                  }
                }
              }
            }
          }
        }
        """
        
        variables = {
            "country": "US",
            "language": "en",
            "first": 20,
            "searchTitlesFilter": {
                "searchQuery": query
            },
            "searchTitlesSortBy": "POPULAR",
            "profile": "S166",
            "backdropProfile": "S1920",
            "format": "JPG"
        }
        
        if content_type:
            if content_type == 'movie':
                variables["searchTitlesFilter"]["objectTypes"] = ["MOVIE"]
            elif content_type == 'show':
                variables["searchTitlesFilter"]["objectTypes"] = ["SHOW"]
        
        response = requests.post(
            JUSTWATCH_GRAPHQL,
            json={"query": graphql_query, "variables": variables},
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Origin': 'https://www.justwatch.com',
                'Referer': 'https://www.justwatch.com/',
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            edges = data.get('data', {}).get('popularTitles', {}).get('edges', [])
            
            # Transform to expected format
            results = []
            for edge in edges:
                node = edge.get('node', {})
                content = node.get('content', {})
                
                # Map object type
                obj_type = node.get('objectType', '').lower()
                if obj_type == 'movie':
                    obj_type = 'movie'
                elif obj_type == 'show':
                    obj_type = 'show'
                
                results.append({
                    'id': node.get('objectId'),
                    'jw_entity_id': node.get('id'),
                    'object_type': obj_type,
                    'title': content.get('title'),
                    'original_release_year': content.get('originalReleaseYear'),
                    'short_description': content.get('shortDescription'),
                    'runtime_minutes': content.get('runtime'),  # Duration in minutes
                    'poster': content.get('posterUrl'),
                    'offers': node.get('offers', []),
                    'full_path': content.get('fullPath'),  # JustWatch URL path like /us/tv-show/scrubs
                })
            
            return results
        else:
            logger.warning(f"JustWatch GraphQL search failed: {response.status_code}")
            # Try fallback to simple search
            return search_justwatch_fallback(query, content_type)
            
    except Exception as e:
        logger.error(f"JustWatch search error: {e}")
        return search_justwatch_fallback(query, content_type)


def search_justwatch_fallback(query: str, content_type: str = None) -> List[Dict]:
    """
    Fallback search using JustWatch website scraping.
    
    Args:
        query: Search term
        content_type: 'movie' or 'show' (optional)
    
    Returns:
        List of content results
    """
    try:
        import urllib.parse
        
        # Use JustWatch search page
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.justwatch.com/us/search?q={encoded_query}"
        
        response = requests.get(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml',
            },
            timeout=30
        )
        
        if response.status_code == 200:
            # Parse HTML for basic info
            # This is a simplified fallback - just return empty for now
            # Full HTML parsing would require BeautifulSoup
            logger.info(f"Fallback search for '{query}' - page loaded but parsing not implemented")
            return []
        else:
            logger.warning(f"JustWatch fallback search failed: {response.status_code}")
            return []
            
    except Exception as e:
        logger.error(f"JustWatch fallback search error: {e}")
        return []


def get_content_details(justwatch_id: str, content_type: str) -> Optional[Dict]:
    """
    Get detailed content info including streaming availability.
    
    Args:
        justwatch_id: JustWatch content ID
        content_type: 'movie' or 'show'
    
    Returns:
        Content details with streaming info
    """
    try:
        url = f"{JUSTWATCH_BASE}/titles/{content_type}/{justwatch_id}/locale/en_US"
        
        response = requests.get(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
                'Accept': 'application/json',
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Failed to get content details: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Error getting content details: {e}")
        return None


def extract_deep_link_id_from_url(url: str, service: str) -> Optional[str]:
    """
    Extract the deep link content ID from a streaming service URL.
    
    Args:
        url: The streaming service URL
        service: Service name (netflix, hulu, etc.)
    
    Returns:
        Content ID suitable for Roku deep linking
    """
    if not url:
        return None
    
    try:
        if service == 'netflix':
            # Netflix: https://www.netflix.com/title/80057281
            if '/title/' in url:
                return url.split('/title/')[-1].split('?')[0].split('/')[0]
        
        elif service == 'hulu':
            # Hulu: various formats
            if '/series/' in url:
                parts = url.split('/series/')[-1].split('/')
                if parts:
                    return parts[0]
            elif '/movie/' in url:
                parts = url.split('/movie/')[-1].split('/')
                if parts:
                    return parts[0]
        
        elif service == 'disney':
            # Disney+: extract content ID
            if '/series/' in url or '/movies/' in url:
                parts = url.split('/')
                for part in parts:
                    if len(part) > 15 and '-' not in part[:10]:
                        return part
        
        elif service == 'max':
            # Max/HBO: URN style IDs
            parts = url.split('/')
            for part in parts:
                if part.startswith('urn:') or (len(part) > 20 and ':' in part):
                    return part
        
        elif service == 'prime':
            # Prime Video: /detail/xxx or /gp/video/detail/xxx
            if '/detail/' in url:
                return url.split('/detail/')[-1].split('/')[0].split('?')[0]
        
        elif service == 'apple':
            # Apple TV+: umc.cmc.xxxxx format
            parts = url.split('/')
            for part in parts:
                if 'umc.cmc.' in part:
                    # Extract the full umc.cmc.xxx portion
                    idx = part.find('umc.cmc.')
                    return part[idx:].split('?')[0]
            # Also check query params
            if 'umc.cmc.' in url:
                import re
                match = re.search(r'umc\.cmc\.[a-z0-9]+', url)
                if match:
                    return match.group(0)
        
        elif service == 'youtube':
            # YouTube: v=xxx or /watch/xxx
            if 'v=' in url:
                return url.split('v=')[-1].split('&')[0]
            elif '/watch/' in url:
                return url.split('/watch/')[-1].split('?')[0]
    
    except Exception:
        pass
    
    return None


def get_series_page_url(service: str, deep_link_url: str, full_path: str = None, title: str = None) -> Optional[str]:
    """
    Construct the proper series page URL for a streaming service.
    
    JustWatch often provides episode playback URLs in offers, but for series tracking
    we need the series page URL. This function attempts to construct or extract
    the correct series page URL.
    
    Args:
        service: Service name (netflix, hulu, max, etc.)
        deep_link_url: The URL from JustWatch offers (may be episode URL)
        full_path: JustWatch full_path like /us/tv-show/scrubs (optional)
        title: Title of the series for slug construction (optional)
    
    Returns:
        Series page URL suitable for scraping, or original URL if conversion not possible
    """
    if not deep_link_url:
        return None
    
    try:
        if service == 'netflix':
            # Netflix /title/ URLs work for both series and episodes
            # Keep as-is, scraper handles it
            return deep_link_url
        
        elif service == 'hulu':
            # Hulu episode URLs: /watch/UUID
            # Hulu series URLs: /series/{slug}
            if '/series/' in deep_link_url:
                return deep_link_url  # Already a series URL
            
            # Try to construct series URL from JustWatch full_path
            # full_path format: /us/tv-show/scrubs
            if full_path:
                # Extract slug from JustWatch path
                parts = full_path.strip('/').split('/')
                if len(parts) >= 3 and parts[1] == 'tv-show':
                    slug = parts[2]  # e.g., "scrubs"
                    # Construct Hulu series URL
                    # Note: Hulu series URLs are typically /series/{slug}-{uuid}
                    # We don't have the UUID, but the slug alone might redirect
                    return f"https://www.hulu.com/series/{slug}"
            
            # Fallback: return original, scraper will attempt to handle
            return deep_link_url
        
        elif service == 'max':
            # Max episode URLs: /video/watch/UUID
            # Max series URLs: /show/{slug} or /series/{slug}
            if '/show/' in deep_link_url or '/series/' in deep_link_url:
                return deep_link_url  # Already a series URL
            
            # Try to construct from JustWatch full_path
            if full_path:
                parts = full_path.strip('/').split('/')
                if len(parts) >= 3 and parts[1] == 'tv-show':
                    slug = parts[2]
                    return f"https://play.max.com/show/{slug}"
            
            return deep_link_url
        
        elif service == 'apple':
            # Apple TV+ episode URLs contain showId parameter
            # Already handled in scraper via showId extraction
            return deep_link_url
        
        elif service == 'prime':
            # Prime Video /detail/ URLs work for series
            # watch.amazon.com/detail?gti= format works
            return deep_link_url
        
        elif service == 'disney':
            # Disney+ /series/ URLs work directly
            return deep_link_url
        
        else:
            return deep_link_url
            
    except Exception:
        return deep_link_url


def extract_deep_link_id(offer: Dict, service: str) -> Optional[str]:
    """
    Extract the deep link content ID from a JustWatch offer.
    
    Args:
        offer: JustWatch offer object
        service: Service name (netflix, hulu, etc.)
    
    Returns:
        Content ID suitable for Roku deep linking
    """
    urls = offer.get('urls', {})
    standard_url = urls.get('standard_web', '')
    
    if service == 'netflix':
        # Netflix URLs: https://www.netflix.com/title/80057281
        if '/title/' in standard_url:
            return standard_url.split('/title/')[-1].split('?')[0]
    
    elif service == 'hulu':
        # Hulu needs the UUID from JustWatch offer
        # The offer has a 'package_short_name' and we can use the offer URL
        # Hulu deep links use UUIDs like "60da223c-d2a0-411a-95c9-665a839371f9"
        element_id = offer.get('element_id')
        if element_id:
            return element_id
    
    elif service == 'disney':
        # Disney+ URLs contain content IDs
        if 'disneyplus.com' in standard_url:
            # Extract from URL path
            parts = standard_url.split('/')
            for part in parts:
                if len(part) > 15 and not part.startswith('http'):
                    return part
    
    elif service == 'max':
        # Max/HBO URLs: contain URN-style IDs
        if 'max.com' in standard_url or 'hbomax.com' in standard_url:
            # Try to extract series/movie ID
            parts = standard_url.split('/')
            for part in parts:
                if part.startswith('urn:') or len(part) > 20:
                    return part
    
    elif service == 'prime':
        # Prime Video URLs contain ASIN-like IDs
        if 'amazon.com' in standard_url or 'primevideo.com' in standard_url:
            # Look for the ID in the URL
            if '/detail/' in standard_url:
                return standard_url.split('/detail/')[-1].split('/')[0]
            elif '/dp/' in standard_url:
                return standard_url.split('/dp/')[-1].split('/')[0]
    
    elif service == 'apple':
        # Apple TV+ URLs: https://tv.apple.com/us/show/slow-horses/umc.cmc.xxxxx
        if 'tv.apple.com' in standard_url:
            parts = standard_url.split('/')
            for part in parts:
                if part.startswith('umc.cmc.'):
                    return part
    
    elif service == 'youtube':
        # YouTube video IDs
        if 'youtube.com' in standard_url:
            if 'v=' in standard_url:
                return standard_url.split('v=')[-1].split('&')[0]
    
    # Fallback: return the element_id if available
    return offer.get('element_id')


def save_content_to_db(content: Dict, streaming_offers: List[Dict]):
    """
    Save content and its streaming availability to the database.
    
    Args:
        content: Content metadata
        streaming_offers: List of streaming availability offers
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Insert or update content
        cursor.execute('''
            INSERT OR REPLACE INTO content 
            (justwatch_id, title, content_type, year, imdb_id, tmdb_id, 
             poster_url, description, genres, rating_imdb, rating_tmdb, 
             runtime_minutes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(content.get('id')),
            content.get('title'),
            content.get('object_type'),
            content.get('original_release_year'),
            content.get('imdb_id'),
            str(content.get('tmdb_id')) if content.get('tmdb_id') else None,
            content.get('poster'),
            content.get('short_description'),
            json.dumps(content.get('genres', [])),
            content.get('imdb_score'),
            content.get('tmdb_score'),
            content.get('runtime_minutes'),  # Duration in minutes
            datetime.now(timezone.utc).isoformat()
        ))
        
        content_id = cursor.lastrowid or cursor.execute(
            'SELECT id FROM content WHERE justwatch_id = ?', 
            (str(content.get('id')),)
        ).fetchone()[0]
        
        # Insert streaming availability
        for offer in streaming_offers:
            # Handle both old API format (provider_id) and new GraphQL format (package.packageId)
            provider_id = offer.get('provider_id')
            if not provider_id:
                package = offer.get('package', {})
                provider_id = package.get('packageId')
                clear_name = package.get('clearName', '').lower()
            else:
                clear_name = ''
            
            # Map provider ID to service name
            service = None
            for svc, pid in PROVIDER_IDS.items():
                if pid == provider_id:
                    service = svc
                    break
            
            # Fallback: try to match by clear name
            if not service and clear_name:
                if 'netflix' in clear_name:
                    service = 'netflix'
                elif 'hulu' in clear_name:
                    service = 'hulu'
                elif 'disney' in clear_name:
                    service = 'disney'
                elif 'max' in clear_name or 'hbo' in clear_name:
                    service = 'max'
                elif 'prime' in clear_name or 'amazon' in clear_name:
                    service = 'prime'
                elif 'apple' in clear_name:
                    service = 'apple'
                elif 'espn' in clear_name:
                    service = 'espn'
                elif 'youtube' in clear_name:
                    service = 'youtube'
            
            if not service or service not in SUBSCRIBED_SERVICES:
                continue
            
            # Extract deep link ID from URL (GraphQL format uses standardWebURL)
            web_url = offer.get('standardWebURL') or offer.get('urls', {}).get('standard_web', '')
            deep_link_id = extract_deep_link_id_from_url(web_url, service)
            
            cursor.execute('''
                INSERT OR REPLACE INTO streaming_availability
                (content_id, service, content_id_for_service, offer_type, 
                 quality, deep_link_url, last_verified)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                content_id,
                service,
                deep_link_id,
                offer.get('monetizationType') or offer.get('monetization_type'),
                offer.get('presentationType') or offer.get('presentation_type'),
                web_url,
                datetime.now(timezone.utc).isoformat()
            ))
        
        conn.commit()
        logger.info(f"Saved content: {content.get('title')}")
        
    except Exception as e:
        logger.error(f"Error saving content: {e}")
        conn.rollback()
    finally:
        conn.close()


def get_popular_content(service: str = None, limit: int = 50) -> List[Dict]:
    """
    Get popular/trending content from JustWatch.
    
    Args:
        service: Filter by service (optional)
        limit: Maximum results
    
    Returns:
        List of popular content
    """
    try:
        providers = [PROVIDER_IDS[service]] if service else list(PROVIDER_IDS.values())
        
        response = requests.get(
            f"{JUSTWATCH_BASE}/titles/en_US/popular",
            params={
                'body': json.dumps({
                    'providers': providers,
                    'page': 1,
                    'page_size': limit,
                    'monetization_types': ['flatrate'],  # Subscription only
                })
            },
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
                'Accept': 'application/json',
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get('items', [])
        else:
            logger.warning(f"Failed to get popular content: {response.status_code}")
            return []
            
    except Exception as e:
        logger.error(f"Error getting popular content: {e}")
        return []


def scrape_popular_for_all_services():
    """Scrape popular content for all subscribed services."""
    logger.info("Starting popular content scrape for all services...")
    
    for service in SUBSCRIBED_SERVICES:
        logger.info(f"Scraping popular content for {service}...")
        
        items = get_popular_content(service, limit=100)
        logger.info(f"  Found {len(items)} items")
        
        for item in items:
            # Get detailed info
            jw_id = item.get('id')
            content_type = item.get('object_type')
            
            if jw_id and content_type:
                details = get_content_details(jw_id, content_type)
                if details:
                    offers = details.get('offers', [])
                    # Filter to subscribed services
                    subscribed_offers = [
                        o for o in offers 
                        if o.get('provider_id') in PROVIDER_IDS.values()
                        and o.get('monetization_type') == 'flatrate'
                    ]
                    save_content_to_db(details, subscribed_offers)
            
            # Rate limiting
            time.sleep(0.5)
        
        # Pause between services
        time.sleep(2)
    
    logger.info("Popular content scrape complete")


def lookup_content(title: str) -> Optional[Dict]:
    """
    Look up content in local database or scrape from JustWatch.
    
    Args:
        title: Content title to search for
    
    Returns:
        Content info with streaming availability
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Search local database first
        cursor.execute('''
            SELECT c.*, GROUP_CONCAT(
                sa.service || ':' || COALESCE(sa.content_id_for_service, '')
            ) as streaming
            FROM content c
            LEFT JOIN streaming_availability sa ON c.id = sa.content_id
            WHERE c.title LIKE ?
            GROUP BY c.id
            LIMIT 1
        ''', (f'%{title}%',))
        
        row = cursor.fetchone()
        
        if row:
            result = dict(row)
            # Parse streaming availability
            streaming = {}
            if result.get('streaming'):
                for item in result['streaming'].split(','):
                    if ':' in item:
                        svc, content_id = item.split(':', 1)
                        streaming[svc] = content_id
            result['streaming_availability'] = streaming
            return result
        
        # Not in database - search JustWatch
        logger.info(f"Content not in database, searching JustWatch: {title}")
        items = search_justwatch(title)
        
        if items:
            # Get details for first match
            item = items[0]
            details = get_content_details(item.get('id'), item.get('object_type'))
            
            if details:
                offers = details.get('offers', [])
                subscribed_offers = [
                    o for o in offers 
                    if o.get('provider_id') in PROVIDER_IDS.values()
                ]
                save_content_to_db(details, subscribed_offers)
                
                # Return the result
                return lookup_content(title)  # Recursive call to get from DB
        
        return None
        
    finally:
        conn.close()


def get_content_for_deep_link(title: str, preferred_service: str = None) -> Optional[Dict]:
    """
    Get content info suitable for deep linking.
    
    Args:
        title: Content title
        preferred_service: Preferred streaming service
    
    Returns:
        Dict with service, content_id for deep linking
    """
    content = lookup_content(title)
    
    if not content:
        return None
    
    streaming = content.get('streaming_availability', {})
    
    if not streaming:
        return None
    
    # If preferred service is available, use it
    if preferred_service and preferred_service in streaming:
        return {
            'title': content.get('title'),
            'service': preferred_service,
            'content_id': streaming[preferred_service],
            'content_type': content.get('content_type'),
        }
    
    # Otherwise, pick first available
    for service, content_id in streaming.items():
        if content_id:
            return {
                'title': content.get('title'),
                'service': service,
                'content_id': content_id,
                'content_type': content.get('content_type'),
            }
    
    return None


if __name__ == '__main__':
    # Initialize database
    init_database()
    
    # Test search
    print("Testing JustWatch search...")
    results = search_justwatch("Slow Horses")
    print(f"Found {len(results)} results")
    
    if results:
        print(f"First result: {results[0].get('title')}")
        
        # Get details
        details = get_content_details(results[0].get('id'), results[0].get('object_type'))
        if details:
            print(f"Title: {details.get('title')}")
            print(f"Offers: {len(details.get('offers', []))}")
            
            for offer in details.get('offers', [])[:5]:
                print(f"  Provider {offer.get('provider_id')}: {offer.get('monetization_type')}")

