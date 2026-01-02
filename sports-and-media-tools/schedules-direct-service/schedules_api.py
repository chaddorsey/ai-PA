#!/usr/bin/env python3
"""
Schedules Direct API Service - Fetches and caches TV listings data.

Provides REST endpoints for:
- What's on now across all channels
- Upcoming programs by channel
- Program search (by title, category)
- Sports-specific listings
"""

import json
import os
import time
import hashlib
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

# Configuration from environment
SD_USERNAME = os.environ.get('SD_USERNAME', '')
SD_PASSWORD = os.environ.get('SD_PASSWORD', '')
SD_LINEUP = os.environ.get('SD_LINEUP', 'USA-MA65213-X')
CACHE_PATH = os.environ.get('CACHE_PATH', '/app/data/schedules_cache.json')
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', 3600))  # 1 hour default

# Schedules Direct API
SD_BASE_URL = "https://json.schedulesdirect.org/20141201"

# Global cache
schedules_cache: Dict[str, Any] = {
    'last_updated': None,
    'token': None,
    'token_expires': None,
    'stations': {},  # station_id -> station info
    'channel_map': {},  # channel_number -> station_id
    'schedules': {},  # station_id -> list of programs
    'programs': {},  # program_id -> program details
}


def get_password_hash() -> str:
    """Get SHA1 hash of password."""
    return hashlib.sha1(SD_PASSWORD.encode()).hexdigest()


def get_token() -> Optional[str]:
    """Get or refresh authentication token."""
    global schedules_cache
    
    # Check if we have a valid token
    if schedules_cache.get('token') and schedules_cache.get('token_expires'):
        expires = datetime.fromisoformat(schedules_cache['token_expires'].replace('Z', '+00:00'))
        if datetime.now(timezone.utc) < expires - timedelta(hours=1):
            return schedules_cache['token']
    
    # Get new token
    try:
        response = requests.post(
            f"{SD_BASE_URL}/token",
            json={"username": SD_USERNAME, "password": get_password_hash()},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get('code') == 0:
            schedules_cache['token'] = data.get('token')
            # Token expires in 24 hours
            schedules_cache['token_expires'] = (
                datetime.now(timezone.utc) + timedelta(hours=24)
            ).isoformat()
            logger.info("Got new Schedules Direct token")
            return schedules_cache['token']
        else:
            logger.error(f"Token error: {data}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to get token: {e}")
        return None


def get_headers() -> Dict[str, str]:
    """Get headers with auth token."""
    token = get_token()
    return {
        "token": token,
        "Content-Type": "application/json"
    }


def fetch_lineup() -> bool:
    """Fetch lineup details (stations and channel mapping)."""
    global schedules_cache
    
    try:
        headers = get_headers()
        response = requests.get(
            f"{SD_BASE_URL}/lineups/{SD_LINEUP}",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        # Store stations
        for station in data.get('stations', []):
            station_id = station.get('stationID')
            schedules_cache['stations'][station_id] = {
                'id': station_id,
                'name': station.get('name'),
                'callsign': station.get('callsign'),
                'affiliate': station.get('affiliate'),
                'broadcast_language': station.get('broadcastLanguage', []),
            }
        
        # Store channel mapping
        for mapping in data.get('map', []):
            channel = mapping.get('channel')
            station_id = mapping.get('stationID')
            schedules_cache['channel_map'][channel] = station_id
        
        logger.info(f"Loaded {len(schedules_cache['stations'])} stations, "
                   f"{len(schedules_cache['channel_map'])} channel mappings")
        return True
        
    except Exception as e:
        logger.error(f"Failed to fetch lineup: {e}")
        return False


def fetch_schedules(days: int = 2) -> bool:
    """Fetch schedules for all stations."""
    global schedules_cache
    
    try:
        headers = get_headers()
        
        # Get list of station IDs
        station_ids = list(schedules_cache['stations'].keys())
        
        if not station_ids:
            logger.warning("No stations to fetch schedules for")
            return False
        
        # Build request for schedules
        # Schedules Direct wants dates in YYYY-MM-DD format
        today = datetime.now(timezone.utc).date()
        dates = [(today + timedelta(days=i)).isoformat() for i in range(days)]
        
        schedule_request = []
        for station_id in station_ids:
            schedule_request.append({
                "stationID": station_id,
                "date": dates
            })
        
        # Fetch schedules in batches (max 5000 per request)
        batch_size = 500
        all_schedules = []
        
        for i in range(0, len(schedule_request), batch_size):
            batch = schedule_request[i:i + batch_size]
            
            response = requests.post(
                f"{SD_BASE_URL}/schedules",
                headers=headers,
                json=batch,
                timeout=60
            )
            response.raise_for_status()
            all_schedules.extend(response.json())
            
            logger.info(f"Fetched schedules batch {i // batch_size + 1}")
        
        # Process schedules
        program_ids_needed = set()
        
        # Clear all schedules first, then populate
        schedules_cache['schedules'] = {}
        
        for schedule in all_schedules:
            station_id = schedule.get('stationID')
            programs = schedule.get('programs', [])
            
            # Initialize list if not exists, then extend (don't overwrite)
            if station_id not in schedules_cache['schedules']:
                schedules_cache['schedules'][station_id] = []
            
            for prog in programs:
                program_id = prog.get('programID')
                program_ids_needed.add(program_id)
                
                schedules_cache['schedules'][station_id].append({
                    'program_id': program_id,
                    'air_datetime': prog.get('airDateTime'),
                    'duration': prog.get('duration'),
                    'md5': prog.get('md5'),
                    'new': prog.get('new', False),
                    'live_tape_delay': prog.get('liveTapeDelay'),
                })
        
        logger.info(f"Processed schedules for {len(all_schedules)} stations, "
                   f"need {len(program_ids_needed)} program details")
        
        # Fetch program details
        if program_ids_needed:
            fetch_programs(list(program_ids_needed))
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to fetch schedules: {e}")
        return False


def fetch_programs(program_ids: List[str]) -> bool:
    """Fetch program details."""
    global schedules_cache
    
    try:
        headers = get_headers()
        
        # Fetch in batches
        batch_size = 500
        
        for i in range(0, len(program_ids), batch_size):
            batch = program_ids[i:i + batch_size]
            
            response = requests.post(
                f"{SD_BASE_URL}/programs",
                headers=headers,
                json=batch,
                timeout=60
            )
            response.raise_for_status()
            programs = response.json()
            
            for prog in programs:
                program_id = prog.get('programID')
                
                # Extract relevant info
                titles = prog.get('titles', [{}])
                title = titles[0].get('title120', '') if titles else ''
                
                descriptions = prog.get('descriptions', {})
                desc_list = descriptions.get('description1000', []) or descriptions.get('description100', [])
                description = desc_list[0].get('description', '') if desc_list else ''
                
                # Get genres/categories
                genres = prog.get('genres', [])
                
                # Check if it's sports - look for sports-related genres
                sports_genres = {
                    'sports', 'football', 'basketball', 'baseball', 'hockey', 'soccer',
                    'golf', 'tennis', 'boxing', 'wrestling', 'mma', 'racing', 'motorsports',
                    'olympics', 'sports talk', 'sports event', 'team event', 'athletic event'
                }
                genres_lower = [g.lower() for g in genres]
                entity_type = (prog.get('entityType') or '').lower()
                
                is_sports = (
                    any(sg in g for g in genres_lower for sg in sports_genres) or
                    entity_type in ['sports', 'team event', 'athletic event']
                )
                
                # Episode info
                episode_title = prog.get('episodeTitle150', '')
                season = prog.get('metadata', [{}])[0].get('season') if prog.get('metadata') else None
                episode = prog.get('metadata', [{}])[0].get('episode') if prog.get('metadata') else None
                
                schedules_cache['programs'][program_id] = {
                    'id': program_id,
                    'title': title,
                    'episode_title': episode_title,
                    'description': description,
                    'genres': genres,
                    'is_sports': is_sports,
                    'season': season,
                    'episode': episode,
                    'original_air_date': prog.get('originalAirDate'),
                    'entity_type': prog.get('entityType'),
                }
            
            logger.info(f"Fetched program details batch {i // batch_size + 1}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to fetch programs: {e}")
        return False


def update_cache() -> None:
    """Full cache update."""
    global schedules_cache
    
    logger.info("Starting cache update...")
    
    if not SD_USERNAME or not SD_PASSWORD:
        logger.error("SD_USERNAME and SD_PASSWORD environment variables required")
        return
    
    # Fetch lineup if not already loaded
    if not schedules_cache.get('stations'):
        fetch_lineup()
    
    # Fetch schedules
    fetch_schedules(days=2)
    
    schedules_cache['last_updated'] = datetime.now(timezone.utc).isoformat()
    save_cache()
    
    logger.info("Cache update complete")


def save_cache() -> None:
    """Save cache to disk."""
    try:
        Path(CACHE_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, 'w') as f:
            json.dump(schedules_cache, f, indent=2, default=str)
        logger.debug(f"Saved cache to {CACHE_PATH}")
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")


def load_cache() -> None:
    """Load cache from disk."""
    global schedules_cache
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, 'r') as f:
                schedules_cache = json.load(f)
            logger.info(f"Loaded cache from {CACHE_PATH}")
    except Exception as e:
        logger.error(f"Failed to load cache: {e}")


def get_whats_on_now(channel: Optional[str] = None) -> List[Dict]:
    """Get currently airing programs."""
    now = datetime.now(timezone.utc)
    results = []
    
    channels_to_check = [channel] if channel else list(schedules_cache.get('channel_map', {}).keys())
    
    for ch in channels_to_check:
        station_id = schedules_cache.get('channel_map', {}).get(ch)
        if not station_id:
            continue
        
        station = schedules_cache.get('stations', {}).get(station_id, {})
        schedule = schedules_cache.get('schedules', {}).get(station_id, [])
        
        for prog in schedule:
            air_time = datetime.fromisoformat(prog['air_datetime'].replace('Z', '+00:00'))
            end_time = air_time + timedelta(seconds=prog['duration'])
            
            if air_time <= now < end_time:
                program = schedules_cache.get('programs', {}).get(prog['program_id'], {})
                
                results.append({
                    'channel': ch,
                    'station': station.get('callsign'),
                    'station_name': station.get('name'),
                    'title': program.get('title'),
                    'episode_title': program.get('episode_title'),
                    'description': program.get('description'),
                    'start_time': air_time.isoformat(),
                    'end_time': end_time.isoformat(),
                    'duration_minutes': prog['duration'] // 60,
                    'genres': program.get('genres', []),
                    'is_sports': program.get('is_sports', False),
                    'is_new': prog.get('new', False),
                    'is_live': prog.get('live_tape_delay') == 'Live',
                })
                break
    
    return results


def get_upcoming(channel: str, hours: int = 6) -> List[Dict]:
    """Get upcoming programs for a channel."""
    now = datetime.now(timezone.utc)
    end_window = now + timedelta(hours=hours)
    results = []
    
    station_id = schedules_cache.get('channel_map', {}).get(channel)
    if not station_id:
        return []
    
    station = schedules_cache.get('stations', {}).get(station_id, {})
    schedule = schedules_cache.get('schedules', {}).get(station_id, [])
    
    for prog in schedule:
        air_time = datetime.fromisoformat(prog['air_datetime'].replace('Z', '+00:00'))
        
        if now <= air_time < end_window:
            program = schedules_cache.get('programs', {}).get(prog['program_id'], {})
            
            results.append({
                'channel': channel,
                'station': station.get('callsign'),
                'title': program.get('title'),
                'episode_title': program.get('episode_title'),
                'start_time': air_time.isoformat(),
                'duration_minutes': prog['duration'] // 60,
                'genres': program.get('genres', []),
                'is_sports': program.get('is_sports', False),
                'is_new': prog.get('new', False),
            })
    
    return sorted(results, key=lambda x: x['start_time'])


# Flask Routes

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'schedules-direct-service',
        'last_updated': schedules_cache.get('last_updated'),
        'station_count': len(schedules_cache.get('stations', {})),
        'lineup': SD_LINEUP,
    })


@app.route('/now', methods=['GET'])
def whats_on_now():
    """Get what's on now across all channels."""
    channel = request.args.get('channel')
    results = get_whats_on_now(channel)
    
    # Sort by channel number
    results.sort(key=lambda x: int(x['channel']) if x['channel'].isdigit() else 9999)
    
    return jsonify({
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'programs': results,
        'count': len(results)
    })


@app.route('/now/sports', methods=['GET'])
def sports_on_now():
    """Get sports programs currently on."""
    results = get_whats_on_now()
    sports = [r for r in results if r.get('is_sports')]
    
    return jsonify({
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'programs': sports,
        'count': len(sports)
    })


@app.route('/channel/<channel>', methods=['GET'])
def channel_schedule(channel: str):
    """Get schedule for a specific channel."""
    hours = int(request.args.get('hours', 6))
    
    # Get what's on now
    now_programs = get_whats_on_now(channel)
    current = now_programs[0] if now_programs else None
    
    # Get upcoming
    upcoming = get_upcoming(channel, hours)
    
    return jsonify({
        'channel': channel,
        'current': current,
        'upcoming': upcoming
    })


@app.route('/search', methods=['GET'])
def search_programs():
    """Search for programs by title."""
    query = request.args.get('q', '').lower()
    if not query:
        return jsonify({'error': 'Query parameter "q" required'}), 400
    
    now = datetime.now(timezone.utc)
    results = []
    
    for station_id, schedule in schedules_cache.get('schedules', {}).items():
        station = schedules_cache.get('stations', {}).get(station_id, {})
        channel = None
        
        # Find channel number for this station
        for ch, sid in schedules_cache.get('channel_map', {}).items():
            if sid == station_id:
                channel = ch
                break
        
        for prog in schedule:
            air_time = datetime.fromisoformat(prog['air_datetime'].replace('Z', '+00:00'))
            if air_time < now:
                continue
            
            program = schedules_cache.get('programs', {}).get(prog['program_id'], {})
            title = program.get('title', '').lower()
            
            if query in title:
                results.append({
                    'channel': channel,
                    'station': station.get('callsign'),
                    'title': program.get('title'),
                    'episode_title': program.get('episode_title'),
                    'start_time': air_time.isoformat(),
                    'duration_minutes': prog['duration'] // 60,
                    'is_sports': program.get('is_sports', False),
                })
    
    results.sort(key=lambda x: x['start_time'])
    return jsonify({
        'query': query,
        'results': results[:50],  # Limit to 50 results
        'count': len(results)
    })


@app.route('/refresh', methods=['POST'])
def refresh_cache():
    """Force refresh the cache."""
    update_cache()
    return jsonify({
        'success': True,
        'last_updated': schedules_cache.get('last_updated'),
        'station_count': len(schedules_cache.get('stations', {}))
    })


@app.route('/stations', methods=['GET'])
def list_stations():
    """List all stations in the lineup."""
    stations = []
    
    for channel, station_id in sorted(
        schedules_cache.get('channel_map', {}).items(),
        key=lambda x: int(x[0]) if x[0].isdigit() else 9999
    ):
        station = schedules_cache.get('stations', {}).get(station_id, {})
        stations.append({
            'channel': channel,
            'station_id': station_id,
            'callsign': station.get('callsign'),
            'name': station.get('name'),
        })
    
    return jsonify({
        'lineup': SD_LINEUP,
        'stations': stations,
        'count': len(stations)
    })


def background_updater() -> None:
    """Background thread to periodically update schedules."""
    # Initial delay to let the app start
    time.sleep(5)
    
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"Background update failed: {e}")
        time.sleep(POLL_INTERVAL)


def initialize_app():
    """Initialize the application - called on startup."""
    # Load existing cache
    load_cache()
    
    # Start background updater thread
    updater_thread = threading.Thread(target=background_updater, daemon=True)
    updater_thread.start()
    logger.info("Background updater thread started")


# Initialize on module load (works with gunicorn)
initialize_app()


if __name__ == '__main__':
    # Run Flask app directly (for development)
    app.run(host='0.0.0.0', port=5125, debug=False)

