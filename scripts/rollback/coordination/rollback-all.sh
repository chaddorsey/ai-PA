#!/bin/bash

# Multi-Framework Rollback Coordination Script
# Purpose: Coordinate rollbacks of multiple frameworks with proper sequencing and validation
# Usage: ./rollback-all.sh --frameworks "n8n,letta,graphiti" --backup-base-path <path> [--sequential]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
LOG_FILE="/var/log/rollback/coordinated-rollback-$(date +%Y%m%d-%H%M%S).log"
FRAMEWORKS=""
BACKUP_BASE_PATH=""
SEQUENTIAL=true
PARALLEL=false

# Framework rollback order (dependencies)
FRAMEWORK_ORDER=("n8n" "letta" "graphiti")

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --frameworks)
            FRAMEWORKS="$2"
            shift 2
            ;;
        --backup-base-path)
            BACKUP_BASE_PATH="$2"
            shift 2
            ;;
        --sequential)
            SEQUENTIAL=true
            shift
            ;;
        --parallel)
            PARALLEL=true
            SEQUENTIAL=false
            shift
            ;;
        -h|--help)
            echo "Usage: $0 --frameworks \"<framework1>,<framework2>,...\" --backup-base-path <path> [--sequential|--parallel]"
            echo ""
            echo "Options:"
            echo "  --frameworks         Comma-separated list of frameworks to rollback"
            echo "  --backup-base-path  Base path containing framework backups"
            echo "  --sequential        Rollback frameworks one at a time (default)"
            echo "  --parallel          Rollback frameworks in parallel (experimental)"
            echo "  -h, --help          Show this help message"
            echo ""
            echo "Available frameworks: n8n, letta, graphiti"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate arguments
if [ -z "$FRAMEWORKS" ] || [ -z "$BACKUP_BASE_PATH" ]; then
    echo -e "${RED}❌ Error: Frameworks and backup base path are required${NC}"
    echo "Usage: $0 --frameworks \"<framework1>,<framework2>,...\" --backup-base-path <path>"
    exit 1
fi

if [ ! -d "$BACKUP_BASE_PATH" ]; then
    echo -e "${RED}❌ Error: Backup base path does not exist: $BACKUP_BASE_PATH${NC}"
    exit 1
fi

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

# Parse frameworks list
parse_frameworks() {
    IFS=',' read -ra FRAMEWORK_ARRAY <<< "$FRAMEWORKS"
    
    # Validate frameworks
    for framework in "${FRAMEWORK_ARRAY[@]}"; do
        case "$framework" in
            "n8n"|"letta"|"graphiti")
                continue
                ;;
            *)
                error_exit "Unknown framework: $framework (available: n8n, letta, graphiti)"
                ;;
        esac
    done
    
    info "Frameworks to rollback: ${FRAMEWORK_ARRAY[*]}"
}

# Find backup for framework
find_framework_backup() {
    local framework="$1"
    local backup_dir="$BACKUP_BASE_PATH/$framework"
    
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

# Rollback single framework
rollback_framework() {
    local framework="$1"
    local backup_path="$2"
    
    info "Rolling back $framework using backup: $backup_path"
    
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

# Sequential rollback process
sequential_rollback() {
    info "Performing sequential rollbacks..."
    
    for framework in "${FRAMEWORK_ARRAY[@]}"; do
        local backup_path=$(find_framework_backup "$framework")
        
        info "Rolling back $framework from backup: $backup_path"
        
        rollback_framework "$framework" "$backup_path"
        
        # Wait between rollbacks
        info "Waiting 30 seconds before next rollback..."
        sleep 30
    done
}

# Parallel rollback process (experimental)
parallel_rollback() {
    warning "Parallel rollback is experimental - use with caution"
    
    # Start all rollbacks in parallel
    local pids=()
    for framework in "${FRAMEWORK_ARRAY[@]}"; do
        local backup_path=$(find_framework_backup "$framework")
        
        info "Starting parallel rollback of $framework from backup: $backup_path"
        
        rollback_framework "$framework" "$backup_path" &
        pids+=($!)
    done
    
    # Wait for all rollbacks to complete
    info "Waiting for all rollbacks to complete..."
    for pid in "${pids[@]}"; do
        wait "$pid"
        if [ $? -ne 0 ]; then
            error_exit "One or more parallel rollbacks failed"
        fi
    done
    
    success "All parallel rollbacks completed"
}

# Validate system health after rollback
validate_system_health() {
    info "Validating system health after rollback..."
    
    # Run health checks for all services
    "$PROJECT_ROOT/scripts/health-check-all.sh"
    
    if [ $? -eq 0 ]; then
        success "System health validation passed"
    else
        warning "System health validation found issues - please review"
    fi
}

# Main coordination process
main() {
    echo -e "${RED}🔄 Multi-Framework Rollback Coordination${NC}"
    echo -e "${RED}======================================${NC}"
    echo "Frameworks: $FRAMEWORKS"
    echo "Backup base path: $BACKUP_BASE_PATH"
    echo "Mode: $([ "$SEQUENTIAL" = true ] && echo "Sequential" || echo "Parallel")"
    echo "Log file: $LOG_FILE"
    echo ""
    
    log "Starting coordinated rollback process"
    
    # Parse and validate frameworks
    parse_frameworks
    
    # Perform rollbacks
    if [ "$SEQUENTIAL" = true ]; then
        sequential_rollback
    else
        parallel_rollback
    fi
    
    # Validate system health
    validate_system_health
    
    success "All framework rollbacks completed successfully!"
    echo ""
    echo -e "${GREEN}📋 Rollback Summary${NC}"
    echo -e "${GREEN}==================${NC}"
    echo "Frameworks rolled back: ${FRAMEWORK_ARRAY[*]}"
    echo "Mode: $([ "$SEQUENTIAL" = true ] && echo "Sequential" || echo "Parallel")"
    echo "Backup base path: $BACKUP_BASE_PATH"
    echo "Log file: $LOG_FILE"
    echo ""
    echo -e "${YELLOW}📝 Next Steps${NC}"
    echo "1. Test all framework functionality"
    echo "2. Verify integrations between frameworks"
    echo "3. Monitor system performance"
    echo "4. Investigate the cause of the rollback"
    echo "5. Plan proper upgrade strategy"
    echo ""
    echo -e "${BLUE}🔧 Troubleshooting${NC}"
    echo "If issues occur:"
    echo "1. Check individual framework logs"
    echo "2. Verify service health: docker ps"
    echo "3. Test API endpoints for each framework"
    echo "4. Review system health check results"
    echo "5. Contact operations team if needed"
}

# Run main function
main "$@"
