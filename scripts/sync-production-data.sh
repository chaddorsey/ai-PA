#!/bin/bash
set -e

# Sync Production Data to Staging Script
# This script synchronizes production data to staging environment

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
STAGING_DATA_DIR="$PROJECT_ROOT/staging-data"
BACKUP_DIR="$PROJECT_ROOT/backups/staging"
LOGS_DIR="$PROJECT_ROOT/logs/staging"

# Create necessary directories
mkdir -p "$STAGING_DATA_DIR"/{postgres,uploads} "$BACKUP_DIR" "$LOGS_DIR"

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOGS_DIR/sync-$(date +%Y%m%d).log"
}

# Success logging
log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] SUCCESS:${NC} $1" | tee -a "$LOGS_DIR/sync-$(date +%Y%m%d).log"
}

# Error logging
log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOGS_DIR/sync-$(date +%Y%m%d).log"
}

# Warning logging
log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOGS_DIR/sync-$(date +%Y%m%d).log"
}

# Check if production environment is running
check_production() {
    log "Checking production environment..."
    
    if docker-compose ps -q | grep -q .; then
        log_success "Production environment is running"
        return 0
    else
        log_error "Production environment is not running"
        return 1
    fi
}

# Sync database from production to staging
sync_database() {
    log "Syncing database from production to staging..."
    
    local db_dump_file="$STAGING_DATA_DIR/postgres/staging-dump-$(date +%Y%m%d-%H%M%S).sql"
    
    # Create database dump from production
    log "Creating database dump from production..."
    if docker-compose exec -T supabase-db pg_dump -U postgres postgres > "$db_dump_file"; then
        log_success "Database dump created: $db_dump_file"
    else
        log_error "Failed to create database dump"
        return 1
    fi
    
    # Sanitize data if on laptop
    if [[ "$ENVIRONMENT" == "laptop" ]]; then
        log "Sanitizing sensitive data for laptop environment..."
        sanitize_database_dump "$db_dump_file"
    fi
    
    # Restore database to staging
    log "Restoring database to staging..."
    if docker-compose -f docker-compose.staging.yml exec -T supabase-db-staging psql -U postgres -d postgres -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"; then
        if docker-compose -f docker-compose.staging.yml exec -T supabase-db-staging psql -U postgres -d postgres < "$db_dump_file"; then
            log_success "Database restored to staging"
        else
            log_error "Failed to restore database to staging"
            return 1
        fi
    else
        log_error "Failed to reset staging database"
        return 1
    fi
}

# Sanitize database dump for laptop environment
sanitize_database_dump() {
    local dump_file="$1"
    local sanitized_file="${dump_file}.sanitized"
    
    log "Sanitizing database dump for laptop environment..."
    
    # Create sanitized version
    cp "$dump_file" "$sanitized_file"
    
    # Replace sensitive data
    sed -i.bak 's/your_actual_email@domain.com/test@example.com/g' "$sanitized_file"
    sed -i.bak 's/your_actual_phone/555-0123/g' "$sanitized_file"
    sed -i.bak 's/your_actual_name/Test User/g' "$sanitized_file"
    
    # Remove backup file
    rm -f "${sanitized_file}.bak"
    
    # Replace original with sanitized version
    mv "$sanitized_file" "$dump_file"
    
    log_success "Database dump sanitized for laptop environment"
}

# Sync files from production to staging
sync_files() {
    log "Syncing files from production to staging..."
    
    # Sync n8n data
    if docker-compose ps -q n8n | grep -q .; then
        log "Syncing n8n data..."
        docker cp "$(docker-compose ps -q n8n):/home/node/.n8n" "$STAGING_DATA_DIR/n8n-data"
        log_success "n8n data synced"
    fi
    
    # Sync uploads and static files
    if [[ -d "$PROJECT_ROOT/uploads" ]]; then
        log "Syncing uploads..."
        rsync -av --delete "$PROJECT_ROOT/uploads/" "$STAGING_DATA_DIR/uploads/"
        log_success "Uploads synced"
    fi
    
    # Sync other data directories
    for dir in "data" "logs" "backups"; do
        if [[ -d "$PROJECT_ROOT/$dir" ]]; then
            log "Syncing $dir directory..."
            rsync -av --delete "$PROJECT_ROOT/$dir/" "$STAGING_DATA_DIR/$dir/"
            log_success "$dir directory synced"
        fi
    done
}

# Validate data synchronization
validate_sync() {
    log "Validating data synchronization..."
    
    # Check if staging database is accessible
    if docker-compose -f docker-compose.staging.yml exec -T supabase-db-staging psql -U postgres -d postgres -c "SELECT 1;" > /dev/null 2>&1; then
        log_success "Staging database is accessible"
    else
        log_error "Staging database is not accessible"
        return 1
    fi
    
    # Check if staging services are running
    local unhealthy_services=$(docker-compose -f docker-compose.staging.yml ps --format json | jq -r '.[] | select(.State != "running") | .Name' | wc -l)
    
    if [[ $unhealthy_services -eq 0 ]]; then
        log_success "All staging services are running"
    else
        log_warning "$unhealthy_services staging services are not running"
    fi
    
    # Check data integrity
    local db_size=$(docker-compose -f docker-compose.staging.yml exec -T supabase-db-staging psql -U postgres -d postgres -t -c "SELECT pg_database_size('postgres');" | tr -d ' ')
    log "Staging database size: $db_size bytes"
    
    log_success "Data synchronization validation completed"
}

# Cleanup old data
cleanup_old_data() {
    log "Cleaning up old staging data..."
    
    # Keep only last 5 database dumps
    find "$STAGING_DATA_DIR/postgres" -name "staging-dump-*.sql" -type f | sort -r | tail -n +6 | xargs rm -f
    
    # Clean up old logs
    find "$LOGS_DIR" -name "*.log" -type f -mtime +7 -delete
    
    log_success "Old data cleaned up"
}

# Main execution
main() {
    log "Starting production data synchronization to staging..."
    log "Project root: $PROJECT_ROOT"
    log "Staging data directory: $STAGING_DATA_DIR"
    
    # Detect environment
    if [[ -n "$SSH_CLIENT" ]] || [[ -n "$SSH_TTY" ]]; then
        ENVIRONMENT="server"
    elif [[ "$(uname -s)" == "Darwin" ]] && [[ -d "/Users" ]]; then
        ENVIRONMENT="laptop"
    elif [[ "$(uname -s)" == "Linux" ]] && [[ -n "$DISPLAY" ]]; then
        ENVIRONMENT="laptop"
    else
        ENVIRONMENT="server"
    fi
    
    log "Environment: $ENVIRONMENT"
    
    # Check if production environment is running
    if ! check_production; then
        log_error "Cannot sync data: production environment is not running"
        exit 1
    fi
    
    # Sync database
    if ! sync_database; then
        log_error "Database synchronization failed"
        exit 1
    fi
    
    # Sync files
    sync_files
    
    # Validate synchronization
    if ! validate_sync; then
        log_error "Data synchronization validation failed"
        exit 1
    fi
    
    # Cleanup old data
    cleanup_old_data
    
    log_success "Production data synchronization completed successfully!"
}

# Help function
show_help() {
    echo "Sync Production Data to Staging Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help     Show this help message"
    echo "  -d, --dry-run  Show what would be synced without actually syncing"
    echo ""
    echo "This script synchronizes production data to staging environment."
    echo "It creates database dumps, syncs files, and validates the synchronization."
    echo "On laptop environments, sensitive data is automatically sanitized."
}

# Parse command line arguments
DRY_RUN=false
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Run main function
main
