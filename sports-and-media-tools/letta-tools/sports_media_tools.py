#!/usr/bin/env python3
"""
Sports & Media Control Tools for Letta Agent

These tools enable a Letta agent to:
- Query ESPN API for current/upcoming sports games
- Control Roku TV via ECP (External Control Protocol)
- Control FIOS cable box via Flipper Zero IR
- Orchestrate end-to-end "watch the game" flows

All tools follow Letta tool compliance requirements:
- Imports inside functions
- Dict[str, Any] return types
- No nested def statements
- Basic JSON types for parameters
"""

from typing import Dict, Any, Optional


def query_sports_games(
    team: Optional[str] = None,
    league: Optional[str] = None,
    include_finished: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Query the sports service for current and upcoming games.
    
    This tool fetches game information from ESPN via the sports-service.
    You can query by team name, league, or get all games. The service
    returns game details including broadcast network, channel numbers,
    and streaming service info.
    
    Args:
        team: Team name to search for (e.g., "patriots", "celtics", "red sox").
              Partial matches work. Leave empty to get all games.
        league: Filter by league (e.g., "nfl", "nba", "mlb", "nhl", "ncaaf", "ncaab").
                Leave empty for all leagues.
        include_finished: Whether to include finished games. Defaults to False.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - games: List of game objects with team info, broadcast details, channels
        - game_count: Number of games returned
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST - immediately after docstring
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Set defaults
        if include_finished is None:
            include_finished = False
        
        # Sports service URL (Docker internal network)
        sports_service_url = "http://sports-service:5123"
        
        # Determine which endpoint to use
        if team:
            # Team-specific lookup
            response = requests.get(
                f"{sports_service_url}/team/{team}",
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('found'):
                game = data.get('game', {})
                games = [game] if game else []
            else:
                games = []
        elif league:
            # League-specific lookup
            response = requests.get(
                f"{sports_service_url}/games/{league}",
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            games = data.get('games', [])
        else:
            # All games
            response = requests.get(
                f"{sports_service_url}/games",
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            games = data.get('games', [])
        
        # Filter out finished games if requested
        if not include_finished:
            games = [g for g in games if g.get('state') != 'post']
        
        # Format games for readable output
        formatted_games = []
        for game in games:
            formatted_game = {
                'short_name': game.get('short_name'),
                'name': game.get('name'),
                'league': game.get('league', '').upper(),
                'state': game.get('state'),
                'status_detail': game.get('status_detail'),
                'broadcast_network': game.get('broadcast_network'),
                'channel': game.get('channel'),
                'streaming_service': game.get('streaming_service'),
                'home_team': game.get('home_team', {}).get('name'),
                'away_team': game.get('away_team', {}).get('name'),
                # Availability info
                'is_available': game.get('is_available', True),
                'watch_method': game.get('watch_method'),  # "cable" or "streaming"
                'unavailable_reason': game.get('unavailable_reason'),
                'is_espn_plus_only': game.get('is_espn_plus_only', False),
            }
            formatted_games.append(formatted_game)
        
        return {
            'status': 'ok',
            'games': formatted_games,
            'game_count': len(formatted_games),
            'query': {'team': team, 'league': league}
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Sports service request failed: {e}")
        return {
            'status': 'error',
            'games': [],
            'game_count': 0,
            'error_message': f"Failed to connect to sports service: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error querying sports games: {e}")
        return {
            'status': 'error',
            'games': [],
            'game_count': 0,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def get_channel_for_game(
    team: Optional[str] = None,
    network: Optional[str] = None
) -> Dict[str, Any]:
    """
    Look up the FIOS channel for a specific game or network.
    
    Use this tool to find what channel a game is on, or to look up
    a network's channel number. Returns both HD and SD channel numbers.
    
    Args:
        team: Team name to look up (e.g., "patriots"). The tool will find
              the game and return its broadcast channel.
        network: Network name to look up directly (e.g., "ESPN", "CBS", "FOX").
                 Use this if you already know the network.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - channel: HD channel number (preferred)
        - channel_sd: SD channel number
        - network: Network name
        - game_name: Game name (if team lookup)
        - streaming_service: Streaming info if applicable
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        sports_service_url = "http://sports-service:5123"
        
        if team:
            # Look up game for team
            response = requests.post(
                f"{sports_service_url}/lookup",
                json={'team': team},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                return {
                    'status': 'ok',
                    'channel': data.get('channel'),
                    'channel_sd': data.get('channel_sd'),
                    'network': data.get('network'),
                    'game_name': data.get('game_name'),
                    'game_state': data.get('state'),
                    'streaming_service': data.get('streaming_service'),
                    'description': data.get('description')
                }
            else:
                return {
                    'status': 'error',
                    'channel': None,
                    'error_message': data.get('error', f"No game found for {team}")
                }
        
        elif network:
            # Direct network lookup
            response = requests.get(
                f"{sports_service_url}/channel/{network}",
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('found'):
                return {
                    'status': 'ok',
                    'channel': data.get('channel'),
                    'channel_sd': data.get('channel_sd'),
                    'network': network,
                    'info': data.get('info')
                }
            else:
                return {
                    'status': 'error',
                    'channel': None,
                    'error_message': f"No channel mapping for network: {network}"
                }
        
        else:
            return {
                'status': 'error',
                'channel': None,
                'error_message': "Must provide either 'team' or 'network' parameter"
            }
            
    except Exception as e:
        logger.error(f"Error looking up channel: {e}")
        return {
            'status': 'error',
            'channel': None,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def control_roku_tv(
    action: str,
    app_name: Optional[str] = None,
    key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Control the Roku TV via its External Control Protocol (ECP).
    
    This tool can power the TV on/off, launch apps, and send remote
    control keypresses. Use this for streaming app control.
    
    Args:
        action: The action to perform. One of:
                - "power_on" or "power_off": Control TV power
                - "launch_app": Launch a streaming app (requires app_name)
                - "keypress": Send a remote key (requires key)
                - "home": Go to Roku home screen
                - "input_hdmi3": Switch to HDMI 3 (FIOS cable box)
        app_name: Name of app to launch (for "launch_app" action).
                  Options: netflix, hulu, youtube, disney, prime, max,
                  peacock, paramount, espn, apple tv, plex, tubi
        key: Key to press (for "keypress" action).
             Options: up, down, left, right, select, back, home,
             play, pause, fwd, rev, info, power
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - action: The action that was performed
        - message: Description of what happened
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import json
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Roku TV configuration
        roku_ip = "192.168.7.187"
        roku_port = 8060
        roku_base_url = f"http://{roku_ip}:{roku_port}"
        
        # Roku app IDs
        roku_apps = {
            "netflix": 12,
            "hulu": 2285,
            "youtube": 837,
            "disney": 291097,
            "prime": 13,
            "max": 61322,
            "peacock": 593099,
            "paramount": 31440,
            "espn": 34376,
            "apple tv": 551012,
            "plex": 13535,
            "tubi": 41468
        }
        
        # Key mapping
        key_mapping = {
            "up": "Up",
            "down": "Down",
            "left": "Left",
            "right": "Right",
            "select": "Select",
            "ok": "Select",
            "back": "Back",
            "home": "Home",
            "play": "Play",
            "pause": "Pause",
            "fwd": "Fwd",
            "rev": "Rev",
            "info": "Info",
            "power": "Power",
            "power_on": "PowerOn",
            "power_off": "PowerOff",
        }
        
        action_lower = action.lower().replace(" ", "_").replace("-", "_")
        
        if action_lower in ["power_on", "poweron"]:
            # Send PowerOn keypress
            response = requests.post(
                f"{roku_base_url}/keypress/PowerOn",
                timeout=5
            )
            return {
                'status': 'ok',
                'action': 'power_on',
                'message': 'Sent power on command to Roku TV'
            }
            
        elif action_lower in ["power_off", "poweroff"]:
            response = requests.post(
                f"{roku_base_url}/keypress/PowerOff",
                timeout=5
            )
            return {
                'status': 'ok',
                'action': 'power_off',
                'message': 'Sent power off command to Roku TV'
            }
            
        elif action_lower == "home":
            response = requests.post(
                f"{roku_base_url}/keypress/Home",
                timeout=5
            )
            return {
                'status': 'ok',
                'action': 'home',
                'message': 'Sent Home command to Roku TV'
            }
            
        elif action_lower in ["input_hdmi3", "hdmi3", "cable", "fios"]:
            # Switch to HDMI3 input for FIOS cable box
            response = requests.post(
                f"{roku_base_url}/keypress/InputHDMI3",
                timeout=5
            )
            return {
                'status': 'ok',
                'action': 'input_hdmi3',
                'message': 'Switched to HDMI 3 input (FIOS cable box)'
            }
            
        elif action_lower == "launch_app":
            if not app_name:
                return {
                    'status': 'error',
                    'action': 'launch_app',
                    'error_message': "app_name is required for launch_app action"
                }
            
            app_name_lower = app_name.lower().strip()
            
            # Find app ID
            app_id = None
            for name, aid in roku_apps.items():
                if app_name_lower == name or app_name_lower in name:
                    app_id = aid
                    break
            
            if not app_id:
                return {
                    'status': 'error',
                    'action': 'launch_app',
                    'error_message': f"Unknown app: {app_name}. Available: {', '.join(roku_apps.keys())}"
                }
            
            response = requests.post(
                f"{roku_base_url}/launch/{app_id}",
                timeout=10
            )
            return {
                'status': 'ok',
                'action': 'launch_app',
                'app_name': app_name,
                'app_id': app_id,
                'message': f'Launched {app_name} on Roku TV'
            }
            
        elif action_lower == "keypress":
            if not key:
                return {
                    'status': 'error',
                    'action': 'keypress',
                    'error_message': "key is required for keypress action"
                }
            
            key_lower = key.lower().strip()
            roku_key = key_mapping.get(key_lower, key.capitalize())
            
            response = requests.post(
                f"{roku_base_url}/keypress/{roku_key}",
                timeout=5
            )
            return {
                'status': 'ok',
                'action': 'keypress',
                'key': roku_key,
                'message': f'Sent keypress: {roku_key}'
            }
            
        else:
            return {
                'status': 'error',
                'action': action,
                'error_message': f"Unknown action: {action}. Valid actions: power_on, power_off, launch_app, keypress, home, input_hdmi3"
            }
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Roku TV request failed: {e}")
        return {
            'status': 'error',
            'action': action,
            'error_message': f"Failed to connect to Roku TV at {roku_ip}: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error controlling Roku TV: {e}")
        return {
            'status': 'error',
            'action': action,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def send_fios_ir_command(
    command: str
) -> Dict[str, Any]:
    """
    Send an IR command to the FIOS cable box via Flipper Zero.
    
    This tool sends infrared commands to control the Verizon FIOS
    cable box. Use this for individual button presses.
    
    Args:
        command: The IR command to send. Available commands:
                 - Navigation: Ok, Menu, Guide, Info, Exit, Up, Down, Left, Right
                 - Channel: Channel_up, Channel_down
                 - Numbers: 0, 1, 2, 3, 4, 5, 6, 7, 8, 9
                 - Power: Power
                 - Volume: Vol_up, Vol_down, Mute
                 - Playback: Play_pause, Ffwd, Rev, Stop, Rec
                 - Other: Last, Favorites, Input
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - command: The command that was sent
        - message: Description of result
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Use host.docker.internal since Flipper API runs on host (not Docker)
        flipper_api_url = "http://host.docker.internal:5124"
        
        response = requests.post(
            f"{flipper_api_url}/ir/{command}",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get('success'):
            return {
                'status': 'ok',
                'command': command,
                'message': data.get('message', f'Sent IR command: {command}')
            }
        else:
            return {
                'status': 'error',
                'command': command,
                'error_message': data.get('error', 'Failed to send command')
            }
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Flipper API request failed: {e}")
        return {
            'status': 'error',
            'command': command,
            'error_message': f"Failed to connect to Flipper API: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error sending IR command: {e}")
        return {
            'status': 'error',
            'command': command,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def tune_fios_channel(
    channel: int
) -> Dict[str, Any]:
    """
    Tune the FIOS cable box to a specific channel number.
    
    This tool sends the digit sequence to tune to a channel.
    It handles multi-digit channels automatically.
    
    Args:
        channel: The channel number to tune to (1-9999).
                 Use HD channels (500+) for best quality.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - channel: The channel that was tuned to
        - message: Description of result
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        if channel < 1 or channel > 9999:
            return {
                'status': 'error',
                'channel': channel,
                'error_message': 'Channel number must be between 1 and 9999'
            }
        
        # Use host.docker.internal since Flipper API runs on host (not Docker)
        flipper_api_url = "http://host.docker.internal:5124"
        
        response = requests.post(
            f"{flipper_api_url}/channel/{channel}",
            timeout=30  # Longer timeout for multi-digit channels
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get('success'):
            return {
                'status': 'ok',
                'channel': channel,
                'message': data.get('message', f'Tuned to channel {channel}')
            }
        else:
            return {
                'status': 'error',
                'channel': channel,
                'error_message': data.get('error', 'Failed to tune channel')
            }
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Flipper API request failed: {e}")
        return {
            'status': 'error',
            'channel': channel,
            'error_message': f"Failed to connect to Flipper API: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error tuning channel: {e}")
        return {
            'status': 'error',
            'channel': channel,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def watch_game(
    team: str
) -> Dict[str, Any]:
    """
    Find a team's game and tune the TV to watch it.
    
    This is a high-level orchestration tool that:
    1. Looks up the team's current or upcoming game
    2. Determines if it's on cable or streaming
    3. Switches the TV to the appropriate input
    4. Tunes to the channel or launches the streaming app
    
    Args:
        team: The team name to watch (e.g., "patriots", "celtics", "red sox").
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - game: Game information
        - action_taken: Description of what was done
        - channel: Channel tuned to (if cable)
        - app: App launched (if streaming)
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import time
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        sports_service_url = "http://sports-service:5123"
        # Use host.docker.internal since Flipper API runs on host (not Docker)
        flipper_api_url = "http://host.docker.internal:5124"
        roku_ip = "192.168.7.187"
        roku_port = 8060
        roku_base_url = f"http://{roku_ip}:{roku_port}"
        
        # Step 1: Look up the game
        response = requests.post(
            f"{sports_service_url}/lookup",
            json={'team': team},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        if not data.get('success'):
            return {
                'status': 'error',
                'game': None,
                'error_message': data.get('error', f"No game found for {team}")
            }
        
        game_name = data.get('game_name')
        network = data.get('network')
        channel = data.get('channel')
        streaming = data.get('streaming_service')
        game_state = data.get('state')
        
        # Step 2: Determine if streaming or cable
        if streaming and streaming.get('roku_app_id'):
            # It's a streaming game - launch the app
            app_id = streaming.get('roku_app_id')
            service_name = streaming.get('service')
            
            # Power on TV first
            requests.post(f"{roku_base_url}/keypress/PowerOn", timeout=5)
            time.sleep(1)
            
            # Launch the streaming app
            requests.post(f"{roku_base_url}/launch/{app_id}", timeout=10)
            
            return {
                'status': 'ok',
                'game': game_name,
                'network': network,
                'game_state': game_state,
                'action_taken': f"Launched {service_name} app to watch {game_name}",
                'app': service_name,
                'streaming': True
            }
        
        elif channel:
            # It's on cable - switch to FIOS and tune
            
            # Power on TV
            requests.post(f"{roku_base_url}/keypress/PowerOn", timeout=5)
            time.sleep(1)
            
            # Switch to HDMI3 (FIOS)
            requests.post(f"{roku_base_url}/keypress/InputHDMI3", timeout=5)
            time.sleep(2)
            
            # Tune to channel
            tune_response = requests.post(
                f"{flipper_api_url}/channel/{channel}",
                timeout=30
            )
            tune_data = tune_response.json()
            
            if not tune_data.get('success'):
                return {
                    'status': 'error',
                    'game': game_name,
                    'error_message': f"Failed to tune to channel {channel}: {tune_data.get('error')}"
                }
            
            return {
                'status': 'ok',
                'game': game_name,
                'network': network,
                'game_state': game_state,
                'action_taken': f"Switched to FIOS and tuned to channel {channel} ({network}) to watch {game_name}",
                'channel': channel,
                'streaming': False
            }
        
        else:
            return {
                'status': 'error',
                'game': game_name,
                'network': network,
                'error_message': f"Cannot determine how to watch {game_name} on {network} - no channel or streaming info available"
            }
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed during watch_game: {e}")
        return {
            'status': 'error',
            'game': None,
            'error_message': f"Service connection error: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error in watch_game: {e}")
        return {
            'status': 'error',
            'game': None,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def launch_streaming_content(
    title: str,
    app: Optional[str] = None,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    content_id: Optional[str] = None,
    profile: Optional[int] = None
) -> Dict[str, Any]:
    """
    Launch streaming content on the Roku TV with deep linking support.
    
    This tool can play movies, TV series, or specific episodes on streaming
    apps like Netflix, Prime Video, Hulu, etc. For "play next episode",
    just provide the series title - the app will resume where you left off.
    
    CONFIRMED WORKING:
    - Netflix: Direct deep link with numeric content IDs
    - Hulu: Direct deep link with JustWatch UUIDs (e.g., "60da223c-d2a0-411a-95c9-665a839371f9")
    - Apple TV+: URL-encoded full URLs with mediaType=live for auto-play
    - Max (HBO): Direct deep link with HBO URN IDs
    - Prime Video: Direct deep link with Amazon GTI IDs
    - Disney+: Direct deep link with content IDs
    - YouTube: Direct deep link with video IDs
    
    USES IN-APP SEARCH (app launches, then searches within app):
    - ESPN: Uses in-app search (Left→Up→Select to open search, then types query)
    
    USES ROKU UNIVERSAL SEARCH FALLBACK:
    - Fox Sports, NBC Sports, History Channel
    
    Args:
        title: The title to search for or play (e.g., "Stranger Things", 
               "The Office", "Wednesday"). Required.
        app: Streaming app to use. Options: netflix, prime, hulu, disney,
             max, peacock, paramount, youtube, youtube_tv, espn, fox_sports,
             nbc_sports, history, apple. Defaults to netflix if not specified.
        season: Season number for specific episode playback (e.g., 1 for S1).
                Leave empty to play from where you left off.
        episode: Episode number for specific episode playback (e.g., 3 for E3).
                 Must be used with season parameter.
        content_id: Direct Netflix/streaming content ID if known (e.g., "80057281").
                    Bypasses title lookup if provided.
        profile: Profile number to select (1 for first profile, 2 for second, etc.).
                 If not specified, defaults to 1 (first/main profile).
                 Set to 0 to skip profile selection entirely.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - title: The title being played
        - app: The streaming app used
        - content_id: The content ID used for deep linking
        - message: Description of what happened
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import logging
    import re
    
    logger = logging.getLogger(__name__)
    
    try:
        # Roku configuration
        roku_ip = "192.168.7.187"
        roku_port = 8060
        roku_base_url = f"http://{roku_ip}:{roku_port}"
        
        # Streaming app IDs and their content parameter names
        streaming_apps = {
            "netflix": {"id": 12, "param": "contentId"},
            "prime": {"id": 13, "param": "contentId"},
            "hulu": {"id": 2285, "param": "contentId"},
            "disney": {"id": 291097, "param": "contentId"},
            "max": {"id": 61322, "param": "contentId"},
            "peacock": {"id": 593099, "param": "contentId"},
            "paramount": {"id": 31440, "param": "contentId"},
            "youtube": {"id": 837, "param": "contentId"},
            "apple": {"id": 551012, "param": "contentId"},
            "espn": {"id": 34376, "param": "contentId"},
            "youtube_tv": {"id": 195316, "param": "contentId"},
            "fox_sports": {"id": 95307, "param": "contentId"},
            "nbc_sports": {"id": 53725, "param": "contentId"},
            "history": {"id": 35059, "param": "contentId"},
        }
        
        # Popular content database - expanded with multiple streaming services
        # Format: lowercase title -> {content_id, type, app}
        # Content IDs: Netflix uses numeric IDs, Apple TV uses "umc.cmc.xxxxx" format
        content_database = {
            # === APPLE TV+ SERIES ===
            "slow horses": {"content_id": "umc.cmc.2szz3fdt71tl1ulnbp8utgq5o", "type": "series", "app": "apple"},
            "ted lasso": {"content_id": "umc.cmc.vtoh0mn0xn7t3c643xqonfzy", "type": "series", "app": "apple"},
            "severance": {"content_id": "umc.cmc.1srk2goyh2q2zdxcx605w8vtx", "type": "series", "app": "apple"},
            "the morning show": {"content_id": "umc.cmc.25tn3v8ku4b39tr6ccgb8nl6m", "type": "series", "app": "apple"},
            "foundation": {"content_id": "umc.cmc.5983fipzqbicvrve6jdfep4x3", "type": "series", "app": "apple"},
            "for all mankind": {"content_id": "umc.cmc.6wsi780sz5tdbqcf11k76mkp7", "type": "series", "app": "apple"},
            "shrinking": {"content_id": "umc.cmc.apszaflnk25p2tezo92tranf", "type": "series", "app": "apple"},
            "silo": {"content_id": "umc.cmc.3yksgc857px0k0rqe5zd4jice", "type": "series", "app": "apple"},
            "monarch": {"content_id": "umc.cmc.41l0od5vjx8lir25b8qetmfx0", "type": "series", "app": "apple"},
            "pachinko": {"content_id": "umc.cmc.5vuz7a7lurqby2w8wyygjp77d", "type": "series", "app": "apple"},
            "black bird": {"content_id": "umc.cmc.555hazmlr7l5rfu0xey8h0l2i", "type": "series", "app": "apple"},
            "presumed innocent": {"content_id": "umc.cmc.1fjflc1v7ry6b2ctpc47aevy", "type": "series", "app": "apple"},
            "dark matter": {"content_id": "umc.cmc.1h4hhifuqdgqt8rdi7bfpf2lg", "type": "series", "app": "apple"},
            "masters of the air": {"content_id": "umc.cmc.2visvcivrbykxwlxqbxjikv0z", "type": "series", "app": "apple"},
            
            # === HBO MAX SERIES ===
            "house of the dragon": {"content_id": "urn:hbo:series:GYf7wnAr3wY7CZgEAAAAI", "type": "series", "app": "max"},
            "the last of us": {"content_id": "urn:hbo:series:GYtMwdwOjy8JjjwEAAAAK", "type": "series", "app": "max"},
            "euphoria": {"content_id": "urn:hbo:series:GXqWVuAopN5uDwgEAAAAB", "type": "series", "app": "max"},
            "succession": {"content_id": "urn:hbo:series:GV7xwpQPV04SPCwEAAAAH", "type": "series", "app": "max"},
            "white lotus": {"content_id": "urn:hbo:series:GYKKfUQBBk44HJgEAAAAN", "type": "series", "app": "max"},
            "the white lotus": {"content_id": "urn:hbo:series:GYKKfUQBBk44HJgEAAAAN", "type": "series", "app": "max"},
            "game of thrones": {"content_id": "urn:hbo:series:GVU2cAAPSJoNJjhsJATwo", "type": "series", "app": "max"},
            "true detective": {"content_id": "urn:hbo:series:GVU2dAAPDNoJPjwEAAAAN", "type": "series", "app": "max"},
            "the penguin": {"content_id": "urn:hbo:series:GZBVaggLt-IPCwgEAAAAJ", "type": "series", "app": "max"},
            "hacks": {"content_id": "urn:hbo:series:GYBEPMQd8HI7DwwEAAAAB", "type": "series", "app": "max"},
            "barry": {"content_id": "urn:hbo:series:GV1hctg7rpIVHwgEAAAAN", "type": "series", "app": "max"},
            "curb your enthusiasm": {"content_id": "urn:hbo:series:GVU1qPArQz44DwgEAAAAH", "type": "series", "app": "max"},
            
            # === PRIME VIDEO SERIES ===
            "the boys": {"content_id": "0LHEN4ND5VT20Q9KDJ1J6Z6UQP", "type": "series", "app": "prime"},
            "fallout": {"content_id": "0H1A1RYAFZK0GVRR1DRNTFR96H", "type": "series", "app": "prime"},
            "reacher": {"content_id": "0PMMXZ9R9SCPQ5WPZ45DJ9CQYF", "type": "series", "app": "prime"},
            "the wheel of time": {"content_id": "0H0X8PO9ZDV5VCWUMXRFUE2HD8", "type": "series", "app": "prime"},
            "the expanse": {"content_id": "0SGGMZ46GY3GVN4CFNHTGQTBQM", "type": "series", "app": "prime"},
            "jack ryan": {"content_id": "0LTXPP5B8NU68HRNTMZANFJB4E", "type": "series", "app": "prime"},
            "the marvelous mrs maisel": {"content_id": "0MFDU0PMXK54CVAUPIVHBQWVJ6", "type": "series", "app": "prime"},
            "invincible": {"content_id": "0M0EPUE7UNR1ZYEJSVZJ71Y12R", "type": "series", "app": "prime"},
            "rings of power": {"content_id": "0MK2P59MZXV0NJ4L6X4NX8LWGK", "type": "series", "app": "prime"},
            "lord of the rings": {"content_id": "0MK2P59MZXV0NJ4L6X4NX8LWGK", "type": "series", "app": "prime"},
            "upload": {"content_id": "0R8N8MJJV1H4M61H4T8TLXBQBW", "type": "series", "app": "prime"},
            
            # === NETFLIX SERIES ===
            "stranger things": {"content_id": "80057281", "type": "series", "app": "netflix"},
            "wednesday": {"content_id": "81231974", "type": "series", "app": "netflix"},
            "squid game": {"content_id": "81040344", "type": "series", "app": "netflix"},
            "the witcher": {"content_id": "80189685", "type": "series", "app": "netflix"},
            "the crown": {"content_id": "80025678", "type": "series", "app": "netflix"},
            "bridgerton": {"content_id": "80232398", "type": "series", "app": "netflix"},
            "ozark": {"content_id": "80117552", "type": "series", "app": "netflix"},
            "money heist": {"content_id": "80192098", "type": "series", "app": "netflix"},
            "la casa de papel": {"content_id": "80192098", "type": "series", "app": "netflix"},
            "breaking bad": {"content_id": "70143836", "type": "series", "app": "netflix"},
            "better call saul": {"content_id": "80021955", "type": "series", "app": "netflix"},
            "the office": {"content_id": "70136120", "type": "series", "app": "netflix"},
            "friends": {"content_id": "70153404", "type": "series", "app": "netflix"},
            "cobra kai": {"content_id": "81002370", "type": "series", "app": "netflix"},
            "you": {"content_id": "80211991", "type": "series", "app": "netflix"},
            "black mirror": {"content_id": "70264888", "type": "series", "app": "netflix"},
            "peaky blinders": {"content_id": "80002479", "type": "series", "app": "netflix"},
            "dark": {"content_id": "80100172", "type": "series", "app": "netflix"},
            "the umbrella academy": {"content_id": "80186863", "type": "series", "app": "netflix"},
            "lupin": {"content_id": "80994082", "type": "series", "app": "netflix"},
            "emily in paris": {"content_id": "81037371", "type": "series", "app": "netflix"},
            "outer banks": {"content_id": "80236318", "type": "series", "app": "netflix"},
            "arcane": {"content_id": "81435684", "type": "series", "app": "netflix"},
            "dahmer": {"content_id": "81287562", "type": "series", "app": "netflix"},
            "beef": {"content_id": "81447461", "type": "series", "app": "netflix"},
            "the night agent": {"content_id": "81073357", "type": "series", "app": "netflix"},
            "ginny and georgia": {"content_id": "81025696", "type": "series", "app": "netflix"},
            "manifest": {"content_id": "80191522", "type": "series", "app": "netflix"},
            "virgin river": {"content_id": "80240027", "type": "series", "app": "netflix"},
            "3 body problem": {"content_id": "81024821", "type": "series", "app": "netflix"},
            "the gentlemen": {"content_id": "81642941", "type": "series", "app": "netflix"},
            "one piece": {"content_id": "80217863", "type": "series", "app": "netflix"},
            "baby reindeer": {"content_id": "81219887", "type": "series", "app": "netflix"},
            "ripley": {"content_id": "81684801", "type": "series", "app": "netflix"},
            "the diplomat": {"content_id": "81286023", "type": "series", "app": "netflix"},
            "bodkin": {"content_id": "81560141", "type": "series", "app": "netflix"},
            
            # === DISNEY+ SERIES ===
            "the mandalorian": {"content_id": "4obxOz3NQXH8SWQY0jBpvQ", "type": "series", "app": "disney"},
            "andor": {"content_id": "6I0bM6bY84UJ9qeCWXZ0fp", "type": "series", "app": "disney"},
            "loki": {"content_id": "2afdyxDFPbVNqUDZ9RDpGb", "type": "series", "app": "disney"},
            "ahsoka": {"content_id": "5dWAE4mspVJAYg4yyCJEwj", "type": "series", "app": "disney"},
            "wandavision": {"content_id": "5FDJGJS9vPpWYQDPlS3Exq", "type": "series", "app": "disney"},
            "the bear": {"content_id": "3P1PSCQ0QDoQqWLrWW9wly", "type": "series", "app": "disney"},
            "shogun": {"content_id": "70DXVb8IgXXvTTSHjXGpq2", "type": "series", "app": "disney"},
            "only murders in the building": {"content_id": "6gMfVNWdKvOy1P88wCfhXr", "type": "series", "app": "disney"},
            
            # === PARAMOUNT+ SERIES ===
            "yellowstone": {"content_id": "wwLLZQp6nLuzYjKNnE7Xz_mOFYxW4XsF", "type": "series", "app": "paramount"},
            "1883": {"content_id": "_2GZ2x3dxfB6gLKD4xNx__g6V2PnzXqR", "type": "series", "app": "paramount"},
            "1923": {"content_id": "3wzWC96TmPPy8nT9LVtJNf_82FTZC6GG", "type": "series", "app": "paramount"},
            "star trek strange new worlds": {"content_id": "vxOO2q17M_G_pJbZb1T2_zlPhYlZ5lpT", "type": "series", "app": "paramount"},
            "tulsa king": {"content_id": "e6p6Z8RTnLEbf2pwQ6N0r3_2NZCCwF0l", "type": "series", "app": "paramount"},
            "mayor of kingstown": {"content_id": "WQD4KF1xGjhBKcMcLknCy_x1Q7wvvFT5", "type": "series", "app": "paramount"},
            
            # === PEACOCK SERIES ===
            "poker face": {"content_id": "5730116286607296112", "type": "series", "app": "peacock"},
            "dr death": {"content_id": "3665872111608987112", "type": "series", "app": "peacock"},
            "bel-air": {"content_id": "2914108888550310112", "type": "series", "app": "peacock"},
            
            # === MOVIES (Various Services) ===
            "the irishman": {"content_id": "80175798", "type": "movie", "app": "netflix"},
            "glass onion": {"content_id": "81458416", "type": "movie", "app": "netflix"},
            "knives out": {"content_id": "81458416", "type": "movie", "app": "netflix"},
            "don't look up": {"content_id": "81252357", "type": "movie", "app": "netflix"},
            "red notice": {"content_id": "81161626", "type": "movie", "app": "netflix"},
            "the adam project": {"content_id": "81309354", "type": "movie", "app": "netflix"},
            "extraction": {"content_id": "80230399", "type": "movie", "app": "netflix"},
            "bird box": {"content_id": "80196789", "type": "movie", "app": "netflix"},
            "all quiet on the western front": {"content_id": "81260280", "type": "movie", "app": "netflix"},
            "the gray man": {"content_id": "81160697", "type": "movie", "app": "netflix"},
            "leave the world behind": {"content_id": "81314956", "type": "movie", "app": "netflix"},
            "the killer": {"content_id": "81204962", "type": "movie", "app": "netflix"},
            "heart of stone": {"content_id": "81264300", "type": "movie", "app": "netflix"},
            "rebel moon": {"content_id": "81313293", "type": "movie", "app": "netflix"},
            "killers of the flower moon": {"content_id": "umc.cmc.5x1fg9g8mhpqj5vx0j6hehs87", "type": "movie", "app": "apple"},
            "napoleon": {"content_id": "umc.cmc.2xfuuq8s1jl33t24xq1bfgr4l", "type": "movie", "app": "apple"},
        }
        
        # Default to Netflix if no app specified
        if app is None:
            app = "netflix"
        
        app_lower = app.lower().strip()
        
        # Normalize app name
        app_aliases = {
            "amazon": "prime",
            "amazon prime": "prime",
            "prime video": "prime",
            "hbo": "max",
            "hbo max": "max",
            "disney+": "disney",
            "disney plus": "disney",
            "paramount+": "paramount",
            "paramount plus": "paramount",
            "apple tv": "apple",
            "apple tv+": "apple",
            "youtube tv": "youtube_tv",
            "youtubetv": "youtube_tv",
            "fox sports": "fox_sports",
            "foxsports": "fox_sports",
            "nbc sports": "nbc_sports",
            "nbcsports": "nbc_sports",
            "history channel": "history",
            "the history channel": "history",
            "espn+": "espn",
            "espn plus": "espn",
        }
        app_lower = app_aliases.get(app_lower, app_lower)
        
        if app_lower not in streaming_apps:
            return {
                'status': 'error',
                'title': title,
                'app': app,
                'error_message': f"Unknown streaming app: {app}. Available: {', '.join(streaming_apps.keys())}"
            }
        
        app_info = streaming_apps[app_lower]
        app_id = app_info["id"]
        
        # Determine content ID
        resolved_content_id = content_id
        content_type = "series"  # default
        detected_app = None
        
        if not resolved_content_id:
            # Try to look up in our database
            title_lower = title.lower().strip()
            
            # Try exact match first
            if title_lower in content_database:
                db_entry = content_database[title_lower]
                resolved_content_id = db_entry["content_id"]
                content_type = db_entry["type"]
                detected_app = db_entry.get("app")
            else:
                # Try partial match
                for db_title, db_entry in content_database.items():
                    if title_lower in db_title or db_title in title_lower:
                        resolved_content_id = db_entry["content_id"]
                        content_type = db_entry["type"]
                        detected_app = db_entry.get("app")
                        break
        
        # If we found the content in database, use its app (unless user specified one)
        if detected_app and app == "netflix":  # netflix is the default
            app_lower = detected_app
            if app_lower in streaming_apps:
                app_info = streaming_apps[app_lower]
                app_id = app_info["id"]
        
        # Build the deep link URL
        use_roku_search = False
        
        if resolved_content_id:
            # Special handling for Apple TV+ - use URL-encoded full URL and mediaType=live for auto-play
            if app_lower == "apple":
                import urllib.parse
                # Apple TV+ works with full URL-encoded URLs
                if resolved_content_id.startswith("umc.cmc."):
                    # Build full Apple TV URL from content ID
                    apple_url = f"https://tv.apple.com/us/show/{title.lower().replace(' ', '-')}/{resolved_content_id}"
                    encoded_url = urllib.parse.quote(apple_url, safe='')
                elif resolved_content_id.startswith("http"):
                    encoded_url = urllib.parse.quote(resolved_content_id, safe='')
                else:
                    encoded_url = resolved_content_id
                
                # mediaType=live triggers auto-play on Apple TV+
                params = [f"contentId={encoded_url}", "mediaType=live"]
                action_desc = f"Playing {title} on Apple TV+"
            else:
                # Standard deep link format for other apps
                params = [f"contentId={resolved_content_id}"]
                
                # Add media type
                if season is not None and episode is not None:
                    params.append("mediaType=episode")
                    # Some apps support season/episode parameters
                    params.append(f"season={season}")
                    params.append(f"episode={episode}")
                    action_desc = f"Playing {title} S{season}E{episode}"
                elif season is not None:
                    params.append("mediaType=series")
                    params.append(f"season={season}")
                    action_desc = f"Playing {title} Season {season}"
                else:
                    params.append(f"mediaType={content_type}")
                    action_desc = f"Playing {title}"
            
            launch_url = f"{roku_base_url}/launch/{app_id}?{'&'.join(params)}"
        else:
            # No content ID found - use Roku universal search
            use_roku_search = True
            resolved_content_id = "roku_universal_search"
            action_desc = f"Searching for '{title}' via Roku universal search"
        
        # Power on TV first
        requests.post(f"{roku_base_url}/keypress/PowerOn", timeout=5)
        
        import time
        time.sleep(0.5)
        
        # Apps with unreliable deep linking - use alternative search methods
        # ESPN: Use in-app search (Roku universal search doesn't work for sports)
        # Fox Sports/NBC Sports/History: Use Roku universal search
        # NOTE: Hulu and Apple TV+ now work with direct deep linking
        apps_needing_in_app_search = ["espn"]
        apps_needing_roku_search = ["fox_sports", "nbc_sports", "history"]
        
        # Handle ESPN with in-app search (specific navigation sequence)
        if app_lower == "espn":
            # ESPN requires in-app search because:
            # 1. Direct deep links only go to home screen
            # 2. Roku universal search doesn't find ESPN+ content well
            
            # Launch ESPN app
            requests.post(f"{roku_base_url}/launch/{app_id}", timeout=10)
            
            # Wait for ESPN to fully load (it's very slow!)
            time.sleep(16)
            
            # Navigate to in-app search: Left (sidebar), Up (search icon), Select (open search)
            requests.post(f"{roku_base_url}/keypress/Left", timeout=5)
            time.sleep(0.5)
            requests.post(f"{roku_base_url}/keypress/Up", timeout=5)
            time.sleep(0.5)
            requests.post(f"{roku_base_url}/keypress/Select", timeout=5)
            time.sleep(2)  # Wait for search box to open
            
            # Type search term
            import urllib.parse
            for char in title:
                if char == ' ':
                    encoded = '%20'
                else:
                    encoded = urllib.parse.quote(char)
                requests.post(f"{roku_base_url}/keypress/Lit_{encoded}", timeout=2)
                time.sleep(0.12)
            
            time.sleep(2)  # Wait for search results
            
            # Navigate right to first result (8 steps to clear keyboard)
            for _ in range(8):
                requests.post(f"{roku_base_url}/keypress/Right", timeout=5)
                time.sleep(0.25)
            
            # Select the result
            requests.post(f"{roku_base_url}/keypress/Select", timeout=5)
            
            return {
                'status': 'ok',
                'title': title,
                'app': app_lower,
                'content_id': 'espn_in_app_search',
                'message': f"Launched ESPN and searched for '{title}'"
            }
        
        if app_lower in apps_needing_roku_search:
            use_roku_search = True
            action_desc = f"Searching for '{title}' via Roku universal search"
        
        if use_roku_search:
            # Use Roku's universal content search (works for all streaming services)
            # This navigates through Roku's interface to search and deep link
            
            # Step 1: Go to Home
            requests.post(f"{roku_base_url}/keypress/Home", timeout=5)
            time.sleep(2)
            
            # Step 2: Navigate to search (Down 7, Right 1)
            for _ in range(7):
                requests.post(f"{roku_base_url}/keypress/Down", timeout=5)
                time.sleep(0.25)
            requests.post(f"{roku_base_url}/keypress/Right", timeout=5)
            time.sleep(1)
            
            # Step 3: Type the search query
            import urllib.parse
            for char in title:
                if char == ' ':
                    encoded = '%20'
                else:
                    encoded = urllib.parse.quote(char)
                requests.post(f"{roku_base_url}/keypress/Lit_{encoded}", timeout=2)
                time.sleep(0.12)
            
            time.sleep(1)
            
            # Step 4: Navigate to first search result (Right 6 from keyboard)
            for _ in range(6):
                requests.post(f"{roku_base_url}/keypress/Right", timeout=5)
                time.sleep(0.25)
            
            # Step 5: Select the content to open its page
            requests.post(f"{roku_base_url}/keypress/Select", timeout=5)
            time.sleep(2)
            
            # Step 6: Select the deep link button (should be pre-selected)
            requests.post(f"{roku_base_url}/keypress/Select", timeout=5)
            time.sleep(1)
            
            # Return success
            result = {
                'status': 'ok',
                'title': title,
                'app': app_lower,
                'content_id': resolved_content_id,
                'message': f"Launched '{title}' via Roku universal search"
            }
            if season is not None:
                result['season'] = season
            if episode is not None:
                result['episode'] = episode
            return result
        
        # Standard deep link launch for apps with known content IDs
        launch_url = f"{roku_base_url}/launch/{app_id}?{'&'.join(params)}"
        response = requests.post(launch_url, timeout=10)
        
        if response.status_code in [200, 204]:
            # Handle profile selection for apps that show "Who's watching?" screen
            # Apps that typically have profile screens: Netflix, Disney+, Max, Prime, Hulu, Apple TV+
            apps_with_profiles = ["netflix", "disney", "max", "prime", "hulu", "paramount", "peacock", "apple"]
            
            if app_lower in apps_with_profiles and profile != 0:
                # Default to first profile if not specified
                profile_num = profile if profile is not None else 1
                
                # Wait for profile selection screen to appear
                time.sleep(3)
                
                # Navigate to the correct profile
                # Profiles are typically arranged horizontally, first one is selected by default
                if profile_num > 1:
                    # Navigate right to reach the desired profile
                    for _ in range(profile_num - 1):
                        requests.post(f"{roku_base_url}/keypress/Right", timeout=5)
                        time.sleep(0.3)
                
                # Select the profile
                requests.post(f"{roku_base_url}/keypress/Select", timeout=5)
                time.sleep(2)  # Wait for profile to load
                
                action_desc += f" (selected profile {profile_num})"
            
            result = {
                'status': 'ok',
                'title': title,
                'app': app_lower,
                'content_id': resolved_content_id,
                'message': action_desc
            }
            
            if season is not None:
                result['season'] = season
            if episode is not None:
                result['episode'] = episode
            if profile is not None:
                result['profile'] = profile
                
            return result
        else:
            return {
                'status': 'error',
                'title': title,
                'app': app_lower,
                'error_message': f"Roku returned status {response.status_code}"
            }
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Roku request failed: {e}")
        return {
            'status': 'error',
            'title': title,
            'error_message': f"Failed to connect to Roku TV: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error launching streaming content: {e}")
        return {
            'status': 'error',
            'title': title,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }

