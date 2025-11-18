# Drive Analytics - Critical Agent Instructions

## Problem: Agent Not Passing Date Parameter

The agent has been calling `collect_daily_workspace_activity()` without the `date` parameter, causing it to default to the last workday instead of the date the user requested.

## Solution: Always Pass Date Parameter

When the user requests data for a specific date, the agent **MUST** pass the `date` parameter to the collection function.

### Correct Usage

**User**: "Show me top documents for November 10, 2025"

**Agent should**:
1. Parse "November 10, 2025" → `"2025-11-10"`
2. Call: `collect_daily_workspace_activity(date='2025-11-10')`

**NOT**: `collect_daily_workspace_activity()` ← This defaults to last workday!

### Function Signature

```python
collect_daily_workspace_activity(date: Optional[str] = None) -> str
```

- `date`: Date in YYYY-MM-DD format (e.g., `'2025-11-10'`)
- **REQUIRED** when user requests a specific date
- If not provided, defaults to last workday (which may not be what user wants)

### Updated Function Behavior

The function now:
1. **Validates date format** - Returns clear error if format is wrong
2. **Uses exact date** - Queries exactly the date provided (even weekends)
3. **Returns date info** - JSON includes `date` (queried) and `date_requested` (what was passed)

### Example Response JSON

```json
{
  "type": "drive_analytics_daily",
  "date": "2025-11-10",
  "date_requested": "2025-11-10",
  "is_workday": true,
  "summary": {...},
  "top_five": {...}
}
```

If the agent calls without a date and it defaults:
```json
{
  "type": "drive_analytics_daily",
  "date": "2025-11-14",  // Last workday
  "date_requested": null,  // No date was passed!
  "is_workday": true,
  ...
}
```

### Agent Instructions Updated

All query tools now include explicit instructions:
- "IMPORTANT: When calling collect_daily_workspace_activity() to collect data, you MUST pass the date parameter."
- "For example, if the user asks for November 10, 2025, you must call: collect_daily_workspace_activity(date='2025-11-10')."
- "Do NOT call collect_daily_workspace_activity() without the date parameter, as it will default to the last workday and may not match what the user requested."

## Next Steps

1. **Re-register tools** so agent gets updated function signatures and docstrings
2. **Test** by asking for a specific date and verifying the agent passes the date parameter
3. **Monitor** the `date_requested` field in responses to confirm correct behavior

