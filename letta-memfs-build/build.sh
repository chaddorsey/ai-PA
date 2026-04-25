#!/bin/bash
# Build the patched Letta server image with the three external-memfs server patches.
# Idempotent — Docker's layer cache makes re-runs near-instant when nothing changed.
#
# Output tag: letta-local:0.16.7-memfs-v1
#
# Usage: ./letta-memfs-build/build.sh [--no-cache]
set -euo pipefail

cd "$(dirname "$0")/.."  # run from repo root regardless of cwd
REPO_ROOT="$(pwd)"

TAG="letta-local:0.16.7-memfs-v2"
NOCACHE=""
for arg in "$@"; do
  case "$arg" in
    --no-cache) NOCACHE="--no-cache" ;;
  esac
done

echo "[build] Building $TAG from $REPO_ROOT/letta-memfs-build/Dockerfile..."
docker build \
  --build-context "root=$REPO_ROOT" \
  --tag "$TAG" \
  -f letta-memfs-build/Dockerfile \
  $NOCACHE \
  letta-memfs-build/

echo ""
echo "[build] Image built. Verifying..."
docker run --rm "$TAG" python -c "import letta; print('letta', letta.__version__)" || {
  echo "[build] ERROR: letta import failed in built image" >&2
  exit 1
}

# Spot-check the patches landed
docker run --rm "$TAG" sh -c "
  grep -q 'sync-from-git' /app/letta/server/rest_api/routers/v1/agents.py && echo '  patch 01 (sync_endpoint) present' || { echo 'MISSING patch 01' >&2; exit 1; };
  grep -q '_delete_block_from_postgres' /app/letta/services/block_manager_git.py && echo '  patch 02 (delete_propagation) present' || { echo 'MISSING patch 02' >&2; exit 1; };
  grep -q 'LETTA_MEMFS_BLOCK_PATH_PREFIXES' /app/letta/services/memory_repo/path_mapping.py && echo '  patch 03 (system_only_blocks) present' || { echo 'MISSING patch 03' >&2; exit 1; };
  grep -q 'block retained for other agents' /app/letta/services/block_manager_git.py && echo '  patch 04 (scoped_delete_propagation) present' || { echo 'MISSING patch 04' >&2; exit 1; };
"

echo ""
echo "[build] OK. Image $TAG ready."
echo "[build] To run with this image, set LETTA_IMAGE in .env:"
echo "          LETTA_IMAGE=$TAG"
echo "[build] Then: docker compose up -d letta"
