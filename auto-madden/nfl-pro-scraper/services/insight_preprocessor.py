"""
NFL Pro Insight Pre-processor

Pre-processes scraped insights for efficient real-time retrieval during games:
1. Loads insights from database
2. Parses for terms of art
3. Extracts player/team entities
4. Generates LLM-ready context
5. Creates indexed structure for fast lookup

Usage:
    python insight_preprocessor.py --week 18 --season 2025
    python insight_preprocessor.py --all --season 2025
"""

import json
import logging
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATA_PATH = Path(os.environ.get('DATA_PATH', '/Volumes/main-drive/ai-PA/auto-madden/data'))

# NFL team abbreviations for entity extraction
NFL_TEAMS = {
    'ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE',
    'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC',
    'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG',
    'NYJ', 'PHI', 'PIT', 'SEA', 'SF', 'TB', 'TEN', 'WAS'
}

# Terms of art for football education
FOOTBALL_TERMS = {
    # Formations
    'shotgun', 'under center', 'pistol', 'spread', 'i-formation', 'single back',
    'empty backfield', 'jumbo', 'goal line', '11 personnel', '12 personnel',
    '21 personnel', '22 personnel', '13 personnel',
    
    # Routes
    'slant', 'out route', 'go route', 'post', 'corner route', 'dig', 'curl',
    'comeback', 'wheel route', 'screen', 'dump off',
    
    # Defensive schemes
    'cover 2', 'cover 3', 'cover 4', 'man coverage', 'zone coverage',
    'press coverage', 'cloud coverage', 'bracket coverage', 'tampa 2',
    'quarters', 'cover 6',
    
    # Blitz/pressure
    'blitz', 'a-gap blitz', 'b-gap blitz', 'zone blitz', 'delayed blitz',
    'contain', 'spy', 'pass rush', 'pressure', 'sack', 'hurry',
    'pressured dropback', 'clean pocket',
    
    # Run concepts
    'zone run', 'power run', 'counter', 'trap', 'stretch', 'dive',
    'draw play', 'play action', 'read option', 'rpo',
    
    # Coverage/defensive terms
    'safety help', 'single high', 'two high', 'box count', 'light box',
    'loaded box', 'defenders in box', 'shell', 'coverage shell',
    
    # Stats/metrics
    'passer rating', 'qbr', 'epa', 'yards after catch', 'yac',
    'air yards', 'target share', 'snap count', 'dropback',
    'completion percentage', 'yards per attempt', 'first down rate',
    'red zone', 'third down', 'fourth down', 'two-minute drill',
    
    # Positions
    'edge rusher', 'interior lineman', 'slot receiver', 'tight end',
    'running back', 'fullback', 'linebacker', 'cornerback', 'safety',
    'nickel', 'dime', 'big nickel'
}


@dataclass
class ProcessedInsight:
    """A pre-processed insight ready for retrieval."""
    id: str
    game_id: str
    week: int
    season: int
    
    # Content
    title: str
    sub_note: str = ''
    
    # Entities
    player_name: str = ''
    player_team: str = ''
    player_position: str = ''
    secondary_entity: str = ''
    secondary_team: str = ''
    
    # Image
    image_url: str = ''
    local_image: str = ''
    
    # Extracted metadata
    terms_of_art: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    teams_mentioned: List[str] = field(default_factory=list)
    
    # Retrieval keys
    retrieval_keys: List[str] = field(default_factory=list)
    
    # LLM context
    llm_summary: str = ''
    
    # Usage tracking
    times_served: int = 0
    last_served_game: str = ''
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class InsightPreprocessor:
    """Pre-processes insights for a game or week."""
    
    def __init__(self, season: int = 2025):
        self.season = season
        self.db_path = DATA_PATH / f"nfl_insights_{season}.db"
        self.output_path = DATA_PATH / "processed_insights"
        self.output_path.mkdir(parents=True, exist_ok=True)
        
        # Term patterns for extraction
        self._term_patterns = self._compile_term_patterns()
    
    def _compile_term_patterns(self) -> Dict[str, re.Pattern]:
        """Compile regex patterns for term extraction."""
        patterns = {}
        for term in FOOTBALL_TERMS:
            # Case-insensitive match with word boundaries
            pattern = re.compile(r'\b' + re.escape(term) + r's?\b', re.IGNORECASE)
            patterns[term] = pattern
        return patterns
    
    def extract_terms_of_art(self, text: str) -> List[str]:
        """Extract football terms of art from text."""
        found_terms = set()
        for term, pattern in self._term_patterns.items():
            if pattern.search(text):
                found_terms.add(term)
        return sorted(found_terms)
    
    # Team name to abbreviation mapping
    TEAM_NAMES = {
        'Cardinals': 'ARI', 'Falcons': 'ATL', 'Ravens': 'BAL', 'Bills': 'BUF',
        'Panthers': 'CAR', 'Bears': 'CHI', 'Bengals': 'CIN', 'Browns': 'CLE',
        'Cowboys': 'DAL', 'Broncos': 'DEN', 'Lions': 'DET', 'Packers': 'GB',
        'Texans': 'HOU', 'Colts': 'IND', 'Jaguars': 'JAX', 'Chiefs': 'KC',
        'Chargers': 'LAC', 'Rams': 'LAR', 'Raiders': 'LV', 'Dolphins': 'MIA',
        'Vikings': 'MIN', 'Patriots': 'NE', 'Saints': 'NO', 'Giants': 'NYG',
        'Jets': 'NYJ', 'Eagles': 'PHI', 'Steelers': 'PIT', 'Seahawks': 'SEA',
        '49ers': 'SF', 'Niners': 'SF', 'Buccaneers': 'TB', 'Bucs': 'TB',
        'Titans': 'TEN', 'Commanders': 'WAS', 'Washington': 'WAS'
    }
    
    def extract_teams(self, text: str) -> List[str]:
        """Extract team abbreviations from text."""
        found_teams = set()
        
        # Check abbreviations
        for team in NFL_TEAMS:
            if re.search(r'\b' + team + r'\b', text, re.IGNORECASE):
                found_teams.add(team)
        
        # Check team names
        for name, abbr in self.TEAM_NAMES.items():
            if re.search(r'\b' + re.escape(name) + r'\b', text, re.IGNORECASE):
                found_teams.add(abbr)
        
        return sorted(found_teams)
    
    def extract_topics(self, text: str, terms: List[str]) -> List[str]:
        """Categorize insight into topics based on content."""
        topics = set()
        text_lower = text.lower()
        
        # Passing game
        if any(w in text_lower for w in ['pass', 'throw', 'quarterback', 'dropback', 'completion', 'intercepti']):
            topics.add('passing')
        
        # Rushing
        if any(w in text_lower for w in ['rush', 'run', 'carry', 'yards per carry', 'running back']):
            topics.add('rushing')
        
        # Defense
        if any(w in text_lower for w in ['defense', 'sack', 'pressure', 'coverage', 'intercept', 'tackle']):
            topics.add('defense')
        
        # Red zone
        if 'red zone' in text_lower:
            topics.add('redzone')
        
        # Third down
        if 'third down' in text_lower:
            topics.add('third_down')
        
        # Turnover related
        if any(w in text_lower for w in ['turnover', 'fumble', 'interception', 'pick']):
            topics.add('turnovers')
        
        # Historical/stats
        if any(w in text_lower for w in ['season', 'career', 'leads', 'ranks', 'average']):
            topics.add('stats')
        
        # Matchup
        if any(w in text_lower for w in ['matchup', 'versus', 'against', 'when facing']):
            topics.add('matchup')
        
        return sorted(topics)
    
    def generate_retrieval_keys(self, insight: ProcessedInsight) -> List[str]:
        """Generate keys for retrieving this insight."""
        keys = []
        
        # Player-based keys
        if insight.player_name:
            # Clean player name (remove team names that might be mistaken for players)
            player_lower = insight.player_name.lower()
            if player_lower not in ['49ers', 'chiefs', 'bills', 'eagles', 'seahawks', 'cowboys']:
                keys.append(f"player:{player_lower}")
                if insight.player_team:
                    keys.append(f"player:{player_lower}:{insight.player_team.lower()}")
        
        # Team-based keys (from explicit field and from text extraction)
        all_teams = set()
        if insight.player_team:
            all_teams.add(insight.player_team.upper())
        for team in insight.teams_mentioned:
            all_teams.add(team.upper())
        
        for team in all_teams:
            keys.append(f"team:{team.lower()}")
        
        # Topic-based keys
        for topic in insight.topics:
            keys.append(f"topic:{topic}")
        
        # Term-based keys
        for term in insight.terms_of_art:
            keys.append(f"term:{term.lower()}")
        
        # Position-based keys
        if insight.player_position:
            keys.append(f"position:{insight.player_position.lower()}")
        
        return keys
    
    def generate_llm_summary(self, insight: ProcessedInsight) -> str:
        """Generate a compact LLM-ready summary."""
        parts = []
        
        if insight.player_name:
            parts.append(f"About {insight.player_name}")
            if insight.player_team:
                parts.append(f"({insight.player_team})")
        
        if insight.topics:
            parts.append(f"Topics: {', '.join(insight.topics)}")
        
        if insight.terms_of_art:
            parts.append(f"Terms: {', '.join(insight.terms_of_art[:3])}")
        
        return ' | '.join(parts)
    
    def process_insight(self, row: Dict) -> ProcessedInsight:
        """Process a single insight from database row."""
        full_text = f"{row.get('title', '')} {row.get('sub_note', '')}"
        
        insight = ProcessedInsight(
            id=row.get('insight_id', ''),
            game_id=row.get('game_id', ''),
            week=row.get('week', 0),
            season=row.get('season', self.season),
            title=row.get('title', ''),
            sub_note=row.get('sub_note', ''),
            player_name=row.get('player_name', ''),
            player_team=row.get('team_abbr', ''),
            player_position=row.get('position', ''),
            secondary_entity=row.get('second_player_name', ''),
            secondary_team=row.get('second_team_abbr', ''),
            image_url=row.get('image_url', ''),
            local_image=row.get('local_image', ''),
            times_served=row.get('times_served', 0),
            last_served_game=row.get('last_served_game', '')
        )
        
        # Extract metadata
        insight.terms_of_art = self.extract_terms_of_art(full_text)
        insight.teams_mentioned = self.extract_teams(full_text)
        insight.topics = self.extract_topics(full_text, insight.terms_of_art)
        
        # Generate retrieval keys
        insight.retrieval_keys = self.generate_retrieval_keys(insight)
        
        # Generate LLM summary
        insight.llm_summary = self.generate_llm_summary(insight)
        
        return insight
    
    def process_game(self, game_id: str) -> List[ProcessedInsight]:
        """Process all insights for a specific game."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM insights WHERE game_id = ?
        ''', (game_id,))
        
        insights = []
        for row in cursor.fetchall():
            insight = self.process_insight(dict(row))
            insights.append(insight)
        
        conn.close()
        return insights
    
    def process_week(self, week: int) -> Dict[str, List[ProcessedInsight]]:
        """Process all insights for a week, grouped by game."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM insights WHERE week = ?
        ''', (week,))
        
        by_game: Dict[str, List[ProcessedInsight]] = defaultdict(list)
        
        for row in cursor.fetchall():
            insight = self.process_insight(dict(row))
            by_game[insight.game_id].append(insight)
        
        conn.close()
        return dict(by_game)
    
    def build_index(self, insights: List[ProcessedInsight]) -> Dict[str, List[str]]:
        """Build a retrieval index from processed insights."""
        index: Dict[str, List[str]] = defaultdict(list)
        
        for insight in insights:
            for key in insight.retrieval_keys:
                if insight.id not in index[key]:
                    index[key].append(insight.id)
        
        return dict(index)
    
    def save_processed_week(self, week: int, by_game: Dict[str, List[ProcessedInsight]]):
        """Save processed insights for a week."""
        output_file = self.output_path / f"week_{week}_processed.json"
        
        all_insights = []
        for game_id, insights in by_game.items():
            all_insights.extend(insights)
        
        # Build index
        index = self.build_index(all_insights)
        
        output = {
            'week': week,
            'season': self.season,
            'processed_at': datetime.now().isoformat(),
            'total_insights': len(all_insights),
            'games': len(by_game),
            'index': index,
            'insights': [i.to_dict() for i in all_insights]
        }
        
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        logger.info(f"Saved {len(all_insights)} processed insights for Week {week}")
        return output_file
    
    def save_game_insights(self, game_id: str, insights: List[ProcessedInsight]):
        """Save processed insights for a single game."""
        output_file = self.output_path / f"game_{game_id[:8]}_processed.json"
        
        index = self.build_index(insights)
        
        output = {
            'game_id': game_id,
            'season': self.season,
            'processed_at': datetime.now().isoformat(),
            'total_insights': len(insights),
            'index': index,
            'insights': [i.to_dict() for i in insights]
        }
        
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        return output_file
    
    def get_stats(self) -> Dict[str, Any]:
        """Get preprocessing statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM insights')
        total = cursor.fetchone()[0]
        
        cursor.execute('SELECT week, COUNT(*) FROM insights GROUP BY week ORDER BY week')
        by_week = {row[0]: row[1] for row in cursor.fetchall()}
        
        cursor.execute('SELECT COUNT(DISTINCT game_id) FROM insights')
        games = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_insights': total,
            'games': games,
            'by_week': by_week
        }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='NFL Pro Insight Pre-processor')
    parser.add_argument('--season', type=int, default=2025, help='Season year')
    parser.add_argument('--week', type=int, help='Process specific week')
    parser.add_argument('--all', action='store_true', help='Process all weeks')
    parser.add_argument('--game', type=str, help='Process specific game UUID')
    parser.add_argument('--stats', action='store_true', help='Show statistics only')
    
    args = parser.parse_args()
    
    preprocessor = InsightPreprocessor(season=args.season)
    
    if args.stats:
        stats = preprocessor.get_stats()
        print(f"\n{'='*50}")
        print(f"Insight Database Statistics (Season {args.season})")
        print(f"{'='*50}")
        print(f"Total insights: {stats['total_insights']}")
        print(f"Total games: {stats['games']}")
        print(f"\nBy week:")
        for week, count in sorted(stats['by_week'].items()):
            print(f"  Week {week}: {count} insights")
        return
    
    if args.game:
        print(f"Processing game {args.game}...")
        insights = preprocessor.process_game(args.game)
        output = preprocessor.save_game_insights(args.game, insights)
        print(f"✓ Saved {len(insights)} insights to {output}")
        
        # Show sample
        if insights:
            sample = insights[0]
            print(f"\nSample insight:")
            print(f"  Player: {sample.player_name} ({sample.player_team})")
            print(f"  Title: {sample.title[:80]}...")
            print(f"  Terms: {', '.join(sample.terms_of_art)}")
            print(f"  Topics: {', '.join(sample.topics)}")
            print(f"  Keys: {len(sample.retrieval_keys)} retrieval keys")
        return
    
    if args.week:
        print(f"Processing Week {args.week}...")
        by_game = preprocessor.process_week(args.week)
        output = preprocessor.save_processed_week(args.week, by_game)
        
        total = sum(len(insights) for insights in by_game.values())
        print(f"✓ Processed {total} insights across {len(by_game)} games")
        print(f"  Saved to: {output}")
        return
    
    if args.all:
        stats = preprocessor.get_stats()
        weeks = sorted(stats['by_week'].keys())
        
        print(f"Processing all {len(weeks)} weeks...")
        for week in weeks:
            by_game = preprocessor.process_week(week)
            preprocessor.save_processed_week(week, by_game)
            total = sum(len(insights) for insights in by_game.values())
            print(f"  Week {week}: {total} insights, {len(by_game)} games")
        
        print(f"\n✓ All weeks processed!")
        return
    
    parser.print_help()


if __name__ == '__main__':
    main()

