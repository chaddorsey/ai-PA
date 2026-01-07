"""
Unified Watch History Polling Service

This service polls all streaming services for watch history and updates
the content database. It uses:
- API polling for: Max, Hulu, Disney+, Apple TV+
- Browser scraping for: Netflix, Prime Video

Designed to be called by a Letta sleeptime agent for regular updates.
"""

import os
import json
import sqlite3
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod

import requests
from flask import Flask, jsonify, request

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DB_PATH = os.environ.get('DB_PATH', '/app/data/content_database.db')
CREDENTIALS_PATH = os.environ.get('CREDENTIALS_PATH', '/app/credentials')

app = Flask(__name__)


@dataclass
class WatchHistoryEntry:
    """Represents a single watch history entry."""
    service: str
    title: str
    content_type: str  # 'movie', 'show', 'episode'
    content_id: str  # Service-specific ID
    episode_title: Optional[str] = None
    season_number: Optional[int] = None
    episode_number: Optional[int] = None
    watch_date: Optional[str] = None
    progress_percent: Optional[int] = None
    deep_link_id: Optional[str] = None


class ServicePoller(ABC):
    """Abstract base class for service-specific pollers."""
    
    @abstractmethod
    def get_continue_watching(self) -> List[WatchHistoryEntry]:
        """Get the Continue Watching list."""
        pass
    
    @abstractmethod
    def get_watch_history(self) -> List[WatchHistoryEntry]:
        """Get full watch history."""
        pass
    
    @abstractmethod
    def is_authenticated(self) -> bool:
        """Check if credentials are valid."""
        pass


class MaxPoller(ServicePoller):
    """Poller for Max (HBO) using their internal API."""
    
    API_BASE = "https://default.beam-amer.prd.api.hbomax.com"
    
    def __init__(self, credentials: Dict[str, str]):
        # Convert cookie list to dict
        raw_cookies = credentials.get('cookies', [])
        if isinstance(raw_cookies, list):
            self.cookies = {c['name']: c['value'] for c in raw_cookies if 'name' in c and 'value' in c}
        else:
            self.cookies = raw_cookies
        
        # JWT token can be passed directly or extracted from 'st' cookie
        self.jwt_token = credentials.get('jwt_token', '') or self.cookies.get('st', '')
        
        # Extract device ID from token if available
        self.device_id = ''
        self.iid = ''
        if self.jwt_token:
            try:
                import base64
                parts = self.jwt_token.split('.')
                if len(parts) >= 2:
                    # Pad the base64 string
                    payload_b64 = parts[1] + '=' * (4 - len(parts[1]) % 4)
                    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                    self.device_id = payload.get('deviceId', '')
                    self.iid = payload.get('iid', '')
            except Exception:
                pass
        
        self.session = requests.Session()
    
    def _get_headers(self) -> Dict[str, str]:
        # Minimal headers to avoid 431 error
        headers = {
            'accept': 'application/json',
            'origin': 'https://play.max.com',
            'referer': 'https://play.max.com/',
            'user-agent': 'Mozilla/5.0',
            'x-disco-client': 'WEB:10.15.7:hbomax:6.10.3',
        }
        
        # Auth via Bearer token
        if self.jwt_token:
            headers['authorization'] = f'Bearer {self.jwt_token}'
        
        return headers
    
    def is_authenticated(self) -> bool:
        # Check if we have the required JWT token
        if not self.jwt_token:
            logger.warning("Max: No JWT token found")
            return False
        
        try:
            response = self.session.get(
                f"{self.API_BASE}/users/me/profiles",
                headers=self._get_headers(),
                cookies=self.cookies,
                timeout=10
            )
            logger.info(f"Max auth check: status={response.status_code}")
            if response.status_code != 200:
                logger.warning(f"Max auth failed: {response.text[:200]}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Max auth check error: {e}")
            return False
    
    def get_continue_watching(self) -> List[WatchHistoryEntry]:
        """Fetch Continue Watching from Max API."""
        entries = []
        try:
            # Add the JWT token to cookies if not already there
            cookies = dict(self.cookies)
            if self.jwt_token and 'st' not in cookies:
                cookies['st'] = self.jwt_token
            
            # Minimal headers (no auth header - use cookie instead)
            headers = {
                'accept': 'application/json',
                'origin': 'https://play.max.com',
                'referer': 'https://play.max.com/',
                'user-agent': 'Mozilla/5.0',
                'x-disco-client': 'WEB:10.15.7:hbomax:6.10.3',
            }
            
            # Use the known collection endpoint
            collection_id = "170978312149821667450710537300541032725"
            response = self.session.get(
                f"{self.API_BASE}/cms/collections/{collection_id}",
                params={'include': 'default'},
                headers=headers,
                cookies=cookies,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            # Parse the response - build a map of all items first
            content_map = {}
            for item in data.get('included', []):
                content_map[item.get('id')] = item
            
            # Find continue watching items
            for item in data.get('included', []):
                item_type = item.get('type', '')
                attrs = item.get('attributes', {})
                
                # Skip non-content items
                if item_type not in ['video', 'show', 'series', 'movie']:
                    continue
                
                # Get title from attributes
                title = attrs.get('name') or attrs.get('title') or 'Unknown'
                content_id = item.get('id')
                
                # Try to get episode info
                episode_title = None
                season_num = None
                episode_num = None
                
                if item_type == 'video':
                    episode_title = attrs.get('name')
                    season_num = attrs.get('seasonNumber')
                    episode_num = attrs.get('episodeNumber')
                    
                    # Try to get series name from relationships
                    rels = item.get('relationships', {})
                    if 'show' in rels:
                        show_data = rels['show'].get('data', {})
                        show_id = show_data.get('id')
                        if show_id and show_id in content_map:
                            show_item = content_map[show_id]
                            title = show_item.get('attributes', {}).get('name', title)
                
                entry = WatchHistoryEntry(
                    service='max',
                    title=title,
                    content_type='show' if item_type in ['show', 'series', 'video'] else 'movie',
                    content_id=content_id,
                    episode_title=episode_title,
                    season_number=season_num,
                    episode_number=episode_num,
                    deep_link_id=content_id
                )
                entries.append(entry)
            
            logger.info(f"Max: Found {len(entries)} continue watching items")
            
        except Exception as e:
            logger.error(f"Max continue watching error: {e}")
        
        return entries
    
    def get_watch_history(self) -> List[WatchHistoryEntry]:
        """Max doesn't have a full history API, return continue watching."""
        return self.get_continue_watching()


class HuluPoller(ServicePoller):
    """Poller for Hulu using their internal API."""
    
    API_BASE = "https://discover.hulu.com/content/v5"
    
    def __init__(self, credentials: Dict[str, str]):
        # Convert cookie list to dict
        raw_cookies = credentials.get('cookies', [])
        if isinstance(raw_cookies, list):
            self.cookies = {c['name']: c['value'] for c in raw_cookies if 'name' in c and 'value' in c}
        else:
            self.cookies = raw_cookies
        self.session = requests.Session()
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'accept': 'application/json',
            'origin': 'https://www.hulu.com',
            'referer': 'https://www.hulu.com/',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        }
    
    def is_authenticated(self) -> bool:
        try:
            response = self.session.get(
                f"{self.API_BASE}/hubs/home",
                params={'schema': 1},
                headers=self._get_headers(),
                cookies=self.cookies,
                timeout=10
            )
            return response.status_code == 200
        except Exception:
            return False
    
    def get_continue_watching(self) -> List[WatchHistoryEntry]:
        """Fetch Continue Watching from Hulu API."""
        entries = []
        try:
            # Get home hub to find Continue Watching component
            response = self.session.get(
                f"{self.API_BASE}/hubs/home",
                params={'schema': 1},
                headers=self._get_headers(),
                cookies=self.cookies,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            # Find Continue Watching component
            for component in data.get('components', []):
                if component.get('name') == 'Continue Watching':
                    cw_url = component.get('href')
                    if cw_url:
                        cw_response = self.session.get(
                            cw_url,
                            params={'schema': 1},
                            headers=self._get_headers(),
                            cookies=self.cookies,
                            timeout=30
                        )
                        cw_response.raise_for_status()
                        cw_data = cw_response.json()
                        
                        for item in cw_data.get('items', []):
                            metrics = item.get('metrics_info', {})
                            title = metrics.get('target_name', 'Unknown')
                            content_id = item.get('id', '')
                            episode_text = item.get('entity_metadata', {}).get('episode_text', '')
                            
                            entry = WatchHistoryEntry(
                                service='hulu',
                                title=title,
                                content_type='show',
                                content_id=content_id,
                                episode_title=episode_text,
                                deep_link_id=content_id
                            )
                            entries.append(entry)
                    break
            
            logger.info(f"Hulu: Found {len(entries)} continue watching items")
            
        except Exception as e:
            logger.error(f"Hulu continue watching error: {e}")
        
        return entries
    
    def get_watch_history(self) -> List[WatchHistoryEntry]:
        return self.get_continue_watching()


class DisneyPoller(ServicePoller):
    """Poller for Disney+ using their internal API."""
    
    API_BASE = "https://disney.api.edge.bamgrid.com"
    
    def __init__(self, credentials: Dict[str, str]):
        # Support both direct token and cookie-based auth
        self.bearer_token = credentials.get('bearer_token', '')
        self.profile_id = credentials.get('profile_id', '')
        
        # Extract from cookies if not provided directly
        raw_cookies = credentials.get('cookies', [])
        if isinstance(raw_cookies, list):
            self.cookies = {c['name']: c['value'] for c in raw_cookies if 'name' in c and 'value' in c}
        else:
            self.cookies = raw_cookies
        
        # Try to extract bearer token from cookies
        if not self.bearer_token:
            # Disney+ stores the access token in a cookie or localStorage
            # Check for common token cookie names
            for cookie_name in ['access_token', 'bamAccessToken', 'token']:
                if cookie_name in self.cookies:
                    self.bearer_token = self.cookies[cookie_name]
                    break
        
        self.session = requests.Session()
        logger.info(f"Disney+ poller initialized: token={'yes' if self.bearer_token else 'no'}, profile={'yes' if self.profile_id else 'no'}, cookies={len(self.cookies)}")
    
    def _get_headers(self) -> Dict[str, str]:
        headers = {
            'accept': 'application/json',
            'origin': 'https://www.disneyplus.com',
            'referer': 'https://www.disneyplus.com/',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'x-bamsdk-client-id': 'disney-svod-3d9324fc',
            'x-bamsdk-platform': 'javascript/macosx/chrome',
        }
        if self.bearer_token:
            headers['authorization'] = f'Bearer {self.bearer_token}'
        if self.profile_id:
            headers['x-request-yp-id'] = self.profile_id
        return headers
    
    def is_authenticated(self) -> bool:
        # Accept if we have either token or cookies
        return bool(self.bearer_token) or bool(self.cookies)
    
    def get_continue_watching(self) -> List[WatchHistoryEntry]:
        """Fetch Continue Watching from Disney+ API."""
        entries = []
        try:
            # Disney+ requires a bearer token for API access
            # If we only have cookies, we need to use browser-based scraping
            if not self.bearer_token:
                logger.warning("Disney+ requires bearer token for API access. Use browser scraping instead.")
                return entries
            
            set_id = "76aed686-1837-49bd-b4f5-5d2a27c0c8d4"
            url = f"{self.API_BASE}/explore/v1.12/set/{set_id}"
            params = {
                'setStyle': 'continue_watching',
                'limit': 15,
                'offset': 0
            }
            
            response = self.session.get(
                url,
                params=params,
                headers=self._get_headers(),
                cookies=self.cookies,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            for s in data.get('data', {}).get('sets', []):
                if s.get('setStyle') == 'continue_watching':
                    for item in s.get('items', []):
                        title = 'Unknown'
                        for action in item.get('actions', []):
                            if action.get('visuals', {}).get('title'):
                                title = action['visuals']['title']
                                break
                        
                        entry = WatchHistoryEntry(
                            service='disney',
                            title=title,
                            content_type='show',
                            content_id=item.get('contentId', ''),
                            deep_link_id=item.get('deeplinkId', item.get('contentId', ''))
                        )
                        entries.append(entry)
            
            logger.info(f"Disney+: Found {len(entries)} continue watching items")
            
        except Exception as e:
            logger.error(f"Disney+ continue watching error: {e}")
        
        return entries
    
    def get_watch_history(self) -> List[WatchHistoryEntry]:
        return self.get_continue_watching()


class AppleTVPoller(ServicePoller):
    """Poller for Apple TV+ using their internal API."""
    
    API_BASE = "https://tv.apple.com/api/uts/v3"
    
    def __init__(self, credentials: Dict[str, str]):
        self.bearer_token = credentials.get('bearer_token', '')
        self.media_user_token = credentials.get('media_user_token', '')
        
        # Convert cookie list to dict
        raw_cookies = credentials.get('cookies', [])
        if isinstance(raw_cookies, list):
            self.cookies = {c['name']: c['value'] for c in raw_cookies if 'name' in c and 'value' in c}
        else:
            self.cookies = raw_cookies
        
        # Extract tokens from cookies if not provided directly
        if not self.media_user_token and 'media-user-token' in self.cookies:
            self.media_user_token = self.cookies['media-user-token']
        
        # Apple TV uses the 'myacinfo' cookie for auth
        self.myacinfo = self.cookies.get('myacinfo', '')
        
        self.session = requests.Session()
        logger.info(f"Apple TV+ poller initialized: bearer={'yes' if self.bearer_token else 'no'}, media_token={'yes' if self.media_user_token else 'no'}, cookies={len(self.cookies)}")
    
    def _get_headers(self) -> Dict[str, str]:
        headers = {
            'accept': '*/*',
            'origin': 'https://tv.apple.com',
            'referer': 'https://tv.apple.com/',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        }
        if self.bearer_token:
            headers['authorization'] = f'Bearer {self.bearer_token}'
        if self.media_user_token:
            headers['media-user-token'] = self.media_user_token
        return headers
    
    def is_authenticated(self) -> bool:
        # Accept if we have tokens or the myacinfo cookie
        return bool(self.media_user_token) or bool(self.myacinfo) or bool(self.cookies)
    
    def get_continue_watching(self) -> List[WatchHistoryEntry]:
        """Fetch Up Next from Apple TV+ API."""
        entries = []
        try:
            url = f"{self.API_BASE}/shelves/uts.col.ChannelUpNext.tvs.sbd.4000"
            params = {
                'caller': 'web',
                'ctx_brand': 'tvs.sbd.4000',
                'locale': 'en-US',
                'pfm': 'web',
                'sf': '143441',
                'v': '92'
            }
            
            response = self.session.get(
                url,
                params=params,
                headers=self._get_headers(),
                cookies=self.cookies,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            # Response structure: data.shelves[] or data.shelf
            shelves = data.get('data', {}).get('shelves', [])
            if not shelves:
                # Try single shelf structure
                shelf = data.get('data', {}).get('shelf', {})
                if shelf:
                    shelves = [shelf]
            
            for shelf in shelves:
                for item in shelf.get('items', []):
                    title = item.get('title', 'Unknown')
                    show_title = item.get('showTitle', '')
                    content_id = item.get('id', '')
                    item_type = item.get('type', 'unknown').lower()
                    
                    season = item.get('seasonNumber')
                    episode = item.get('episodeNumber')
                    
                    entry = WatchHistoryEntry(
                        service='apple',
                        title=show_title if show_title else title,
                        content_type='episode' if item_type == 'episode' else item_type,
                        content_id=content_id,
                        episode_title=title if show_title else None,
                        season_number=season,
                        episode_number=episode,
                        deep_link_id=content_id
                    )
                    entries.append(entry)
            
            logger.info(f"Apple TV+: Found {len(entries)} up next items")
            
        except Exception as e:
            logger.error(f"Apple TV+ continue watching error: {e}")
        
        return entries
    
    def get_watch_history(self) -> List[WatchHistoryEntry]:
        return self.get_continue_watching()


class NetflixPoller(ServicePoller):
    """
    Poller for Netflix using the Viewing Activity API.
    
    Netflix's pathEvaluator API can fetch viewing activity when given the right paths.
    """
    
    API_BASE = "https://www.netflix.com/nq/website/memberapi/release/pathEvaluator"
    
    def __init__(self, credentials: Dict[str, str]):
        # Convert cookie list to dict
        raw_cookies = credentials.get('cookies', [])
        if isinstance(raw_cookies, list):
            self.cookies = {c['name']: c['value'] for c in raw_cookies if 'name' in c and 'value' in c}
        else:
            self.cookies = raw_cookies
        
        self.profile_guid = credentials.get('profile_guid', credentials.get('netflix_id', ''))
        self.auth_url = credentials.get('auth_url', '')
        self.session = requests.Session()
        
        logger.info(f"Netflix poller initialized: cookies={len(self.cookies)}, profile_guid={'yes' if self.profile_guid else 'no'}")
    
    def _get_headers(self) -> Dict[str, str]:
        headers = {
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://www.netflix.com',
            'referer': 'https://www.netflix.com/browse',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        }
        if self.profile_guid:
            headers['x-netflix.request.client.user.guid'] = self.profile_guid
        return headers
    
    def is_authenticated(self) -> bool:
        # Netflix uses NetflixId cookie for auth
        has_auth = bool(self.cookies.get('NetflixId')) or bool(self.cookies)
        logger.info(f"Netflix auth check: NetflixId={'yes' if self.cookies.get('NetflixId') else 'no'}, total_cookies={len(self.cookies)}")
        return has_auth
    
    def get_continue_watching(self) -> List[WatchHistoryEntry]:
        """Fetch Continue Watching from Netflix API."""
        entries = []
        try:
            # Query for the continue watching row
            params = {
                'webp': 'true',
                'drmSystem': 'widevine',
                'falcor_server': '0.1.0',
                'withSize': 'true',
                'materialize': 'true'
            }
            
            # Path for continue watching - typically in the "continueWatching" lolomo
            data = {
                'path': json.dumps(["continueWatching", {"from": 0, "to": 20}, 
                    ["availability", "summary", "title", "episodeCount"]]),
                'authURL': self.auth_url
            }
            
            response = self.session.post(
                self.API_BASE,
                params=params,
                headers=self._get_headers(),
                cookies=self.cookies,
                data=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                # Parse Falcor JSON Graph response
                videos = result.get('jsonGraph', {}).get('videos', {})
                for video_id, video_data in videos.items():
                    if isinstance(video_data, dict):
                        summary = video_data.get('summary', {}).get('value', {})
                        title = summary.get('title', 'Unknown')
                        
                        entry = WatchHistoryEntry(
                            service='netflix',
                            title=title,
                            content_type=summary.get('type', 'show'),
                            content_id=video_id,
                            deep_link_id=video_id
                        )
                        entries.append(entry)
            
            logger.info(f"Netflix: Found {len(entries)} continue watching items")
            
        except Exception as e:
            logger.error(f"Netflix continue watching error: {e}")
        
        return entries
    
    def get_watch_history(self) -> List[WatchHistoryEntry]:
        """
        For full history, we'd need to scrape the viewing activity page.
        This requires Playwright browser automation.
        """
        return self.get_continue_watching()


class PrimeVideoPoller(ServicePoller):
    """
    Poller for Prime Video using the enrichItemMetadata API.
    
    Note: Prime Video doesn't have a direct "get Continue Watching list" API.
    We need to either:
    1. Scrape the storefront for ASIN IDs, then enrich them
    2. Use browser automation to get the full list
    """
    
    API_BASE = "https://www.amazon.com/gp/video/api"
    
    def __init__(self, credentials: Dict[str, str]):
        # Convert cookie list to dict
        raw_cookies = credentials.get('cookies', [])
        if isinstance(raw_cookies, list):
            self.cookies = {c['name']: c['value'] for c in raw_cookies if 'name' in c and 'value' in c}
        else:
            self.cookies = raw_cookies
        self.session = requests.Session()
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://www.amazon.com',
            'referer': 'https://www.amazon.com/gp/video/storefront',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
            'x-requested-with': 'XMLHttpRequest',
        }
    
    def is_authenticated(self) -> bool:
        return bool(self.cookies.get('at-main'))
    
    def enrich_titles(self, asin_list: List[str]) -> List[WatchHistoryEntry]:
        """Enrich a list of ASINs with metadata."""
        entries = []
        try:
            data = {
                'metadataToEnrich': json.dumps({
                    'placement': 'HOVER',
                    'playback': True,
                    'trailer': True,
                    'watchlist': True
                }),
                'titleIDsToEnrich': json.dumps(asin_list),
                'currentUrl': 'https://www.amazon.com/gp/video/storefront'
            }
            
            response = self.session.post(
                f"{self.API_BASE}/enrichItemMetadata",
                headers=self._get_headers(),
                cookies=self.cookies,
                data=data,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            enrichments = result.get('enrichments', {})
            for asin, enrichment in enrichments.items():
                playback = enrichment.get('playbackActions', [])
                if playback:
                    action = playback[0]
                    label = action.get('label', '')
                    
                    # Parse "Resume S2 E1" style labels
                    entry = WatchHistoryEntry(
                        service='prime',
                        title=label,  # Will be enriched later
                        content_type='show' if 'S' in label and 'E' in label else 'movie',
                        content_id=asin,
                        deep_link_id=asin
                    )
                    entries.append(entry)
            
            logger.info(f"Prime: Enriched {len(entries)} items")
            
        except Exception as e:
            logger.error(f"Prime enrichment error: {e}")
        
        return entries
    
    def get_continue_watching(self) -> List[WatchHistoryEntry]:
        """
        Prime Video requires scraping the storefront to get ASIN list first.
        This is a placeholder - full implementation requires Playwright.
        """
        # For now, return empty - will be filled by browser scraping
        logger.warning("Prime Video Continue Watching requires browser scraping")
        return []
    
    def get_watch_history(self) -> List[WatchHistoryEntry]:
        return self.get_continue_watching()


def save_entries_to_db(entries: List[WatchHistoryEntry], username: str):
    """Save watch history entries to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get or create user
    cursor.execute('INSERT OR IGNORE INTO users (username) VALUES (?)', (username,))
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user_id = cursor.fetchone()[0]
    
    saved_count = 0
    for entry in entries:
        try:
            # Check if content exists in our database
            cursor.execute(
                'SELECT id FROM content WHERE title LIKE ? LIMIT 1',
                (f'%{entry.title}%',)
            )
            content_row = cursor.fetchone()
            content_id = content_row[0] if content_row else None
            
            # Insert into watch history (avoiding duplicates by checking recent entries)
            cursor.execute('''
                INSERT INTO user_watch_history 
                (user_id, content_id, service, title, episode_title, 
                 season_number, episode_number, watched_at, service_content_id, source)
                SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM user_watch_history 
                    WHERE user_id = ? AND service = ? AND service_content_id = ?
                    AND watched_at > datetime('now', '-1 hour')
                )
            ''', (
                user_id, content_id, entry.service, entry.title,
                entry.episode_title, entry.season_number, entry.episode_number,
                entry.watch_date or datetime.now(timezone.utc).isoformat(),
                entry.content_id,
                'api_poll',
                user_id, entry.service, entry.content_id
            ))
            
            if cursor.rowcount > 0:
                saved_count += 1
                
        except Exception as e:
            logger.error(f"Error saving entry {entry.title}: {e}")
    
    conn.commit()
    conn.close()
    
    logger.info(f"Saved {saved_count} new entries for user {username}")
    return saved_count


def load_credentials(service: str) -> Dict[str, Any]:
    """Load credentials for a service from the credentials directory."""
    cred_file = os.path.join(CREDENTIALS_PATH, f'{service}_credentials.json')
    if os.path.exists(cred_file):
        with open(cred_file, 'r') as f:
            return json.load(f)
    return {}


def poll_service_internal(service: str, username: str) -> Dict[str, Any]:
    """
    Internal function to poll a service (not a Flask route).
    Returns a dict with items_found, items_saved, method, entries.
    """
    api_pollers = {
        'max': MaxPoller,
        'hulu': HuluPoller,
        'disney': DisneyPoller,
        'apple': AppleTVPoller,
        'netflix': NetflixPoller,
        'prime': PrimeVideoPoller,
    }
    
    browser_services = {'netflix', 'disney', 'apple', 'prime'}
    
    credentials = load_credentials(service)
    entries = []
    method_used = 'api'
    
    # Try API polling first
    if credentials:
        poller = api_pollers[service](credentials)
        if poller.is_authenticated():
            entries = poller.get_continue_watching()
    
    # Fall back to browser scraping
    if not entries and service in browser_services:
        browser_state_file = os.path.join(CREDENTIALS_PATH, 'browser_states', f'{service}_state.json')
        if os.path.exists(browser_state_file):
            logger.info(f"Using browser scraping for {service}")
            try:
                from browser_poller import scrape_service_sync
                entries = scrape_service_sync(service)
                method_used = 'browser'
            except Exception as e:
                logger.error(f"Browser scraping failed for {service}: {e}")
    
    saved = save_entries_to_db(entries, username) if entries else 0
    
    return {
        'service': service,
        'method': method_used,
        'items_found': len(entries),
        'items_saved': saved,
        'entries': entries
    }


def poll_all_services(username: str) -> Dict[str, Any]:
    """Poll all services and update the database."""
    results = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'username': username,
        'services': {}
    }
    
    pollers = {
        'max': MaxPoller,
        'hulu': HuluPoller,
        'disney': DisneyPoller,
        'apple': AppleTVPoller,
        'netflix': NetflixPoller,
        'prime': PrimeVideoPoller,
    }
    
    total_entries = 0
    
    for service_name, poller_class in pollers.items():
        try:
            credentials = load_credentials(service_name)
            if not credentials:
                results['services'][service_name] = {
                    'status': 'skipped',
                    'reason': 'No credentials configured'
                }
                continue
            
            poller = poller_class(credentials)
            
            if not poller.is_authenticated():
                results['services'][service_name] = {
                    'status': 'error',
                    'reason': 'Authentication failed - credentials may be expired'
                }
                continue
            
            entries = poller.get_continue_watching()
            saved = save_entries_to_db(entries, username)
            
            results['services'][service_name] = {
                'status': 'ok',
                'items_found': len(entries),
                'items_saved': saved
            }
            total_entries += len(entries)
            
        except Exception as e:
            logger.error(f"Error polling {service_name}: {e}")
            results['services'][service_name] = {
                'status': 'error',
                'reason': str(e)
            }
    
    results['total_items'] = total_entries
    return results


# Flask routes
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'watch-history-poller'})


@app.route('/poll', methods=['POST'])
def poll():
    """Trigger polling for all services."""
    data = request.get_json() or {}
    username = data.get('username', 'chad')
    
    results = poll_all_services(username)
    return jsonify(results)


@app.route('/poll/<service>', methods=['POST'])
def poll_service(service: str):
    """Poll a specific service."""
    data = request.get_json() or {}
    username = data.get('username', 'chad')
    use_browser = data.get('use_browser', False)  # Force browser scraping
    
    # Services that work with API polling
    api_pollers = {
        'max': MaxPoller,
        'hulu': HuluPoller,
        'disney': DisneyPoller,
        'apple': AppleTVPoller,
        'netflix': NetflixPoller,
        'prime': PrimeVideoPoller,
    }
    
    # Services that need browser scraping
    browser_services = {'netflix', 'disney', 'apple', 'prime'}
    
    if service not in api_pollers:
        return jsonify({'error': f'Unknown service: {service}'}), 400
    
    try:
        credentials = load_credentials(service)
        if not credentials:
            return jsonify({'error': 'No credentials configured'}), 400
        
        entries = []
        method_used = 'api'
        
        # Try API polling first (unless browser is forced)
        if not use_browser:
            poller = api_pollers[service](credentials)
            
            if poller.is_authenticated():
                entries = poller.get_continue_watching()
        
        # Fall back to browser scraping if API returns nothing and browser state exists
        if not entries and service in browser_services:
            browser_state_file = os.path.join(CREDENTIALS_PATH, 'browser_states', f'{service}_state.json')
            
            if os.path.exists(browser_state_file):
                logger.info(f"Using browser scraping for {service}")
                try:
                    from browser_poller import scrape_service_sync
                    browser_entries = scrape_service_sync(service)
                    entries = browser_entries
                    method_used = 'browser'
                except Exception as e:
                    logger.error(f"Browser scraping failed for {service}: {e}")
        
        saved = save_entries_to_db(entries, username) if entries else 0
        
        return jsonify({
            'service': service,
            'method': method_used,
            'items_found': len(entries),
            'items_saved': saved,
            'entries': [asdict(e) for e in entries]
        })
        
    except Exception as e:
        logger.error(f"Error polling {service}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/credentials/<service>', methods=['POST'])
def update_credentials(service: str):
    """Update credentials for a service."""
    credentials = request.get_json()
    
    if not credentials:
        return jsonify({'error': 'No credentials provided'}), 400
    
    os.makedirs(CREDENTIALS_PATH, exist_ok=True)
    cred_file = os.path.join(CREDENTIALS_PATH, f'{service}_credentials.json')
    
    with open(cred_file, 'w') as f:
        json.dump(credentials, f, indent=2)
    
    return jsonify({'status': 'ok', 'service': service})


@app.route('/credentials/<service>', methods=['GET'])
def get_credentials_status(service: str):
    """Check if credentials are configured for a service."""
    credentials = load_credentials(service)
    return jsonify({
        'service': service,
        'configured': bool(credentials),
        'keys': list(credentials.keys()) if credentials else []
    })


@app.route('/credentials/status', methods=['GET'])
def get_all_credentials_status():
    """Check credentials status for all services."""
    services = ['max', 'hulu', 'disney', 'apple', 'netflix', 'prime']
    result = {}
    
    for service in services:
        credentials = load_credentials(service)
        result[service] = {
            'configured': bool(credentials),
            'keys': list(credentials.keys()) if credentials else []
        }
    
    return jsonify({'services': result})


# ============================================================
# Session Keeper Endpoints
# ============================================================

# Import session keeper (lazy load to avoid import errors if Playwright not ready)
_session_keeper = None
_scheduler = None


def get_keeper():
    """Lazy load the session keeper."""
    global _session_keeper
    if _session_keeper is None:
        try:
            from session_keeper import SessionKeeper
            _session_keeper = SessionKeeper(CREDENTIALS_PATH)
        except Exception as e:
            logger.error(f"Could not initialize SessionKeeper: {e}")
            raise
    return _session_keeper


def get_scheduler():
    """Lazy load the scheduler."""
    global _scheduler
    if _scheduler is None:
        try:
            from session_keeper import SessionScheduler
            _scheduler = SessionScheduler(get_keeper(), check_interval_minutes=30)
        except Exception as e:
            logger.error(f"Could not initialize SessionScheduler: {e}")
            raise
    return _scheduler


@app.route('/sessions/status', methods=['GET'])
def session_status():
    """Get status of all streaming service sessions."""
    try:
        keeper = get_keeper()
        return jsonify({
            'status': 'ok',
            'sessions': keeper.get_status(),
            'needs_login': keeper.get_services_needing_login()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/sessions/check/<service>', methods=['POST'])
def check_session(service: str):
    """Check if a specific service session is valid."""
    import asyncio
    try:
        keeper = get_keeper()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(keeper.check_session(service))
        loop.close()
        
        return jsonify({
            'status': 'ok',
            'service': service,
            'session': result.to_dict()
        })
    except Exception as e:
        logger.error(f"Error checking session for {service}: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/sessions/check-all', methods=['POST'])
def check_all_sessions():
    """Check all service sessions."""
    import asyncio
    try:
        keeper = get_keeper()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(keeper.check_all_sessions())
        loop.close()
        
        return jsonify({
            'status': 'ok',
            'sessions': {k: v.to_dict() for k, v in results.items()},
            'needs_login': keeper.get_services_needing_login()
        })
    except Exception as e:
        logger.error(f"Error checking all sessions: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/sessions/refresh/<service>', methods=['POST'])
def refresh_session(service: str):
    """Refresh a specific service session."""
    import asyncio
    try:
        keeper = get_keeper()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(keeper.refresh_session(service))
        loop.close()
        
        return jsonify({
            'status': 'ok',
            'service': service,
            'session': result.to_dict()
        })
    except Exception as e:
        logger.error(f"Error refreshing session for {service}: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/sessions/refresh-due', methods=['POST'])
def refresh_due_sessions():
    """Refresh all sessions that are due for refresh."""
    import asyncio
    try:
        keeper = get_keeper()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(keeper.refresh_due_sessions())
        loop.close()
        
        return jsonify({
            'status': 'ok',
            'refreshed': {k: v.to_dict() for k, v in results.items()} if results else {},
            'needs_login': keeper.get_services_needing_login()
        })
    except Exception as e:
        logger.error(f"Error refreshing due sessions: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/sessions/import-cookies/<service>', methods=['POST'])
def import_cookies(service: str):
    """Import cookies from browser export into the session keeper."""
    import asyncio
    data = request.get_json()
    
    if not data or 'cookies' not in data:
        return jsonify({'error': 'No cookies provided'}), 400
    
    cookies = data['cookies']
    
    try:
        keeper = get_keeper()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(keeper.import_cookies_to_browser(service, cookies))
        loop.close()
        
        if success:
            return jsonify({
                'status': 'ok',
                'service': service,
                'message': 'Cookies imported and validated'
            })
        else:
            return jsonify({
                'status': 'error',
                'service': service,
                'message': 'Cookies imported but session not valid'
            }), 400
            
    except Exception as e:
        logger.error(f"Error importing cookies for {service}: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/sessions/scheduler/start', methods=['POST'])
def start_scheduler():
    """Start the background session maintenance scheduler."""
    try:
        import asyncio
        scheduler = get_scheduler()
        
        # Start in a background thread
        import threading
        def run_scheduler():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            scheduler.start()
            loop.run_forever()
        
        thread = threading.Thread(target=run_scheduler, daemon=True)
        thread.start()
        
        return jsonify({
            'status': 'ok',
            'message': 'Scheduler started (30 min interval)'
        })
    except Exception as e:
        logger.error(f"Error starting scheduler: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/sessions/scheduler/stop', methods=['POST'])
def stop_scheduler():
    """Stop the background session maintenance scheduler."""
    try:
        scheduler = get_scheduler()
        scheduler.stop()
        return jsonify({
            'status': 'ok',
            'message': 'Scheduler stopped'
        })
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ==================== WATCHLIST ENDPOINTS ====================

@app.route('/watchlist/<service>', methods=['POST'])
def get_watchlist(service):
    """Get watchlist from a specific service."""
    try:
        from browser_poller import scrape_watchlist_sync, WatchlistEntry
        from dataclasses import asdict
        
        logger.info(f"Scraping watchlist from {service}")
        entries = scrape_watchlist_sync(service)
        
        # Get username from request for saving
        data = request.get_json() or {}
        username = data.get('username', 'default')
        
        # Save to database
        saved = save_watchlist_to_db(entries, username)
        
        return jsonify({
            'service': service,
            'entries': [asdict(e) for e in entries],
            'count': len(entries),
            'saved': saved
        })
    except Exception as e:
        logger.error(f"Error getting watchlist from {service}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/watchlist/all', methods=['POST'])
def get_all_watchlists():
    """Get watchlists from all services."""
    try:
        from browser_poller import scrape_all_watchlists_sync, WatchlistEntry
        from dataclasses import asdict
        
        logger.info("Scraping watchlists from all services")
        results = scrape_all_watchlists_sync()
        
        # Get username from request
        data = request.get_json() or {}
        username = data.get('username', 'default')
        
        response = {'services': {}, 'total': 0}
        for service, entries in results.items():
            saved = save_watchlist_to_db(entries, username)
            response['services'][service] = {
                'count': len(entries),
                'saved': saved,
                'entries': [asdict(e) for e in entries]
            }
            response['total'] += len(entries)
        
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error getting all watchlists: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== RECOMMENDATIONS ENDPOINTS ====================

@app.route('/recommendations/<service>', methods=['POST'])
def get_recommendations(service):
    """Get recommendations from a specific service."""
    try:
        from browser_poller import scrape_recommendations_sync, RecommendationEntry
        from dataclasses import asdict
        
        logger.info(f"Scraping recommendations from {service}")
        entries = scrape_recommendations_sync(service)
        
        # Get username from request
        data = request.get_json() or {}
        username = data.get('username', 'default')
        
        # Save to database
        saved = save_recommendations_to_db(entries, username)
        
        return jsonify({
            'service': service,
            'entries': [asdict(e) for e in entries],
            'count': len(entries),
            'saved': saved
        })
    except Exception as e:
        logger.error(f"Error getting recommendations from {service}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/recommendations/all', methods=['POST'])
def get_all_recommendations():
    """Get recommendations from all services."""
    try:
        from browser_poller import scrape_all_recommendations_sync, RecommendationEntry
        from dataclasses import asdict
        
        logger.info("Scraping recommendations from all services")
        results = scrape_all_recommendations_sync()
        
        # Get username from request
        data = request.get_json() or {}
        username = data.get('username', 'default')
        
        response = {'services': {}, 'total': 0}
        for service, entries in results.items():
            saved = save_recommendations_to_db(entries, username)
            response['services'][service] = {
                'count': len(entries),
                'saved': saved,
                'entries': [asdict(e) for e in entries[:10]]  # Limit response size
            }
            response['total'] += len(entries)
        
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error getting all recommendations: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== FULL SYNC ENDPOINT ====================

@app.route('/sync/all', methods=['POST'])
def sync_all():
    """Full sync: watch history, watchlists, and recommendations from all services."""
    try:
        data = request.get_json() or {}
        username = data.get('username', 'default')
        include_recommendations = data.get('include_recommendations', True)
        
        results = {
            'username': username,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'watch_history': {},
            'watchlists': {},
            'recommendations': {},
            'totals': {'history': 0, 'watchlist': 0, 'recommendations': 0}
        }
        
        # Poll watch history
        logger.info("Syncing watch history from all services...")
        from browser_poller import scrape_service_sync, scrape_all_watchlists_sync
        
        for service in ['max', 'hulu', 'netflix', 'prime', 'apple', 'disney']:
            try:
                poll_result = poll_service_internal(service, username)
                results['watch_history'][service] = {
                    'count': poll_result.get('items_found', 0),
                    'saved': poll_result.get('items_saved', 0),
                    'method': poll_result.get('method', 'unknown')
                }
                results['totals']['history'] += poll_result.get('items_found', 0)
            except Exception as e:
                results['watch_history'][service] = {'error': str(e)}
        
        # Poll watchlists
        logger.info("Syncing watchlists from all services...")
        watchlist_results = scrape_all_watchlists_sync()
        for service, entries in watchlist_results.items():
            saved = save_watchlist_to_db(entries, username)
            results['watchlists'][service] = {'count': len(entries), 'saved': saved}
            results['totals']['watchlist'] += len(entries)
        
        # Poll recommendations (optional, can be slow)
        if include_recommendations:
            logger.info("Syncing recommendations from all services...")
            from browser_poller import scrape_all_recommendations_sync
            rec_results = scrape_all_recommendations_sync()
            for service, entries in rec_results.items():
                saved = save_recommendations_to_db(entries, username)
                results['recommendations'][service] = {'count': len(entries), 'saved': saved}
                results['totals']['recommendations'] += len(entries)
        
        return jsonify(results)
    except Exception as e:
        logger.error(f"Error in full sync: {e}")
        return jsonify({'error': str(e)}), 500


def save_watchlist_to_db(entries, username: str) -> int:
    """Save watchlist entries to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get or create user
    cursor.execute('INSERT OR IGNORE INTO users (username) VALUES (?)', (username,))
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user_id = cursor.fetchone()[0]
    
    saved_count = 0
    for entry in entries:
        try:
            # Use INSERT OR REPLACE to update existing entries
            cursor.execute('''
                INSERT OR REPLACE INTO user_watchlist 
                (user_id, title, service, added_at, status)
                VALUES (?, ?, ?, ?, 'pending')
            ''', (
                user_id, entry.title, entry.service,
                entry.added_at or datetime.now(timezone.utc).isoformat()
            ))
            saved_count += 1
        except Exception as e:
            logger.error(f"Error saving watchlist entry {entry.title}: {e}")
    
    conn.commit()
    conn.close()
    
    logger.info(f"Saved {saved_count} watchlist entries for user {username}")
    return saved_count


def save_recommendations_to_db(entries, username: str) -> int:
    """Save recommendation entries to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get or create user
    cursor.execute('INSERT OR IGNORE INTO users (username) VALUES (?)', (username,))
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user_id = cursor.fetchone()[0]
    
    # Clear old recommendations for this user/service combo (they're refreshed each sync)
    services = set(e.service for e in entries)
    for service in services:
        cursor.execute(
            'DELETE FROM service_recommendations WHERE user_id = ? AND service = ?',
            (user_id, service)
        )
    
    saved_count = 0
    for entry in entries:
        try:
            cursor.execute('''
                INSERT INTO service_recommendations 
                (user_id, title, service, service_content_id, recommendation_type, 
                 category, position, captured_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, entry.title, entry.service, entry.content_id,
                entry.recommendation_type, entry.category, entry.position,
                datetime.now(timezone.utc).isoformat()
            ))
            saved_count += 1
        except Exception as e:
            logger.error(f"Error saving recommendation entry {entry.title}: {e}")
    
    conn.commit()
    conn.close()
    
    logger.info(f"Saved {saved_count} recommendation entries for user {username}")
    return saved_count


# ============================================================================
# SERIES PROGRESS TRACKING
# ============================================================================

def init_series_progress_table():
    """Create the series_progress table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS series_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            service TEXT NOT NULL,
            series_title TEXT NOT NULL,
            series_id TEXT,
            season_number INTEGER NOT NULL,
            episode_number INTEGER NOT NULL,
            episode_title TEXT,
            duration_minutes INTEGER,
            status TEXT NOT NULL,
            progress_percent INTEGER DEFAULT 0,
            deep_link TEXT,
            scraped_at TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, service, series_id, season_number, episode_number)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS series_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            service TEXT NOT NULL,
            series_title TEXT NOT NULL,
            series_id TEXT,
            total_seasons INTEGER,
            total_episodes INTEGER,
            watched_episodes INTEGER DEFAULT 0,
            in_progress_episodes INTEGER DEFAULT 0,
            unwatched_episodes INTEGER DEFAULT 0,
            next_episode_season INTEGER,
            next_episode_number INTEGER,
            next_episode_title TEXT,
            next_episode_progress INTEGER DEFAULT 0,
            scraped_at TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, service, series_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Series progress tables initialized")


def save_series_progress_to_db(series_progress, username: str = 'chad', series_url: str = None) -> int:
    """
    Save series progress data to the database.
    
    Args:
        series_progress: SeriesProgress object from scraper
        username: Username to associate with the data
        series_url: URL of the series page (for reliable tracked_series matching)
        
    Returns:
        Number of episodes saved
    """
    from series_progress_scraper import SeriesProgress, series_progress_to_dict
    
    init_series_progress_table()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get or create user
    cursor.execute('INSERT OR IGNORE INTO users (username) VALUES (?)', (username,))
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user_id = cursor.fetchone()[0]
    
    saved_count = 0
    
    # Save individual episode progress
    for ep in series_progress.episodes:
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO series_progress 
                (user_id, service, series_title, series_id, season_number, episode_number,
                 episode_title, duration_minutes, status, progress_percent, deep_link, 
                 scraped_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                user_id, ep.service, ep.series_title, ep.series_id,
                ep.season_number, ep.episode_number, ep.episode_title,
                ep.duration_minutes, ep.status, ep.progress_percent,
                ep.deep_link, ep.scraped_at
            ))
            saved_count += 1
        except Exception as e:
            logger.error(f"Error saving episode progress: {e}")
    
    # Save series summary
    try:
        next_ep = series_progress.next_episode
        cursor.execute('''
            INSERT OR REPLACE INTO series_summary
            (user_id, service, series_title, series_id, total_seasons, total_episodes,
             watched_episodes, in_progress_episodes, unwatched_episodes,
             next_episode_season, next_episode_number, next_episode_title, 
             next_episode_progress, scraped_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            user_id, series_progress.service, series_progress.series_title,
            series_progress.series_id, series_progress.total_seasons,
            series_progress.total_episodes, series_progress.watched_episodes,
            series_progress.in_progress_episodes, series_progress.unwatched_episodes,
            next_ep.get('season') if next_ep else None,
            next_ep.get('episode') if next_ep else None,
            next_ep.get('title') if next_ep else None,
            next_ep.get('progress', 0) if next_ep else 0,
            series_progress.scraped_at
        ))
    except Exception as e:
        logger.error(f"Error saving series summary: {e}")
    
    # Compute and update duration info in tracked_series
    try:
        # Calculate average episode duration
        durations = [ep.duration_minutes for ep in series_progress.episodes if ep.duration_minutes]
        avg_duration = int(sum(durations) / len(durations)) if durations else None
        
        # Find next episode duration
        next_duration = None
        if next_ep:
            for ep in series_progress.episodes:
                if (ep.season_number == next_ep.get('season') and 
                    ep.episode_number == next_ep.get('episode')):
                    next_duration = ep.duration_minutes
                    break
        
        # Try to update tracked_series - prefer series_url match (most reliable)
        updated = False
        
        if series_url:
            # First try: exact series_url match (most reliable)
            cursor.execute('''
                UPDATE tracked_series 
                SET avg_episode_duration = ?,
                    next_episode_duration = ?,
                    total_episodes_known = ?,
                    watched_episode_count = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND series_url = ?
            ''', (
                avg_duration,
                next_duration,
                series_progress.total_episodes,
                series_progress.watched_episodes,
                user_id,
                series_url
            ))
            if cursor.rowcount > 0:
                logger.info(f"Updated tracked_series (via URL) with avg={avg_duration}min, next={next_duration}min")
                updated = True
        
        if not updated:
            # Fallback: try title matching
            base_title = series_progress.series_title
            for suffix in [' - Netflix', ' - Prime', ' - Max', ' - Hulu', ' - Disney+', ' - Apple TV+']:
                if base_title.endswith(suffix):
                    base_title = base_title[:-len(suffix)]
                    break
            
            cursor.execute('''
                UPDATE tracked_series 
                SET avg_episode_duration = ?,
                    next_episode_duration = ?,
                    total_episodes_known = ?,
                    watched_episode_count = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND (
                    LOWER(title) = LOWER(?) OR
                    LOWER(title) LIKE LOWER(?) OR
                    LOWER(?) LIKE LOWER('%' || title || '%')
                )
            ''', (
                avg_duration,
                next_duration,
                series_progress.total_episodes,
                series_progress.watched_episodes,
                user_id,
                base_title,
                f'{base_title}%',
                series_progress.series_title
            ))
            
            if cursor.rowcount > 0:
                logger.info(f"Updated tracked_series '{base_title}' with avg={avg_duration}min, next={next_duration}min")
            else:
                logger.warning(f"No tracked_series match for '{base_title}' (original: '{series_progress.series_title}', url: {series_url})")
    except Exception as e:
        logger.error(f"Error updating tracked_series duration: {e}")
    
    conn.commit()
    conn.close()
    
    logger.info(f"Saved {saved_count} episode progress entries for '{series_progress.series_title}'")
    return saved_count


def generate_series_progress_memory_block(username: str = 'chad') -> str:
    """
    Generate a formatted memory block summarizing all series progress.
    
    Args:
        username: Username to query for
        
    Returns:
        Formatted string suitable for Letta archival memory
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user_row = cursor.fetchone()
    if not user_row:
        conn.close()
        return "No series progress data found."
    
    user_id = user_row[0]
    
    cursor.execute('''
        SELECT service, series_title, total_seasons, total_episodes, 
               watched_episodes, in_progress_episodes, unwatched_episodes,
               next_episode_season, next_episode_number, next_episode_title,
               next_episode_progress, scraped_at
        FROM series_summary
        WHERE user_id = ?
        ORDER BY service, series_title
    ''', (user_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return "No series progress data found."
    
    # Group by service
    by_service = {}
    for row in rows:
        service = row[0]
        if service not in by_service:
            by_service[service] = []
        by_service[service].append(row)
    
    # Format output
    lines = [f"## Series Progress (updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC)\n"]
    
    for service in sorted(by_service.keys()):
        service_display = {
            'max': 'Max (HBO)',
            'disney': 'Disney+',
            'apple': 'Apple TV+',
            'netflix': 'Netflix',
            'prime': 'Prime Video',
            'hulu': 'Hulu'
        }.get(service, service.title())
        
        lines.append(f"**{service_display}:**")
        
        for row in by_service[service]:
            (_, series_title, total_seasons, total_episodes, watched, in_progress, unwatched,
             next_s, next_e, next_title, next_progress, scraped_at) = row
            
            # Format: "Series S1: 8/12 watched, next: S1E9 'Title' (42%)"
            summary = f"- {series_title}"
            if total_seasons and total_seasons > 1:
                summary += f" ({total_seasons} seasons)"
            summary += f": {watched}/{total_episodes} watched"
            
            if next_s is not None and next_e is not None:
                summary += f", next: S{next_s}E{next_e}"
                if next_title:
                    summary += f" \"{next_title}\""
                if in_progress > 0 and next_progress and next_progress > 0:
                    summary += f" ({next_progress}%)"
            
            lines.append(summary)
        
        lines.append("")
    
    return "\n".join(lines)


def get_unwatched_episodes(
    series_title: str,
    service: str,
    username: str = 'chad'
) -> Dict[str, Any]:
    """
    Get list of unwatched and in-progress episodes for a series.
    
    Args:
        series_title: Title of the series
        service: Streaming service name
        username: Username to query for
        
    Returns:
        Dict with series info and list of unwatched episodes
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user_row = cursor.fetchone()
    if not user_row:
        conn.close()
        return {'error': 'User not found'}
    
    user_id = user_row[0]
    
    # Find the series (fuzzy match on title)
    cursor.execute('''
        SELECT DISTINCT series_title, series_id, service
        FROM series_progress
        WHERE user_id = ? AND service = ? AND series_title LIKE ?
        LIMIT 1
    ''', (user_id, service, f'%{series_title}%'))
    
    series_row = cursor.fetchone()
    if not series_row:
        conn.close()
        return {'error': f'Series "{series_title}" not found on {service}'}
    
    actual_title, series_id, _ = series_row
    
    # Get all unwatched and in-progress episodes
    cursor.execute('''
        SELECT season_number, episode_number, episode_title, duration_minutes,
               status, progress_percent, deep_link
        FROM series_progress
        WHERE user_id = ? AND service = ? AND series_id = ?
              AND status IN ('unwatched', 'in_progress')
        ORDER BY season_number, episode_number
    ''', (user_id, service, series_id))
    
    episodes = []
    for row in cursor.fetchall():
        episodes.append({
            'season': row[0],
            'episode': row[1],
            'title': row[2],
            'duration_minutes': row[3],
            'status': row[4],
            'progress_percent': row[5],
            'deep_link': row[6]
        })
    
    # Get summary info
    cursor.execute('''
        SELECT total_episodes, watched_episodes
        FROM series_summary
        WHERE user_id = ? AND service = ? AND series_id = ?
    ''', (user_id, service, series_id))
    
    summary_row = cursor.fetchone()
    
    conn.close()
    
    return {
        'series_title': actual_title,
        'service': service,
        'series_id': series_id,
        'total_episodes': summary_row[0] if summary_row else len(episodes),
        'watched_episodes': summary_row[1] if summary_row else 0,
        'unwatched_count': len([e for e in episodes if e['status'] == 'unwatched']),
        'in_progress_count': len([e for e in episodes if e['status'] == 'in_progress']),
        'episodes': episodes
    }


# Flask routes for series progress

@app.route('/series-progress/scrape', methods=['POST'])
def scrape_series_progress():
    """
    Scrape episode progress for a specific series.
    
    Request body:
        service: 'max', 'disney', 'apple', 'hulu', 'netflix', 'prime'
        series_url: URL to the series page
        username: Optional, defaults to 'chad'
    """
    import asyncio
    from series_progress_scraper import (
        MaxSeriesProgressScraper,
        DisneySeriesProgressScraper,
        AppleSeriesProgressScraper,
        HuluSeriesProgressScraper,
        NetflixSeriesProgressScraper,
        PrimeSeriesProgressScraper,
        series_progress_to_dict
    )
    from playwright.async_api import async_playwright
    
    data = request.get_json() or {}
    service = data.get('service', '').lower()
    series_url = data.get('series_url', '')
    username = data.get('username', 'chad')
    
    if not service or not series_url:
        return jsonify({'error': 'service and series_url required'}), 400
    
    if service not in ('max', 'disney', 'apple', 'hulu', 'netflix', 'prime'):
        return jsonify({'error': f'Unsupported service: {service}'}), 400
    
    async def scrape():
        scrapers = {
            'max': MaxSeriesProgressScraper,
            'disney': DisneySeriesProgressScraper,
            'apple': AppleSeriesProgressScraper,
            'hulu': HuluSeriesProgressScraper,
            'netflix': NetflixSeriesProgressScraper,
            'prime': PrimeSeriesProgressScraper,
        }
        
        browser_state_file = os.path.join(
            CREDENTIALS_PATH, 'browser_states', f'{service}_state.json'
        )
        
        if not os.path.exists(browser_state_file):
            return {'error': f'No browser state found for {service}'}
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            with open(browser_state_file, 'r') as f:
                storage_state = json.load(f)
            
            context = await browser.new_context(storage_state=storage_state)
            
            try:
                scraper = scrapers[service](context)
                progress = await scraper.get_series_progress(series_url)
                
                if progress:
                    saved = save_series_progress_to_db(progress, username, series_url=series_url)
                    return {
                        'status': 'ok',
                        'service': service,
                        'series_title': progress.series_title,
                        'episodes_scraped': progress.total_episodes,
                        'episodes_saved': saved,
                        'summary': {
                            'total_seasons': progress.total_seasons,
                            'total_episodes': progress.total_episodes,
                            'watched': progress.watched_episodes,
                            'in_progress': progress.in_progress_episodes,
                            'unwatched': progress.unwatched_episodes,
                            'next_episode': progress.next_episode
                        },
                        'progress': series_progress_to_dict(progress)
                    }
                else:
                    return {'error': 'Failed to scrape series progress'}
            finally:
                await context.close()
                await browser.close()
    
    try:
        result = asyncio.run(scrape())
        if 'error' in result:
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error scraping series progress: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/series-progress/unwatched', methods=['GET'])
def get_unwatched():
    """
    Get unwatched episodes for a series.
    
    Query params:
        series: Series title (fuzzy match)
        service: 'max', 'disney', 'apple', etc.
        username: Optional, defaults to 'chad'
    """
    series = request.args.get('series', '')
    service = request.args.get('service', '')
    username = request.args.get('username', 'chad')
    
    if not series or not service:
        return jsonify({'error': 'series and service query params required'}), 400
    
    result = get_unwatched_episodes(series, service, username)
    
    if 'error' in result:
        return jsonify(result), 404
    
    return jsonify(result)


@app.route('/series-progress/summary', methods=['GET'])
def get_progress_summary():
    """
    Get the formatted memory block summary of all series progress.
    
    Query params:
        username: Optional, defaults to 'chad'
    """
    username = request.args.get('username', 'chad')
    summary = generate_series_progress_memory_block(username)
    return jsonify({'summary': summary})


@app.route('/series-progress/list', methods=['GET'])
def list_tracked_series():
    """
    List all series currently being tracked for progress.
    
    Query params:
        service: Optional, filter by service
        username: Optional, defaults to 'chad'
    """
    service = request.args.get('service', '')
    username = request.args.get('username', 'chad')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user_row = cursor.fetchone()
    if not user_row:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    
    user_id = user_row[0]
    
    if service:
        cursor.execute('''
            SELECT service, series_title, series_id, total_seasons, total_episodes,
                   watched_episodes, in_progress_episodes, unwatched_episodes, scraped_at
            FROM series_summary
            WHERE user_id = ? AND service = ?
            ORDER BY series_title
        ''', (user_id, service))
    else:
        cursor.execute('''
            SELECT service, series_title, series_id, total_seasons, total_episodes,
                   watched_episodes, in_progress_episodes, unwatched_episodes, scraped_at
            FROM series_summary
            WHERE user_id = ?
            ORDER BY service, series_title
        ''', (user_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    series_list = []
    for row in rows:
        series_list.append({
            'service': row[0],
            'series_title': row[1],
            'series_id': row[2],
            'total_seasons': row[3],
            'total_episodes': row[4],
            'watched_episodes': row[5],
            'in_progress_episodes': row[6],
            'unwatched_episodes': row[7],
            'scraped_at': row[8]
        })
    
    return jsonify({'series': series_list, 'count': len(series_list)})


if __name__ == '__main__':
    init_series_progress_table()
    app.run(host='0.0.0.0', port=5127, debug=True)

