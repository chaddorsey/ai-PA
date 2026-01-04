"""
Test the Full Integration: NFL Pro Insights → Insight Engine

This test simulates:
1. Loading insights for a game (like at game start)
2. Processing play events 
3. Triggering player-specific insights
4. Generating break-time insights
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Any
from unittest.mock import Mock, patch

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'insight-engine'))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import components
from scrapers.insight_parser import InsightParser
from models.insight_schema import InsightIndex

# Path to test data
INSIGHT_FILE = Path(__file__).parent.parent / "nfl_pro_data_f979d7ee_20260104_000445.json"


def convert_insight_format(raw_insight: Dict) -> Dict:
    """Convert NFL Pro API format to parser format."""
    return {
        'id': raw_insight.get('insight_id', ''),
        'title': raw_insight.get('title', ''),
        'subNote1': raw_insight.get('sub_note', ''),
        'subNote2': raw_insight.get('sub_note2', ''),
        'playerName': raw_insight.get('player_name', ''),
        'position1': raw_insight.get('position', ''),
        'teamAbbr': raw_insight.get('team_abbr', ''),
        'playerName2': raw_insight.get('second_player_name', ''),
        'position2': raw_insight.get('second_position', ''),
        'teamAbbr2': raw_insight.get('second_team_abbr', ''),
    }


def load_test_insights() -> InsightIndex:
    """Load and parse test insights."""
    with open(INSIGHT_FILE, 'r') as f:
        data = json.load(f)
    
    raw_insights = data.get('insights', [])
    parser_format = [convert_insight_format(i) for i in raw_insights]
    
    parser = InsightParser()
    return parser.parse_batch(parser_format)


def test_insight_loading_integration():
    """Test that the nfl_pro_integration module loads insights correctly."""
    print("\n" + "="*60)
    print("TEST 1: nfl_pro_integration Loading")
    print("="*60)
    
    try:
        from nfl_pro_integration import (
            nfl_pro_narratives,
            load_narrative_insights,
        )
        
        # Load raw insights
        with open(INSIGHT_FILE, 'r') as f:
            data = json.load(f)
        
        raw_insights = data.get('insights', [])
        parser_format = [convert_insight_format(i) for i in raw_insights]
        
        # Load into the narrative system
        success = load_narrative_insights(
            game_uuid='f979d7ee-311e-11f0-b670-ae1250fadad1',
            home_team='SF',
            away_team='SEA',
            insights_data=parser_format
        )
        
        print(f"✓ Load success: {success}")
        
        stats = nfl_pro_narratives.get_stats()
        print(f"  Total insights: {stats.get('total', 0)}")
        print(f"  Players indexed: {stats.get('players_indexed', 0)}")
        print(f"  Matchup insights: {stats.get('matchup_insights', 0)}")
        
        return True
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
        print("  Make sure you're running from the right directory")
        return False


def test_player_triggered_insights():
    """Test player-triggered insight retrieval."""
    print("\n" + "="*60)
    print("TEST 2: Player-Triggered Insights")
    print("="*60)
    
    try:
        from nfl_pro_integration import get_player_triggered_insight
        
        test_cases = [
            ('Smith-Njigba', 1, None),
            ('Purdy', 2, 'red zone'),
            ('Darnold', 3, '3rd down'),
            ('Walker', 1, None),
        ]
        
        for player, quarter, situation in test_cases:
            insight = get_player_triggered_insight(player, quarter, situation)
            
            if insight:
                print(f"\n✓ {player} (Q{quarter}, {situation or 'normal'}):")
                print(f"   Headline: {insight['headline'][:50]}...")
                print(f"   Priority: {insight['priority']}")
            else:
                print(f"\n  {player}: No insight available")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_break_insights():
    """Test break-time insight retrieval."""
    print("\n" + "="*60)
    print("TEST 3: Break-Time Insights")
    print("="*60)
    
    try:
        from nfl_pro_integration import get_break_narrative_insights
        
        # Test commercial break
        print("\n--- Commercial Break (Q1) ---")
        commercial_insights = get_break_narrative_insights('commercial', 1, 2)
        for ins in commercial_insights:
            print(f"  • {ins['headline'][:50]}...")
        
        # Test halftime
        print("\n--- Halftime ---")
        halftime_insights = get_break_narrative_insights('halftime', 2, 4)
        for ins in halftime_insights:
            print(f"  • {ins['headline'][:50]}...")
            if ins.get('is_extended'):
                print(f"    (Extended insight available)")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_pregame_insights():
    """Test pregame insight sequence."""
    print("\n" + "="*60)
    print("TEST 4: Pregame Insight Sequence")
    print("="*60)
    
    try:
        from nfl_pro_integration import get_pregame_narrative_insights
        
        pregame = get_pregame_narrative_insights(count=5)
        print(f"\n✓ Generated {len(pregame)} pregame insights:")
        
        for i, ins in enumerate(pregame, 1):
            print(f"  [{i}] {ins['headline'][:45]}...")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_llm_context():
    """Test LLM context generation."""
    print("\n" + "="*60)
    print("TEST 5: LLM Context Generation")
    print("="*60)
    
    try:
        from nfl_pro_integration import get_narrative_llm_context
        
        context = get_narrative_llm_context(
            player='Brock Purdy',
            team='SF',
            situation='passing'
        )
        
        if context:
            print(f"\n✓ Context generated ({len(context)} chars):")
            print(context[:400] + "...")
        else:
            print("  (No context available)")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_usage_persistence():
    """Test that usage tracking works across sessions."""
    print("\n" + "="*60)
    print("TEST 6: Usage Persistence")
    print("="*60)
    
    try:
        from nfl_pro_integration import nfl_pro_narratives
        
        stats = nfl_pro_narratives.get_stats()
        total = stats.get('total', 0)
        unused = stats.get('unused_this_game', 0)
        used = stats.get('used_this_game', 0)
        
        print(f"\n✓ Usage stats for current game:")
        print(f"   Total: {total}")
        print(f"   Unused: {unused}")
        print(f"   Used: {used}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_simulated_play_sequence():
    """Simulate a sequence of plays and check insight generation."""
    print("\n" + "="*60)
    print("TEST 7: Simulated Play Sequence")
    print("="*60)
    
    try:
        from nfl_pro_integration import (
            get_player_triggered_insight,
            nfl_pro_narratives
        )
        import re
        
        # Sample plays from a real game
        plays = [
            "(15:00 - 1st) G.Smith pass short middle to J.Smith-Njigba for 8 yards",
            "(14:23 - 1st) K.Walker run right guard for 4 yards, FIRST DOWN",
            "(13:45 - 1st) G.Smith pass deep left to D.Metcalf for 35 yards",
            "(12:30 - 1st) B.Purdy pass short right to D.Samuel for 12 yards",
            "(11:55 - 1st) J.Mason run middle for 45 yards TOUCHDOWN",
        ]
        
        insights_generated = 0
        
        for i, play in enumerate(plays):
            # Extract player
            player_match = re.search(r'([A-Z]\.[A-Za-z\-]+)', play)
            if not player_match:
                continue
            
            player = player_match.group(1)
            
            # Check if big play
            yards_match = re.search(r'for (\d+) yard', play)
            yards = int(yards_match.group(1)) if yards_match else 0
            is_big = yards >= 20 or 'TOUCHDOWN' in play
            
            print(f"\n[Play {i+1}] {play[:60]}...")
            print(f"   Player: {player}, Yards: {yards}, Big: {is_big}")
            
            if is_big:
                insight = get_player_triggered_insight(player, quarter=1)
                if insight:
                    print(f"   ✓ INSIGHT: {insight['headline'][:40]}...")
                    insights_generated += 1
                else:
                    print(f"   (No insight triggered)")
        
        print(f"\n--- Summary ---")
        print(f"  Plays processed: {len(plays)}")
        print(f"  Insights generated: {insights_generated}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all integration tests."""
    print("\n" + "#"*60)
    print("# NFL PRO → INSIGHT ENGINE INTEGRATION TESTS")
    print("# Game: SEA @ SF (Week 18)")
    print("#"*60)
    
    # First load insights into the system
    if not test_insight_loading_integration():
        print("\n⛔ Cannot continue without loading insights")
        return
    
    # Run component tests
    test_player_triggered_insights()
    test_break_insights()
    test_pregame_insights()
    test_llm_context()
    test_usage_persistence()
    test_simulated_play_sequence()
    
    print("\n" + "#"*60)
    print("# ALL INTEGRATION TESTS COMPLETE")
    print("#"*60 + "\n")


if __name__ == '__main__':
    main()

