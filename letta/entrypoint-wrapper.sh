#!/bin/bash
# Letta entrypoint wrapper — installs sandbox pip requirements before starting
# These packages are needed by custom tools (prepare_completion_feedback, etc.)
# and won't survive container rebuilds without this script.

set -e

echo "[entrypoint-wrapper] Installing custom tool dependencies..."
python3 -m ensurepip --default-pip 2>/dev/null || true
python3 -m pip install --quiet --no-warn-script-location \
    pytz \
    google-auth \
    google-auth-oauthlib \
    google-api-python-client \
    2>&1 | tail -3

echo "[entrypoint-wrapper] Dependencies installed. Starting Letta..."
exec letta server "$@"
