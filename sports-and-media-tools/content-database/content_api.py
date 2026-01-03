#!/usr/bin/env python3
"""
Content Database API

Flask API for querying the content database and getting deep link information.
Used by Letta tools to find streaming availability and launch content.
"""

import os
import json
import logging
import sqlite3
from datetime import datetime, timezone
from flask import Flask, jsonify, request

# Import the scraper functions
from justwatch_scraper import (
    init_database,
    lookup_content,
    get_content_for_deep_link,
    search_justwatch,
    get_content_details,
    save_content_to_db,
    scrape_popular_for_all_services,
    PROVIDER_IDS,
    SUBSCRIBED_SERVICES,
    DB_PATH
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def extract_content_id_from_url(url: str, service: str) -> str:
    """Extract content ID from a streaming service URL."""
    if not url:
        return None
    
    try:
        if service == 'netflix':
            # Netflix: https://www.netflix.com/title/80057281
            if '/title/' in url:
                return url.split('/title/')[-1].split('?')[0].split('/')[0]
        
        elif service == 'hulu':
            # Hulu: various formats, extract path segments
            if '/series/' in url:
                parts = url.split('/series/')[-1].split('/')
                if parts:
                    return parts[0]
            elif '/movie/' in url:
                parts = url.split('/movie/')[-1].split('/')
                if parts:
                    return parts[0]
        
        elif service == 'disney':
            # Disney+: extract content ID from URL
            if '/series/' in url or '/movies/' in url:
                parts = url.split('/')
                for i, part in enumerate(parts):
                    if len(part) > 15 and '-' not in part[:10]:
                        return part
        
        elif service == 'max':
            # Max/HBO: URN style IDs
            if '/show/' in url or '/movie/' in url:
                parts = url.split('/')
                for part in parts:
                    if part.startswith('urn:') or (len(part) > 20 and ':' in part):
                        return part
        
        elif service == 'prime':
            # Prime Video: /detail/XXXX or /gp/video/detail/XXXX
            if '/detail/' in url:
                return url.split('/detail/')[-1].split('/')[0].split('?')[0]
        
        elif service == 'apple':
            # Apple TV+: umc.cmc.xxxxx format
            parts = url.split('/')
            for part in parts:
                if part.startswith('umc.cmc.'):
                    return part
        
        elif service == 'youtube':
            # YouTube: v=XXXXX or /watch/XXXXX
            if 'v=' in url:
                return url.split('v=')[-1].split('&')[0]
            elif '/watch/' in url:
                return url.split('/watch/')[-1].split('?')[0]
        
    except Exception:
        pass
    
    return None


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'content-database'})


@app.route('/search', methods=['GET'])
def search():
    """
    Search for content by title.
    
    Query params:
        q: Search query
        type: 'movie' or 'show' (optional)
    
    Returns:
        List of matching content with streaming availability
    """
    query = request.args.get('q', '')
    content_type = request.args.get('type')
    
    if not query:
        return jsonify({'error': 'Missing query parameter q'}), 400
    
    try:
        # First check local database
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        sql = '''
            SELECT c.*, GROUP_CONCAT(
                sa.service || ':' || COALESCE(sa.content_id_for_service, '') || ':' || sa.offer_type
            ) as streaming
            FROM content c
            LEFT JOIN streaming_availability sa ON c.id = sa.content_id
            WHERE c.title LIKE ?
        '''
        params = [f'%{query}%']
        
        if content_type:
            sql += ' AND c.content_type = ?'
            params.append(content_type)
        
        sql += ' GROUP BY c.id LIMIT 10'
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        
        results = []
        for row in rows:
            item = dict(row)
            # Parse streaming availability
            streaming = {}
            if item.get('streaming'):
                for entry in item['streaming'].split(','):
                    parts = entry.split(':')
                    if len(parts) >= 2:
                        svc = parts[0]
                        content_id = parts[1] if len(parts) > 1 else None
                        offer_type = parts[2] if len(parts) > 2 else 'flatrate'
                        if svc not in streaming:
                            streaming[svc] = []
                        streaming[svc].append({
                            'content_id': content_id,
                            'offer_type': offer_type
                        })
            item['streaming_availability'] = streaming
            del item['streaming']
            results.append(item)
        
        # If no local results, search JustWatch
        if not results:
            logger.info(f"No local results for '{query}', searching JustWatch...")
            jw_results = search_justwatch(query, content_type)
            
            for jw_item in jw_results[:5]:
                # The GraphQL search already includes offers, use them directly
                offers = jw_item.get('offers', [])
                
                # Save to database using the search result data
                save_content_to_db(jw_item, offers)
                
                # Build result - map package info to our service names
                streaming = {}
                for offer in offers:
                    package = offer.get('package', {})
                    package_id = package.get('packageId')
                    clear_name = package.get('clearName', '').lower()
                    
                    # Map package to our service names
                    service = None
                    if package_id == 8 or 'netflix' in clear_name:
                        service = 'netflix'
                    elif package_id == 15 or 'hulu' in clear_name:
                        service = 'hulu'
                    elif package_id == 337 or 'disney' in clear_name:
                        service = 'disney'
                    elif package_id == 1899 or 'max' in clear_name or 'hbo' in clear_name:
                        service = 'max'
                    elif package_id == 9 or 'prime' in clear_name or 'amazon' in clear_name:
                        service = 'prime'
                    elif package_id == 350 or 'apple' in clear_name:
                        service = 'apple'
                    elif package_id == 2303 or 'espn' in clear_name:
                        service = 'espn'
                    elif package_id == 192 or 'youtube' in clear_name:
                        service = 'youtube'
                    
                    if service and service in SUBSCRIBED_SERVICES:
                        if service not in streaming:
                            streaming[service] = []
                        
                        # Extract content ID from URL
                        web_url = offer.get('standardWebURL', '')
                        content_id = extract_content_id_from_url(web_url, service)
                        
                        streaming[service].append({
                            'content_id': content_id,
                            'offer_type': offer.get('monetizationType', 'flatrate')
                        })
                
                # Add result for this item (outside the offers loop)
                results.append({
                    'title': jw_item.get('title'),
                    'content_type': jw_item.get('object_type'),
                    'year': jw_item.get('original_release_year'),
                    'description': jw_item.get('short_description'),
                    'streaming_availability': streaming
                })
        
        return jsonify({
            'query': query,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/deep-link', methods=['GET'])
def get_deep_link():
    """
    Get deep link info for a specific title.
    
    Query params:
        title: Content title
        service: Preferred streaming service (optional)
    
    Returns:
        Deep link information for Roku
    """
    title = request.args.get('title', '')
    preferred_service = request.args.get('service')
    
    if not title:
        return jsonify({'error': 'Missing title parameter'}), 400
    
    try:
        result = get_content_for_deep_link(title, preferred_service)
        
        if result:
            # Add Roku deep link format
            service = result['service']
            content_id = result['content_id']
            
            # Build Roku launch parameters based on service
            roku_params = build_roku_params(service, content_id, result.get('content_type'))
            result['roku_launch'] = roku_params
            
            return jsonify(result)
        else:
            return jsonify({
                'error': 'Content not found',
                'title': title,
                'suggestion': 'Try using Roku universal search as fallback'
            }), 404
            
    except Exception as e:
        logger.error(f"Deep link error: {e}")
        return jsonify({'error': str(e)}), 500


def build_roku_params(service: str, content_id: str, content_type: str = None) -> dict:
    """
    Build Roku launch parameters for a given service and content.
    
    Args:
        service: Streaming service name
        content_id: Content ID for the service
        content_type: 'movie' or 'show'
    
    Returns:
        Dict with app_id and params for Roku ECP launch
    """
    # Roku app IDs
    app_ids = {
        'netflix': 12,
        'hulu': 2285,
        'disney': 291097,
        'max': 61322,
        'prime': 13,
        'apple': 551012,
        'espn': 34376,
        'youtube': 837,
        'youtube_tv': 195316,
    }
    
    app_id = app_ids.get(service)
    if not app_id:
        return None
    
    params = {'app_id': app_id}
    
    if service == 'netflix':
        params['contentId'] = content_id
        params['mediaType'] = 'series' if content_type == 'show' else 'movie'
    
    elif service == 'hulu':
        params['contentId'] = content_id
        params['mediaType'] = 'series' if content_type == 'show' else 'movie'
    
    elif service == 'disney':
        params['contentId'] = content_id
        params['mediaType'] = content_type or 'movie'
    
    elif service == 'max':
        params['contentId'] = content_id
        params['mediaType'] = 'series' if content_type == 'show' else 'movie'
    
    elif service == 'prime':
        params['contentId'] = content_id
        params['mediaType'] = 'series' if content_type == 'show' else 'movie'
    
    elif service == 'apple':
        # Apple TV+ uses URL-encoded full URLs
        from urllib.parse import quote
        full_url = f"https://tv.apple.com/us/show/{content_id}"
        params['contentId'] = quote(full_url, safe='')
        params['mediaType'] = 'live'
    
    elif service == 'youtube':
        params['contentId'] = content_id
        params['mediaType'] = 'live'
    
    return params


@app.route('/availability/<title>', methods=['GET'])
def check_availability(title: str):
    """
    Check which subscribed services have a specific title.
    
    Returns:
        List of services where content is available
    """
    try:
        content = lookup_content(title)
        
        if content:
            streaming = content.get('streaming_availability', {})
            available_on = []
            
            for service, content_id in streaming.items():
                if content_id:
                    available_on.append({
                        'service': service,
                        'has_deep_link': bool(content_id),
                        'content_id': content_id
                    })
            
            return jsonify({
                'title': content.get('title'),
                'available_on': available_on,
                'count': len(available_on)
            })
        else:
            return jsonify({
                'error': 'Content not found',
                'title': title
            }), 404
            
    except Exception as e:
        logger.error(f"Availability check error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/refresh', methods=['POST'])
def refresh_popular():
    """
    Trigger a refresh of popular content from JustWatch.
    This is resource-intensive and should be called sparingly.
    """
    try:
        # Run in background ideally, but for now sync
        scrape_popular_for_all_services()
        return jsonify({'status': 'ok', 'message': 'Popular content refreshed'})
    except Exception as e:
        logger.error(f"Refresh error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/stats', methods=['GET'])
def get_stats():
    """Get database statistics."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM content')
        content_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT service, COUNT(*) FROM streaming_availability GROUP BY service')
        service_counts = {row[0]: row[1] for row in cursor.fetchall()}
        
        cursor.execute('SELECT MAX(updated_at) FROM content')
        last_updated = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'total_content': content_count,
            'by_service': service_counts,
            'last_updated': last_updated,
            'subscribed_services': SUBSCRIBED_SERVICES
        })
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/scrape-title', methods=['POST'])
def scrape_single_title():
    """
    Scrape a specific title from JustWatch and add to database.
    
    This endpoint is used by the sleeptime agent to add specific titles
    that users are interested in to the local database.
    
    Body params:
        title: Title to search for
        content_type: 'movie' or 'show' (optional)
    """
    try:
        data = request.get_json() or {}
        title = data.get('title')
        content_type = data.get('content_type')
        
        if not title:
            return jsonify({'error': 'Missing title parameter'}), 400
        
        # Search JustWatch
        results = search_justwatch(title, content_type)
        
        if not results:
            return jsonify({
                'status': 'not_found',
                'title': title,
                'message': 'No results found on JustWatch'
            }), 404
        
        # Get details for first result
        item = results[0]
        details = get_content_details(item.get('id'), item.get('object_type'))
        
        if not details:
            return jsonify({
                'status': 'error',
                'title': title,
                'message': 'Could not fetch content details'
            }), 500
        
        # Filter to subscribed services
        offers = [o for o in details.get('offers', []) 
                  if o.get('provider_id') in PROVIDER_IDS.values()
                  and o.get('monetization_type') == 'flatrate']
        
        # Save to database
        save_content_to_db(details, offers)
        
        # Build response
        streaming_services = []
        for offer in offers:
            for svc, pid in PROVIDER_IDS.items():
                if pid == offer.get('provider_id'):
                    streaming_services.append(svc)
                    break
        
        return jsonify({
            'status': 'ok',
            'title': details.get('title'),
            'content_type': details.get('object_type'),
            'year': details.get('original_release_year'),
            'available_on': list(set(streaming_services)),
            'message': f"Added '{details.get('title')}' to content database"
        })
        
    except Exception as e:
        logger.error(f"Error scraping title: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/nfl', methods=['GET'])
def get_nfl_content():
    """
    Get available NFL content from YouTube/YouTube TV.
    
    Query params:
        team: Filter by team name (optional)
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        team = request.args.get('team')
        
        if team:
            cursor.execute('''
                SELECT * FROM nfl_content 
                WHERE teams LIKE ? 
                ORDER BY date DESC
            ''', (f'%{team}%',))
        else:
            cursor.execute('SELECT * FROM nfl_content ORDER BY date DESC LIMIT 20')
        
        rows = cursor.fetchall()
        conn.close()
        
        results = [dict(row) for row in rows]
        
        return jsonify({
            'games': results,
            'count': len(results)
        })
        
    except Exception as e:
        logger.error(f"NFL content error: {e}")
        return jsonify({'error': str(e)}), 500


# =============================================================================
# USER WATCH HISTORY ENDPOINTS
# =============================================================================

@app.route('/user/<username>/history', methods=['GET'])
def get_user_history(username: str):
    """
    Get a user's watch history.
    
    Query params:
        service: Filter by service (netflix, prime, etc.)
        limit: Maximum results (default 50)
        offset: Pagination offset
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get user
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': f'User not found: {username}'}), 404
        
        user_id = user[0]
        service = request.args.get('service')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        
        sql = '''
            SELECT wh.*, c.justwatch_id, c.year, c.content_type,
                   GROUP_CONCAT(sa.service || ':' || COALESCE(sa.content_id_for_service, '')) as streaming
            FROM user_watch_history wh
            LEFT JOIN content c ON wh.content_id = c.id
            LEFT JOIN streaming_availability sa ON c.id = sa.content_id
            WHERE wh.user_id = ?
        '''
        params = [user_id]
        
        if service:
            sql += ' AND wh.service = ?'
            params.append(service)
        
        sql += ' GROUP BY wh.id ORDER BY wh.watched_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            item = dict(row)
            # Parse streaming info
            streaming = {}
            if item.get('streaming'):
                for entry in item['streaming'].split(','):
                    parts = entry.split(':')
                    if len(parts) >= 2 and parts[1]:
                        streaming[parts[0]] = parts[1]
            item['streaming_links'] = streaming
            del item['streaming']
            results.append(item)
        
        # Get total count
        cursor.execute(
            'SELECT COUNT(*) FROM user_watch_history WHERE user_id = ?' + 
            (' AND service = ?' if service else ''),
            [user_id, service] if service else [user_id]
        )
        total = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'user': username,
            'history': results,
            'count': len(results),
            'total': total,
            'offset': offset
        })
        
    except Exception as e:
        logger.error(f"User history error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/user/<username>/continue-watching', methods=['GET'])
def get_continue_watching(username: str):
    """
    Get shows/series the user has started but not completed.
    Returns the next episode to watch for each series.
    
    Query params:
        limit: Maximum series to return (default 10)
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get user
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': f'User not found: {username}'}), 404
        
        user_id = user[0]
        limit = int(request.args.get('limit', 10))
        
        # Find series with the most recent watch date and highest episode
        cursor.execute('''
            SELECT 
                wh.title,
                wh.service,
                MAX(wh.season_number) as last_season,
                MAX(wh.episode_number) as last_episode,
                MAX(wh.watched_at) as last_watched,
                c.id as content_id,
                c.content_type,
                c.justwatch_id
            FROM user_watch_history wh
            LEFT JOIN content c ON wh.content_id = c.id
            WHERE wh.user_id = ?
                AND wh.episode_title IS NOT NULL
            GROUP BY wh.title
            ORDER BY last_watched DESC
            LIMIT ?
        ''', (user_id, limit))
        
        series = cursor.fetchall()
        
        results = []
        for s in series:
            item = dict(s)
            
            # Get streaming links for this content
            if item.get('content_id'):
                cursor.execute('''
                    SELECT service, content_id_for_service
                    FROM streaming_availability
                    WHERE content_id = ? AND content_id_for_service IS NOT NULL
                ''', (item['content_id'],))
                streaming = {row[0]: row[1] for row in cursor.fetchall()}
                item['streaming_links'] = streaming
            else:
                item['streaming_links'] = {}
            
            # Suggest next episode
            next_ep = (item.get('last_episode') or 0) + 1
            item['suggested_next'] = {
                'season': item.get('last_season') or 1,
                'episode': next_ep
            }
            
            results.append(item)
        
        conn.close()
        
        return jsonify({
            'user': username,
            'continue_watching': results,
            'count': len(results)
        })
        
    except Exception as e:
        logger.error(f"Continue watching error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/user/<username>/stats', methods=['GET'])
def get_user_stats(username: str):
    """Get statistics about a user's watch history."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get user
        cursor.execute('SELECT id, display_name, created_at FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': f'User not found: {username}'}), 404
        
        user_id = user[0]
        
        # Total entries
        cursor.execute('SELECT COUNT(*) FROM user_watch_history WHERE user_id = ?', (user_id,))
        total = cursor.fetchone()[0]
        
        # By service
        cursor.execute('''
            SELECT service, COUNT(*) 
            FROM user_watch_history 
            WHERE user_id = ? 
            GROUP BY service
        ''', (user_id,))
        by_service = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Unique titles
        cursor.execute('SELECT COUNT(DISTINCT title) FROM user_watch_history WHERE user_id = ?', (user_id,))
        unique_titles = cursor.fetchone()[0]
        
        # Most watched
        cursor.execute('''
            SELECT title, COUNT(*) as watch_count
            FROM user_watch_history
            WHERE user_id = ?
            GROUP BY title
            ORDER BY watch_count DESC
            LIMIT 10
        ''', (user_id,))
        most_watched = [{'title': row[0], 'count': row[1]} for row in cursor.fetchall()]
        
        # Recent activity
        cursor.execute('''
            SELECT DATE(watched_at) as watch_date, COUNT(*) as count
            FROM user_watch_history
            WHERE user_id = ? AND watched_at IS NOT NULL
            GROUP BY DATE(watched_at)
            ORDER BY watch_date DESC
            LIMIT 30
        ''', (user_id,))
        recent_activity = [{'date': row[0], 'count': row[1]} for row in cursor.fetchall()]
        
        conn.close()
        
        return jsonify({
            'user': username,
            'display_name': user[1],
            'member_since': user[2],
            'total_watches': total,
            'unique_titles': unique_titles,
            'by_service': by_service,
            'most_watched': most_watched,
            'recent_activity': recent_activity
        })
        
    except Exception as e:
        logger.error(f"User stats error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/user/<username>/search', methods=['GET'])
def search_user_history(username: str):
    """
    Search a user's watch history.
    
    Query params:
        q: Search query
    """
    try:
        query = request.args.get('q', '')
        if not query:
            return jsonify({'error': 'Missing query parameter q'}), 400
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get user
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': f'User not found: {username}'}), 404
        
        user_id = user[0]
        
        cursor.execute('''
            SELECT DISTINCT wh.title, wh.service, wh.episode_title,
                   MAX(wh.watched_at) as last_watched,
                   c.content_type, c.year
            FROM user_watch_history wh
            LEFT JOIN content c ON wh.content_id = c.id
            WHERE wh.user_id = ?
                AND (wh.title LIKE ? OR wh.episode_title LIKE ?)
            GROUP BY wh.title
            ORDER BY last_watched DESC
            LIMIT 20
        ''', (user_id, f'%{query}%', f'%{query}%'))
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({
            'user': username,
            'query': query,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        logger.error(f"User search error: {e}")
        return jsonify({'error': str(e)}), 500


# =============================================================================
# TRACKED SERIES ENDPOINTS
# =============================================================================

@app.route('/user/<username>/tracked-series', methods=['GET'])
def list_user_tracked_series(username: str):
    """
    List tracked series for a user.
    
    Query params:
        status: Filter by tracking_status (watching, finished, dropped, on_hold, all)
        service: Filter by preferred_service
    """
    try:
        from user_schema import (
            get_or_create_user, list_tracked_series as list_ts
        )
        
        user_id = get_or_create_user(DB_PATH, username)
        status = request.args.get('status', 'all')
        service = request.args.get('service', 'all')
        
        series_list = list_ts(DB_PATH, user_id, status, service)
        
        # Parse JSON fields
        for s in series_list:
            if s.get('available_services'):
                try:
                    s['available_services'] = json.loads(s['available_services'])
                except json.JSONDecodeError:
                    pass
            if s.get('manual_progress'):
                try:
                    s['manual_progress'] = json.loads(s['manual_progress'])
                except json.JSONDecodeError:
                    pass
        
        return jsonify({
            'user': username,
            'series': series_list,
            'count': len(series_list),
            'filters': {'status': status, 'service': service}
        })
        
    except Exception as e:
        logger.error(f"List tracked series error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/user/<username>/tracked-series', methods=['POST'])
def create_user_tracked_series(username: str):
    """
    Add a series to tracking.
    
    Body params:
        title: Series title (required)
        preferred_service: Streaming service (optional)
        justwatch_id: JustWatch ID (optional)
        imdb_id: IMDB ID (optional)
        series_url: URL to series page (optional)
        auto_tracked: Whether auto-added from watchlist (optional)
    """
    try:
        from user_schema import get_or_create_user, create_tracked_series, get_tracked_series_by_id
        
        data = request.get_json() or {}
        title = data.get('title')
        
        if not title:
            return jsonify({'error': 'Missing required field: title'}), 400
        
        user_id = get_or_create_user(DB_PATH, username)
        
        # Check for duplicate
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id FROM tracked_series WHERE user_id = ? AND LOWER(title) = LOWER(?)',
            (user_id, title)
        )
        existing = cursor.fetchone()
        conn.close()
        
        if existing:
            return jsonify({'error': f'Series already tracked: {title}', 'id': existing[0]}), 409
        
        series_id = create_tracked_series(
            DB_PATH,
            user_id,
            title=title,
            preferred_service=data.get('preferred_service'),
            justwatch_id=data.get('justwatch_id'),
            imdb_id=data.get('imdb_id'),
            series_url=data.get('series_url'),
            available_services=json.dumps(data.get('available_services')) if data.get('available_services') else None,
            total_seasons_known=data.get('total_seasons_known'),
            auto_tracked=data.get('auto_tracked', False)
        )
        
        series = get_tracked_series_by_id(DB_PATH, series_id)
        
        return jsonify({
            'status': 'ok',
            'message': f"Added '{title}' to tracked series",
            'series': series
        }), 201
        
    except Exception as e:
        logger.error(f"Create tracked series error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/user/<username>/tracked-series/<int:series_id>', methods=['GET'])
def get_user_tracked_series(username: str, series_id: int):
    """Get a specific tracked series by ID."""
    try:
        from user_schema import get_tracked_series_by_id
        
        series = get_tracked_series_by_id(DB_PATH, series_id)
        if not series:
            return jsonify({'error': 'Series not found'}), 404
        
        # Parse JSON fields
        if series.get('available_services'):
            try:
                series['available_services'] = json.loads(series['available_services'])
            except json.JSONDecodeError:
                pass
        if series.get('manual_progress'):
            try:
                series['manual_progress'] = json.loads(series['manual_progress'])
            except json.JSONDecodeError:
                pass
        
        return jsonify(series)
        
    except Exception as e:
        logger.error(f"Get tracked series error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/user/<username>/tracked-series/<int:series_id>', methods=['PUT'])
def update_user_tracked_series(username: str, series_id: int):
    """
    Update a tracked series.
    
    Body params (all optional):
        tracking_status: watching, finished, dropped, on_hold
        watch_status: not_started, in_progress, fully_watched
        preferred_service: Streaming service
        notes: User notes
        manual_progress: Dict with progress overrides
    """
    try:
        from user_schema import update_tracked_series, get_tracked_series_by_id
        
        data = request.get_json() or {}
        
        # Handle JSON fields
        if 'manual_progress' in data and isinstance(data['manual_progress'], dict):
            data['manual_progress'] = json.dumps(data['manual_progress'])
        if 'available_services' in data and isinstance(data['available_services'], list):
            data['available_services'] = json.dumps(data['available_services'])
        
        success = update_tracked_series(DB_PATH, series_id, **data)
        
        if not success:
            return jsonify({'error': 'Series not found or no changes made'}), 404
        
        series = get_tracked_series_by_id(DB_PATH, series_id)
        
        return jsonify({
            'status': 'ok',
            'message': 'Series updated',
            'series': series
        })
        
    except Exception as e:
        logger.error(f"Update tracked series error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/user/<username>/tracked-series/<int:series_id>', methods=['DELETE'])
def delete_user_tracked_series(username: str, series_id: int):
    """Remove a series from tracking."""
    try:
        from user_schema import delete_tracked_series, get_tracked_series_by_id
        
        series = get_tracked_series_by_id(DB_PATH, series_id)
        if not series:
            return jsonify({'error': 'Series not found'}), 404
        
        title = series.get('title', 'Unknown')
        success = delete_tracked_series(DB_PATH, series_id)
        
        return jsonify({
            'status': 'ok',
            'message': f"Removed '{title}' from tracked series"
        })
        
    except Exception as e:
        logger.error(f"Delete tracked series error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/user/<username>/tracked-series/by-title/<title>', methods=['GET'])
def get_tracked_series_by_title_endpoint(username: str, title: str):
    """Get a tracked series by title (fuzzy match)."""
    try:
        from user_schema import get_or_create_user, get_tracked_series_by_title
        
        user_id = get_or_create_user(DB_PATH, username)
        series = get_tracked_series_by_title(DB_PATH, user_id, title)
        
        if not series:
            return jsonify({'error': f'Series not found: {title}'}), 404
        
        # Parse JSON fields
        if series.get('available_services'):
            try:
                series['available_services'] = json.loads(series['available_services'])
            except json.JSONDecodeError:
                pass
        if series.get('manual_progress'):
            try:
                series['manual_progress'] = json.loads(series['manual_progress'])
            except json.JSONDecodeError:
                pass
        
        return jsonify(series)
        
    except Exception as e:
        logger.error(f"Get tracked series by title error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/user/<username>/tracked-series/by-title/<title>/status', methods=['PUT'])
def update_tracking_status_endpoint(username: str, title: str):
    """
    Update tracking status for a series by title.
    
    Body params:
        status: New tracking status (watching, finished, dropped, on_hold)
    """
    try:
        from user_schema import get_or_create_user, update_tracking_status as update_ts
        
        data = request.get_json() or {}
        new_status = data.get('status')
        
        if not new_status:
            return jsonify({'error': 'Missing required field: status'}), 400
        
        user_id = get_or_create_user(DB_PATH, username)
        result = update_ts(DB_PATH, user_id, title, new_status)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify({
            'status': 'ok',
            'message': f"Updated '{title}' to {new_status}",
            'series': result
        })
        
    except Exception as e:
        logger.error(f"Update tracking status error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/user/<username>/tracked-series/by-title/<title>/progress', methods=['PUT'])
def update_manual_progress_endpoint(username: str, title: str):
    """
    Update manual progress for a series.
    
    Body params:
        watched_through: {season, episode} - Everything up to this is watched
        additional_watched: [{season, episode}, ...] - Additional individual episodes
        source_note: Explanation (e.g., "Originally watched on Amazon Prime")
    """
    try:
        from user_schema import get_or_create_user, update_manual_progress as update_mp
        
        data = request.get_json() or {}
        
        if not data:
            return jsonify({'error': 'Missing progress data'}), 400
        
        user_id = get_or_create_user(DB_PATH, username)
        result = update_mp(DB_PATH, user_id, title, data)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify({
            'status': 'ok',
            'message': f"Updated manual progress for '{title}'",
            'series': result
        })
        
    except Exception as e:
        logger.error(f"Update manual progress error: {e}")
        return jsonify({'error': str(e)}), 500


# Initialize database on startup
init_database()

# Extend with user tables
try:
    from user_schema import extend_database_with_user_tables
    extend_database_with_user_tables(DB_PATH)
except ImportError:
    logger.warning("Could not import user_schema module")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5126, debug=True)

