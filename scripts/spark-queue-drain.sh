#!/bin/bash
# Spark queue drain check — runs via cron, nudges tasks agent only if queue is non-empty.
# No LLM call unless there's actual work to process.
#
# Install: crontab -e → */2 * * * * /Volumes/main-drive/ai-PA/scripts/spark-queue-drain.sh
#
LETTA_BASE="http://localhost:8283"
SPARK_BLOCK="block-534bb56d-f7f1-4ea4-b2d9-20dc75eca03a"
TASKS_AGENT="agent-dd15479e-6543-400e-8463-b2a48b13cd4a"
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

TS=$(date +"%Y-%m-%d %H:%M:%S")

# Read block (cheap GET, no LLM call)
BLOCK_VAL=$(curl -s -L "$LETTA_BASE/v1/blocks/$SPARK_BLOCK" 2>/dev/null | python3 -c "
import sys, json
b = json.load(sys.stdin)
print(b.get('value', ''))
" 2>/dev/null)

if [ -z "$BLOCK_VAL" ]; then
    echo "[$TS] ERROR: empty response from block read"
    exit 1
fi

# Check if non-empty (more than just the header)
if echo "$BLOCK_VAL" | grep -q "(empty)"; then
    exit 0
fi

if [ ${#BLOCK_VAL} -lt 30 ]; then
    exit 0
fi

# Count entries
ENTRY_COUNT=$(echo "$BLOCK_VAL" | grep -c '"spark_id"')
if [ "$ENTRY_COUNT" -eq 0 ]; then
    exit 0
fi

# Check if agent is currently processing (has active runs)
ACTIVE=$(curl -s -L "$LETTA_BASE/v1/runs/?agent_id=$TASKS_AGENT&status=running&limit=1" 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)" 2>/dev/null)

if [ "$ACTIVE" != "0" ] && [ -n "$ACTIVE" ]; then
    echo "[$TS] Agent busy ($ACTIVE active runs), skipping nudge"
    exit 0
fi

# Queue is non-empty and agent is free — nudge
echo "[$TS] Nudging tasks agent: $ENTRY_COUNT spark(s) pending"

RESULT=$(curl -s -L -o /dev/null -w "%{http_code}" -X POST "$LETTA_BASE/v1/agents/$TASKS_AGENT/messages/" \
    -H "Content-Type: application/json" \
    -d "{\"messages\":[{\"role\":\"user\",\"content\":\"[Spark Queue Poll] $ENTRY_COUNT unprocessed spark(s) in your spark_queue block. Read and process each one separately using add_extracted_tasks, then clear the queue.\"}]}" \
    --max-time 120 2>/dev/null)

echo "[$TS] Agent response: HTTP $RESULT"
