#!/bin/bash
#
# Stop OmniFocus Host Bridge Service
#

PID_FILE="/tmp/omnifocus-bridge.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "OmniFocus bridge not running (no PID file)"
    exit 0
fi

PID=$(cat "$PID_FILE")

if ps -p "$PID" > /dev/null 2>&1; then
    echo "Stopping OmniFocus bridge (PID: $PID)..."
    kill "$PID"
    sleep 1

    # Force kill if still running
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "  Force killing..."
        kill -9 "$PID"
    fi

    rm "$PID_FILE"
    echo "✓ OmniFocus bridge stopped"
else
    echo "OmniFocus bridge not running (stale PID)"
    rm "$PID_FILE"
fi
