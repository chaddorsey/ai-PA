#!/usr/bin/env bash
#
# Monitor the running Slack analytics backfill and run retries until complete.
#
# This script:
#   1. Waits for the initial backfill (b58f48e) to finish
#   2. Checks how many dates still have null Slack data
#   3. Runs retry passes (channels-only, then members-only) for missing dates
#   4. Repeats until all dates are filled or max retries reached
#
# Usage:
#   bash scripts/slack-backfill-monitor.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKFILL_SCRIPT="$PROJECT_DIR/scripts/backfill-slack-analytics.py"
LOG_DIR="/tmp/slack-backfill-logs"
MAX_RETRY_ROUNDS=3

# Load env
set -a
source "$PROJECT_DIR/.env" 2>/dev/null || true
set +a

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

check_null_slack_count() {
    python3 -c "
import urllib.request, json, os
url = os.getenv('SUPABASE_REST_URL', 'http://localhost:8000')
key = os.getenv('SUPABASE_SERVICE_KEY', '')
req = urllib.request.Request(
    f'{url}/daily_snapshots?select=snapshot_date&slack_total_messages=is.null&order=snapshot_date.asc',
    headers={'apikey': key, 'Authorization': f'Bearer {key}', 'Accept-Profile': 'analytics'}
)
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read().decode('utf-8'))
print(len(data))
"
}

check_total_snapshots() {
    python3 -c "
import urllib.request, json, os
url = os.getenv('SUPABASE_REST_URL', 'http://localhost:8000')
key = os.getenv('SUPABASE_SERVICE_KEY', '')
req = urllib.request.Request(
    f'{url}/daily_snapshots?select=snapshot_date',
    headers={'apikey': key, 'Authorization': f'Bearer {key}', 'Accept-Profile': 'analytics',
             'Prefer': 'count=exact', 'Range-Unit': 'items', 'Range': '0-0'}
)
with urllib.request.urlopen(req, timeout=30) as resp:
    cr = resp.headers.get('Content-Range', '*/0')
    total = cr.split('/')[-1]
    print(total)
"
}

# --- Phase 1: Wait for the initial backfill to finish ---
INITIAL_PID_FILE="/private/tmp/claude-501/-Volumes-main-drive-ai-PA/tasks/b58f48e.output"
if [ -f "$INITIAL_PID_FILE" ]; then
    log "Waiting for initial backfill to complete..."
    while true; do
        if grep -q "Backfill Complete" "$INITIAL_PID_FILE" 2>/dev/null; then
            log "Initial backfill completed!"
            grep "Backfill Complete" "$INITIAL_PID_FILE"
            break
        fi
        # Show progress
        last_line=$(tail -1 "$INITIAL_PID_FILE" 2>/dev/null || echo "")
        log "Still running... $last_line"
        sleep 120
    done
else
    log "No initial backfill output found, starting fresh."
fi

# --- Phase 2: Check status and run retries ---
for round in $(seq 1 $MAX_RETRY_ROUNDS); do
    null_count=$(check_null_slack_count)
    total=$(check_total_snapshots)
    log "Round $round/$MAX_RETRY_ROUNDS: $null_count dates with null Slack data (out of $total total)"

    if [ "$null_count" -eq 0 ]; then
        log "All dates have Slack data! Backfill complete."
        exit 0
    fi

    # Run channels retry for dates with null slack data
    log "Running channels retry pass ($null_count dates)..."
    CHANNELS_LOG="$LOG_DIR/retry-channels-round${round}.log"
    python3 "$BACKFILL_SCRIPT" --existing-only 2>&1 | tee "$CHANNELS_LOG"

    # Check remaining
    null_count=$(check_null_slack_count)
    log "After round $round: $null_count dates still need Slack data"

    if [ "$null_count" -eq 0 ]; then
        log "All dates have Slack data! Backfill complete."
        exit 0
    fi

    # Run members-only retry for dates that got channels but not members
    log "Running members-only retry pass..."
    MEMBERS_LOG="$LOG_DIR/retry-members-round${round}.log"
    python3 "$BACKFILL_SCRIPT" --existing-only --members-only 2>&1 | tee "$MEMBERS_LOG"

    null_count=$(check_null_slack_count)
    log "After round $round (both passes): $null_count dates still need Slack data"
done

# --- Final status ---
null_count=$(check_null_slack_count)
total=$(check_total_snapshots)
log "Final status: $null_count/$total dates with null Slack data"
if [ "$null_count" -gt 0 ]; then
    log "Some dates still missing. You can run manually:"
    log "  python3 scripts/backfill-slack-analytics.py --existing-only"
fi
