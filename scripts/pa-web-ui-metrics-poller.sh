#!/bin/bash
# pa-web-ui metrics poller — runs once per invocation, appends a CSV row.
#
# Designed to run on a 5-minute cron during soak windows. Captures:
#   - timestamp
#   - subprocess pool size + handles count
#   - error count from docker logs since last invocation
#   - HEAD /health latency (wall-clock ms)
#   - sidebar fetch latency (HEAD /api/tasks)
#   - container memory (MB)
#   - container CPU%
#
# Output: appends one CSV row to $METRICS_CSV (default /tmp/pa-web-ui-metrics.csv).
# Header is written if the file doesn't exist.
#
# Usage:
#   ./scripts/pa-web-ui-metrics-poller.sh            # one-shot, append to default CSV
#   METRICS_CSV=/tmp/foo.csv ./scripts/...           # custom output
#
# Cron example (every 5 min):
#   */5 * * * * /Volumes/main-drive/ai-PA/scripts/pa-web-ui-metrics-poller.sh >>/tmp/pa-web-ui-metrics-cron.log 2>&1

set -uo pipefail   # not -e: we want to continue on individual failures and write a partial row

METRICS_CSV="${METRICS_CSV:-/tmp/pa-web-ui-metrics.csv}"
WINDOW_MIN="${WINDOW_MIN:-5}"   # log-error window in minutes

NOW_ISO="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# Health latency (ms)
HEALTH_MS=$(curl -s -o /dev/null -w "%{time_total}" --max-time 5 "http://localhost:5200/health" 2>/dev/null \
  | awk '{printf "%.0f", $1 * 1000}')
HEALTH_MS="${HEALTH_MS:-NA}"

# Subprocess pool size (handles count)
POOL_HANDLES=$(curl -s --max-time 5 "http://localhost:5200/api/subprocess/status" 2>/dev/null \
  | python3 -c "
import json,sys
try:
    d=json.loads(sys.stdin.read())
    handles=d.get('handles',[]) or []
    print(len(handles) if isinstance(handles,list) else 0)
except Exception:
    print('NA')
" 2>/dev/null)
POOL_HANDLES="${POOL_HANDLES:-NA}"

# Tasks fetch latency (sidebar polls this every 30s)
TASKS_MS=$(curl -s -o /dev/null -w "%{time_total}" --max-time 5 "http://localhost:5200/api/tasks" 2>/dev/null \
  | awk '{printf "%.0f", $1 * 1000}')
TASKS_MS="${TASKS_MS:-NA}"

# Errors in docker logs since the window began
ERR_COUNT=$(docker logs pa-web-ui --since "${WINDOW_MIN}m" 2>&1 \
  | grep -ciE "error|exception|traceback|critical" || echo 0)

# Container memory + CPU
STATS=$(docker stats pa-web-ui --no-stream --format "{{.MemUsage}}|{{.CPUPerc}}" 2>/dev/null || echo "NA|NA")
MEM_RAW="$(echo "$STATS" | cut -d'|' -f1 | awk '{print $1}')"   # e.g. "36.3MiB"
CPU_RAW="$(echo "$STATS" | cut -d'|' -f2)"                      # e.g. "0.03%"
# Strip units: keep numeric only
MEM_MB="$(echo "$MEM_RAW" | sed 's/MiB//;s/MB//;s/B//' || echo NA)"
CPU_PCT="$(echo "$CPU_RAW" | sed 's/%//' || echo NA)"

# Letta-code subprocess uptime (longest-lived subprocess)
LETTA_CODE_AGE=$(docker exec pa-web-ui sh -c 'ps -eo etimes,comm 2>/dev/null | grep -E " node$" | sort -rn | head -1 | awk "{print \$1}"' 2>/dev/null || echo "NA")
LETTA_CODE_AGE="${LETTA_CODE_AGE:-NA}"

# Container restart count (docker inspect)
RESTART_COUNT=$(docker inspect pa-web-ui --format '{{.RestartCount}}' 2>/dev/null || echo NA)

# Write header if first run
if [ ! -f "$METRICS_CSV" ]; then
  echo "timestamp_utc,health_ms,pool_handles,tasks_ms,err_count_${WINDOW_MIN}m,mem_mb,cpu_pct,letta_code_age_s,restart_count" > "$METRICS_CSV"
fi

echo "$NOW_ISO,$HEALTH_MS,$POOL_HANDLES,$TASKS_MS,$ERR_COUNT,$MEM_MB,$CPU_PCT,$LETTA_CODE_AGE,$RESTART_COUNT" >> "$METRICS_CSV"

# Brief stdout summary so cron-tail is informative
echo "[metrics] $NOW_ISO health=${HEALTH_MS}ms pool=$POOL_HANDLES tasks=${TASKS_MS}ms err=${ERR_COUNT}/${WINDOW_MIN}m mem=${MEM_MB}MiB cpu=${CPU_PCT}% age=${LETTA_CODE_AGE}s restarts=$RESTART_COUNT"
