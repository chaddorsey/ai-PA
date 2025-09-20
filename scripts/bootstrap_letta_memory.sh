#!/usr/bin/env bash
set -euo pipefail

LETTABASE="${LETTABASE:-http://localhost:8283}"
AGENT_NAME="${AGENT_NAME:-chad-gemini}"

# 1) find or create agent id
AGENT_ID=$(curl -sS "$LETTABASE/v1/agents/?name=$AGENT_NAME" | jq -r '.[0].id // empty')
if [ -z "$AGENT_ID" ]; then
  echo "Agent $AGENT_NAME not found; please create it via your existing flow."
  exit 1
fi

# 2) ensure core_memory block exists
BLOCK_ID=$(curl -sS "$LETTABASE/v1/blocks/?label=core_memory" | jq -r '.[0].id // empty')
if [ -z "$BLOCK_ID" ]; then
  BLOCK_ID=$(curl -sS -X POST "$LETTABASE/v1/blocks/" \
    -H "Content-Type: application/json" \
    -d '{"label":"core_memory","description":"Long-term facts about the user and durable context.","limit":12000,"value":""}' \
    | jq -r '.id')
fi

# 3) attach if not already
ATTACHED=$(curl -sS "$LETTABASE/v1/agents/$AGENT_ID/core-memory" | jq -r --arg BID "$BLOCK_ID" '.blocks[].id == $BID' | grep -q true && echo yes || echo no)
if [ "$ATTACHED" != "yes" ]; then
  curl -sS -X PATCH "$LETTABASE/v1/agents/$AGENT_ID/core-memory/blocks/attach/$BLOCK_ID" \
    -H "Content-Type: application/json" -d '' >/dev/null
  echo "Attached core_memory to $AGENT_ID"
else
  echo "core_memory already attached"
fi
