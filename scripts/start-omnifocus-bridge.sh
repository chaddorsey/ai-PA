#!/bin/bash
#
# Start OmniFocus Host Bridge Service
#
# This service runs on the macOS host and provides an AppleScript bridge
# for the OmniFocus MCP server (which runs in Docker).
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BRIDGE_DIR="$PROJECT_ROOT/omnifocus-mcp-letta"
PID_FILE="/tmp/omnifocus-bridge.pid"
LOG_FILE="$PROJECT_ROOT/logs/omnifocus-bridge.log"

# Create logs directory if it doesn't exist
mkdir -p "$(dirname "$LOG_FILE")"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "✓ OmniFocus bridge already running (PID: $PID)"
        exit 0
    else
        echo "  Removing stale PID file"
        rm "$PID_FILE"
    fi
fi

# Environment variables (match launchd plist com.omnifocus.bridge)
export TIMER_LOG_DIR="${TIMER_LOG_DIR:-$PROJECT_ROOT/omnifocus-timer/logs}"
export LETTA_URL="${LETTA_URL:-http://localhost:8283}"
export MC_AGENT_ID="${MC_AGENT_ID:-agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef}"
export ROVER_AGENT_ID="${ROVER_AGENT_ID:-agent-76ee5448-68ec-4fdd-b102-d4895d44e090}"

# Start the bridge
echo "Starting OmniFocus host bridge..."
cd "$BRIDGE_DIR"

# Start in background and capture PID
nohup node host-bridge-service.js 8889 >> "$LOG_FILE" 2>&1 &
BRIDGE_PID=$!

# Save PID
echo "$BRIDGE_PID" > "$PID_FILE"

# Wait a moment and verify it started
sleep 2

if ps -p "$BRIDGE_PID" > /dev/null 2>&1; then
    echo "✓ OmniFocus bridge started successfully (PID: $BRIDGE_PID)"
    echo "  Listening on: http://0.0.0.0:8889/execute"
    echo "  Log file: $LOG_FILE"
else
    echo "✗ Failed to start OmniFocus bridge"
    rm -f "$PID_FILE"
    exit 1
fi
