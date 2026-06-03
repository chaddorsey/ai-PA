#!/usr/bin/env bash
# poll-granola-meetings.sh
#
# Wrapper around scripts/poll_granola.py — sets the env from .env so
# launchd can run it without needing a full shell. Logs to
# logs/health/granola-poll.log.

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/Volumes/main-drive/ai-PA}"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
LOG_DIR="${LOG_DIR:-$REPO_ROOT/logs/health}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/granola-poll.log"

ts() { date -u "+%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" | tee -a "$LOG"; }

GRANOLA_API_KEY=$(grep ^GRANOLA_API_KEY= "$ENV_FILE" | cut -d= -f2-)
POSTGRES_PASSWORD=$(grep ^POSTGRES_PASSWORD= "$ENV_FILE" | cut -d= -f2-)

if [[ -z "${GRANOLA_API_KEY:-}" ]]; then
  log "ERROR: GRANOLA_API_KEY not set in $ENV_FILE"
  exit 2
fi

export GRANOLA_API_KEY
export POSTGRES_PASSWORD
export PA_WEB_POSTGRES_PORT="${PA_WEB_POSTGRES_PORT:-5433}"
export GRANOLA_POLL_STATE="${GRANOLA_POLL_STATE:-$LOG_DIR/granola-poll.state}"
export LETTA_PUSH_RECEIVER_URL="${LETTA_PUSH_RECEIVER_URL:-http://localhost:8099}"

# Use a Python with psycopg available. The pipx task-cli venv has psycopg.
PYTHON="${PYTHON:-/Users/dorseyhomeserver/.local/pipx/venvs/task-cli/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="/opt/homebrew/bin/python3"
fi
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(which python3)"
fi

"$PYTHON" "$REPO_ROOT/scripts/poll_granola.py" 2>&1 | tee -a "$LOG"
exit "${PIPESTATUS[0]}"
