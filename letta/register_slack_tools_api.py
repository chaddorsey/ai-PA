#!/usr/bin/env python3
"""
Register Slack Analytics Tools with Letta via HTTP API
"""

import os
import json
import urllib.request
import urllib.parse

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID", "agent-6eb765bf-7268-4f6d-a380-c527c9c53000")


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
    # Get current agent
    agent = http_get(f"{LETTA_BASE}/v1/agents/{agent_id}")
    if not agent:
        return False
    
    current_tool_ids = agent.get("tools", [])
    
    # Merge tool lists
    all_tool_ids = list(set(current_tool_ids + tool_ids))
    
    # Update agent
    result = http_patch(f"{LETTA_BASE}/v1/agents/{agent_id}", {"tools": all_tool_ids})
    return result is not None


# Tool source codes
TOOL_1_SOURCE = '''import os
import subprocess

def trigger_slack_analytics_export(analytics_type: str = "channels") -> str:
    """Trigger a Slack analytics CSV export using browser automation.
    
    Args:
        analytics_type: Type of analytics to export (channels, members, overview, all)
    
    Returns:
        Success message with instructions on retrieving the file
    """
    SCRIPT = "/Users/dorseyhomeserver/ai-PA/scripts/slack_analytics_trigger_export.py"
    AUTH = "/Users/dorseyhomeserver/ai-PA/slack_auth_state.json"
    
    if analytics_type not in ["channels", "members", "overview", "all"]:
        return f"❌ Invalid analytics_type: {analytics_type}. Must be: channels, members, overview, or all"
    
    try:
        result = subprocess.run(
            ["python3", SCRIPT, "--type", analytics_type, "--headless", "--auth-file", AUTH],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            if analytics_type == "all":
                return "✓ Triggered exports for all analytics types. CSV files will be in Slack Files in 1-2 minutes. Use list_recent_slack_files() to find them."
            else:
                return f"✓ Triggered {analytics_type} analytics export. CSV will be in Slack Files in 1-2 minutes. Use list_recent_slack_files() to find it."
        else:
            return f"❌ Failed to trigger export: {result.stderr}"
    except Exception as e:
        return f"❌ Error: {str(e)}"
'''

TOOL_2_SOURCE = '''import os
import json
from datetime import datetime

def list_recent_slack_files(types: str = "csv", count: int = 10) -> str:
    """List recent files uploaded to Slack workspace.
    
    Args:
        types: File types to filter (csv, pdf, all)
        count: Number of files to return (max 100)
    
    Returns:
        JSON string with list of recent files
    """
    import urllib.request
    
    TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
    if not TOKEN:
        return "❌ SLACK_MCP_XOXP_TOKEN not set in environment"
    
    try:
        params = {"count": str(min(count, 100))}
        if types != "all":
            params["types"] = types
        
        url = "https://slack.com/api/files.list?" + "&".join(f"{k}={v}" for k, v in params.items())
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
        
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
        
        if not data.get("ok"):
            return f"❌ Slack API error: {data.get('error', 'Unknown error')}"
        
        files = []
        for f in data.get("files", []):
            files.append({
                "id": f.get("id"),
                "name": f.get("name"),
                "title": f.get("title"),
                "created": datetime.fromtimestamp(f.get("created", 0)).isoformat(),
                "url_download": f.get("url_private_download"),
                "size_bytes": f.get("size")
            })
        
        return json.dumps({"count": len(files), "files": files}, indent=2)
    except Exception as e:
        return f"❌ Error listing files: {str(e)}"
'''

def main():
    print("="*60)
    print("Slack Analytics Tools Registration")
    print("="*60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Agent ID: {AGENT_ID}")
    print()
    
    # Tool 1
    print("→ Registering trigger_slack_analytics_export...")
    tool1 = find_tool_by_name("trigger_slack_analytics_export")
    if tool1:
        print(f"  → Tool already exists (ID: {tool1['id']})")
        tool1_id = tool1['id']
    else:
        result = create_tool(TOOL_1_SOURCE, tags=["slack", "analytics"])
        if result:
            tool1_id = result.get('id')
            print(f"  ✓ Created tool (ID: {tool1_id})")
        else:
            print("  ✗ Failed to create tool")
            tool1_id = None
    
    # Tool 2
    print("→ Registering list_recent_slack_files...")
    tool2 = find_tool_by_name("list_recent_slack_files")
    if tool2:
        print(f"  → Tool already exists (ID: {tool2['id']})")
        tool2_id = tool2['id']
    else:
        result = create_tool(TOOL_2_SOURCE, tags=["slack", "analytics"])
        if result:
            tool2_id = result.get('id')
            print(f"  ✓ Created tool (ID: {tool2_id})")
        else:
            print("  ✗ Failed to create tool")
            tool2_id = None
    
    # Attach to agent
    print()
    print(f"→ Attaching tools to agent {AGENT_ID}...")
    
    tool_ids = [tid for tid in [tool1_id, tool2_id] if tid]
    
    if not tool_ids:
        print("  ✗ No tools to attach")
        return 1
    
    if attach_tools_to_agent(AGENT_ID, tool_ids):
        print(f"  ✓ Attached {len(tool_ids)} tools to agent")
    else:
        print("  ✗ Failed to attach tools")
        return 1
    
    print()
    print("="*60)
    print("✓ Registration Complete")
    print("="*60)
    print()
    print("Your agent now has these Slack analytics tools:")
    print("  • trigger_slack_analytics_export - Trigger CSV export")
    print("  • list_recent_slack_files - List recent files")
    print()
    print("Try asking your agent:")
    print('  "Trigger a channels analytics export from Slack"')
    print('  "List recent CSV files from Slack"')
    print()
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


