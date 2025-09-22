#!/bin/bash

# n8n Framework Rollback Script
# Purpose: Safely rollback n8n to a previous version with data and configuration recovery
# Usage: ./rollback-n8n.sh --backup-path <backup-path> [--target-version <version>] [--dry-run] [--force]

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
LOG_FILE="/var/log/rollback/n8n-rollback-$(date +%Y%m%d-%H%M%S).log"
BACKUP_PATH=""
TARGET_VERSION=""
DRY_RUN=false
FORCE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --backup-path)
            BACKUP_PATH="$2"
            shift 2
            ;;
        --target-version)
            TARGET_VERSION="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 --backup-path <backup-path> [--target-version <version>] [--dry-run] [--force]"
            echo ""
            echo "Options:"
            echo "  --backup-path     Path to backup directory for rollback"
            echo "  --target-version  Target version to rollback to (optional)"
            echo "  --dry-run         Show what would be done without making changes"
            echo "  --force           Force rollback even if validation fails"
            echo "  -h, --help        Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate arguments
if [ -z "$BACKUP_PATH" ]; then
    echo -e "${RED}❌ Error: Backup path is required${NC}"
    echo "Usage: $0 --backup-path <backup-path>"
    exit 1
fi

if [ ! -d "$BACKUP_PATH" ]; then
    echo -e "${RED}❌ Error: Backup path does not exist: $BACKUP_PATH${NC}"
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

# Get current n8n version
get_current_version() {
    if docker ps --format "table {{.Names}}" | grep -q "^n8n$"; then
        local current_version=$(docker exec n8n n8n --version 2>/dev/null || echo "unknown")
        echo "$current_version"
    else
        echo "not_running"
    fi
}

# Validate backup
validate_backup() {
    info "Validating backup: $BACKUP_PATH"
    
    # Check backup manifest
    local manifest_file="$BACKUP_PATH/backup-manifest.json"
    if [ ! -f "$manifest_file" ]; then
        error_exit "Backup manifest not found: $manifest_file"
    fi
    
    # Parse backup manifest
    local backup_framework=$(jq -r '.framework // "unknown"' "$manifest_file")
    local backup_version=$(jq -r '.current_version // "unknown"' "$manifest_file")
    local backup_timestamp=$(jq -r '.timestamp // "unknown"' "$manifest_file")
    
    info "Backup details:"
    info "  Framework: $backup_framework"
    info "  Version: $backup_version"
    info "  Timestamp: $backup_timestamp"
    
    # Validate framework
    if [ "$backup_framework" != "n8n" ]; then
        error_exit "Backup is not for n8n framework: $backup_framework"
    fi
    
    # Check backup files
    local required_files=("n8n_data.tar.gz" "config.json" "docker-compose.yml.backup")
    for file in "${required_files[@]}"; do
        if [ ! -f "$BACKUP_PATH/$file" ]; then
            error_exit "Required backup file not found: $file"
        fi
    done
    
    success "Backup validation passed"
    echo "$backup_version"
}

# Pre-rollback validation
pre_rollback_validation() {
    info "Running pre-rollback validation..."
    
    # Check if n8n container is running
    local current_version=$(get_current_version)
    if [ "$current_version" = "not_running" ]; then
        warning "n8n container is not running - rollback will start service"
    else
        info "Current n8n version: $current_version"
    fi
    
    # Check database connectivity
    if docker ps --format "table {{.Names}}" | grep -q "^supabase-db$"; then
        if docker exec supabase-db pg_isready -U postgres >/dev/null 2>&1; then
            success "Database is ready for rollback"
        else
            error_exit "Database is not ready"
        fi
    else
        error_exit "Database container is not running"
    fi
    
    # Check disk space
    local available_space=$(df "$BACKUP_PATH" | awk 'NR==2 {print $4}')
    local required_space=1000000  # 1GB in KB
    
    if [ "$available_space" -lt "$required_space" ]; then
        warning "Low disk space: ${available_space}KB available, ${required_space}KB recommended"
    fi
    
    success "Pre-rollback validation completed"
}

# Stop n8n service
stop_n8n_service() {
    info "Stopping n8n service..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would stop n8n service"
        return 0
    fi
    
    cd "$PROJECT_ROOT"
    docker compose stop n8n
    
    # Wait for service to stop
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if ! docker ps --format "table {{.Names}}" | grep -q "^n8n$"; then
            break
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            error_exit "n8n service failed to stop within timeout"
        fi
        
        sleep 2
        attempt=$((attempt + 1))
    done
    
    success "n8n service stopped"
}

# Restore n8n data
restore_n8n_data() {
    info "Restoring n8n data from backup..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would restore n8n data from $BACKUP_PATH/n8n_data.tar.gz"
        return 0
    fi
    
    # Remove existing data volume
    if docker volume ls | grep -q "n8n_data"; then
        info "Removing existing n8n data volume..."
        docker volume rm n8n_data
    fi
    
    # Create new data volume
    info "Creating new n8n data volume..."
    docker volume create n8n_data
    
    # Restore data from backup
    info "Restoring data from backup..."
    docker run --rm -v n8n_data:/target -v "$BACKUP_PATH":/backup alpine tar xzf /backup/n8n_data.tar.gz -C /target
    
    success "n8n data restored"
}

# Restore n8n configuration
restore_n8n_configuration() {
    info "Restoring n8n configuration..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would restore n8n configuration from $BACKUP_PATH/config.json"
        return 0
    fi
    
    # Restore Docker Compose configuration
    if [ -f "$BACKUP_PATH/docker-compose.yml.backup" ]; then
        info "Restoring Docker Compose configuration..."
        cp "$BACKUP_PATH/docker-compose.yml.backup" "$PROJECT_ROOT/docker-compose.yml"
    fi
    
    success "n8n configuration restored"
}

# Start n8n service
start_n8n_service() {
    info "Starting n8n service..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would start n8n service"
        return 0
    fi
    
    cd "$PROJECT_ROOT"
    docker compose up -d n8n
    
    # Wait for service to be healthy
    info "Waiting for n8n service to be healthy..."
    local max_attempts=60
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if docker exec n8n n8n --version >/dev/null 2>&1; then
            break
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            error_exit "n8n service failed to start within timeout"
        fi
        
        sleep 5
        attempt=$((attempt + 1))
    done
    
    success "n8n service started"
}

# Post-rollback validation
post_rollback_validation() {
    info "Running post-rollback validation..."
    
    # Verify version
    local actual_version=$(get_current_version)
    if [ -n "$TARGET_VERSION" ] && [ "$actual_version" != "$TARGET_VERSION" ]; then
        warning "Version mismatch: expected $TARGET_VERSION, got $actual_version"
    else
        success "n8n version verified: $actual_version"
    fi
    
    # Check service health
    info "Checking service health..."
    if ! docker exec n8n n8n --version >/dev/null 2>&1; then
        error_exit "n8n service is not responding"
    fi
    
    # Test API endpoints
    info "Testing API endpoints..."
    local health_response=$(curl -s -w "%{http_code}" http://localhost:5678/health 2>/dev/null || echo "000")
    local http_code="${health_response: -3}"
    
    if [ "$http_code" = "200" ]; then
        success "n8n health endpoint is accessible"
    else
        warning "n8n health endpoint returned HTTP $http_code"
    fi
    
    # Test workflows
    info "Testing workflow functionality..."
    local workflows_response=$(curl -s -w "%{http_code}" http://localhost:5678/rest/workflows 2>/dev/null || echo "000")
    local http_code="${workflows_response: -3}"
    
    if [ "$http_code" = "200" ]; then
        success "n8n workflows endpoint is accessible"
    else
        warning "n8n workflows endpoint returned HTTP $http_code"
    fi
    
    # Check for error logs
    info "Checking for error logs..."
    local error_count=$(docker logs n8n --since 5m 2>&1 | grep -i error | wc -l)
    if [ "$error_count" -gt 10 ]; then
        warning "Found $error_count errors in recent logs - please review"
    else
        success "No significant errors found in recent logs"
    fi
    
    success "Post-rollback validation completed"
}

# Update version lock file
update_version_lock() {
    info "Updating version lock file..."
    
    local lock_file="$PROJECT_ROOT/config/versions/versions.lock.yml"
    local rollback_version=$(jq -r '.current_version // "unknown"' "$BACKUP_PATH/backup-manifest.json")
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would update version lock file with version $rollback_version"
        return 0
    fi
    
    # Update the lock file
    sed -i.bak "s|tag: \"[^\"]*\"|tag: \"$rollback_version\"|" "$lock_file"
    sed -i.bak "s|version: \"[^\"]*\"|version: \"$rollback_version\"|" "$lock_file"
    sed -i.bak "s|last_updated: \"[^\"]*\"|last_updated: \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"|" "$lock_file"
    
    success "Version lock file updated"
}

# Main rollback process
main() {
    echo -e "${BLUE}🔄 n8n Framework Rollback${NC}"
    echo -e "${BLUE}========================${NC}"
    echo "Backup path: $BACKUP_PATH"
    echo "Target version: ${TARGET_VERSION:-auto}"
    echo "Dry run: $DRY_RUN"
    echo "Force: $FORCE"
    echo "Log file: $LOG_FILE"
    echo ""
    
    log "Starting n8n rollback process"
    
    # Validate backup
    local backup_version=$(validate_backup)
    
    # Pre-rollback validation
    pre_rollback_validation
    
    # Stop n8n service
    stop_n8n_service
    
    # Restore data and configuration
    restore_n8n_data
    restore_n8n_configuration
    
    # Start n8n service
    start_n8n_service
    
    # Post-rollback validation
    post_rollback_validation
    
    # Update version lock file
    update_version_lock
    
    success "n8n rollback completed successfully!"
    echo ""
    echo -e "${GREEN}📋 Rollback Summary${NC}"
    echo -e "${GREEN}==================${NC}"
    echo "Rollback version: $backup_version"
    echo "Current version: $(get_current_version)"
    echo "Backup location: $BACKUP_PATH"
    echo "Log file: $LOG_FILE"
    echo ""
    echo -e "${YELLOW}📝 Next Steps${NC}"
    echo "1. Test n8n functionality thoroughly"
    echo "2. Verify workflows are working"
    echo "3. Check integrations with other services"
    echo "4. Monitor system performance"
    echo "5. Plan next upgrade attempt if needed"
    echo ""
    echo -e "${BLUE}🔧 Troubleshooting${NC}"
    echo "If issues occur:"
    echo "1. Check logs: $LOG_FILE"
    echo "2. Verify service health: docker logs n8n"
    echo "3. Test API endpoints: curl http://localhost:5678/health"
    echo "4. Contact operations team if needed"
}

# Run main function
main "$@"
