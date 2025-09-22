#!/bin/bash

# Letta Framework Rollback Script
# Purpose: Safely rollback Letta to a previous version with data and configuration recovery
# Usage: ./rollback-letta.sh --backup-path <backup-path> [--target-version <version>] [--dry-run] [--force]

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
LOG_FILE="/var/log/rollback/letta-rollback-$(date +%Y%m%d-%H%M%S).log"
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

# Get current Letta version
get_current_version() {
    if docker ps --format "table {{.Names}}" | grep -q "^ai-pa-letta-1$"; then
        local current_version=$(curl -s http://localhost:8283/v1/health/ 2>/dev/null | jq -r '.version // "unknown"' || echo "unknown")
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
    if [ "$backup_framework" != "letta" ]; then
        error_exit "Backup is not for Letta framework: $backup_framework"
    fi
    
    # Check backup files
    local required_files=("letta_database.sql" "agents.json")
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
    
    # Check if Letta container is running
    local current_version=$(get_current_version)
    if [ "$current_version" = "not_running" ]; then
        warning "Letta container is not running - rollback will start service"
    else
        info "Current Letta version: $current_version"
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

# Stop Letta service
stop_letta_service() {
    info "Stopping Letta service..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would stop Letta service"
        return 0
    fi
    
    cd "$PROJECT_ROOT"
    docker compose stop letta
    
    # Wait for service to stop
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if ! docker ps --format "table {{.Names}}" | grep -q "^ai-pa-letta-1$"; then
            break
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            error_exit "Letta service failed to stop within timeout"
        fi
        
        sleep 2
        attempt=$((attempt + 1))
    done
    
    success "Letta service stopped"
}

# Restore Letta database
restore_letta_database() {
    info "Restoring Letta database from backup..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would restore Letta database from $BACKUP_PATH/letta_database.sql"
        return 0
    fi
    
    # Drop existing Letta schemas
    info "Dropping existing Letta schemas..."
    docker exec supabase-db psql -U postgres -c "DROP SCHEMA IF EXISTS letta_agents CASCADE;" 2>/dev/null || true
    docker exec supabase-db psql -U postgres -c "DROP SCHEMA IF EXISTS letta_embeddings CASCADE;" 2>/dev/null || true
    
    # Restore database from backup
    info "Restoring database from backup..."
    docker exec -i supabase-db psql -U postgres < "$BACKUP_PATH/letta_database.sql"
    
    success "Letta database restored"
}

# Restore Letta configuration
restore_letta_configuration() {
    info "Restoring Letta configuration..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would restore Letta configuration"
        return 0
    fi
    
    # Restore MCP configuration
    if [ -f "$BACKUP_PATH/letta_mcp_config.json" ]; then
        info "Restoring MCP configuration..."
        cp "$BACKUP_PATH/letta_mcp_config.json" "$PROJECT_ROOT/letta/letta_mcp_config.json"
    fi
    
    # Restore Docker Compose configuration
    if [ -f "$BACKUP_PATH/docker-compose.yml.backup" ]; then
        info "Restoring Docker Compose configuration..."
        cp "$BACKUP_PATH/docker-compose.yml.backup" "$PROJECT_ROOT/docker-compose.yml"
    fi
    
    success "Letta configuration restored"
}

# Start Letta service
start_letta_service() {
    info "Starting Letta service..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would start Letta service"
        return 0
    fi
    
    cd "$PROJECT_ROOT"
    docker compose up -d letta
    
    # Wait for service to be healthy
    info "Waiting for Letta service to be healthy..."
    local max_attempts=60
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s http://localhost:8283/v1/health/ >/dev/null 2>&1; then
            break
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            error_exit "Letta service failed to start within timeout"
        fi
        
        sleep 5
        attempt=$((attempt + 1))
    done
    
    success "Letta service started"
}

# Restore agent configurations
restore_agent_configurations() {
    info "Restoring agent configurations..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would restore agent configurations from $BACKUP_PATH/agents.json"
        return 0
    fi
    
    # Wait for Letta service to be ready
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s http://localhost:8283/v1/health/ >/dev/null 2>&1; then
            break
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            warning "Letta service not ready - skipping agent configuration restore"
            return 0
        fi
        
        sleep 2
        attempt=$((attempt + 1))
    done
    
    # Restore agent configurations via API
    if [ -f "$BACKUP_PATH/agents.json" ]; then
        info "Restoring agent configurations..."
        
        # Parse and restore each agent
        local agent_count=$(jq '. | length' "$BACKUP_PATH/agents.json" 2>/dev/null || echo "0")
        info "Found $agent_count agents to restore"
        
        if [ "$agent_count" -gt 0 ]; then
            jq -c '.[]' "$BACKUP_PATH/agents.json" 2>/dev/null | while read -r agent; do
                local agent_name=$(echo "$agent" | jq -r '.name // "unknown"')
                info "Restoring agent: $agent_name"
                
                # Restore agent via API
                curl -s -X POST http://localhost:8283/v1/agents \
                    -H "Content-Type: application/json" \
                    -d "$agent" >/dev/null 2>&1 || warning "Failed to restore agent: $agent_name"
            done
        fi
    fi
    
    success "Agent configurations restored"
}

# Post-rollback validation
post_rollback_validation() {
    info "Running post-rollback validation..."
    
    # Verify version
    local actual_version=$(get_current_version)
    if [ -n "$TARGET_VERSION" ] && [ "$actual_version" != "$TARGET_VERSION" ]; then
        warning "Version mismatch: expected $TARGET_VERSION, got $actual_version"
    else
        success "Letta version verified: $actual_version"
    fi
    
    # Check service health
    info "Checking service health..."
    if ! curl -s http://localhost:8283/v1/health/ >/dev/null 2>&1; then
        error_exit "Letta service is not responding"
    fi
    
    # Test health endpoint
    local health_response=$(curl -s http://localhost:8283/v1/health/ 2>/dev/null || echo "")
    if [ -n "$health_response" ]; then
        success "Letta health endpoint is accessible"
        
        # Parse health response
        local db_status=$(echo "$health_response" | jq -r '.database // "unknown"')
        if [ "$db_status" = "healthy" ]; then
            success "Letta database connectivity is healthy"
        else
            warning "Letta database status: $db_status"
        fi
    else
        error_exit "Letta health endpoint is not responding"
    fi
    
    # Test agents endpoint
    info "Testing agents endpoint..."
    local agents_response=$(curl -s -w "%{http_code}" http://localhost:8283/v1/agents 2>/dev/null || echo "000")
    local http_code="${agents_response: -3}"
    
    if [ "$http_code" = "200" ]; then
        success "Letta agents endpoint is accessible"
        
        # Check agent count
        local agent_count=$(echo "${agents_response%???}" | jq '. | length' 2>/dev/null || echo "0")
        info "Active agents after rollback: $agent_count"
    else
        warning "Letta agents endpoint returned HTTP $http_code"
    fi
    
    # Test MCP servers endpoint
    info "Testing MCP servers endpoint..."
    local mcp_response=$(curl -s -w "%{http_code}" http://localhost:8283/v1/mcp/servers 2>/dev/null || echo "000")
    local http_code="${mcp_response: -3}"
    
    if [ "$http_code" = "200" ]; then
        success "Letta MCP servers endpoint is accessible"
    else
        warning "Letta MCP servers endpoint returned HTTP $http_code"
    fi
    
    # Check for error logs
    info "Checking for error logs..."
    local error_count=$(docker logs ai-pa-letta-1 --since 5m 2>&1 | grep -i error | wc -l)
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
    echo -e "${BLUE}🔄 Letta Framework Rollback${NC}"
    echo -e "${BLUE}========================${NC}"
    echo "Backup path: $BACKUP_PATH"
    echo "Target version: ${TARGET_VERSION:-auto}"
    echo "Dry run: $DRY_RUN"
    echo "Force: $FORCE"
    echo "Log file: $LOG_FILE"
    echo ""
    
    log "Starting Letta rollback process"
    
    # Validate backup
    local backup_version=$(validate_backup)
    
    # Pre-rollback validation
    pre_rollback_validation
    
    # Stop Letta service
    stop_letta_service
    
    # Restore data and configuration
    restore_letta_database
    restore_letta_configuration
    
    # Start Letta service
    start_letta_service
    
    # Restore agent configurations
    restore_agent_configurations
    
    # Post-rollback validation
    post_rollback_validation
    
    # Update version lock file
    update_version_lock
    
    success "Letta rollback completed successfully!"
    echo ""
    echo -e "${GREEN}📋 Rollback Summary${NC}"
    echo -e "${GREEN}==================${NC}"
    echo "Rollback version: $backup_version"
    echo "Current version: $(get_current_version)"
    echo "Backup location: $BACKUP_PATH"
    echo "Log file: $LOG_FILE"
    echo ""
    echo -e "${YELLOW}📝 Next Steps${NC}"
    echo "1. Test Letta functionality thoroughly"
    echo "2. Verify agents are working correctly"
    echo "3. Test MCP server integrations"
    echo "4. Check integrations with other services"
    echo "5. Monitor system performance"
    echo "6. Plan next upgrade attempt if needed"
    echo ""
    echo -e "${BLUE}🔧 Troubleshooting${NC}"
    echo "If issues occur:"
    echo "1. Check logs: $LOG_FILE"
    echo "2. Verify service health: docker logs ai-pa-letta-1"
    echo "3. Test API endpoints: curl http://localhost:8283/v1/health/"
    echo "4. Check database connectivity: docker exec supabase-db psql -U postgres -c 'SELECT 1;'"
    echo "5. Contact operations team if needed"
}

# Run main function
main "$@"
