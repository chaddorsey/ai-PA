#!/usr/bin/env bash
# Host launchd entry for the current-briefing refresher. Sources pa-tools env,
# enforces the active-hours window, runs the pinned-venv refresher. Exits
# non-zero on failure (launchd records it; the freshness monitor is the SLO).
set -euo pipefail

ENV_FILE="/Users/dorseyhomeserver/.letta/pa-tools.env"
VENV_PY="/Users/dorseyhomeserver/.letta/pa-tools-venv/bin/python"
REPO="/Volumes/main-drive/ai-PA"

# Active-hours guard: only run 06:00..22:59 Eastern (cheap no-op otherwise).
HOUR=$(TZ=America/New_York date +%H)
if (( 10#$HOUR < 6 || 10#$HOUR > 22 )); then
    exit 0
fi

set -a; . "$ENV_FILE"; set +a
export PATH="/Users/dorseyhomeserver/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"
export PYTHONPATH="${REPO}/letta/pulse-tools:${REPO}/letta"

exec "$VENV_PY" -m daily_briefing.refresh_current
