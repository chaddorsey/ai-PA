# Drive Analytics Tools Setup Guide

## Overview

This guide explains how to set up and use the Drive Analytics tools for Letta agents.

## Prerequisites

1. **Google OAuth Credentials**: You need `gcp-oauth.admin-reports.desktop.json` file
   - Location: `~/.gmail-mcp/gcp-oauth.admin-reports.desktop.json` or set `GMAIL_OAUTH_PATH`
   - This should be a Desktop OAuth client (not Web) to avoid HTTPS restrictions

2. **OAuth Token**: Authenticate once to get tokens
   - Tokens will be saved to `~/.gmail-mcp/admin-reports.credentials.json`
   - Set `GMAIL_CREDENTIALS_PATH` to override location

3. **Python Dependencies**: Install required packages
   ```bash
   cd letta
   pip install -r requirements.txt
   ```

4. **Environment Variables** (optional):
   - `MY_EMAIL`: Your email address (defaults to `cdorsey@concord.org`)
   - `GMAIL_OAUTH_PATH`: Path to OAuth keys file
   - `GMAIL_CREDENTIALS_PATH`: Path to store/load tokens
   - `LETTA_BASE_URL`: Letta server URL (defaults to `http://localhost:8283`)
   - `LETTA_AGENT_ID`: Your Letta agent ID

## Setup Steps

### 1. Install Dependencies

```bash
cd /Users/dorseyhomeserver/ai-PA/letta
pip install -r requirements.txt
```

### 2. Register Tools with Letta

```bash
python3 register_drive_analytics_tools.py
```

This will register all 11 Drive analytics tools with your Letta server.

### 3. Attach Tools to Your Agent

```bash
export LETTA_AGENT_ID=your-agent-id
python3 attach_drive_analytics_to_agent.py
```

This attaches the tools to your agent so it can use them.

### 4. Set Up Scheduled Reminders

Use the `schedule_reminder` tool (from scheduler MCP) to set up daily collection:

**Daily Collection** (every weekday at 6am):
```
Schedule a reminder with:
- Title: "Daily Drive Analytics Collection"
- Message: "Run the Drive analytics collection tools for yesterday's workday. Call collect_daily_workspace_activity(), collect_daily_personal_activity(), and collect_daily_mentions(). Process the JSON results and store them in memory blocks using memory_replace. Update the memory blocks: drive_analytics_daily_YYYY-MM-DD, drive_analytics_personal_YYYY-MM-DD, and drive_analytics_mentions_YYYY-MM-DD with the data from each tool. Use the date from yesterday (format: YYYY-MM-DD)."
- When: "every weekday at 6am"
- Agent ID: your-agent-id
```

**Weekly Aggregation** (every Sunday at 6am):
```
Schedule a reminder with:
- Title: "Weekly Drive Analytics Aggregation"
- Message: "Calculate running averages for Drive analytics. Call calculate_running_averages() which will read historical data from memory blocks and calculate 3-day, 10-day, and 50-day averages. Store the results in the drive_analytics_averages memory block using memory_replace."
- When: "every Sunday at 6am"
- Agent ID: your-agent-id
```

## Available Tools

### Data Collection Tools (Called by Scheduled Reminders)

1. **`collect_daily_workspace_activity(date=None)`**
   - Collects workspace-wide Drive activity
   - Returns JSON with top-five lists (edited, shared, commented, viewed, active users)

2. **`collect_daily_personal_activity(date=None)`**
   - Collects your personal Drive activity
   - Returns JSON with your activity patterns and top documents with links

3. **`collect_daily_mentions(date=None)`**
   - Checks for comments mentioning you
   - Returns JSON with mention details, timestamps, and document links

4. **`calculate_running_averages()`**
   - Calculates running averages (requires Letta API access - not yet fully implemented)

### Query Tools (Called On-Demand)

5. **`get_drive_analytics_summary(period="yesterday", scope="workspace")`**
   - Gets summary from memory blocks

6. **`get_drive_trends(metric="document", comparison_period="10_day")`**
   - Compares current data to historical averages

7. **`get_my_drive_activity(days=7, include_links=True)`**
   - Gets your personal activity with document links

8. **`get_drive_mentions(days=7, unread_only=False)`**
   - Gets comments mentioning you from memory

9. **`get_document_activity(doc_ids, days=7)`**
   - Gets activity for specific documents (queries API directly)

10. **`get_top_documents(category="edited", count=5, include_links=True)`**
    - Gets top documents by category with links

11. **`get_recent_my_activity(activity_type="all", days=3, include_links=True)`**
    - Gets documents you've viewed/edited recently with links

## Testing

Test a tool manually:

```python
from drive_analytics_tools import collect_daily_workspace_activity

result = collect_daily_workspace_activity("2025-11-16")
print(result)
```

## Troubleshooting

### OAuth Authentication Issues

If you get authentication errors:
1. Delete `~/.gmail-mcp/admin-reports.credentials.json`
2. Run a tool - it will open a browser for authentication
3. Complete the OAuth flow
4. Tokens will be saved automatically

### API Errors

- **403 Forbidden**: Check that Admin SDK API is enabled in Google Cloud Console
- **Insufficient Permissions**: Ensure you're using a Super Admin account for Admin Reports API
- **Rate Limits**: Tools include delays between requests to respect rate limits

### Tool Registration Issues

- Ensure Letta server is running
- Check `LETTA_BASE_URL` is correct
- Verify you have permissions to create tools

## Next Steps

1. Test tools manually to verify OAuth works
2. Register and attach tools to your agent
3. Set up scheduled reminders
4. Test end-to-end: reminder → tool execution → memory storage
5. Iterate based on usage

