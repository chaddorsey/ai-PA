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


def get_tv_listings_now(
    sports_only: Optional[bool] = None,
    channel: Optional[str] = None,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get what's currently on TV across all channels or a specific channel.
    
    This tool queries the Schedules Direct TV listings service to show
    what programs are currently airing. Great for answering "what's on TV?"
    or "what sports are on right now?"
    
    Args:
        sports_only: If True, only return sports programs. Defaults to False.
        channel: Specific channel number to check (e.g., "570" for ESPN HD).
                 Leave empty to get all channels.
        limit: Maximum number of programs to return. Defaults to 20.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - programs: List of currently airing programs with channel, title, etc.
        - count: Total number of programs found
        - sports_count: Number of sports programs (if sports_only=False)
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Set defaults
        if sports_only is None:
            sports_only = False
        if limit is None:
            limit = 20
        
        # Schedules Direct service URL (Docker internal network)
        sd_service_url = "http://schedules-direct-service:5125"
        
        # Choose endpoint based on sports_only flag
        if sports_only:
            endpoint = f"{sd_service_url}/now/sports"
        elif channel:
            endpoint = f"{sd_service_url}/channel/{channel}"
        else:
            endpoint = f"{sd_service_url}/now"
        
        response = requests.get(endpoint, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Handle channel-specific response differently
        if channel:
            current = data.get('current')
            upcoming = data.get('upcoming', [])
            
            programs = []
            if current:
                programs.append({
                    'channel': channel,
                    'station': current.get('station'),
                    'title': current.get('title'),
                    'episode_title': current.get('episode_title'),
                    'description': current.get('description'),
                    'start_time': current.get('start_time'),
                    'end_time': current.get('end_time'),
                    'duration_minutes': current.get('duration_minutes'),
                    'is_live': current.get('is_live', False),
                    'is_sports': current.get('is_sports', False),
                    'status': 'NOW PLAYING'
                })
            
            return {
                'status': 'ok',
                'channel': channel,
                'current': current,
                'upcoming': upcoming[:limit] if upcoming else [],
                'count': 1 if current else 0
            }
        
        # Format programs for general listings
        programs = data.get('programs', [])[:limit]
        
        formatted_programs = []
        for prog in programs:
            formatted_programs.append({
                'channel': prog.get('channel'),
                'station': prog.get('station'),
                'station_name': prog.get('station_name'),
                'title': prog.get('title'),
                'episode_title': prog.get('episode_title'),
                'description': prog.get('description', '')[:200] if prog.get('description') else None,
                'start_time': prog.get('start_time'),
                'end_time': prog.get('end_time'),
                'duration_minutes': prog.get('duration_minutes'),
                'is_live': prog.get('is_live', False),
                'is_sports': prog.get('is_sports', False),
                'is_new': prog.get('is_new', False),
            })
        
        # Count sports programs
        sports_count = sum(1 for p in data.get('programs', []) if p.get('is_sports'))
        
        return {
            'status': 'ok',
            'programs': formatted_programs,
            'count': len(formatted_programs),
            'total_available': data.get('count', len(formatted_programs)),
            'sports_count': sports_count,
            'sports_only': sports_only
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Schedules Direct service request failed: {e}")
        return {
            'status': 'error',
            'programs': [],
            'count': 0,
            'error_message': f"Failed to connect to TV listings service: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error getting TV listings: {e}")
        return {
            'status': 'error',
            'programs': [],
            'count': 0,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def search_tv_guide(
    query: str,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Search the TV guide for upcoming programs by title.
    
    This tool searches the next 2 days of TV listings for programs
    matching the search query. Use this to find when specific shows,
    movies, or sports events will be on.
    
    Args:
        query: The search term to find in program titles (e.g., "Patriots",
               "SportsCenter", "College Football", "Breaking Bad").
        limit: Maximum number of results to return. Defaults to 20.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - query: The search term used
        - results: List of matching programs with channel, title, start_time
        - count: Number of results found
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        if limit is None:
            limit = 20
        
        # Schedules Direct service URL
        sd_service_url = "http://schedules-direct-service:5125"
        
        response = requests.get(
            f"{sd_service_url}/search",
            params={'q': query},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        results = data.get('results', [])[:limit]
        
        formatted_results = []
        for prog in results:
            formatted_results.append({
                'channel': prog.get('channel'),
                'station': prog.get('station'),
                'title': prog.get('title'),
                'episode_title': prog.get('episode_title'),
                'start_time': prog.get('start_time'),
                'duration_minutes': prog.get('duration_minutes'),
                'is_sports': prog.get('is_sports', False),
            })
        
        return {
            'status': 'ok',
            'query': query,
            'results': formatted_results,
            'count': len(formatted_results),
            'total_found': data.get('count', len(formatted_results))
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"TV guide search failed: {e}")
        return {
            'status': 'error',
            'query': query,
            'results': [],
            'count': 0,
            'error_message': f"Failed to search TV guide: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error searching TV guide: {e}")
        return {
            'status': 'error',
            'query': query,
            'results': [],
            'count': 0,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def lookup_streaming_content(
    title: str,
    preferred_service: Optional[str] = None
) -> Dict[str, Any]:
    """
    Look up streaming availability and deep link info for a title.
    
    This tool queries JustWatch data to find where content is available
    across your subscribed streaming services (Netflix, Hulu, Disney+,
    Max, Prime Video, Apple TV+, ESPN+, YouTube). It returns the content
    ID needed for deep linking.
    
    Use this tool when you need to:
    - Find where a movie or show is available to stream
    - Get the content ID for deep linking before using launch_streaming_content
    - Compare availability across services
    
    Args:
        title: The title to search for (e.g., "Stranger Things", "The Bear").
        preferred_service: Preferred streaming service if content is on multiple.
                          Options: netflix, hulu, disney, max, prime, apple, espn.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"  
        - title: The matched title
        - available_on: List of services where content is available
        - recommended: Best option (with content_id for deep linking)
        - all_options: Full list of streaming options with content IDs
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Content database service URL (Docker internal network)
        content_db_url = "http://content-database:5126"
        
        # Search for the title
        params = {'title': title}
        if preferred_service:
            params['service'] = preferred_service
        
        response = requests.get(
            f"{content_db_url}/deep-link",
            params=params,
            timeout=30
        )
        
        if response.status_code == 404:
            # Content not found - try a broader search
            search_response = requests.get(
                f"{content_db_url}/search",
                params={'q': title},
                timeout=30
            )
            search_response.raise_for_status()
            search_data = search_response.json()
            
            results = search_data.get('results', [])
            if not results:
                return {
                    'status': 'not_found',
                    'title': title,
                    'available_on': [],
                    'recommended': None,
                    'message': f"'{title}' not found in streaming database. Try using Roku universal search."
                }
            
            # Use first result
            first_result = results[0]
            streaming = first_result.get('streaming_availability', {})
            
            available_on = list(streaming.keys())
            
            # Pick recommended service
            recommended = None
            if preferred_service and preferred_service in streaming:
                options = streaming[preferred_service]
                if options:
                    recommended = {
                        'service': preferred_service,
                        'content_id': options[0].get('content_id') if options else None
                    }
            elif streaming:
                first_service = available_on[0]
                options = streaming[first_service]
                recommended = {
                    'service': first_service,
                    'content_id': options[0].get('content_id') if options else None
                }
            
            return {
                'status': 'ok',
                'title': first_result.get('title', title),
                'content_type': first_result.get('content_type'),
                'year': first_result.get('year'),
                'available_on': available_on,
                'recommended': recommended,
                'all_options': streaming
            }
        
        response.raise_for_status()
        data = response.json()
        
        return {
            'status': 'ok',
            'title': data.get('title', title),
            'content_type': data.get('content_type'),
            'service': data.get('service'),
            'content_id': data.get('content_id'),
            'roku_launch': data.get('roku_launch'),
            'message': f"Found on {data.get('service')}"
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Content database request failed: {e}")
        return {
            'status': 'error',
            'title': title,
            'available_on': [],
            'error_message': f"Content lookup service unavailable: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error looking up streaming content: {e}")
        return {
            'status': 'error',
            'title': title,
            'available_on': [],
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def add_content_to_database(
    title: str,
    content_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Scrape and add a title to the local streaming content database.
    
    This tool is primarily for the sleeptime agent to proactively build
    the content database. It scrapes JustWatch for the title and stores
    streaming availability and deep link IDs for future lookups.
    
    Use this when:
    - A user mentions a title that isn't in the database
    - Building up the database with popular content
    - Adding titles the user might be interested in
    
    Args:
        title: The title to add (e.g., "Breaking Bad", "Oppenheimer").
        content_type: Type of content - "movie" or "show". Optional.
    
    Returns:
        Dictionary with keys:
        - status: "ok", "not_found", or "error"
        - title: The matched title
        - available_on: List of streaming services where content is available
        - message: Status message
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Content database service URL (Docker internal network)
        content_db_url = "http://content-database:5126"
        
        # Request the scrape
        payload = {'title': title}
        if content_type:
            payload['content_type'] = content_type
        
        response = requests.post(
            f"{content_db_url}/scrape-title",
            json=payload,
            timeout=60  # Longer timeout for scraping
        )
        
        if response.status_code == 404:
            return {
                'status': 'not_found',
                'title': title,
                'message': f"'{title}' not found on JustWatch"
            }
        
        response.raise_for_status()
        data = response.json()
        
        return {
            'status': data.get('status', 'ok'),
            'title': data.get('title', title),
            'content_type': data.get('content_type'),
            'year': data.get('year'),
            'available_on': data.get('available_on', []),
            'message': data.get('message', 'Content added to database')
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Content database request failed: {e}")
        return {
            'status': 'error',
            'title': title,
            'error_message': f"Content database service unavailable: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error adding content to database: {e}")
        return {
            'status': 'error',
            'title': title,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def get_channel_info(
    channel: str
) -> Dict[str, Any]:
    """
    Get detailed schedule information for a specific TV channel.
    
    This tool shows what's currently playing on a channel and what's
    coming up next. Use this to answer questions like "What's on ESPN?"
    or "What's playing on channel 570?"
    
    Args:
        channel: The channel number to look up (e.g., "570" for ESPN HD,
                 "504" for CBS, "588" for NFL Network).
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - channel: The channel number
        - current: Currently playing program (title, description, times)
        - upcoming: List of upcoming programs
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Schedules Direct service URL
        sd_service_url = "http://schedules-direct-service:5125"
        
        response = requests.get(
            f"{sd_service_url}/channel/{channel}",
            params={'hours': 6},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        current = data.get('current')
        upcoming = data.get('upcoming', [])
        
        # Format current program
        current_formatted = None
        if current:
            current_formatted = {
                'title': current.get('title'),
                'episode_title': current.get('episode_title'),
                'description': current.get('description'),
                'station': current.get('station'),
                'start_time': current.get('start_time'),
                'end_time': current.get('end_time'),
                'duration_minutes': current.get('duration_minutes'),
                'is_live': current.get('is_live', False),
                'is_sports': current.get('is_sports', False),
            }
        
        # Format upcoming programs
        upcoming_formatted = []
        for prog in upcoming[:10]:
            upcoming_formatted.append({
                'title': prog.get('title'),
                'episode_title': prog.get('episode_title'),
                'start_time': prog.get('start_time'),
                'duration_minutes': prog.get('duration_minutes'),
                'is_sports': prog.get('is_sports', False),
            })
        
        return {
            'status': 'ok',
            'channel': channel,
            'current': current_formatted,
            'upcoming': upcoming_formatted,
            'upcoming_count': len(upcoming_formatted)
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Channel info request failed: {e}")
        return {
            'status': 'error',
            'channel': channel,
            'current': None,
            'upcoming': [],
            'error_message': f"Failed to get channel info: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error getting channel info: {e}")
        return {
            'status': 'error',
            'channel': channel,
            'current': None,
            'upcoming': [],
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def get_user_watch_stats(
    username: str
) -> Dict[str, Any]:
    """
    Get statistics about a user's watch history.
    
    This tool provides an overview of what a user has watched, including
    their most-watched shows, watch counts by service, and recent activity.
    Use this to understand viewing habits and preferences.
    
    Args:
        username: The username to get stats for (e.g., "chad").
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - user: The username
        - total_watches: Total number of watch entries
        - unique_titles: Number of unique titles watched
        - by_service: Watch counts by streaming service
        - most_watched: List of most-watched titles with counts
        - recent_activity: Recent watch activity by date
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        content_db_url = "http://content-database:5126"
        
        response = requests.get(
            f"{content_db_url}/user/{username}/stats",
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        return {
            'status': 'ok',
            'user': username,
            'display_name': data.get('display_name'),
            'total_watches': data.get('total_watches', 0),
            'unique_titles': data.get('unique_titles', 0),
            'by_service': data.get('by_service', {}),
            'most_watched': data.get('most_watched', []),
            'recent_activity': data.get('recent_activity', [])[:10]
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"User stats request failed: {e}")
        return {
            'status': 'error',
            'user': username,
            'error_message': f"Failed to get user stats: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {
            'status': 'error',
            'user': username,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def get_continue_watching(
    username: str,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get shows/series a user has started but may not have completed.
    
    This tool returns series the user has watched recently, with information
    about the last episode watched and suggestions for the next episode.
    Perfect for helping users pick up where they left off.
    
    Args:
        username: The username to get continue watching for (e.g., "chad").
        limit: Maximum number of series to return. Defaults to 10.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - user: The username
        - continue_watching: List of series with last watched info and next episode suggestions
        - count: Number of series returned
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        if limit is None:
            limit = 10
        
        content_db_url = "http://content-database:5126"
        
        response = requests.get(
            f"{content_db_url}/user/{username}/continue-watching",
            params={'limit': limit},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        # Format results
        results = []
        for item in data.get('continue_watching', []):
            results.append({
                'title': item.get('title'),
                'service': item.get('service'),
                'last_season': item.get('last_season'),
                'last_episode': item.get('last_episode'),
                'last_watched': item.get('last_watched'),
                'suggested_next': item.get('suggested_next'),
                'streaming_links': item.get('streaming_links', {})
            })
        
        return {
            'status': 'ok',
            'user': username,
            'continue_watching': results,
            'count': len(results)
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Continue watching request failed: {e}")
        return {
            'status': 'error',
            'user': username,
            'continue_watching': [],
            'count': 0,
            'error_message': f"Failed to get continue watching: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error getting continue watching: {e}")
        return {
            'status': 'error',
            'user': username,
            'continue_watching': [],
            'count': 0,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def search_user_watch_history(
    username: str,
    query: str
) -> Dict[str, Any]:
    """
    Search a user's watch history for specific titles.
    
    This tool searches through a user's watch history to find content
    they've watched. Use this to answer questions like "Have I watched
    Breaking Bad?" or "When did I watch The Office?"
    
    Args:
        username: The username to search history for (e.g., "chad").
        query: Search query to match against titles (e.g., "breaking", "office").
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - user: The username
        - query: The search query
        - results: List of matching titles with watch info
        - count: Number of results
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        content_db_url = "http://content-database:5126"
        
        response = requests.get(
            f"{content_db_url}/user/{username}/search",
            params={'q': query},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        return {
            'status': 'ok',
            'user': username,
            'query': query,
            'results': data.get('results', []),
            'count': data.get('count', 0)
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Search history request failed: {e}")
        return {
            'status': 'error',
            'user': username,
            'query': query,
            'results': [],
            'count': 0,
            'error_message': f"Failed to search history: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error searching history: {e}")
        return {
            'status': 'error',
            'user': username,
            'query': query,
            'results': [],
            'count': 0,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def update_streaming_credentials(
    service: str,
    cookies_json: str,
    additional_params: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update authentication credentials for a streaming service.
    
    This tool allows updating the stored credentials (cookies, tokens) for
    streaming services so that watch history polling can continue to work
    when credentials expire.
    
    Credentials should be exported from the browser as JSON.
    
    Args:
        service: The streaming service name (max, hulu, disney, apple, netflix, prime).
        cookies_json: JSON string containing the exported browser cookies.
        additional_params: Optional JSON string with additional parameters like:
                          - profile_guid (for Netflix)
                          - bearer_token (for Disney+/Apple TV+)
                          - profile_id (for Disney+)
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - service: The service that was updated
        - message: Success or error message
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import json
    import logging
    
    logger = logging.getLogger(__name__)
    
    valid_services = ['max', 'hulu', 'disney', 'apple', 'netflix', 'prime']
    
    if service not in valid_services:
        return {
            'status': 'error',
            'service': service,
            'message': f"Invalid service. Must be one of: {', '.join(valid_services)}"
        }
    
    try:
        # Parse the cookies JSON
        try:
            cookies = json.loads(cookies_json)
        except json.JSONDecodeError as e:
            return {
                'status': 'error',
                'service': service,
                'message': f"Invalid cookies JSON: {str(e)}"
            }
        
        # Build credentials object
        credentials = {'cookies': cookies}
        
        # Add additional parameters if provided
        if additional_params:
            try:
                extra = json.loads(additional_params)
                credentials.update(extra)
            except json.JSONDecodeError as e:
                return {
                    'status': 'error',
                    'service': service,
                    'message': f"Invalid additional_params JSON: {str(e)}"
                }
        
        # Send to the watch history service
        poller_url = "http://watch-history-service:5127"
        
        response = requests.post(
            f"{poller_url}/credentials/{service}",
            json=credentials,
            timeout=30
        )
        response.raise_for_status()
        
        return {
            'status': 'ok',
            'service': service,
            'message': f"Credentials updated successfully for {service}"
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Credential update failed: {e}")
        return {
            'status': 'error',
            'service': service,
            'message': f"Failed to update credentials: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error updating credentials: {e}")
        return {
            'status': 'error',
            'service': service,
            'message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def check_credential_status() -> Dict[str, Any]:
    """
    Check the authentication status of all streaming service credentials.
    
    This tool checks which services have credentials configured and whether
    they appear to be valid. Useful for the sleeptime agent to know which
    services can be polled.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - services: Dict mapping service names to their credential status
        - configured_count: Number of services with credentials
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    services = ['max', 'hulu', 'disney', 'apple', 'netflix', 'prime']
    
    try:
        poller_url = "http://watch-history-service:5127"
        service_status = {}
        configured_count = 0
        
        for service in services:
            try:
                response = requests.get(
                    f"{poller_url}/credentials/{service}",
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    service_status[service] = {
                        'configured': data.get('configured', False),
                        'keys': data.get('keys', [])
                    }
                    if data.get('configured'):
                        configured_count += 1
                else:
                    service_status[service] = {
                        'configured': False,
                        'error': f"HTTP {response.status_code}"
                    }
            except Exception as e:
                service_status[service] = {
                    'configured': False,
                    'error': str(e)
                }
        
        return {
            'status': 'ok',
            'services': service_status,
            'configured_count': configured_count,
            'total_services': len(services)
        }
        
    except Exception as e:
        logger.error(f"Error checking credentials: {e}")
        return {
            'status': 'error',
            'services': {},
            'configured_count': 0,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


# ==================== WATCH HISTORY POLLING TOOLS ====================


def poll_watch_history(
    service: Optional[str] = None,
    username: Optional[str] = None
) -> Dict[str, Any]:
    """
    Poll streaming services for watch history and automatically save to database.
    
    This tool fetches "continue watching" data from streaming services and
    AUTOMATICALLY saves new entries to the content database. No additional
    action is required after calling this tool - just report the results.
    
    Args:
        service: Specific service to poll. Options: 'max', 'hulu', 'netflix', 
                 'prime', 'apple', 'disney'. Leave empty to poll ALL services.
        username: The user to associate history with. Defaults to 'chad'.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - services: Dict of service -> {items_found, items_saved}
        - total_items: Total items found across all services
        - total_saved: Total NEW items saved to database (0 if already existed)
    """
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        if username is None:
            username = 'chad'
        
        watch_history_url = "http://watch-history-service:5127"
        
        if service:
            # Poll single service
            response = requests.post(
                f"{watch_history_url}/poll/{service}",
                json={'username': username},
                timeout=120
            )
            response.raise_for_status()
            data = response.json()
            
            return {
                'status': 'ok',
                'services': {
                    service: {
                        'count': data.get('items_found', 0),
                        'saved': data.get('items_saved', 0),
                        'method': data.get('method', 'unknown')
                    }
                },
                'total_items': data.get('items_found', 0),
                'total_saved': data.get('items_saved', 0)
            }
        else:
            # Poll all services
            response = requests.post(
                f"{watch_history_url}/poll",
                json={'username': username},
                timeout=300
            )
            response.raise_for_status()
            data = response.json()
            
            total_items = sum(s.get('items_found', 0) for s in data.get('services', {}).values())
            total_saved = sum(s.get('items_saved', 0) for s in data.get('services', {}).values())
            
            return {
                'status': 'ok',
                'services': data.get('services', {}),
                'total_items': total_items,
                'total_saved': total_saved
            }
        
    except Exception as e:
        logger.error(f"Error polling watch history: {e}")
        return {
            'status': 'error',
            'services': {},
            'total_items': 0,
            'total_saved': 0,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def poll_watchlists(
    service: Optional[str] = None,
    username: Optional[str] = None
) -> Dict[str, Any]:
    """
    Poll streaming services for watchlist/My List and automatically save to database.
    
    This tool fetches the user's saved watchlists from streaming services
    and AUTOMATICALLY saves entries to the database. Just report the results.
    (Netflix My List, Prime Watchlist, etc.) and saves them to the database.
    Use this to keep track of what the user wants to watch.
    
    Args:
        service: Specific service to poll. Options: 'netflix', 'prime', 
                 'disney', 'apple'. Leave empty to poll all services.
        username: The user to associate watchlists with. Defaults to 'chad'.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - services: Dict of service -> {count, saved}
        - total_items: Total items found across all services
    """
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        if username is None:
            username = 'chad'
        
        watch_history_url = "http://watch-history-service:5127"
        
        if service:
            # Poll single service
            response = requests.post(
                f"{watch_history_url}/watchlist/{service}",
                json={'username': username},
                timeout=120
            )
            response.raise_for_status()
            data = response.json()
            
            return {
                'status': 'ok',
                'services': {
                    service: {
                        'count': data.get('count', 0),
                        'saved': data.get('saved', 0)
                    }
                },
                'total_items': data.get('count', 0)
            }
        else:
            # Poll all services
            response = requests.post(
                f"{watch_history_url}/watchlist/all",
                json={'username': username},
                timeout=300
            )
            response.raise_for_status()
            data = response.json()
            
            services_summary = {}
            for svc, info in data.get('services', {}).items():
                services_summary[svc] = {
                    'count': info.get('count', 0),
                    'saved': info.get('saved', 0)
                }
            
            return {
                'status': 'ok',
                'services': services_summary,
                'total_items': data.get('total', 0)
            }
        
    except Exception as e:
        logger.error(f"Error polling watchlists: {e}")
        return {
            'status': 'error',
            'services': {},
            'total_items': 0,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def poll_recommendations(
    service: Optional[str] = None,
    username: Optional[str] = None
) -> Dict[str, Any]:
    """
    Poll streaming services for personalized recommendations.
    
    This tool fetches the recommendation rows from streaming service home pages
    (e.g., "Because you watched...", "Trending Now", "Top Picks") and saves
    them to the database. Use this to understand what each service is suggesting.
    
    Note: This can be slow as it requires browser scraping of each service's
    home page. Consider running during off-peak times.
    
    Args:
        service: Specific service to poll. Options: 'netflix', 'prime', 
                 'disney', 'apple'. Leave empty to poll all services.
        username: The user to associate recommendations with. Defaults to 'chad'.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - services: Dict of service -> {count, saved}
        - total_items: Total recommendations found across all services
    """
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        if username is None:
            username = 'chad'
        
        watch_history_url = "http://watch-history-service:5127"
        
        if service:
            # Poll single service
            response = requests.post(
                f"{watch_history_url}/recommendations/{service}",
                json={'username': username},
                timeout=180
            )
            response.raise_for_status()
            data = response.json()
            
            return {
                'status': 'ok',
                'services': {
                    service: {
                        'count': data.get('count', 0),
                        'saved': data.get('saved', 0)
                    }
                },
                'total_items': data.get('count', 0)
            }
        else:
            # Poll all services
            response = requests.post(
                f"{watch_history_url}/recommendations/all",
                json={'username': username},
                timeout=600
            )
            response.raise_for_status()
            data = response.json()
            
            services_summary = {}
            for svc, info in data.get('services', {}).items():
                services_summary[svc] = {
                    'count': info.get('count', 0),
                    'saved': info.get('saved', 0)
                }
            
            return {
                'status': 'ok',
                'services': services_summary,
                'total_items': data.get('total', 0)
            }
        
    except Exception as e:
        logger.error(f"Error polling recommendations: {e}")
        return {
            'status': 'error',
            'services': {},
            'total_items': 0,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def sync_all_streaming_data(
    username: Optional[str] = None,
    include_recommendations: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Perform a full sync of all streaming service data.
    
    This is a comprehensive sync that polls:
    1. Watch history from all services (what the user has watched)
    2. Watchlists from all services (what the user wants to watch)
    3. Recommendations from all services (what services suggest) - optional
    
    This is the tool to use for scheduled daily syncs. It saves all data
    to the content database for later querying.
    
    Args:
        username: The user to sync data for. Defaults to 'chad'.
        include_recommendations: Whether to also sync recommendations.
                                  Defaults to True but can be slow.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - watch_history: Summary of watch history sync per service
        - watchlists: Summary of watchlist sync per service
        - recommendations: Summary of recommendations sync per service (if included)
        - totals: Overall counts for each category
    """
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        if username is None:
            username = 'chad'
        if include_recommendations is None:
            include_recommendations = True
        
        watch_history_url = "http://watch-history-service:5127"
        
        response = requests.post(
            f"{watch_history_url}/sync/all",
            json={
                'username': username,
                'include_recommendations': include_recommendations
            },
            timeout=900  # 15 minutes for full sync
        )
        response.raise_for_status()
        data = response.json()
        
        return {
            'status': 'ok',
            'username': data.get('username'),
            'timestamp': data.get('timestamp'),
            'watch_history': data.get('watch_history', {}),
            'watchlists': data.get('watchlists', {}),
            'recommendations': data.get('recommendations', {}),
            'totals': data.get('totals', {})
        }
        
    except Exception as e:
        logger.error(f"Error in full sync: {e}")
        return {
            'status': 'error',
            'watch_history': {},
            'watchlists': {},
            'recommendations': {},
            'totals': {},
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def query_user_watch_history(
    username: Optional[str] = None,
    service: Optional[str] = None,
    title_search: Optional[str] = None,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Query the user's watch history from the database.
    
    Use this to find out what the user has watched. You can search by
    title, filter by service, or get recent viewing activity.
    
    Args:
        username: The user to query. Defaults to 'chad'.
        service: Filter by streaming service (e.g., 'netflix', 'prime').
        title_search: Search for titles containing this text.
        limit: Maximum number of results. Defaults to 50.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - entries: List of watch history entries
        - count: Number of entries returned
    """
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        if username is None:
            username = 'chad'
        if limit is None:
            limit = 50
        
        content_api_url = "http://content-database-api:5126"
        
        params = {'username': username, 'limit': limit}
        if service:
            params['service'] = service
        if title_search:
            params['title'] = title_search
        
        response = requests.get(
            f"{content_api_url}/user/history",
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        return {
            'status': 'ok',
            'entries': data.get('entries', []),
            'count': len(data.get('entries', []))
        }
        
    except Exception as e:
        logger.error(f"Error querying watch history: {e}")
        return {
            'status': 'error',
            'entries': [],
            'count': 0,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def query_user_watchlist(
    username: Optional[str] = None,
    service: Optional[str] = None
) -> Dict[str, Any]:
    """
    Query the user's watchlist/My List from the database.
    
    Use this to find out what the user has saved to watch later.
    
    Args:
        username: The user to query. Defaults to 'chad'.
        service: Filter by streaming service (e.g., 'netflix', 'prime').
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - entries: List of watchlist entries
        - count: Number of entries returned
    """
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        if username is None:
            username = 'chad'
        
        content_api_url = "http://content-database-api:5126"
        
        params = {'username': username}
        if service:
            params['service'] = service
        
        response = requests.get(
            f"{content_api_url}/user/watchlist",
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        return {
            'status': 'ok',
            'entries': data.get('entries', []),
            'count': len(data.get('entries', []))
        }
        
    except Exception as e:
        logger.error(f"Error querying watchlist: {e}")
        return {
            'status': 'error',
            'entries': [],
            'count': 0,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def get_aggregated_recommendations(
    username: Optional[str] = None,
    limit_per_service: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get aggregated recommendations from all streaming services.
    
    This queries the cached recommendations from the database and provides
    a unified view of what all services are suggesting. Useful for helping
    the user decide what to watch by showing top picks across services.
    
    Args:
        username: The user to get recommendations for. Defaults to 'chad'.
        limit_per_service: Max recommendations per service. Defaults to 10.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - recommendations: Dict of service -> list of recommended titles
        - total_count: Total recommendations across all services
    """
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        if username is None:
            username = 'chad'
        if limit_per_service is None:
            limit_per_service = 10
        
        content_api_url = "http://content-database-api:5126"
        
        response = requests.get(
            f"{content_api_url}/user/recommendations",
            params={'username': username, 'limit': limit_per_service},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        return {
            'status': 'ok',
            'recommendations': data.get('recommendations', {}),
            'total_count': data.get('total_count', 0)
        }
        
    except Exception as e:
        logger.error(f"Error getting recommendations: {e}")
        return {
            'status': 'error',
            'recommendations': {},
            'total_count': 0,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


# ============================================================================
# SERIES PROGRESS TRACKING TOOLS
# ============================================================================

def sync_series_progress(
    service: str,
    series_url: str,
    username: Optional[str] = None
) -> Dict[str, Any]:
    """
    Scrape and sync episode-level watch progress for a specific series.
    
    This tool navigates to a series page on a streaming service, scrapes
    the watch progress for every episode across all seasons, and saves
    the data to the content database. Use this to track which episodes
    a user has watched, which are in progress, and which are unwatched.
    
    Supported services: max (HBO), disney (Disney+), apple (Apple TV+), hulu
    
    Args:
        service: The streaming service ('max', 'disney', 'apple', 'hulu')
        series_url: The full URL to the series page on the streaming service
        username: The user to associate progress with. Defaults to 'chad'.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - series_title: Title of the series
        - total_episodes: Number of episodes found
        - watched: Number of watched episodes
        - in_progress: Number of in-progress episodes
        - unwatched: Number of unwatched episodes
        - next_episode: Dict with season, episode, title of next unwatched episode
        - error_message: Error message if status is "error"
    
    Example:
        sync_series_progress('max', 'https://play.hbomax.com/show/...')
    """
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        if username is None:
            username = 'chad'
        
        watch_history_service_url = "http://watch-history-service:5127"
        
        response = requests.post(
            f"{watch_history_service_url}/series-progress/scrape",
            json={
                'service': service,
                'series_url': series_url,
                'username': username
            },
            timeout=120  # Long timeout for browser scraping
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') == 'ok':
            summary = data.get('summary', {})
            return {
                'status': 'ok',
                'series_title': data.get('series_title', 'Unknown'),
                'service': service,
                'total_episodes': summary.get('total_episodes', 0),
                'watched': summary.get('watched', 0),
                'in_progress': summary.get('in_progress', 0),
                'unwatched': summary.get('unwatched', 0),
                'next_episode': summary.get('next_episode'),
                'episodes_saved': data.get('episodes_saved', 0)
            }
        else:
            return {
                'status': 'error',
                'error_message': data.get('error', 'Unknown error')
            }
        
    except Exception as e:
        logger.error(f"Error syncing series progress: {e}")
        return {
            'status': 'error',
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def get_series_progress(
    series_title: str,
    service: str,
    username: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get the current watch progress for a specific series.
    
    This tool queries the database for episode-level progress on a series,
    returning which episodes are watched, in progress, or unwatched.
    Use this to answer questions like "What episodes of X haven't I watched?"
    
    Args:
        series_title: Title of the series (partial match supported)
        service: The streaming service ('max', 'disney', 'apple', 'hulu')
        username: The user to query for. Defaults to 'chad'.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - series_title: Full matched title
        - total_episodes: Total episode count
        - watched_episodes: Number watched
        - unwatched_count: Number unwatched
        - in_progress_count: Number in progress
        - episodes: List of unwatched/in-progress episodes with season, episode, title, progress
    
    Example:
        get_series_progress('Last Week Tonight', 'max')
    """
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        if username is None:
            username = 'chad'
        
        watch_history_service_url = "http://watch-history-service:5127"
        
        response = requests.get(
            f"{watch_history_service_url}/series-progress/unwatched",
            params={
                'series': series_title,
                'service': service,
                'username': username
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        if 'error' in data:
            return {
                'status': 'error',
                'error_message': data['error']
            }
        
        return {
            'status': 'ok',
            'series_title': data.get('series_title'),
            'service': data.get('service'),
            'total_episodes': data.get('total_episodes', 0),
            'watched_episodes': data.get('watched_episodes', 0),
            'unwatched_count': data.get('unwatched_count', 0),
            'in_progress_count': data.get('in_progress_count', 0),
            'episodes': data.get('episodes', [])
        }
        
    except Exception as e:
        logger.error(f"Error getting series progress: {e}")
        return {
            'status': 'error',
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def get_series_progress_summary(
    username: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get a formatted summary of all tracked series progress.
    
    This tool returns a human-readable summary of watch progress across
    all tracked series on all streaming services. The output is suitable
    for storing in a Letta memory block for quick agent reference.
    
    Use this periodically (e.g., daily) to update the agent's knowledge
    of the user's viewing progress across all series.
    
    Args:
        username: The user to query for. Defaults to 'chad'.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - summary: Formatted multi-line string summarizing all series progress
        - suitable_for_memory: True if summary should be saved to memory block
    
    Example output in summary:
        ## Series Progress (updated: 2025-01-03 15:00 UTC)
        
        **Max (HBO):**
        - Last Week Tonight S12: 20/30 watched, next: S12E21 "Health Agency Cuts"
        - The White Lotus S3: 4/8 watched, S3E5 in progress (42%)
    """
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        if username is None:
            username = 'chad'
        
        watch_history_service_url = "http://watch-history-service:5127"
        
        response = requests.get(
            f"{watch_history_service_url}/series-progress/summary",
            params={'username': username},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        return {
            'status': 'ok',
            'summary': data.get('summary', 'No series progress data found.'),
            'suitable_for_memory': True
        }
        
    except Exception as e:
        logger.error(f"Error getting series progress summary: {e}")
        return {
            'status': 'error',
            'summary': '',
            'suitable_for_memory': False,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }


def list_tracked_series(
    service: Optional[str] = None,
    username: Optional[str] = None
) -> Dict[str, Any]:
    """
    List all series currently being tracked for episode progress.
    
    This tool returns a list of all series that have been synced for
    episode-level progress tracking. Use this to see which series
    the user is actively watching and might need progress updates.
    
    Args:
        service: Optional, filter by streaming service ('max', 'disney', 'apple')
        username: The user to query for. Defaults to 'chad'.
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - series: List of series with title, service, episode counts
        - count: Number of tracked series
    """
    import traceback
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        if username is None:
            username = 'chad'
        
        watch_history_service_url = "http://watch-history-service:5127"
        
        params = {'username': username}
        if service:
            params['service'] = service
        
        response = requests.get(
            f"{watch_history_service_url}/series-progress/list",
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        return {
            'status': 'ok',
            'series': data.get('series', []),
            'count': data.get('count', 0)
        }
        
    except Exception as e:
        logger.error(f"Error listing tracked series: {e}")
        return {
            'status': 'error',
            'series': [],
            'count': 0,
            'error_message': f"Error: {str(e)}\n{traceback.format_exc()}"
        }

