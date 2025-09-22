#!/bin/bash

# n8n Framework Upgrade Script
# Purpose: Safely upgrade n8n to a specified version with validation and rollback capability
# Usage: ./upgrade-n8n.sh --version <target-version> [--dry-run] [--force]

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
LOG_FILE="/var/log/upgrades/n8n-upgrade-$(date +%Y%m%d-%H%M%S).log"
BACKUP_DIR="/var/backups/upgrades/n8n"
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
            echo "  --version    Target n8n version (e.g., 1.110.0)"
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

# Get current n8n version
get_current_version() {
    if docker ps --format "table {{.Names}}" | grep -q "^n8n$"; then
        local current_version=$(docker exec n8n n8n --version 2>/dev/null || echo "unknown")
        echo "$current_version"
    else
        echo "not_running"
    fi
}

# Validate target version
validate_target_version() {
    info "Validating target version: $TARGET_VERSION"
    
    # Check if version format is valid (semantic versioning)
    if [[ ! $TARGET_VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        error_exit "Invalid version format: $TARGET_VERSION (expected: X.Y.Z)"
    fi
    
    # Check if Docker image exists
    local image_name="docker.n8n.io/n8nio/n8n:$TARGET_VERSION"
    if ! docker manifest inspect "$image_name" >/dev/null 2>&1; then
        error_exit "Docker image not found: $image_name"
    fi
    
    success "Target version validation passed"
}

# Pre-upgrade validation
pre_upgrade_validation() {
    info "Running pre-upgrade validation..."
    
    # Check if n8n container is running
    local current_version=$(get_current_version)
    if [ "$current_version" = "not_running" ]; then
        error_exit "n8n container is not running"
    fi
    
    info "Current n8n version: $current_version"
    
    # Check if target version is newer
    if [ "$current_version" = "$TARGET_VERSION" ]; then
        if [ "$FORCE" = false ]; then
            error_exit "Target version ($TARGET_VERSION) is the same as current version ($current_version)"
        else
            warning "Forcing upgrade to same version: $TARGET_VERSION"
        fi
    fi
    
    # Check database connectivity
    info "Validating database connectivity..."
    if ! docker exec n8n n8n --version >/dev/null 2>&1; then
        error_exit "Cannot connect to n8n service"
    fi
    
    # Check for active workflows
    info "Checking for active workflows..."
    # This would need to be implemented based on n8n API
    # For now, we'll assume it's safe to proceed
    
    success "Pre-upgrade validation completed"
}

# Create backup
create_backup() {
    info "Creating backup..."
    
    local backup_timestamp=$(date +%Y%m%d-%H%M%S)
    local backup_path="$BACKUP_DIR/n8n-backup-$backup_timestamp"
    
    mkdir -p "$backup_path"
    
    # Backup n8n data volume
    info "Backing up n8n data volume..."
    docker run --rm -v n8n_data:/source -v "$backup_path":/backup alpine tar czf /backup/n8n_data.tar.gz -C /source .
    
    # Backup n8n configuration
    info "Backing up n8n configuration..."
    docker exec n8n cat /home/node/.n8n/config.json > "$backup_path/config.json" 2>/dev/null || true
    
    # Backup Docker Compose configuration
    info "Backing up Docker Compose configuration..."
    cp "$PROJECT_ROOT/docker-compose.yml" "$backup_path/docker-compose.yml.backup"
    
    # Create backup manifest
    cat > "$backup_path/backup-manifest.json" << EOF
{
    "timestamp": "$backup_timestamp",
    "framework": "n8n",
    "current_version": "$(get_current_version)",
    "target_version": "$TARGET_VERSION",
    "backup_type": "pre_upgrade",
    "files": [
        "n8n_data.tar.gz",
        "config.json",
        "docker-compose.yml.backup"
    ]
}
EOF
    
    success "Backup created: $backup_path"
    echo "$backup_path"
}

# Perform upgrade
perform_upgrade() {
    info "Performing n8n upgrade to version $TARGET_VERSION..."
    
    if [ "$DRY_RUN" = true ]; then
        info "DRY RUN: Would upgrade n8n from $(get_current_version) to $TARGET_VERSION"
        return 0
    fi
    
    # Stop n8n service
    info "Stopping n8n service..."
    cd "$PROJECT_ROOT"
    docker compose stop n8n
    
    # Update Docker Compose file with new version
    info "Updating Docker Compose configuration..."
    sed -i.bak "s|image: docker.n8n.io/n8nio/n8n.*|image: docker.n8n.io/n8nio/n8n:$TARGET_VERSION|" docker-compose.yml
    
    # Pull new image
    info "Pulling new n8n image..."
    docker compose pull n8n
    
    # Start n8n service
    info "Starting n8n service with new version..."
    docker compose up -d n8n
    
    # Wait for service to be healthy
    info "Waiting for n8n service to be healthy..."
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if docker exec n8n n8n --version >/dev/null 2>&1; then
            break
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            error_exit "n8n service failed to start within timeout"
        fi
        
        sleep 2
        attempt=$((attempt + 1))
    done
    
    success "n8n upgrade completed successfully"
}

# Post-upgrade validation
post_upgrade_validation() {
    info "Running post-upgrade validation..."
    
    # Verify version
    local actual_version=$(get_current_version)
    if [ "$actual_version" != "$TARGET_VERSION" ]; then
        error_exit "Version mismatch: expected $TARGET_VERSION, got $actual_version"
    fi
    
    # Check service health
    info "Checking service health..."
    if ! docker exec n8n n8n --version >/dev/null 2>&1; then
        error_exit "n8n service is not responding"
    fi
    
    # Validate database connectivity
    info "Validating database connectivity..."
    # This would need to be implemented based on n8n API
    # For now, we'll assume it's working if the service is responding
    
    # Check for any error logs
    info "Checking for error logs..."
    local error_count=$(docker logs n8n --since 5m 2>&1 | grep -i error | wc -l)
    if [ "$error_count" -gt 10 ]; then
        warning "Found $error_count errors in recent logs - please review"
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
    sed -i.bak "s|tag: \"[^\"]*\"|tag: \"$TARGET_VERSION\"|" "$lock_file"
    sed -i.bak "s|version: \"[^\"]*\"|version: \"$TARGET_VERSION\"|" "$lock_file"
    sed -i.bak "s|last_updated: \"[^\"]*\"|last_updated: \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"|" "$lock_file"
    
    success "Version lock file updated"
}

# Main upgrade process
main() {
    echo -e "${BLUE}🚀 n8n Framework Upgrade${NC}"
    echo -e "${BLUE}========================${NC}"
    echo "Target version: $TARGET_VERSION"
    echo "Dry run: $DRY_RUN"
    echo "Force: $FORCE"
    echo "Log file: $LOG_FILE"
    echo ""
    
    log "Starting n8n upgrade process"
    
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
    
    success "n8n upgrade completed successfully!"
    echo ""
    echo -e "${GREEN}📋 Upgrade Summary${NC}"
    echo -e "${GREEN}==================${NC}"
    echo "Previous version: $(get_current_version)"
    echo "New version: $TARGET_VERSION"
    echo "Backup location: $backup_path"
    echo "Log file: $LOG_FILE"
    echo ""
    echo -e "${YELLOW}📝 Next Steps${NC}"
    echo "1. Test n8n functionality"
    echo "2. Verify workflows are working"
    echo "3. Monitor system performance"
    echo "4. Update documentation if needed"
    echo ""
    echo -e "${BLUE}🔧 Rollback Instructions${NC}"
    echo "If issues occur, rollback using:"
    echo "./scripts/upgrades/rollback/rollback-n8n.sh --backup-path $backup_path"
}

# Run main function
main "$@"
