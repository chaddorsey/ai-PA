# Drive Analytics Memory Structure Update

## Problem

The original design created individual memory blocks for each date:
- `drive_analytics_daily_2025-11-13`
- `drive_analytics_daily_2025-11-14`
- etc.

This approach:
- Creates memory block clutter (hundreds of blocks over time)
- Makes it hard to query historical data
- Violates Letta's recommended limit of < 20 blocks per agent
- Causes errors when blocks don't exist yet

## Solution

**Consolidated Memory Blocks** with date-indexed JSON:

1. **`drive_analytics_workspace`** - All workspace activity data
2. **`drive_analytics_personal`** - All personal activity data
3. **`drive_analytics_mentions`** - All mentions data
4. **`drive_analytics_averages`** - Running averages
5. **`drive_analytics_config`** - Configuration

Each block contains JSON with date keys:
```json
{
  "2025-11-13": { /* data for Nov 13 */ },
  "2025-11-14": { /* data for Nov 14 */ },
  ...
}
```

## Benefits

- ✅ Only 4-5 memory blocks total (well under the 20-block limit)
- ✅ Easy date-based queries (simple JSON key lookup)
- ✅ Automatic cleanup (remove entries older than 50 days)
- ✅ No stranded blocks
- ✅ Scalable (can store years of data in a single block)

## Updated Tools

All query tools have been updated to reference the consolidated blocks:
- `get_drive_analytics_summary()` → reads `drive_analytics_workspace` or `drive_analytics_personal`
- `get_my_drive_activity()` → reads `drive_analytics_personal`
- `get_drive_mentions()` → reads `drive_analytics_mentions`
- `get_top_documents()` → reads `drive_analytics_workspace`
- `get_recent_my_activity()` → reads `drive_analytics_personal`

## Agent Instructions

When the scheduled reminder triggers, the agent should:

1. Call the collection tools
2. For each result:
   - Read the consolidated block (or create it with `{}` if missing)
   - Parse the JSON
   - Extract the date from the tool result
   - Add/update: `block_data[date] = tool_result_data`
   - Remove entries older than 50 days
   - Use `memory_replace` to update the block

See `DRIVE_ANALYTICS_MEMORY_GUIDE.md` for detailed instructions.

## Migration

If you have existing per-date memory blocks, you can:
1. Read each block
2. Extract the date from the block name
3. Merge into the appropriate consolidated block
4. Delete the old per-date blocks

Or simply let the new system start fresh - old blocks will be ignored.

