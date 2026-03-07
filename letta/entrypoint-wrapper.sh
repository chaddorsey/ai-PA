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

echo "[entrypoint-wrapper] Dependencies installed. Starting Letta..."
exec letta server "$@"
