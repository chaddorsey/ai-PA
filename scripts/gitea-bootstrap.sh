#!/bin/bash
# Bootstrap script for Gitea — idempotent.
#
# Creates:
#   - Admin user (via gitea CLI; no API call until we have the user)
#   - "agents" organization (one repo per memfs-enabled agent)
#   - Personal access token scoped to repo:read/write on agents org
#
# With --write-env: appends GITEA_ADMIN_USER, GITEA_ADMIN_PASS, GITEA_MEMFS_TOKEN,
# LETTA_MEMFS_GIT_URL to the project .env (only if those keys aren't already
# present — won't clobber existing values). Without --write-env: prints the
# values to stdout for manual copy.
#
# Usage:
#   ./scripts/gitea-bootstrap.sh             # print to stdout
#   ./scripts/gitea-bootstrap.sh --write-env # append to .env (idempotent)
#
# Prerequisites: gitea container is running and healthy (docker compose up -d gitea).

set -euo pipefail

GITEA_CONTAINER="${GITEA_CONTAINER:-gitea}"
GITEA_HOST="${GITEA_HOST:-http://127.0.0.1:3030}"
ADMIN_USER="${GITEA_ADMIN_USER:-pa-admin}"
ADMIN_PASS="${GITEA_ADMIN_PASS:-}"   # passed via env if rotating
AGENTS_ORG="${GITEA_AGENTS_ORG:-agents}"
ADMIN_EMAIL="${GITEA_ADMIN_EMAIL:-pa-admin@gitea.local}"
TOKEN_NAME="${GITEA_TOKEN_NAME:-letta-memfs-pat}"

if [ -z "$ADMIN_PASS" ]; then
  # Generate a fresh strong password if not supplied
  ADMIN_PASS=$(openssl rand -base64 32 | tr -d '/+=\n' | head -c 32)
fi

echo "[gitea-bootstrap] Container: $GITEA_CONTAINER"
echo "[gitea-bootstrap] Admin user: $ADMIN_USER"

# 1) Create admin user (idempotent — gitea returns non-zero if exists)
if docker exec -u git "$GITEA_CONTAINER" gitea admin user list 2>/dev/null | grep -qE "^[0-9]+\s+$ADMIN_USER\s"; then
  echo "[gitea-bootstrap] Admin user '$ADMIN_USER' already exists; skipping creation"
else
  echo "[gitea-bootstrap] Creating admin user '$ADMIN_USER'..."
  docker exec -u git "$GITEA_CONTAINER" gitea admin user create \
    --username "$ADMIN_USER" \
    --password "$ADMIN_PASS" \
    --email "$ADMIN_EMAIL" \
    --admin \
    --must-change-password=false
  echo ""
  echo "[gitea-bootstrap] !!!! ADMIN PASSWORD (record it now if you want to log in via web UI) !!!!"
  echo "[gitea-bootstrap]    $ADMIN_PASS"
  echo ""
fi

# 2) Create agents org via API (idempotent)
ORG_CHECK=$(curl -sS -u "$ADMIN_USER:$ADMIN_PASS" -o /dev/null -w "%{http_code}" \
  "$GITEA_HOST/api/v1/orgs/$AGENTS_ORG")
if [ "$ORG_CHECK" = "200" ]; then
  echo "[gitea-bootstrap] Org '$AGENTS_ORG' already exists; skipping creation"
elif [ "$ORG_CHECK" = "404" ]; then
  echo "[gitea-bootstrap] Creating org '$AGENTS_ORG'..."
  curl -sS -u "$ADMIN_USER:$ADMIN_PASS" \
    -H "Content-Type: application/json" \
    -X POST "$GITEA_HOST/api/v1/orgs" \
    -d "{\"username\":\"$AGENTS_ORG\",\"visibility\":\"private\"}" \
    | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print('[gitea-bootstrap] org created: id=' + str(d.get('id','?')))" \
    || { echo "[gitea-bootstrap] ERROR: org creation failed" >&2; exit 1; }
else
  echo "[gitea-bootstrap] ERROR: unexpected org-check HTTP $ORG_CHECK" >&2
  exit 1
fi

# 3) Create PAT (idempotent — Gitea returns 422 if name collides; we generate a fresh one if so)
echo "[gitea-bootstrap] Creating PAT '$TOKEN_NAME'..."
TOKEN_RESP=$(curl -sS -u "$ADMIN_USER:$ADMIN_PASS" \
  -H "Content-Type: application/json" \
  -X POST "$GITEA_HOST/api/v1/users/$ADMIN_USER/tokens" \
  -d "{\"name\":\"$TOKEN_NAME\",\"scopes\":[\"write:repository\",\"write:organization\"]}")

TOKEN=$(echo "$TOKEN_RESP" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('sha1',''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  ERR=$(echo "$TOKEN_RESP" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('message','unknown'))" 2>/dev/null || echo "unknown")
  if echo "$ERR" | grep -qi "already exists\|access token name has been used"; then
    # Token name was reused — Gitea won't return the existing token's value.
    # Generate a versioned name to get a fresh token instead.
    UNIQUE_NAME="${TOKEN_NAME}-$(date +%s)"
    echo "[gitea-bootstrap] Token name '$TOKEN_NAME' already exists; creating '$UNIQUE_NAME' instead"
    TOKEN_RESP=$(curl -sS -u "$ADMIN_USER:$ADMIN_PASS" \
      -H "Content-Type: application/json" \
      -X POST "$GITEA_HOST/api/v1/users/$ADMIN_USER/tokens" \
      -d "{\"name\":\"$UNIQUE_NAME\",\"scopes\":[\"write:repository\",\"write:organization\"]}")
    TOKEN=$(echo "$TOKEN_RESP" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('sha1',''))" 2>/dev/null)
  fi
fi

if [ -z "$TOKEN" ]; then
  echo "[gitea-bootstrap] ERROR: token creation failed: $TOKEN_RESP" >&2
  exit 1
fi

WRITE_ENV=0
for arg in "$@"; do
  case "$arg" in
    --write-env) WRITE_ENV=1 ;;
  esac
done

ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"
GIT_URL="http://${ADMIN_USER}:${TOKEN}@gitea:3000/${AGENTS_ORG}/{agentId}.git"

if [ "$WRITE_ENV" = "1" ]; then
  if [ ! -f "$ENV_FILE" ]; then
    echo "[gitea-bootstrap] ERROR: .env not found at $ENV_FILE" >&2
    exit 1
  fi
  # Append-if-missing for each key
  append_if_missing() {
    local KEY="$1"; local VAL="$2"
    if grep -qE "^${KEY}=" "$ENV_FILE"; then
      echo "[gitea-bootstrap]   $KEY already in .env; not overwriting"
    else
      printf "\n# Gitea (added by gitea-bootstrap.sh)\n%s=%s\n" "$KEY" "$VAL" >> "$ENV_FILE"
      echo "[gitea-bootstrap]   appended $KEY to .env"
    fi
  }
  echo "[gitea-bootstrap] Writing to $ENV_FILE..."
  append_if_missing "GITEA_ADMIN_USER"   "$ADMIN_USER"
  append_if_missing "GITEA_ADMIN_PASS"   "$ADMIN_PASS"
  append_if_missing "GITEA_MEMFS_TOKEN"  "$TOKEN"
  append_if_missing "LETTA_MEMFS_GIT_URL" "$GIT_URL"
else
  echo ""
  echo "[gitea-bootstrap] Bootstrap complete. To persist credentials, re-run with --write-env"
  echo "[gitea-bootstrap] OR add manually to .env:"
  echo ""
  echo "    GITEA_ADMIN_USER=$ADMIN_USER"
  echo "    GITEA_ADMIN_PASS=$ADMIN_PASS"
  echo "    GITEA_MEMFS_TOKEN=$TOKEN"
  echo "    LETTA_MEMFS_GIT_URL=$GIT_URL"
fi
echo ""
echo "[gitea-bootstrap] Web UI at $GITEA_HOST (sign in with $ADMIN_USER)"
