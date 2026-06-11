#!/usr/bin/env bash
# Entrypoint for MC: query open work-time across a date range. Loads pa-tools
# env (Gitea token + gws creds for lazy refresh) and forwards all args.
set -euo pipefail
ENV_FILE="/Users/dorseyhomeserver/.letta/pa-tools.env"
VENV_PY="/Users/dorseyhomeserver/.letta/pa-tools-venv/bin/python"
REPO="/Volumes/main-drive/ai-PA"
set -a; . "$ENV_FILE"; set +a
export PATH="/Users/dorseyhomeserver/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"
export PYTHONPATH="${REPO}/letta/pulse-tools:${REPO}/letta"
exec "$VENV_PY" -m daily_briefing.query_available_time "$@"
