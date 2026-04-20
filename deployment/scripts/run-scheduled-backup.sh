#!/bin/bash
# run-scheduled-backup.sh — master runner: preflight → backup → verify → retention.
# Invoked by launchd (com.ai-pa.pa-ecosystem-backup) at 2am daily.
# Can also be run manually for ad-hoc backups.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_DIR="$PROJECT_ROOT/deployment/backups"
LOG_DIR="$HOME/Library/Logs/ai-pa-backup"
mkdir -p "$LOG_DIR"

STAMP=$(date +%Y%m%d_%H%M%S)
RUN_LOG="$LOG_DIR/scheduled-$STAMP.log"
MIN_FREE_GB="${PA_BACKUP_MIN_FREE_GB:-200}"

# Mirror all output to the run log.
exec > >(tee -a "$RUN_LOG") 2>&1

echo "=================================================================="
echo "PA-ecosystem scheduled backup run: $STAMP"
echo "Project root: $PROJECT_ROOT"
echo "Backup dir:   $BACKUP_DIR"
echo "Log:          $RUN_LOG"
echo "=================================================================="

cd "$PROJECT_ROOT"

# ---- [0/3] Preflight: disk space ----
avail_gb=$(df -Pk "$BACKUP_DIR" 2>/dev/null | awk 'NR==2 {print int($4/1024/1024)}')
if [[ -z "$avail_gb" ]]; then
    echo "FATAL: preflight could not determine free space at $BACKUP_DIR"
    exit 2
fi
echo "[0/3] Preflight: ${avail_gb}G free at $BACKUP_DIR (minimum ${MIN_FREE_GB}G)"
if (( avail_gb < MIN_FREE_GB )); then
    echo "FATAL: only ${avail_gb}G free; need at least ${MIN_FREE_GB}G. Aborting before a partial backup is written."
    exit 2
fi

# ---- [1/3] Backup ----
echo
echo "[1/3] Running backup.sh..."
BACKUP_START=$(date +%s)
if "$SCRIPT_DIR/backup.sh" --verbose; then
    backup_exit=0
else
    backup_exit=$?
fi
BACKUP_ELAPSED=$(( $(date +%s) - BACKUP_START ))
echo "[1/3] backup.sh exited $backup_exit after ${BACKUP_ELAPSED}s"

# Resolve latest
if [[ ! -L "$BACKUP_DIR/latest" ]]; then
    echo "FATAL: $BACKUP_DIR/latest symlink missing after backup"
    exit 1
fi
BACKUP_PATH="$BACKUP_DIR/$(readlink "$BACKUP_DIR/latest")"
echo "[1/3] Latest backup: $BACKUP_PATH"

# ---- [2/3] Verify ----
echo
echo "[2/3] Verifying backup..."
if "$SCRIPT_DIR/verify-backup.sh" "$BACKUP_PATH"; then
    echo "[2/3] Verification PASSED"
else
    echo "[2/3] Verification FAILED — keeping backup for inspection, skipping retention"
    exit 1
fi

# ---- [3/3] Retention ----
echo
echo "[3/3] Applying retention policy..."
if command -v python3 >/dev/null 2>&1; then
    python3 "$SCRIPT_DIR/retention-backup.py" --dir "$BACKUP_DIR" || echo "WARN: retention step failed (non-fatal)"
else
    echo "WARN: python3 not found; skipping retention"
fi

echo
echo "=================================================================="
echo "Scheduled backup run complete: $(date)"
echo "=================================================================="
