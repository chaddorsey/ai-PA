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

# Install gws CLI (Google Workspace) for Gmail/Calendar/Drive API access
GWS_VERSION=0.7.0
ARCH=$(uname -m)
if [ "$ARCH" = "aarch64" ]; then
    TARGET="aarch64-unknown-linux-gnu"
elif [ "$ARCH" = "x86_64" ]; then
    TARGET="x86_64-unknown-linux-gnu"
else
    echo "[entrypoint-wrapper] Unsupported arch for gws: $ARCH"
    TARGET=""
fi

if [ -n "$TARGET" ] && ! command -v gws &>/dev/null; then
    echo "[entrypoint-wrapper] Installing gws ${GWS_VERSION} (${TARGET})..."
    curl -fsSL "https://github.com/googleworkspace/cli/releases/download/v${GWS_VERSION}/gws-${TARGET}.tar.gz" \
        | tar -xz --strip-components=1 -C /usr/local/bin/ \
        && chmod +x /usr/local/bin/gws \
        && echo "[entrypoint-wrapper] gws ${GWS_VERSION} installed" \
        || echo "[entrypoint-wrapper] WARNING: Failed to download gws binary"
fi

# Install SSH client for laptop access via Tailscale
if ! command -v ssh &>/dev/null; then
    echo "[entrypoint-wrapper] Installing SSH client..."
    apt-get update -qq && apt-get install -y -qq openssh-client 2>&1 | tail -1
fi

echo "[entrypoint-wrapper] Dependencies installed. Starting Letta..."
exec letta server "$@"
