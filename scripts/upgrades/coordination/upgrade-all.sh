#!/bin/bash

# Multi-Framework Upgrade Coordination Script
# Purpose: Coordinate upgrades of multiple frameworks with proper sequencing and validation
# Usage: ./upgrade-all.sh --frameworks "n8n,letta,graphiti" [--dry-run] [--sequential]

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
LOG_FILE="/var/log/upgrades/coordinated-upgrade-$(date +%Y%m%d-%H%M%S).log"
FRAMEWORKS=""
DRY_RUN=false
SEQUENTIAL=false
PARALLEL=false

# Framework upgrade order (dependencies)
FRAMEWORK_ORDER=("n8n" "letta" "graphiti")

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --frameworks)
            FRAMEWORKS="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --sequential)
            SEQUENTIAL=true
            shift
            ;;
        --parallel)
            PARALLEL=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 --frameworks \"<framework1>,<framework2>,...\" [--dry-run] [--sequential|--parallel]"
            echo ""
            echo "Options:"
            echo "  --frameworks   Comma-separated list of frameworks to upgrade"
            echo "  --dry-run      Show what would be done without making changes"
            echo "  --sequential   Upgrade frameworks one at a time (default)"
            echo "  --parallel     Upgrade frameworks in parallel (experimental)"
            echo "  -h, --help     Show this help message"
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
if [ -z "$FRAMEWORKS" ]; then
    echo -e "${RED}❌ Error: Frameworks list is required${NC}"
    echo "Usage: $0 --frameworks \"<framework1>,<framework2>,...\""
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
    
    info "Frameworks to upgrade: ${FRAMEWORK_ARRAY[*]}"
}

# Get target version for framework
get_target_version() {
    local framework="$1"
    
    case "$framework" in
        "n8n")
            echo "1.110.0"  # Example target version
            ;;
        "letta")
            echo "0.12.0"   # Example target version
            ;;
        "graphiti")
            echo "0.19.0"   # Example target version
            ;;
        *)
            error_exit "Unknown framework: $framework"
            ;;
    esac
}

# Get current version for framework
get_current_version() {
    local framework="$1"
    
    case "$framework" in
        "n8n")
            if docker ps --format "table {{.Names}}" | grep -q "^n8n$"; then
                docker exec n8n n8n --version 2>/dev/null || echo "unknown"
            else
                echo "not_running"
            fi
            ;;
        "letta")
            if docker ps --format "table {{.Names}}" | grep -q "^ai-pa-letta-1$"; then
                curl -s http://localhost:8283/v1/health/ 2>/dev/null | jq -r '.version // "unknown"' || echo "unknown"
            else
                echo "not_running"
            fi
            ;;
        "graphiti")
            local pyproject_file="$PROJECT_ROOT/graphiti/pyproject.toml"
            if [ -f "$pyproject_file" ]; then
                grep -o 'version[[:space:]]*=[[:space:]]*"[^"]*"' "$pyproject_file" | cut -d'"' -f2
            else
                echo "unknown"
            fi
            ;;
        *)
            error_exit "Unknown framework: $framework"
            ;;
    esac
}

# Run pre-upgrade validation
run_pre_upgrade_validation() {
    info "Running pre-upgrade validation..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would run pre-upgrade validation"
        return 0
    fi
    
    "$PROJECT_ROOT/scripts/upgrades/validation/pre-upgrade-check.sh"
    
    if [ $? -eq 0 ]; then
        success "Pre-upgrade validation passed"
    else
        error_exit "Pre-upgrade validation failed"
    fi
}

# Create system backup
create_system_backup() {
    info "Creating system backup..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would create system backup"
        return 0
    fi
    
    local backup_timestamp=$(date +%Y%m%d-%H%M%S)
    local backup_path="/var/backups/upgrades/system-backup-$backup_timestamp"
    
    mkdir -p "$backup_path"
    
    # Backup Docker Compose configuration
    cp "$PROJECT_ROOT/docker-compose.yml" "$backup_path/"
    
    # Backup version lock file
    cp "$PROJECT_ROOT/config/versions/versions.lock.yml" "$backup_path/" 2>/dev/null || true
    
    # Backup environment files
    cp "$PROJECT_ROOT/.env" "$backup_path/" 2>/dev/null || true
    
    # Create backup manifest
    cat > "$backup_path/backup-manifest.json" << EOF
{
    "timestamp": "$backup_timestamp",
    "type": "system_backup",
    "frameworks": "${FRAMEWORK_ARRAY[*]}",
    "files": [
        "docker-compose.yml",
        "versions.lock.yml",
        ".env"
    ]
}
EOF
    
    success "System backup created: $backup_path"
    echo "$backup_path"
}

# Upgrade single framework
upgrade_framework() {
    local framework="$1"
    local target_version="$2"
    
    info "Upgrading $framework to version $target_version..."
    
    local upgrade_script="$PROJECT_ROOT/scripts/upgrades/$framework/upgrade-$framework.sh"
    
    if [ ! -f "$upgrade_script" ]; then
        error_exit "Upgrade script not found: $upgrade_script"
    fi
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would upgrade $framework to $target_version"
        return 0
    fi
    
    # Run the framework-specific upgrade script
    "$upgrade_script" --version "$target_version"
    
    if [ $? -eq 0 ]; then
        success "$framework upgrade completed successfully"
    else
        error_exit "$framework upgrade failed"
    fi
}

# Run post-upgrade validation
run_post_upgrade_validation() {
    info "Running post-upgrade validation..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would run post-upgrade validation"
        return 0
    fi
    
    # Run health checks for all services
    "$PROJECT_ROOT/scripts/health-check-all.sh"
    
    if [ $? -eq 0 ]; then
        success "Post-upgrade validation passed"
    else
        warning "Post-upgrade validation found issues - please review"
    fi
}

# Sequential upgrade process
sequential_upgrade() {
    info "Performing sequential upgrades..."
    
    local backup_path=$(create_system_backup)
    
    for framework in "${FRAMEWORK_ARRAY[@]}"; do
        local current_version=$(get_current_version "$framework")
        local target_version=$(get_target_version "$framework")
        
        info "Upgrading $framework from $current_version to $target_version"
        
        upgrade_framework "$framework" "$target_version"
        
        # Wait between upgrades
        if [ "$DRY_RUN" = false ]; then
            info "Waiting 30 seconds before next upgrade..."
            sleep 30
        fi
    done
}

# Parallel upgrade process (experimental)
parallel_upgrade() {
    warning "Parallel upgrade is experimental - use with caution"
    
    local backup_path=$(create_system_backup)
    
    # Start all upgrades in parallel
    local pids=()
    for framework in "${FRAMEWORK_ARRAY[@]}"; do
        local target_version=$(get_target_version "$framework")
        
        info "Starting parallel upgrade of $framework to $target_version"
        
        if [ "$DRY_RUN" = false ]; then
            upgrade_framework "$framework" "$target_version" &
            pids+=($!)
        else
            info "DRY RUN: Would start parallel upgrade of $framework"
        fi
    done
    
    # Wait for all upgrades to complete
    if [ "$DRY_RUN" = false ]; then
        info "Waiting for all upgrades to complete..."
        for pid in "${pids[@]}"; do
            wait "$pid"
            if [ $? -ne 0 ]; then
                error_exit "One or more parallel upgrades failed"
            fi
        done
    fi
    
    success "All parallel upgrades completed"
}

# Main coordination process
main() {
    echo -e "${BLUE}🚀 Multi-Framework Upgrade Coordination${NC}"
    echo -e "${BLUE}======================================${NC}"
    echo "Frameworks: $FRAMEWORKS"
    echo "Mode: $([ "$SEQUENTIAL" = true ] && echo "Sequential" || echo "Parallel")"
    echo "Dry run: $DRY_RUN"
    echo "Log file: $LOG_FILE"
    echo ""
    
    log "Starting coordinated upgrade process"
    
    # Parse and validate frameworks
    parse_frameworks
    
    # Run pre-upgrade validation
    run_pre_upgrade_validation
    
    # Perform upgrades
    if [ "$SEQUENTIAL" = true ] || [ "$PARALLEL" = false ]; then
        sequential_upgrade
    else
        parallel_upgrade
    fi
    
    # Run post-upgrade validation
    run_post_upgrade_validation
    
    success "All framework upgrades completed successfully!"
    echo ""
    echo -e "${GREEN}📋 Upgrade Summary${NC}"
    echo -e "${GREEN}==================${NC}"
    echo "Frameworks upgraded: ${FRAMEWORK_ARRAY[*]}"
    echo "Mode: $([ "$SEQUENTIAL" = true ] && echo "Sequential" || echo "Parallel")"
    echo "Log file: $LOG_FILE"
    echo ""
    echo -e "${YELLOW}📝 Next Steps${NC}"
    echo "1. Test all framework functionality"
    echo "2. Verify integrations between frameworks"
    echo "3. Monitor system performance"
    echo "4. Update documentation if needed"
    echo ""
    echo -e "${BLUE}🔧 Rollback Instructions${NC}"
    echo "If issues occur, use individual framework rollback scripts:"
    for framework in "${FRAMEWORK_ARRAY[@]}"; do
        echo "./scripts/upgrades/rollback/rollback-$framework.sh --backup-path <backup-path>"
    done
}

# Run main function
main "$@"
