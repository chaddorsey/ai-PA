#!/bin/bash
# MC Model Manager — reactive fallback and timed recovery
#
# Runs every 2 minutes via launchd.
# 1. Queries Letta runs API for recent chatgpt_oauth rate limit failures
# 2. If found and MC is on oauth → switch to LiteLLM fallback, notify user
# 3. If stored reset time has passed and MC is on fallback → switch back to oauth, notify user
# No probing. No test messages. Zero LLM cost for detection.

STATE_FILE="/Volumes/main-drive/ai-PA/omnifocus-timer/logs/mc-model-state.json"
LETTA_URL="http://localhost:8283"
MC_AGENT_ID="agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef"

# OAuth config (preferred)
OAUTH_MODEL="gpt-5.4"
OAUTH_ENDPOINT="https://chatgpt.com/backend-api/codex/responses"
OAUTH_PROVIDER="chatgpt_oauth"
OAUTH_REASONING="low"

# Fallback config
FALLBACK_MODEL="gpt-5-mini"
FALLBACK_ENDPOINT="http://litellm:4000/v1"
FALLBACK_PROVIDER="openai"

# Default rate limit window (used if we can't parse exact reset time)
DEFAULT_COOLDOWN_SECS=10800  # 3 hours

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

NOW=$(date +%s)

# Read state file
if [ -f "$STATE_FILE" ]; then
  CURRENT_MODE=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('mode','unknown'))" 2>/dev/null)
  RETRY_AFTER=$(python3 -c "import json; print(int(json.load(open('$STATE_FILE')).get('retry_after',0)))" 2>/dev/null)
else
  CURRENT_MODE="unknown"
  RETRY_AFTER=0
fi

# Check what MC is actually running
ACTUAL_PROVIDER=$(curl -sL "$LETTA_URL/v1/agents/$MC_AGENT_ID/" 2>/dev/null | python3 -c "
import sys,json
data=json.load(sys.stdin)
print(data.get('llm_config',{}).get('model_endpoint_type','unknown'))
" 2>/dev/null)

notify_user() {
  local MSG="$1"
  # Send a message through MC (now on fallback model) so user sees it in pa-web/Telegram
  curl -sL --max-time 30 -X POST "$LETTA_URL/v1/agents/$MC_AGENT_ID/messages/" \
    -H "Content-Type: application/json" \
    -d "{\"messages\":[{\"role\":\"system\",\"content\":\"[SYSTEM] $MSG\"}]}" > /dev/null 2>&1
}

switch_to_fallback() {
  local RESET_AT=$1
  local REMAINING=$(( (RESET_AT - NOW) / 60 ))
  log "FALLBACK: Switching MC to LiteLLM ($FALLBACK_MODEL). OAuth resets in ~${REMAINING}m"

  curl -sL "$LETTA_URL/v1/agents/$MC_AGENT_ID/" 2>/dev/null | python3 -c "
import sys,json,subprocess
data=json.load(sys.stdin)
llm=data['llm_config']
llm['model']='$FALLBACK_MODEL'
llm['model_endpoint_type']='$FALLBACK_PROVIDER'
llm['model_endpoint']='$FALLBACK_ENDPOINT'
llm['provider_name']='litellm'
llm['provider_category']=None
llm['handle']='litellm/$FALLBACK_MODEL'
llm['max_tokens']=32768
payload=json.dumps({'llm_config':llm})
subprocess.run(['curl','-sL','-X','PATCH','$LETTA_URL/v1/agents/$MC_AGENT_ID/','-H','Content-Type: application/json','-d',payload],capture_output=True,timeout=15)
" 2>/dev/null

  echo "{\"mode\":\"fallback\",\"switched_at\":$NOW,\"retry_after\":$RESET_AT}" > "$STATE_FILE"
  notify_user "ChatGPT rate limit hit. Switched to fallback model ($FALLBACK_MODEL) for ~${REMAINING} minutes. Will auto-recover when the limit resets."
}

switch_to_oauth() {
  log "RECOVERY: Switching MC back to chatgpt_oauth ($OAUTH_MODEL)"

  curl -sL "$LETTA_URL/v1/agents/$MC_AGENT_ID/" 2>/dev/null | python3 -c "
import sys,json,subprocess
data=json.load(sys.stdin)
llm=data['llm_config']
llm['model']='$OAUTH_MODEL'
llm['model_endpoint_type']='$OAUTH_PROVIDER'
llm['model_endpoint']='$OAUTH_ENDPOINT'
llm['provider_name']='chatgpt-plus-pro'
llm['provider_category']='byok'
llm['handle']='chatgpt-plus-pro/$OAUTH_MODEL'
llm['context_window']=272000
llm['max_tokens']=128000
llm['reasoning_effort']='$OAUTH_REASONING'
llm['strict']=True
llm['parallel_tool_calls']=True
payload=json.dumps({'llm_config':llm})
subprocess.run(['curl','-sL','-X','PATCH','$LETTA_URL/v1/agents/$MC_AGENT_ID/','-H','Content-Type: application/json','-d',payload],capture_output=True,timeout=15)
" 2>/dev/null

  echo "{\"mode\":\"oauth\",\"switched_at\":$NOW,\"retry_after\":0}" > "$STATE_FILE"
  notify_user "ChatGPT rate limit cleared. Switched back to primary model ($OAUTH_MODEL). Full capability restored."
}

# --- STEP 1: Check Letta runs API for recent rate limit failures ---
check_recent_rate_limit() {
  # Look at the last 5 runs for rate limit errors
  python3 -c "
import json, urllib.request, sys

url = '$LETTA_URL/v1/runs/?agent_id=$MC_AGENT_ID&limit=5'
data = json.loads(urllib.request.urlopen(url).read())

for run in data:
    if run.get('status') != 'failed':
        continue
    meta = run.get('metadata', {})
    err = meta.get('error', {})
    if err.get('error_type') == 'llm_rate_limit' and 'chatgpt' in err.get('detail', '').lower():
        # Found a recent chatgpt rate limit error
        # Try to get reset time from docker logs
        import subprocess
        logs = subprocess.run(
            ['docker', 'logs', 'ai-pa-letta-1', '--tail', '500'],
            capture_output=True, text=True, timeout=10
        ).stderr + subprocess.run(
            ['docker', 'logs', 'ai-pa-letta-1', '--tail', '500'],
            capture_output=True, text=True, timeout=10
        ).stdout

        import re
        # Look for x-codex-primary-reset-at epoch
        matches = re.findall(r\"x-codex-primary-reset-at.*?b'(\d+)'\", logs)
        if matches:
            reset_at = int(matches[-1])
            print(f'RATE_LIMITED {reset_at}')
        else:
            # Use default cooldown from the run's timestamp
            import datetime
            completed = run.get('completed_at', '')[:19]
            try:
                dt = datetime.datetime.fromisoformat(completed)
                epoch = int(dt.timestamp())
                print(f'RATE_LIMITED {epoch + $DEFAULT_COOLDOWN_SECS}')
            except:
                print(f'RATE_LIMITED {int($(date +%s)) + $DEFAULT_COOLDOWN_SECS}')
        sys.exit(0)

print('OK')
" 2>/dev/null
}

# --- STEP 2: Decide what to do ---

if [ "$ACTUAL_PROVIDER" = "$OAUTH_PROVIDER" ] || [ "$ACTUAL_PROVIDER" = "chatgpt_oauth" ]; then
  # MC is on oauth — check for recent rate limit failures
  RESULT=$(check_recent_rate_limit)
  if echo "$RESULT" | grep -q "RATE_LIMITED"; then
    RESET_AT=$(echo "$RESULT" | grep -o "[0-9]*$")
    if [ -n "$RESET_AT" ] && [ "$RESET_AT" -gt "$NOW" ] 2>/dev/null; then
      switch_to_fallback "$RESET_AT"
    else
      log "OK: MC on oauth, rate limit detected but reset time has passed"
    fi
  else
    log "OK: MC on oauth, no rate limit detected"
    echo "{\"mode\":\"oauth\",\"switched_at\":$NOW,\"retry_after\":0}" > "$STATE_FILE"
  fi

elif [ "$ACTUAL_PROVIDER" = "$FALLBACK_PROVIDER" ] || [ "$ACTUAL_PROVIDER" = "openai" ]; then
  # MC is on fallback — check if oauth is available again (but don't auto-switch)
  if [ "$RETRY_AFTER" -gt 0 ] && [ "$NOW" -lt "$RETRY_AFTER" ]; then
    REMAINING=$(( (RETRY_AFTER - NOW) / 60 ))
    log "WAITING: MC on fallback, oauth resets in ${REMAINING}m"
  else
    # OAuth is available but don't auto-switch — let the user decide
    log "READY: OAuth available, MC still on fallback (user controls switch)"
    echo "{\"mode\":\"fallback\",\"oauth_available\":true,\"switched_at\":$NOW,\"retry_after\":0}" > "$STATE_FILE"
  fi

else
  log "UNKNOWN: MC on '$ACTUAL_PROVIDER' — switching to oauth"
  switch_to_oauth
fi
