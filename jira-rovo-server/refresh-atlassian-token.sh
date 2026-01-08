#!/bin/bash
#
# Refresh Atlassian Rovo MCP OAuth token
# This script helps complete the OAuth flow manually
#

echo "============================================================"
echo "Refresh Atlassian Rovo MCP Token"
echo "============================================================"
echo ""
echo "This will:"
echo "  1. Stop supergateway temporarily"
echo "  2. Start mcp-remote to trigger OAuth"
echo "  3. Wait for you to complete OAuth in browser"
echo "  4. Extract and save the new token"
echo "  5. Restart supergateway"
echo ""
echo "Press Enter to continue, or Ctrl+C to cancel..."
read

# Stop supergateway
echo ""
echo "Stopping supergateway..."
/Volumes/main-drive/ai-PA/jira-rovo-server/supergateway-service.sh stop
sleep 2

# Kill any existing mcp-remote processes
pkill -f "mcp-remote.*atlassian" 2>/dev/null
sleep 1

# Start mcp-remote
echo ""
echo "Starting mcp-remote..."
echo "A browser window should open for OAuth."
echo "Complete the authorization, then come back here."
echo ""
cd /Volumes/main-drive/ai-PA/jira-rovo-server

# Run mcp-remote in foreground so user can see what's happening
echo "Starting mcp-remote (this will open a browser window)..."
npx mcp-remote https://mcp.atlassian.com/v1/mcp > /tmp/mcp-remote-oauth.log 2>&1 &
MCP_PID=$!

# Wait a moment for mcp-remote to start
sleep 3

# Check if OAuth callback server started
if lsof -i :3736 >/dev/null 2>&1; then
    echo "✓ OAuth callback server is running on port 3736"
else
    echo "⚠ OAuth callback server not detected on port 3736"
    echo "  Check /tmp/mcp-remote-oauth.log for details"
fi

echo ""
echo "mcp-remote started (PID: $MCP_PID)"
echo "A browser window should open for OAuth."
echo ""
echo "IMPORTANT: Complete the OAuth flow in the browser."
echo "If you see 'Safari can't connect to localhost:3736', try:"
echo "  1. Wait a few seconds and refresh the callback URL"
echo "  2. Or copy the callback URL and open it manually"
echo ""
echo "After OAuth completes (you should see 'Authorization successful'),"
echo "press Enter here to continue..."
read

# Stop mcp-remote
echo ""
echo "Stopping mcp-remote..."
kill $MCP_PID 2>/dev/null
sleep 2

# Extract token
echo ""
echo "Extracting token..."
cd /Volumes/main-drive/ai-PA/jira-rovo-server
node extract-token-from-mcp-auth.js

if [ -f ~/.atlassian-rovo-token.txt ]; then
    TOKEN=$(cat ~/.atlassian-rovo-token.txt)
    if [ -n "$TOKEN" ]; then
        echo ""
        echo "✓ Token extracted successfully"
        echo ""
        echo "Restarting supergateway..."
        /Volumes/main-drive/ai-PA/jira-rovo-server/supergateway-service.sh restart
        sleep 5
        
        echo ""
        echo "Checking status..."
        /Volumes/main-drive/ai-PA/jira-rovo-server/supergateway-service.sh status
    else
        echo ""
        echo "✗ Token file is empty - OAuth may not have completed"
    fi
else
    echo ""
    echo "✗ No token file found - OAuth may not have completed"
    echo "Try running the OAuth flow again"
fi

