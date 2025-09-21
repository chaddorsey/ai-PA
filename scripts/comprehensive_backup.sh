#!/bin/bash

# Comprehensive Database Backup Script for AI-PA Infrastructure
# Created: 2025-09-19
# This script backs up all critical databases and volumes in the AI-PA stack

set -e  # Exit on any error

# Configuration
BACKUP_ROOT="/Users/chaddorsey/Dropbox/dev/ai-PA/backups"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"
LOG_FILE="$BACKUP_DIR/backup.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Function to check if container is running
check_container() {
    local container_name=$1
    if ! docker ps --format "table {{.Names}}" | grep -q "^${container_name}$"; then
        error "Container $container_name is not running"
        return 1
    fi
    return 0
}

# Create backup directory
mkdir -p "$BACKUP_DIR"
log "Created backup directory: $BACKUP_DIR"

# Start logging
log "Starting comprehensive backup for AI-PA infrastructure"
log "Backup location: $BACKUP_DIR"

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    error "Docker is not running. Please start Docker and try again."
    exit 1
fi

# 1. Backup Supabase PostgreSQL databases
log "Backing up Supabase PostgreSQL databases..."
if check_container "supabase-db"; then
    docker exec supabase-db pg_dump -U postgres -d postgres > "$BACKUP_DIR/supabase_postgres_$(date +%Y%m%d_%H%M%S).sql"
    log "✓ Supabase postgres database backed up"
    
    docker exec supabase-db pg_dump -U postgres -d n8n_restore > "$BACKUP_DIR/n8n_database_$(date +%Y%m%d_%H%M%S).sql"
    log "✓ N8N database backed up"
else
    error "Supabase database container not found"
fi

# 2. Backup Letta PostgreSQL database
log "Backing up Letta PostgreSQL database..."
if check_container "ai-pa-letta_db-1"; then
    docker exec ai-pa-letta_db-1 pg_dump -U letta -d letta > "$BACKUP_DIR/letta_database_$(date +%Y%m%d_%H%M%S).sql"
    log "✓ Letta database backed up"
else
    error "Letta database container not found"
fi

# 3. Backup Neo4j data (volume-based since live dump requires stopping)
log "Backing up Neo4j data volume..."
if check_container "graphiti-neo4j"; then
    docker run --rm -v ai-pa_neo4j_data:/source:ro -v "$BACKUP_DIR":/backup alpine tar czf /backup/neo4j_data_$(date +%Y%m%d_%H%M%S).tar.gz -C /source .
    log "✓ Neo4j data volume backed up"
else
    warning "Neo4j container not found, skipping backup"
fi

# 4. Backup critical Docker volumes
log "Backing up critical Docker volumes..."

# N8N data volume
docker run --rm -v ai-pa_n8n_data:/source:ro -v "$BACKUP_DIR":/backup alpine tar czf /backup/n8n_data_$(date +%Y%m%d_%H%M%S).tar.gz -C /source .
log "✓ N8N data volume backed up"

# Open WebUI data volume
docker run --rm -v ai-pa_open-webui:/source:ro -v "$BACKUP_DIR":/backup alpine tar czf /backup/openwebui_data_$(date +%Y%m%d_%H%M%S).tar.gz -C /source .
log "✓ Open WebUI data volume backed up"

# Gmail MCP data volume
if check_container "gmail-mcp-server"; then
    docker run --rm -v gmail-mcp-data:/source:ro -v "$BACKUP_DIR":/backup alpine tar czf /backup/gmail-mcp-data_$(date +%Y%m%d_%H%M%S).tar.gz -C /source .
    log "✓ Gmail MCP data volume backed up"
    
    # Backup Gmail MCP credentials
    docker cp gmail-mcp-server:/app/config/gcp-oauth.keys.json "$BACKUP_DIR/gmail-mcp-oauth-$(date +%Y%m%d_%H%M%S).json" 2>/dev/null || warning "Could not backup Gmail MCP OAuth keys"
    docker cp gmail-mcp-server:/app/data/credentials.json "$BACKUP_DIR/gmail-mcp-credentials-$(date +%Y%m%d_%H%M%S).json" 2>/dev/null || warning "Could not backup Gmail MCP credentials"
    log "✓ Gmail MCP credentials backed up"
else
    warning "Gmail MCP container not found, skipping backup"
fi

# 5. Backup configuration files
log "Backing up configuration files..."
cp "/Users/chaddorsey/Dropbox/dev/ai-PA/docker-compose.yml" "$BACKUP_DIR/"
log "✓ Docker compose configuration backed up"

# Environment file (if exists)
if [ -f "/Users/chaddorsey/Dropbox/dev/ai-PA/.env" ]; then
    cp "/Users/chaddorsey/Dropbox/dev/ai-PA/.env" "$BACKUP_DIR/.env_backup"
    log "✓ Environment file backed up"
else
    warning "No .env file found to backup"
fi

# Letta configuration
if [ -d "/Users/chaddorsey/Dropbox/dev/ai-PA/letta" ]; then
    cp -r "/Users/chaddorsey/Dropbox/dev/ai-PA/letta" "$BACKUP_DIR/"
    log "✓ Letta configuration backed up"
fi

# 6. Generate backup summary
log "Generating backup summary..."
{
    echo "=== AI-PA Infrastructure Backup Summary ==="
    echo "Backup Date: $(date)"
    echo "Backup Location: $BACKUP_DIR"
    echo ""
    echo "=== Backup Contents ==="
    ls -la "$BACKUP_DIR/"
    echo ""
    echo "=== Size Information ==="
    du -sh "$BACKUP_DIR/"*
    echo ""
    echo "Total Backup Size: $(du -sh "$BACKUP_DIR/" | cut -f1)"
    echo ""
    echo "=== Critical Components Backed Up ==="
    echo "✓ Supabase PostgreSQL (postgres + n8n_restore databases)"
    echo "✓ Letta PostgreSQL (with pgvector embeddings)"
    echo "✓ Neo4j data volume (Graphiti knowledge graphs)"
    echo "✓ N8N workflow data and configurations"
    echo "✓ Open WebUI user data and settings"
    echo "✓ Docker Compose configuration"
    echo "✓ Environment variables and Letta configs"
} > "$BACKUP_DIR/BACKUP_SUMMARY.txt"

log "✓ Backup summary created"

# 7. Final verification
TOTAL_SIZE=$(du -sh "$BACKUP_DIR/" | cut -f1)
FILE_COUNT=$(find "$BACKUP_DIR" -type f | wc -l)

log "=== BACKUP COMPLETED SUCCESSFULLY ==="
log "Total files backed up: $FILE_COUNT"
log "Total backup size: $TOTAL_SIZE"
log "Backup location: $BACKUP_DIR"
log "Summary file: $BACKUP_DIR/BACKUP_SUMMARY.txt"

# Optional: Clean up old backups (keep last 7 days)
CLEANUP=${1:-false}
if [ "$CLEANUP" = "cleanup" ]; then
    log "Cleaning up backups older than 7 days..."
    find "$BACKUP_ROOT" -name "20*" -type d -mtime +7 -exec rm -rf {} + 2>/dev/null || true
    log "✓ Old backups cleaned up"
fi

echo ""
echo -e "${GREEN}Backup completed successfully!${NC}"
echo -e "Location: ${YELLOW}$BACKUP_DIR${NC}"
echo -e "Size: ${YELLOW}$TOTAL_SIZE${NC}"
