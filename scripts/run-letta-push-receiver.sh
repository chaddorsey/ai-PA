#!/bin/bash
# launchd wrapper for letta-push-receiver. Provides PATH and explicit
# env so the pipx-installed binary can find its venv python.
set -e
export PATH="/Users/dorseyhomeserver/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export LETTA_PUSH_RECEIVER_HOST="${LETTA_PUSH_RECEIVER_HOST:-127.0.0.1}"
export LETTA_PUSH_RECEIVER_PORT="${LETTA_PUSH_RECEIVER_PORT:-8099}"
export LETTA_PUSH_RECEIVER_ENV_FILE="${LETTA_PUSH_RECEIVER_ENV_FILE:-/Volumes/main-drive/ai-PA/.env}"
export LETTA_LAUNCH_DIR="${LETTA_LAUNCH_DIR:-/Volumes/main-drive/letta-launchpad}"
cd /Volumes/main-drive/ai-PA
exec /Users/dorseyhomeserver/.local/bin/letta-push-receiver
