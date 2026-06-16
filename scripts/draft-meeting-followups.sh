#!/usr/bin/env bash
# draft-meeting-followups.sh
#
# Wrapper around scripts/draft_meeting_followup.py — sets env from .env so
# launchd can run it. Creates post-meeting follow-up Gmail DRAFTS (D/NA format)
# by re-sourcing the well-designed prepare_meeting_followup tool from the Granola
# REST API (attendees + summary) + MCP (private-note markers), with one bounded
# litellm call for the decision/action lists. Idempotent via a state file.
#
# Cadence: every 30 min via launchd (com.ai-pa.meeting-followup-drafter.plist).
# Logs to logs/health/meeting-followup-draft.log.

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/Volumes/main-drive/ai-PA}"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
LOG_DIR="${LOG_DIR:-$REPO_ROOT/logs/health}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/meeting-followup-draft.log"

ts() { date -u "+%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" | tee -a "$LOG"; }

# Keys: prefer plist-supplied env; fall back to .env. Fail LOUD if missing.
if [[ -z "${GRANOLA_API_KEY:-}" && -r "$ENV_FILE" ]]; then
  GRANOLA_API_KEY=$(grep ^GRANOLA_API_KEY= "$ENV_FILE" | cut -d= -f2-)
fi
if [[ -z "${LITELLM_MASTER_KEY:-}" && -r "$ENV_FILE" ]]; then
  LITELLM_MASTER_KEY=$(grep ^LITELLM_MASTER_KEY= "$ENV_FILE" | cut -d= -f2-)
fi
if [[ -z "${GRANOLA_API_KEY:-}" ]]; then
  log "FATAL: GRANOLA_API_KEY unavailable (env unset and $ENV_FILE unreadable)."
  exit 1
fi
export GRANOLA_API_KEY LITELLM_MASTER_KEY
export GRANOLA_MCP_URL="${GRANOLA_MCP_URL:-http://localhost:8089/mcp}"
export LITELLM_URL="${LITELLM_URL:-http://localhost:4000}"
export GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE="${GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE:-$REPO_ROOT/gws-bridge/credentials.json}"
export PA_AI_REPO_ROOT="$REPO_ROOT"

# prepare_meeting_followup shells out to `gws` (~/bin/gws). launchd's minimal
# PATH doesn't include it, so prepend the CLI dirs — without this, every draft
# fails with "No such file or directory: 'gws'".
export PATH="$HOME/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

# Use a Python with pytz + psycopg available (the pipx task-cli venv — pytz was
# injected for prepare_meeting_followup).
PYTHON="${PYTHON:-/Users/dorseyhomeserver/.local/pipx/venvs/task-cli/bin/python}"
[[ -x "$PYTHON" ]] || PYTHON="/opt/homebrew/bin/python3"
[[ -x "$PYTHON" ]] || PYTHON="$(which python3)"

"$PYTHON" "$REPO_ROOT/scripts/draft_meeting_followup.py" \
  --window-days "${FOLLOWUP_WINDOW_DAYS:-2}" 2>&1 | tee -a "$LOG"
exit "${PIPESTATUS[0]}"
