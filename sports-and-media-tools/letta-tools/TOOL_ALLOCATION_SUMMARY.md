# Tool Allocation Summary

## Tools Removed from Main Agent

The following **7 tools** have been removed from the main agent to reduce tool bloat. These are background/maintenance tools that users don't need direct access to.

### Background Sync Tools (5)
1. **`poll_watch_history`** - Background sync of watch history
2. **`poll_watchlists`** - Background sync of watchlists  
3. **`poll_recommendations`** - Background sync of recommendations
4. **`sync_all_streaming_data`** - Full background sync
5. **`add_content_to_database`** - Background content scraping

### Maintenance Tools (2)
6. **`check_credential_status`** - System health check
7. **`update_streaming_credentials`** - Admin credential update

## Tools Kept in Main Agent (17 tools)

### User Query Tools (6)
- `query_user_watch_history` - "What have I watched?"
- `query_user_watchlist` - "What's on my watchlist?"
- `get_aggregated_recommendations` - "What should I watch?"
- `get_continue_watching` - "What am I watching?"
- `search_user_watch_history` - "Have I watched X?"
- `get_user_watch_stats` - "What are my viewing stats?"

### Control Tools (5)
- `control_roku_tv` - TV control
- `send_fios_ir_command` - FIOS control
- `tune_fios_channel` - Channel changing
- `watch_game` - Watch sports games
- `launch_streaming_content` - Launch streaming content

### Lookup Tools (6)
- `query_sports_games` - Current games
- `get_channel_for_game` - Game channel lookup
- `get_tv_listings_now` - Current TV listings
- `search_tv_guide` - TV guide search
- `get_channel_info` - Channel schedule
- `lookup_streaming_content` - Content availability

## Sleeptime Agent

The sleeptime agent retains **13 tools** for:
- Running scheduled background syncs (5 tools)
- Maintenance tasks (2 tools)
- Data query and analysis (6 tools)

### Tools Removed from Sleeptime Agent (11 tools)

**Hardware Control Tools (5):**
- `control_roku_tv` - Hardware control
- `send_fios_ir_command` - Hardware control
- `tune_fios_channel` - Hardware control
- `watch_game` - Hardware orchestration
- `launch_streaming_content` - User interaction

**Real-time User Query Tools (6):**
- `query_sports_games` - Real-time game queries
- `get_channel_for_game` - Real-time channel lookup
- `get_tv_listings_now` - Real-time TV listings
- `search_tv_guide` - Real-time guide search
- `get_channel_info` - Real-time channel info
- `lookup_streaming_content` - Real-time content lookup

## Implementation

The registration script (`register_sports_media_tools.py`) now:
1. Registers all 24 tools
2. Attaches 17 tools to the main agent (excludes 7 background/maintenance tools)
3. Attaches 13 tools to the sleeptime agent (excludes 11 user-interaction/hardware tools)

### Final Tool Distribution

- **Main Agent**: 17 tools (user queries, control, lookups)
- **Sleeptime Agent**: 13 tools (sync, maintenance, data analysis)
- **Overlap**: 6 tools (data query tools used by both agents)

To apply changes, run:
```bash
python3 register_sports_media_tools.py
```

