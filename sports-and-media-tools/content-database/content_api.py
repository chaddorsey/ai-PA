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


# Initialize database on startup
init_database()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5126, debug=True)

