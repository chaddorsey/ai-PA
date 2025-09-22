#!/bin/bash

# Graphiti Framework Upgrade Script
# Purpose: Safely upgrade Graphiti to a specified version with validation and rollback capability
# Usage: ./upgrade-graphiti.sh --version <target-version> [--dry-run] [--force]

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
LOG_FILE="/var/log/upgrades/graphiti-upgrade-$(date +%Y%m%d-%H%M%S).log"
BACKUP_DIR="/var/backups/upgrades/graphiti"
DRY_RUN=false
FORCE=false
TARGET_VERSION=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --version)
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
            echo "Usage: $0 --version <target-version> [--dry-run] [--force]"
            echo ""
            echo "Options:"
            echo "  --version    Target Graphiti version (e.g., 0.19.0)"
            echo "  --dry-run    Show what would be done without making changes"
            echo "  --force      Force upgrade even if validation fails"
            echo "  -h, --help   Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate arguments
if [ -z "$TARGET_VERSION" ]; then
    echo -e "${RED}❌ Error: Target version is required${NC}"
    echo "Usage: $0 --version <target-version>"
    exit 1
fi

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$BACKUP_DIR"

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

# Validate target version
validate_target_version() {
    info "Validating target version: $TARGET_VERSION"
    
    # Check if version format is valid (semantic versioning)
    if [[ ! $TARGET_VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        error_exit "Invalid version format: $TARGET_VERSION (expected: X.Y.Z)"
    fi
    
    # Check if Graphiti directory exists
    if [ ! -d "$PROJECT_ROOT/graphiti" ]; then
        error_exit "Graphiti directory not found: $PROJECT_ROOT/graphiti"
    fi
    
    # Check if pyproject.toml exists
    if [ ! -f "$PROJECT_ROOT/graphiti/pyproject.toml" ]; then
        error_exit "Graphiti pyproject.toml not found"
    fi
    
    success "Target version validation passed"
}

# Pre-upgrade validation
pre_upgrade_validation() {
    info "Running pre-upgrade validation..."
    
    # Check current version
    local current_version=$(get_current_version)
    info "Current Graphiti version: $current_version"
    
    # Check if target version is newer
    if [ "$current_version" = "$TARGET_VERSION" ]; then
        if [ "$FORCE" = false ]; then
            error_exit "Target version ($TARGET_VERSION) is the same as current version ($current_version)"
        else
            warning "Forcing upgrade to same version: $TARGET_VERSION"
        fi
    fi
    
    # Check if Graphiti MCP server is running
    info "Checking Graphiti MCP server status..."
    if docker ps --format "table {{.Names}}" | grep -q "^graphiti-mcp-server$"; then
        info "Graphiti MCP server is running"
    else
        warning "Graphiti MCP server is not running"
    fi
    
    # Check Neo4j connectivity
    info "Validating Neo4j connectivity..."
    if docker ps --format "table {{.Names}}" | grep -q "^graphiti-neo4j$"; then
        info "Neo4j container is running"
    else
        warning "Neo4j container is not running"
    fi
    
    # Check Python environment
    info "Checking Python environment..."
    if [ -f "$PROJECT_ROOT/graphiti/pyproject.toml" ]; then
        info "Python project configuration found"
    else
        error_exit "Python project configuration not found"
    fi
    
    success "Pre-upgrade validation completed"
}

# Create backup
create_backup() {
    info "Creating backup..."
    
    local backup_timestamp=$(date +%Y%m%d-%H%M%S)
    local backup_path="$BACKUP_DIR/graphiti-backup-$backup_timestamp"
    
    mkdir -p "$backup_path"
    
    # Backup Graphiti source code
    info "Backing up Graphiti source code..."
    tar czf "$backup_path/graphiti_source.tar.gz" -C "$PROJECT_ROOT" graphiti/
    
    # Backup Neo4j data
    info "Backing up Neo4j data..."
    if docker ps --format "table {{.Names}}" | grep -q "^graphiti-neo4j$"; then
        docker exec graphiti-neo4j neo4j-admin dump --database=neo4j > "$backup_path/neo4j_dump.sql" 2>/dev/null || true
    fi
    
    # Backup Graphiti MCP server configuration
    info "Backing up Graphiti MCP server configuration..."
    if [ -f "$PROJECT_ROOT/graphiti/mcp_server/graphiti_mcp_server.py" ]; then
        cp "$PROJECT_ROOT/graphiti/mcp_server/graphiti_mcp_server.py" "$backup_path/"
    fi
    
    # Backup Docker Compose configuration
    info "Backing up Docker Compose configuration..."
    cp "$PROJECT_ROOT/docker-compose.yml" "$backup_path/docker-compose.yml.backup"
    
    # Create backup manifest
    cat > "$backup_path/backup-manifest.json" << EOF
{
    "timestamp": "$backup_timestamp",
    "framework": "graphiti",
    "current_version": "$(get_current_version)",
    "target_version": "$TARGET_VERSION",
    "backup_type": "pre_upgrade",
    "files": [
        "graphiti_source.tar.gz",
        "neo4j_dump.sql",
        "graphiti_mcp_server.py",
        "docker-compose.yml.backup"
    ]
}
EOF
    
    success "Backup created: $backup_path"
    echo "$backup_path"
}

# Perform upgrade
perform_upgrade() {
    info "Performing Graphiti upgrade to version $TARGET_VERSION..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would upgrade Graphiti from $(get_current_version) to $TARGET_VERSION"
        return 0
    fi
    
    # Stop Graphiti MCP server
    info "Stopping Graphiti MCP server..."
    cd "$PROJECT_ROOT"
    docker compose stop graphiti-mcp-server
    
    # Update pyproject.toml with new version
    info "Updating pyproject.toml version..."
    sed -i.bak "s|version[[:space:]]*=[[:space:]]*\"[^\"]*\"|version = \"$TARGET_VERSION\"|" graphiti/pyproject.toml
    
    # Update dependencies if needed
    info "Updating dependencies..."
    cd graphiti
    if command -v uv >/dev/null 2>&1; then
        uv lock --upgrade
    elif command -v poetry >/dev/null 2>&1; then
        poetry lock --no-update
    elif command -v pip >/dev/null 2>&1; then
        pip install -e .
    else
        warning "No Python package manager found - skipping dependency update"
    fi
    cd ..
    
    # Rebuild Graphiti MCP server
    info "Rebuilding Graphiti MCP server..."
    docker compose build graphiti-mcp-server
    
    # Start Graphiti MCP server
    info "Starting Graphiti MCP server with new version..."
    docker compose up -d graphiti-mcp-server
    
    # Wait for service to be healthy
    info "Waiting for Graphiti MCP server to be healthy..."
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s http://localhost:8082/health >/dev/null 2>&1; then
            break
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            error_exit "Graphiti MCP server failed to start within timeout"
        fi
        
        sleep 2
        attempt=$((attempt + 1))
    done
    
    success "Graphiti upgrade completed successfully"
}

# Post-upgrade validation
post_upgrade_validation() {
    info "Running post-upgrade validation..."
    
    # Verify version in pyproject.toml
    local actual_version=$(get_current_version)
    if [ "$actual_version" != "$TARGET_VERSION" ]; then
        error_exit "Version mismatch: expected $TARGET_VERSION, got $actual_version"
    fi
    
    # Check service health
    info "Checking Graphiti MCP server health..."
    if ! curl -s http://localhost:8082/health >/dev/null 2>&1; then
        error_exit "Graphiti MCP server is not responding"
    fi
    
    # Validate Neo4j connectivity
    info "Validating Neo4j connectivity..."
    if ! docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "RETURN 1;" >/dev/null 2>&1; then
        warning "Neo4j connectivity test failed - please review"
    fi
    
    # Check for any error logs
    info "Checking for error logs..."
    local error_count=$(docker logs graphiti-mcp-server --since 5m 2>&1 | grep -i error | wc -l)
    if [ "$error_count" -gt 5 ]; then
        warning "Found $error_count errors in recent logs - please review"
    fi
    
    # Test MCP server functionality
    info "Testing MCP server functionality..."
    local health_response=$(curl -s http://localhost:8082/health)
    if [ -z "$health_response" ]; then
        error_exit "Health endpoint not responding"
    fi
    
    # Validate Python package installation
    info "Validating Python package installation..."
    if docker exec graphiti-mcp-server python -c "import graphiti_core; print(graphiti_core.__version__)" >/dev/null 2>&1; then
        info "Graphiti core package is properly installed"
    else
        warning "Graphiti core package validation failed"
    fi
    
    success "Post-upgrade validation completed"
}

# Update version lock file
update_version_lock() {
    info "Updating version lock file..."
    
    local lock_file="$PROJECT_ROOT/config/versions/versions.lock.yml"
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would update version lock file with version $TARGET_VERSION"
        return 0
    fi
    
    # Update the lock file
    sed -i.bak "s|version: \"[^\"]*\"|version: \"$TARGET_VERSION\"|" "$lock_file"
    sed -i.bak "s|last_updated: \"[^\"]*\"|last_updated: \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"|" "$lock_file"
    
    success "Version lock file updated"
}

# Main upgrade process
main() {
    echo -e "${BLUE}🚀 Graphiti Framework Upgrade${NC}"
    echo -e "${BLUE}============================${NC}"
    echo "Target version: $TARGET_VERSION"
    echo "Dry run: $DRY_RUN"
    echo "Force: $FORCE"
    echo "Log file: $LOG_FILE"
    echo ""
    
    log "Starting Graphiti upgrade process"
    
    # Validate target version
    validate_target_version
    
    # Pre-upgrade validation
    pre_upgrade_validation
    
    # Create backup
    local backup_path=$(create_backup)
    
    # Perform upgrade
    perform_upgrade
    
    # Post-upgrade validation
    post_upgrade_validation
    
    # Update version lock file
    update_version_lock
    
    success "Graphiti upgrade completed successfully!"
    echo ""
    echo -e "${GREEN}📋 Upgrade Summary${NC}"
    echo -e "${GREEN}==================${NC}"
    echo "Previous version: $(get_current_version)"
    echo "New version: $TARGET_VERSION"
    echo "Backup location: $backup_path"
    echo "Log file: $LOG_FILE"
    echo ""
    echo -e "${YELLOW}📝 Next Steps${NC}"
    echo "1. Test Graphiti functionality"
    echo "2. Verify knowledge graph operations"
    echo "3. Test MCP server integrations"
    echo "4. Monitor system performance"
    echo "5. Update documentation if needed"
    echo ""
    echo -e "${BLUE}🔧 Rollback Instructions${NC}"
    echo "If issues occur, rollback using:"
    echo "./scripts/upgrades/rollback/rollback-graphiti.sh --backup-path $backup_path"
}

# Run main function
main "$@"
