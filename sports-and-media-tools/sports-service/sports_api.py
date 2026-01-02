#!/usr/bin/env python3
"""
Sports API Service - Polls ESPN for live game schedules and provides REST endpoints
for Letta agents to query current/upcoming games and their broadcast information.

Adapted from the reference voice-tv-remote implementation for Letta agent integration.
"""

import json
import os
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any
from pathlib import Path
import threading

import requests
from flask import Flask, jsonify, request

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
CHANNEL_MAPPING_PATH = os.environ.get('CHANNEL_MAPPING_PATH', '/app/config/channel_mapping.json')
CACHE_PATH = os.environ.get('CACHE_PATH', '/app/data/sports_cache.json')
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', 900))  # 15 minutes default

# ESPN API endpoints
ESPN_ENDPOINTS = {
    'nfl': 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard',
    'nba': 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard',
    'mlb': 'https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard',
    'nhl': 'https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard',
    'ncaaf': 'https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard',
    'ncaab': 'https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard',
    'mls': 'https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard',
}

# Global cache
sports_cache: Dict[str, Any] = {
    'last_updated': None,
    'games': [],
    'by_team': {},
    'by_league': {}
}

channel_mapping: Dict[str, Any] = {}


def load_channel_mapping() -> None:
    """Load channel mapping from JSON file."""
    global channel_mapping
    try:
        with open(CHANNEL_MAPPING_PATH, 'r') as f:
            channel_mapping = json.load(f)
        logger.info(f"Loaded channel mapping from {CHANNEL_MAPPING_PATH}")
    except Exception as e:
        logger.error(f"Failed to load channel mapping: {e}")
        channel_mapping = {"networks": {}, "teams": {}, "roku_apps": {}}


def save_cache() -> None:
    """Save sports cache to disk."""
    try:
        # Ensure directory exists
        Path(CACHE_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, 'w') as f:
            json.dump(sports_cache, f, indent=2, default=str)
        logger.debug(f"Saved cache to {CACHE_PATH}")
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")


def load_cache() -> None:
    """Load sports cache from disk."""
    global sports_cache
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, 'r') as f:
                sports_cache = json.load(f)
            logger.info(f"Loaded cache from {CACHE_PATH}")
    except Exception as e:
        logger.error(f"Failed to load cache: {e}")


def parse_broadcast_info(broadcasts: List[Dict]) -> Dict[str, Any]:
    """
    Extract broadcast information from ESPN broadcast data.
    
    Returns dict with:
    - network: Primary broadcast network name
    - is_espn_plus_only: True if ONLY available on ESPN+ (streaming, no cable option)
    - has_cable_option: True if available on a cable channel
    - all_networks: List of all broadcast networks
    """
    result = {
        'network': None,
        'is_espn_plus_only': False,
        'has_cable_option': False,
        'all_networks': []
    }
    
    if not broadcasts:
        return result
    
    # Priority order for broadcast networks (cable channels first)
    priority_networks = [
        'CBS', 'FOX', 'NBC', 'ABC', 'ESPN', 'ESPN2', 'TNT', 'TBS',
        'NFL Network', 'NESN', 'NBC Sports Boston', 'FS1', 'MLB Network',
        'NBA TV', 'NHL Network', 'Peacock', 'Amazon Prime Video',
        'Apple TV+', 'Netflix', 'ESPN+'
    ]
    
    # Cable networks that we can access via FIOS (from channel lineup)
    # These are exact matches or patterns for networks available on cable
    cable_networks = {
        # Broadcast networks
        'cbs', 'fox', 'nbc', 'abc', 'the cw', 'cw', 'pbs',
        # ESPN family (cable channels, not ESPN+ streaming)
        'espnews', 'espnu',
        # Sports networks
        'tnt', 'tbs', 'usa', 'usa network',
        'nfl network', 'nfl net', 'nfln',
        'nba tv', 'nbatv',
        'nhl network', 'nhl net', 'nhln',
        'mlb network', 'mlbn', 'mlb net',
        'nesn', 'nesnplus', 'nesn+',
        'nbc sports boston', 'nbcsb', 'nbc sports bo',
        'fs1', 'fox sports 1', 'fs2', 'fox sports 2',
        'big ten network', 'btn', 'big ten',
        'acc network', 'accn', 'acc net',
        'sec network', 'sec net', 'sec network national',
        'cbs sports network', 'cbssn',
        'golf channel', 'tennis channel',
        'trutv', 'tru tv', 'truTV',
        # General entertainment with sports
        'fx', 'fxx', 'syfy', 'a&e', 'history',
        'freeform', 'cartoon network'
    }
    
    broadcast_names: List[str] = []
    has_espn_plus = False
    has_espn_cable = False  # ESPN or ESPN2 (not ESPN+)
    has_other_cable = False
    
    for broadcast in broadcasts:
        names = broadcast.get('names', [])
        for name in names:
            broadcast_names.append(name)
            name_lower = name.lower().strip()
            
            # Check for ESPN+ specifically (streaming only)
            if 'espn+' in name_lower or 'espn plus' in name_lower:
                has_espn_plus = True
                continue  # Don't also count this as cable ESPN
            
            # Check for cable ESPN (exact match for ESPN or ESPN2, not ESPN+)
            if name_lower == 'espn' or name_lower == 'espn2':
                has_espn_cable = True
                continue
            
            # Check for other cable options
            for cable_net in cable_networks:
                if cable_net == name_lower or (len(cable_net) > 3 and cable_net in name_lower):
                    has_other_cable = True
                    break
    
    result['all_networks'] = broadcast_names
    has_any_cable = has_espn_cable or has_other_cable
    result['has_cable_option'] = has_any_cable
    
    # Determine if ESPN+ only (streaming, no accessible cable option)
    # Note: Regional sports networks like MNMT, FanDuel SN, etc. are NOT 
    # universally available on FIOS, so we don't count them as "cable"
    if has_espn_plus and not has_any_cable:
        result['is_espn_plus_only'] = True
    
    # Find highest priority network for primary display
    for network in priority_networks:
        for name in broadcast_names:
            if network.lower() in name.lower():
                result['network'] = network
                break
        if result['network']:
            break
    
    # Fallback to first available
    if not result['network'] and broadcast_names:
        result['network'] = broadcast_names[0]
    
    return result


def get_channel_for_network(network: str) -> Optional[Dict]:
    """Look up channel number for a broadcast network."""
    if not network or 'networks' not in channel_mapping:
        return None
    
    networks = channel_mapping.get('networks', {})
    
    # Direct match
    if network in networks:
        return networks[network]
    
    # Case-insensitive search
    for net_name, net_info in networks.items():
        if net_name.lower() == network.lower():
            return net_info
        # Check aliases
        aliases = net_info.get('aliases', [])
        if network.lower() in [a.lower() for a in aliases]:
            return net_info
    
    return None


def fetch_espn_scoreboard(league: str) -> List[Dict]:
    """Fetch current scoreboard from ESPN API."""
    url = ESPN_ENDPOINTS.get(league)
    if not url:
        logger.warning(f"Unknown league: {league}")
        return []
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        games: List[Dict] = []
        events = data.get('events', [])
        
        for event in events:
            game_info = parse_event(event, league)
            if game_info:
                games.append(game_info)
        
        return games
    
    except Exception as e:
        logger.error(f"Failed to fetch {league} scoreboard: {e}")
        return []


def parse_event(event: Dict, league: str) -> Optional[Dict]:
    """Parse an ESPN event into our game format."""
    try:
        competition = event.get('competitions', [{}])[0]
        competitors = competition.get('competitors', [])
        
        if len(competitors) < 2:
            return None
        
        # Get teams
        home_team = None
        away_team = None
        for comp in competitors:
            # Extract record (win-loss) from records array
            record = None
            records = comp.get('records', [])
            for rec in records:
                if rec.get('type') == 'total':
                    record = rec.get('summary', '')
                    break
            
            # Extract ranking (only for college teams)
            ranking = None
            curated_rank = comp.get('curatedRank', {})
            if curated_rank.get('current'):
                ranking = curated_rank.get('current')
            
            team_info = {
                'id': comp.get('team', {}).get('id'),
                'name': comp.get('team', {}).get('displayName'),
                'abbreviation': comp.get('team', {}).get('abbreviation'),
                'score': comp.get('score', '0'),
                'is_home': comp.get('homeAway') == 'home',
                'record': record,
                'ranking': ranking
            }
            if team_info['is_home']:
                home_team = team_info
            else:
                away_team = team_info
        
        # Get status
        status = event.get('status', {})
        status_type = status.get('type', {})
        state = status_type.get('state', 'pre')  # pre, in, post
        status_detail = status_type.get('shortDetail', '')
        
        # Get broadcast info (now returns dict with ESPN+ detection)
        broadcasts = competition.get('broadcasts', [])
        broadcast_info = parse_broadcast_info(broadcasts)
        broadcast_network = broadcast_info['network']
        channel_info = get_channel_for_network(broadcast_network)
        
        # Get game time
        game_date = event.get('date')
        
        # Generate consistent short_name format: AWAY @ HOME
        if away_team and home_team:
            away_abbrev = away_team.get('abbreviation', '')
            home_abbrev = home_team.get('abbreviation', '')
            if away_abbrev and home_abbrev:
                short_name = f"{away_abbrev} @ {home_abbrev}"
            else:
                short_name = event.get('shortName', event.get('name', 'Unknown'))
        else:
            short_name = event.get('shortName', event.get('name', 'Unknown'))
        
        # Determine availability
        # ESPN+ is now available via streaming, so ESPN+ only games ARE accessible
        is_available = True
        unavailable_reason = None
        watch_method = None
        
        if broadcast_info['is_espn_plus_only']:
            # ESPN+ only - available via ESPN app
            watch_method = "streaming"
        elif channel_info:
            # Available on cable
            watch_method = "cable"
        elif broadcast_info['network'] and 'espn' in broadcast_info['network'].lower():
            # ESPN family network
            watch_method = "cable"
        else:
            # Check if it's a streaming-only service we have
            streaming_services_available = ['espn+', 'peacock', 'apple tv', 'amazon prime', 'netflix', 'hbo max', 'max', 'paramount+']
            network_lower = (broadcast_info['network'] or '').lower()
            if any(svc in network_lower for svc in streaming_services_available):
                watch_method = "streaming"
            elif not channel_info and broadcast_info['network']:
                # Unknown network without channel mapping - may not be available
                is_available = False
                unavailable_reason = f"No channel mapping for {broadcast_info['network']}"
        
        game = {
            'id': event.get('id'),
            'league': league,
            'name': event.get('name'),
            'short_name': short_name,
            'date': game_date,
            'state': state,
            'status_detail': status_detail,
            'home_team': home_team,
            'away_team': away_team,
            'broadcast_network': broadcast_network,
            'channel': channel_info.get('hd_channel') if channel_info else None,
            'channel_sd': channel_info.get('channel') if channel_info else None,
            'streaming_service': _get_streaming_service(broadcast_network),
            'is_available': is_available,
            'unavailable_reason': unavailable_reason,
            'watch_method': watch_method,  # "cable", "streaming", or None
            'is_espn_plus_only': broadcast_info['is_espn_plus_only'],
            'all_broadcast_networks': broadcast_info['all_networks'],
        }
        
        return game
    
    except Exception as e:
        logger.error(f"Failed to parse event: {e}")
        return None


def _get_streaming_service(network: Optional[str]) -> Optional[Dict]:
    """Check if network is a streaming service and return app info."""
    if not network:
        return None
    
    streaming_networks = {
        'ESPN+': 'espn',
        'Peacock': 'peacock',
        'Amazon Prime Video': 'prime',
        'Apple TV+': 'apple tv',
        'Netflix': 'netflix',
        'Paramount+': 'paramount',
    }
    
    for service_name, app_key in streaming_networks.items():
        if service_name.lower() in network.lower():
            roku_apps = channel_mapping.get('roku_apps', {})
            if app_key in roku_apps:
                return {
                    'service': service_name,
                    'roku_app_id': roku_apps[app_key].get('app_id'),
                    'app_key': app_key
                }
    
    return None


def update_sports_cache() -> None:
    """Fetch all sports data and update cache."""
    global sports_cache
    
    logger.info("Updating sports cache...")
    all_games: List[Dict] = []
    
    for league in ESPN_ENDPOINTS.keys():
        games = fetch_espn_scoreboard(league)
        all_games.extend(games)
        logger.info(f"Fetched {len(games)} games from {league}")
    
    # Organize by team
    by_team: Dict[str, List[Dict]] = {}
    for game in all_games:
        for team_key in ['home_team', 'away_team']:
            team = game.get(team_key)
            if team and team.get('name'):
                team_name = team['name'].lower()
                if team_name not in by_team:
                    by_team[team_name] = []
                by_team[team_name].append(game)
    
    # Organize by league
    by_league: Dict[str, List[Dict]] = {}
    for game in all_games:
        league = game.get('league')
        if league:
            if league not in by_league:
                by_league[league] = []
            by_league[league].append(game)
    
    sports_cache = {
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'games': all_games,
        'by_team': by_team,
        'by_league': by_league
    }
    
    save_cache()
    logger.info(f"Cache updated with {len(all_games)} total games")


def find_team_game(team_query: str) -> Optional[Dict]:
    """Find a current/upcoming game for a team."""
    team_query = team_query.lower().strip()
    
    # Check team aliases from channel mapping
    teams_config = channel_mapping.get('teams', {})
    matched_team_name = None
    
    for alias, team_info in teams_config.items():
        if team_query in alias.lower() or alias.lower() in team_query:
            matched_team_name = team_info.get('name', '').lower()
            break
    
    # Search in cache
    search_terms = [team_query]
    if matched_team_name:
        search_terms.append(matched_team_name)
    
    for term in search_terms:
        # Direct lookup
        if term in sports_cache.get('by_team', {}):
            games = sports_cache['by_team'][term]
            # Prefer live games, then upcoming
            live_games = [g for g in games if g.get('state') == 'in']
            if live_games:
                return live_games[0]
            upcoming = [g for g in games if g.get('state') == 'pre']
            if upcoming:
                return upcoming[0]
            if games:
                return games[0]
        
        # Partial match
        for team_name, games in sports_cache.get('by_team', {}).items():
            if term in team_name:
                live_games = [g for g in games if g.get('state') == 'in']
                if live_games:
                    return live_games[0]
                upcoming = [g for g in games if g.get('state') == 'pre']
                if upcoming:
                    return upcoming[0]
                if games:
                    return games[0]
    
    return None


# Flask Routes

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'sports-service',
        'last_updated': sports_cache.get('last_updated'),
        'game_count': len(sports_cache.get('games', []))
    })


@app.route('/games', methods=['GET'])
def get_all_games():
    """Get all cached games."""
    return jsonify({
        'last_updated': sports_cache.get('last_updated'),
        'games': sports_cache.get('games', [])
    })


@app.route('/games/<league>', methods=['GET'])
def get_league_games(league: str):
    """Get games for a specific league."""
    games = sports_cache.get('by_league', {}).get(league.lower(), [])
    return jsonify({
        'league': league,
        'games': games
    })


@app.route('/team/<team_name>', methods=['GET'])
def get_team_game(team_name: str):
    """Find a game for a specific team."""
    game = find_team_game(team_name)
    if game:
        return jsonify({
            'found': True,
            'game': game
        })
    return jsonify({
        'found': False,
        'message': f"No game found for '{team_name}'"
    })


@app.route('/channel/<network>', methods=['GET'])
def get_network_channel(network: str):
    """Get channel number for a network."""
    channel_info = get_channel_for_network(network)
    if channel_info:
        return jsonify({
            'found': True,
            'network': network,
            'channel': channel_info.get('hd_channel'),
            'channel_sd': channel_info.get('channel'),
            'info': channel_info
        })
    return jsonify({
        'found': False,
        'message': f"No channel mapping for '{network}'"
    })


@app.route('/lookup', methods=['POST'])
def lookup_game():
    """
    Main endpoint for Letta agent to look up what to tune to.
    Accepts: {"team": "patriots"} or {"network": "ESPN"}
    Returns: {"channel": 570, "description": "Patriots vs Bills on CBS"}
    """
    data = request.get_json() or {}
    
    # Team lookup
    if 'team' in data:
        game = find_team_game(data['team'])
        if game:
            channel = game.get('channel') or game.get('channel_sd')
            streaming = game.get('streaming_service')
            return jsonify({
                'success': True,
                'channel': channel,
                'network': game.get('broadcast_network'),
                'game_name': game.get('short_name') or game.get('name'),
                'state': game.get('state'),
                'status': game.get('status_detail'),
                'streaming_service': streaming,
                'description': f"{game.get('short_name')} on {game.get('broadcast_network')}"
            })
        return jsonify({
            'success': False,
            'error': f"No game found for {data['team']}"
        })
    
    # Network lookup
    if 'network' in data:
        channel_info = get_channel_for_network(data['network'])
        if channel_info:
            return jsonify({
                'success': True,
                'channel': channel_info.get('hd_channel'),
                'channel_sd': channel_info.get('channel'),
                'network': data['network'],
                'description': f"{data['network']} - Channel {channel_info.get('hd_channel')}"
            })
        return jsonify({
            'success': False,
            'error': f"No channel mapping for {data['network']}"
        })
    
    return jsonify({
        'success': False,
        'error': "Request must include 'team' or 'network'"
    })


@app.route('/refresh', methods=['POST'])
def refresh_cache():
    """Force refresh the sports cache."""
    update_sports_cache()
    return jsonify({
        'success': True,
        'last_updated': sports_cache.get('last_updated'),
        'game_count': len(sports_cache.get('games', []))
    })


@app.route('/mapping', methods=['GET'])
def get_channel_mapping():
    """Get the current channel mapping configuration."""
    return jsonify(channel_mapping)


def background_updater() -> None:
    """Background thread to periodically update sports data."""
    while True:
        try:
            update_sports_cache()
        except Exception as e:
            logger.error(f"Background update failed: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    # Load initial data
    load_channel_mapping()
    load_cache()
    
    # Initial fetch
    update_sports_cache()
    
    # Start background updater
    updater_thread = threading.Thread(target=background_updater, daemon=True)
    updater_thread.start()
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5123, debug=False)

