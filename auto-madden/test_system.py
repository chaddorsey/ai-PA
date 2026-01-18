#!/usr/bin/env python3
"""
Auto-Madden System Test

Quick verification that all components are working correctly.
Run before starting live game testing.

Usage:
    python3 test_system.py
    python3 test_system.py --verbose
"""

import json
import sys
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent / 'nfl-pro-scraper'))
sys.path.insert(0, str(Path(__file__).parent / 'insight-engine'))

DATA_PATH = Path(__file__).parent / 'data'


def test_insights_database():
    """Test that insights database exists and has data."""
    import sqlite3
    
    db_path = DATA_PATH / 'nfl_insights_2025.db'
    if not db_path.exists():
        return False, "Database not found"
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM insights')
    count = cursor.fetchone()[0]
    
    cursor.execute('SELECT week, COUNT(*) FROM insights GROUP BY week ORDER BY week DESC')
    by_week = dict(cursor.fetchall())
    conn.close()
    
    if count == 0:
        return False, "No insights in database"
    
    return True, f"{count} insights ({by_week})"


def test_processed_insights():
    """Test that processed insights files exist."""
    processed_dir = DATA_PATH / 'processed_insights'
    
    if not processed_dir.exists():
        return False, "Processed insights directory not found"
    
    files = list(processed_dir.glob('week_*_processed.json'))
    
    if not files:
        return False, "No processed insight files"
    
    weeks = []
    for f in files:
        try:
            with open(f) as fp:
                data = json.load(fp)
                weeks.append(f"W{data['week']}:{data['total_insights']}")
        except:
            pass
    
    return True, f"{len(files)} weeks ({', '.join(weeks)})"


def test_insight_loading():
    """Test that insights can be loaded and retrieved."""
    try:
        from nfl_pro_integration import load_narrative_insights, nfl_pro_narratives

        count = load_narrative_insights("test", week=18)
        if count == 0:
            return False, "No insights loaded for Week 18"

        # Test retrieval - must provide valid_teams (simulates real game scenario)
        # Using SEA vs SF which are in Week 18 data
        insight = nfl_pro_narratives.get_random_unserved_insight(valid_teams={'SEA', 'SF'})
        if not insight:
            return False, "Could not retrieve insight for SEA vs SF"

        return True, f"{count} insights loaded, retrieval working"
    except Exception as e:
        return False, f"Error: {e}"


def test_team_lookup():
    """Test that team-based lookups work."""
    try:
        from nfl_pro_integration import load_narrative_insights, nfl_pro_narratives
        
        load_narrative_insights("test", week=18)
        
        teams_found = 0
        for team in ['SEA', 'SF', 'KC', 'BUF', 'DET']:
            insight = nfl_pro_narratives.get_insight_by_team(team)
            if insight:
                teams_found += 1
        
        if teams_found == 0:
            return False, "No team lookups working"
        
        return True, f"{teams_found}/5 teams found"
    except Exception as e:
        return False, f"Error: {e}"


def test_nfl_pro_session():
    """Test NFL Pro session status."""
    session_file = Path(__file__).parent / 'credentials' / 'browser_states' / 'nfl_pro_state.json'
    
    if not session_file.exists():
        return False, "No session file - run nfl_pro_login.py"
    
    try:
        import requests
        with open(session_file) as f:
            state = json.load(f)
        
        cookies = {c['name']: c['value'] for c in state.get('cookies', []) if 'nfl.com' in c.get('domain', '')}
        
        if not cookies:
            return False, "No NFL cookies in session"
        
        # Quick test (don't actually call API, just check cookies exist)
        return True, f"{len(cookies)} cookies loaded (validity unknown until live test)"
    except Exception as e:
        return False, f"Error: {e}"


def main():
    verbose = '--verbose' in sys.argv
    
    print("=" * 60)
    print("Auto-Madden System Test")
    print("=" * 60)
    print()
    
    tests = [
        ("Insights Database", test_insights_database),
        ("Processed Insights", test_processed_insights),
        ("Insight Loading", test_insight_loading),
        ("Team Lookups", test_team_lookup),
        ("NFL Pro Session", test_nfl_pro_session),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            success, message = test_fn()
            status = "✅" if success else "❌"
            print(f"{status} {name}")
            if verbose or not success:
                print(f"   {message}")
            if success:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {name}")
            print(f"   Error: {e}")
            failed += 1
    
    print()
    print("-" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("\n🎉 All tests passed! System ready for live testing.")
        print("\nTo start:")
        print("  1. (Optional) Re-login to NFL Pro: python3 nfl-pro-scraper/session/nfl_pro_login.py")
        print("  2. Start services: ./start_companion.sh")
        print("  3. Open http://localhost:5130/simple")
    else:
        print("\n⚠️  Some tests failed. Check the errors above.")
    
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

