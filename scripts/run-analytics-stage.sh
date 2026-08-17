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

# 2026-08-17 runner migration (docs/plans/2026-08-17-010): agent stages ride the
# sole-owner App Server's /v1/responses (the enrichment path) instead of the retired
# letta-local-runner. Same semantics: fresh conversation per call, memfs is the durable
# memory. /v1/responses targets agents by FRIENDLY model name, not agent-local-* id.
MODEL="pulse-monitor-agent-local"
APP_SERVER="http://127.0.0.1:4577/v1/responses"

invoke_agent(){ # $1=message $2=timeout
  python3 - "$MODEL" "$APP_SERVER" "$1" "$2" <<'PY'
import json,sys,time,urllib.request
model,url,msg,to=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4])
req=urllib.request.Request(url,data=json.dumps({"model":model,"input":msg}).encode(),
    headers={"Content-Type":"application/json"},method="POST")
t0=time.time()
r=json.load(urllib.request.urlopen(req,timeout=to+20))
text=""
for item in r.get("output",[]):
    if item.get("type")=="message" and item.get("content"):
        text=item["content"][0].get("text","")
print("app_server_status:",r.get("status","?"),"dur:",round(time.time()-t0,1))
print((text or "")[:400])
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
    invoke_agent "Intra-day mentions refresh (rolling 48h, today+yesterday ET): find @-mentions directed AT Chad in DMs and channels. Then REPLACE the entire contents of system/slack_mentions_view.md with a SINGLE current rolling-48h snapshot: keep the frontmatter, write one up-to-date section, and do NOT append/prepend a new dated section or retain any prior refresh sections. The file must contain exactly one current snapshot (this keeps the file small so every turn stays fast/cheap). Reply DONE." 400 2>&1 | tee -a "$LOG" || rc=$?
    ;;
  *) log "unknown stage: $STAGE"; exit 2 ;;
esac
log "stage=$STAGE done rc=$rc"
exit $rc
