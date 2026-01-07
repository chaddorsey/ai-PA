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
TOKEN_FILE="$HOME/.atlassian-rovo-token.txt"

# Token refresh interval in seconds (50 minutes = 3000 seconds, before 55 min expiry)
TOKEN_REFRESH_INTERVAL=3000

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

check_token_validity() {
    # Check if token file exists and is valid
    if [ ! -f "$TOKEN_FILE" ]; then
        return 1
    fi
    
    TOKEN=$(cat "$TOKEN_FILE" 2>/dev/null)
    if [ -z "$TOKEN" ]; then
        return 1
    fi
    
    # Test token by making a simple MCP request
    RESPONSE=$(curl -s --max-time 5 -X POST "$MCP_URL" \
      -H "Content-Type: application/json" \
      -H "Accept: application/json, text/event-stream" \
      -H "Authorization: Bearer $TOKEN" \
      -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"token-check","version":"1.0"}}}' 2>&1)
    
    if echo "$RESPONSE" | grep -q "atlassian-mcp-server"; then
        return 0
    else
        return 1
    fi
}

refresh_token_using_stored() {
    log "Attempting to refresh token using stored refresh token..."
    
    # Check if we have stored tokens
    if [ ! -d "$HOME/.mcp-auth" ]; then
        log "ERROR: No mcp-auth directory - need manual OAuth"
        return 1
    fi
    
    # mcp-remote should automatically use stored refresh token
    # Run it briefly to trigger refresh
    log "Running mcp-remote to refresh token (should use stored refresh token)..."
    
    # Start mcp-remote in background, redirect output
    TEMP_LOG="/tmp/mcp-remote-refresh-$$.log"
    npx mcp-remote "$MCP_URL" > "$TEMP_LOG" 2>&1 &
    MCP_PID=$!
    
    # Wait for it to attempt refresh
    sleep 6
    
    # Check if it's waiting for OAuth (means refresh token expired)
    if grep -q "OAuth callback server" "$TEMP_LOG" 2>/dev/null || \
       grep -q "authorize" "$TEMP_LOG" 2>/dev/null; then
        log "Refresh token expired - need manual OAuth"
        kill $MCP_PID 2>/dev/null
        rm -f "$TEMP_LOG"
        return 1
    fi
    
    # Give it a bit more time if still running
    if kill -0 "$MCP_PID" 2>/dev/null; then
        sleep 3
    fi
    
    # Stop it
    kill $MCP_PID 2>/dev/null
    sleep 1
    
    # Extract new token
    if "$SCRIPT_DIR/extract-token-from-mcp-auth.js" >> "$LOG_FILE" 2>&1; then
        log "Token refreshed successfully using stored refresh token"
        rm -f "$TEMP_LOG"
        return 0
    else
        log "Failed to extract refreshed token"
        if [ -f "$TEMP_LOG" ]; then
            log "mcp-remote output:"
            tail -5 "$TEMP_LOG" | while read line; do
                log "  $line"
            done
        fi
        rm -f "$TEMP_LOG"
        return 1
    fi
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

    # Check token validity before starting
    log "Checking token validity..."
    if ! check_token_validity; then
        log "Token is invalid or expired, attempting refresh..."
        if ! refresh_token_using_stored; then
            log "ERROR: Token refresh failed. Please run refresh-atlassian-token.sh manually"
            log "  Or run: $SCRIPT_DIR/refresh-atlassian-token.sh"
            return 1
        fi
        # Verify the refreshed token works
        if ! check_token_validity; then
            log "ERROR: Refreshed token is still invalid"
            return 1
        fi
        log "Token refreshed successfully"
    else
        log "Token is valid"
    fi

    log "Starting supergateway on port $PORT..."
    
    # Start supergateway with mcp-remote
    # mcp-remote will use stored tokens automatically
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
    log "Refreshing OAuth token..."
    
    # Try using stored refresh token first
    if refresh_token_using_stored; then
        log "Token refresh completed successfully"
        return 0
    else
        log "Automatic refresh failed - may need manual OAuth"
        log "Run: $SCRIPT_DIR/refresh-atlassian-token.sh"
        return 1
    fi
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
    
    if ! start_supergateway; then
        log "ERROR: Failed to start supergateway"
        return 1
    fi
    
    while true; do
        sleep $TOKEN_REFRESH_INTERVAL
        
        log "Scheduled token refresh (proactive refresh before expiration)..."
        
        # Check if token is still valid
        if check_token_validity; then
            log "Token is still valid, refreshing proactively..."
        else
            log "Token expired, refreshing now..."
        fi
        
        # Attempt refresh
        if refresh_token_using_stored; then
            log "Token refreshed, restarting supergateway..."
            restart_supergateway
        else
            log "WARNING: Token refresh failed, but continuing with current token"
            log "Supergateway will continue running, but may fail when token expires"
            log "Run refresh-atlassian-token.sh manually if needed"
        fi
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

