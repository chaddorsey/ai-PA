#!/bin/bash
# Integration test for letta-duplicate-block.sh
#
# Exercises:
#  - Duplicate a source block (no target agent) — produces unattached block with same content
#  - Duplicate to a target agent — attaches and is queryable
#  - Idempotence — re-running with same target+label skips creation, returns existing id
#  - Refusal — Class-B shared queue blocks (R20) are rejected with exit 2
#  - Edit isolation — modifying the duplicate doesn't touch the source
#
# Self-cleanup via trap: removes any blocks/agents created during the test.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LETTA_BASE_URL="${LETTA_BASE_URL:-http://localhost:8283}"
HELPER="$REPO_ROOT/scripts/letta-duplicate-block.sh"
RUN_ID="${RANDOM}-${RANDOM}"  # unique per-run, no shell-quoting hazards

# Use Class-B forbidden block (extracted_tasks) as the refusal-test source — guaranteed to exist.
FORBIDDEN_BLOCK="block-90300b77-6b72-42cb-8e67-c74fbb497cf6"

# Track created resources for cleanup
CREATED_BLOCKS=()
CREATED_AGENTS=()

cleanup() {
  for aid in "${CREATED_AGENTS[@]:-}"; do
    [ -n "$aid" ] && curl -s -L -X DELETE "$LETTA_BASE_URL/v1/agents/$aid" -o /dev/null || true
  done
  for bid in "${CREATED_BLOCKS[@]:-}"; do
    [ -n "$bid" ] && curl -s -L -X DELETE "$LETTA_BASE_URL/v1/blocks/$bid" -o /dev/null || true
  done
}
trap cleanup EXIT

echo "[test] Setup: create source block + target agent"
SRC_PAYLOAD=$(python3 -c "import json; print(json.dumps({'value':'DUPLICATE-TEST-SOURCE-payload','label':'test-dup-source-$RUN_ID','description':'test source','limit':4000}))")
SRC_RESP=$(curl -s -L -X POST "$LETTA_BASE_URL/v1/blocks/" \
  -H "Content-Type: application/json" -d "$SRC_PAYLOAD")
SRC_BLOCK_ID=$(echo "$SRC_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))")
[ -z "$SRC_BLOCK_ID" ] && { echo "FAIL: src block create"; exit 1; }
CREATED_BLOCKS+=("$SRC_BLOCK_ID")
echo "[test]    src block: $SRC_BLOCK_ID"

TGT_PAYLOAD=$(python3 -c "import json; print(json.dumps({'name':'dup-test-target-$RUN_ID','memory_blocks':[{'label':'persona','value':'target'}],'model':'openai-proxy/gpt-4.1-mini/rover','embedding':'letta/letta-free'}))")
TGT_RESP=$(curl -s -L -X POST "$LETTA_BASE_URL/v1/agents/" \
  -H "Content-Type: application/json" -d "$TGT_PAYLOAD")
TGT_AGENT_ID=$(echo "$TGT_RESP" | python3 -c "import json,sys; d=json.loads(sys.stdin.read(),strict=False); print(d.get('id',''))")
[ -z "$TGT_AGENT_ID" ] && { echo "FAIL: tgt agent create"; exit 1; }
CREATED_AGENTS+=("$TGT_AGENT_ID")
echo "[test]    tgt agent: $TGT_AGENT_ID"

echo "[test] 1. Duplicate (no target) — produces unattached block"
NEW_BID_1=$("$HELPER" "$SRC_BLOCK_ID" 2>/dev/null)
[ -z "$NEW_BID_1" ] && { echo "FAIL: duplicate produced no id"; exit 1; }
[ "$NEW_BID_1" = "$SRC_BLOCK_ID" ] && { echo "FAIL: dup id == src id (should differ)"; exit 1; }
CREATED_BLOCKS+=("$NEW_BID_1")
echo "[test]    new block: $NEW_BID_1 (≠ src)"

# Verify content matches
NEW_VAL=$(curl -s -L "$LETTA_BASE_URL/v1/blocks/$NEW_BID_1" | python3 -c "import json,sys; print(json.load(sys.stdin).get('value',''))")
[ "$NEW_VAL" = "DUPLICATE-TEST-SOURCE-payload" ] || { echo "FAIL: content not preserved (got '$NEW_VAL')"; exit 1; }
echo "[test]    content preserved"

echo "[test] 2. Duplicate to target agent (with --label override)"
NEW_BID_2=$("$HELPER" "$SRC_BLOCK_ID" "$TGT_AGENT_ID" --label "dup-test-attached-${RUN_ID}" 2>/dev/null)
CREATED_BLOCKS+=("$NEW_BID_2")
ATTACHED=$(curl -s -L "$LETTA_BASE_URL/v1/agents/$TGT_AGENT_ID/core-memory/blocks" \
  | python3 -c "import json,sys; d=json.loads(sys.stdin.read(),strict=False); blocks=d if isinstance(d,list) else []; print('YES' if any(b.get('id')=='$NEW_BID_2' for b in blocks) else 'NO')")
[ "$ATTACHED" = "YES" ] || { echo "FAIL: dup not attached to target"; exit 1; }
echo "[test]    attached to target"

echo "[test] 3. Idempotence — re-run with same target+label returns same id (no duplicate)"
NEW_BID_2B=$("$HELPER" "$SRC_BLOCK_ID" "$TGT_AGENT_ID" --label "dup-test-attached-${RUN_ID}" 2>/dev/null)
[ "$NEW_BID_2B" = "$NEW_BID_2" ] || { echo "FAIL: idempotent re-run produced different id ($NEW_BID_2B vs $NEW_BID_2)"; exit 1; }
echo "[test]    idempotent (same id returned)"

echo "[test] 4. Edit isolation — modifying dup doesn't touch source"
curl -s -L -X PATCH "$LETTA_BASE_URL/v1/blocks/$NEW_BID_1" \
  -H "Content-Type: application/json" \
  -d '{"value":"DUP-MUTATED"}' -o /dev/null
SRC_AFTER=$(curl -s -L "$LETTA_BASE_URL/v1/blocks/$SRC_BLOCK_ID" | python3 -c "import json,sys; print(json.load(sys.stdin).get('value',''))")
[ "$SRC_AFTER" = "DUPLICATE-TEST-SOURCE-payload" ] || { echo "FAIL: source mutated when dup edited (got '$SRC_AFTER')"; exit 1; }
echo "[test]    source unchanged after dup edit"

echo "[test] 5. Refusal — Class-B forbidden block exits 2"
set +e
"$HELPER" "$FORBIDDEN_BLOCK" "$TGT_AGENT_ID" 2>/dev/null
RC=$?
set -e
[ "$RC" = "2" ] || { echo "FAIL: expected exit 2 for forbidden block, got $RC"; exit 1; }
echo "[test]    forbidden block correctly refused (exit 2)"

echo "[test] PASS — all 5 duplicate-block scenarios"
