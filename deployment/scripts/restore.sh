#!/bin/bash

# PA Ecosystem Restore Script
# Comprehensive restore system for all PA ecosystem components

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/deployment/backups}"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/deployment/logs}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging
LOG_FILE="$LOG_DIR/restore-$TIMESTAMP.log"
mkdir -p "$LOG_DIR"

log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] ✓${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] ⚠${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ✗${NC} $1" | tee -a "$LOG_FILE"
}

# Help function
show_help() {
    cat << EOF
PA Ecosystem Restore Script

USAGE:
    $0 [OPTIONS] BACKUP_PATH

ARGUMENTS:
    BACKUP_PATH            Path to backup directory or backup name

OPTIONS:
    -h, --help              Show this help message
    -d, --dry-run           Show what would be restored without actually doing it
    -f, --force             Force restore even if services are running
    -c, --config-only       Restore only configuration files
    -d, --data-only         Restore only data volumes
    -s, --services-only     Restore only service configurations
    -v, --verbose           Enable verbose output
    -q, --quiet             Suppress output except errors
    -y, --yes               Skip confirmation prompts

EXAMPLES:
    $0 latest               # Restore from latest backup
    $0 /backups/backup-20240121_120000  # Restore from specific backup
    $0 --dry-run latest    # Show what would be restored
    $0 --config-only latest # Restore only configuration
    $0 --data-only latest  # Restore only data

EOF
}

# Parse command line arguments
DRY_RUN=false
FORCE=false
RESTORE_TYPE="full"
VERBOSE=false
QUIET=false
SKIP_CONFIRM=false
BACKUP_PATH=""

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
        -f|--force)
            FORCE=true
            shift
            ;;
        -c|--config-only)
            RESTORE_TYPE="config"
            shift
            ;;
        --data-only)
            RESTORE_TYPE="data"
            shift
            ;;
        -s|--services-only)
            RESTORE_TYPE="services"
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -q|--quiet)
            QUIET=true
            shift
            ;;
        -y|--yes)
            SKIP_CONFIRM=true
            shift
            ;;
        -*)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
        *)
            if [[ -z "$BACKUP_PATH" ]]; then
                BACKUP_PATH="$1"
            else
                log_error "Multiple backup paths specified: $BACKUP_PATH and $1"
                exit 1
            fi
            shift
            ;;
    esac
done

# Check if backup path is specified
if [[ -z "$BACKUP_PATH" ]]; then
    log_error "Backup path is required"
    show_help
    exit 1
fi

# Resolve backup path
if [[ "$BACKUP_PATH" == "latest" ]]; then
    BACKUP_PATH="$BACKUP_DIR/latest"
fi

# Check if backup exists
if [[ ! -d "$BACKUP_PATH" ]]; then
    log_error "Backup not found: $BACKUP_PATH"
    exit 1
fi

# Check if backup manifest exists
if [[ ! -f "$BACKUP_PATH/BACKUP_MANIFEST.md" ]]; then
    log_warning "Backup manifest not found. Proceeding with caution."
fi

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    log_error "Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose >/dev/null 2>&1; then
    log_error "docker-compose is not available. Please install docker-compose and try again."
    exit 1
fi

# Function to check if services are running
are_services_running() {
    docker-compose ps | grep -q "Up"
}

# Function to stop services
stop_services() {
    log "Stopping PA ecosystem services..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would stop services"
    else
        docker-compose down
        log_success "Services stopped"
    fi
}

# Function to start services
start_services() {
    log "Starting PA ecosystem services..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would start services"
    else
        docker-compose up -d
        log_success "Services started"
    fi
}

# Function to restore database
restore_database() {
    local db_name="$1"
    local backup_file="$2"
    
    if [[ ! -f "$backup_file" ]]; then
        log_warning "Database backup not found: $backup_file"
        return
    fi
    
    log "Restoring database: $db_name"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would restore database $db_name from $backup_file"
    else
        # Start database service if not running
        if ! is_service_running "supabase-db"; then
            docker-compose up -d supabase-db
            sleep 10
        fi
        
        # Restore database
        docker-compose exec -T supabase-db psql -U postgres -c "DROP DATABASE IF EXISTS $db_name;"
        docker-compose exec -T supabase-db psql -U postgres -c "CREATE DATABASE $db_name;"
        docker-compose exec -T supabase-db psql -U postgres "$db_name" < "$backup_file"
        log_success "Database $db_name restored from $backup_file"
    fi
}

# Function to restore volume
restore_volume() {
    local volume_name="$1"
    local backup_file="$2"
    
    if [[ ! -f "$backup_file" ]]; then
        log_warning "Volume backup not found: $backup_file"
        return
    fi
    
    log "Restoring volume: $volume_name"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would restore volume $volume_name from $backup_file"
    else
        # Create volume if it doesn't exist
        docker volume create "$volume_name" 2>/dev/null || true
        
        # Restore volume
        docker run --rm -v "$volume_name":/data -v "$(dirname "$backup_file")":/backup alpine tar xzf "/backup/$(basename "$backup_file")" -C /data
        log_success "Volume $volume_name restored from $backup_file"
    fi
}

# Function to restore configuration
restore_config() {
    local config_file="$1"
    local target_path="$2"
    
    if [[ ! -f "$config_file" ]]; then
        log_warning "Configuration backup not found: $config_file"
        return
    fi
    
    log "Restoring configuration: $config_file"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would restore configuration $config_file to $target_path"
    else
        # Create target directory
        mkdir -p "$(dirname "$target_path")"
        
        # Restore configuration
        tar xzf "$config_file" -C "$(dirname "$target_path")"
        log_success "Configuration restored from $config_file to $target_path"
    fi
}

# Function to restore service configuration
restore_service_config() {
    local service_name="$1"
    local config_file="$2"
    
    if [[ ! -f "$config_file" ]]; then
        log_warning "Service configuration backup not found: $config_file"
        return
    fi
    
    log "Restoring service configuration: $service_name"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would restore service configuration $service_name from $config_file"
    else
        # Start service if not running
        if ! is_service_running "$service_name"; then
            docker-compose up -d "$service_name"
            sleep 5
        fi
        
        # Copy configuration to service
        docker cp "$config_file" "$(docker-compose ps -q "$service_name")":/tmp/config.json
        docker-compose exec "$service_name" cp /tmp/config.json /app/config.json
        log_success "Service configuration $service_name restored from $config_file"
    fi
}

# Function to confirm restore
confirm_restore() {
    if [[ "$SKIP_CONFIRM" == "true" ]]; then
        return 0
    fi
    
    echo
    log_warning "This will restore the PA ecosystem from backup: $BACKUP_PATH"
    log_warning "Restore type: $RESTORE_TYPE"
    
    if [[ "$RESTORE_TYPE" == "full" || "$RESTORE_TYPE" == "data" ]]; then
        log_warning "This will overwrite all current data!"
    fi
    
    if are_services_running; then
        log_warning "Services are currently running and will be stopped."
    fi
    
    echo
    read -p "Are you sure you want to continue? (y/N): " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Restore cancelled by user"
        exit 0
    fi
}

# Function to validate backup
validate_backup() {
    log "Validating backup: $BACKUP_PATH"
    
    # Check backup manifest
    if [[ -f "$BACKUP_PATH/BACKUP_MANIFEST.md" ]]; then
        log_success "Backup manifest found"
        if [[ "$VERBOSE" == "true" ]]; then
            cat "$BACKUP_PATH/BACKUP_MANIFEST.md"
        fi
    else
        log_warning "Backup manifest not found"
    fi
    
    # Check backup contents
    local required_dirs=("databases" "volumes" "configs")
    for dir in "${required_dirs[@]}"; do
        if [[ -d "$BACKUP_PATH/$dir" ]]; then
            log_success "Backup directory found: $dir"
        else
            log_warning "Backup directory missing: $dir"
        fi
    done
}

# Main restore function
main() {
    log "Starting PA Ecosystem restore..."
    log "Backup Path: $BACKUP_PATH"
    log "Restore Type: $RESTORE_TYPE"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN MODE: No actual restore will be performed"
    fi
    
    # Validate backup
    validate_backup
    
    # Confirm restore
    confirm_restore
    
    # Stop services if running
    if are_services_running; then
        if [[ "$FORCE" == "true" ]]; then
            stop_services
        else
            log_error "Services are running. Use --force to stop them automatically."
            exit 1
        fi
    fi
    
    # Restore databases
    if [[ "$RESTORE_TYPE" == "full" || "$RESTORE_TYPE" == "data" ]]; then
        restore_database "postgres" "$BACKUP_PATH/databases/postgres_$TIMESTAMP.sql"
        restore_database "letta" "$BACKUP_PATH/databases/letta_$TIMESTAMP.sql"
        restore_database "n8n" "$BACKUP_PATH/databases/n8n_$TIMESTAMP.sql"
    fi
    
    # Restore volumes
    if [[ "$RESTORE_TYPE" == "full" || "$RESTORE_TYPE" == "data" ]]; then
        restore_volume "pa-ecosystem_letta_data" "$BACKUP_PATH/volumes/letta_data_$TIMESTAMP.tar.gz"
        restore_volume "pa-ecosystem_n8n_data" "$BACKUP_PATH/volumes/n8n_data_$TIMESTAMP.tar.gz"
        restore_volume "pa-ecosystem_openwebui_data" "$BACKUP_PATH/volumes/openwebui_data_$TIMESTAMP.tar.gz"
        restore_volume "pa-ecosystem_neo4j_data" "$BACKUP_PATH/volumes/neo4j_data_$TIMESTAMP.tar.gz"
        restore_volume "pa-ecosystem_supabase_storage" "$BACKUP_PATH/volumes/supabase_storage_$TIMESTAMP.tar.gz"
    fi
    
    # Restore configuration files
    if [[ "$RESTORE_TYPE" == "full" || "$RESTORE_TYPE" == "config" ]]; then
        restore_config "$BACKUP_PATH/configs/env_$TIMESTAMP.tar.gz" "$PROJECT_ROOT/.env"
        restore_config "$BACKUP_PATH/configs/docker-compose_$TIMESTAMP.tar.gz" "$PROJECT_ROOT/docker-compose.yml"
        restore_config "$BACKUP_PATH/configs/deployment_$TIMESTAMP.tar.gz" "$PROJECT_ROOT/deployment/"
        restore_config "$BACKUP_PATH/configs/docs_$TIMESTAMP.tar.gz" "$PROJECT_ROOT/docs/"
    fi
    
    # Restore service configurations
    if [[ "$RESTORE_TYPE" == "full" || "$RESTORE_TYPE" == "services" ]]; then
        restore_service_config "letta" "$BACKUP_PATH/configs/letta_agent.json"
        restore_service_config "letta" "$BACKUP_PATH/configs/letta_blocks.json"
        restore_service_config "letta" "$BACKUP_PATH/configs/letta_core_memory.json"
        restore_service_config "n8n" "$BACKUP_PATH/configs/n8n_workflows.json"
    fi
    
    # Start services
    if [[ "$RESTORE_TYPE" == "full" || "$RESTORE_TYPE" == "data" ]]; then
        start_services
    fi
    
    if [[ "$DRY_RUN" == "false" ]]; then
        log_success "Restore completed successfully!"
        log_success "Restore log: $LOG_FILE"
        
        # Wait for services to be healthy
        log "Waiting for services to be healthy..."
        sleep 30
        
        # Run health check
        if [[ -f "$PROJECT_ROOT/deployment/scripts/health-check.sh" ]]; then
            "$PROJECT_ROOT/deployment/scripts/health-check.sh"
        fi
    else
        log_success "Dry run completed successfully!"
    fi
}

# Error handling
trap 'log_error "Restore failed at line $LINENO"' ERR

# Run main function
main "$@"
