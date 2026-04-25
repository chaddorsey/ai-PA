#!/bin/bash
# Reproducible build: install pinned letta-code + apply Path C handle-fix
# patch + memfs-external-git patch.
#
# Idempotent — safe to re-run after npm version bumps or upstream auto-updates.
# Each apply.py is itself idempotent and detects "already applied" via marker
# comments.

set -euo pipefail

cd "$(dirname "$0")"

echo "[build] Installing letta-code 0.24.2..."
npm install --silent --no-audit --no-fund

LETTA_JS=node_modules/@letta-ai/letta-code/letta.js

if [ ! -f "$LETTA_JS" ]; then
  echo "[build] ERROR: $LETTA_JS not found after install" >&2
  exit 2
fi

# Backup the pre-patch original ONCE — only if .original doesn't already
# exist. On re-runs, .original stays pristine (we don't want to overwrite
# it with the now-patched file).
# To force a fresh .original, run: rm -rf node_modules && ./build.sh
if [ ! -f "$LETTA_JS.original" ]; then
  if grep -q "PATCH-3205\|PATCH-MEMFS-GIT" "$LETTA_JS" 2>/dev/null; then
    echo "[build] WARNING: $LETTA_JS is already patched but no .original backup exists." >&2
    echo "[build]          Reinstall to capture a clean baseline:" >&2
    echo "[build]            rm -rf node_modules && ./build.sh" >&2
  else
    cp "$LETTA_JS" "$LETTA_JS.original"
    echo "[build] Captured pristine backup: $LETTA_JS.original"
  fi
fi

echo "[build] Applying Path C handle-fix patch (#3205)..."
python3 ../letta-memfs-patches/patches/apply_letta_code_self_hosted_handle_fix.py "$LETTA_JS"

echo "[build] Applying memfs-external-git patch..."
python3 ../letta-memfs-patches/patches/apply_letta_code_memfs_external_git.py "$LETTA_JS"

echo "[build] Verifying..."
MARKERS_3205=$(grep -c "PATCH-3205" "$LETTA_JS" || echo 0)
MARKERS_MEMFS=$(grep -c "PATCH-MEMFS-GIT" "$LETTA_JS" || echo 0)
if [ "$MARKERS_3205" -lt 6 ]; then
  echo "[build] ERROR: expected >=6 PATCH-3205 markers, found $MARKERS_3205" >&2
  exit 3
fi
if [ "$MARKERS_MEMFS" -lt 3 ]; then
  echo "[build] ERROR: expected >=3 PATCH-MEMFS-GIT markers, found $MARKERS_MEMFS" >&2
  exit 3
fi

# Quick parse + version check
node --check "$LETTA_JS" >/dev/null
VERSION=$(node "$LETTA_JS" --version 2>&1 | head -1)
echo "[build] OK — letta-code $VERSION"
echo "[build]      Path C (#3205) handle-fix markers: $MARKERS_3205"
echo "[build]      memfs-external-git markers:        $MARKERS_MEMFS"
