#!/bin/bash

# Gmail MCP Server Migration and Maintenance Script
# Part of PA Ecosystem Migration and Maintenance System
# Created: 2025-01-21

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/backups}"
LOG_FILE="${LOG_FILE:-$PROJECT_ROOT/logs/gmail-mcp-migration.log}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to log messages
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOG_FILE"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO:${NC} $1" | tee -a "$LOG_FILE"
}

# Function to check prerequisites
check_prerequisites() {
    log "Checking migration prerequisites..."
    
    # Check if Docker is running
    if ! docker info >/dev/null 2>&1; then
        error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
    
    # Check if docker-compose is available
    if ! command -v docker-compose &> /dev/null; then
        error "docker-compose is not installed or not in PATH"
        exit 1
    fi
    
    # Check if backup directory exists
    if [ ! -d "$BACKUP_DIR" ]; then
        warning "Backup directory does not exist, creating: $BACKUP_DIR"
        mkdir -p "$BACKUP_DIR"
    fi
    
    # Check if log directory exists
    mkdir -p "$(dirname "$LOG_FILE")"
    
    log "✓ Prerequisites check passed"
}

# Function to backup current state
backup_current_state() {
    log "Creating backup of current Gmail MCP state..."
    
    local backup_timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_path="$BACKUP_DIR/gmail-mcp-migration-$backup_timestamp"
    
    mkdir -p "$backup_path"
    
    # Backup credentials if container is running
    if docker ps --format "table {{.Names}}" | grep -q "gmail-mcp-server"; then
        info "Backing up credentials from running container..."
        
        # Backup OAuth credentials
        if docker cp gmail-mcp-server:/app/config/gcp-oauth.keys.json "$backup_path/" 2>/dev/null; then
            log "✓ OAuth credentials backed up"
        else
            warning "Could not backup OAuth credentials"
        fi
        
        # Backup stored tokens
        if docker cp gmail-mcp-server:/app/data/credentials.json "$backup_path/" 2>/dev/null; then
            log "✓ OAuth tokens backed up"
        else
            warning "Could not backup OAuth tokens"
        fi
        
        # Backup additional data
        if docker cp gmail-mcp-server:/app/data "$backup_path/data/" 2>/dev/null; then
            log "✓ Additional data backed up"
        fi
        
        # Backup container logs
        docker logs gmail-mcp-server > "$backup_path/container-logs.log" 2>&1
        log "✓ Container logs backed up"
        
    else
        warning "Gmail MCP container not running - backing up configuration only"
    fi
    
    # Backup configuration files
    if [ -f "$PROJECT_ROOT/.env" ]; then
        grep -E "GMAIL_|MCP_" "$PROJECT_ROOT/.env" > "$backup_path/gmail-env.txt" 2>/dev/null || true
        log "✓ Environment variables backed up"
    fi
    
    if [ -d "$PROJECT_ROOT/gmail-mcp" ]; then
        cp -r "$PROJECT_ROOT/gmail-mcp" "$backup_path/" 2>/dev/null || true
        log "✓ Gmail MCP source backed up"
    fi
    
    # Create backup manifest
    cat > "$backup_path/manifest.json" << EOF
{
  "backup_type": "gmail-mcp-migration",
  "timestamp": "$backup_timestamp",
  "backup_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "migration_type": "pre-migration",
  "backup_path": "$backup_path"
}
EOF
    
    log "✓ Backup completed: $backup_path"
    echo "$backup_path"
}

# Function to validate Gmail MCP health before migration
validate_health() {
    log "Validating Gmail MCP health before migration..."
    
    # Check if container is running
    if ! docker ps --format "table {{.Names}}" | grep -q "gmail-mcp-server"; then
        warning "Gmail MCP container is not running"
        return 1
    fi
    
    # Check health endpoint
    local health_url="http://localhost:8080/health"
    if command -v curl &> /dev/null; then
        if curl -s -f "$health_url" >/dev/null 2>&1; then
            log "✓ Health check passed"
            
            # Get detailed health status
            local health_response=$(curl -s "$health_url")
            local health_status=$(echo "$health_response" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
            
            if [ "$health_status" = "healthy" ]; then
                log "✓ Gmail MCP is healthy"
                return 0
            elif [ "$health_status" = "degraded" ]; then
                warning "Gmail MCP is degraded but functional"
                return 0
            else
                error "Gmail MCP is unhealthy"
                return 1
            fi
        else
            error "Health check failed"
            return 1
        fi
    else
        warning "curl not available, skipping health check"
        return 0
    fi
}

# Function to perform migration
perform_migration() {
    local migration_type="$1"
    local target_version="$2"
    
    log "Starting Gmail MCP migration: $migration_type"
    
    case "$migration_type" in
        "update")
            migrate_update "$target_version"
            ;;
        "restore")
            migrate_restore "$target_version"
            ;;
        "rollback")
            migrate_rollback "$target_version"
            ;;
        "maintenance")
            migrate_maintenance
            ;;
        *)
            error "Unknown migration type: $migration_type"
            exit 1
            ;;
    esac
}

# Function to perform update migration
migrate_update() {
    local target_version="$1"
    
    log "Performing Gmail MCP update to version: ${target_version:-latest}"
    
    # Pull latest image
    if [ -n "$target_version" ] && [ "$target_version" != "latest" ]; then
        info "Pulling specific version: $target_version"
        docker-compose pull gmail-mcp-server || {
            error "Failed to pull Gmail MCP image version $target_version"
            return 1
        }
    else
        info "Pulling latest version"
        docker-compose pull gmail-mcp-server || {
            error "Failed to pull latest Gmail MCP image"
            return 1
        }
    fi
    
    # Stop current container
    info "Stopping current Gmail MCP container..."
    docker-compose stop gmail-mcp-server || {
        error "Failed to stop Gmail MCP container"
        return 1
    }
    
    # Start updated container
    info "Starting updated Gmail MCP container..."
    docker-compose up -d gmail-mcp-server || {
        error "Failed to start updated Gmail MCP container"
        return 1
    }
    
    # Wait for container to be ready
    info "Waiting for container to be ready..."
    sleep 10
    
    # Validate health after update
    if validate_health; then
        log "✓ Gmail MCP update completed successfully"
    else
        error "Gmail MCP health check failed after update"
        return 1
    fi
}

# Function to perform restore migration
migrate_restore() {
    local backup_path="$1"
    
    if [ -z "$backup_path" ]; then
        error "Backup path required for restore migration"
        return 1
    fi
    
    if [ ! -d "$backup_path" ]; then
        error "Backup path does not exist: $backup_path"
        return 1
    fi
    
    log "Performing Gmail MCP restore from: $backup_path"
    
    # Stop current container
    info "Stopping current Gmail MCP container..."
    docker-compose stop gmail-mcp-server || {
        error "Failed to stop Gmail MCP container"
        return 1
    }
    
    # Start container
    info "Starting Gmail MCP container..."
    docker-compose up -d gmail-mcp-server || {
        error "Failed to start Gmail MCP container"
        return 1
    }
    
    # Wait for container to be ready
    sleep 10
    
    # Restore credentials
    info "Restoring credentials..."
    if [ -f "$backup_path/gcp-oauth.keys.json" ]; then
        docker cp "$backup_path/gcp-oauth.keys.json" gmail-mcp-server:/app/config/ || {
            error "Failed to restore OAuth credentials"
            return 1
        }
        log "✓ OAuth credentials restored"
    fi
    
    if [ -f "$backup_path/credentials.json" ]; then
        docker cp "$backup_path/credentials.json" gmail-mcp-server:/app/data/ || {
            error "Failed to restore OAuth tokens"
            return 1
        }
        log "✓ OAuth tokens restored"
    fi
    
    # Restore additional data if exists
    if [ -d "$backup_path/data" ]; then
        docker cp "$backup_path/data/." gmail-mcp-server:/app/data/ || {
            warning "Failed to restore additional data (non-critical)"
        }
    fi
    
    # Restart container to apply changes
    info "Restarting container to apply restored data..."
    docker-compose restart gmail-mcp-server || {
        error "Failed to restart Gmail MCP container"
        return 1
    }
    
    # Wait for container to be ready
    sleep 10
    
    # Validate health after restore
    if validate_health; then
        log "✓ Gmail MCP restore completed successfully"
    else
        error "Gmail MCP health check failed after restore"
        return 1
    fi
}

# Function to perform rollback migration
migrate_rollback() {
    local rollback_version="$1"
    
    log "Performing Gmail MCP rollback to version: ${rollback_version:-previous}"
    
    # Find the most recent backup
    local latest_backup=$(find "$BACKUP_DIR" -name "gmail-mcp-migration-*" -type d | sort -r | head -1)
    
    if [ -z "$latest_backup" ]; then
        error "No backup found for rollback"
        return 1
    fi
    
    info "Rolling back using backup: $latest_backup"
    
    # Perform restore using the latest backup
    migrate_restore "$latest_backup"
}

# Function to perform maintenance migration
migrate_maintenance() {
    log "Performing Gmail MCP maintenance..."
    
    # Stop container
    info "Stopping Gmail MCP container for maintenance..."
    docker-compose stop gmail-mcp-server || {
        error "Failed to stop Gmail MCP container"
        return 1
    }
    
    # Clean up old containers and images
    info "Cleaning up old containers and images..."
    docker system prune -f || {
        warning "Failed to clean up Docker system"
    }
    
    # Start container
    info "Starting Gmail MCP container after maintenance..."
    docker-compose up -d gmail-mcp-server || {
        error "Failed to start Gmail MCP container after maintenance"
        return 1
    }
    
    # Wait for container to be ready
    sleep 10
    
    # Validate health after maintenance
    if validate_health; then
        log "✓ Gmail MCP maintenance completed successfully"
    else
        error "Gmail MCP health check failed after maintenance"
        return 1
    fi
}

# Function to show migration status
show_status() {
    log "Gmail MCP Migration Status"
    log "========================="
    
    # Check container status
    if docker ps --format "table {{.Names}}" | grep -q "gmail-mcp-server"; then
        local container_info=$(docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}" | grep "gmail-mcp-server")
        log "Container Status: $container_info"
        
        # Check health
        if validate_health; then
            log "Health Status: ✓ Healthy"
        else
            log "Health Status: ✗ Unhealthy"
        fi
    else
        log "Container Status: ✗ Not running"
    fi
    
    # Show recent backups
    log ""
    log "Recent Backups:"
    find "$BACKUP_DIR" -name "gmail-mcp-migration-*" -type d | sort -r | head -5 | while read backup; do
        local backup_name=$(basename "$backup")
        local backup_date=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$backup" 2>/dev/null || stat -c "%y" "$backup" 2>/dev/null | cut -d' ' -f1-2)
        log "  - $backup_name ($backup_date)"
    done
}

# Function to show help
show_help() {
    echo "Gmail MCP Server Migration and Maintenance Script"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  update [VERSION]     Update Gmail MCP to specified version or latest"
    echo "  restore BACKUP_PATH  Restore Gmail MCP from backup"
    echo "  rollback [VERSION]   Rollback Gmail MCP to previous version"
    echo "  maintenance          Perform maintenance tasks"
    echo "  status               Show current migration status"
    echo "  backup               Create backup of current state"
    echo "  health               Check Gmail MCP health"
    echo "  help                 Show this help message"
    echo ""
    echo "Options:"
    echo "  --backup-dir DIR     Backup directory (default: $BACKUP_DIR)"
    echo "  --log-file FILE      Log file (default: $LOG_FILE)"
    echo "  --verbose            Enable verbose output"
    echo ""
    echo "Examples:"
    echo "  $0 update            # Update to latest version"
    echo "  $0 update 1.1.10     # Update to specific version"
    echo "  $0 restore /path/to/backup  # Restore from backup"
    echo "  $0 rollback          # Rollback to previous version"
    echo "  $0 maintenance       # Perform maintenance"
    echo "  $0 status            # Show current status"
}

# Main function
main() {
    local command="$1"
    shift
    
    # Parse options
    while [[ $# -gt 0 ]]; do
        case $1 in
            --backup-dir)
                BACKUP_DIR="$2"
                shift 2
                ;;
            --log-file)
                LOG_FILE="$2"
                shift 2
                ;;
            --verbose)
                set -x
                shift
                ;;
            *)
                break
                ;;
        esac
    done
    
    # Initialize logging
    mkdir -p "$(dirname "$LOG_FILE")"
    
    log "Gmail MCP Migration Script Started"
    log "=================================="
    
    # Check prerequisites
    check_prerequisites
    
    # Execute command
    case "$command" in
        "update")
            perform_migration "update" "$1"
            ;;
        "restore")
            perform_migration "restore" "$1"
            ;;
        "rollback")
            perform_migration "rollback" "$1"
            ;;
        "maintenance")
            perform_migration "maintenance"
            ;;
        "status")
            show_status
            ;;
        "backup")
            backup_current_state
            ;;
        "health")
            validate_health
            ;;
        "help"|"--help"|"-h")
            show_help
            ;;
        *)
            error "Unknown command: $command"
            show_help
            exit 1
            ;;
    esac
    
    log "Gmail MCP Migration Script Completed"
}

# Run main function
main "$@"
