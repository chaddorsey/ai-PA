#!/bin/bash
# Auto-Madden Companion Startup Script
# Starts all services needed for live game companion

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🏈 Starting Auto-Madden Companion..."
echo ""

# Check if ports are available
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        echo "⚠️  Port $1 is already in use"
        return 1
    fi
    return 0
}

# Kill existing processes on our ports
cleanup() {
    echo "Cleaning up..."
    pkill -f "game_simulator.py" 2>/dev/null || true
    pkill -f "insight_engine.py" 2>/dev/null || true
    pkill -f "companion-ui/app.py" 2>/dev/null || true
    sleep 1
}

# Start a service in background
start_service() {
    local name=$1
    local dir=$2
    local cmd=$3
    local port=$4
    
    echo "Starting $name on port $port..."
    cd "$SCRIPT_DIR/$dir"
    $cmd &
    sleep 2
    
    if check_port $port; then
        echo "❌ $name failed to start"
        return 1
    fi
    echo "✅ $name running"
    cd "$SCRIPT_DIR"
}

# Handle Ctrl+C
trap cleanup EXIT

# Optional: cleanup first
if [ "$1" = "--clean" ]; then
    cleanup
fi

echo "Starting services..."
echo ""

# Start simulator (game state service)
start_service "Game State Service" "simulator" "python3 game_simulator.py serve --port 5132" 5132

# Start insight engine
start_service "Insight Engine" "insight-engine" "python3 insight_engine.py" 5131

# Start companion UI
start_service "Companion UI" "companion-ui" "python3 app.py" 5130

echo ""
echo "🎉 All services started!"
echo ""
echo "Open http://localhost:5130/simple in your browser"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for interrupt
wait

