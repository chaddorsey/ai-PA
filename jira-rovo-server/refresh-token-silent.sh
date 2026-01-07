#!/bin/bash
#
# Silently refresh OAuth token using mcp-remote's stored refresh token
# This attempts to refresh without opening a browser
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/tmp/supergateway-atlassian.log"
MCP_URL="https://mcp.atlassian.com/v1/mcp"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Attempting silent token refresh..."

# Check if we have stored tokens (refresh token)
if [ ! -d "$HOME/.mcp-auth" ]; then
    log "ERROR: No mcp-auth directory found - need to complete OAuth manually first"
    exit 1
fi

# Try to refresh by running mcp-remote briefly
# mcp-remote should use the stored refresh token automatically
# We run it with a timeout and capture output
log "Running mcp-remote to refresh token..."

# Start mcp-remote in background, capture output
TEMP_LOG="/tmp/mcp-remote-refresh-$$.log"
npx mcp-remote "$MCP_URL" > "$TEMP_LOG" 2>&1 &
MCP_PID=$!

# Wait a bit for it to attempt refresh
sleep 5

# Check if it's still running (means it might be waiting for OAuth)
if kill -0 "$MCP_PID" 2>/dev/null; then
    # Check if it's waiting for OAuth or if it connected successfully
    if grep -q "OAuth callback server" "$TEMP_LOG" 2>/dev/null; then
        log "mcp-remote is waiting for OAuth - refresh token may be expired"
        kill $MCP_PID 2>/dev/null
        rm -f "$TEMP_LOG"
        exit 1
    fi
    
    # Give it a bit more time
    sleep 3
    
    # If still running, it might have connected successfully
    # Try to extract token
    kill $MCP_PID 2>/dev/null
    sleep 1
else
    # Process already finished
    sleep 1
fi

# Extract token
if "$SCRIPT_DIR/extract-token-from-mcp-auth.js" >> "$LOG_FILE" 2>&1; then
    log "Token refreshed successfully"
    rm -f "$TEMP_LOG"
    exit 0
else
    log "Failed to extract token - may need manual OAuth"
    if [ -f "$TEMP_LOG" ]; then
        log "mcp-remote output:"
        tail -10 "$TEMP_LOG" | while read line; do
            log "  $line"
        done
        rm -f "$TEMP_LOG"
    fi
    exit 1
fi

