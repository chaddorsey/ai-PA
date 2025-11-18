#!/usr/bin/env python3
"""
Register Slack Analytics Tools with Letta Agent
"""

import os
import json
import urllib.request
import urllib.parse

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = "agent-6eb765bf-7268-4f6d-a380-c527c9c53000"


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
    
    current_tools = agent.get("tools", [])
    
    # Extract IDs from current tools (they might be dicts)
    current_tool_ids = []
    for tool in current_tools:
        if isinstance(tool, dict):
            current_tool_ids.append(tool.get("id"))
        else:
            current_tool_ids.append(tool)
    
    # Merge and deduplicate
    all_tool_ids = list(set(current_tool_ids + tool_ids))
    
    result = http_patch(f"{LETTA_BASE}/v1/agents/{agent_id}", {"tools": all_tool_ids})
    return result is not None


# Tool 1: Trigger export with date range support
TOOL_1_SOURCE = '''import json

def trigger_slack_analytics_export(analytics_type: str = "channels", days_ago: int = 3, date_range_days: int = 1) -> str:
    """Trigger Slack analytics CSV export with custom date range.
    
    Args:
        analytics_type: Type of analytics (channels or members)
        days_ago: How many days ago to start (default 3, since recent data may not be available)
        date_range_days: Number of days to include (default 1 for single day)
    
    Returns:
        Success message with date range used
    
    Example:
        # Get channels data from 7 days ago
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
            return f"✓ Triggered {analytics_type} export for {start} to {end}. CSV will be in Slack Files in 1-2 min. Use list_recent_slack_files() to find it."
        else:
            error_msg = result.get("error", "")
            stdout_msg = result.get("stdout", "")
            
            # Build detailed error message
            msg_parts = []
            if error_msg:
                # Truncate very long errors
                if len(error_msg) > 500:
                    msg_parts.append(error_msg[:500] + "...")
                else:
                    msg_parts.append(error_msg)
            if stdout_msg and "FAILED" in stdout_msg:
                msg_parts.append(f"Output: {stdout_msg[-200:]}")
            if not msg_parts:
                msg_parts.append(f"Unknown error. Response: {json.dumps(result)[:200]}")
            
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
from datetime import datetime

def list_recent_slack_files(types: str = "csv", count: int = 10) -> str:
    """List recent files in Slack workspace.
    
    Args:
        types: File types to filter (csv, pdf, all)  
        count: Number of files (max 100)
    
    Returns:
        JSON with recent files including name, URL, timestamp
    """
    import urllib.request
    
    TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
    if not TOKEN:
        return "❌ SLACK_MCP_XOXP_TOKEN not set"
    
    try:
        params = {"count": str(min(count, 100))}
        if types != "all":
            params["types"] = types
        
        url = "https://slack.com/api/files.list?" + "&".join(f"{k}={v}" for k, v in params.items())
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
        
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        
        if not data.get("ok"):
            return f"❌ API error: {data.get('error')}"
        
        files = []
        for f in data.get("files", []):
            created_dt = datetime.fromtimestamp(f.get("created", 0))
            files.append({
                "id": f.get("id"),
                "name": f.get("name"),
                "title": f.get("title"),
                "created": created_dt.isoformat(),
                "age_hours": round((datetime.now() - created_dt).total_seconds() / 3600, 1),
                "url_download": f.get("url_private_download"),
                "size_kb": round(f.get("size", 0) / 1024, 1)
            })
        
        return json.dumps({"count": len(files), "files": files}, indent=2)
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
    ]
    
    created_tool_ids = []
    
    for tool_name, source_code, description in tools_to_create:
        print(f"→ Registering {tool_name}...")
        
        existing = find_tool_by_name(tool_name)
        if existing:
            print(f"  → Tool already exists (ID: {existing['id']})")
            created_tool_ids.append(existing['id'])
        else:
            result = create_tool(source_code, tags=["slack", "analytics", "custom"])
            if result and result.get('id'):
                tool_id = result['id']
                print(f"  ✓ Created tool (ID: {tool_id})")
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

