"""
NFL Pro Insight Fetcher Service

Fetches and caches narrative insights from NFL Pro for game-start loading.
Designed to be called before or at game start to pre-populate the insight cache.

Usage:
    # Async context
    async with InsightFetcher() as fetcher:
        insights = await fetcher.fetch_for_game(game_uuid)
        fetcher.cache_insights(game_uuid, insights)
    
    # Or as a CLI
    python insight_fetcher.py <game_uuid>
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.nfl_pro_api import NFLProAPIClient, InsightData
from scrapers.insight_parser import InsightParser
from models.insight_schema import InsightIndex

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
DATA_PATH = Path(__file__).parent.parent / "data"
CACHE_DIR = DATA_PATH / "nfl_pro_insights"


class InsightFetcher:
    """
    Fetches and caches NFL Pro narrative insights.
    
    Handles:
    - Fetching insights from NFL Pro API
    - Parsing and indexing
    - Caching to disk for fast loading
    - Cache validation and refresh
    """
    
    CACHE_EXPIRY_HOURS = 24  # Refresh insights daily
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._client: Optional[NFLProAPIClient] = None
        self._parser = InsightParser()
        
        # Ensure cache directory exists
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def start(self):
        """Initialize the API client."""
        self._client = NFLProAPIClient(headless=self.headless)
        await self._client.start()
        logger.info("Insight fetcher initialized")
    
    async def close(self):
        """Clean up resources."""
        if self._client:
            await self._client.close()
    
    def get_cache_path(self, game_uuid: str) -> Path:
        """Get the cache file path for a game."""
        return CACHE_DIR / f"{game_uuid[:8]}_insights.json"
    
    def is_cache_valid(self, game_uuid: str) -> bool:
        """Check if cached insights are still valid."""
        cache_path = self.get_cache_path(game_uuid)
        
        if not cache_path.exists():
            return False
        
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
            
            cached_at = datetime.fromisoformat(data.get('cached_at', '2000-01-01'))
            age_hours = (datetime.now() - cached_at).total_seconds() / 3600
            
            return age_hours < self.CACHE_EXPIRY_HOURS
            
        except Exception as e:
            logger.warning(f"Error checking cache validity: {e}")
            return False
    
    async def fetch_for_game(
        self,
        game_uuid: str,
        wait_time: int = 15
    ) -> List[Dict[str, Any]]:
        """
        Fetch insights from NFL Pro API.
        
        Args:
            game_uuid: NFL Pro game UUID
            wait_time: Seconds to wait for page load
        
        Returns:
            List of raw insight dicts in parser format
        """
        if not self._client:
            raise RuntimeError("Fetcher not initialized. Use 'async with' or call start()")
        
        logger.info(f"Fetching insights for game: {game_uuid}")
        
        insights_raw = await self._client.get_insights(game_uuid, wait_time=wait_time)
        
        if not insights_raw:
            logger.warning("No insights returned from API")
            return []
        
        # Convert to parser format
        parser_format = [i.to_parser_format() for i in insights_raw]
        
        logger.info(f"Fetched {len(parser_format)} insights")
        return parser_format
    
    def parse_insights(self, raw_insights: List[Dict]) -> InsightIndex:
        """Parse raw insights into an indexed structure."""
        return self._parser.parse_batch(raw_insights)
    
    def cache_insights(
        self,
        game_uuid: str,
        raw_insights: List[Dict],
        home_team: str = "",
        away_team: str = ""
    ):
        """
        Cache parsed insights to disk.
        
        Args:
            game_uuid: Game UUID
            raw_insights: Raw insight dicts
            home_team: Home team abbreviation
            away_team: Away team abbreviation
        """
        index = self.parse_insights(raw_insights)
        
        cache_data = {
            'game_uuid': game_uuid,
            'home_team': home_team,
            'away_team': away_team,
            'cached_at': datetime.now().isoformat(),
            'insight_count': len(index.all_insights),
            'insights': json.loads(index.to_json())['insights'],
        }
        
        cache_path = self.get_cache_path(game_uuid)
        with open(cache_path, 'w') as f:
            json.dump(cache_data, f, indent=2)
        
        logger.info(f"Cached {len(index.all_insights)} insights to: {cache_path}")
    
    def load_cached_insights(self, game_uuid: str) -> Optional[InsightIndex]:
        """Load cached insights for a game."""
        cache_path = self.get_cache_path(game_uuid)
        
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
            
            index = InsightIndex.from_json(json.dumps({'insights': data['insights']}))
            logger.info(f"Loaded {len(index.all_insights)} cached insights for {game_uuid[:8]}")
            return index
            
        except Exception as e:
            logger.error(f"Error loading cached insights: {e}")
            return None
    
    async def ensure_cached(
        self,
        game_uuid: str,
        home_team: str = "",
        away_team: str = "",
        force_refresh: bool = False
    ) -> InsightIndex:
        """
        Ensure insights are cached and return the index.
        
        Fetches from API if cache is missing or expired.
        """
        if not force_refresh and self.is_cache_valid(game_uuid):
            index = self.load_cached_insights(game_uuid)
            if index:
                return index
        
        # Fetch and cache
        raw_insights = await self.fetch_for_game(game_uuid)
        
        if raw_insights:
            self.cache_insights(game_uuid, raw_insights, home_team, away_team)
            return self.parse_insights(raw_insights)
        
        # Return empty index if fetch failed
        return InsightIndex()


async def fetch_and_cache_game_insights(
    game_uuid: str,
    home_team: str = "",
    away_team: str = "",
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Convenience function to fetch and cache insights for a game.
    
    Returns:
        Dict with status and stats
    """
    async with InsightFetcher() as fetcher:
        index = await fetcher.ensure_cached(
            game_uuid,
            home_team=home_team,
            away_team=away_team,
            force_refresh=force_refresh
        )
        
        return {
            'success': len(index.all_insights) > 0,
            'total_insights': len(index.all_insights),
            'players_indexed': len(index.by_player),
            'teams_indexed': len(index.by_team),
            'matchup_insights': len(index.matchup_insights),
        }


async def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python insight_fetcher.py <game_uuid> [--refresh]")
        print("\nExample:")
        print("  python insight_fetcher.py f979d7ee-311e-11f0-b670-ae1250fadad1")
        sys.exit(1)
    
    game_uuid = sys.argv[1]
    force_refresh = '--refresh' in sys.argv
    
    print(f"\n📰 Fetching insights for game: {game_uuid}")
    print(f"   Force refresh: {force_refresh}")
    
    result = await fetch_and_cache_game_insights(game_uuid, force_refresh=force_refresh)
    
    print(f"\n✅ Results:")
    print(f"   Success: {result['success']}")
    print(f"   Total insights: {result['total_insights']}")
    print(f"   Players indexed: {result['players_indexed']}")
    print(f"   Teams indexed: {result['teams_indexed']}")
    print(f"   Matchup insights: {result['matchup_insights']}")
    
    # Show cache location
    cache_path = CACHE_DIR / f"{game_uuid[:8]}_insights.json"
    print(f"\n📁 Cache location: {cache_path}")


if __name__ == '__main__':
    asyncio.run(main())

