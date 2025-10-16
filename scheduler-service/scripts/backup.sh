#!/bin/bash
# Backup wrapper for scheduler service execution
# This script runs INSIDE the scheduler container with Docker access

# DO NOT use set -e because we want to capture all errors
set -uo pipefail

# Configuration - use container paths, not host paths!
PROJECT_ROOT="/workspace"

# Ensure these are set for subprocess execution
export COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"
export COMPOSE_PROJECT_NAME="ai-pa"
export BACKUP_DIR="${PROJECT_ROOT}/deployment/backups"
export LOG_DIR="${PROJECT_ROOT}/deployment/logs"
export PATH="/usr/local/bin:/usr/bin:/bin"

# Change to project root
cd "${PROJECT_ROOT}"

# Log start
echo "=== Scheduler Backup Execution Started ===" >&2
echo "Time: $(date)" >&2
echo "Working directory: $(pwd)" >&2
echo "COMPOSE_FILE: ${COMPOSE_FILE}" >&2
echo "BACKUP_DIR: ${BACKUP_DIR}" >&2

# Execute backup script
"${PROJECT_ROOT}/deployment/scripts/backup.sh" -f -v 2>&1

EXIT_CODE=$?
echo "=== Backup Execution Completed with exit code: ${EXIT_CODE} ===" >&2
exit ${EXIT_CODE}

