#!/usr/bin/env bash
# launchd wrapper: sync OmniFocus-timer actuals -> pa_web.tasks.actual_minutes.
# Sources env for PA_WEB_POSTGRES_URL; runs the idempotent sync via the pa-tools venv.
set -euo pipefail
REPO="/Volumes/main-drive/ai-PA"
VENV_PY="/Users/dorseyhomeserver/.letta/pa-tools-venv/bin/python"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
set -a
. "$REPO/.env" 2>/dev/null || true
. "/Users/dorseyhomeserver/.letta/pa-tools.env" 2>/dev/null || true
set +a
exec "$VENV_PY" "$REPO/scripts/sync-actual-minutes.py"
