#!/bin/bash
#
# Check if Atlassian Rovo MCP token is valid
# Returns 0 if valid, 1 if expired/invalid
#

TOKEN_FILE="$HOME/.atlassian-rovo-token.txt"
MCP_URL="https://mcp.atlassian.com/v1/mcp"

if [ ! -f "$TOKEN_FILE" ]; then
    echo "No token file found"
    exit 1
fi

TOKEN=$(cat "$TOKEN_FILE")

if [ -z "$TOKEN" ]; then
    echo "Token file is empty"
    exit 1
fi

# Test token by making a simple MCP request
RESPONSE=$(curl -s --max-time 10 -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"token-check","version":"1.0"}}}' 2>&1)

if echo "$RESPONSE" | grep -q "atlassian-mcp-server"; then
    echo "Token is valid"
    exit 0
else
    echo "Token is expired or invalid"
    echo "Response: $RESPONSE" | head -3
    exit 1
fi

