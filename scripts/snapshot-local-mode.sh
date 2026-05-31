#!/usr/bin/env bash
# snapshot-local-mode.sh
#
# Capture the local-mode-specific artifacts the daily pa-ecosystem-backup
# doesn't cover. Runs as a standalone snapshot (one tarball per category)
# under /Volumes/main-filestore/ai-PA-backups/local-mode-snapshots/<ts>/.
#
# Safe to run ad-hoc or on a cron. Idempotent (each run creates a new
# timestamped directory). Designed to complement, not replace, backup.sh.

set -euo pipefail

TIMESTAMP="${TIMESTAMP:-$(date +%Y%m%d_%H%M%S)}"
BACKUP_ROOT="${BACKUP_ROOT:-/Volumes/main-filestore/ai-PA-backups/local-mode-snapshots}"
OUT_DIR="$BACKUP_ROOT/snapshot_$TIMESTAMP"
REPO_ROOT="${REPO_ROOT:-/Volumes/main-drive/ai-PA}"

mkdir -p "$OUT_DIR"

log() { echo "[$(date -u "+%Y-%m-%dT%H:%M:%SZ")] $*"; }

log "snapshot → $OUT_DIR"

# ---- (1) ~/bin/letta-* wrappers ----
if ls "$HOME/bin/letta-"* >/dev/null 2>&1; then
  tar -czf "$OUT_DIR/bin-letta-wrappers_${TIMESTAMP}.tar.gz" \
    -C "$HOME/bin" $(ls "$HOME/bin" | grep -E '^letta-' | tr '\n' ' ')
  log "  ✓ bin/letta-* wrappers"
fi

# ---- (2) ~/.letta/lc-local-backend/ (agent records, providers, conversations, memfs) ----
if [[ -d "$HOME/.letta/lc-local-backend" ]]; then
  # memfs working trees can be large; capture metadata + small files only.
  # Conversations + providers + agents records are small and critical.
  tar -czf "$OUT_DIR/lc-local-backend-core_${TIMESTAMP}.tar.gz" \
    -C "$HOME/.letta" \
    lc-local-backend/agents \
    lc-local-backend/providers \
    lc-local-backend/conversations \
    2>/dev/null || log "  ⚠ lc-local-backend core: partial"
  log "  ✓ lc-local-backend core (agents/providers/conversations)"

  # Memfs trees separately so they're easy to skip on restore.
  if [[ -d "$HOME/.letta/lc-local-backend/memfs" ]]; then
    tar -czf "$OUT_DIR/lc-local-backend-memfs_${TIMESTAMP}.tar.gz" \
      -C "$HOME/.letta" \
      lc-local-backend/memfs \
      2>/dev/null || log "  ⚠ lc-local-backend memfs: partial"
    log "  ✓ lc-local-backend memfs working trees"
  fi
fi

# ---- (3) Bronze CSV archive ----
if [[ -d "$REPO_ROOT/data/raw-archive" ]]; then
  tar -czf "$OUT_DIR/raw-archive_${TIMESTAMP}.tar.gz" \
    -C "$REPO_ROOT" \
    data/raw-archive
  log "  ✓ data/raw-archive (Bronze CSV archive)"
fi

# ---- (4) Top-level repo scripts/ (not in deployment_*.tar.gz) ----
if [[ -d "$REPO_ROOT/scripts" ]]; then
  tar -czf "$OUT_DIR/repo-scripts_${TIMESTAMP}.tar.gz" \
    -C "$REPO_ROOT" \
    scripts
  log "  ✓ scripts/ (top-level repo scripts)"
fi

# ---- (5) Extracted Letta tool sources (per-agent local-mode CLIs) ----
for tooldir in pulse-tools email-tools tasks-tools docs-tools calendar-tools; do
  if [[ -d "$REPO_ROOT/letta/$tooldir" ]]; then
    tar -czf "$OUT_DIR/letta-${tooldir}_${TIMESTAMP}.tar.gz" \
      -C "$REPO_ROOT/letta" \
      "$tooldir" 2>/dev/null && log "  ✓ letta/$tooldir"
  fi
done

# ---- (6) Migration docs (track which agents are migrated + how) ----
if [[ -d "$REPO_ROOT/docs/migrations/local-mode" ]]; then
  tar -czf "$OUT_DIR/migration-docs_${TIMESTAMP}.tar.gz" \
    -C "$REPO_ROOT/docs" \
    migrations/local-mode
  log "  ✓ migration docs"
fi

# ---- (7) Manifest ----
{
  echo "# Local-mode snapshot — ${TIMESTAMP}"
  echo "host: $(hostname)"
  echo "captured_utc: $(date -u "+%Y-%m-%dT%H:%M:%SZ")"
  echo ""
  echo "## Contents"
  for f in "$OUT_DIR"/*.tar.gz; do
    [ -e "$f" ] || continue
    size=$(du -h "$f" | cut -f1)
    echo "- $(basename "$f"): $size"
  done
  echo ""
  echo "## Restore notes"
  echo "- bin-letta-wrappers: extract to \$HOME/bin/"
  echo "- lc-local-backend-core: extract to \$HOME/.letta/ (provides agents/providers/conversations)"
  echo "- lc-local-backend-memfs: optional; agents will re-clone from Gitea if absent"
  echo "- raw-archive: extract to /Volumes/main-drive/ai-PA/data/"
  echo "- repo-scripts: source-of-truth is git; this tarball is for between-commit recovery"
  echo "- letta-*-tools: extract to /Volumes/main-drive/ai-PA/letta/"
} > "$OUT_DIR/MANIFEST.md"

log "done → $OUT_DIR"
log "  manifest: $OUT_DIR/MANIFEST.md"
