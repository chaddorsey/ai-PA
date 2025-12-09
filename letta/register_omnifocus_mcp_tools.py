#!/usr/bin/env python3
"""
Register OmniFocus MCP Tools with Letta via HTTP API
"""

import os
import json
import urllib.request
import urllib.parse

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID", "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a")


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


def http_put(url, data):
    """Make HTTP PUT request."""
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method='PUT')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"PUT Error {e.code}: {error_body}")
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


def register_mcp_server(server_config):
    """Register an MCP server with Letta."""
    url = f"{LETTA_BASE}/v1/tools/mcp/servers"
    return http_put(url, server_config)


def list_mcp_servers():
    """List all registered MCP servers."""
    url = f"{LETTA_BASE}/v1/tools/mcp/servers"
    return http_get(url)


def get_mcp_tools(server_name):
    """Get tools from an MCP server."""
    url = f"{LETTA_BASE}/v1/tools/mcp/servers/{server_name}/tools"
    tools = http_get(url)
    # If tools endpoint doesn't work, try direct MCP call
    if not tools:
        # The simplified server requires Accept header and session initialization
        # Let Letta handle this through its MCP client
        return None
    return tools


def attach_tools_to_agent(agent_id, tool_ids):
    """Attach tools to agent."""
    # Get current agent
    agent = http_get(f"{LETTA_BASE}/v1/agents/{agent_id}")
    if not agent:
        print(f"  ✗ Failed to get agent {agent_id}")
        return False
    
    current_tools = agent.get("tools", [])
    
    # Extract tool IDs if they're objects, otherwise use as-is
    current_tool_ids = []
    for tool in current_tools:
        if isinstance(tool, dict):
            # Tool might be an object with an 'id' field
            tool_id = tool.get("id") or tool.get("name") or str(tool)
            current_tool_ids.append(tool_id)
        else:
            current_tool_ids.append(tool)
    
    # Merge tool lists (remove duplicates)
    all_tool_ids = list(set(current_tool_ids + tool_ids))
    
    # Update agent
    result = http_patch(f"{LETTA_BASE}/v1/agents/{agent_id}", {"tools": all_tool_ids})
    return result is not None


def main():
    print("="*60)
    print("OmniFocus MCP Tools Registration")
    print("="*60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Agent ID: {AGENT_ID}")
    print()
    
    # Step 1: Register MCP server
    print("→ Step 1: Registering OmniFocus MCP server...")
    server_config = {
        "server_name": "omnifocus-tools",
        "type": "streamable_http",
        "server_url": "http://host.docker.internal:8888/mcp",
        "auth_header": None,
        "auth_token": None,
        "custom_headers": {
            "Content-Type": "application/json"
        }
    }
    
    # Check if server already exists
    existing_servers = list_mcp_servers()
    if existing_servers and "omnifocus-tools" in existing_servers:
        print(f"  → MCP server 'omnifocus-tools' already registered")
    else:
        result = register_mcp_server(server_config)
        if result:
            print(f"  ✓ Registered MCP server: omnifocus-tools")
        else:
            print("  ✗ Failed to register MCP server")
            return 1
    
    # Step 2: Get tools from MCP server
    print()
    print("→ Step 2: Discovering tools from OmniFocus MCP server...")
    tools = get_mcp_tools("omnifocus-tools")
    
    if not tools:
        print("  ✗ Failed to get tools from MCP server")
        print("  → Trying to refresh server connection...")
        # Sometimes we need to wait a moment for the server to be ready
        import time
        time.sleep(2)
        tools = get_mcp_tools("omnifocus-tools")
    
    if not tools:
        print("  ✗ Still failed to get tools. Check that the MCP server is running.")
        return 1
    
    tool_list = tools if isinstance(tools, list) else tools.get("tools", [])
    print(f"  ✓ Found {len(tool_list)} tools:")
    for tool in tool_list:
        tool_name = tool.get("name", "unknown")
        tool_desc = tool.get("description", "No description")
        print(f"    • {tool_name}: {tool_desc[:60]}...")
    
    # Step 3: Get actual tool IDs from Letta (Letta creates tool objects when MCP server is registered)
    print()
    print("→ Step 3: Getting tool IDs from Letta...")
    all_tools = http_get(f"{LETTA_BASE}/v1/tools/")
    if not all_tools:
        print("  ✗ Failed to get tools from Letta")
        return 1
    
    # Filter tools by MCP server name
    omnifocus_tool_ids = []
    for tool in all_tools:
        mcp_meta = tool.get("metadata_", {}).get("mcp", {})
        if mcp_meta.get("server_name") == "omnifocus-tools":
            tool_id = tool.get("id")
            if tool_id:
                omnifocus_tool_ids.append(tool_id)
    
    print(f"  ✓ Found {len(omnifocus_tool_ids)} OmniFocus tool objects in Letta")
    if len(omnifocus_tool_ids) < len(tool_list):
        print(f"  ⚠ Note: {len(tool_list)} tools available from MCP server, but only {len(omnifocus_tool_ids)} tool objects found in Letta")
        print(f"     (This is normal - Letta may create tool objects on-demand or in batches)")
    
    tool_ids = omnifocus_tool_ids
    
    # Step 4: Attach tools to agent
    print()
    print(f"→ Step 4: Attaching tools to agent {AGENT_ID}...")
    
    if not tool_ids:
        print("  ✗ No tools to attach")
        return 1
    
    if attach_tools_to_agent(AGENT_ID, tool_ids):
        print(f"  ✓ Attached {len(tool_ids)} OmniFocus tools to agent")
    else:
        print("  ✗ Failed to attach tools")
        return 1
    
    print()
    print("="*60)
    print("✓ Registration Complete")
    print("="*60)
    print()
    print("Your agent now has access to OmniFocus tools:")
    for tool in tool_list[:10]:  # Show first 10
        print(f"  • {tool.get('name')}")
    if len(tool_list) > 10:
        print(f"  ... and {len(tool_list) - 10} more")
    print()
    print("Try asking your agent:")
    print('  "List my remaining OmniFocus tasks"')
    print('  "Show me all my OmniFocus projects"')
    print()
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

