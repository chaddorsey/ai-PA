#!/usr/bin/env bash
# backfill-slack-analytics.sh
#
# One-shot backfill of the slack-analytics CSV exports for a date range,
# matching the daily-cron pattern (1-day windows). Each call triggers a
# CSV that Slack DMs to the workspace admin user.
#
# Usage:
#   scripts/backfill-slack-analytics.sh 2026-05-17 2026-05-30
#
# Default range covers the 2026-05-17 → 2026-05-30 outage window.

set -euo pipefail

START="${1:-2026-05-17}"
END="${2:-2026-05-30}"
TRIGGER_URL="${TRIGGER_URL:-http://localhost:8097/trigger-export}"
SLEEP_BETWEEN="${SLEEP_BETWEEN:-3}"  # be polite to Slack
LOG_DIR="${LOG_DIR:-/Volumes/main-drive/ai-PA/logs/health}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/backfill-$(date +%Y%m%d-%H%M%S).log"

ts() { date -u "+%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" | tee -a "$LOG"; }

log "Backfill: $START → $END  (1-day windows, channels+members each)"

# Build inclusive list of dates START..END
day="$START"
total_ok=0
total_fail=0
day_count=0

while [[ "$day" < "$END" ]] || [[ "$day" == "$END" ]]; do
  next=$(date -j -v+1d -f "%Y-%m-%d" "$day" "+%Y-%m-%d")
  day_count=$((day_count + 1))

  for kind in channels members; do
    log "  → triggering $kind  $day → $next"
    resp=$(curl -s -X POST "$TRIGGER_URL" \
      -H 'Content-Type: application/json' \
      -d "{\"analytics_type\":\"$kind\",\"start_date\":\"$day\",\"end_date\":\"$next\"}" \
      --max-time 90 || echo '{"error":"curl-failed"}')

    ok=$(echo "$resp" | python3 -c 'import json,sys
try:
    r = json.load(sys.stdin)
    d = r.get("detail", r)
    print(bool(d.get("success")))
except Exception:
    print(False)' 2>/dev/null)

    if [[ "$ok" == "True" ]]; then
      total_ok=$((total_ok + 1))
      log "    ✓ ok"
    else
      total_fail=$((total_fail + 1))
      err=$(echo "$resp" | python3 -c 'import json,sys
try:
    r = json.load(sys.stdin)
    d = r.get("detail", r)
    out = d.get("stdout","")[-300:]
    err = d.get("stderr","")[-300:]
    print(f"stdout={out[-200:]} | stderr={err[-200:]}")
except Exception as e:
    print(f"parse-error: {e}")' 2>/dev/null)
      log "    ✗ FAIL  $err"
    fi
    sleep "$SLEEP_BETWEEN"
  done

  day="$next"
done

log "Done. ${total_ok}/$((total_ok+total_fail)) exports succeeded across $day_count days."

if [[ "$total_fail" -gt 0 ]]; then
  exit 1
fi
