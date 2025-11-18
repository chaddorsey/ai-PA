# Drive Analytics Tools - Date-Specific Query Updates

## Summary

All query tools that read from memory blocks have been updated to support date-specific requests. This allows users to ask for data for specific dates (e.g., "Thursday, November 13") rather than just relative periods (e.g., "yesterday", "last 7 days").

## Updated Tools

### 1. `get_top_documents()`
**Added**: `date: Optional[str] = None` parameter

**Usage**:
- Without date: Returns top documents from most recent entry
- With date: Returns top documents for specific date (YYYY-MM-DD format)

**Example requests**:
- "Show me the top edited documents" → Uses most recent entry
- "Show me the top edited documents for Thursday, November 13" → Looks for "2025-11-13"

### 2. `get_drive_analytics_summary()`
**Added**: `date: Optional[str] = None` parameter

**Usage**:
- Without date: Uses `period` parameter ("yesterday", "today", etc.)
- With date: Overrides `period` and looks for specific date

**Example requests**:
- "Get summary for yesterday" → Uses period logic
- "Get summary for November 13, 2025" → Looks for "2025-11-13"

### 3. `get_my_drive_activity()`
**Added**: `start_date: Optional[str] = None`, `end_date: Optional[str] = None` parameters

**Usage**:
- Without dates: Uses `days` parameter to look back
- With dates: Extracts entries for date range (inclusive)

**Example requests**:
- "Get my activity for the past 7 days" → Uses days=7
- "Get my activity from November 10 to November 13" → Extracts "2025-11-10" to "2025-11-13"

### 4. `get_drive_mentions()`
**Added**: `start_date: Optional[str] = None`, `end_date: Optional[str] = None` parameters

**Usage**:
- Without dates: Uses `days` parameter to look back
- With dates: Extracts entries for date range (inclusive)

**Example requests**:
- "Get mentions from the past week" → Uses days=7
- "Get mentions from November 10 to November 13" → Extracts "2025-11-10" to "2025-11-13"

### 5. `get_recent_my_activity()`
**Added**: `start_date: Optional[str] = None`, `end_date: Optional[str] = None` parameters

**Usage**:
- Without dates: Uses `days` parameter to look back
- With dates: Extracts entries for date range (inclusive)

**Example requests**:
- "Get my recent activity" → Uses days=3
- "Get my recent activity from November 10 to November 13" → Extracts "2025-11-10" to "2025-11-13"

## Tools Not Updated

### `get_drive_trends()`
- Compares current activity to historical averages
- Doesn't need specific date support (uses relative periods)

### `get_document_activity()`
- Queries Admin Reports API directly (not memory blocks)
- Already supports date ranges via API parameters

## Agent Behavior

All updated tools now instruct the agent to:

1. **Parse dates from natural language** (e.g., "Thursday, November 13" → "2025-11-13")
2. **Check if data exists** for the requested date(s)
3. **Inform the user** if data is missing
4. **Offer to collect data** using the appropriate collection tool if needed

## Date Format

- **Memory block keys**: Always `YYYY-MM-DD` format (e.g., `"2025-11-13"`)
- **User requests**: May be in natural language
- **Agent parsing**: Converts user's date to `YYYY-MM-DD` before lookup

## Example Workflow

**User**: "Show me the top edited documents for Thursday, November 13"

1. Agent calls `get_top_documents(category="edited", count=5)`
2. Tool instructs agent to parse "Thursday, November 13" → "2025-11-13"
3. Agent reads `drive_analytics_workspace` memory block
4. Agent looks for key `"2025-11-13"` in the JSON
5. If found: Extract and return `data["2025-11-13"]["top_five"]["most_edited"]`
6. If not found: Inform user and offer to collect using `collect_daily_workspace_activity('2025-11-13')`

