#!/bin/bash
# Backup health check script - verifies backup integrity
# Returns 0 if healthy, non-zero if issues found

set -euo pipefail

# Configuration
PROJECT_ROOT="/workspace"
BACKUP_DIR="${PROJECT_ROOT}/deployment/backups"
LATEST="${BACKUP_DIR}/latest"
LOG_DIR="${PROJECT_ROOT}/deployment/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/health-check-${TIMESTAMP}.log"

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" | tee -a "${LOG_FILE}" >&2
}

mkdir -p "${LOG_DIR}"

log "Starting backup health check"

# Check 1: Latest symlink exists
if [[ ! -L "${LATEST}" ]]; then
    error "Latest backup symlink not found"
    exit 1
fi
log "✓ Latest backup symlink exists"

# Check 2: Git reference file
if [[ ! -f "${LATEST}/GIT_REFERENCE.txt" ]]; then
    error "Git reference file missing"
    exit 1
fi
log "✓ Git reference file present"

# Check 3: Database backups directory
if [[ ! -d "${LATEST}/databases" ]]; then
    error "Database backup directory missing"
    exit 1
fi
log "✓ Database directory exists"

# Check 4: At least one database backup exists and is non-empty
DB_COUNT=$(find "${LATEST}/databases" -name "*.sql" -size +1k | wc -l)
if [[ ${DB_COUNT} -lt 1 ]]; then
    error "No valid database backups found"
    exit 1
fi
log "✓ Found ${DB_COUNT} database backups"

# Check 5: Letta exports directory
if [[ ! -d "${LATEST}/letta_exports/agents" ]]; then
    error "Letta agents export directory missing"
    exit 1
fi
log "✓ Letta exports directory exists"

# Check 6: Agent exports
AGENT_COUNT=$(find "${LATEST}/letta_exports/agents" -name "*.json" -size +1k | wc -l)
if [[ ${AGENT_COUNT} -lt 1 ]]; then
    error "No valid agent exports found"
    exit 1
fi
log "✓ Found ${AGENT_COUNT} agent exports"

# Check 7: Memory blocks export
if [[ ! -f "${LATEST}/letta_exports/memory/blocks_all.json" ]]; then
    error "Memory blocks export missing"
    exit 1
fi
log "✓ Memory blocks export present"

# Check 8: Backup manifest
if [[ ! -f "${LATEST}/BACKUP_MANIFEST.md" ]]; then
    error "Backup manifest missing"
    exit 1
fi
log "✓ Backup manifest present"

# Check 9: Backup age (warn if older than 48 hours)
BACKUP_AGE_HOURS=$(find "${LATEST}" -maxdepth 0 -mtime +2 -printf "%T@\n" 2>/dev/null | wc -l || echo 0)
if [[ ${BACKUP_AGE_HOURS} -gt 0 ]]; then
    log "WARNING: Latest backup is older than 48 hours"
else
    log "✓ Backup is recent (< 48 hours)"
fi

# Get backup size
BACKUP_SIZE=$(du -sh "${LATEST}" 2>/dev/null | cut -f1 || echo "unknown")
log "Backup size: ${BACKUP_SIZE}"

log "Health check completed successfully"
exit 0

