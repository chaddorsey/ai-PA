#!/bin/bash
# Test if mcp-remote is working and can make authenticated requests

echo "============================================================"
echo "Testing mcp-remote Connection"
echo "============================================================"
echo ""

# Start mcp-remote in the background
echo "Starting mcp-remote..."
mcp-remote https://mcp.atlassian.com/v1/mcp > /tmp/mcp-remote.log 2>&1 &
MCP_REMOTE_PID=$!

echo "mcp-remote PID: $MCP_REMOTE_PID"
echo "Waiting for OAuth to complete..."
echo ""

# Wait a bit for OAuth
sleep 10

# Check if mcp-remote is still running (means OAuth completed)
if ps -p $MCP_REMOTE_PID > /dev/null; then
    echo "✓ mcp-remote is running (OAuth likely completed)"
    echo ""
    echo "Check the log for token information:"
    echo "  tail -f /tmp/mcp-remote.log"
    echo ""
    echo "To stop mcp-remote:"
    echo "  kill $MCP_REMOTE_PID"
else
    echo "⚠️  mcp-remote stopped. Check /tmp/mcp-remote.log for errors"
fi

