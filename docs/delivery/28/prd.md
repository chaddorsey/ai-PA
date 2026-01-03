# PBI-28: Series Tracking Management System

[View in Backlog](../backlog.md#user-content-28)

## Overview

Extend the sports-and-media-tools series progress tracking with a comprehensive tracking management system that supports intentional series tracking, multi-service availability, manual progress overrides, and new season monitoring.

## Problem Statement

The current series progress implementation is scrape-centric rather than intent-centric:
- No explicit "tracked series" concept - just raw scraped data
- No distinction between completed series and those awaiting new seasons
- No way to mark episodes watched when streaming service doesn't reflect it (service migration)
- No cross-service availability awareness
- No integration between watchlists and tracked series
- Users cannot casually add series by title for automatic lookup and tracking

## User Stories

1. **As a user**, I want to add a series to tracking by just naming it, so the agent can find it and set up tracking automatically.
2. **As a user**, I want to mark series as "watching", "finished", or "dropped" so the agent knows which to actively monitor.
3. **As a user**, I want to manually specify episodes I've already watched (e.g., on a previous service) so the agent tracks only truly unwatched episodes.
4. **As a user**, I want to be notified when new seasons become available for series I've finished watching.
5. **As a user**, I want series on my watchlists to be automatically tracked unless I remove them from tracking.
6. **As a user**, I want to see which streaming services have a series and how many seasons each has available.

## Technical Approach

### Database Schema

New `tracked_series` table in content database:

```sql
CREATE TABLE tracked_series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    justwatch_id TEXT,
    imdb_id TEXT,
    
    -- Status fields
    tracking_status TEXT DEFAULT 'active',      -- watching, finished, dropped, on_hold
    watch_status TEXT DEFAULT 'not_started',    -- not_started, in_progress, fully_watched
    
    -- Service information
    preferred_service TEXT,
    available_services TEXT,  -- JSON: [{service, seasons, last_checked}]
    
    -- Progress tracking
    total_seasons_known INTEGER,
    total_episodes_known INTEGER,
    watched_episode_count INTEGER DEFAULT 0,
    
    -- Manual overrides
    manual_progress TEXT,  -- JSON: {watched_through, additional_watched, note}
    
    -- Timestamps
    last_synced_at TEXT,
    last_availability_check TEXT,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    -- Metadata
    notes TEXT,
    auto_tracked_from_watchlist BOOLEAN DEFAULT FALSE,
    
    UNIQUE(user_id, justwatch_id)
);

CREATE INDEX idx_tracked_series_user_status ON tracked_series(user_id, tracking_status);
CREATE INDEX idx_tracked_series_user_service ON tracked_series(user_id, preferred_service);
```

Extend `series_progress` table:
```sql
ALTER TABLE series_progress ADD COLUMN is_manual BOOLEAN DEFAULT FALSE;
ALTER TABLE series_progress ADD COLUMN source TEXT DEFAULT 'scraped';
```

### New Letta Tools

**Management Tools:**
| Tool | Purpose |
|------|---------|
| `add_tracked_series(title, preferred_service)` | Add series by title with JustWatch lookup |
| `remove_tracked_series(title)` | Stop tracking a series |
| `update_tracking_status(title, status)` | Set watching/finished/dropped/on_hold |
| `set_preferred_service(title, service)` | Choose where to watch |
| `mark_episodes_watched(title, watched_spec, note)` | Manual progress with flexible spec |
| `clear_manual_progress(title)` | Reset overrides |

**Query Tools:**
| Tool | Purpose |
|------|---------|
| `get_tracked_series(status_filter, service_filter)` | List tracked series |
| `get_series_status(title)` | Full status for one series |
| `check_series_availability(title)` | JustWatch lookup for streaming locations |

**Background Tools:**
| Tool | Purpose |
|------|---------|
| `sync_all_active_series()` | Sync progress for all active series |
| `check_new_seasons()` | Monitor for new season availability |
| `refresh_service_availability()` | Update where series are streaming |
| `reconcile_watchlist_tracking()` | Auto-track watchlist items |

### Manual Progress Specification

The `mark_episodes_watched` tool accepts flexible specifications:
- `"seasons 1-3"` → Marks S1, S2, S3 as fully watched
- `"through S2E5"` → Marks everything up to and including S2E5
- `"S1E3"` → Marks single episode
- `"S3E1-5"` → Marks range within season

Stored as JSON:
```json
{
  "watched_through": {"season": 2, "episode": 5},
  "additional_watched": [{"season": 3, "episode": 1}],
  "source_note": "Originally watched on Amazon Prime"
}
```

### Watchlist Integration

- Series from watchlists auto-added with `auto_tracked_from_watchlist=TRUE`
- Can be removed from tracking while staying on watchlist
- Tracked series don't need to be on any watchlist
- `reconcile_watchlist_tracking()` runs periodically to sync

### New Season Monitoring

Weekly job for `tracking_status IN ('watching', 'finished')`:
1. Query JustWatch for current season count
2. Compare to `total_seasons_known`
3. If new season detected:
   - Update `watch_status` to `in_progress`
   - Log to memory block
4. Store `last_availability_check` timestamp

## UX/UI Considerations

**Natural Language Examples:**
- "Add The Mandalorian to my tracked series" → `add_tracked_series`
- "I finished watching Severance" → `update_tracking_status(..., 'finished')`
- "I dropped The Rings of Power" → `update_tracking_status(..., 'dropped')`
- "I watched The Americans through season 4 on Amazon" → `mark_episodes_watched`
- "What series haven't I finished?" → `get_tracked_series(status_filter='in_progress')`
- "Where can I watch Ted Lasso?" → `check_series_availability`

## Acceptance Criteria

1. Users can add series by casual title mention with auto-lookup
2. Series have distinct tracking_status (watching/finished/dropped/on_hold) and watch_status (not_started/in_progress/fully_watched)
3. Manual progress overrides persist and affect progress calculations
4. Watchlist series are auto-tracked unless explicitly removed
5. New season detection works for finished series
6. Multi-service availability is tracked with per-service season counts
7. All tools registered with appropriate agents (main vs sleeptime)
8. Multi-user support works correctly

## Dependencies

- JustWatch scraper for title lookup and availability
- Existing series_progress scraping infrastructure
- Existing watchlist polling infrastructure

## Open Questions

None - all clarified in design discussion.

## Related Tasks

See [tasks.md](./tasks.md)

