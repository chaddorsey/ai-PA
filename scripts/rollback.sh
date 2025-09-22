#!/bin/bash
set -e

# Rollback Script
# This script provides rapid rollback capability within 5 minutes

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_ROOT/backups/production"
LOGS_DIR="$PROJECT_ROOT/logs/production"

# Create necessary directories
mkdir -p "$BACKUP_DIR" "$LOGS_DIR"

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOGS_DIR/rollback-$(date +%Y%m%d).log"
}

# Success logging
log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] SUCCESS:${NC} $1" | tee -a "$LOGS_DIR/rollback-$(date +%Y%m%d).log"
}

# Error logging
log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOGS_DIR/rollback-$(date +%Y%m%d).log"
}

# Warning logging
log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOGS_DIR/rollback-$(date +%Y%m%d).log"
}

# Confirm action
confirm_action() {
    local message="$1"
    echo -e "${YELLOW}$message${NC}"
    read -p "Do you want to continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Rollback cancelled by user"
        exit 0
    fi
}

# List available rollback points
list_rollback_points() {
    log "Available rollback points:"
    echo ""
    
    # List Git tags
    echo "Git tags:"
    git tag --sort=-creatordate | head -10
    echo ""
    
    # List database backups
    echo "Database backups:"
    ls -la "$BACKUP_DIR"/*.sql 2>/dev/null | head -10 || echo "No database backups found"
    echo ""
    
    # List volume backups
    echo "Volume backups:"
    ls -la "$BACKUP_DIR"/*.tar.gz 2>/dev/null | head -10 || echo "No volume backups found"
    echo ""
}

# Stop current production environment
stop_production() {
    log "Stopping current production environment..."
    
    if docker-compose ps -q | grep -q .; then
        docker-compose down
        log_success "Production environment stopped"
    else
        log "No production environment running"
    fi
}

# Rollback to Git tag
rollback_to_tag() {
    local tag="$1"
    
    log "Rolling back to Git tag: $tag"
    
    # Check if tag exists
    if ! git tag -l | grep -q "^$tag$"; then
        log_error "Tag $tag does not exist"
        return 1
    fi
    
    # Checkout tag
    git checkout "$tag"
    log_success "Checked out tag: $tag"
    
    # Start production environment
    docker-compose up -d
    log_success "Production environment started with tag: $tag"
}

# Rollback to database backup
rollback_to_database() {
    local backup_file="$1"
    
    log "Rolling back to database backup: $backup_file"
    
    # Check if backup file exists
    if [[ ! -f "$backup_file" ]]; then
        log_error "Backup file $backup_file does not exist"
        return 1
    fi
    
    # Start production environment
    docker-compose up -d
    
    # Wait for database to be ready
    log "Waiting for database to be ready..."
    local max_attempts=30
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if docker-compose exec -T supabase-db pg_isready -U postgres > /dev/null 2>&1; then
            log_success "Database is ready"
            break
        fi
        
        sleep 2
        ((attempt++))
    done
    
    if [[ $attempt -gt $max_attempts ]]; then
        log_error "Database did not become ready within expected time"
        return 1
    fi
    
    # Restore database
    log "Restoring database from backup..."
    docker-compose exec -T supabase-db psql -U postgres -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
    docker-compose exec -T supabase-db psql -U postgres -d postgres < "$backup_file"
    log_success "Database restored from backup"
}

# Rollback to volume backup
rollback_to_volumes() {
    local backup_file="$1"
    
    log "Rolling back to volume backup: $backup_file"
    
    # Check if backup file exists
    if [[ ! -f "$backup_file" ]]; then
        log_error "Backup file $backup_file does not exist"
        return 1
    fi
    
    # Stop production environment
    docker-compose down
    
    # Remove existing volumes
    log "Removing existing volumes..."
    docker volume ls -q | grep pa-internal | xargs docker volume rm 2>/dev/null || true
    
    # Restore volumes
    log "Restoring volumes from backup..."
    docker run --rm -v pa-internal_supabase_db:/data -v "$backup_file":/backup.tar.gz alpine sh -c "cd /data && tar xzf /backup.tar.gz"
    log_success "Volumes restored from backup"
    
    # Start production environment
    docker-compose up -d
    log_success "Production environment started with restored volumes"
}

# Emergency rollback (fastest)
emergency_rollback() {
    log "Performing emergency rollback..."
    
    # Stop current environment
    docker-compose down
    
    # Get the most recent rollback tag
    local latest_tag=$(git tag --sort=-creatordate | grep "^rollback-" | head -1)
    
    if [[ -n "$latest_tag" ]]; then
        log "Rolling back to latest rollback tag: $latest_tag"
        git checkout "$latest_tag"
        docker-compose up -d
        log_success "Emergency rollback completed to tag: $latest_tag"
    else
        log_error "No rollback tags found, cannot perform emergency rollback"
        return 1
    fi
}

# Validate rollback
validate_rollback() {
    log "Validating rollback..."
    
    # Wait for services to be ready
    local max_attempts=30
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        log "Health check attempt $attempt/$max_attempts..."
        
        # Check if all services are healthy
        local unhealthy_services=$(docker-compose ps --format json | jq -r '.[] | select(.State != "running") | .Name' | wc -l)
        
        if [[ $unhealthy_services -eq 0 ]]; then
            log_success "All services are healthy after rollback"
            return 0
        fi
        
        sleep 10
        ((attempt++))
    done
    
    log_error "Services did not become healthy after rollback"
    return 1
}

# Main execution
main() {
    local start_time=$(date +%s)
    
    log "Starting rollback procedure..."
    log "Project root: $PROJECT_ROOT"
    
    # Check if we're in a Git repository
    if [[ ! -d ".git" ]]; then
        log_error "Not in a Git repository, cannot perform rollback"
        exit 1
    fi
    
    # Parse arguments
    local rollback_type=""
    local rollback_target=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --tag)
                rollback_type="tag"
                rollback_target="$2"
                shift 2
                ;;
            --database)
                rollback_type="database"
                rollback_target="$2"
                shift 2
                ;;
            --volumes)
                rollback_type="volumes"
                rollback_target="$2"
                shift 2
                ;;
            --emergency)
                rollback_type="emergency"
                shift
                ;;
            --list)
                list_rollback_points
                exit 0
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # If no rollback type specified, show options
    if [[ -z "$rollback_type" ]]; then
        log "No rollback type specified. Available options:"
        echo "  --tag <tag>        Rollback to Git tag"
        echo "  --database <file>  Rollback to database backup"
        echo "  --volumes <file>   Rollback to volume backup"
        echo "  --emergency        Emergency rollback to latest rollback tag"
        echo "  --list             List available rollback points"
        echo "  -h, --help         Show help"
        exit 1
    fi
    
    # Confirm action
    confirm_action "This will rollback the production environment. This action cannot be undone."
    
    # Perform rollback based on type
    case "$rollback_type" in
        "tag")
            if [[ -z "$rollback_target" ]]; then
                log_error "Tag name required for --tag option"
                exit 1
            fi
            rollback_to_tag "$rollback_target"
            ;;
        "database")
            if [[ -z "$rollback_target" ]]; then
                log_error "Backup file required for --database option"
                exit 1
            fi
            rollback_to_database "$rollback_target"
            ;;
        "volumes")
            if [[ -z "$rollback_target" ]]; then
                log_error "Backup file required for --volumes option"
                exit 1
            fi
            rollback_to_volumes "$rollback_target"
            ;;
        "emergency")
            emergency_rollback
            ;;
    esac
    
    # Validate rollback
    if ! validate_rollback; then
        log_error "Rollback validation failed"
        exit 1
    fi
    
    # Calculate rollback time
    local end_time=$(date +%s)
    local rollback_time=$((end_time - start_time))
    
    log_success "Rollback completed successfully in ${rollback_time} seconds"
    
    # Show current status
    log "Current production status:"
    docker-compose ps
}

# Help function
show_help() {
    echo "Rollback Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --tag <tag>        Rollback to specific Git tag"
    echo "  --database <file>  Rollback to database backup file"
    echo "  --volumes <file>   Rollback to volume backup file"
    echo "  --emergency        Emergency rollback to latest rollback tag"
    echo "  --list             List available rollback points"
    echo "  -h, --help         Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --list                                    # List available rollback points"
    echo "  $0 --tag rollback-20250121-143000           # Rollback to specific tag"
    echo "  $0 --database production-db-20250121.sql    # Rollback to database backup"
    echo "  $0 --emergency                              # Emergency rollback"
    echo ""
    echo "This script provides rapid rollback capability within 5 minutes."
}

# Run main function
main "$@"
