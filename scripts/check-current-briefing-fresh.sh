#!/usr/bin/env bash
# check-current-briefing-fresh.sh
#
# Freshness watchdog for signals/current/schedule.md in agents-canonical (Gitea).
# A host launchd job refreshes that cell every 15 min, 06:00–22:59 ET; this
# watchdog detects when it goes stale and emits a canonical signal on state
# transitions (no spam).
#
# State transitions:
#   ok  -> stale : emit attention=elevated signal
#   stale -> ok  : emit attention=routine  (recovery) signal
#
# Runs every 30 min via launchd (com.ai-pa.current-briefing-monitor.plist).
# Exit 0 = fresh; exit 1 = stale/error.

set -euo pipefail

ENV_FILE="${ENV_FILE:-/Volumes/main-drive/ai-PA/.env}"
LOG_DIR="${LOG_DIR:-/Volumes/main-drive/ai-PA/logs/health}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/check-current-briefing-fresh.log"
STATE_FILE="$LOG_DIR/check-current-briefing-fresh.state"

# Thresholds (mirrors check_current_freshness.py)
DAYTIME_MAX_MIN=40     # refresher runs every 15 min; allow a couple misses
OVERNIGHT_MAX_MIN=480  # refresher sleeps 23:00–06:00 ET

ts()  { date -u "+%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" | tee -a "$LOG_FILE"; }

log "--- freshness watchdog start ---"

# ---- (1) Load creds ----
GITEA_MEMFS_TOKEN=$(grep ^GITEA_MEMFS_TOKEN= "$ENV_FILE" | cut -d= -f2-)
GITEA_BASE_URL="${GITEA_BASE_URL:-http://127.0.0.1:3030}"
export GITEA_MEMFS_TOKEN GITEA_BASE_URL

# ---- (2) Fetch last commit timestamp for signals/current/schedule.md ----
FETCH_OK=true
RAW_TS=""
RAW_TS=$(curl -fsSL \
  -H "Authorization: token $GITEA_MEMFS_TOKEN" \
  "$GITEA_BASE_URL/api/v1/repos/agents/agents-canonical/commits?path=signals/current/schedule.md&limit=1" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['commit']['committer']['date'])" \
  2>>"$LOG_FILE") || FETCH_OK=false

if [[ "$FETCH_OK" != "true" || -z "$RAW_TS" ]]; then
  log "ERROR: failed to fetch or parse last commit timestamp"
  FETCH_OK=false
fi

# ---- (3) Compute age in minutes (BSD date / macOS) ----
AGE_MIN=0
if [[ "$FETCH_OK" == "true" ]]; then
  # Timestamp is like 2026-06-07T23:17:55Z (UTC, trailing Z)
  COMMIT_EPOCH=$(date -ju -f "%Y-%m-%dT%H:%M:%SZ" "$RAW_TS" +%s 2>>"$LOG_FILE") || FETCH_OK=false
  if [[ "$FETCH_OK" == "true" ]]; then
    NOW_EPOCH=$(date -u +%s)
    AGE_MIN=$(( (NOW_EPOCH - COMMIT_EPOCH) / 60 ))
  else
    log "ERROR: failed to parse timestamp: $RAW_TS"
  fi
fi

# ---- (4) Determine overnight vs daytime limit (ET hour) ----
HOUR=$(TZ=America/New_York date +%H)
if (( 10#$HOUR >= 23 || 10#$HOUR < 6 )); then
  LIMIT=$OVERNIGHT_MAX_MIN
  WINDOW="overnight"
else
  LIMIT=$DAYTIME_MAX_MIN
  WINDOW="daytime"
fi

# ---- (5) Determine new state ----
NEW_STATE="ok"
if [[ "$FETCH_OK" != "true" ]]; then
  NEW_STATE="stale"
  log "STALE (fetch/parse error)"
elif (( AGE_MIN > LIMIT )); then
  NEW_STATE="stale"
  log "STALE: age=${AGE_MIN}min limit=${LIMIT}min window=${WINDOW} last_commit=${RAW_TS}"
else
  log "OK: age=${AGE_MIN}min limit=${LIMIT}min window=${WINDOW} last_commit=${RAW_TS}"
fi

# ---- (6) Read previous state (default ok) ----
PREV_STATE=$(cat "$STATE_FILE" 2>/dev/null || echo "ok")

# ---- (7) Emit canonical signal on state transition ----
if [[ "$NEW_STATE" != "$PREV_STATE" ]]; then
  TODAY_ET=$(TZ=America/New_York date +%Y-%m-%d)

  if [[ "$NEW_STATE" == "stale" ]]; then
    # Transition: ok -> stale
    if [[ "$FETCH_OK" == "true" ]]; then
      SIGNAL_BODY="**signals/current/schedule.md is STALE** (host freshness watchdog)

- Age: ${AGE_MIN} minutes (threshold: ${LIMIT} min, window: ${WINDOW})
- Last commit: \`${RAW_TS}\`
- Cell path: \`signals/current/schedule.md\` in agents-canonical (Gitea)

The host launchd refresher (com.ai-pa.current-briefing-refresh) runs every 15 min,
06:00–22:59 ET. This alert means it has missed ≥ $(( AGE_MIN / 15 )) expected
refreshes. Check \`~/Library/Logs/current-briefing-refresh/stdout.log\` and
\`launchctl list | grep current-briefing-refresh\` for status.

Emitted by \`scripts/check-current-briefing-fresh.sh\`."
    else
      SIGNAL_BODY="**signals/current/schedule.md freshness check FAILED** (host watchdog)

- Could not fetch or parse the last commit timestamp from Gitea
- GITEA_BASE_URL: ${GITEA_BASE_URL}
- This may indicate Gitea is unreachable or the token is invalid.

Emitted by \`scripts/check-current-briefing-fresh.sh\`."
    fi
    SIGNAL_ATTENTION="elevated"
    SIGNAL_SLUG="refresh-health"
    SIGNAL_DESC="signals/current/schedule.md is stale — refresher may have stopped"

  else
    # Transition: stale -> ok (recovery)
    SIGNAL_BODY="**signals/current/schedule.md is FRESH again** (host freshness watchdog)

- Age: ${AGE_MIN} minutes (threshold: ${LIMIT} min, window: ${WINDOW})
- Last commit: \`${RAW_TS}\`

The prior stale-alert signal can be considered resolved as of this signal's
composed_at timestamp.

Emitted by \`scripts/check-current-briefing-fresh.sh\`."
    SIGNAL_ATTENTION="routine"
    SIGNAL_SLUG="refresh-health"
    SIGNAL_DESC="signals/current/schedule.md freshness recovered"
  fi

  # Emit via signal CLI (source=schedule so path is signals/<date>/schedule-refresh-health.md)
  if command -v signal >/dev/null 2>&1; then
    if echo "$SIGNAL_BODY" | signal emit \
      --slug "$SIGNAL_SLUG" \
      --source schedule \
      --date "$TODAY_ET" \
      --attention "$SIGNAL_ATTENTION" \
      --description "$SIGNAL_DESC" \
      --body-file - 2>>"$LOG_FILE"; then
      log "emitted canonical signal: signals/${TODAY_ET}/schedule-${SIGNAL_SLUG}.md  attention=${SIGNAL_ATTENTION}"
    else
      log "WARN: signal emit failed (CLI returned nonzero)"
    fi
  else
    log "WARN: signal CLI not on PATH — cannot emit transition signal"
  fi
fi

# ---- (8) Write new state ----
echo "$NEW_STATE" > "$STATE_FILE"

# ---- (9) Exit code reflects health ----
if [[ "$NEW_STATE" == "stale" ]]; then
  exit 1
fi
exit 0
