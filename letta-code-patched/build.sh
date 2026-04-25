#!/bin/bash
# Reproducible build: install pinned letta-code + apply Path C handle-fix patch.
# Idempotent — safe to re-run after npm version bumps or upstream auto-updates.
set -euo pipefail

cd "$(dirname "$0")"

echo "[build] Installing letta-code 0.24.2..."
npm install --silent --no-audit --no-fund

LETTA_JS=node_modules/@letta-ai/letta-code/letta.js

if [ ! -f "$LETTA_JS" ]; then
  echo "[build] ERROR: $LETTA_JS not found after install" >&2
  exit 2
fi

# Backup original (overwriting any stale backup) so rollback is one cp away
cp "$LETTA_JS" "$LETTA_JS.original"

echo "[build] Applying Path C handle-fix patch..."
python3 ../letta-memfs-patches/patches/apply_letta_code_self_hosted_handle_fix.py "$LETTA_JS"

echo "[build] Verifying..."
MARKER_COUNT=$(grep -c "PATCH-3205" "$LETTA_JS" || echo 0)
if [ "$MARKER_COUNT" -lt 6 ]; then
  echo "[build] ERROR: expected >=6 PATCH-3205 markers, found $MARKER_COUNT" >&2
  exit 3
fi

VERSION=$(node "$LETTA_JS" --version 2>&1 | head -1)
echo "[build] OK — letta-code $VERSION with $MARKER_COUNT PATCH-3205 markers"
