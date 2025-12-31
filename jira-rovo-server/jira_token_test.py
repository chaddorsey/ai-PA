#!/usr/bin/env python3
"""Test Atlassian Rovo Token"""

import requests
import sys

token = "70121-cecc6a6e-e07f-440f-bcef-0e1b8d0fe274:qCYFdQe8sPrAM1Gn:Z1UoX5oauP1K7D2IxNV-LxUdPF2uxhSW"

print("Testing token with Rovo MCP server...")
print()

# Test SSE endpoint
print("1. Testing SSE endpoint...")
try:
    response = requests.get(
        "https://mcp.atlassian.com/v1/sse",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "text/event-stream"
        },
        timeout=10
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print("   ✓ Token works!")
        print(f"   Response: {response.text[:200]}")
    else:
        print(f"   Response: {response.text[:200]}")
except Exception as e:
    print(f"   Error: {e}")

print()

# Test MCP endpoint
print("2. Testing MCP endpoint...")
try:
    mcp_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0.0"}
        }
    }
    
    response = requests.post(
        "https://mcp.atlassian.com/v1/mcp",
        json=mcp_request,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        timeout=10
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print("   ✓ Token works!")
        print(f"   Response: {response.json()}")
    else:
        print(f"   Response: {response.text[:200]}")
except Exception as e:
    print(f"   Error: {e}")

print()
print("If both tests pass, save the token:")
print(f"  echo '{token}' > ~/.atlassian-rovo-token.txt")
