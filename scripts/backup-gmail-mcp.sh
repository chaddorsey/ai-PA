#!/bin/bash

# Gmail MCP Server Backup Script
# Part of PA Ecosystem Backup and Recovery System
# Created: 2025-01-21

set -e

# Configuration
BACKUP_ROOT="${BACKUP_ROOT:-/Users/chaddorsey/Dropbox/dev/ai-PA/backups}"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_DIR="$BACKUP_ROOT/gmail-mcp/$TIMESTAMP"
LOG_FILE="$BACKUP_DIR/backup.log"

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

# Function to check if container is running
check_container() {
    local container_name=$1
    if ! docker ps --format "table {{.Names}}" | grep -q "^${container_name}$"; then
        error "Container $container_name is not running"
        return 1
    fi
    return 0
}

# Function to backup Gmail MCP credentials
backup_credentials() {
    log "Backing up Gmail MCP credentials..."
    
    if check_container "gmail-mcp-server"; then
        # Create credentials backup directory
        mkdir -p "$BACKUP_DIR/credentials"
        
        # Backup OAuth credentials file
        if docker cp gmail-mcp-server:/app/config/gcp-oauth.keys.json "$BACKUP_DIR/credentials/" 2>/dev/null; then
            log "✓ OAuth credentials backed up"
        else
            warning "OAuth credentials file not found or accessible"
        fi
        
        # Backup stored tokens
        if docker cp gmail-mcp-server:/app/data/credentials.json "$BACKUP_DIR/credentials/" 2>/dev/null; then
            log "✓ OAuth tokens backed up"
            
            # Validate token structure
            if [ -f "$BACKUP_DIR/credentials/credentials.json" ]; then
                if jq empty "$BACKUP_DIR/credentials/credentials.json" 2>/dev/null; then
                    log "✓ Token file validation passed"
                    
                    # Check token expiry
                    EXPIRY=$(jq -r '.expiry_date // empty' "$BACKUP_DIR/credentials/credentials.json" 2>/dev/null)
                    if [ -n "$EXPIRY" ]; then
                        CURRENT_TIME=$(date +%s)000
                        if [ "$EXPIRY" -gt "$CURRENT_TIME" ]; then
                            MINUTES_LEFT=$(( ($EXPIRY - $CURRENT_TIME) / 60000 ))
                            info "Access token expires in ~$MINUTES_LEFT minutes"
                        else
                            warning "Access token has expired (will auto-refresh on next use)"
                        fi
                    fi
                else
                    error "Invalid token file format"
                fi
            fi
        else
            warning "OAuth tokens file not found or accessible"
        fi
        
        # Backup any additional configuration files
        if docker cp gmail-mcp-server:/app/data "$BACKUP_DIR/data/" 2>/dev/null; then
            log "✓ Additional data files backed up"
        fi
        
    else
        error "Gmail MCP server container not running - cannot backup credentials"
        return 1
    fi
}

# Function to backup Gmail MCP configuration
backup_configuration() {
    log "Backing up Gmail MCP configuration..."
    
    # Create configuration backup directory
    mkdir -p "$BACKUP_DIR/config"
    
    # Backup Docker Compose configuration
    if [ -f "docker-compose.yml" ]; then
        # Extract Gmail MCP service configuration
        docker-compose config --services | grep -q "gmail-mcp-server" && {
            docker-compose config gmail-mcp-server > "$BACKUP_DIR/config/gmail-mcp-compose.yml"
            log "✓ Docker Compose configuration backed up"
        }
    fi
    
    # Backup environment variables
    if [ -f ".env" ]; then
        grep -E "GMAIL_|MCP_" .env > "$BACKUP_DIR/config/gmail-mcp-env.txt" 2>/dev/null || true
        log "✓ Environment variables backed up"
    fi
    
    # Backup Gmail MCP source configuration
    if [ -d "gmail-mcp" ]; then
        cp -r gmail-mcp "$BACKUP_DIR/config/" 2>/dev/null || true
        log "✓ Gmail MCP source configuration backed up"
    fi
}

# Function to backup Gmail MCP logs
backup_logs() {
    log "Backing up Gmail MCP logs..."
    
    # Create logs backup directory
    mkdir -p "$BACKUP_DIR/logs"
    
    if check_container "gmail-mcp-server"; then
        # Backup container logs
        docker logs gmail-mcp-server > "$BACKUP_DIR/logs/container.log" 2>&1
        log "✓ Container logs backed up"
        
        # Backup recent logs (last 1000 lines)
        docker logs --tail 1000 gmail-mcp-server > "$BACKUP_DIR/logs/recent.log" 2>&1
        log "✓ Recent logs backed up"
        
        # Extract token refresh events
        docker logs gmail-mcp-server 2>&1 | grep -E "(Auto-saved refreshed tokens|Failed to save refreshed tokens|Token refresh)" > "$BACKUP_DIR/logs/token-refresh.log" 2>/dev/null || true
        log "✓ Token refresh logs backed up"
        
    else
        warning "Gmail MCP server container not running - cannot backup logs"
    fi
}

# Function to validate backup integrity
validate_backup() {
    log "Validating backup integrity..."
    
    local validation_errors=0
    
    # Check if backup directory exists
    if [ ! -d "$BACKUP_DIR" ]; then
        error "Backup directory not created"
        ((validation_errors++))
    fi
    
    # Check if credentials were backed up
    if [ ! -d "$BACKUP_DIR/credentials" ]; then
        error "Credentials directory not created"
        ((validation_errors++))
    fi
    
    # Check if configuration was backed up
    if [ ! -d "$BACKUP_DIR/config" ]; then
        error "Configuration directory not created"
        ((validation_errors++))
    fi
    
    # Check if logs were backed up
    if [ ! -d "$BACKUP_DIR/logs" ]; then
        error "Logs directory not created"
        ((validation_errors++))
    fi
    
    # Validate token file if it exists
    if [ -f "$BACKUP_DIR/credentials/credentials.json" ]; then
        if ! jq empty "$BACKUP_DIR/credentials/credentials.json" 2>/dev/null; then
            error "Invalid token file format"
            ((validation_errors++))
        fi
    fi
    
    # Create backup manifest
    cat > "$BACKUP_DIR/manifest.json" << EOF
{
  "backup_type": "gmail-mcp",
  "timestamp": "$TIMESTAMP",
  "backup_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "components": {
    "credentials": $(ls -la "$BACKUP_DIR/credentials/" 2>/dev/null | wc -l),
    "configuration": $(ls -la "$BACKUP_DIR/config/" 2>/dev/null | wc -l),
    "logs": $(ls -la "$BACKUP_DIR/logs/" 2>/dev/null | wc -l)
  },
  "validation_errors": $validation_errors,
  "backup_size": "$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)"
}
EOF
    
    if [ $validation_errors -eq 0 ]; then
        log "✓ Backup validation passed"
    else
        error "Backup validation failed with $validation_errors errors"
    fi
    
    return $validation_errors
}

# Function to compress backup
compress_backup() {
    log "Compressing backup..."
    
    local backup_name="gmail-mcp-backup-$TIMESTAMP.tar.gz"
    local backup_path="$BACKUP_ROOT/$backup_name"
    
    if tar -czf "$backup_path" -C "$BACKUP_ROOT" "gmail-mcp/$TIMESTAMP"; then
        log "✓ Backup compressed: $backup_path"
        
        # Remove uncompressed directory
        rm -rf "$BACKUP_DIR"
        
        # Calculate and log backup size
        local backup_size=$(du -sh "$backup_path" | cut -f1)
        log "✓ Backup size: $backup_size"
        
        # Update manifest with compressed path
        cat > "$BACKUP_ROOT/gmail-mcp/$TIMESTAMP/manifest.json" << EOF
{
  "backup_type": "gmail-mcp",
  "timestamp": "$TIMESTAMP",
  "backup_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "compressed_path": "$backup_path",
  "backup_size": "$backup_size",
  "status": "compressed"
}
EOF
        
    else
        error "Failed to compress backup"
        return 1
    fi
}

# Function to cleanup old backups
cleanup_old_backups() {
    local retention_days="${GMAIL_BACKUP_RETENTION_DAYS:-30}"
    log "Cleaning up backups older than $retention_days days..."
    
    find "$BACKUP_ROOT" -name "gmail-mcp-backup-*.tar.gz" -type f -mtime +$retention_days -delete 2>/dev/null || true
    find "$BACKUP_ROOT/gmail-mcp" -type d -mtime +$retention_days -exec rm -rf {} + 2>/dev/null || true
    
    log "✓ Old backups cleaned up"
}

# Main backup function
main() {
    log "Starting Gmail MCP server backup..."
    log "Backup directory: $BACKUP_DIR"
    
    # Create backup directory
    mkdir -p "$BACKUP_DIR"
    
    # Start logging
    log "Gmail MCP Backup Log - $(date)"
    log "================================"
    
    # Check if Docker is running
    if ! docker info >/dev/null 2>&1; then
        error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
    
    # Perform backup operations
    backup_credentials
    backup_configuration
    backup_logs
    
    # Validate backup
    if validate_backup; then
        # Compress backup
        compress_backup
        
        # Cleanup old backups
        cleanup_old_backups
        
        log "✓ Gmail MCP backup completed successfully"
        exit 0
    else
        error "Gmail MCP backup validation failed"
        exit 1
    fi
}

# Help function
show_help() {
    echo "Gmail MCP Server Backup Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -d, --directory DIR     Backup directory (default: $BACKUP_ROOT)"
    echo "  -r, --retention DAYS    Retention days for old backups (default: 30)"
    echo "  -v, --verbose           Enable verbose output"
    echo ""
    echo "Environment Variables:"
    echo "  BACKUP_ROOT             Root backup directory"
    echo "  GMAIL_BACKUP_RETENTION_DAYS  Retention days for old backups"
    echo ""
    echo "Examples:"
    echo "  $0                      # Run backup with defaults"
    echo "  $0 -d /custom/backup    # Use custom backup directory"
    echo "  $0 -r 7                 # Keep backups for 7 days"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -d|--directory)
            BACKUP_ROOT="$2"
            shift 2
            ;;
        -r|--retention)
            export GMAIL_BACKUP_RETENTION_DAYS="$2"
            shift 2
            ;;
        -v|--verbose)
            set -x
            shift
            ;;
        *)
            error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Run main function
main "$@"
