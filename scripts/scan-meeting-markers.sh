#!/usr/bin/env bash
# scan-meeting-markers.sh
#
# Wrapper around scripts/scan_meeting_markers.py — sets env from .env so launchd
# can run it without a full shell. Restores the [c]/[;] meeting-marker → task
# path that broke when the meeting pipeline moved off the Granola MCP onto the
# REST poller (the REST API does not expose private notes; the markers live only
# in the MCP's <private_notes>). Logs to logs/health/meeting-marker-scan.log.
#
# Cadence: every 30 min via launchd (com.ai-pa.meeting-marker-scanner.plist).
# Deliberately less frequent than the docs-meeting poller — the marker scan
# makes one MCP get_meetings call per meeting in the window, and the MCP
# throttles under rapid calls.

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/Volumes/main-drive/ai-PA}"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
LOG_DIR="${LOG_DIR:-$REPO_ROOT/logs/health}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/meeting-marker-scan.log"

ts() { date -u "+%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" | tee -a "$LOG"; }

# Prefer a plist-supplied POSTGRES_PASSWORD; fall back to .env. Fail LOUDLY if
# neither yields one — a silent no-op is exactly the failure mode we're avoiding.
if [[ -z "${POSTGRES_PASSWORD:-}" && -r "$ENV_FILE" ]]; then
  POSTGRES_PASSWORD=$(grep ^POSTGRES_PASSWORD= "$ENV_FILE" | cut -d= -f2-)
fi
if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  log "FATAL: POSTGRES_PASSWORD unavailable (env var unset and $ENV_FILE unreadable). Check the LaunchAgent plist."
  exit 1
fi
export POSTGRES_PASSWORD
export PA_WEB_POSTGRES_PORT="${PA_WEB_POSTGRES_PORT:-5433}"
export GRANOLA_MCP_URL="${GRANOLA_MCP_URL:-http://localhost:8089/mcp}"

# Use a Python with psycopg available (the pipx task-cli venv has it).
PYTHON="${PYTHON:-/Users/dorseyhomeserver/.local/pipx/venvs/task-cli/bin/python}"
[[ -x "$PYTHON" ]] || PYTHON="/opt/homebrew/bin/python3"
[[ -x "$PYTHON" ]] || PYTHON="$(which python3)"

"$PYTHON" "$REPO_ROOT/scripts/scan_meeting_markers.py" \
  --window-days "${MARKER_WINDOW_DAYS:-14}" 2>&1 | tee -a "$LOG"
exit "${PIPESTATUS[0]}"
