#!/usr/bin/env bash
# process-task-queue.sh
#
# Backup poller. The primary path is producer → letta-push-receiver →
# warm per-agent subprocess. If the receiver was down or a producer
# failed to POST, rows accumulate in pa_web.task_queue unclaimed. This
# script runs every 15 minutes via launchd and wakes the receiver for
# any source that has unclaimed rows.
#
# Sources handled (each is routed by the receiver to its owner agent):
#   slack            → pulse
#   email            → email
#   meeting          → docs
#   meeting_marker   → docs
#   google-docs-comment → docs
#   docs-meeting     → docs
#   drive            → docs
#
# Sources NOT handled here (they have their own consumers):
#   email-watch    → Email agent processes via its own routing
#   mc-completion  → MC reads its own completion notifications
#
# Runs every 15 min via launchd
# (~/Library/LaunchAgents/com.ai-pa.task-queue-processor.plist).

set -euo pipefail

ENV_FILE="${ENV_FILE:-/Volumes/main-drive/ai-PA/.env}"
LOG_DIR="${LOG_DIR:-/Volumes/main-drive/ai-PA/logs/health}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/process-task-queue.log"

RECEIVER_URL="${LETTA_PUSH_RECEIVER_URL:-http://127.0.0.1:8099/push}"

# Sources eligible for task creation (bash array — splitting via $QUEUE_SOURCES
# alone was unreliable across shell contexts).
QUEUE_SOURCES=(slack email meeting meeting_marker google-docs-comment docs-meeting drive)

ts() { date -u "+%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" | tee -a "$LOG"; }

# Load Postgres password. Prefer $POSTGRES_PASSWORD already in the env
# (the LaunchAgent plist can supply it directly, sidestepping the TCC
# issue where launchd-spawned bash cannot read /Volumes/main-drive/.env).
# Fall back to grepping .env if the env var isn't set.
if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  if [[ -r "$ENV_FILE" ]]; then
    POSTGRES_PASSWORD=$(grep ^POSTGRES_PASSWORD= "$ENV_FILE" | cut -d= -f2-)
  fi
fi
export POSTGRES_PASSWORD

if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  log "FATAL: POSTGRES_PASSWORD unavailable (env var unset and $ENV_FILE unreadable). Check LaunchAgent plist."
  exit 1
fi

# ---- (1) Find sources with unclaimed rows ----
quoted=$(printf "'%s'," "${QUEUE_SOURCES[@]}" | sed 's/,$//')
psql_query="SELECT source, COUNT(*) FROM pa_web.task_queue WHERE claimed_at IS NULL AND source IN ($quoted) GROUP BY source ORDER BY 2 DESC"

depth_report=$(PGPASSWORD="$POSTGRES_PASSWORD" psql -h localhost -p 5433 -U postgres -d postgres -At -c "$psql_query" 2>/dev/null || echo "")

if [[ -z "$depth_report" ]]; then
  log "queue empty (no unclaimed rows in task-creation sources) — nothing to do"
  exit 0
fi

total=$(echo "$depth_report" | awk -F'|' '{sum += $2} END {print sum+0}')
log "queue has $total unclaimed row(s): $(echo "$depth_report" | tr '\n' ' ')"

# ---- (2) Verify the receiver is up before issuing pushes ----
if ! curl -sf "${RECEIVER_URL%/push}/health" >/dev/null 2>&1; then
  log "WARN: letta-push-receiver health check FAILED at ${RECEIVER_URL%/push}/health — leaving rows unclaimed for next cycle"
  exit 0
fi

# ---- (3) Issue one push per source with rows. Receiver routes each
#         to the source's owner agent, which applies its own
#         per-source extraction recipe and writes pa_web.tasks. ----
pushed=0
errors=0
while IFS='|' read -r source count; do
  [[ -z "$source" ]] && continue
  prompt="[Backup poller] $count unclaimed row(s) in pa_web.task_queue source=$source. Apply your per-source extraction recipe: claim with \`task queue-claim --source $source --limit 20\`, extract per row, \`task write\` to pa_web.tasks, \`task queue-mark --status processed\`."
  body=$(printf '{"source":"%s","prompt":%s,"priority":"normal"}' "$source" "$(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$prompt")")
  status=$(curl -s -o /tmp/proc-task-q.body -w "%{http_code}" -X POST "$RECEIVER_URL" \
    -H "Content-Type: application/json" -d "$body" 2>/dev/null || echo "000")
  if [[ "$status" == "202" || "$status" == "200" ]]; then
    pushed=$((pushed + 1))
    log "  pushed source=$source rows=$count → HTTP $status"
  else
    errors=$((errors + 1))
    log "  ERROR source=$source HTTP=$status body=$(head -c 200 /tmp/proc-task-q.body 2>/dev/null)"
  fi
done <<< "$depth_report"

rm -f /tmp/proc-task-q.body

log "done: pushed=$pushed errors=$errors total_rows_signalled=$total"
