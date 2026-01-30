#!/usr/bin/env python3
"""
Register Slack Analytics Tools with Letta Agent
"""

import os
import json
import urllib.request
import urllib.parse

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"


def http_post(url, data):
    """Make HTTP POST request."""
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"HTTP Error {e.code}: {error_body}")
        return None


def http_get(url):
    """Make HTTP GET request."""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f"GET Error: {e}")
        return None


def http_patch(url, data):
    """Make HTTP PATCH request."""
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method='PATCH')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"PATCH Error {e.code}: {error_body}")
        return None


def create_tool(source_code, tags=None):
    """Create a tool in Letta."""
    payload = {
        "source_code": source_code,
        "tags": tags or []
    }
    return http_post(f"{LETTA_BASE}/v1/tools/", payload)


def get_all_tools():
    """Get all tools."""
    tools = http_get(f"{LETTA_BASE}/v1/tools/")
    return tools if isinstance(tools, list) else []


def find_tool_by_name(name):
    """Find a tool by name."""
    tools = get_all_tools()
    for tool in tools:
        if tool.get("name") == name:
            return tool
    return None


def attach_tools_to_agent(agent_id, tool_ids):
    """Attach tools to agent."""
    agent = http_get(f"{LETTA_BASE}/v1/agents/{agent_id}")
    if not agent:
        return False
    
    current_tool_refs = agent.get("tools", [])
    
    # Extract current tool IDs (handle both string and dict formats)
    current_tool_ids = set()
    for ref in current_tool_refs:
        if isinstance(ref, dict):
            current_tool_ids.add(ref.get("id"))
        elif isinstance(ref, str):
            current_tool_ids.add(ref)
    
    # Ensure new tool IDs are strings
    new_tool_ids = [t if isinstance(t, str) else str(t) for t in tool_ids]
    
    # Merge tool lists (convert to list of strings, dedupe, preserve order)
    all_tool_ids = list(dict.fromkeys(list(current_tool_ids) + new_tool_ids))
    
    # Update agent - use 'tool_ids' field (not 'tools')
    result = http_patch(f"{LETTA_BASE}/v1/agents/{agent_id}", {"tool_ids": all_tool_ids})
    return result is not None


# Tool 1: Trigger export with date range support
TOOL_1_SOURCE = '''import json

def trigger_slack_analytics_export(analytics_type: str = "channels", days_ago: int = 3, date_range_days: int = 1) -> str:
    """Trigger Slack analytics CSV export with custom date range.
    
    IMPORTANT: Slack does not allow exports when start_date == end_date.
    If date_range_days=1, the service automatically adjusts the end_date to be one day later
    to avoid this error.
    
    Args:
        analytics_type: Type of analytics (channels or members)
        days_ago: How many days ago to start (default 3, since recent data may not be available)
        date_range_days: Number of days to include (default 1). Note: If this results in the same
                        start and end date, the end date will be automatically adjusted.
    
    Returns:
        Success message with date range used, or error message if export failed
    
    Example:
        # Get channels data from 7 days ago (will use 7 days ago to 6 days ago)
        trigger_slack_analytics_export("channels", days_ago=7, date_range_days=1)
        
        # Get members data from last week (7 days starting 7 days ago)
        trigger_slack_analytics_export("members", days_ago=7, date_range_days=7)
    """
    import urllib.request
    import urllib.error
    
    # Call the HTTP endpoint running in slack-analytics-mcp-server
    import os
    BASE = os.getenv("SLACK_ANALYTICS_BASE_URL", "http://slack-analytics-mcp-server:8087")
    ENDPOINT_URL = f\"{BASE.rstrip('/')}/trigger-export\"
    
    if analytics_type not in ["channels", "members"]:
        return f"❌ Invalid analytics_type: {analytics_type}. Must be channels or members"
    
    try:
        payload = {
            "analytics_type": analytics_type,
            "days_ago": days_ago,
            "date_range_days": date_range_days
        }
        
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            ENDPOINT_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        response = urllib.request.urlopen(req, timeout=90)
        response_text = response.read().decode("utf-8")
        result = json.loads(response_text)
        
        # Detailed result inspection
        success = result.get("success")
        
        if success is True:
            date_info = result.get("date_range", {})
            start = date_info.get("start", "?") if date_info else "?"
            end = date_info.get("end", "?") if date_info else "?"
            
            # Include diagnostic info from stdout
            stdout_msg = result.get("stdout", "")
            diagnostic_info = ""
            
            # Check for key indicators in stdout
            if "button_clicked" in stdout_msg.lower() or "Clicked Export CSV" in stdout_msg:
                diagnostic_info = " (Button was clicked)"
            if "error" in stdout_msg.lower() or "failed" in stdout_msg.lower():
                # Extract error lines
                error_lines = [line for line in stdout_msg.split('\\n') if 'error' in line.lower() or 'failed' in line.lower() or '×' in line]
                if error_lines:
                    diagnostic_info += " | Warnings: " + ", ".join(error_lines[:2])
            
            note = "\\n\\nNote: If no file appears, check the service logs: docker logs slack-analytics-mcp-server --tail 50"
            return f"✓ Triggered {analytics_type} export for {start} to {end}. CSV will be in Slack Files in 1-2 min. Use list_recent_slack_files() to find it.{diagnostic_info}{note}"
        else:
            error_msg = result.get("error", "")
            stdout_msg = result.get("stdout", "")
            stderr_msg = result.get("stderr", "")
            
            # Build detailed error message
            msg_parts = []
            
            # Check stdout for specific error messages
            if stdout_msg:
                if "Unable to export your CSV" in stdout_msg:
                    msg_parts.append("Slack error: Unable to export your CSV. Please try again later.")
                elif "Export failed" in stdout_msg:
                    # Extract the error line
                    error_lines = [line for line in stdout_msg.split('\\n') if 'Export failed' in line or '✗' in line]
                    if error_lines:
                        msg_parts.append(error_lines[0])
                elif "Could not find or click Export CSV button" in stdout_msg:
                    msg_parts.append("Could not find or click the Export CSV button. The UI may have changed.")
            
            # Add generic error message if available
            if error_msg:
                if len(error_msg) > 500:
                    msg_parts.append(error_msg[:500] + "...")
                else:
                    msg_parts.append(error_msg)
            
            # Add stderr if present
            if stderr_msg:
                msg_parts.append(f"Error details: {stderr_msg[:200]}")
            
            if not msg_parts:
                msg_parts.append(f"Unknown error. Check service logs: docker logs slack-analytics-mcp-server --tail 50")
            
            return f"❌ Export failed: {' | '.join(msg_parts)}"
    except urllib.error.URLError as e:
        return f"❌ Network error: {str(e)}"
    except json.JSONDecodeError as e:
        return f"❌ Invalid JSON response: {str(e)}"
    except Exception as e:
        return f"❌ Error: {type(e).__name__}: {str(e)}"
'''

# Tool 2: List recent files
TOOL_2_SOURCE = '''import os
import json
from datetime import datetime, timedelta

def list_recent_slack_files(types: str = "csv", count: int = 10, hours_back: int = None) -> str:
    """List recent files in Slack workspace.
    
    Args:
        types: File types to filter (csv, pdf, all)  
        count: Number of files to retrieve from API (max 100)
        hours_back: Optional filter to only show files created within last N hours
    
    Returns:
        JSON with recent files including name, URL, timestamp, sorted by creation time (newest first)
    
    Note:
        Slack API may have a short delay (10-60 seconds) before newly created files appear.
        If you just ran an export and don't see it, wait a minute and try again, or use hours_back
        to filter for very recent files.
    """
    import urllib.request
    
    TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
    if not TOKEN:
        return "❌ SLACK_MCP_XOXP_TOKEN not set"
    
    try:
        # Request more files than needed to account for filtering
        request_count = min(count * 3, 100) if hours_back else min(count, 100)
        
        params = {
            "count": str(request_count),
            "sort": "timestamp",  # Sort by creation time
            "page": 1
        }
        if types != "all":
            params["types"] = types
        
        url = "https://slack.com/api/files.list?" + "&".join(f"{k}={v}" for k, v in params.items())
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
        
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        
        if not data.get("ok"):
            return f"❌ API error: {data.get('error')}"
        
        files = []
        now = datetime.now()
        cutoff_time = now - timedelta(hours=hours_back) if hours_back else None
        
        for f in data.get("files", []):
            created_ts = f.get("created", 0)
            created_dt = datetime.fromtimestamp(created_ts)
            
            # Filter by time if specified
            if cutoff_time and created_dt < cutoff_time:
                continue
            
            age_seconds = (now - created_dt).total_seconds()
            age_hours = round(age_seconds / 3600, 1)
            age_minutes = round(age_seconds / 60, 1)
            
            files.append({
                "id": f.get("id"),
                "name": f.get("name"),
                "title": f.get("title"),
                "created": created_dt.isoformat(),
                "age_hours": age_hours,
                "age_minutes": age_minutes if age_minutes < 120 else None,  # Only show minutes for recent files
                "url_download": f.get("url_private_download"),
                "size_kb": round(f.get("size", 0) / 1024, 1)
            })
        
        # Sort by creation time (newest first) - API should do this but ensure it
        files.sort(key=lambda x: x["created"], reverse=True)
        
        # Limit to requested count
        files = files[:count]
        
        result = {
            "count": len(files),
            "files": files
        }
        
        if hours_back:
            result["filter_hours_back"] = hours_back
        
        # Add note if no very recent files
        if files and files[0].get("age_hours", 999) > 24:
            result["note"] = "Most recent file is more than 24 hours old. New exports may take 10-60 seconds to appear."
        
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"❌ Error: {str(e)}"
'''

# Tool 3: Download file
TOOL_3_SOURCE = '''import os
import json
import time

def download_slack_analytics_file(file_url: str, save_path: str = None) -> str:
    """Download a Slack file and return its path.
    
    Args:
        file_url: The url_private_download from list_recent_slack_files()
        save_path: Optional path to save (defaults to /tmp/)
    
    Returns:
        JSON with file path and size
    """
    import urllib.request
    
    TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
    if not TOKEN:
        return "❌ SLACK_MCP_XOXP_TOKEN not set"
    
    if not file_url:
        return "❌ No file URL provided"
    
    try:
        req = urllib.request.Request(file_url, headers={"Authorization": f"Bearer {TOKEN}"})
        
        with urllib.request.urlopen(req, timeout=30) as r:
            content = r.read()
        
        if not save_path:
            filename = file_url.split("/")[-1].split("?")[0] or f"slack_{int(time.time())}.csv"
            save_path = f"/tmp/{filename}"
        
        with open(save_path, "wb") as f:
            f.write(content)
        
        return json.dumps({
            "success": True,
            "file_path": save_path,
            "size_bytes": len(content),
            "size_kb": round(len(content) / 1024, 1)
        }, indent=2)
    except Exception as e:
        return f"❌ Error: {str(e)}"
'''

# Tool 4: Analyze analytics CSV files  
TOOL_4_SOURCE = '''import os
import json
import csv

def analyze_slack_analytics(file_url: str, top_n: int = 10) -> str:
    """Analyze a Slack analytics CSV file and generate summary.
    
    Args:
        file_url: The url_private_download from list_recent_slack_files()
        top_n: Number of top results to return (default 10)
    
    Returns:
        JSON with analysis results including top channels/members by various metrics
        
    Examples:
        # After listing files, analyze a channels file
        analyze_slack_analytics("https://files.slack.com/.../channels-2024-10-14.csv")
        
        # Analyze with custom top N
        analyze_slack_analytics("https://files.slack.com/.../members.csv", top_n=15)
    """
    import urllib.request
    import io
    
    TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
    if not TOKEN:
        return json.dumps({"error": "SLACK_MCP_XOXP_TOKEN not set"}, indent=2)
    
    if not file_url:
        return json.dumps({"error": "No file URL provided"}, indent=2)
    
    results = {
        "file_url": file_url,
        "file_type": None,
        "analysis": None,
        "errors": []
    }
    
    try:
        # Download the file
        req = urllib.request.Request(
            file_url,
            headers={"Authorization": f"Bearer {TOKEN}"}
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode("utf-8")
        
        # Parse CSV
        csv_reader = csv.DictReader(io.StringIO(content))
        rows = list(csv_reader)
        
        if not rows:
            results["errors"].append("Empty file")
            return json.dumps(results, indent=2)
        
        # Detect file type based on columns
        columns = set(rows[0].keys())
        
        # Channels file detection - look for channel-specific metrics
        has_channel_metrics = ("Members who posted" in columns or "Members posted" in columns) and \
                             ("Members who viewed" in columns or "Members viewed" in columns)
        
        # Channels file detection and analysis
        if has_channel_metrics or "Channel" in columns or "Channel name" in columns:
            results["file_type"] = "channels"
            
            # Find channel column (Slack exports use "Name" for channels)
            channel_col = None
            for name in ["Channel", "Channel name", "Name", "channel", "channel_name", "name"]:
                if name in rows[0]:
                    channel_col = name
                    break
            
            if not channel_col:
                results["errors"].append("Could not find channel name column")
                return json.dumps(results, indent=2)
            
            ch_analysis = {
                "total_channels": len(rows),
                "top_by_messages_posted": [],
                "top_by_members_posted": [],
                "top_by_members_viewed": []
            }
            
            # Messages posted
            msg_col = None
            for name in ["Messages posted", "messages_posted", "Messages", "Messages sent"]:
                if name in rows[0]:
                    msg_col = name
                    break
            if msg_col:
                sorted_msgs = sorted(
                    rows,
                    key=lambda r: int(r.get(msg_col, "0").replace(",", "")),
                    reverse=True
                )[:top_n]
                ch_analysis["top_by_messages_posted"] = [
                    {"channel": r[channel_col], "count": int(r[msg_col].replace(",", ""))}
                    for r in sorted_msgs
                ]
            
            # Members posted
            posted_col = None
            for name in ["Members who posted", "Members posted", "members_posted", "Posters"]:
                if name in rows[0]:
                    posted_col = name
                    break
            if posted_col:
                sorted_posted = sorted(
                    rows,
                    key=lambda r: int(r.get(posted_col, "0").replace(",", "")),
                    reverse=True
                )[:top_n]
                ch_analysis["top_by_members_posted"] = [
                    {"channel": r[channel_col], "count": int(r[posted_col].replace(",", ""))}
                    for r in sorted_posted
                ]
            
            # Members viewed
            viewed_col = None
            for name in ["Members who viewed", "Members viewed", "members_viewed", "Viewers"]:
                if name in rows[0]:
                    viewed_col = name
                    break
            if viewed_col:
                sorted_viewed = sorted(
                    rows,
                    key=lambda r: int(r.get(viewed_col, "0").replace(",", "")),
                    reverse=True
                )[:top_n]
                ch_analysis["top_by_members_viewed"] = [
                    {"channel": r[channel_col], "count": int(r[viewed_col].replace(",", ""))}
                    for r in sorted_viewed
                ]
            
            results["analysis"] = ch_analysis
        
        # Members file detection and analysis
        elif "Full name" in columns or "Display name" in columns or "Member" in columns:
            results["file_type"] = "members"
            
            # Find name column
            name_col = None
            for name in ["Full name", "Display name", "Member", "Name", "User"]:
                if name in rows[0]:
                    name_col = name
                    break
            
            if not name_col:
                results["errors"].append("Could not find member name column")
                return json.dumps(results, indent=2)
            
            mem_analysis = {
                "total_members": len(rows),
                "top_by_messages_posted": []
            }
            
            # Messages posted
            msg_col = None
            for col_name in ["Messages posted", "messages_posted", "Messages"]:
                if col_name in rows[0]:
                    msg_col = col_name
                    break
            if msg_col:
                sorted_msgs = sorted(
                    rows,
                    key=lambda r: int(r.get(msg_col, "0").replace(",", "")),
                    reverse=True
                )[:top_n]
                mem_analysis["top_by_messages_posted"] = [
                    {"member": r[name_col], "count": int(r[msg_col].replace(",", ""))}
                    for r in sorted_msgs
                ]
            
            results["analysis"] = mem_analysis
        
        else:
            results["errors"].append(f"Unknown file type (columns: {list(columns)[:5]})")
    
    except Exception as e:
        results["errors"].append(f"Error processing file: {str(e)}")
    
    return json.dumps(results, indent=2)

'''

# Tool 5: Resolve DM channel ID from user ID
TOOL_5_SOURCE = '''import os
import json

def resolve_dm_channel_id(user_id: str) -> str:
    """Resolve a user ID to a DM channel ID using Slack's conversations.open API.
    
    When the MCP server returns channel information like "#U09C3N5LZ" (a user ID),
    this function converts it to the actual DM channel ID like "D09C3JMB9".
    
    Args:
        user_id: The Slack user ID (e.g., "U09C3N5LZ" or "#U09C3N5LZ")
    
    Returns:
        JSON string with DM channel ID or error message
    
    Example:
        resolve_dm_channel_id("U09C3N5LZ")
        # Returns: {"channel_id": "D09C3JMB9", "user_id": "U09C3N5LZ"}
    """
    import urllib.request
    import urllib.parse
    
    TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
    if not TOKEN:
        return json.dumps({
            "error": "SLACK_MCP_XOXP_TOKEN not set in environment",
            "message": "Slack authentication token is required"
        }, indent=2)
    
    # Remove # prefix if present
    clean_user_id = user_id.lstrip("#")
    
    # Validate user ID format (should start with U)
    if not clean_user_id.startswith("U"):
        return json.dumps({
            "error": f"Invalid user ID format: {user_id}",
            "message": "User ID should start with 'U' (e.g., 'U09C3N5LZ')"
        }, indent=2)
    
    try:
        # Call Slack API conversations.open to get/create DM channel
        url = "https://slack.com/api/conversations.open"
        params = {
            "users": clean_user_id
        }
        data = urllib.parse.urlencode(params).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )
        
        with urllib.request.urlopen(req, timeout=10) as r:
            response_data = json.loads(r.read().decode('utf-8'))
        
        if not response_data.get("ok"):
            error = response_data.get("error", "Unknown error")
            return json.dumps({
                "error": f"Slack API error: {error}",
                "user_id": clean_user_id,
                "message": f"Failed to resolve DM channel: {error}"
            }, indent=2)
        
        channel = response_data.get("channel", {})
        channel_id = channel.get("id")
        
        if not channel_id:
            return json.dumps({
                "error": "No channel ID returned from Slack API",
                "user_id": clean_user_id
            }, indent=2)
        
        return json.dumps({
            "success": True,
            "channel_id": channel_id,
            "user_id": clean_user_id,
            "message": "DM channel ID resolved successfully"
        }, indent=2)
        
    except urllib.error.URLError as e:
        return json.dumps({
            "error": f"Network error: {str(e)}",
            "user_id": clean_user_id
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "error": f"Unexpected error: {str(e)}",
            "user_id": clean_user_id
        }, indent=2)

'''

# Tool 6: Get Slack message permalink
TOOL_6_SOURCE = '''import os
import json

def get_slack_message_permalink(channel_id: str, message_ts: str) -> str:
    """Get a permalink URL for a specific Slack message.
    
    Uses Slack's chat.getPermalink API method to generate a permanent link
    to a message in a channel. For DM/MPDM channels where the API doesn't work,
    constructs the permalink manually using the standard format.
    
    Args:
        channel_id: The Slack channel ID (e.g., "C1234567890", "D1234567890", "mpdm-...")
        message_ts: The message timestamp (e.g., "1234567890.123456")
                   Can be in format "1234567890.123456" or "1234567890123456"
    
    Returns:
        JSON string with permalink URL or error message
    
    Example:
        get_slack_message_permalink("C1234567890", "1234567890.123456")
        # Returns: {"permalink": "https://concord-consortium.slack.com/archives/C1234567890/p1234567890123456"}
    """
    import urllib.request
    import urllib.parse
    
    TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
    if not TOKEN:
        return json.dumps({
            "error": "SLACK_MCP_XOXP_TOKEN not set in environment",
            "message": "Slack authentication token is required"
        }, indent=2)
    
    # Store original message_ts for permalink construction
    original_message_ts = message_ts
    
    # Normalize message_ts format (Slack API expects format like "1234567890.123456")
    # If provided as integer or without decimal, add decimal point
    try:
        if '.' not in message_ts:
            # If it's a long integer, insert decimal point 10 digits from the end
            if len(message_ts) > 10:
                message_ts = message_ts[:-6] + '.' + message_ts[-6:]
            else:
                message_ts = message_ts + '.000000'
    except Exception:
        pass  # Keep original format if parsing fails
    
    # Slack workspace URL
    SLACK_WORKSPACE_URL = "https://concord-consortium.slack.com"
    
    # Check if channel_id is actually a user ID (starts with #U or U)
    # This happens when MCP server returns "#U09C3N5LZ" instead of "D09C3JMB9"
    if channel_id.startswith("#U") or (channel_id.startswith("U") and not channel_id.startswith("D")):
        # Resolve user ID to DM channel ID using conversations.open
        user_id = channel_id.lstrip("#")
        try:
            import urllib.request
            import urllib.parse
            
            TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
            if TOKEN:
                url = "https://slack.com/api/conversations.open"
                params = {"users": user_id}
                data = urllib.parse.urlencode(params).encode('utf-8')
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={
                        "Authorization": f"Bearer {TOKEN}",
                        "Content-Type": "application/x-www-form-urlencoded"
                    }
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    resolve_data = json.loads(r.read().decode('utf-8'))
                if resolve_data.get("ok"):
                    channel = resolve_data.get("channel", {})
                    resolved_channel_id = channel.get("id")
                    if resolved_channel_id:
                        channel_id = resolved_channel_id
        except Exception:
            pass  # If resolution fails, continue with original channel_id
    
    # Check if this looks like a DM/MPDM channel (starts with D or mpdm-)
    is_dm_or_mpdm = channel_id.startswith("D") or channel_id.startswith("mpdm-")
    
    try:
        # Try Slack API chat.getPermalink first (works for regular channels)
        url = "https://slack.com/api/chat.getPermalink"
        params = {
            "channel": channel_id,
            "message_ts": message_ts
        }
        data = urllib.parse.urlencode(params).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )
        
        with urllib.request.urlopen(req, timeout=10) as r:
            response_data = json.loads(r.read().decode('utf-8'))
        
        if response_data.get("ok"):
            permalink = response_data.get("permalink", "")
            if permalink:
                return json.dumps({
                    "success": True,
                    "permalink": permalink,
                    "channel_id": channel_id,
                    "message_ts": message_ts,
                    "message": "Permalink generated successfully via API"
                }, indent=2)
        
        # If API failed and this is a DM/MPDM channel, construct permalink manually
        error = response_data.get("error", "Unknown error")
        if (error == "channel_not_found" and is_dm_or_mpdm) or is_dm_or_mpdm:
            # Construct permalink manually for DM/MPDM channels
            # Format: https://workspace.slack.com/archives/CHANNEL_ID/pTIMESTAMP
            # Where TIMESTAMP is message_ts without the decimal point
            permalink_ts = original_message_ts.replace('.', '')
            permalink = f"{SLACK_WORKSPACE_URL}/archives/{channel_id}/p{permalink_ts}"
            
            return json.dumps({
                "success": True,
                "permalink": permalink,
                "channel_id": channel_id,
                "message_ts": message_ts,
                "message": "Permalink constructed manually for DM/MPDM channel",
                "note": "DM/MPDM channels don't support chat.getPermalink API, so permalink was constructed using standard format"
            }, indent=2)
        
        # For other errors, return the error
        return json.dumps({
            "error": f"Slack API error: {error}",
            "channel_id": channel_id,
            "message_ts": message_ts,
            "message": f"Failed to get permalink: {error}"
        }, indent=2)
        
    except urllib.error.URLError as e:
        # If network error and it's a DM/MPDM, try constructing manually anyway
        if is_dm_or_mpdm:
            permalink_ts = original_message_ts.replace('.', '')
            permalink = f"{SLACK_WORKSPACE_URL}/archives/{channel_id}/p{permalink_ts}"
            return json.dumps({
                "success": True,
                "permalink": permalink,
                "channel_id": channel_id,
                "message_ts": message_ts,
                "message": "Permalink constructed manually (API unavailable)",
                "note": "Network error occurred, but permalink was constructed using standard format"
            }, indent=2)
        
        return json.dumps({
            "error": f"Network error: {str(e)}",
            "channel_id": channel_id,
            "message_ts": message_ts
        }, indent=2)
    except Exception as e:
        # If unexpected error and it's a DM/MPDM, try constructing manually anyway
        if is_dm_or_mpdm:
            permalink_ts = original_message_ts.replace('.', '')
            permalink = f"{SLACK_WORKSPACE_URL}/archives/{channel_id}/p{permalink_ts}"
            return json.dumps({
                "success": True,
                "permalink": permalink,
                "channel_id": channel_id,
                "message_ts": message_ts,
                "message": "Permalink constructed manually (fallback)",
                "note": "Unexpected error occurred, but permalink was constructed using standard format"
            }, indent=2)
        
        return json.dumps({
            "error": f"Unexpected error: {str(e)}",
            "channel_id": channel_id,
            "message_ts": message_ts
        }, indent=2)

'''

# Tool 7: List files from a specific channel (including MPDMs)
TOOL_7_SOURCE = '''import os
import json
from datetime import datetime

def list_files_from_channel(channel_id: str, limit: int = 100) -> str:
    """List files posted to a specific Slack channel (including MPDM channels).
    
    Retrieves messages from the channel using conversations.history, then extracts
    files from messages that contain file attachments. This is the recommended
    approach for getting files from specific channels, especially MPDMs.
    
    Args:
        channel_id: The Slack channel ID (e.g., "C1234567890", "mpdm-user1--user2-1", "G1234567890")
        limit: Maximum number of messages to retrieve (default: 100, max: 1000)
    
    Returns:
        JSON string with list of files found in the channel
    
    Example:
        files = list_files_from_channel("mpdm-cmcintyre--lstephens--cdorsey-1", limit=50)
        # Returns JSON with files posted in that MPDM channel
    """
    import urllib.request
    import urllib.parse
    
    TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
    if not TOKEN:
        return json.dumps({
            "error": "SLACK_MCP_XOXP_TOKEN not set in environment",
            "message": "Slack authentication token is required"
        }, indent=2)
    
    try:
        # Step 1: Get messages from the channel
        url = "https://slack.com/api/conversations.history"
        params = {
            "channel": channel_id,
            "limit": str(min(limit, 1000))  # Slack API max is 1000
        }
        query_string = urllib.parse.urlencode(params)
        full_url = f"{url}?{query_string}"
        
        req = urllib.request.Request(
            full_url,
            headers={
                "Authorization": f"Bearer {TOKEN}"
            }
        )
        
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
        
        if not data.get("ok"):
            error = data.get("error", "Unknown error")
            return json.dumps({
                "error": f"Slack API error: {error}",
                "channel_id": channel_id,
                "message": f"Failed to retrieve messages from channel: {error}"
            }, indent=2)
        
        messages = data.get("messages", [])
        
        # Step 2: Extract files from messages
        files_found = []
        for message in messages:
            if "files" in message and message["files"]:
                for file_obj in message["files"]:
                    created_ts = file_obj.get("created")
                    created_iso = None
                    if created_ts:
                        try:
                            created_iso = datetime.fromtimestamp(created_ts).isoformat()
                        except:
                            pass
                    
                    file_data = {
                        "file_id": file_obj.get("id"),
                        "name": file_obj.get("name"),
                        "title": file_obj.get("title"),
                        "mimetype": file_obj.get("mimetype"),
                        "filetype": file_obj.get("filetype"),
                        "pretty_type": file_obj.get("pretty_type"),
                        "size": file_obj.get("size"),
                        "url_private_download": file_obj.get("url_private_download"),
                        "created": created_ts,
                        "created_iso": created_iso,
                        "user": file_obj.get("user"),
                        "message_ts": message.get("ts"),
                        "channel_id": channel_id
                    }
                    files_found.append(file_data)
        
        return json.dumps({
            "success": True,
            "channel_id": channel_id,
            "files_count": len(files_found),
            "messages_scanned": len(messages),
            "files": files_found,
            "message": f"Found {len(files_found)} file(s) in {len(messages)} message(s)"
        }, indent=2)
        
    except urllib.error.URLError as e:
        return json.dumps({
            "error": f"Network error: {str(e)}",
            "channel_id": channel_id
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "error": f"Unexpected error: {str(e)}",
            "channel_id": channel_id
        }, indent=2)

'''


def main():
    print("="*60)
    print("Slack Analytics Tools Registration")
    print("="*60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Agent ID: {AGENT_ID}")
    print()
    
    tools_to_create = [
        ("trigger_slack_analytics_export", TOOL_1_SOURCE, "Trigger Slack analytics CSV export with custom date range"),
        ("list_recent_slack_files", TOOL_2_SOURCE, "List recent files from Slack workspace"),
        ("download_slack_analytics_file", TOOL_3_SOURCE, "Download a Slack file by URL"),
        ("analyze_slack_analytics", TOOL_4_SOURCE, "Analyze Slack analytics CSV files and generate summaries"),
        ("resolve_dm_channel_id", TOOL_5_SOURCE, "Resolve a user ID to a DM channel ID (useful when MCP server returns #U... format)"),
        ("get_slack_message_permalink", TOOL_6_SOURCE, "Get a permalink URL for a specific Slack message (automatically handles user IDs from MCP server)"),
        ("list_files_from_channel", TOOL_7_SOURCE, "List files posted to a specific Slack channel (including MPDM channels)"),
    ]
    
    created_tool_ids = []
    
    for tool_name, source_code, description in tools_to_create:
        print(f"→ Registering {tool_name}...")
        
        existing = find_tool_by_name(tool_name)
        if existing:
            print(f"  → Tool already exists (ID: {existing['id']}), deleting to update...")
            # Delete old tool to recreate with updated code
            delete_url = f"{LETTA_BASE}/v1/tools/{existing['id']}"
            try:
                req = urllib.request.Request(delete_url, method='DELETE')
                with urllib.request.urlopen(req, timeout=30) as r:
                    print(f"  ✓ Deleted old tool")
            except Exception as e:
                print(f"  ⚠ Could not delete old tool: {e}")
        
        # Always create/update the tool
        result = create_tool(source_code, tags=["slack", "analytics", "custom"])
        if result and result.get('id'):
            tool_id = result['id']
            print(f"  ✓ Created/updated tool (ID: {tool_id})")
            print(f"    {description}")
            created_tool_ids.append(tool_id)
        else:
            print(f"  ✗ Failed to create tool")
    
    if not created_tool_ids:
        print("\n❌ No tools to attach")
        return 1
    
    print()
    print(f"→ Attaching {len(created_tool_ids)} tools to agent {AGENT_ID}...")
    
    if attach_tools_to_agent(AGENT_ID, created_tool_ids):
        print(f"  ✓ Successfully attached tools to agent")
    else:
        print("  ✗ Failed to attach tools")
        return 1
    
    print()
    print("="*60)
    print("✓ Registration Complete")
    print("="*60)
    print()
    print("Your Letta agent now has these Slack analytics tools:")
    print()
    print("  • trigger_slack_analytics_export")
    print("    - Trigger CSV exports with custom date ranges")
    print("    - Default: 3 days ago (analytics delay)")
    print("    - Supports channels and members")
    print()
    print("  • list_recent_slack_files")
    print("    - List recent files from Slack")
    print("    - Filter by type (csv, pdf, all)")
    print()
    print("  • download_slack_analytics_file")
    print("    - Download files from Slack by URL")
    print("    - Returns file path and size")
    print()
    print("Example conversation with your agent:")
    print('  "Export channels analytics from 7 days ago"')
    print('  "List my recent CSV files from Slack"')
    print('  "Download that analytics file"')
    print()
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

