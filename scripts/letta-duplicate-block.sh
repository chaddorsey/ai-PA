#!/bin/bash
# Duplicate a Letta memory block (copy-by-value) and optionally attach to a target agent.
#
# Used during Phase 4 canary work to seed disposable test agents with realistic
# block content drawn from production agents — without coupling the canary's edits
# to production state.
#
# Why copy-by-value not attach: attaching shares the same block-ID across agents,
# so canary edits would mutate the production block. Duplication creates a fresh
# block_id with the same value/label/description, fully isolated.
#
# Hard-coded refusal of the six Class-B shared queue blocks (R20 in the migration
# plan) — these are external-writer IPC, not memory worth duplicating.
#
# Usage:
#   ./scripts/letta-duplicate-block.sh <SOURCE_BLOCK_ID> [TARGET_AGENT_ID] [--label NEW_LABEL]
#
# Arguments:
#   SOURCE_BLOCK_ID  — block to copy from (block-...)
#   TARGET_AGENT_ID  — if given, attach the new block to this agent (agent-...)
#   --label NEW_LABEL — override the new block's label (default: source's label)
#
# Output: the new block_id on stdout (so callers can capture it).
# Exit 0 on success, non-zero on any failure.

set -euo pipefail

LETTA_BASE_URL="${LETTA_BASE_URL:-http://localhost:8283}"

# Class-B shared queue blocks (R20) — refuse to duplicate these
FORBIDDEN_BLOCK_IDS=(
  "block-e64dcb37-aae3-416f-8565-5f2a23f53325"  # queued_tasks_from_email
  "block-033a720d-1f13-44a2-a5cb-b5edde418ea1"  # queued_tasks_from_slack
  "block-809efd9b-e2ca-4d11-af89-9a1c7710716c"  # queued_tasks_from_meetings
  "block-cfbba10b-5796-408d-8540-72a7b31bcb97"  # queued_tasks_from_drive
  "block-534bb56d-f7f1-4ea4-b2d9-20dc75eca03a"  # SPARK queue
  "block-90300b77-6b72-42cb-8e67-c74fbb497cf6"  # extracted_tasks
)

if [ $# -lt 1 ]; then
  echo "Usage: $0 <SOURCE_BLOCK_ID> [TARGET_AGENT_ID] [--label NEW_LABEL]" >&2
  exit 1
fi

SOURCE_BLOCK_ID="$1"
shift
TARGET_AGENT_ID=""
NEW_LABEL=""

while [ $# -gt 0 ]; do
  case "$1" in
    --label)
      NEW_LABEL="$2"
      shift 2
      ;;
    --label=*)
      NEW_LABEL="${1#--label=}"
      shift
      ;;
    -*)
      echo "Unknown flag: $1" >&2
      exit 1
      ;;
    *)
      if [ -z "$TARGET_AGENT_ID" ]; then
        TARGET_AGENT_ID="$1"
      else
        echo "Unexpected arg: $1" >&2
        exit 1
      fi
      shift
      ;;
  esac
done

# Refuse Class-B shared queue blocks
for forbidden in "${FORBIDDEN_BLOCK_IDS[@]}"; do
  if [ "$SOURCE_BLOCK_ID" = "$forbidden" ]; then
    echo "[duplicate-block] REFUSED: $SOURCE_BLOCK_ID is a Class-B shared queue block (R20). " >&2
    echo "[duplicate-block]          These are external-writer IPC, not memory state — duplicating " >&2
    echo "[duplicate-block]          them onto a canary would create misleading test conditions." >&2
    echo "[duplicate-block]          See docs/plans/2026-04-24-001-feat-letta-memfs-upgrade-plan.md R20." >&2
    exit 2
  fi
done

# Fetch source block
SRC_JSON=$(curl -sS -L "$LETTA_BASE_URL/v1/blocks/$SOURCE_BLOCK_ID")
HAS_ERR=$(echo "$SRC_JSON" | python3 -c "import json,sys; d=json.loads(sys.stdin.read(),strict=False); print(d.get('detail') or '')" 2>/dev/null || echo "parse-fail")
if [ -n "$HAS_ERR" ] && [ "$HAS_ERR" != "parse-fail" ]; then
  echo "[duplicate-block] ERROR: source block fetch failed: $HAS_ERR" >&2
  exit 3
fi

# Extract fields
SRC_VALUE=$(echo "$SRC_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin).get('value',''))")
SRC_LABEL=$(echo "$SRC_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin).get('label',''))")
SRC_DESCRIPTION=$(echo "$SRC_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin).get('description') or '')")
SRC_LIMIT=$(echo "$SRC_JSON" | python3 -c "import json,sys; v=json.load(sys.stdin).get('limit'); print(v if v is not None else '')")

if [ -z "$SRC_LABEL" ]; then
  echo "[duplicate-block] ERROR: source block has no label" >&2
  exit 3
fi

LABEL_TO_USE="${NEW_LABEL:-$SRC_LABEL}"

# Idempotence: if target agent already has a block with this label, skip
if [ -n "$TARGET_AGENT_ID" ]; then
  EXISTING=$(curl -sS -L "$LETTA_BASE_URL/v1/agents/$TARGET_AGENT_ID/core-memory/blocks" 2>/dev/null \
    | python3 -c "
import json,sys
d=json.loads(sys.stdin.read(),strict=False)
blocks = d if isinstance(d,list) else []
for b in blocks:
    if b.get('label') == '$LABEL_TO_USE':
        print(b.get('id',''))
        break
" 2>/dev/null || echo "")
  if [ -n "$EXISTING" ]; then
    echo "[duplicate-block] WARN: target agent $TARGET_AGENT_ID already has block with label '$LABEL_TO_USE' (id=$EXISTING); skipping" >&2
    echo "$EXISTING"
    exit 0
  fi
fi

# Build create-payload
CREATE_PAYLOAD=$(python3 -c "
import json
payload = {
    'value': '''$SRC_VALUE''',
    'label': '$LABEL_TO_USE',
}
desc = '''$SRC_DESCRIPTION'''
if desc:
    payload['description'] = desc
limit_str = '$SRC_LIMIT'
if limit_str:
    payload['limit'] = int(limit_str)
print(json.dumps(payload))
")

# Create new block
NEW_RESP=$(curl -sS -L -X POST "$LETTA_BASE_URL/v1/blocks/" \
  -H "Content-Type: application/json" \
  -d "$CREATE_PAYLOAD")
NEW_BLOCK_ID=$(echo "$NEW_RESP" | python3 -c "import json,sys; d=json.loads(sys.stdin.read(),strict=False); print(d.get('id') or '')")

if [ -z "$NEW_BLOCK_ID" ]; then
  ERR=$(echo "$NEW_RESP" | python3 -c "import json,sys; print(json.loads(sys.stdin.read(),strict=False).get('detail',''))")
  echo "[duplicate-block] ERROR: block creation failed: $ERR" >&2
  exit 4
fi

# If target agent specified, attach the new block
if [ -n "$TARGET_AGENT_ID" ]; then
  ATTACH_RESP=$(curl -sS -L -o /dev/null -w "%{http_code}" -X PATCH \
    "$LETTA_BASE_URL/v1/agents/$TARGET_AGENT_ID/core-memory/blocks/attach/$NEW_BLOCK_ID")
  if [ "$ATTACH_RESP" != "200" ]; then
    echo "[duplicate-block] ERROR: attach to $TARGET_AGENT_ID failed (HTTP $ATTACH_RESP)" >&2
    # Cleanup the orphan block to avoid clutter
    curl -sS -L -X DELETE "$LETTA_BASE_URL/v1/blocks/$NEW_BLOCK_ID" -o /dev/null
    exit 5
  fi
  echo "[duplicate-block] OK: duplicated $SOURCE_BLOCK_ID -> $NEW_BLOCK_ID, attached to $TARGET_AGENT_ID (label=$LABEL_TO_USE)" >&2
else
  echo "[duplicate-block] OK: duplicated $SOURCE_BLOCK_ID -> $NEW_BLOCK_ID (unattached, label=$LABEL_TO_USE)" >&2
fi

# Stdout: just the new block_id
echo "$NEW_BLOCK_ID"
