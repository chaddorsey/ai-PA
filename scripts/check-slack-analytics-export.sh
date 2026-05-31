#!/usr/bin/env bash
# check-slack-analytics-export.sh
#
# Daily watchdog for slack-analytics-mcp-server's Playwright export job.
# Looks at the last 26 hours of container logs; if no "export succeeded"
# message is found, emits a canonical signal at attention=elevated and
# (optionally) DMs Chad on Slack.
#
# Intended to run via launchd around 07:00 ET (after the 06:00 export crons).

set -euo pipefail

CONTAINER="slack-analytics-mcp-server"
LOOKBACK_HOURS=26
ENV_FILE="${ENV_FILE:-/Volumes/main-drive/ai-PA/.env}"
LOG_DIR="${LOG_DIR:-/Volumes/main-drive/ai-PA/logs/health}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/check-slack-analytics-export.log"

ts() { date -u "+%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" | tee -a "$LOG_FILE"; }

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  log "WARN: container $CONTAINER not running — skipping check"
  exit 0
fi

since="${LOOKBACK_HOURS}h"
logs=$(docker logs --since "$since" "$CONTAINER" 2>&1 || true)

successes=$(echo "$logs" | grep -c "Slack analytics export succeeded" || true)
failures=$(echo "$logs" | grep -c "Slack analytics export failed" || true)

log "lookback=${LOOKBACK_HOURS}h successes=$successes failures=$failures"

if [[ "$successes" -gt 0 ]]; then
  log "OK: at least one export succeeded in lookback window"
  exit 0
fi

# Failure path — gather the last error excerpt
last_err=$(echo "$logs" | grep -A 8 "Slack analytics export failed" | tail -50)

# Try to grab the most recent debug HTML filename for the followup
last_debug=$(docker exec "$CONTAINER" sh -c 'ls -t /app/slack_analytics_screenshots/*_debug_*.html 2>/dev/null | head -1' || true)

body=$(cat <<EOF
**slack-analytics-mcp-server: no successful exports in last ${LOOKBACK_HOURS}h.**

- successes: $successes
- failures: $failures
- last debug artifact (inside container): \`${last_debug:-none}\`

Last failure tail:
\`\`\`
$last_err
\`\`\`

This means the daily Slack admin CSV export is broken (likely Slack DOM
or URL change). Live \`slack\` CLI queries are still fine; only the
admin-CSV-based analytics pipeline is affected.

Diagnosis + recovery: docs/followups/2026-05-31-slack-analytics-export-broken.md
EOF
)

# Emit canonical signal (best-effort, with env from .env)
if [[ -f "$ENV_FILE" ]]; then
  GITEA_MEMFS_TOKEN=$(grep ^GITEA_MEMFS_TOKEN= "$ENV_FILE" | cut -d= -f2-)
  export GITEA_MEMFS_TOKEN
  export GITEA_BASE_URL="${GITEA_BASE_URL:-http://localhost:3030}"
fi

if command -v signal >/dev/null 2>&1; then
  if echo "$body" | signal emit \
    --slug slack-analytics-export-failed \
    --source health-watchdog \
    --attention elevated \
    --description "slack-analytics export job: no successes in ${LOOKBACK_HOURS}h" \
    --body-file -; then
    log "emitted canonical signal slack-analytics-export-failed"
  else
    log "WARN: signal emit failed"
  fi
else
  log "WARN: signal CLI not on PATH"
fi

# Optional: Slack DM. Use --as-user so user-token reaches Chad's DM.
if command -v slack >/dev/null 2>&1; then
  short=$(echo "$body" | head -8)
  if slack --as-user chat +send \
    --channel "@chad.dorsey" \
    --text "$short" >/dev/null 2>&1; then
    log "posted Slack DM"
  else
    log "WARN: slack DM failed (token scope / target)"
  fi
fi

exit 1
