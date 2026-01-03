# Tool Allocation Analysis

## Tools to REMOVE from Main Agent

### Background Sync/Polling Tools (Sleeptime Only)
These run automatically on schedule and don't need user interaction:

1. **`poll_watch_history`** ❌
   - **Why remove**: Background sync tool, runs on schedule
   - **Keep in**: Sleeptime agent only

2. **`poll_watchlists`** ❌
   - **Why remove**: Background sync tool, runs on schedule
   - **Keep in**: Sleeptime agent only

3. **`poll_recommendations`** ❌
   - **Why remove**: Background sync tool, runs on schedule
   - **Keep in**: Sleeptime agent only

4. **`sync_all_streaming_data`** ❌
   - **Why remove**: Full background sync, runs on schedule
   - **Keep in**: Sleeptime agent only

5. **`add_content_to_database`** ❌
   - **Why remove**: Background scraping tool, not user-initiated
   - **Keep in**: Sleeptime agent only

### Maintenance/Admin Tools (Sleeptime Only)
These are for system maintenance, not user queries:

6. **`check_credential_status`** ❌
   - **Why remove**: System health check, runs on schedule
   - **Keep in**: Sleeptime agent only

7. **`update_streaming_credentials`** ❌
   - **Why remove**: Admin function, user doesn't need direct access
   - **Keep in**: Sleeptime agent only (or remove from both if handled separately)

---

## Tools to KEEP in Main Agent

### User Query Tools (Main Agent Needs)
Users will ask questions like "What have I watched?" or "What's on my list?"

8. **`query_user_watch_history`** ✅
   - **Why keep**: User might ask "What shows have I watched?"

9. **`query_user_watchlist`** ✅
   - **Why keep**: User might ask "What's on my Netflix watchlist?"

10. **`get_aggregated_recommendations`** ✅
    - **Why keep**: User might ask "What should I watch?"

11. **`get_continue_watching`** ✅
    - **Why keep**: User might ask "What am I in the middle of watching?"

12. **`search_user_watch_history`** ✅
    - **Why keep**: User might ask "Have I watched Breaking Bad?"

13. **`get_user_watch_stats`** ✅
    - **Why keep**: User might ask "What's my most watched service?"

### Real-time Control Tools (Main Agent Needs)
Users will ask to control TV, launch content, etc.

14. **`control_roku_tv`** ✅
    - **Why keep**: User might ask "Turn on the TV" or "Launch Netflix"

15. **`send_fios_ir_command`** ✅
    - **Why keep**: User might ask to control cable box

16. **`tune_fios_channel`** ✅
    - **Why keep**: User might ask "Change to channel 570"

17. **`watch_game`** ✅
    - **Why keep**: User might ask "Watch the Patriots game"

18. **`launch_streaming_content`** ✅
    - **Why keep**: User might ask "Play Stranger Things on Netflix"

### Real-time Lookup Tools (Main Agent Needs)
Users will ask about current games, TV listings, content availability

19. **`query_sports_games`** ✅
    - **Why keep**: User might ask "What games are on today?"

20. **`get_channel_for_game`** ✅
    - **Why keep**: User might ask "What channel is the game on?"

21. **`get_tv_listings_now`** ✅
    - **Why keep**: User might ask "What's on TV right now?"

22. **`search_tv_guide`** ✅
    - **Why keep**: User might ask "When is the Patriots game on?"

23. **`get_channel_info`** ✅
    - **Why keep**: User might ask "What's on ESPN tonight?"

24. **`lookup_streaming_content`** ✅
    - **Why keep**: User might ask "Where can I watch The Bear?"

---

## Summary

### Main Agent Should Have: 17 tools
- 6 user query tools (watch history, watchlists, recommendations, stats)
- 5 control tools (Roku, FIOS, game watching, content launching)
- 6 lookup tools (sports games, TV listings, content availability)

### Main Agent Should Remove: 7 tools
- 5 background sync/polling tools
- 2 maintenance/admin tools

### Sleeptime Agent Should Have: All 24 tools
- Needs all tools to run scheduled syncs and maintenance

