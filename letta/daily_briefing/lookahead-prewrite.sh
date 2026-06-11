#!/usr/bin/env bash
# Host launchd entry for the daily schedule lookahead pre-write (D+2..D+13).
# Sources pa-tools env, runs the pinned-venv module. Exits non-zero on any
# per-day failure (the module also writes an urgent health signal).
set -euo pipefail

ENV_FILE="/Users/dorseyhomeserver/.letta/pa-tools.env"
VENV_PY="/Users/dorseyhomeserver/.letta/pa-tools-venv/bin/python"
REPO="/Volumes/main-drive/ai-PA"

set -a; . "$ENV_FILE"; set +a
export PATH="/Users/dorseyhomeserver/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"
export PYTHONPATH="${REPO}/letta/pulse-tools:${REPO}/letta"

exec "$VENV_PY" -m daily_briefing.lookahead_prewrite
