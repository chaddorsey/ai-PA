"""
Integration Test: NFL Pro Insights with Play-by-Play Data

Tests the full flow:
1. Load insights from saved data
2. Parse and index them
3. Simulate plays from the database
4. Trigger insights based on plays
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Any

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'insight-engine'))

import sqlite3

from models.insight_schema import InsightIndex
from scrapers.insight_parser import InsightParser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
DATA_PATH = Path(__file__).parent.parent
INSIGHT_FILE = DATA_PATH / "nfl_pro_data_f979d7ee_20260104_000445.json"
PLAYS_DB = DATA_PATH.parent / "data" / "nfl_plays_2024.db"


def load_insights_data() -> Dict[str, Any]:
    """Load the saved insights data."""
    with open(INSIGHT_FILE, 'r') as f:
        return json.load(f)


def convert_insight_format(raw_insight: Dict) -> Dict:
    """Convert NFL Pro API format to parser format."""
    return {
        'id': raw_insight.get('insight_id', ''),
        'title': raw_insight.get('title', ''),
        'subNote1': raw_insight.get('sub_note', ''),  # Primary text
        'subNote2': raw_insight.get('sub_note2', ''),  # Secondary text (may be empty)
        'playerName': raw_insight.get('player_name', ''),
        'position1': raw_insight.get('position', ''),
        'teamAbbr': raw_insight.get('team_abbr', ''),
        'playerName2': raw_insight.get('second_player_name', ''),
        'position2': raw_insight.get('second_position', ''),
        'teamAbbr2': raw_insight.get('second_team_abbr', ''),
    }


def get_sample_plays_from_db(game_team: str, limit: int = 10) -> List[Dict]:
    """Get sample plays from the database."""
    if not PLAYS_DB.exists():
        logger.warning(f"Plays database not found: {PLAYS_DB}")
        return []
    
    conn = sqlite3.connect(PLAYS_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get plays with interesting characteristics
    cursor.execute('''
        SELECT * FROM plays 
        WHERE possession_team IS NOT NULL
          AND play_type IN ('pass', 'rush')
          AND play_description NOT LIKE '%penalty%'
        ORDER BY RANDOM()
        LIMIT ?
    ''', (limit,))
    
    plays = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return plays


def test_insight_loading():
    """Test loading and parsing insights."""
    print("\n" + "="*60)
    print("TEST 1: Load and Parse Insights")
    print("="*60)
    
    # Load raw data
    data = load_insights_data()
    raw_insights = data.get('insights', [])
    print(f"Loaded {len(raw_insights)} raw insights from file")
    
    # Convert to parser format
    parser_format = [convert_insight_format(i) for i in raw_insights]
    
    # Parse
    parser = InsightParser()
    index = parser.parse_batch(parser_format)
    
    print(f"\n✓ Parsed {len(index.all_insights)} insights")
    print(f"  Players: {list(index.by_player.keys())[:8]}...")
    print(f"  Teams: {list(index.by_team.keys())}")
    print(f"  Categories: {list(index.by_category.keys())}")
    print(f"  Matchups: {len(index.matchup_insights)}")
    
    return index


def test_player_triggered_insights(index: InsightIndex):
    """Test retrieving insights when a player makes a play."""
    print("\n" + "="*60)
    print("TEST 2: Player-Triggered Insights")
    print("="*60)
    
    # Test players from SEA @ SF
    test_players = [
        'Jaxon Smith-Njigba',
        'Geno Smith',
        'Brock Purdy',
        'Deebo Samuel',
        'Kenneth Walker',
    ]
    
    game_id = "test_game_001"
    
    for player_name in test_players:
        # Try both full name and last name
        for name in [player_name, player_name.split()[-1]]:
            insights = index.get_for_player(name, unused_only=True)
            unused = [i for i in insights if not i.was_used_in_game(game_id)]
            
            if unused:
                insight = unused[0]
                print(f"\n--- {player_name} ---")
                print(f"  Title: {insight.title[:60]}...")
                print(f"  Priority: {insight.significance}")
                print(f"  Categories: {[c.value for c in insight.categories]}")
                
                # Mark as used
                insight.record_usage(game_id, quarter=2)
                break


def test_play_simulation(index: InsightIndex):
    """Simulate plays and check for triggered insights."""
    print("\n" + "="*60)
    print("TEST 3: Play Simulation")
    print("="*60)
    
    # Sample plays with player names
    sample_plays = [
        {
            'play_description': '(10:23 - 1st) G.Smith pass short left to J.Smith-Njigba for 12 yards',
            'play_type': 'pass',
            'possession_team': 'SEA',
            'down': 2,
            'yards_to_go': 7,
            'quarter': 1,
        },
        {
            'play_description': '(5:45 - 2nd) K.Walker run right guard for 8 yards',
            'play_type': 'rush',
            'possession_team': 'SEA',
            'down': 1,
            'yards_to_go': 10,
            'quarter': 2,
        },
        {
            'play_description': '(2:00 - 3rd) B.Purdy pass deep right to D.Samuel for 45 yards TOUCHDOWN',
            'play_type': 'pass',
            'possession_team': 'SF',
            'down': 1,
            'yards_to_go': 10,
            'quarter': 3,
            'is_scoring': True,
        },
    ]
    
    game_id = "simulation_game_001"
    
    for i, play in enumerate(sample_plays):
        print(f"\n--- Play {i+1} ---")
        print(f"  {play['play_description'][:70]}...")
        
        # Extract player name from description
        import re
        player_match = re.search(r'([A-Z]\.[A-Za-z\-]+)', play['play_description'])
        if player_match:
            player_abbr = player_match.group(1)
            print(f"  Player detected: {player_abbr}")
            
            # Check for insight
            insights = index.get_for_player(player_abbr, unused_only=False)
            available = [ins for ins in insights if not ins.was_used_in_game(game_id)]
            
            if available:
                insight = available[0]
                print(f"  ✓ INSIGHT AVAILABLE: {insight.title[:50]}...")
                print(f"    Significance: {insight.significance}")
                
                # Mark used
                insight.record_usage(game_id, quarter=play.get('quarter', 1))
            else:
                print(f"  (No unused insight for this player)")


def test_break_insights(index: InsightIndex):
    """Test getting insights during breaks."""
    print("\n" + "="*60)
    print("TEST 4: Break-Time Insights")
    print("="*60)
    
    game_id = "break_test_game_001"
    
    # Simulate a commercial break
    print("\n--- Commercial Break (Q2) ---")
    break_insights = index.get_for_break(quarter=2, teams=['SEA', 'SF'])
    
    for i, insight in enumerate(break_insights[:3]):
        if not insight.was_used_in_game(game_id):
            print(f"\n  [{i+1}] {insight.title[:50]}...")
            print(f"      Primary: {insight.primary_text[:80]}...")
            if insight.secondary_text:
                print(f"      Extended: {insight.secondary_text[:60]}...")
            
            insight.record_usage(game_id, quarter=2)


def test_matchup_insights(index: InsightIndex):
    """Test getting matchup-specific insights."""
    print("\n" + "="*60)
    print("TEST 5: Matchup Insights")
    print("="*60)
    
    matchups = index.get_matchup_insights('SEA', 'SF')
    print(f"\nFound {len(matchups)} SEA vs SF matchup insights:")
    
    for insight in matchups[:3]:
        print(f"\n  Title: {insight.title[:60]}...")
        print(f"  Dual-team: {insight.is_dual_team}")
        print(f"  Entities: {[e.name for e in insight.entities]}")


def test_llm_context(index: InsightIndex):
    """Test LLM context generation."""
    print("\n" + "="*60)
    print("TEST 6: LLM Context Bundle")
    print("="*60)
    
    context = index.get_llm_context_bundle(
        player='Geno Smith',
        team='SEA',
        situation='passing'
    )
    
    print(f"\n--- Context for Geno Smith (passing situation) ---")
    print(context[:500] if context else "(No context available)")


def test_usage_tracking(index: InsightIndex):
    """Test cross-game usage tracking."""
    print("\n" + "="*60)
    print("TEST 7: Usage Tracking")
    print("="*60)
    
    game1 = "game_week18_001"
    game2 = "game_week19_001"
    
    # Get an insight and use it
    insight = index.all_insights[0]
    original_history_len = len(insight.usage_history)
    
    print(f"\n--- Initial state ---")
    print(f"  Insight: {insight.title[:40]}...")
    print(f"  Usage history: {original_history_len} entries")
    
    # Use in game 1
    insight.record_usage(game1, quarter=1, game_date="2025-01-04")
    
    print(f"\n--- After using in Game 1 ---")
    print(f"  was_used_in_game(game1): {insight.was_used_in_game(game1)}")
    print(f"  was_used_in_game(game2): {insight.was_used_in_game(game2)}")
    print(f"  games_used_in: {insight.get_games_used_in()}")
    
    # Check availability for game 2
    available_g2 = index.get_available_for_game(game2, allow_past_game_repeats=True)
    no_repeat_g2 = index.get_available_for_game(game2, allow_past_game_repeats=False)
    
    print(f"\n--- Availability for Game 2 ---")
    print(f"  With repeats allowed: {len(available_g2)}")
    print(f"  Without repeats: {len(no_repeat_g2)}")


def main():
    """Run all integration tests."""
    print("\n" + "#"*60)
    print("# NFL PRO INSIGHT INTEGRATION TESTS")
    print("# Game: SEA @ SF (Week 18)")
    print("#"*60)
    
    # Load and parse insights
    index = test_insight_loading()
    
    # Test various retrieval methods
    test_player_triggered_insights(index)
    test_play_simulation(index)
    test_break_insights(index)
    test_matchup_insights(index)
    test_llm_context(index)
    test_usage_tracking(index)
    
    print("\n" + "#"*60)
    print("# ALL INTEGRATION TESTS COMPLETE")
    print("#"*60 + "\n")


if __name__ == '__main__':
    main()

