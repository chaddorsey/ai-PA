#!/bin/bash

# PA Ecosystem Backup Script
# Comprehensive backup system for all PA ecosystem components

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/deployment/backups}"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/deployment/logs}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="pa-ecosystem-backup-$TIMESTAMP"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging
LOG_FILE="$LOG_DIR/backup-$TIMESTAMP.log"
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
PA Ecosystem Backup Script

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -h, --help              Show this help message
    -d, --dry-run           Show what would be backed up without actually doing it
    -f, --full              Perform full backup (default)
    -i, --incremental       Perform incremental backup
    -c, --config-only       Backup only configuration files
    -d, --data-only         Backup only data volumes
    -s, --services-only     Backup only service configurations
    -o, --output DIR        Specify backup output directory
    -n, --name NAME         Specify backup name
    -v, --verbose           Enable verbose output
    -q, --quiet             Suppress output except errors

EXAMPLES:
    $0                      # Full backup
    $0 --dry-run            # Show what would be backed up
    $0 --incremental        # Incremental backup
    $0 --config-only        # Backup only configuration
    $0 --output /backups    # Backup to specific directory

EOF
}

# Parse command line arguments
DRY_RUN=false
BACKUP_TYPE="full"
VERBOSE=false
QUIET=false
OUTPUT_DIR=""
BACKUP_NAME_CUSTOM=""

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
        -f|--full)
            BACKUP_TYPE="full"
            shift
            ;;
        -i|--incremental)
            BACKUP_TYPE="incremental"
            shift
            ;;
        -c|--config-only)
            BACKUP_TYPE="config"
            shift
            ;;
        --data-only)
            BACKUP_TYPE="data"
            shift
            ;;
        -s|--services-only)
            BACKUP_TYPE="services"
            shift
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -n|--name)
            BACKUP_NAME_CUSTOM="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -q|--quiet)
            QUIET=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Set backup directory
if [[ -n "$OUTPUT_DIR" ]]; then
    BACKUP_DIR="$OUTPUT_DIR"
fi

# Set backup name
if [[ -n "$BACKUP_NAME_CUSTOM" ]]; then
    BACKUP_NAME="$BACKUP_NAME_CUSTOM"
    BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"
fi

# Create backup directory
mkdir -p "$BACKUP_PATH"

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

# Function to check if service is running
is_service_running() {
    local service_name="$1"
    docker-compose ps "$service_name" | grep -q "Up"
}

# Function to backup database
backup_database() {
    local db_name="$1"
    local backup_file="$2"
    
    log "Backing up database: $db_name"
    
    if is_service_running "supabase-db"; then
        if [[ "$DRY_RUN" == "true" ]]; then
            log "DRY RUN: Would backup database $db_name to $backup_file"
        else
            docker-compose exec -T supabase-db pg_dump -U postgres "$db_name" > "$backup_file"
            log_success "Database $db_name backed up to $backup_file"
        fi
    else
        log_warning "Database service is not running. Skipping database backup."
    fi
}

# Function to backup volume
backup_volume() {
    local volume_name="$1"
    local backup_file="$2"
    
    log "Backing up volume: $volume_name"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would backup volume $volume_name to $backup_file"
    else
        docker run --rm -v "$volume_name":/data -v "$(dirname "$backup_file")":/backup alpine tar czf "/backup/$(basename "$backup_file")" -C /data .
        log_success "Volume $volume_name backed up to $backup_file"
    fi
}

# Function to backup configuration files
backup_config() {
    local config_dir="$1"
    local backup_file="$2"
    
    log "Backing up configuration: $config_dir"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would backup configuration $config_dir to $backup_file"
    else
        tar czf "$backup_file" -C "$(dirname "$config_dir")" "$(basename "$config_dir")"
        log_success "Configuration $config_dir backed up to $backup_file"
    fi
}

# Function to create backup manifest
create_manifest() {
    local manifest_file="$1"
    
    log "Creating backup manifest: $manifest_file"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would create manifest $manifest_file"
    else
        cat > "$manifest_file" << EOF
# PA Ecosystem Backup Manifest
# Created: $(date)
# Backup Type: $BACKUP_TYPE
# Backup Name: $BACKUP_NAME
# Backup Path: $BACKUP_PATH

## System Information
- Hostname: $(hostname)
- OS: $(uname -s)
- Architecture: $(uname -m)
- Docker Version: $(docker --version)
- Docker Compose Version: $(docker-compose --version)

## Backup Contents
EOF
        
        # Add file listings
        find "$BACKUP_PATH" -type f -name "*.tar.gz" -o -name "*.sql" -o -name "*.env" | while read -r file; do
            echo "- $(basename "$file") ($(du -h "$file" | cut -f1))" >> "$manifest_file"
        done
        
        log_success "Backup manifest created: $manifest_file"
    fi
}

# Main backup function
main() {
    log "Starting PA Ecosystem backup..."
    log "Backup Type: $BACKUP_TYPE"
    log "Backup Directory: $BACKUP_DIR"
    log "Backup Name: $BACKUP_NAME"
    log "Backup Path: $BACKUP_PATH"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN MODE: No actual backup will be performed"
    fi
    
    # Create backup directory structure
    mkdir -p "$BACKUP_PATH"/{databases,volumes,configs,logs}
    
    # Backup databases
    if [[ "$BACKUP_TYPE" == "full" || "$BACKUP_TYPE" == "data" ]]; then
        backup_database "postgres" "$BACKUP_PATH/databases/postgres_$TIMESTAMP.sql"
        backup_database "letta" "$BACKUP_PATH/databases/letta_$TIMESTAMP.sql"
        backup_database "n8n" "$BACKUP_PATH/databases/n8n_$TIMESTAMP.sql"
    fi
    
    # Backup volumes
    if [[ "$BACKUP_TYPE" == "full" || "$BACKUP_TYPE" == "data" ]]; then
        backup_volume "pa-ecosystem_letta_data" "$BACKUP_PATH/volumes/letta_data_$TIMESTAMP.tar.gz"
        backup_volume "pa-ecosystem_n8n_data" "$BACKUP_PATH/volumes/n8n_data_$TIMESTAMP.tar.gz"
        backup_volume "pa-ecosystem_openwebui_data" "$BACKUP_PATH/volumes/openwebui_data_$TIMESTAMP.tar.gz"
        backup_volume "pa-ecosystem_neo4j_data" "$BACKUP_PATH/volumes/neo4j_data_$TIMESTAMP.tar.gz"
        backup_volume "pa-ecosystem_supabase_storage" "$BACKUP_PATH/volumes/supabase_storage_$TIMESTAMP.tar.gz"
    fi
    
    # Backup configuration files
    if [[ "$BACKUP_TYPE" == "full" || "$BACKUP_TYPE" == "config" ]]; then
        backup_config ".env" "$BACKUP_PATH/configs/env_$TIMESTAMP.tar.gz"
        backup_config "docker-compose.yml" "$BACKUP_PATH/configs/docker-compose_$TIMESTAMP.tar.gz"
        backup_config "deployment/" "$BACKUP_PATH/configs/deployment_$TIMESTAMP.tar.gz"
        backup_config "docs/" "$BACKUP_PATH/configs/docs_$TIMESTAMP.tar.gz"
    fi
    
    # Backup service configurations
    if [[ "$BACKUP_TYPE" == "full" || "$BACKUP_TYPE" == "services" ]]; then
        # Backup Letta configuration
        if is_service_running "letta"; then
            docker-compose exec -T letta cat /app/agent.json > "$BACKUP_PATH/configs/letta_agent.json" 2>/dev/null || true
            docker-compose exec -T letta cat /app/blocks.json > "$BACKUP_PATH/configs/letta_blocks.json" 2>/dev/null || true
            docker-compose exec -T letta cat /app/core_memory.json > "$BACKUP_PATH/configs/letta_core_memory.json" 2>/dev/null || true
        fi
        
        # Backup n8n workflows
        if is_service_running "n8n"; then
            docker-compose exec -T n8n n8n export:workflow --backup --output=/tmp/n8n_backup.json 2>/dev/null || true
            docker cp "$(docker-compose ps -q n8n)":/tmp/n8n_backup.json "$BACKUP_PATH/configs/n8n_workflows.json" 2>/dev/null || true
        fi
    fi
    
    # Create backup manifest
    create_manifest "$BACKUP_PATH/BACKUP_MANIFEST.md"
    
    # Create backup summary
    if [[ "$DRY_RUN" == "false" ]]; then
        local total_size=$(du -sh "$BACKUP_PATH" | cut -f1)
        log_success "Backup completed successfully!"
        log_success "Backup location: $BACKUP_PATH"
        log_success "Total size: $total_size"
        log_success "Backup manifest: $BACKUP_PATH/BACKUP_MANIFEST.md"
        
        # Create symlink to latest backup
        ln -sfn "$BACKUP_NAME" "$BACKUP_DIR/latest"
        log_success "Latest backup symlink created: $BACKUP_DIR/latest"
    else
        log_success "Dry run completed successfully!"
    fi
}

# Error handling
trap 'log_error "Backup failed at line $LINENO"' ERR

# Run main function
main "$@"
