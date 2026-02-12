#!/bin/bash
#
# Supergateway Service for Granola MCP
#
# Bridges Letta to Granola's MCP server via supergateway + mcp-remote.
# mcp-remote handles OAuth (stored in ~/.mcp-auth/) and supergateway
# exposes a local HTTP endpoint that Letta can reach.
#
# Usage:
#   ./supergateway-service.sh start   - Start the service
#   ./supergateway-service.sh stop    - Stop the service
#   ./supergateway-service.sh restart - Restart the service
#   ./supergateway-service.sh status  - Check status
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="/tmp/supergateway-granola.log"
PID_FILE="/tmp/supergateway-granola.pid"
PORT=8089
MCP_URL="https://mcp.granola.ai/mcp"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

check_connection() {
    # Test the local supergateway endpoint
    RESPONSE=$(curl -s --max-time 5 -X POST "http://localhost:$PORT/mcp" \
      -H "Content-Type: application/json" \
      -H "Accept: application/json, text/event-stream" \
      -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"health-check","version":"1.0"}}}' 2>&1)

    if echo "$RESPONSE" | grep -q '"serverInfo"'; then
        return 0
    else
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

    log "Starting supergateway for Granola MCP on port $PORT..."

    # supergateway wraps mcp-remote (stdio) and exposes it as streamable HTTP
    # mcp-remote handles OAuth token storage/refresh via ~/.mcp-auth/
    nohup supergateway \
        --stdio "npx mcp-remote $MCP_URL" \
        --outputTransport streamableHttp \
        --port $PORT \
        --cors \
        --logLevel info >> "$LOG_FILE" 2>&1 &

    SG_PID=$!
    echo $SG_PID > "$PID_FILE"

    # Wait for startup
    sleep 5

    if kill -0 "$SG_PID" 2>/dev/null; then
        log "Supergateway started (PID: $SG_PID)"
        log "Endpoint: http://localhost:$PORT/mcp"

        # Test connection
        if check_connection; then
            log "Connection to Granola MCP: OK"
        else
            log "WARNING: Supergateway started but Granola MCP not responding yet"
            log "  mcp-remote may need OAuth - check if a browser window opened"
            log "  Or run: python3 $PROJECT_ROOT/scripts/granola-oauth.py"
        fi
        return 0
    else
        log "ERROR: Supergateway failed to start"
        log "Last log lines:"
        tail -5 "$LOG_FILE" | while read line; do log "  $line"; done
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

    # Kill orphaned processes
    pkill -f "supergateway.*$PORT" 2>/dev/null
    pkill -f "mcp-remote.*granola" 2>/dev/null
}

restart_supergateway() {
    stop_supergateway
    sleep 2
    start_supergateway
}

check_status() {
    echo "Granola MCP Supergateway Status"
    echo "--------------------------------"

    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "  Process: Running (PID: $PID)"

            if check_connection; then
                echo "  Connection: OK"

                # Show available tools
                TOOLS=$(curl -s --max-time 5 -X POST "http://localhost:$PORT/mcp" \
                    -H "Content-Type: application/json" \
                    -H "Accept: application/json, text/event-stream" \
                    -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' 2>&1)

                TOOL_COUNT=$(echo "$TOOLS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('result',{}).get('tools',[])))" 2>/dev/null || echo "?")
                echo "  Tools available: $TOOL_COUNT"
            else
                echo "  Connection: FAILED (supergateway running but MCP not responding)"
            fi
            return 0
        else
            echo "  Process: Not running (stale PID file)"
            rm -f "$PID_FILE"
            return 1
        fi
    else
        echo "  Process: Not running"
        return 1
    fi
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
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        echo ""
        echo "Granola MCP Supergateway Proxy"
        echo "  Bridges Letta to https://mcp.granola.ai/mcp via local HTTP"
        echo "  Local endpoint: http://localhost:$PORT/mcp"
        echo ""
        echo "Commands:"
        echo "  start   - Start supergateway (opens browser for OAuth if needed)"
        echo "  stop    - Stop supergateway"
        echo "  restart - Restart supergateway"
        echo "  status  - Check status and test connection"
        exit 1
        ;;
esac
