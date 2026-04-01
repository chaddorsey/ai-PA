#!/bin/bash
# Letta entrypoint wrapper — installs sandbox pip requirements before starting
# These packages are needed by custom tools (prepare_completion_feedback, etc.)
# and won't survive container rebuilds without this script.

set -e

echo "[entrypoint-wrapper] Installing custom tool dependencies..."
python3 -m ensurepip --default-pip 2>/dev/null || true
python3 -m pip install --quiet --no-warn-script-location \
    pytz \
    2>&1 | tail -3

# Install omnifocus-cli for OmniFocus task management
if [ -d "/app/tools/omnifocus-cli" ]; then
    echo "[entrypoint-wrapper] Installing omnifocus-cli..."
    python3 -m pip install --quiet --no-warn-script-location \
        /app/tools/omnifocus-cli/ \
        2>&1 | tail -3
fi

# Install notebooklm-cli for NotebookLM access
if [ -d "/app/tools/notebooklm-cli" ]; then
    echo "[entrypoint-wrapper] Installing notebooklm-cli..."
    python3 -m pip install --quiet --no-warn-script-location \
        /app/tools/notebooklm-cli/ \
        2>&1 | tail -3
fi

# Install slack-cli for Slack Web API access
if [ -d "/app/tools/slack-cli" ]; then
    echo "[entrypoint-wrapper] Installing slack-cli..."
    python3 -m pip install --quiet --no-warn-script-location \
        /app/tools/slack-cli/ \
        2>&1 | tail -3
fi

# Install/update gws CLI (Google Workspace) for Gmail/Calendar/Drive API access
if [ -f "/app/tools/scripts/update-gws.sh" ]; then
    GWS_INSTALL_DIR=/usr/local/bin bash /app/tools/scripts/update-gws.sh || \
        echo "[entrypoint-wrapper] WARNING: gws update failed, continuing with existing version"
elif ! command -v gws &>/dev/null; then
    echo "[entrypoint-wrapper] WARNING: update-gws.sh not found and gws not installed"
fi

# Install SSH client for laptop access via Tailscale
if ! command -v ssh &>/dev/null; then
    echo "[entrypoint-wrapper] Installing SSH client..."
    apt-get update -qq && apt-get install -y -qq openssh-client 2>&1 | tail -1
fi

echo "[entrypoint-wrapper] Dependencies installed. Starting Letta..."
exec letta server "$@"
