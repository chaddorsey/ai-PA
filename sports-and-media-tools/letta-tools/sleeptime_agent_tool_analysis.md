# Sleeptime Agent Tool Analysis

## Sleeptime Agent's Core Responsibilities

1. **Regular data updates** - Poll streaming services for fresh data
2. **Data observation** - Read and analyze existing patterns
3. **Information curation** - Aggregate and prepare data for main agent
4. **Maintenance** - Monitor system health and credentials
5. **Background scraping** - Enrich database with content metadata

## Tools to REMOVE from Sleeptime Agent

### Hardware Control Tools (5)
These are user-interaction focused, not background tasks:

1. **`control_roku_tv`** ❌
   - **Why remove**: Hardware control for user interaction
   - **Keep in**: Main agent only

2. **`send_fios_ir_command`** ❌
   - **Why remove**: Hardware control for user interaction
   - **Keep in**: Main agent only

3. **`tune_fios_channel`** ❌
   - **Why remove**: Hardware control for user interaction
   - **Keep in**: Main agent only

4. **`watch_game`** ❌
   - **Why remove**: Orchestrates hardware control for immediate user action
   - **Keep in**: Main agent only

5. **`launch_streaming_content`** ❌
   - **Why remove**: Launches content for immediate viewing (user interaction)
   - **Keep in**: Main agent only

### Real-time User Query Tools (6)
These answer "what's happening now" questions, not background curation:

6. **`query_sports_games`** ❌
   - **Why remove**: Real-time game queries for user interaction
   - **Keep in**: Main agent only

7. **`get_channel_for_game`** ❌
   - **Why remove**: Real-time lookup for user queries
   - **Keep in**: Main agent only

8. **`get_tv_listings_now`** ❌
   - **Why remove**: Real-time TV listings for user queries
   - **Note**: Schedule refresh could use direct API, not this tool
   - **Keep in**: Main agent only

9. **`search_tv_guide`** ❌
   - **Why remove**: Real-time search for user queries
   - **Keep in**: Main agent only

10. **`get_channel_info`** ❌
    - **Why remove**: Real-time channel info for user queries
    - **Keep in**: Main agent only

11. **`lookup_streaming_content`** ❌
    - **Why remove**: Real-time content availability for user queries
    - **Keep in**: Main agent only

---

## Tools to KEEP in Sleeptime Agent

### Background Sync/Polling Tools (5)
Essential for regular data updates:

1. **`poll_watch_history`** ✅
2. **`poll_watchlists`** ✅
3. **`poll_recommendations`** ✅
4. **`sync_all_streaming_data`** ✅
5. **`add_content_to_database`** ✅

### Maintenance Tools (2)
System health and credential management:

6. **`check_credential_status`** ✅
7. **`update_streaming_credentials`** ✅

### Data Query/Analysis Tools (6)
For observing patterns and curating information:

8. **`query_user_watch_history`** ✅ - Analyze viewing patterns
9. **`query_user_watchlist`** ✅ - Curate watchlist data
10. **`get_aggregated_recommendations`** ✅ - Aggregate recommendations
11. **`get_continue_watching`** ✅ - Identify in-progress content
12. **`search_user_watch_history`** ✅ - Pattern analysis
13. **`get_user_watch_stats`** ✅ - Statistical analysis

---

## Summary

### Sleeptime Agent Should Have: **13 tools**
- 5 background sync/polling tools
- 2 maintenance tools
- 6 data query/analysis tools

### Sleeptime Agent Should Remove: **11 tools**
- 5 hardware control tools
- 6 real-time user query tools

### Main Agent Should Have: **17 tools** (unchanged)
- All user-interaction focused tools

