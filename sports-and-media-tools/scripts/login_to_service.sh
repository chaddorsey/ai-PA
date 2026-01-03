#!/bin/bash
#
# Login to Streaming Services - Session Capture Tool
#
# This script helps you log into streaming services to capture
# authentication sessions for the watch history poller.
#
# Usage:
#   ./login_to_service.sh <service>
#   ./login_to_service.sh all
#
# Services: max, netflix, disney, apple, prime, hulu
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_DIR="$PROJECT_DIR/watch-history-service"
CREDENTIALS_DIR="$PROJECT_DIR/credentials"

# Ensure credentials directory exists and is mounted properly
mkdir -p "$CREDENTIALS_DIR/browser_states"

# Check for Python and Playwright
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

# Check if playwright is installed
if ! python3 -c "import playwright" 2>/dev/null; then
    echo "📦 Installing Playwright..."
    pip3 install playwright
    python3 -m playwright install chromium
fi

# Set environment variable for credentials path
export CREDENTIALS_PATH="$CREDENTIALS_DIR"

# Run the login script
cd "$SERVICE_DIR"
python3 session_login.py "$@"

# After successful login, sync credentials to Docker volume
if [ $? -eq 0 ]; then
    echo ""
    echo "🔄 Syncing credentials to Docker container..."
    
    # Copy credentials to the Docker volume
    docker cp "$CREDENTIALS_DIR/." watch-history-service:/app/credentials/ 2>/dev/null || true
    
    echo "✅ Credentials synced!"
    echo ""
    echo "You can now poll watch history with:"
    echo "  curl -X POST http://localhost:5127/poll/<service>"
fi

