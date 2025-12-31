#!/bin/bash
#
# Install Supergateway Atlassian MCP as a launchd service
#
# This will:
# 1. Copy the plist to ~/Library/LaunchAgents/
# 2. Load the service
# 3. The service will start automatically on login
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_NAME="com.ai-pa.supergateway-atlassian.plist"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "Installing Supergateway Atlassian MCP launchd service..."
echo ""

# Check if source plist exists
if [ ! -f "$PLIST_SRC" ]; then
    echo "ERROR: Plist file not found: $PLIST_SRC"
    exit 1
fi

# Stop existing service if running
if launchctl list | grep -q "com.ai-pa.supergateway-atlassian"; then
    echo "Stopping existing service..."
    launchctl unload "$PLIST_DEST" 2>/dev/null
fi

# Stop any running supergateway
"$SCRIPT_DIR/supergateway-service.sh" stop 2>/dev/null

# Create LaunchAgents directory if needed
mkdir -p "$HOME/Library/LaunchAgents"

# Copy plist
echo "Copying plist to $PLIST_DEST..."
cp "$PLIST_SRC" "$PLIST_DEST"

# Load the service
echo "Loading service..."
launchctl load "$PLIST_DEST"

sleep 3

# Check status
if launchctl list | grep -q "com.ai-pa.supergateway-atlassian"; then
    echo ""
    echo "✓ Service installed and running!"
    echo ""
    echo "The service will:"
    echo "  - Start automatically on login"
    echo "  - Refresh OAuth token every 50 minutes"
    echo "  - Restart automatically if it crashes"
    echo ""
    echo "Logs: /tmp/supergateway-atlassian.log"
    echo "Endpoint: http://localhost:9999/mcp"
    echo ""
    echo "Manual commands:"
    echo "  Check status: $SCRIPT_DIR/supergateway-service.sh status"
    echo "  Stop:         launchctl unload $PLIST_DEST"
    echo "  Start:        launchctl load $PLIST_DEST"
    echo "  Uninstall:    rm $PLIST_DEST && launchctl remove com.ai-pa.supergateway-atlassian"
else
    echo ""
    echo "ERROR: Service failed to start. Check logs:"
    echo "  tail -50 /tmp/supergateway-atlassian-launchd.log"
    exit 1
fi

