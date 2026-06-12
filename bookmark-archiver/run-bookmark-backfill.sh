#!/usr/bin/env bash
# launchd wrapper: one-time historical bookmark backfill (resumable).
# Same env as the daily archiver (Twitter cookies + LITELLM + Gitea). Runs the
# paginating backfill, which self-throttles, persists its cursor, and no-ops
# once complete. Loaded as a guard (RunAtLoad + hourly) so it survives restarts;
# unload it once `backfill_done` is set.
set -euo pipefail
REPO="/Volumes/main-drive/ai-PA"
VENV_PY="/Users/dorseyhomeserver/.letta/pa-tools-venv/bin/python"
export PATH="/Users/dorseyhomeserver/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
set -a
. "$REPO/.env" 2>/dev/null || true
. "/Users/dorseyhomeserver/.letta/pa-tools.env" 2>/dev/null || true
set +a
CFG="$REPO/smaug/smaug.config.json"
export TWITTER_CONFIG_PATH="$CFG"
export AUTH_TOKEN="$("$VENV_PY" -c "import json;print(json.load(open('$CFG'))['twitter']['authToken'])")"
export CT0="$("$VENV_PY" -c "import json;print(json.load(open('$CFG'))['twitter']['ct0'])")"
export PYTHONPATH="$REPO/bookmark-archiver"
exec "$VENV_PY" -m bookmark_archiver.backfill
