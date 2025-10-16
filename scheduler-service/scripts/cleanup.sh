#!/bin/bash
# Backup cleanup script - removes backups older than specified retention period
# Usage: cleanup.sh [RETENTION_DAYS]

set -euo pipefail

# Configuration
RETENTION_DAYS="${1:-30}"
PROJECT_ROOT="/workspace"
BACKUP_DIR="${PROJECT_ROOT}/deployment/backups"
LOG_DIR="${PROJECT_ROOT}/deployment/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/cleanup-${TIMESTAMP}.log"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

# Ensure directories exist
mkdir -p "${LOG_DIR}"

log "Starting backup cleanup (retention: ${RETENTION_DAYS} days)"

if [[ ! -d "${BACKUP_DIR}" ]]; then
    log "ERROR: Backup directory not found: ${BACKUP_DIR}"
    exit 1
fi

# Find and remove old backups
OLD_BACKUPS=$(find "${BACKUP_DIR}" -maxdepth 1 -type d -name "pa-ecosystem-backup-*" -mtime +${RETENTION_DAYS} 2>/dev/null || true)

if [[ -z "${OLD_BACKUPS}" ]]; then
    log "No backups older than ${RETENTION_DAYS} days found"
    exit 0
fi

COUNT=0
while IFS= read -r backup_dir; do
    if [[ -n "${backup_dir}" ]]; then
        BACKUP_NAME=$(basename "${backup_dir}")
        BACKUP_SIZE=$(du -sh "${backup_dir}" 2>/dev/null | cut -f1 || echo "unknown")
        log "Removing old backup: ${BACKUP_NAME} (${BACKUP_SIZE})"
        rm -rf "${backup_dir}"
        ((COUNT++)) || true
    fi
done <<< "${OLD_BACKUPS}"

log "Cleanup completed: removed ${COUNT} old backups"
exit 0

