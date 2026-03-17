#!/bin/bash
# MC Model Manager — reactive fallback and timed recovery
#
# Runs every 2 minutes via launchd.
# 1. Scans Letta logs for recent chatgpt_oauth 429s
# 2. If found and MC is on oauth → extract reset time, switch to LiteLLM fallback
# 3. If reset time has passed and MC is on fallback → switch back to oauth
# No probing. No test messages. Zero LLM cost.

STATE_FILE="/tmp/mc-model-state.json"
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

switch_to_fallback() {
  local RESET_AT=$1
  log "FALLBACK: Switching MC to LiteLLM ($FALLBACK_MODEL). OAuth resets at $(date -r $RESET_AT '+%Y-%m-%d %H:%M:%S')"

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
payload=json.dumps({'llm_config':llm})
subprocess.run(['curl','-sL','-X','PATCH','$LETTA_URL/v1/agents/$MC_AGENT_ID/','-H','Content-Type: application/json','-d',payload],capture_output=True,timeout=15)
" 2>/dev/null

  echo "{\"mode\":\"fallback\",\"switched_at\":$NOW,\"retry_after\":$RESET_AT}" > "$STATE_FILE"
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
}

# --- STEP 1: Scan Letta logs for recent 429s with reset info ---
# Look for x-codex-primary-reset-at in the last 200 lines of logs
RESET_AT_EPOCH=$(docker logs ai-pa-letta-1 --tail 200 2>&1 | \
  grep -o "x-codex-primary-reset-at.*b'[0-9]*'" | \
  tail -1 | \
  grep -o "[0-9]*" | \
  head -1)

# Also check for the 429 itself to confirm it's recent
RECENT_429=$(docker logs ai-pa-letta-1 --tail 200 2>&1 | \
  grep "429.*Too Many Requests.*chatgpt.com" | \
  tail -1)

# --- STEP 2: Decide what to do ---

if [ "$ACTUAL_PROVIDER" = "$OAUTH_PROVIDER" ] || [ "$ACTUAL_PROVIDER" = "chatgpt_oauth" ]; then
  # MC is on oauth
  if [ -n "$RECENT_429" ] && [ -n "$RESET_AT_EPOCH" ] && [ "$RESET_AT_EPOCH" -gt "$NOW" ] 2>/dev/null; then
    # Rate limited! Switch to fallback.
    switch_to_fallback "$RESET_AT_EPOCH"
  else
    log "OK: MC on oauth, no rate limit detected"
    echo "{\"mode\":\"oauth\",\"switched_at\":$NOW,\"retry_after\":0}" > "$STATE_FILE"
  fi

elif [ "$ACTUAL_PROVIDER" = "$FALLBACK_PROVIDER" ] || [ "$ACTUAL_PROVIDER" = "openai" ]; then
  # MC is on fallback
  if [ "$RETRY_AFTER" -gt 0 ] && [ "$NOW" -lt "$RETRY_AFTER" ]; then
    REMAINING=$((RETRY_AFTER - NOW))
    MINS=$((REMAINING / 60))
    log "WAITING: MC on fallback, oauth resets in ${MINS}m ($(date -r $RETRY_AFTER '+%H:%M:%S'))"
  else
    # Retry time has passed (or was never set) — switch back
    switch_to_oauth
  fi

else
  log "UNKNOWN: MC on '$ACTUAL_PROVIDER' — switching to oauth"
  switch_to_oauth
fi
