#!/bin/bash

# Emergency Rollback Script
# Purpose: Quick emergency rollback for any framework to a previous version
# Usage: ./emergency-rollback.sh --framework <framework> --target-version <version> [--backup-path <path>]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="/var/log/rollback/emergency-rollback-$(date +%Y%m%d-%H%M%S).log"
FRAMEWORK=""
TARGET_VERSION=""
BACKUP_PATH=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --framework)
            FRAMEWORK="$2"
            shift 2
            ;;
        --target-version)
            TARGET_VERSION="$2"
            shift 2
            ;;
        --backup-path)
            BACKUP_PATH="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 --framework <framework> --target-version <version> [--backup-path <path>]"
            echo ""
            echo "Options:"
            echo "  --framework       Framework to rollback (n8n, letta, graphiti)"
            echo "  --target-version  Target version to rollback to"
            echo "  --backup-path     Specific backup path (optional)"
            echo "  -h, --help        Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --framework n8n --target-version 1.109.2"
            echo "  $0 --framework letta --target-version 0.11.7 --backup-path /var/backups/upgrades/letta/letta-backup-20250121-050000"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate arguments
if [ -z "$FRAMEWORK" ] || [ -z "$TARGET_VERSION" ]; then
    echo -e "${RED}❌ Error: Framework and target version are required${NC}"
    echo "Usage: $0 --framework <framework> --target-version <version>"
    exit 1
fi

# Validate framework
case "$FRAMEWORK" in
    "n8n"|"letta"|"graphiti")
        ;;
    *)
        echo -e "${RED}❌ Error: Unknown framework: $FRAMEWORK${NC}"
        echo "Available frameworks: n8n, letta, graphiti"
        exit 1
        ;;
esac

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"

# Logging function
log() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $message" | tee -a "$LOG_FILE"
}

# Error handling
error_exit() {
    local message="$1"
    log "ERROR: $message"
    echo -e "${RED}❌ $message${NC}"
    exit 1
}

# Warning function
warning() {
    local message="$1"
    log "WARNING: $message"
    echo -e "${YELLOW}⚠️  $message${NC}"
}

# Success function
success() {
    local message="$1"
    log "SUCCESS: $message"
    echo -e "${GREEN}✅ $message${NC}"
}

# Info function
info() {
    local message="$1"
    log "INFO: $message"
    echo -e "${BLUE}ℹ️  $message${NC}"
}

# Find latest backup for framework
find_latest_backup() {
    local framework="$1"
    local backup_dir="/var/backups/upgrades/$framework"
    
    if [ ! -d "$backup_dir" ]; then
        error_exit "Backup directory not found: $backup_dir"
    fi
    
    # Find the most recent backup
    local latest_backup=$(find "$backup_dir" -name "${framework}-backup-*" -type d | sort -r | head -1)
    
    if [ -z "$latest_backup" ]; then
        error_exit "No backups found for $framework in $backup_dir"
    fi
    
    echo "$latest_backup"
}

# Execute framework-specific rollback
execute_rollback() {
    local framework="$1"
    local backup_path="$2"
    
    info "Executing $framework rollback using backup: $backup_path"
    
    case "$framework" in
        "n8n")
            "$PROJECT_ROOT/scripts/rollback/n8n/rollback-n8n.sh" --backup-path "$backup_path"
            ;;
        "letta")
            "$PROJECT_ROOT/scripts/rollback/letta/rollback-letta.sh" --backup-path "$backup_path"
            ;;
        "graphiti")
            "$PROJECT_ROOT/scripts/rollback/graphiti/rollback-graphiti.sh" --backup-path "$backup_path"
            ;;
        *)
            error_exit "Unknown framework: $framework"
            ;;
    esac
}

# Main emergency rollback process
main() {
    echo -e "${RED}🚨 EMERGENCY ROLLBACK${NC}"
    echo -e "${RED}==================${NC}"
    echo "Framework: $FRAMEWORK"
    echo "Target version: $TARGET_VERSION"
    echo "Backup path: ${BACKUP_PATH:-auto}"
    echo "Log file: $LOG_FILE"
    echo ""
    
    log "Starting emergency rollback process"
    
    # Find backup if not specified
    if [ -z "$BACKUP_PATH" ]; then
        info "Finding latest backup for $FRAMEWORK..."
        BACKUP_PATH=$(find_latest_backup "$FRAMEWORK")
        info "Using backup: $BACKUP_PATH"
    fi
    
    # Validate backup exists
    if [ ! -d "$BACKUP_PATH" ]; then
        error_exit "Backup path does not exist: $BACKUP_PATH"
    fi
    
    # Execute rollback
    execute_rollback "$FRAMEWORK" "$BACKUP_PATH"
    
    success "Emergency rollback completed!"
    echo ""
    echo -e "${GREEN}📋 Emergency Rollback Summary${NC}"
    echo -e "${GREEN}============================${NC}"
    echo "Framework: $FRAMEWORK"
    echo "Target version: $TARGET_VERSION"
    echo "Backup used: $BACKUP_PATH"
    echo "Log file: $LOG_FILE"
    echo ""
    echo -e "${YELLOW}📝 Next Steps${NC}"
    echo "1. Verify service is running and healthy"
    echo "2. Test critical functionality"
    echo "3. Monitor system performance"
    echo "4. Investigate the cause of the emergency"
    echo "5. Plan proper upgrade strategy"
    echo ""
    echo -e "${BLUE}🔧 Troubleshooting${NC}"
    echo "If issues persist:"
    echo "1. Check logs: $LOG_FILE"
    echo "2. Verify service health: docker ps"
    echo "3. Test API endpoints"
    echo "4. Contact operations team immediately"
}

# Run main function
main "$@"
