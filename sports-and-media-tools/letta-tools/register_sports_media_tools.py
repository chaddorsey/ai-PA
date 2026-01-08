#!/usr/bin/env python3
"""
Register Sports & Media Control Tools with Letta Agent

This script registers the sports and media control tools with Letta and
allocates them appropriately between the main agent and sleeptime agent.

Main Agent Tools (user-facing):
- query_sports_games, get_channel_for_game, control_roku_tv, etc.
- launch_streaming_content, get_series_progress

Sleeptime Agent Tools (background sync):
- poll_watch_history, sync_series_progress, sync_all_streaming_data, etc.
"""

import os
import sys
from pathlib import Path

# Add this directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Letta client import
try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found. Install with: pip install letta-client")
        sys.exit(1)

# Import the sports media tools
from sports_media_tools import (
    query_sports_games,
    get_channel_for_game,
    control_roku_tv,
    send_fios_ir_command,
    tune_fios_channel,
    watch_game,
    launch_streaming_content,
    get_tv_listings_now,
    search_tv_guide,
    get_upcoming_listings,
    get_channel_info,
    lookup_streaming_content,
    add_content_to_database,
    # Watch history and streaming sync tools
    poll_watch_history,
    update_streaming_credentials,
    check_credential_status,
    poll_watchlists,
    poll_recommendations,
    sync_all_streaming_data,
    query_user_watch_history,
    query_user_watchlist,
    get_aggregated_recommendations,
    # Series progress tracking tools
    sync_series_progress,
    get_series_progress,
    get_series_progress_summary,
    list_tracked_series,
    # Tracked series management tools (PBI-28)
    add_tracked_series,
    remove_tracked_series,
    update_tracking_status,
    set_preferred_service,
    mark_episodes_watched,
    clear_manual_progress,
    get_tracked_series_list,
    get_series_tracking_status,
    # Background sync tools for tracked series
    sync_all_active_series,
    check_new_seasons,
    reconcile_watchlist_tracking,
)

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.getenv("LETTA_SPORTS_AGENT_ID", "agent-2515f29d-b773-43c5-b9ce-b6237897391d")
SLEEPTIME_AGENT_ID = os.getenv("LETTA_SLEEPTIME_AGENT_ID", "agent-a9f2c740-663c-4414-a553-47115180e49b")

# Tool allocation: which tools should NOT be on each agent
# Main agent: No background sync tools (user doesn't need to poll/sync)
MAIN_AGENT_EXCLUDE_TOOLS = [
    "add_content_to_database",
    "poll_watch_history",
    "update_streaming_credentials",
    "check_credential_status",
    "poll_watchlists",
    "poll_recommendations",
    "sync_all_streaming_data",
    "sync_series_progress",  # Background sync tool
    "get_series_progress_summary",  # For agent memory, not user queries
    # Background tracked series tools
    "sync_all_active_series",
    "check_new_seasons",
    "reconcile_watchlist_tracking",
]

# Sleeptime agent: No hardware control or real-time user interaction tools
SLEEPTIME_AGENT_EXCLUDE_TOOLS = [
    "query_sports_games",
    "get_channel_for_game",
    "control_roku_tv",
    "send_fios_ir_command",
    "tune_fios_channel",
    "watch_game",
    "launch_streaming_content",
    "get_tv_listings_now",
    "search_tv_guide",
    "get_channel_info",
    "lookup_streaming_content",
    # User-facing tracked series tools (main agent only)
    "add_tracked_series",
    "remove_tracked_series",
    "update_tracking_status",
    "set_preferred_service",
    "mark_episodes_watched",
    "clear_manual_progress",
    "get_tracked_series_list",
    "get_series_tracking_status",
]


def main():
    """Register sports media tools with Letta agent."""
    
    print(f"{'='*60}")
    print("Sports & Media Control Tools Registration")
    print(f"{'='*60}\n")
    
    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Main Agent ID: {AGENT_ID}")
    print(f"Sleeptime Agent ID: {SLEEPTIME_AGENT_ID}\n")
    
    tools_to_register = [
        # User-facing tools (main agent)
        ("query_sports_games", query_sports_games, "Query ESPN for current/upcoming sports games"),
        ("get_channel_for_game", get_channel_for_game, "Look up FIOS channel for a game or network"),
        ("control_roku_tv", control_roku_tv, "Control Roku TV - power, apps, keypresses"),
        ("send_fios_ir_command", send_fios_ir_command, "Send IR command to FIOS cable box"),
        ("tune_fios_channel", tune_fios_channel, "Tune FIOS to a specific channel"),
        ("watch_game", watch_game, "End-to-end: find game and tune TV to watch it"),
        ("launch_streaming_content", launch_streaming_content, "Launch streaming content with deep linking or Roku search"),
        ("get_tv_listings_now", get_tv_listings_now, "Get what's currently on TV (all channels or sports only)"),
        ("search_tv_guide", search_tv_guide, "Search TV guide for upcoming programs by title"),
        ("get_upcoming_listings", get_upcoming_listings, "Get upcoming TV programs (sports, primetime, etc.)"),
        ("get_channel_info", get_channel_info, "Get detailed schedule for a specific channel"),
        ("lookup_streaming_content", lookup_streaming_content, "Look up streaming availability and deep links from JustWatch"),
        
        # Background sync tools (sleeptime agent)
        ("add_content_to_database", add_content_to_database, "Scrape and add content to local database"),
        ("poll_watch_history", poll_watch_history, "Poll streaming services for watch history updates"),
        ("update_streaming_credentials", update_streaming_credentials, "Update credentials for a streaming service"),
        ("check_credential_status", check_credential_status, "Check the health of streaming service credentials"),
        ("poll_watchlists", poll_watchlists, "Poll streaming services for watchlist/My List updates"),
        ("poll_recommendations", poll_recommendations, "Poll streaming services for personalized recommendations"),
        ("sync_all_streaming_data", sync_all_streaming_data, "Full sync of watch history, watchlists, and recommendations"),
        
        # Series progress tracking tools
        ("sync_series_progress", sync_series_progress, "Scrape episode-level watch progress for a series"),
        ("get_series_progress", get_series_progress, "Get unwatched episodes for a series"),
        ("get_series_progress_summary", get_series_progress_summary, "Get formatted summary for memory block"),
        ("list_tracked_series", list_tracked_series, "List all series being tracked for progress"),
        
        # Query tools (both agents)
        ("query_user_watch_history", query_user_watch_history, "Query user's watch history with filters"),
        ("query_user_watchlist", query_user_watchlist, "Get user's watchlist entries"),
        ("get_aggregated_recommendations", get_aggregated_recommendations, "Get aggregated recommendations from all services"),
        
        # Tracked series management tools (PBI-28) - Main agent
        ("add_tracked_series", add_tracked_series, "Add a series to tracking with JustWatch lookup"),
        ("remove_tracked_series", remove_tracked_series, "Remove a series from tracking"),
        ("update_tracking_status", update_tracking_status, "Update status: watching/finished/dropped/on_hold"),
        ("set_preferred_service", set_preferred_service, "Set preferred streaming service for a series"),
        ("mark_episodes_watched", mark_episodes_watched, "Mark episodes as watched with flexible spec"),
        ("clear_manual_progress", clear_manual_progress, "Clear manual progress overrides for a series"),
        ("get_tracked_series_list", get_tracked_series_list, "Get user's tracked series with filters"),
        ("get_series_tracking_status", get_series_tracking_status, "Get detailed tracking status for a series"),
        
        # Background tracked series tools (PBI-28) - Sleeptime agent
        ("sync_all_active_series", sync_all_active_series, "Sync progress for all actively tracked series"),
        ("check_new_seasons", check_new_seasons, "Check for new season availability on tracked series"),
        ("reconcile_watchlist_tracking", reconcile_watchlist_tracking, "Auto-track series from watchlists"),
    ]
    
    registered_tool_ids = []
    
    try:
        # Initialize Letta client
        client = Letta(base_url=LETTA_BASE_URL)
        print("✓ Connected to Letta server\n")
        
        # Register each tool
        for tool_name, tool_func, tool_description in tools_to_register:
            print(f"Registering tool: {tool_name}")
            print(f"  Description: {tool_description}")
            
            try:
                # Create tool from function
                created_tool = client.tools.create_from_function(
                    func=tool_func,
                    tags=["sports", "media", "tv-control", "custom"]
                )
                print(f"  ✓ Registered: {tool_name}")
                tool_id = created_tool.id if hasattr(created_tool, 'id') else (created_tool.get('id') if isinstance(created_tool, dict) else 'N/A')
                print(f"    Tool ID: {tool_id}")
                registered_tool_ids.append(tool_id)
                
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "409" in error_str or "duplicate" in error_str:
                    print(f"  → Tool {tool_name} already exists")
                    # Try to find existing tool
                    try:
                        all_tools = client.tools.list()
                        for tool in all_tools:
                            t_name = tool.get("name") if isinstance(tool, dict) else (tool.name if hasattr(tool, 'name') else None)
                            if t_name == tool_name:
                                tool_id = tool.get("id") if isinstance(tool, dict) else (tool.id if hasattr(tool, 'id') else None)
                                if tool_id:
                                    registered_tool_ids.append(tool_id)
                                    print(f"    Found existing tool ID: {tool_id}")
                                    break
                    except Exception:
                        pass
                else:
                    print(f"  ❌ Failed to register {tool_name}: {e}")
                    import traceback
                    traceback.print_exc()
            
            print()
        
        # Build tool name to ID mapping
        tool_name_to_id = {}
        for tool_name, tool_func, tool_description in tools_to_register:
            # Find the tool ID we registered
            for tool_id in registered_tool_ids:
                # Tool IDs are sometimes returned in order, but safer to check
                pass
        
        # Alternative: rebuild mapping from registered_tool_ids list position
        for idx, (tool_name, _, _) in enumerate(tools_to_register):
            if idx < len(registered_tool_ids):
                tool_name_to_id[tool_name] = registered_tool_ids[idx]
        
        # Attach tools to main agent (excluding background sync tools)
        if registered_tool_ids:
            main_agent_tools = [
                tool_name_to_id[name] for name, _, _ in tools_to_register
                if name not in MAIN_AGENT_EXCLUDE_TOOLS and name in tool_name_to_id
            ]
            excluded_main = [name for name in MAIN_AGENT_EXCLUDE_TOOLS if name in tool_name_to_id]
            
            print(f"\n→ Attaching {len(main_agent_tools)} tools to main agent {AGENT_ID}...")
            print(f"   (Excluding {len(excluded_main)} background/maintenance tools)")
            if excluded_main:
                print(f"   Excluded: {', '.join(excluded_main)}")
            attach_tools_to_agent(client, AGENT_ID, main_agent_tools)
            
            # Attach to sleeptime agent (excluding hardware control tools)
            if SLEEPTIME_AGENT_ID and SLEEPTIME_AGENT_ID != AGENT_ID:
                sleeptime_agent_tools = [
                    tool_name_to_id[name] for name, _, _ in tools_to_register
                    if name not in SLEEPTIME_AGENT_EXCLUDE_TOOLS and name in tool_name_to_id
                ]
                excluded_sleep = [name for name in SLEEPTIME_AGENT_EXCLUDE_TOOLS if name in tool_name_to_id]
                
                print(f"\n→ Attaching {len(sleeptime_agent_tools)} tools to sleeptime agent {SLEEPTIME_AGENT_ID}...")
                print(f"   (Excluding {len(excluded_sleep)} user-interaction/hardware tools)")
                if excluded_sleep:
                    print(f"   Excluded: {', '.join(excluded_sleep)}")
                attach_tools_to_agent(client, SLEEPTIME_AGENT_ID, sleeptime_agent_tools)
        
        print(f"\n{'='*60}")
        print("Registration Complete")
        print(f"{'='*60}\n")
        
        print("✓ Tools registered successfully")
        
        print("\n--- Main Agent Tools ---")
        for tool_name, _, tool_description in tools_to_register:
            if tool_name not in MAIN_AGENT_EXCLUDE_TOOLS:
                print(f"  - {tool_name}: {tool_description}")
        
        print("\n--- Sleeptime Agent Tools ---")
        for tool_name, _, tool_description in tools_to_register:
            if tool_name not in SLEEPTIME_AGENT_EXCLUDE_TOOLS:
                print(f"  - {tool_name}: {tool_description}")
        
        print("\nUsage Examples:")
        print('  query_sports_games(team="patriots")')
        print('  watch_game(team="red sox")')
        print('  launch_streaming_content(title="Slow Horses", app="apple")')
        print('  get_series_progress(series_title="Last Week Tonight", service="max")')
        print('  sync_series_progress(service="max", series_url="https://play.hbomax.com/show/...")')
        print('  add_tracked_series(title="The Mandalorian")')
        print('  update_tracking_status(title="Severance", status="finished")')
        print('  mark_episodes_watched(title="The Americans", watched_spec="seasons 1-4")')
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Failed to connect to Letta server or register tools: {e}")
        import traceback
        traceback.print_exc()
        return 1


def attach_tools_to_agent(client, agent_id: str, tool_ids: list):
    """Attach tools to a specific agent."""
    try:
        # Try newer SDK v1.0 method first
        if hasattr(client, 'agents') and hasattr(client.agents, 'tools') and hasattr(client.agents.tools, 'attach'):
            for tool_id in tool_ids:
                try:
                    client.agents.tools.attach(agent_id=agent_id, tool_id=tool_id)
                    print(f"  ✓ Attached tool {tool_id}")
                except Exception as e:
                    error_str = str(e).lower()
                    if "already attached" in error_str or "already exists" in error_str or "409" in error_str:
                        print(f"  → Tool {tool_id} already attached")
                    else:
                        print(f"  ⚠ Could not attach tool {tool_id}: {e}")
        # Fallback to older method
        elif hasattr(client, 'add_tool_to_agent'):
            for tool_id in tool_ids:
                try:
                    client.add_tool_to_agent(agent_id=agent_id, tool_id=tool_id)
                    print(f"  ✓ Attached tool {tool_id}")
                except Exception as e:
                    error_str = str(e).lower()
                    if "already attached" in error_str or "already exists" in error_str or "409" in error_str:
                        print(f"  → Tool {tool_id} already attached")
                    else:
                        print(f"  ⚠ Could not attach tool {tool_id}: {e}")
        else:
            print(f"  ⚠ Tool attachment API not available")
            print(f"     You can attach tools manually in Letta ADE using tool IDs:")
            for tool_id in tool_ids:
                print(f"       - {tool_id}")
    except Exception as e:
        print(f"  ⚠ Could not attach tools to agent: {e}")
        print(f"     You can attach them manually in Letta ADE using tool IDs:")
        for tool_id in tool_ids:
            print(f"       - {tool_id}")


if __name__ == "__main__":
    sys.exit(main())

