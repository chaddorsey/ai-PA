# Drive Analytics Date-Specific Queries

## How the Agent Handles Date-Specific Requests

When a user asks for Drive analytics for a specific date, the agent should follow this workflow:

### Example Request
**User**: "Show me the top edited documents across the workspace for Thursday, November 13."

### Agent Workflow

1. **Parse the date from the user's request**
   - Extract: "Thursday, November 13" → Convert to: `"2025-11-13"` (YYYY-MM-DD format)
   - Note: The agent should determine the year from context (current year is 2025)

2. **Call the appropriate tool**
   - Use `get_top_documents(category="edited", count=5, include_links=True)`
   - The tool will return instructions to read from the memory block

3. **Read the memory block**
   - Use `memory_read` to read `drive_analytics_workspace`
   - Parse the JSON content

4. **Check for the requested date**
   - Look for the key `"2025-11-13"` in the parsed JSON
   - If the block is empty (`{}`), proceed to step 5
   - If the block has entries but not the requested date, proceed to step 5
   - If the date exists, proceed to step 6

5. **Handle missing data**
   - Inform the user: "I don't have analytics data for November 13, 2025 yet."
   - Offer to collect it: "Would you like me to collect the data for that date? I can run `collect_daily_workspace_activity('2025-11-13')` to gather it."
   - If the user agrees, call the collection tool and then retry the query

6. **Extract and present the data**
   - Navigate to: `data["2025-11-13"]["top_five"]["most_edited"]`
   - Extract the top 5 items (or requested count)
   - Format the response with:
     - Document title
     - Edit count
     - Document link (if `include_links=True`)
     - Owner (if available)

### Example Response (when data exists)

```
Here are the top 5 most edited documents for Thursday, November 13, 2025:

1. **RITEL – NSAI for Generation of Open Pedagogy**
   - Edit count: 290
   - Owner: cdorsey@concord.org
   - Link: https://docs.google.com/document/d/1jgEgFVPu3WcVDne7FqYOz_MiHIShQXnXwIrcX5LWwIU/edit

2. **Teacher-in-the-Loop summary and narrative**
   - Edit count: 245
   - Owner: ddamelin@concord.org
   - Link: https://docs.google.com/document/d/1K72eiol7zRhKzHWpNgk05-CWMFZgOryzcztdwH5OqUQ/edit

[... continues for top 5 ...]
```

### Example Response (when data doesn't exist)

```
I don't have analytics data for Thursday, November 13, 2025 yet. 

Would you like me to collect it? I can run the collection tool to gather workspace activity data for that date. This will take a few moments as it queries the Google Admin Reports API.

Should I proceed with collecting the data?
```

## Date Format Reference

- **Memory block keys**: Always use `YYYY-MM-DD` format (e.g., `"2025-11-13"`)
- **User requests**: May be in natural language (e.g., "Thursday, November 13", "Nov 13", "11/13/2025")
- **Agent parsing**: Convert user's date to `YYYY-MM-DD` before looking up in memory block

## Related Tools

- `get_top_documents(category, count, include_links, date)` - Get top documents for a category
- `get_drive_analytics_summary(period, scope)` - Get summary for a period
- `collect_daily_workspace_activity(date)` - Collect data for a specific date

