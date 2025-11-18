# Drive Analytics Memory Block Management Guide

## Overview

Drive analytics data is stored in **consolidated memory blocks** that contain JSON with date-indexed entries. This approach prevents memory block clutter and makes it easy to query historical data.

## Memory Block Structure

### Block Names

1. **`drive_analytics_workspace`** - Workspace-wide activity data
2. **`drive_analytics_personal`** - Your personal activity data
3. **`drive_analytics_mentions`** - Comments mentioning you
4. **`drive_analytics_averages`** - Running averages and trends
5. **`drive_analytics_config`** - Configuration settings

### Block Format

Each block (except `drive_analytics_averages` and `drive_analytics_config`) contains JSON with date keys:

```json
{
  "2025-11-13": {
    "type": "drive_analytics_daily",
    "date": "2025-11-13",
    "is_workday": true,
    "summary": {
      "total_activities": 5248,
      "unique_users": 68,
      "unique_documents": 1956
    },
    "top_five": {
      "most_edited": [...],
      "most_shared": [...],
      "most_commented": [...],
      "most_viewed": [...],
      "most_active_users": [...]
    }
  },
  "2025-11-14": {
    "type": "drive_analytics_daily",
    "date": "2025-11-14",
    ...
  }
}
```

## Agent Instructions for Daily Collection

When the scheduled reminder triggers, the agent should:

1. **Call the collection tools**:
   - `collect_daily_workspace_activity()` → returns JSON for workspace data
   - `collect_daily_personal_activity()` → returns JSON for personal data
   - `collect_daily_mentions()` → returns JSON for mentions

2. **For each tool result**:
   - Read the corresponding memory block (or create it if it doesn't exist)
   - Parse the existing JSON (or start with `{}` if empty)
   - Extract the date from the tool result
   - Add/update the entry: `data[date] = tool_result_data`
   - Remove entries older than 50 days
   - Use `memory_replace` to update the block

3. **Example workflow**:
   ```
   workspace_result = collect_daily_workspace_activity()
   workspace_data = json.loads(workspace_result)
   date = workspace_data["date"]  # e.g., "2025-11-14"
   
   # Read existing block
   existing = memory_read("drive_analytics_workspace")
   if not existing:
       existing = "{}"
   
   # Parse and merge
   block_data = json.loads(existing)
   block_data[date] = workspace_data
   
   # Remove old entries (older than 50 days)
   cutoff = (datetime.now() - timedelta(days=50)).strftime("%Y-%m-%d")
   block_data = {k: v for k, v in block_data.items() if k >= cutoff}
   
   # Update block
   memory_replace("drive_analytics_workspace", json.dumps(block_data, indent=2))
   ```

## Querying Data

When querying data:

1. **Read the appropriate block**:
   - Workspace queries → `drive_analytics_workspace`
   - Personal queries → `drive_analytics_personal`
   - Mentions queries → `drive_analytics_mentions`

2. **Parse the JSON and extract date entries**:
   ```python
   block_content = memory_read("drive_analytics_workspace")
   data = json.loads(block_content)
   
   # Get specific date
   date_data = data.get("2025-11-14")
   
   # Get date range
   start_date = "2025-11-10"
   end_date = "2025-11-14"
   range_data = {k: v for k, v in data.items() if start_date <= k <= end_date}
   
   # Get latest entry
   latest_date = max(data.keys())
   latest_data = data[latest_date]
   ```

## Benefits of This Approach

- **Low memory block count**: Only 4-5 blocks total, regardless of how many days of data
- **Easy date queries**: Simple JSON key lookups
- **Automatic cleanup**: Remove entries older than 50 days
- **No clutter**: No stranded per-date memory blocks
- **Efficient**: All related data in one place

## Memory Block Limits

- Recommended: < 50k characters per block
- Recommended: < 20 blocks per agent
- Our approach: 4-5 blocks, each with ~50 days of data (well within limits)

