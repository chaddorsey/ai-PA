#!/bin/bash
# Test script to show what Postman will see

echo "============================================================"
echo "What Postman Will See"
echo "============================================================"
echo ""
echo "Request:"
echo "  Method: POST"
echo "  URL: https://mcp.atlassian.com/v1/mcp"
echo "  Headers:"
echo "    Content-Type: application/json"
echo "    Accept: application/json"
echo ""
echo "Body:"
cat << 'EOF'
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "postman-client",
      "version": "1.0.0"
    }
  }
}
EOF
echo ""
echo "Expected Response:"
echo "  Status: 401 Unauthorized"
echo "  Headers:"
echo "    WWW-Authenticate: Bearer realm=\"OAuth\""
echo ""
echo "  Body:"
echo "    {\"error\":\"invalid_token\",\"error_description\":\"Missing or invalid access token\"}"
echo ""
echo "============================================================"
echo "The Problem:"
echo "============================================================"
echo "The server returns 401 but doesn't provide an OAuth URL."
echo "This means Postman alone won't trigger OAuth automatically."
echo ""
echo "However, we can try:"
echo "1. Check if there's a different MCP method to request OAuth"
echo "2. Manually construct the OAuth URL (if we can get the context/JWT)"
echo "3. Use Letta's interface if it has OAuth support built-in"
echo ""

