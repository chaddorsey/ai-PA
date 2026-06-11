#!/usr/bin/env bash
# run-analytics-stage.sh — local driver for the daily analytics pipeline.
# Replaces the Docker pulse-agent agent_message scheduler jobs (dead since
# 2026-05-31) with host-local pulse CLI + local-pulse-agent invocations.
# Usage: run-analytics-stage.sh <export|snapshot|vibe|recollect|compose|mentions>
set -uo pipefail

STAGE="${1:?usage: run-analytics-stage.sh <export|snapshot|vibe|recollect|compose|mentions>}"
export HOME="${HOME:-/Users/dorseyhomeserver}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONPATH="$HOME/.letta/lc-local-backend/tool-deps"
set -a; . "$HOME/.letta/pa-tools.env" 2>/dev/null; set +a

LOG_DIR="$HOME/Library/Logs/analytics-pipeline"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/${STAGE}.log"
ts(){ date -u "+%Y-%m-%dT%H:%M:%SZ"; }
log(){ echo "[$(ts)] $*" | tee -a "$LOG"; }

AGENT="agent-local-d48b128a-b3a8-4930-a27f-b4127c96fe3a"
RUNNER="http://127.0.0.1:8920/invoke"

invoke_agent(){ # $1=message $2=timeout
  python3 - "$AGENT" "$RUNNER" "$1" "$2" <<'PY'
import json,sys,urllib.request
aid,url,msg,to=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4])
req=urllib.request.Request(url,data=json.dumps({"agent_id":aid,"message":msg,"timeout":to}).encode(),
    headers={"Content-Type":"application/json"},method="POST")
r=json.load(urllib.request.urlopen(req,timeout=to+20))
print("runner_status:",r.get("status"),"exit:",r.get("letta_exit"),"dur:",r.get("duration_seconds"))
print((r.get("agent_response") or "")[:400])
PY
}

log "stage=$STAGE start"
rc=0
case "$STAGE" in
  export)
    pulse slack-trigger --analytics-type channels 2>&1 | tee -a "$LOG" || rc=$?
    pulse slack-trigger --analytics-type members  2>&1 | tee -a "$LOG" || rc=$?
    ;;
  snapshot|recollect)
    pulse snapshot 2>&1 | tee -a "$LOG" || rc=$?
    ;;
  compose)
    pulse compose-briefing 2>&1 | tee -a "$LOG" || rc=$?
    # Materialize a stable date-less cell so MC reads signals/current/analytics-morning.md
    # (like signals/current/schedule.md) instead of guessing the data-lagged date.
    python3 /Volumes/main-drive/ai-PA/scripts/materialize-current-signal.py analytics 2>&1 | tee -a "$LOG" || true
    ;;
  vibe)
    invoke_agent "Generate the daily Slack vibe check for yesterday (ET) across the top channels. After summarizing each channel, write the per-channel and combined summary to your memfs at system/daily_vibe_check_<YYYY-MM-DD>.md using yesterday's ET date. Then reply DONE." 600 2>&1 | tee -a "$LOG" || rc=$?
    # Materialize signals/current/slack-vibe.md from the latest vibe so MC can surface it.
    python3 /Volumes/main-drive/ai-PA/scripts/materialize-current-signal.py vibe 2>&1 | tee -a "$LOG" || true
    ;;
  mentions)
    invoke_agent "Intra-day mentions refresh (rolling 48h, today+yesterday ET): find @-mentions directed AT Chad in DMs and channels, update your stored mentions view. Reply DONE." 400 2>&1 | tee -a "$LOG" || rc=$?
    ;;
  *) log "unknown stage: $STAGE"; exit 2 ;;
esac
log "stage=$STAGE done rc=$rc"
exit $rc
