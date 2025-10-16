#!/usr/bin/env python3
"""Test script for scheduler MCP v2 tools."""

import asyncio
import json

import httpx


async def test_mcp_tools():
    """Test the new v2 MCP tools."""
    base_url = "http://localhost:8088"

    # Headers required by FastMCP
    headers = {
        "X-Agent-ID": "test-agent-1",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Initialize MCP session
        print("\n=== Initialize MCP Session ===")
        init_request = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0",
                },
            },
        }
        response = await client.post(f"{base_url}/mcp", json=init_request, headers=headers)
        print(f"Init Status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type')}")
        print(f"Response text (first 500 chars): {response.text[:500]}")
        
        if "application/json" in response.headers.get("content-type", ""):
            init_result = response.json()
            print(json.dumps(init_result, indent=2))
        else:
            print("Response is not JSON, likely SSE")
        
        # Test 1: List tools (MCP protocol)
        print("\n=== Test 1: List Tools ===")
        tools_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        }
        response = await client.post(f"{base_url}/mcp", json=tools_request, headers=headers)
        print(f"Status: {response.status_code}")
        tools_data = response.json()
        print(f"Tools available: {len(tools_data.get('result', {}).get('tools', []))}")
        for tool in tools_data.get("result", {}).get("tools", []):
            print(f"  - {tool['name']}: {tool.get('description', '')[:80]}")

        # Test 2: Schedule a reminder (natural language)
        print("\n=== Test 2: Schedule Reminder ===")
        schedule_reminder_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "schedule_reminder",
                "arguments": {
                    "message": "Check on deployment status",
                    "when": "in 5 minutes",
                    "title": "Deployment Check",
                    "category": "ops",
                },
            },
        }
        response = await client.post(f"{base_url}/mcp", json=schedule_reminder_request, headers=headers)
        print(f"Status: {response.status_code}")
        reminder_result = response.json()
        print(json.dumps(reminder_result, indent=2))

        # Test 3: Schedule an action (script with error - wrong param combination)
        print("\n=== Test 3: Schedule Action (Error Case - body with script) ===")
        schedule_action_error_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "schedule_action",
                "arguments": {
                    "action_type": "script",
                    "target": "backup.sh",
                    "when": "tomorrow at 2am",
                    "title": "Daily backup",
                    "body": {"compress": True},  # ERROR: body not valid for scripts
                },
            },
        }
        response = await client.post(f"{base_url}/mcp", json=schedule_action_error_request, headers=headers)
        print(f"Status: {response.status_code}")
        action_error_result = response.json()
        print(json.dumps(action_error_result, indent=2))

        # Test 4: Schedule an action (HTTP - correct)
        print("\n=== Test 4: Schedule Action (HTTP) ===")
        schedule_http_request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "schedule_action",
                "arguments": {
                    "action_type": "http",
                    "target": "https://httpbin.org/post",
                    "when": "every day at 3am",
                    "title": "Daily sync",
                    "method": "POST",
                    "body": {"sync_type": "full", "timestamp": "auto"},
                },
            },
        }
        response = await client.post(f"{base_url}/mcp", json=schedule_http_request, headers=headers)
        print(f"Status: {response.status_code}")
        http_result = response.json()
        print(json.dumps(http_result, indent=2))

        # Test 5: List scheduled jobs (with filters)
        print("\n=== Test 5: List Scheduled Jobs (filter by 'me') ===")
        list_jobs_request = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "list_scheduled_jobs",
                "arguments": {
                    "filters": {"created_by": "me", "status": "scheduled"},
                    "limit": 10,
                },
            },
        }
        response = await client.post(f"{base_url}/mcp", json=list_jobs_request, headers=headers)
        print(f"Status: {response.status_code}")
        list_result = response.json()
        print(json.dumps(list_result, indent=2))

        # Get a job ID from the list for next test
        job_id = None
        if "result" in list_result and isinstance(list_result["result"], list):
            for item in list_result["result"]:
                if "content" in item and isinstance(item["content"], list):
                    for content_item in item["content"]:
                        if content_item.get("type") == "text":
                            try:
                                data = json.loads(content_item.get("text", "{}"))
                                if data.get("jobs") and len(data["jobs"]) > 0:
                                    job_id = data["jobs"][0].get("job_id")
                                    print(f"\nFound job ID for testing: {job_id}")
                                    break
                            except json.JSONDecodeError:
                                pass

        # Test 6: Manage scheduled job (pause)
        if job_id:
            print(f"\n=== Test 6: Manage Job (Pause) ===")
            manage_job_request = {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "manage_scheduled_job",
                    "arguments": {"job_id": job_id, "operation": "pause"},
                },
            }
            response = await client.post(f"{base_url}/mcp", json=manage_job_request, headers=headers)
            print(f"Status: {response.status_code}")
            manage_result = response.json()
            print(json.dumps(manage_result, indent=2))
        else:
            print("\n=== Test 6: Skipped (no job ID) ===")


if __name__ == "__main__":
    asyncio.run(test_mcp_tools())

