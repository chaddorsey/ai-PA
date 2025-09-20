#!/bin/bash

echo "🔍 Gmail MCP Token Monitor"
echo "========================="
echo ""

# Function to check token status
check_tokens() {
    echo "📅 Current Status: $(date)"
    
    # Check if container is running
    if ! docker ps | grep -q gmail-mcp-gmail-mcp-1; then
        echo "❌ Gmail MCP container is not running"
        return 1
    fi
    
    # Get current token info from container (without jq dependency)
    if docker exec gmail-mcp-gmail-mcp-1 test -f /gmail-server/credentials.json 2>/dev/null; then
        echo "✅ Credentials file exists"
        
        # Extract expiry date (simple approach)
        EXPIRY=$(docker exec gmail-mcp-gmail-mcp-1 grep -o '"expiry_date":[0-9]*' /gmail-server/credentials.json 2>/dev/null | cut -d: -f2)
        if [ -n "$EXPIRY" ]; then
            CURRENT_TIME=$(date +%s)000  # Convert to milliseconds
            if [ "$EXPIRY" -gt "$CURRENT_TIME" ]; then
                MINUTES_LEFT=$(( ($EXPIRY - $CURRENT_TIME) / 60000 ))
                echo "✅ Access token expires in ~$MINUTES_LEFT minutes"
            else
                echo "⚠️  Access token has expired (will auto-refresh on next use)"
            fi
        fi
        
        # Check for refresh token
        if docker exec gmail-mcp-gmail-mcp-1 grep -q '"refresh_token"' /gmail-server/credentials.json 2>/dev/null; then
            echo "✅ Refresh token present"
        else
            echo "❌ No refresh token found"
        fi
    else
        echo "❌ Credentials file not found"
    fi
    
    echo ""
}

# Function to show recent token refresh logs
show_refresh_logs() {
    echo "📝 Recent Token Refresh Activity:"
    if docker logs gmail-mcp-gmail-mcp-1 2>/dev/null | grep -E "(Auto-saved refreshed tokens|Failed to save refreshed tokens)" | tail -5 | grep -q .; then
        docker logs gmail-mcp-gmail-mcp-1 2>/dev/null | grep -E "(Auto-saved refreshed tokens|Failed to save refreshed tokens)" | tail -5
    else
        echo "   No token refresh events yet"
    fi
    echo ""
}

# Function to test server health
test_server() {
    echo "🏥 Server Health Check:"
    if curl -s http://localhost:8331/healthz | grep -q '"ok":true'; then
        echo "✅ Server is responding"
    else
        echo "❌ Server is not responding"
    fi
    echo ""
}

# Show current status
check_tokens
show_refresh_logs
test_server

# If monitoring mode requested
if [[ "$1" == "--watch" ]]; then
    echo "🔄 Watching for changes (Press Ctrl+C to stop)..."
    echo "   Will check every 60 seconds"
    echo ""
    
    while true; do
        sleep 60
        echo "----------------------------------------"
        check_tokens
        show_refresh_logs
    done
else
    echo "💡 Run with '--watch' to monitor token refresh events in real-time"
fi
