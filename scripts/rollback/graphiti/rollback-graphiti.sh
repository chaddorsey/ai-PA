#!/bin/bash

# Graphiti Framework Rollback Script
# Purpose: Safely rollback Graphiti to a previous version with data and configuration recovery
# Usage: ./rollback-graphiti.sh --backup-path <backup-path> [--target-version <version>] [--dry-run] [--force]

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
LOG_FILE="/var/log/rollback/graphiti-rollback-$(date +%Y%m%d-%H%M%S).log"
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

# Get current Graphiti version
get_current_version() {
    local pyproject_file="$PROJECT_ROOT/graphiti/pyproject.toml"
    if [ -f "$pyproject_file" ]; then
        local current_version=$(grep -o 'version[[:space:]]*=[[:space:]]*"[^"]*"' "$pyproject_file" | cut -d'"' -f2)
        echo "$current_version"
    else
        echo "unknown"
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
    if [ "$backup_framework" != "graphiti" ]; then
        error_exit "Backup is not for Graphiti framework: $backup_framework"
    fi
    
    # Check backup files
    local required_files=("graphiti_source.tar.gz")
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
    
    # Check current version
    local current_version=$(get_current_version)
    info "Current Graphiti version: $current_version"
    
    # Check if Graphiti MCP server is running
    if docker ps --format "table {{.Names}}" | grep -q "^graphiti-mcp-server$"; then
        info "Graphiti MCP server is running"
    else
        info "Graphiti MCP server is not running"
    fi
    
    # Check Neo4j connectivity
    if docker ps --format "table {{.Names}}" | grep -q "^graphiti-neo4j$"; then
        if docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "RETURN 1;" >/dev/null 2>&1; then
            success "Neo4j is ready for rollback"
        else
            error_exit "Neo4j is not ready"
        fi
    else
        error_exit "Neo4j container is not running"
    fi
    
    # Check Python environment
    if [ -f "$PROJECT_ROOT/graphiti/pyproject.toml" ]; then
        success "Python project configuration found"
    else
        error_exit "Python project configuration not found"
    fi
    
    # Check disk space
    local available_space=$(df "$BACKUP_PATH" | awk 'NR==2 {print $4}')
    local required_space=1000000  # 1GB in KB
    
    if [ "$available_space" -lt "$required_space" ]; then
        warning "Low disk space: ${available_space}KB available, ${required_space}KB recommended"
    fi
    
    success "Pre-rollback validation completed"
}

# Stop Graphiti MCP server
stop_graphiti_service() {
    info "Stopping Graphiti MCP server..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would stop Graphiti MCP server"
        return 0
    fi
    
    cd "$PROJECT_ROOT"
    docker compose stop graphiti-mcp-server
    
    # Wait for service to stop
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if ! docker ps --format "table {{.Names}}" | grep -q "^graphiti-mcp-server$"; then
            break
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            error_exit "Graphiti MCP server failed to stop within timeout"
        fi
        
        sleep 2
        attempt=$((attempt + 1))
    done
    
    success "Graphiti MCP server stopped"
}

# Restore Graphiti source code
restore_graphiti_source() {
    info "Restoring Graphiti source code from backup..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would restore Graphiti source code from $BACKUP_PATH/graphiti_source.tar.gz"
        return 0
    fi
    
    # Backup current source code
    local current_backup="/tmp/graphiti-current-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
    info "Creating backup of current source code: $current_backup"
    tar czf "$current_backup" -C "$PROJECT_ROOT" graphiti/
    
    # Remove current source code
    info "Removing current Graphiti source code..."
    rm -rf "$PROJECT_ROOT/graphiti"
    
    # Restore source code from backup
    info "Restoring source code from backup..."
    tar xzf "$BACKUP_PATH/graphiti_source.tar.gz" -C "$PROJECT_ROOT"
    
    success "Graphiti source code restored"
}

# Restore Neo4j data
restore_neo4j_data() {
    info "Restoring Neo4j data from backup..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would restore Neo4j data from $BACKUP_PATH/neo4j_dump.sql"
        return 0
    fi
    
    if [ -f "$BACKUP_PATH/neo4j_dump.sql" ]; then
        info "Restoring Neo4j data from dump..."
        
        # Stop Neo4j service
        docker compose stop graphiti-neo4j
        
        # Remove existing data
        docker volume rm graphiti_neo4j_data 2>/dev/null || true
        docker volume create graphiti_neo4j_data
        
        # Start Neo4j service
        docker compose up -d graphiti-neo4j
        
        # Wait for Neo4j to be ready
        local max_attempts=60
        local attempt=1
        
        while [ $attempt -le $max_attempts ]; do
            if docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "RETURN 1;" >/dev/null 2>&1; then
                break
            fi
            
            if [ $attempt -eq $max_attempts ]; then
                error_exit "Neo4j failed to start within timeout"
            fi
            
            sleep 5
            attempt=$((attempt + 1))
        done
        
        # Restore data from dump
        docker exec -i graphiti-neo4j neo4j-admin load --database=neo4j --from=/dev/stdin < "$BACKUP_PATH/neo4j_dump.sql"
        
        success "Neo4j data restored"
    else
        info "No Neo4j dump found - skipping data restoration"
    fi
}

# Restore Graphiti configuration
restore_graphiti_configuration() {
    info "Restoring Graphiti configuration..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would restore Graphiti configuration"
        return 0
    fi
    
    # Restore MCP server configuration
    if [ -f "$BACKUP_PATH/graphiti_mcp_server.py" ]; then
        info "Restoring MCP server configuration..."
        cp "$BACKUP_PATH/graphiti_mcp_server.py" "$PROJECT_ROOT/graphiti/mcp_server/"
    fi
    
    # Restore Docker Compose configuration
    if [ -f "$BACKUP_PATH/docker-compose.yml.backup" ]; then
        info "Restoring Docker Compose configuration..."
        cp "$BACKUP_PATH/docker-compose.yml.backup" "$PROJECT_ROOT/docker-compose.yml"
    fi
    
    success "Graphiti configuration restored"
}

# Rebuild Graphiti MCP server
rebuild_graphiti_service() {
    info "Rebuilding Graphiti MCP server..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would rebuild Graphiti MCP server"
        return 0
    fi
    
    cd "$PROJECT_ROOT"
    
    # Rebuild the container
    info "Rebuilding Graphiti MCP server container..."
    docker compose build graphiti-mcp-server
    
    # Start the service
    info "Starting Graphiti MCP server..."
    docker compose up -d graphiti-mcp-server
    
    # Wait for service to be healthy
    info "Waiting for Graphiti MCP server to be healthy..."
    local max_attempts=60
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s http://localhost:8082/health >/dev/null 2>&1; then
            break
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            error_exit "Graphiti MCP server failed to start within timeout"
        fi
        
        sleep 5
        attempt=$((attempt + 1))
    done
    
    success "Graphiti MCP server rebuilt and started"
}

# Post-rollback validation
post_rollback_validation() {
    info "Running post-rollback validation..."
    
    # Verify version in pyproject.toml
    local actual_version=$(get_current_version)
    if [ -n "$TARGET_VERSION" ] && [ "$actual_version" != "$TARGET_VERSION" ]; then
        warning "Version mismatch: expected $TARGET_VERSION, got $actual_version"
    else
        success "Graphiti version verified: $actual_version"
    fi
    
    # Check service health
    info "Checking Graphiti MCP server health..."
    if ! curl -s http://localhost:8082/health >/dev/null 2>&1; then
        error_exit "Graphiti MCP server is not responding"
    fi
    
    # Test health endpoint
    local health_response=$(curl -s http://localhost:8082/health 2>/dev/null || echo "")
    if [ -n "$health_response" ]; then
        success "Graphiti health endpoint is accessible"
    else
        error_exit "Graphiti health endpoint is not responding"
    fi
    
    # Test MCP endpoints
    info "Testing MCP endpoints..."
    local mcp_response=$(curl -s -w "%{http_code}" http://localhost:8082/mcp 2>/dev/null || echo "000")
    local http_code="${mcp_response: -3}"
    
    if [ "$http_code" = "200" ]; then
        success "Graphiti MCP endpoint is accessible"
    else
        warning "Graphiti MCP endpoint returned HTTP $http_code"
    fi
    
    # Validate Neo4j connectivity
    info "Validating Neo4j connectivity..."
    if docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "RETURN 1;" >/dev/null 2>&1; then
        success "Neo4j connectivity is working"
    else
        warning "Neo4j connectivity test failed"
    fi
    
    # Test Python package installation
    info "Validating Python package installation..."
    if docker exec graphiti-mcp-server python -c "import graphiti_core; print(graphiti_core.__version__)" >/dev/null 2>&1; then
        success "Graphiti core package is properly installed"
    else
        warning "Graphiti core package validation failed"
    fi
    
    # Check for error logs
    info "Checking for error logs..."
    local error_count=$(docker logs graphiti-mcp-server --since 5m 2>&1 | grep -i error | wc -l)
    if [ "$error_count" -gt 5 ]; then
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
    sed -i.bak "s|version: \"[^\"]*\"|version: \"$rollback_version\"|" "$lock_file"
    sed -i.bak "s|last_updated: \"[^\"]*\"|last_updated: \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"|" "$lock_file"
    
    success "Version lock file updated"
}

# Main rollback process
main() {
    echo -e "${BLUE}🔄 Graphiti Framework Rollback${NC}"
    echo -e "${BLUE}===========================${NC}"
    echo "Backup path: $BACKUP_PATH"
    echo "Target version: ${TARGET_VERSION:-auto}"
    echo "Dry run: $DRY_RUN"
    echo "Force: $FORCE"
    echo "Log file: $LOG_FILE"
    echo ""
    
    log "Starting Graphiti rollback process"
    
    # Validate backup
    local backup_version=$(validate_backup)
    
    # Pre-rollback validation
    pre_rollback_validation
    
    # Stop Graphiti service
    stop_graphiti_service
    
    # Restore data and configuration
    restore_graphiti_source
    restore_neo4j_data
    restore_graphiti_configuration
    
    # Rebuild and start service
    rebuild_graphiti_service
    
    # Post-rollback validation
    post_rollback_validation
    
    # Update version lock file
    update_version_lock
    
    success "Graphiti rollback completed successfully!"
    echo ""
    echo -e "${GREEN}📋 Rollback Summary${NC}"
    echo -e "${GREEN}==================${NC}"
    echo "Rollback version: $backup_version"
    echo "Current version: $(get_current_version)"
    echo "Backup location: $BACKUP_PATH"
    echo "Log file: $LOG_FILE"
    echo ""
    echo -e "${YELLOW}📝 Next Steps${NC}"
    echo "1. Test Graphiti functionality thoroughly"
    echo "2. Verify knowledge graph operations"
    echo "3. Test MCP server integrations"
    echo "4. Check integrations with other services"
    echo "5. Monitor system performance"
    echo "6. Plan next upgrade attempt if needed"
    echo ""
    echo -e "${BLUE}🔧 Troubleshooting${NC}"
    echo "If issues occur:"
    echo "1. Check logs: $LOG_FILE"
    echo "2. Verify service health: docker logs graphiti-mcp-server"
    echo "3. Test API endpoints: curl http://localhost:8082/health"
    echo "4. Check Neo4j connectivity: docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo 'RETURN 1;'"
    echo "5. Verify Python package: docker exec graphiti-mcp-server python -c 'import graphiti_core'"
    echo "6. Contact operations team if needed"
}

# Run main function
main "$@"
