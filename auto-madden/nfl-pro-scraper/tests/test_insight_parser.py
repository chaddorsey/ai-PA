"""
Test the Insight Parser and Index with real or sample data.

Tests:
1. Parsing raw insights into structured format
2. Index retrieval by player, team, situation
3. Cross-game usage tracking
4. LLM context generation
"""

import sys
import os
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.insight_schema import (
    NFLProInsight,
    InsightIndex,
    InsightTiming,
    InsightCategory,
)
from scrapers.insight_parser import InsightParser, load_game_insights
from scrapers.nfl_pro_api import NFLProAPIClient, InsightData

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sample insights for testing without API
SAMPLE_INSIGHTS = [
    {
        'id': 'ins_001',
        'title': 'Darnold Precision',
        'subNote1': 'Sam Darnold has completed 68.4% of his passes this season, ranking 5th among qualified quarterbacks.',
        'subNote2': 'Darnold has thrown for 2,456 yards and 18 touchdowns in 2024, with only 4 interceptions. His passer rating of 105.2 is a career high.',
        'playerName': 'Sam Darnold',
        'teamAbbr': 'MIN',
        'position1': 'QB',
    },
    {
        'id': 'ins_002',
        'title': 'QB Showdown',
        'subNote1': 'This matchup features two of the top 5 passers in the NFC. Sam Darnold vs. Brock Purdy have a combined 34 TDs this season.',
        'subNote2': 'The last time these quarterbacks faced off, the game went to overtime with a combined 856 passing yards.',
        'playerName': 'Sam Darnold',
        'teamAbbr': 'MIN',
        'playerName2': 'Brock Purdy',
        'teamAbbr2': 'SF',
    },
    {
        'id': 'ins_003',
        'title': 'Red Zone Specialist',
        'subNote1': 'Justin Jefferson leads the league in red zone targets with 24 this season, converting 14 of them into touchdowns.',
        'subNote2': 'Jefferson\'s 58.3% red zone TD rate is the highest in the NFL among receivers with at least 20 targets.',
        'playerName': 'Justin Jefferson',
        'teamAbbr': 'MIN',
        'position1': 'WR',
    },
    {
        'id': 'ins_004',
        'title': 'Defensive Dominance',
        'subNote1': 'The 49ers defense has allowed just 17.2 points per game, ranking 3rd in the NFL.',
        'subNote2': 'San Francisco\'s pass rush has generated 38 sacks this season, with Nick Bosa leading the way with 11.5.',
        'playerName': '',
        'teamAbbr': 'SF',
    },
    {
        'id': 'ins_005',
        'title': 'Third Down Excellence',
        'subNote1': 'Minnesota converts 47.8% of third downs, the second-best rate in the league. They are particularly dangerous on 3rd and medium.',
        'subNote2': 'Darnold has a 112.4 passer rating on third down, completing 72.3% of his passes when the chains are on the line.',
        'playerName': 'Sam Darnold',
        'teamAbbr': 'MIN',
    },
    {
        'id': 'ins_006',
        'title': 'Bosa vs. The Pocket',
        'subNote1': 'Nick Bosa has registered pressure on 22.4% of his pass rush snaps, the highest rate among edge rushers with 200+ snaps.',
        'subNote2': 'When Bosa generates pressure, opposing QBs have a passer rating of just 52.3.',
        'playerName': 'Nick Bosa',
        'teamAbbr': 'SF',
        'position1': 'DE',
    },
]


def test_basic_parsing():
    """Test parsing individual insights."""
    print("\n" + "="*60)
    print("TEST 1: Basic Parsing")
    print("="*60)
    
    parser = InsightParser()
    
    for raw in SAMPLE_INSIGHTS:
        insight = parser.parse_raw_insight(raw)
        if insight:
            print(f"\n✓ Parsed: {insight.title}")
            print(f"  Entities: {[e.name for e in insight.entities]}")
            print(f"  Teams: {insight.teams}")
            print(f"  Categories: {[c.value for c in insight.categories]}")
            print(f"  Situations: {insight.situation_triggers}")
            print(f"  Facts: {len(insight.facts)}")
            print(f"  Significance: {insight.significance}/10")
            print(f"  Timing: {insight.timing.value}")
        else:
            print(f"✗ Failed to parse: {raw.get('title')}")
    
    return True


def test_index_creation():
    """Test batch parsing and index creation."""
    print("\n" + "="*60)
    print("TEST 2: Index Creation")
    print("="*60)
    
    parser = InsightParser()
    index = parser.parse_batch(SAMPLE_INSIGHTS)
    
    print(f"\n✓ Index created with {len(index.all_insights)} insights")
    print(f"  Players indexed: {list(index.by_player.keys())}")
    print(f"  Teams indexed: {list(index.by_team.keys())}")
    print(f"  Categories: {list(index.by_category.keys())}")
    print(f"  Situations: {list(index.by_situation.keys())}")
    print(f"  Matchup insights: {len(index.matchup_insights)}")
    
    return index


def test_retrieval(index: InsightIndex):
    """Test retrieving insights by various criteria."""
    print("\n" + "="*60)
    print("TEST 3: Retrieval")
    print("="*60)
    
    # By player
    print("\n--- By Player: 'Darnold' ---")
    player_insights = index.get_for_player('Darnold')
    for i in player_insights:
        print(f"  • {i.title}")
    
    # By player variant
    print("\n--- By Player Variant: 'S. Darnold' ---")
    variant_insights = index.get_for_player('S. Darnold')
    for i in variant_insights:
        print(f"  • {i.title}")
    
    # By team
    print("\n--- By Team: 'SF' ---")
    team_insights = index.get_for_team('SF')
    for i in team_insights:
        print(f"  • {i.title}")
    
    # By situation
    print("\n--- By Situation: 'red zone' ---")
    situation_insights = index.get_for_situation('red zone')
    for i in situation_insights:
        print(f"  • {i.title}")
    
    # For break
    print("\n--- For Break (Q2 = halftime) ---")
    break_insights = index.get_for_break(2, teams=['MIN', 'SF'])
    for i in break_insights[:3]:
        print(f"  • {i.title} (sig: {i.significance})")
    
    # Matchups
    print("\n--- Matchup Insights (MIN vs SF) ---")
    matchup = index.get_matchup_insights('MIN', 'SF')
    for i in matchup:
        print(f"  • {i.title}")


def test_usage_tracking(index: InsightIndex):
    """Test cross-game usage tracking."""
    print("\n" + "="*60)
    print("TEST 4: Usage Tracking")
    print("="*60)
    
    game1_id = "game_2024_MIN_SF_001"
    game2_id = "game_2024_MIN_GB_002"
    
    # Mark first insight as used in game 1
    insight = index.all_insights[0]
    print(f"\n--- Marking '{insight.title}' as used in Game 1 ---")
    index.mark_used(insight.id, quarter=2, game_id=game1_id, game_date="2024-12-15")
    
    print(f"  times_used: {insight.times_used}")
    print(f"  was_used_in_game(game1): {insight.was_used_in_game(game1_id)}")
    print(f"  was_used_in_game(game2): {insight.was_used_in_game(game2_id)}")
    print(f"  games_used_in: {insight.get_games_used_in()}")
    
    # Test get_unused_for_game
    print(f"\n--- Unused for Game 1 ---")
    unused_g1 = index.get_unused_for_game(game1_id)
    print(f"  {len(unused_g1)} of {len(index.all_insights)} insights unused")
    
    print(f"\n--- Unused for Game 2 (new game) ---")
    unused_g2 = index.get_unused_for_game(game2_id)
    print(f"  {len(unused_g2)} of {len(index.all_insights)} insights unused")
    
    # Test get_available_for_game
    print(f"\n--- Available for Game 1 (allow_past_game_repeats=True) ---")
    avail_g1 = index.get_available_for_game(game1_id, allow_past_game_repeats=True)
    print(f"  {len(avail_g1)} available")
    
    print(f"\n--- Available for Game 2 (allow_past_game_repeats=True) ---")
    avail_g2_repeat = index.get_available_for_game(game2_id, allow_past_game_repeats=True)
    print(f"  {len(avail_g2_repeat)} available (includes repeat from game 1)")
    
    print(f"\n--- Available for Game 2 (allow_past_game_repeats=False) ---")
    avail_g2_no_repeat = index.get_available_for_game(game2_id, allow_past_game_repeats=False)
    print(f"  {len(avail_g2_no_repeat)} available (excludes insights used anywhere)")


def test_llm_context(index: InsightIndex):
    """Test LLM context bundle generation."""
    print("\n" + "="*60)
    print("TEST 5: LLM Context Bundle")
    print("="*60)
    
    # Get context for a specific player in a situation
    context = index.get_llm_context_bundle(
        player='Darnold',
        team='MIN',
        situation='3rd down'
    )
    
    print(f"\n--- Context for Darnold on 3rd down ---")
    print(context)


def test_serialization(index: InsightIndex):
    """Test saving and loading index."""
    print("\n" + "="*60)
    print("TEST 6: Serialization")
    print("="*60)
    
    # Serialize
    json_str = index.to_json()
    
    # Deserialize
    loaded_index = InsightIndex.from_json(json_str)
    
    print(f"\n✓ Serialized and loaded {len(loaded_index.all_insights)} insights")
    print(f"  Players: {len(loaded_index.by_player)}")
    print(f"  Teams: {len(loaded_index.by_team)}")
    
    # Verify usage history persisted
    if index.all_insights[0].usage_history:
        orig_history = index.all_insights[0].usage_history
        loaded_history = loaded_index.all_insights[0].usage_history
        print(f"\n  Usage history preserved: {orig_history == loaded_history}")
    
    # Save to file
    output_dir = Path(__file__).parent.parent / 'data'
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / 'sample_insights_index.json'
    
    with open(output_file, 'w') as f:
        f.write(json_str)
    print(f"\n  Saved to: {output_file}")


async def test_with_live_api(game_uuid: str):
    """Test with real NFL Pro API data."""
    print("\n" + "="*60)
    print("TEST 7: Live API Integration")
    print("="*60)
    
    try:
        async with NFLProAPIClient(headless=True) as client:
            print(f"\n--- Fetching insights for game: {game_uuid} ---")
            insights_raw = await client.get_insights(game_uuid, wait_time=10)
            
            if not insights_raw:
                print("✗ No insights returned from API")
                return None
            
            print(f"✓ Received {len(insights_raw)} insights from API")
            
            # Convert to parser format and parse
            parser = InsightParser()
            raw_for_parser = [i.to_parser_format() for i in insights_raw]
            index = parser.parse_batch(raw_for_parser)
            
            print(f"\n--- Parsed Results ---")
            print(f"  Total insights: {len(index.all_insights)}")
            print(f"  Players: {list(index.by_player.keys())[:10]}...")
            print(f"  Teams: {list(index.by_team.keys())}")
            
            # Save the raw data for reference
            output_dir = Path(__file__).parent.parent / 'data'
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / f'insights_{game_uuid[:8]}_{datetime.now().strftime("%Y%m%d")}.json'
            
            with open(output_file, 'w') as f:
                json.dump({
                    'game_uuid': game_uuid,
                    'fetched_at': datetime.now().isoformat(),
                    'raw_insights': [i.to_dict() for i in insights_raw],
                    'parsed_index': json.loads(index.to_json()),
                }, f, indent=2)
            print(f"\n  Saved to: {output_file}")
            
            return index
            
    except FileNotFoundError as e:
        print(f"✗ No NFL Pro session: {e}")
        print("  Run: python session/nfl_pro_login.py")
        return None
    except Exception as e:
        print(f"✗ API error: {e}")
        return None


def main():
    """Run all tests."""
    print("\n" + "#"*60)
    print("# NFL PRO INSIGHT PARSER TESTS")
    print("#"*60)
    
    # Run offline tests with sample data
    test_basic_parsing()
    index = test_index_creation()
    test_retrieval(index)
    test_usage_tracking(index)
    test_llm_context(index)
    test_serialization(index)
    
    # Optional: test with live API
    if len(sys.argv) > 1:
        game_uuid = sys.argv[1]
        asyncio.run(test_with_live_api(game_uuid))
    else:
        print("\n" + "-"*60)
        print("To test with live API, run:")
        print("  python tests/test_insight_parser.py <game_uuid>")
        print("-"*60)
    
    print("\n" + "#"*60)
    print("# ALL TESTS COMPLETE")
    print("#"*60 + "\n")


if __name__ == '__main__':
    main()

