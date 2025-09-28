#!/usr/bin/env bash
set -euo pipefail

MCP_ENDPOINT="http://localhost:8888/mcp"
PAYLOAD='{"jsonrpc":"2.0","id":"smoke","method":"tools/call","params":{"name":"listRemaining","arguments":{}}}'

response=$(curl -s "$MCP_ENDPOINT" -H "Content-Type: application/json" -d "$PAYLOAD")

text=$(echo "$response" | jq -r '.result.content[0].text')

parsed=$(JSON_TEXT="$text" python3 - <<'PY'
import json
import os

text = os.environ["JSON_TEXT"]

obj = json.loads(text)
while isinstance(obj, str):
    obj = json.loads(obj)

print(json.dumps(obj))
PY
)

items=$(echo "$parsed" | jq '.result')

if [ -z "$items" ] || [ "$items" = "null" ]; then
  echo "❌ listRemaining returned no result set"
  exit 1
fi

missing=$(echo "$parsed" | jq '[.result[] | select((has("added") | not) or (has("modified") | not) or (has("plannedDate") | not) or (has("effectivePlannedDate") | not))] | length')

if [ "$missing" -ne 0 ]; then
  echo "❌ Detected $missing tasks missing required timestamp/planned date fields"
  exit 1
fi

echo "✅ Timestamp/planned date smoke test passed"
