"""
Session Keeper - Automated Playwright-based session maintenance for streaming services.

This module maintains persistent browser sessions for streaming services,
automatically refreshing credentials before they expire and storing them
for use by the watch history poller.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

# Session state directory
SESSION_DIR = Path(os.environ.get('CREDENTIALS_PATH', '/app/credentials'))
BROWSER_STATE_DIR = SESSION_DIR / 'browser_states'


class SessionStatus(Enum):
    """Status of a streaming service session."""
    UNKNOWN = "unknown"
    ACTIVE = "active"
    EXPIRED = "expired"
    NEEDS_LOGIN = "needs_login"
    ERROR = "error"


@dataclass
class ServiceSession:
    """Represents a session for a streaming service."""
    service: str
    status: SessionStatus
    last_check: Optional[datetime] = None
    last_refresh: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    error_message: Optional[str] = None
    cookies_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'service': self.service,
            'status': self.status.value,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'error_message': self.error_message,
            'cookies_count': self.cookies_count
        }


class StreamingServiceConfig:
    """Configuration for each streaming service."""
    
    SERVICES = {
        'netflix': {
            'name': 'Netflix',
            'login_url': 'https://www.netflix.com/login',
            'home_url': 'https://www.netflix.com/browse',
            'check_url': 'https://www.netflix.com/browse',
            'logged_in_selector': '[data-uia="profile-link"]',
            'login_needed_selector': '[data-uia="login-submit-button"]',
            'session_duration_hours': 168,  # 7 days
            'refresh_before_hours': 24,
        },
        'hulu': {
            'name': 'Hulu',
            'login_url': 'https://auth.hulu.com/web/login',
            'home_url': 'https://www.hulu.com/hub/home',
            'check_url': 'https://www.hulu.com/hub/home',
            'logged_in_selector': '[data-testid="user-menu-button"]',
            'login_needed_selector': '[data-automationid="login-button"]',
            'session_duration_hours': 720,  # 30 days
            'refresh_before_hours': 48,
        },
        'max': {
            'name': 'Max (HBO)',
            'login_url': 'https://play.max.com/sign-in',
            'home_url': 'https://play.max.com/',
            'check_url': 'https://play.max.com/',
            'logged_in_selector': '[data-testid="profile-menu-button"]',
            'login_needed_selector': '[data-testid="sign-in-button"]',
            'session_duration_hours': 720,  # 30 days (token shows 10 years but refresh periodically)
            'refresh_before_hours': 168,  # 7 days
        },
        'disney': {
            'name': 'Disney+',
            'login_url': 'https://www.disneyplus.com/login',
            'home_url': 'https://www.disneyplus.com/home',
            'check_url': 'https://www.disneyplus.com/home',
            'logged_in_selector': '[data-testid="profile-avatar"]',
            'login_needed_selector': '[data-testid="login-btn"]',
            'session_duration_hours': 720,  # 30 days
            'refresh_before_hours': 48,
        },
        'apple': {
            'name': 'Apple TV+',
            'login_url': 'https://tv.apple.com/',
            'home_url': 'https://tv.apple.com/',
            'check_url': 'https://tv.apple.com/',
            'logged_in_selector': '[data-testid="account-menu"]',
            'login_needed_selector': 'a[href*="sign-in"]',
            'session_duration_hours': 168,  # 7 days
            'refresh_before_hours': 24,
        },
        'prime': {
            'name': 'Prime Video',
            'login_url': 'https://www.amazon.com/ap/signin',
            'home_url': 'https://www.amazon.com/gp/video/storefront',
            'check_url': 'https://www.amazon.com/gp/video/storefront',
            'logged_in_selector': '#nav-link-accountList',
            'login_needed_selector': '[name="signIn"]',
            'session_duration_hours': 336,  # 14 days
            'refresh_before_hours': 48,
        },
    }
    
    @classmethod
    def get(cls, service: str) -> Optional[Dict]:
        return cls.SERVICES.get(service)
    
    @classmethod
    def all_services(cls) -> List[str]:
        return list(cls.SERVICES.keys())


class SessionKeeper:
    """
    Maintains browser sessions for streaming services.
    
    Uses Playwright to:
    1. Check if sessions are still valid
    2. Refresh sessions by navigating to the service
    3. Extract and store cookies/tokens
    4. Alert when manual login is needed
    """
    
    def __init__(self, credentials_path: str = None):
        self.credentials_path = Path(credentials_path or SESSION_DIR)
        self.browser_state_dir = self.credentials_path / 'browser_states'
        self.browser_state_dir.mkdir(parents=True, exist_ok=True)
        
        self.sessions: Dict[str, ServiceSession] = {}
        self._browser: Optional[Browser] = None
        self._playwright = None
        
        # Initialize session tracking
        for service in StreamingServiceConfig.all_services():
            self.sessions[service] = ServiceSession(
                service=service,
                status=SessionStatus.UNKNOWN
            )
        
        # Load existing session info
        self._load_session_info()
    
    def _load_session_info(self):
        """Load session info from disk."""
        info_file = self.credentials_path / 'session_info.json'
        if info_file.exists():
            try:
                with open(info_file) as f:
                    data = json.load(f)
                for service, info in data.items():
                    if service in self.sessions:
                        self.sessions[service].last_check = (
                            datetime.fromisoformat(info['last_check']) 
                            if info.get('last_check') else None
                        )
                        self.sessions[service].last_refresh = (
                            datetime.fromisoformat(info['last_refresh']) 
                            if info.get('last_refresh') else None
                        )
                        self.sessions[service].status = SessionStatus(info.get('status', 'unknown'))
                        self.sessions[service].cookies_count = info.get('cookies_count', 0)
            except Exception as e:
                logger.warning(f"Could not load session info: {e}")
    
    def _save_session_info(self):
        """Save session info to disk."""
        info_file = self.credentials_path / 'session_info.json'
        data = {
            service: session.to_dict() 
            for service, session in self.sessions.items()
        }
        with open(info_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _get_state_path(self, service: str) -> Path:
        """Get the browser state file path for a service."""
        return self.browser_state_dir / f'{service}_state.json'
    
    async def _get_browser(self) -> Browser:
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
    
    async def _create_context(self, service: str) -> BrowserContext:
        """Create a browser context, optionally restoring state."""
        browser = await self._get_browser()
        state_path = self._get_state_path(service)
        
        context_options = {
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        
        if state_path.exists():
            try:
                context_options['storage_state'] = str(state_path)
                logger.info(f"Restoring browser state for {service}")
            except Exception as e:
                logger.warning(f"Could not restore state for {service}: {e}")
        
        return await browser.new_context(**context_options)
    
    async def _save_context_state(self, context: BrowserContext, service: str):
        """Save browser context state to disk."""
        state_path = self._get_state_path(service)
        try:
            state = await context.storage_state()
            with open(state_path, 'w') as f:
                json.dump(state, f)
            logger.info(f"Saved browser state for {service}")
        except Exception as e:
            logger.error(f"Could not save state for {service}: {e}")
    
    async def _extract_and_save_credentials(self, context: BrowserContext, service: str) -> Dict:
        """Extract cookies and tokens from browser context and save to credentials store."""
        cookies = await context.cookies()
        
        # Convert to our credential format
        credentials = {
            'cookies': cookies,
            'extracted_at': datetime.now().isoformat(),
            'service': service
        }
        
        # Save to credentials file
        cred_file = self.credentials_path / f'{service}.json'
        with open(cred_file, 'w') as f:
            json.dump(credentials, f, indent=2)
        
        self.sessions[service].cookies_count = len(cookies)
        logger.info(f"Saved {len(cookies)} cookies for {service}")
        
        return credentials
    
    async def check_session(self, service: str) -> ServiceSession:
        """Check if a session is still valid."""
        config = StreamingServiceConfig.get(service)
        if not config:
            self.sessions[service].status = SessionStatus.ERROR
            self.sessions[service].error_message = f"Unknown service: {service}"
            return self.sessions[service]
        
        context = None
        try:
            context = await self._create_context(service)
            page = await context.new_page()
            
            # Navigate to check URL
            logger.info(f"Checking session for {service} at {config['check_url']}")
            await page.goto(config['check_url'], wait_until='networkidle', timeout=30000)
            
            # Wait a moment for dynamic content
            await asyncio.sleep(2)
            
            # Check for logged-in indicator
            logged_in = await page.query_selector(config['logged_in_selector'])
            login_needed = await page.query_selector(config['login_needed_selector'])
            
            self.sessions[service].last_check = datetime.now()
            
            if logged_in and not login_needed:
                self.sessions[service].status = SessionStatus.ACTIVE
                self.sessions[service].last_refresh = datetime.now()
                self.sessions[service].error_message = None
                
                # Save state and extract credentials
                await self._save_context_state(context, service)
                await self._extract_and_save_credentials(context, service)
                
                logger.info(f"Session for {service} is ACTIVE")
            else:
                self.sessions[service].status = SessionStatus.NEEDS_LOGIN
                self.sessions[service].error_message = "Login required"
                logger.warning(f"Session for {service} NEEDS LOGIN")
            
            await page.close()
            
        except Exception as e:
            logger.error(f"Error checking session for {service}: {e}")
            self.sessions[service].status = SessionStatus.ERROR
            self.sessions[service].error_message = str(e)
        
        finally:
            if context:
                await context.close()
            self._save_session_info()
        
        return self.sessions[service]
    
    async def refresh_session(self, service: str) -> ServiceSession:
        """Refresh a session by navigating and interacting with the service."""
        config = StreamingServiceConfig.get(service)
        if not config:
            return self.sessions[service]
        
        context = None
        try:
            context = await self._create_context(service)
            page = await context.new_page()
            
            # Navigate to home to refresh session
            logger.info(f"Refreshing session for {service}")
            await page.goto(config['home_url'], wait_until='networkidle', timeout=30000)
            
            # Wait for page to load fully
            await asyncio.sleep(3)
            
            # Check if we're still logged in
            logged_in = await page.query_selector(config['logged_in_selector'])
            
            if logged_in:
                # Do some light interaction to refresh session
                await page.mouse.move(500, 500)
                await asyncio.sleep(1)
                
                # Scroll a bit
                await page.evaluate('window.scrollBy(0, 300)')
                await asyncio.sleep(1)
                
                self.sessions[service].status = SessionStatus.ACTIVE
                self.sessions[service].last_refresh = datetime.now()
                self.sessions[service].error_message = None
                
                # Save state and credentials
                await self._save_context_state(context, service)
                await self._extract_and_save_credentials(context, service)
                
                logger.info(f"Session for {service} refreshed successfully")
            else:
                self.sessions[service].status = SessionStatus.NEEDS_LOGIN
                self.sessions[service].error_message = "Session expired during refresh"
                logger.warning(f"Session for {service} expired")
            
            await page.close()
            
        except Exception as e:
            logger.error(f"Error refreshing session for {service}: {e}")
            self.sessions[service].status = SessionStatus.ERROR
            self.sessions[service].error_message = str(e)
        
        finally:
            if context:
                await context.close()
            self._save_session_info()
        
        return self.sessions[service]
    
    async def import_cookies_to_browser(self, service: str, cookies: List[Dict]) -> bool:
        """Import cookies from external source into browser context."""
        context = None
        try:
            browser = await self._get_browser()
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            )
            
            # Add cookies to context
            await context.add_cookies(cookies)
            
            # Navigate to verify
            config = StreamingServiceConfig.get(service)
            if config:
                page = await context.new_page()
                await page.goto(config['check_url'], wait_until='networkidle', timeout=30000)
                await asyncio.sleep(2)
                
                logged_in = await page.query_selector(config['logged_in_selector'])
                if logged_in:
                    # Save the state
                    await self._save_context_state(context, service)
                    self.sessions[service].status = SessionStatus.ACTIVE
                    self.sessions[service].last_refresh = datetime.now()
                    self.sessions[service].cookies_count = len(cookies)
                    logger.info(f"Successfully imported cookies for {service}")
                    return True
                else:
                    logger.warning(f"Imported cookies for {service} but session not valid")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error importing cookies for {service}: {e}")
            return False
        
        finally:
            if context:
                await context.close()
            self._save_session_info()
    
    async def check_all_sessions(self) -> Dict[str, ServiceSession]:
        """Check all service sessions."""
        results = {}
        for service in StreamingServiceConfig.all_services():
            results[service] = await self.check_session(service)
            await asyncio.sleep(2)  # Be gentle with services
        return results
    
    async def refresh_due_sessions(self) -> Dict[str, ServiceSession]:
        """Refresh sessions that are due for refresh."""
        results = {}
        now = datetime.now()
        
        for service, session in self.sessions.items():
            config = StreamingServiceConfig.get(service)
            if not config:
                continue
            
            needs_refresh = False
            
            if session.status == SessionStatus.UNKNOWN:
                needs_refresh = True
            elif session.status == SessionStatus.ACTIVE and session.last_refresh:
                refresh_threshold = timedelta(hours=config['refresh_before_hours'])
                if now - session.last_refresh > refresh_threshold:
                    needs_refresh = True
            
            if needs_refresh:
                logger.info(f"Refreshing due session for {service}")
                results[service] = await self.refresh_session(service)
                await asyncio.sleep(5)  # Be gentle with services
        
        return results
    
    def get_status(self) -> Dict[str, Dict]:
        """Get status of all sessions."""
        return {
            service: session.to_dict()
            for service, session in self.sessions.items()
        }
    
    def get_services_needing_login(self) -> List[str]:
        """Get list of services that need manual login."""
        return [
            service for service, session in self.sessions.items()
            if session.status == SessionStatus.NEEDS_LOGIN
        ]
    
    async def close(self):
        """Clean up resources."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


# Background scheduler for session maintenance
class SessionScheduler:
    """Scheduler for periodic session maintenance."""
    
    def __init__(self, keeper: SessionKeeper, check_interval_minutes: int = 30):
        self.keeper = keeper
        self.check_interval = check_interval_minutes * 60
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def _run_loop(self):
        """Main scheduler loop."""
        while self._running:
            try:
                logger.info("Running scheduled session maintenance...")
                await self.keeper.refresh_due_sessions()
                
                # Check for services needing login and log
                needs_login = self.keeper.get_services_needing_login()
                if needs_login:
                    logger.warning(f"Services needing manual login: {needs_login}")
                
            except Exception as e:
                logger.error(f"Error in session maintenance: {e}")
            
            await asyncio.sleep(self.check_interval)
    
    def start(self):
        """Start the scheduler."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run_loop())
            logger.info(f"Session scheduler started (interval: {self.check_interval}s)")
    
    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            logger.info("Session scheduler stopped")


# Global instance
_session_keeper: Optional[SessionKeeper] = None
_scheduler: Optional[SessionScheduler] = None


def get_session_keeper() -> SessionKeeper:
    """Get the global session keeper instance."""
    global _session_keeper
    if _session_keeper is None:
        _session_keeper = SessionKeeper()
    return _session_keeper


def get_scheduler() -> SessionScheduler:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = SessionScheduler(get_session_keeper())
    return _scheduler

