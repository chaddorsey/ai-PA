#!/usr/bin/env bash
# bridge-agent-to-gitea.sh — automate the Gitea bridge steps of memfs
# migration. Idempotent: safe to re-run on an agent that's already bridged.
#
# Runs after a first `/memfs enable` attempt (which creates the server-side
# bare repo with backfilled blocks). This script:
#   1. Creates a Gitea repo at agents/<agent_id> (or no-ops if it exists)
#   2. Pushes the bare repo's main branch from the Letta container to Gitea
#   3. Configures Gitea as the bare repo's `origin` remote so patch 05's
#      auto-fetch fires on every sync-from-git
#
# Usage:
#   ./bridge-agent-to-gitea.sh <agent_id>
#
# Env (optional, with defaults):
#   GITEA_API_URL=http://127.0.0.1:3030
#   GITEA_INTERNAL_URL=http://gitea:3000  (used by Letta container)
#   LETTA_ORG_ID=org-00000000-0000-4000-8000-000000000000
#   LETTA_CONTAINER=ai-pa-letta-1
#   GITEA_ADMIN_USER, GITEA_ADMIN_PASS, GITEA_MEMFS_TOKEN — pulled from .env

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/Volumes/main-drive/ai-PA}"
ENV_FILE="$REPO_ROOT/.env"

GITEA_API_URL="${GITEA_API_URL:-http://127.0.0.1:3030}"
GITEA_INTERNAL_URL="${GITEA_INTERNAL_URL:-http://gitea:3000}"
LETTA_ORG_ID="${LETTA_ORG_ID:-org-00000000-0000-4000-8000-000000000000}"
LETTA_CONTAINER="${LETTA_CONTAINER:-ai-pa-letta-1}"

GITEA_ADMIN_USER="${GITEA_ADMIN_USER:-$(grep ^GITEA_ADMIN_USER= "$ENV_FILE" | cut -d= -f2)}"
GITEA_ADMIN_PASS="${GITEA_ADMIN_PASS:-$(grep ^GITEA_ADMIN_PASS= "$ENV_FILE" | cut -d= -f2)}"
GITEA_MEMFS_TOKEN="${GITEA_MEMFS_TOKEN:-$(grep ^GITEA_MEMFS_TOKEN= "$ENV_FILE" | cut -d= -f2)}"

AGENT_ID="${1:-}"
if [[ -z "$AGENT_ID" ]]; then
    echo "usage: $0 <agent_id>" >&2
    exit 1
fi

if [[ ! "$AGENT_ID" =~ ^agent-[0-9a-f-]{36}$ ]]; then
    echo "error: agent_id doesn't look right: '$AGENT_ID'" >&2
    exit 1
fi

BARE="/root/.letta/memfs/repository/$LETTA_ORG_ID/$AGENT_ID/repo.git"
GITEA_INTERNAL_REMOTE="$GITEA_INTERNAL_URL/agents/$AGENT_ID.git"
GITEA_AUTH_REMOTE="${GITEA_INTERNAL_URL/http:\/\//http://$GITEA_ADMIN_USER:$GITEA_MEMFS_TOKEN@}/agents/$AGENT_ID.git"

echo "[bridge] agent: $AGENT_ID"
echo "[bridge] bare repo: $BARE (in $LETTA_CONTAINER)"
echo "[bridge] Gitea repo: agents/$AGENT_ID"

# 1. Confirm bare repo exists in Letta container
if ! docker exec "$LETTA_CONTAINER" test -d "$BARE"; then
    echo "[bridge] ERROR: bare repo does not exist at $BARE" >&2
    echo "[bridge]        Run /memfs enable in TUI first to backfill it" >&2
    exit 2
fi
echo "[bridge] bare repo present ✓"

# 2. Create Gitea repo if missing (idempotent)
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
    -u "$GITEA_ADMIN_USER:$GITEA_ADMIN_PASS" \
    "$GITEA_API_URL/api/v1/repos/agents/$AGENT_ID")
if [[ "$HTTP_CODE" == "200" ]]; then
    echo "[bridge] Gitea repo already exists ✓"
else
    CREATE_RESP=$(curl -s -u "$GITEA_ADMIN_USER:$GITEA_ADMIN_PASS" \
        -X POST "$GITEA_API_URL/api/v1/orgs/agents/repos" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"$AGENT_ID\",\"default_branch\":\"main\",\"auto_init\":false,\"private\":true}")
    if echo "$CREATE_RESP" | grep -q '"id":'; then
        echo "[bridge] Gitea repo created ✓"
    else
        echo "[bridge] ERROR: Gitea repo create failed: $CREATE_RESP" >&2
        exit 3
    fi
fi

# 3. Push bare repo content to Gitea (force, so re-runs are safe)
PUSH_OUT=$(docker exec "$LETTA_CONTAINER" sh -c "
git --git-dir='$BARE' push '$GITEA_AUTH_REMOTE' main:main --force 2>&1
")
if echo "$PUSH_OUT" | grep -qE "rejected|fatal|error:"; then
    echo "[bridge] ERROR: push failed:" >&2
    echo "$PUSH_OUT" >&2
    exit 4
fi
echo "[bridge] bare repo -> Gitea push ✓"

# 4. Configure Gitea as origin remote on bare repo (idempotent)
EXISTING_ORIGIN=$(docker exec "$LETTA_CONTAINER" sh -c "
git --git-dir='$BARE' remote 2>/dev/null
" | tr -d '\r')

if echo "$EXISTING_ORIGIN" | grep -qx "origin"; then
    docker exec "$LETTA_CONTAINER" git --git-dir="$BARE" remote set-url origin "$GITEA_AUTH_REMOTE"
    echo "[bridge] origin remote updated ✓"
else
    docker exec "$LETTA_CONTAINER" git --git-dir="$BARE" remote add origin "$GITEA_AUTH_REMOTE"
    echo "[bridge] origin remote added ✓"
fi

echo "[bridge] DONE for $AGENT_ID"
echo "[bridge] Next: re-open the TUI and run '/memfs enable' to complete the local clone."
