#!/usr/bin/env python3
"""
NFL Pro Page Investigator

A tool to explore the structure of NFL Pro pages and understand the DOM
for building scrapers. Opens a visible browser to inspect elements.

Usage:
    python page_investigator.py <game_uuid> [tab]
    
    tab: overview (default), box-score, play-by-play, insights
    
Example:
    python page_investigator.py f979d7ee-311e-11f0-b670-ae1250fadad1 play-by-play
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

from playwright.async_api import async_playwright, Page

# Configuration
CREDENTIALS_PATH = Path(os.environ.get('CREDENTIALS_PATH', '../credentials'))
BROWSER_STATES_PATH = CREDENTIALS_PATH / 'browser_states'
OUTPUT_PATH = Path('../data/investigations')


class PageInvestigator:
    """Investigates NFL Pro page structure for scraper development."""
    
    BASE_URL = "https://pro.nfl.com/games/game"
    
    TABS = {
        'overview': '',
        'box-score': '/box-score',
        'play-by-play': '/play-by-play',
        'insights': '/insights',
    }
    
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def start(self):
        """Initialize the browser."""
        state_file = BROWSER_STATES_PATH / 'nfl_pro_state.json'
        
        if not state_file.exists():
            print("❌ No saved session found. Please run nfl_pro_login.py first.")
            raise FileNotFoundError("No NFL Pro session")
        
        self._playwright = await async_playwright().start()
        
        self.browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=['--start-maximized'] if not self.headless else [],
        )
        
        self.context = await self.browser.new_context(
            storage_state=str(state_file),
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        )
        
        self.page = await self.context.new_page()
        print("🚀 Browser initialized with saved session")
    
    async def close(self):
        """Clean up browser resources."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    async def navigate_to_game(self, game_uuid: str, tab: str = 'overview') -> bool:
        """Navigate to a specific game tab."""
        tab_path = self.TABS.get(tab, '')
        url = f"{self.BASE_URL}/{game_uuid}{tab_path}"
        
        print(f"📍 Navigating to: {url}")
        await self.page.goto(url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(3)  # Wait for dynamic content
        
        # Check if we got redirected to login
        if 'login' in self.page.url.lower() or 'signin' in self.page.url.lower():
            print("❌ Session expired - please run nfl_pro_login.py")
            return False
        
        print(f"✅ Loaded: {self.page.url}")
        return True
    
    async def analyze_page_structure(self) -> Dict[str, Any]:
        """Analyze the current page structure."""
        print("\n🔍 Analyzing page structure...")
        
        analysis = {
            'url': self.page.url,
            'title': await self.page.title(),
            'timestamp': datetime.now().isoformat(),
            'major_sections': [],
            'tables': [],
            'interactive_elements': [],
            'data_attributes': [],
        }
        
        # Find major sections
        sections = await self.page.query_selector_all('section, [class*="section"], [class*="Section"]')
        for section in sections[:20]:  # Limit to first 20
            try:
                class_attr = await section.get_attribute('class') or ''
                id_attr = await section.get_attribute('id') or ''
                text_preview = (await section.inner_text())[:100] if section else ''
                analysis['major_sections'].append({
                    'class': class_attr,
                    'id': id_attr,
                    'preview': text_preview.replace('\n', ' ')[:100],
                })
            except Exception:
                pass
        
        # Find tables
        tables = await self.page.query_selector_all('table, [role="grid"], [class*="table"], [class*="Table"]')
        for table in tables[:10]:
            try:
                class_attr = await table.get_attribute('class') or ''
                headers = await table.query_selector_all('th, [role="columnheader"]')
                header_texts = []
                for h in headers[:10]:
                    text = await h.inner_text()
                    header_texts.append(text.strip())
                analysis['tables'].append({
                    'class': class_attr,
                    'headers': header_texts,
                })
            except Exception:
                pass
        
        # Find interactive elements (filters, dropdowns)
        selects = await self.page.query_selector_all('select, [role="listbox"], [class*="dropdown"], [class*="filter"]')
        for elem in selects[:10]:
            try:
                class_attr = await elem.get_attribute('class') or ''
                aria_label = await elem.get_attribute('aria-label') or ''
                analysis['interactive_elements'].append({
                    'type': 'select/dropdown',
                    'class': class_attr,
                    'aria_label': aria_label,
                })
            except Exception:
                pass
        
        # Find data attributes (note: can't use [data-*] wildcard in CSS)
        data_elements = await self.page.query_selector_all('[data-testid], [data-analytics], [data-game], [data-play]')
        seen_attrs = set()
        for elem in data_elements[:50]:
            try:
                attrs = await elem.evaluate('el => Object.fromEntries([...el.attributes].filter(a => a.name.startsWith("data-")).map(a => [a.name, a.value]))')
                for name, value in attrs.items():
                    if name not in seen_attrs:
                        seen_attrs.add(name)
                        analysis['data_attributes'].append({
                            'name': name,
                            'sample_value': value[:50] if value else '',
                        })
            except Exception:
                pass
        
        print(f"   Found {len(analysis['major_sections'])} sections")
        print(f"   Found {len(analysis['tables'])} tables")
        print(f"   Found {len(analysis['interactive_elements'])} interactive elements")
        print(f"   Found {len(analysis['data_attributes'])} unique data attributes")
        
        return analysis
    
    async def analyze_play_by_play(self) -> Dict[str, Any]:
        """Specialized analysis for play-by-play page."""
        print("\n🏈 Analyzing play-by-play structure...")
        
        analysis = {
            'plays': [],
            'filters': [],
            'columns': [],
            'hidden_data': [],
        }
        
        # Wait for play content to load
        await asyncio.sleep(2)
        
        # Find play rows
        play_rows = await self.page.query_selector_all(
            '[class*="play"], [class*="Play"], tbody tr, [role="row"]'
        )
        print(f"   Found {len(play_rows)} potential play rows")
        
        # Analyze first few plays
        for row in play_rows[:5]:
            try:
                play_data = {
                    'class': await row.get_attribute('class') or '',
                    'text': (await row.inner_text())[:200].replace('\n', ' | '),
                }
                
                # Look for nested elements
                cells = await row.query_selector_all('td, [role="cell"], div')
                play_data['cell_count'] = len(cells)
                
                analysis['plays'].append(play_data)
            except Exception:
                pass
        
        # Find filter controls
        filter_elements = await self.page.query_selector_all(
            '[class*="filter"], [class*="Filter"], select, [role="listbox"]'
        )
        for elem in filter_elements[:10]:
            try:
                class_attr = await elem.get_attribute('class') or ''
                options = await elem.query_selector_all('option, [role="option"]')
                option_texts = []
                for opt in options[:10]:
                    text = await opt.inner_text()
                    option_texts.append(text.strip())
                analysis['filters'].append({
                    'class': class_attr,
                    'options': option_texts,
                })
            except Exception:
                pass
        
        print(f"   Found {len(analysis['filters'])} filter elements")
        
        return analysis
    
    async def analyze_insights_page(self) -> Dict[str, Any]:
        """Specialized analysis for insights page."""
        print("\n💡 Analyzing insights structure...")
        
        analysis = {
            'insights': [],
            'insight_structure': {},
        }
        
        await asyncio.sleep(2)
        
        # Find insight cards
        insight_cards = await self.page.query_selector_all(
            '[class*="insight"], [class*="Insight"], [class*="card"], [class*="Card"]'
        )
        print(f"   Found {len(insight_cards)} potential insight cards")
        
        for card in insight_cards[:10]:
            try:
                insight = {
                    'class': await card.get_attribute('class') or '',
                    'full_text': (await card.inner_text())[:500].replace('\n', ' | '),
                }
                
                # Look for structure elements
                headline = await card.query_selector('h2, h3, h4, [class*="headline"], [class*="title"]')
                if headline:
                    insight['headline'] = await headline.inner_text()
                
                paragraphs = await card.query_selector_all('p')
                insight['paragraph_count'] = len(paragraphs)
                
                analysis['insights'].append(insight)
            except Exception:
                pass
        
        return analysis
    
    async def capture_network_requests(self, duration: int = 10) -> List[Dict]:
        """Capture network requests to find API endpoints."""
        print(f"\n🌐 Capturing network requests for {duration} seconds...")
        
        requests = []
        
        async def handle_request(request):
            if 'api' in request.url.lower() or 'graphql' in request.url.lower():
                requests.append({
                    'url': request.url,
                    'method': request.method,
                    'resource_type': request.resource_type,
                })
        
        self.page.on('request', handle_request)
        
        # Wait and interact to trigger requests
        await asyncio.sleep(duration)
        
        # Try scrolling to load more
        await self.page.evaluate('window.scrollBy(0, 500)')
        await asyncio.sleep(2)
        
        print(f"   Captured {len(requests)} API requests")
        return requests
    
    async def save_investigation(self, data: Dict[str, Any], filename: str):
        """Save investigation results to file."""
        OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
        filepath = OUTPUT_PATH / filename
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"📄 Saved to: {filepath}")
    
    async def interactive_inspect(self):
        """Open browser for interactive inspection."""
        print("\n🔬 Interactive inspection mode")
        print("   Browser is open for manual inspection.")
        print("   Press Enter when done to continue...")
        
        await asyncio.get_event_loop().run_in_executor(None, input)


async def investigate_game(game_uuid: str, tab: str = 'overview'):
    """Run investigation on a game page."""
    async with PageInvestigator(headless=False) as investigator:
        if not await investigator.navigate_to_game(game_uuid, tab):
            return
        
        # General structure analysis
        structure = await investigator.analyze_page_structure()
        
        # Tab-specific analysis
        if tab == 'play-by-play':
            specific = await investigator.analyze_play_by_play()
            structure['play_by_play_analysis'] = specific
        elif tab == 'insights':
            specific = await investigator.analyze_insights_page()
            structure['insights_analysis'] = specific
        
        # Capture network requests
        api_requests = await investigator.capture_network_requests(5)
        structure['api_requests'] = api_requests
        
        # Save results
        filename = f"investigation_{tab}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        await investigator.save_investigation(structure, filename)
        
        # Allow interactive inspection
        await investigator.interactive_inspect()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    game_uuid = sys.argv[1]
    tab = sys.argv[2] if len(sys.argv) > 2 else 'overview'
    
    if tab not in PageInvestigator.TABS:
        print(f"❌ Unknown tab: {tab}")
        print(f"   Available tabs: {', '.join(PageInvestigator.TABS.keys())}")
        sys.exit(1)
    
    asyncio.run(investigate_game(game_uuid, tab))


if __name__ == '__main__':
    main()

