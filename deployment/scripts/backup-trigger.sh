#!/bin/bash
# HTTP-triggered backup wrapper
# This script runs on the HOST (via systemd, launchd, or simple HTTP server)
# and is triggered by the scheduler service

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$PROJECT_ROOT/deployment/logs"

mkdir -p "$LOG_DIR"

# Execute backup
"$SCRIPT_DIR/backup.sh" -f -v >> "$LOG_DIR/scheduled-backup.log" 2>&1

# Return success
echo "Backup completed successfully"
exit 0

