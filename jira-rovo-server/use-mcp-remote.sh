#!/bin/bash
# Script to use mcp-remote to get OAuth token for Atlassian Rovo MCP

echo "============================================================"
echo "Using mcp-remote to Get OAuth Token"
echo "============================================================"
echo ""
echo "According to Atlassian's documentation:"
echo "https://support.atlassian.com/atlassian-rovo-mcp-server/docs/getting-started-with-the-atlassian-remote-mcp-server/"
echo ""
echo "For local clients, you need to use mcp-remote proxy."
echo ""

# Check if mcp-remote is installed
if ! command -v mcp-remote &> /dev/null; then
    echo "❌ mcp-remote is not installed."
    echo "   Install it with: npm install -g mcp-remote"
    exit 1
fi

echo "✓ mcp-remote is installed"
echo ""
echo "Starting mcp-remote..."
echo "This will:"
echo "  1. Connect to https://mcp.atlassian.com/v1/mcp"
echo "  2. Trigger OAuth flow"
echo "  3. Open browser for authorization"
echo "  4. Capture the token"
echo ""
echo "Press Ctrl+C to stop after OAuth completes"
echo ""

# Run mcp-remote
# Note: mcp-remote runs as a proxy, so we need to keep it running
# But we can capture its output to see the token
mcp-remote https://mcp.atlassian.com/v1/mcp 2>&1 | tee /tmp/mcp-remote-output.log

echo ""
echo "============================================================"
echo "OAuth Flow Complete"
echo "============================================================"
echo ""
echo "Check the output above for token information."
echo "Full log saved to: /tmp/mcp-remote-output.log"
echo ""
echo "Next steps:"
echo "  1. Extract token from mcp-remote output or storage"
echo "  2. Configure Letta to use the token"
echo "  3. Or configure Letta to use mcp-remote as a proxy"
echo ""

