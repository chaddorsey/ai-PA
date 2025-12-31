#!/bin/bash
#
# Supergateway Service for Atlassian Rovo MCP
# 
# This script manages supergateway as a bridge between Letta and Atlassian MCP.
# It handles:
#   - Starting supergateway with mcp-remote
#   - Automatic token refresh (tokens expire after ~55 minutes)
#   - Graceful restarts
#
# Usage:
#   ./supergateway-service.sh start   - Start the service
#   ./supergateway-service.sh stop    - Stop the service
#   ./supergateway-service.sh restart - Restart the service
#   ./supergateway-service.sh status  - Check status
#   ./supergateway-service.sh refresh - Refresh OAuth token
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/tmp/supergateway-atlassian.log"
PID_FILE="/tmp/supergateway-atlassian.pid"
PORT=9999
MCP_URL="https://mcp.atlassian.com/v1/mcp"

# Token refresh interval in seconds (50 minutes = 3000 seconds, before 55 min expiry)
TOKEN_REFRESH_INTERVAL=3000

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

start_supergateway() {
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if kill -0 "$OLD_PID" 2>/dev/null; then
            log "Supergateway already running (PID: $OLD_PID)"
            return 0
        fi
        rm -f "$PID_FILE"
    fi

    log "Starting supergateway on port $PORT..."
    
    # Start supergateway with mcp-remote
    nohup supergateway \
        --stdio "npx mcp-remote $MCP_URL" \
        --outputTransport streamableHttp \
        --port $PORT \
        --cors \
        --logLevel info >> "$LOG_FILE" 2>&1 &
    
    SG_PID=$!
    echo $SG_PID > "$PID_FILE"
    
    sleep 3
    
    if kill -0 "$SG_PID" 2>/dev/null; then
        log "Supergateway started successfully (PID: $SG_PID)"
        log "Endpoint: http://localhost:$PORT/mcp"
        return 0
    else
        log "ERROR: Supergateway failed to start"
        rm -f "$PID_FILE"
        return 1
    fi
}

stop_supergateway() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        log "Stopping supergateway (PID: $PID)..."
        kill "$PID" 2>/dev/null
        sleep 2
        kill -9 "$PID" 2>/dev/null
        rm -f "$PID_FILE"
        log "Supergateway stopped"
    else
        log "Supergateway not running (no PID file)"
    fi
    
    # Also kill any orphaned processes
    pkill -f "supergateway.*$PORT" 2>/dev/null
    pkill -f "mcp-remote.*atlassian" 2>/dev/null
}

restart_supergateway() {
    stop_supergateway
    sleep 2
    start_supergateway
}

refresh_token() {
    log "Refreshing OAuth token via mcp-remote..."
    
    # Run mcp-remote briefly to refresh the token
    npx mcp-remote "$MCP_URL" &
    MCP_PID=$!
    sleep 8
    kill $MCP_PID 2>/dev/null
    
    log "Token refresh completed"
}

check_status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            log "Supergateway is running (PID: $PID)"
            
            # Test connection
            RESPONSE=$(curl -s --max-time 5 -X POST "http://localhost:$PORT/mcp" \
                -H "Content-Type: application/json" \
                -H "Accept: application/json, text/event-stream" \
                -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"health-check","version":"1.0"}}}' 2>&1)
            
            if echo "$RESPONSE" | grep -q "atlassian-mcp-server"; then
                log "Connection to Atlassian MCP: OK"
                return 0
            else
                log "Connection to Atlassian MCP: FAILED"
                log "Response: $RESPONSE"
                return 1
            fi
        else
            log "Supergateway not running (stale PID file)"
            rm -f "$PID_FILE"
            return 1
        fi
    else
        log "Supergateway not running"
        return 1
    fi
}

# Auto-refresh loop (for daemon mode)
run_with_refresh() {
    log "Starting supergateway with auto-refresh (every $TOKEN_REFRESH_INTERVAL seconds)..."
    
    start_supergateway
    
    while true; do
        sleep $TOKEN_REFRESH_INTERVAL
        
        log "Scheduled token refresh..."
        refresh_token
        
        # Restart supergateway to use fresh token
        restart_supergateway
    done
}

case "$1" in
    start)
        start_supergateway
        ;;
    stop)
        stop_supergateway
        ;;
    restart)
        restart_supergateway
        ;;
    status)
        check_status
        ;;
    refresh)
        refresh_token
        restart_supergateway
        ;;
    daemon)
        run_with_refresh
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|refresh|daemon}"
        echo ""
        echo "Commands:"
        echo "  start   - Start supergateway"
        echo "  stop    - Stop supergateway"
        echo "  restart - Restart supergateway"
        echo "  status  - Check status and test connection"
        echo "  refresh - Refresh OAuth token and restart"
        echo "  daemon  - Run with automatic token refresh (every 50 min)"
        exit 1
        ;;
esac

