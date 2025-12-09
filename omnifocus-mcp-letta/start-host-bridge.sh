#!/bin/bash
# Start the OmniFocus host bridge service
# This service must run on the macOS host to execute osascript

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

PORT=${1:-8889}

echo "🚀 Starting OmniFocus Host Bridge Service on port $PORT"
echo "   This service allows Docker containers to execute osascript commands"
echo "   Endpoint: http://localhost:$PORT/execute"
echo ""

# Check if node is available
if ! command -v node &> /dev/null; then
    echo "❌ Error: node is not installed or not in PATH"
    exit 1
fi

# Check if osascript is available
if ! command -v osascript &> /dev/null; then
    echo "❌ Error: osascript is not available (this should only run on macOS)"
    exit 1
fi

# Start the service
node host-bridge-service.js "$PORT"

