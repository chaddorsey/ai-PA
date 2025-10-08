#!/bin/bash
# Backup wrapper for scheduled backups

set -euo pipefail

# Configuration
SCRIPT_DIR="/Users/dorseyhomeserver/ai-PA"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup.sh"
LOG_DIR="$PROJECT_ROOT/deployment/logs"

# Create log directory
mkdir -p "$LOG_DIR"

# Run backup
"$BACKUP_SCRIPT" --type "full" --verbose >> "$LOG_DIR/scheduled-backup.log" 2>&1

# Clean up old backups
"$SCRIPT_DIR/schedule-backup.sh" cleanup --retention 30 >> "$LOG_DIR/scheduled-backup.log" 2>&1
