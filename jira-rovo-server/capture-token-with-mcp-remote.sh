#!/bin/bash
# Run mcp-remote and capture token from browser requests

echo "============================================================"
echo "Capture Token from mcp-remote"
echo "============================================================"
echo ""
echo "This will:"
echo "  1. Start mcp-remote (it should use existing OAuth session)"
echo "  2. Make a request that triggers an API call"
echo "  3. You'll need to check Safari DevTools for the token"
echo ""
echo "Instructions:"
echo "  1. Open Safari DevTools (Cmd+Option+I)"
echo "  2. Go to Network tab"
echo "  3. Filter: mcp.atlassian.com"
echo "  4. Watch for requests with Authorization header"
echo ""
echo "Press Enter to start mcp-remote..."
read

# Start mcp-remote in background
echo "Starting mcp-remote..."
mcp-remote https://mcp.atlassian.com/v1/mcp > /tmp/mcp-remote-token.log 2>&1 &
MCP_PID=$!

echo "mcp-remote started (PID: $MCP_PID)"
echo ""
echo "Now:"
echo "  1. Check Safari DevTools Network tab"
echo "  2. Look for requests to mcp.atlassian.com"
echo "  3. Find Authorization: Bearer <token> header"
echo ""
echo "Press Enter when you've found the token (or Ctrl+C to stop)..."
read

# Kill mcp-remote
kill $MCP_PID 2>/dev/null
echo ""
echo "mcp-remote stopped"
echo "Check /tmp/mcp-remote-token.log for any token information"

