#!/usr/bin/env python3
"""
Test script for Core_Event_Data MCP tool.
Tests the n8n MCP server to understand what data it provides.
"""

import asyncio
import json
import httpx
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

MCP_SERVER_URL = "http://localhost:5678/mcp/ede03719-3045-4eba-9f78-959cb02c04bb"


async def test_mcp_server():
    """Test the MCP server and Core_Event_Data tool."""
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    
    # Use a session to maintain cookies/state
    # Create a cookie jar to maintain session state
    cookies = {}
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, cookies=cookies) as client:
        print("=" * 60)
        print("Testing MCP Server: Core_Event_Data")
        print("=" * 60)
        print()
        
        # Step 1: Initialize MCP session
        print("Step 1: Initializing MCP session...")
        init_request = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }
        
        try:
            init_response = await client.post(
                f"{MCP_SERVER_URL}",
                json=init_request,
                headers=headers
            )
            print(f"Status: {init_response.status_code}")
            
            # Check for session ID in headers
            session_id = init_response.headers.get("mcp-session-id")
            if session_id:
                print(f"Session ID: {session_id}")
                headers["mcp-session-id"] = session_id
            
            # Handle SSE response
            if "text/event-stream" in init_response.headers.get("content-type", ""):
                print("Response is SSE format")
                # Parse SSE
                lines = init_response.text.split('\n')
                for line in lines:
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        print(f"Init result: {json.dumps(data, indent=2)}")
                        break
            else:
                init_result = init_response.json()
                print(f"Init result: {json.dumps(init_result, indent=2)}")
        except Exception as e:
            print(f"Error initializing: {e}")
            return
        
        print()
        
        # Step 2: List available tools
        print("Step 2: Listing available tools...")
        
        # Try with session ID from init
        tools_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }
        
        try:
            # Try multiple approaches
            # Approach 1: With session ID in header
            tools_response = await client.post(
                f"{MCP_SERVER_URL}",
                json=tools_request,
                headers=headers
            )
            
            # Update session ID if returned
            new_session_id = tools_response.headers.get("mcp-session-id")
            if new_session_id:
                headers["mcp-session-id"] = new_session_id
            
            print(f"Status: {tools_response.status_code}")
            
            # If that didn't work, try without session requirement
            if tools_response.status_code != 200:
                print("  Trying alternative approach...")
                # Maybe n8n doesn't require session persistence
                # Try calling tools/list again fresh
                tools_response2 = await client.post(
                    f"{MCP_SERVER_URL}",
                    json=tools_request,
                    headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
                )
                print(f"  Alternative Status: {tools_response2.status_code}")
                if tools_response2.status_code == 200:
                    tools_response = tools_response2
            
            # Handle SSE response
            if "text/event-stream" in tools_response.headers.get("content-type", ""):
                lines = tools_response.text.split('\n')
                for line in lines:
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if "result" in data and "tools" in data["result"]:
                            tools = data["result"]["tools"]
                            print(f"Found {len(tools)} tool(s):")
                            for tool in tools:
                                print(f"  - {tool.get('name', 'unknown')}")
                                if "description" in tool:
                                    print(f"    Description: {tool['description']}")
                                if "inputSchema" in tool:
                                    print(f"    Parameters:")
                                    props = tool["inputSchema"].get("properties", {})
                                    for param, details in props.items():
                                        param_type = details.get("type", "unknown")
                                        required = param in tool["inputSchema"].get("required", [])
                                        print(f"      - {param} ({param_type}){' [required]' if required else ''}")
                                        if "description" in details:
                                            print(f"        {details['description']}")
                        break
            else:
                tools_result = tools_response.json()
                print(f"Tools result: {json.dumps(tools_result, indent=2)}")
        except Exception as e:
            print(f"Error listing tools: {e}")
            import traceback
            traceback.print_exc()
            return
        
        print()
        
        # Step 3: Call Core_Event_Data tool
        print("Step 3: Calling Core_Event_Data tool...")
        print("  Tool schema:")
        print("    - Before: string (required) - END date/time (counterintuitive naming!)")
        print("    - Calendar: string (required) - calendar identifier")
        print("    - After: string (required) - START date/time (counterintuitive naming!)")
        print("  Note: request_heartbeat is from Letta, not needed for direct MCP calls")
        print("  Note: Parameter names are reversed - Before=end, After=start")
        print()
        
        # Prepare test parameters with real calendar ID
        # IMPORTANT: "Before" is the END date, "After" is the START date
        start_date = (datetime.now() + timedelta(days=1))
        end_date = (datetime.now() + timedelta(days=7))
        calendar_id = "cdorsey@concord.org"
        
        # Test with real calendar - matching the format from Letta example
        test_cases = [
            {
                "name": f"Real calendar ({calendar_id}) - ISO datetime format (matching Letta)",
                "arguments": {
                    "Before": end_date.strftime("%Y-%m-%dT00:00:00Z"),  # END date
                    "Calendar": calendar_id,
                    "After": start_date.strftime("%Y-%m-%dT00:00:00Z")   # START date
                }
            },
            {
                "name": f"Real calendar ({calendar_id}) - Date strings",
                "arguments": {
                    "Before": end_date.strftime("%Y-%m-%d"),  # END date
                    "Calendar": calendar_id,
                    "After": start_date.strftime("%Y-%m-%d")   # START date
                }
            }
        ]
        
        test_params = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "Core_Event_Data",
                "arguments": {}
            }
        }
        
        for test_case in test_cases:
            print(f"\n  Testing: {test_case['name']}")
            print(f"    Arguments: {json.dumps(test_case['arguments'], indent=6)}")
            test_params["params"]["arguments"] = test_case["arguments"]
            
            try:
                call_response = await client.post(
                    f"{MCP_SERVER_URL}",
                    json=test_params,
                    headers=headers
                )
                
                # Update session ID if present
                new_session_id = call_response.headers.get("mcp-session-id")
                if new_session_id:
                    headers["mcp-session-id"] = new_session_id
                
                print(f"    Status: {call_response.status_code}")
                
                # Handle SSE response
                if "text/event-stream" in call_response.headers.get("content-type", ""):
                    lines = call_response.text.split('\n')
                    for line in lines:
                        if line.startswith('data: '):
                            data = json.loads(line[6:])
                            if "error" in data:
                                print(f"    Error: {data['error']}")
                            elif "result" in data:
                                result = data["result"]
                                print(f"    Success! Result structure:")
                                print(f"    {json.dumps(result, indent=4)}")
                                
                                # Try to understand the data format
                                if "content" in result:
                                    content = result["content"]
                                    if content and len(content) > 0:
                                        text_content = content[0].get("text", "")
                                        try:
                                            parsed = json.loads(text_content)
                                            print(f"    Parsed content (first 500 chars):")
                                            print(f"    {json.dumps(parsed, indent=2)[:500]}...")
                                        except:
                                            print(f"    Text content (first 500 chars): {text_content[:500]}")
                            break
                else:
                    call_result = call_response.json()
                    if "error" in call_result:
                        print(f"    Error: {call_result['error']}")
                    else:
                        print(f"    Result: {json.dumps(call_result, indent=2)}")
                
                # If we got a successful response, break
                if call_response.status_code == 200:
                    # Check if it's actually successful (not an error)
                    if "text/event-stream" in call_response.headers.get("content-type", ""):
                        lines = call_response.text.split('\n')
                        for line in lines:
                            if line.startswith('data: '):
                                data = json.loads(line[6:])
                                if "result" in data and "error" not in data:
                                    print(f"\n    ✓ Successfully called Core_Event_Data!")
                                    break
                
            except Exception as e:
                print(f"    Error: {e}")
                import traceback
                traceback.print_exc()
        
        print()
        print("=" * 60)
        print("Test complete")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_mcp_server())

