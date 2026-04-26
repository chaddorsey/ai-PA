#!/usr/bin/env bash
# verify-agent-memfs.sh — read-only audit of an agent's memfs migration state.
#
# Reports PASS/FAIL across:
#   - Agent has git-memory-enabled tag
#   - Server-side bare repo exists and has commits
#   - Bare repo has Gitea origin remote configured
#   - Gitea repo exists and HEAD matches bare repo
#   - Postgres block cache matches bare repo (block count + label set)
#   - Local working tree exists (warns if absent — that's a CLI-side state,
#     not a migration completeness gate)
#
# Usage:  ./verify-agent-memfs.sh <agent_id>

set -uo pipefail

REPO_ROOT="${REPO_ROOT:-/Volumes/main-drive/ai-PA}"
ENV_FILE="$REPO_ROOT/.env"

LETTA_BASE_URL="${LETTA_BASE_URL:-http://localhost:8283}"
GITEA_API_URL="${GITEA_API_URL:-http://127.0.0.1:3030}"
LETTA_ORG_ID="${LETTA_ORG_ID:-org-00000000-0000-4000-8000-000000000000}"
LETTA_CONTAINER="${LETTA_CONTAINER:-ai-pa-letta-1}"

GITEA_ADMIN_USER="${GITEA_ADMIN_USER:-$(grep ^GITEA_ADMIN_USER= "$ENV_FILE" | cut -d= -f2)}"
GITEA_ADMIN_PASS="${GITEA_ADMIN_PASS:-$(grep ^GITEA_ADMIN_PASS= "$ENV_FILE" | cut -d= -f2)}"

AGENT_ID="${1:-}"
[[ -z "$AGENT_ID" ]] && { echo "usage: $0 <agent_id>" >&2; exit 1; }

BARE="/root/.letta/memfs/repository/$LETTA_ORG_ID/$AGENT_ID/repo.git"
LOCAL_WT="$HOME/.letta/agents/$AGENT_ID/memory"

PASS=0
FAIL=0
WARN=0

ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }
warn() { echo "  ! $1"; WARN=$((WARN+1)); }

echo "=== verify $AGENT_ID ==="

# 1. git-memory-enabled tag
TAGS=$(curl -s "$LETTA_BASE_URL/v1/agents/$AGENT_ID" | python3 -c "
import sys,json
try: print(' '.join(json.load(sys.stdin).get('tags') or []))
except: print('')
")
if echo "$TAGS" | grep -qw "git-memory-enabled"; then
    ok "git-memory-enabled tag present"
else
    fail "git-memory-enabled tag MISSING (tags='$TAGS')"
fi

# 2. Bare repo
if docker exec "$LETTA_CONTAINER" test -d "$BARE" 2>/dev/null; then
    ok "server bare repo present"
    BARE_HEAD=$(docker exec "$LETTA_CONTAINER" git --git-dir="$BARE" rev-parse HEAD 2>/dev/null)
    if [[ -n "$BARE_HEAD" ]]; then
        ok "bare repo has commits (HEAD=${BARE_HEAD:0:12})"
    else
        fail "bare repo has no commits"
    fi
else
    fail "server bare repo MISSING at $BARE"
    BARE_HEAD=""
fi

# 3. origin remote
ORIGIN_URL=$(docker exec "$LETTA_CONTAINER" git --git-dir="$BARE" remote get-url origin 2>/dev/null)
if [[ -n "$ORIGIN_URL" ]]; then
    ok "bare repo has origin remote (-> ${ORIGIN_URL//$GITEA_ADMIN_PASS/REDACTED})"
else
    fail "bare repo origin remote NOT configured (patch 05 auto-fetch disabled for this agent)"
fi

# 4. Gitea repo
GITEA_HEAD=$(curl -s -u "$GITEA_ADMIN_USER:$GITEA_ADMIN_PASS" \
    "$GITEA_API_URL/api/v1/repos/agents/$AGENT_ID/branches/main" 2>/dev/null | \
    python3 -c "import sys,json;
try: print(json.load(sys.stdin).get('commit',{}).get('id',''))
except: print('')
")
if [[ -n "$GITEA_HEAD" ]]; then
    ok "Gitea repo exists and has main branch (HEAD=${GITEA_HEAD:0:12})"
    if [[ "$BARE_HEAD" == "$GITEA_HEAD" ]]; then
        ok "bare repo HEAD == Gitea HEAD"
    else
        fail "bare repo HEAD ($BARE_HEAD) != Gitea HEAD ($GITEA_HEAD)"
    fi
else
    fail "Gitea repo MISSING or no main branch"
fi

# 5. Postgres blocks vs bare repo files
SYS_FILES=$(docker exec "$LETTA_CONTAINER" git --git-dir="$BARE" ls-tree -r HEAD --name-only 2>/dev/null | grep -E '^system/.+\.md$' | sed 's|system/||;s|\.md$||' | sort)
SYS_FILE_COUNT=$(echo -n "$SYS_FILES" | grep -c '^' 2>/dev/null || echo 0)
PG_BLOCKS=$(curl -sL "$LETTA_BASE_URL/v1/agents/$AGENT_ID/core-memory/blocks/" 2>/dev/null | python3 -c "
import sys,json
try:
    bs = json.load(sys.stdin)
    labels = sorted([b.get('label','').replace('system/','') for b in bs if b.get('label','').startswith('system/')])
    print('\n'.join(labels))
except: pass
")
PG_BLOCK_COUNT=$(echo -n "$PG_BLOCKS" | grep -c '^' 2>/dev/null || echo 0)
if [[ "$SYS_FILE_COUNT" == "$PG_BLOCK_COUNT" ]] && [[ "$SYS_FILES" == "$PG_BLOCKS" ]]; then
    ok "Postgres blocks match bare repo system/ files ($SYS_FILE_COUNT entries)"
else
    fail "Postgres blocks DIVERGE from bare repo (bare=$SYS_FILE_COUNT, pg=$PG_BLOCK_COUNT)"
fi

# 6. Local working tree (warning, not gate)
if [[ -d "$LOCAL_WT/system" ]]; then
    LOCAL_HEAD=$(git -C "$LOCAL_WT" rev-parse HEAD 2>/dev/null)
    if [[ "$LOCAL_HEAD" == "$BARE_HEAD" ]]; then
        ok "local working tree present and at HEAD ($LOCAL_WT)"
    else
        warn "local working tree present but at different SHA ($LOCAL_HEAD vs $BARE_HEAD) — pull recommended"
    fi
else
    warn "local working tree absent ($LOCAL_WT) — open in TUI to materialize"
fi

echo
echo "=== summary: PASS=$PASS  FAIL=$FAIL  WARN=$WARN ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
