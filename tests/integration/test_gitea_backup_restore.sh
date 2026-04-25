#!/bin/bash
# Gitea backup/restore integration test.
#
# Verifies that:
# - Gitea dump produces a usable artifact
# - Restore into a clean state (deleted-and-recreated repo) reconstructs the data
# - PAT-based clone access works post-restore
#
# Non-destructive to current state: creates a temp test repo, exercises dump on
# the live Gitea (no service downtime), then deletes only the test repo.
#
# Does NOT exercise full volume-level restore — that's tested separately
# in test_full_backup_restore.sh (a more disruptive test).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GITEA_HOST="${GITEA_HOST:-http://127.0.0.1:3030}"
TEST_REPO="test-backup-restore-$(date +%s)"
TEST_FILE_CONTENT="backup-restore-test-payload-$(date +%s)"

# Read creds from .env without exposing them
if [ ! -f "$REPO_ROOT/.env" ]; then
  echo "FAIL: .env not found at $REPO_ROOT/.env" >&2
  exit 1
fi
ADMIN_USER=$(grep "^GITEA_ADMIN_USER=" "$REPO_ROOT/.env" | cut -d= -f2)
TOKEN=$(grep "^GITEA_MEMFS_TOKEN=" "$REPO_ROOT/.env" | cut -d= -f2)
if [ -z "$ADMIN_USER" ] || [ -z "$TOKEN" ]; then
  echo "FAIL: GITEA_ADMIN_USER and/or GITEA_MEMFS_TOKEN not in .env" >&2
  exit 1
fi

cleanup() {
  curl -s -H "Authorization: token $TOKEN" \
    -X DELETE "$GITEA_HOST/api/v1/repos/agents/$TEST_REPO" -o /dev/null || true
  rm -rf /tmp/test-gitea-clone /tmp/test-gitea-restore-clone /tmp/gitea-test-dump.zip 2>/dev/null || true
}
trap cleanup EXIT

echo "[test] 1. Create test repo with seeded content"
RESP=$(curl -s -H "Authorization: token $TOKEN" \
  -H "Content-Type: application/json" \
  -X POST "$GITEA_HOST/api/v1/orgs/agents/repos" \
  -d "{\"name\":\"$TEST_REPO\",\"auto_init\":true,\"private\":true}")
echo "$RESP" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); assert d.get('id'), 'create failed: '+str(d)" \
  || { echo "FAIL: repo creation"; exit 1; }

# Push a known file so we can verify it survives dump→restore
git clone "http://${ADMIN_USER}:${TOKEN}@127.0.0.1:3030/agents/$TEST_REPO.git" /tmp/test-gitea-clone -q
cd /tmp/test-gitea-clone
git config user.email "test@gitea.local"
git config user.name "test"
echo "$TEST_FILE_CONTENT" > marker.txt
git add marker.txt
git commit -q -m "seed test marker"
git push -q origin HEAD:main 2>&1 | tail -3 >/dev/null
cd "$REPO_ROOT"
echo "[test]    seeded marker.txt"

echo "[test] 2. Run gitea dump"
docker exec -u git gitea sh -c 'mkdir -p /tmp/test-dump && cd /tmp/test-dump && gitea dump -c /data/gitea/conf/app.ini --type zip' \
  >/dev/null 2>&1 || { echo "FAIL: gitea dump"; exit 1; }
DUMP_PATH=$(docker exec gitea sh -c 'ls /tmp/test-dump/*.zip 2>/dev/null | head -1')
[ -z "$DUMP_PATH" ] && { echo "FAIL: no dump file produced"; exit 1; }
docker cp "gitea:$DUMP_PATH" /tmp/gitea-test-dump.zip
echo "[test]    dump created: $(ls -la /tmp/gitea-test-dump.zip | awk '{print $5}') bytes"

echo "[test] 3. Verify dump contains the test repo + marker file"
unzip -p /tmp/gitea-test-dump.zip "repos/agents/$TEST_REPO.git/HEAD" >/dev/null 2>&1 \
  || { echo "FAIL: dump missing repos/agents/$TEST_REPO.git"; exit 1; }
echo "[test]    dump contains repos/agents/$TEST_REPO.git/"

echo "[test] 4. Delete the test repo (simulating data loss)"
curl -s -H "Authorization: token $TOKEN" \
  -X DELETE "$GITEA_HOST/api/v1/repos/agents/$TEST_REPO" -o /dev/null
sleep 1
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: token $TOKEN" \
  "$GITEA_HOST/api/v1/repos/agents/$TEST_REPO")
[ "$HTTP" = "404" ] || { echo "FAIL: repo not actually deleted (HTTP $HTTP)"; exit 1; }
echo "[test]    test repo deleted from gitea"

echo "[test] 5. Restore from dump (extract + git push the bundle back into Gitea)"
# Restore strategy: we don't do a full Gitea restore (which would wipe all
# other repos). We extract just the deleted test repo's bare-repo bundle from
# the dump, recreate the empty repo via API, then push the contents.
mkdir -p /tmp/test-gitea-restore
cd /tmp/test-gitea-restore
unzip -q /tmp/gitea-test-dump.zip "repos/agents/$TEST_REPO.git/*"
[ -d "repos/agents/$TEST_REPO.git" ] || { echo "FAIL: bare repo not in dump"; exit 1; }
# Recreate empty repo
curl -s -H "Authorization: token $TOKEN" \
  -H "Content-Type: application/json" \
  -X POST "$GITEA_HOST/api/v1/orgs/agents/repos" \
  -d "{\"name\":\"$TEST_REPO\",\"auto_init\":false,\"private\":true}" >/dev/null
sleep 1
# Push the extracted bare repo's contents back
cd "repos/agents/$TEST_REPO.git"
git push --mirror "http://${ADMIN_USER}:${TOKEN}@127.0.0.1:3030/agents/$TEST_REPO.git" 2>&1 | tail -3 >/dev/null \
  || { echo "FAIL: restore push"; exit 1; }
cd "$REPO_ROOT"
echo "[test]    restore pushed"

echo "[test] 6. Clone restored repo and verify marker file content"
git clone "http://${ADMIN_USER}:${TOKEN}@127.0.0.1:3030/agents/$TEST_REPO.git" /tmp/test-gitea-restore-clone -q
RESTORED_CONTENT=$(cat /tmp/test-gitea-restore-clone/marker.txt)
[ "$RESTORED_CONTENT" = "$TEST_FILE_CONTENT" ] \
  || { echo "FAIL: marker content mismatch (expected '$TEST_FILE_CONTENT', got '$RESTORED_CONTENT')"; exit 1; }
echo "[test]    marker.txt content matches"

echo "[test] 7. Cleanup in-container dump dir"
docker exec -u git gitea rm -rf /tmp/test-dump

echo "[test] PASS — Gitea backup/restore round-trip works"
