#!/bin/bash

# PA Ecosystem Backup Script
# Comprehensive backup system for all PA ecosystem components

set -uo pipefail

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

# Function to translate container path to host path for Docker mounts
# When running inside a container, /workspace maps to /Users/dorseyhomeserver/ai-PA on host
translate_to_host_path() {
    local path="$1"
    # If running inside scheduler container and path starts with /workspace
    if [[ -f /.dockerenv ]] && [[ "$path" == /workspace/* ]]; then
        # Replace /workspace with actual host path
        echo "${path/\/workspace/\/Users\/dorseyhomeserver\/ai-PA}"
    else
        echo "$path"
    fi
}

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
        # Check if volume exists and has data
        if ! docker volume inspect "$volume_name" >/dev/null 2>&1; then
            log_warning "Volume $volume_name does not exist. Skipping."
            return
        fi
        
        local volume_size=$(docker run --rm -v "$volume_name":/data alpine du -sh /data 2>/dev/null | awk '{print $1}')
        if [[ "$volume_size" == "0" || "$volume_size" == "4.0K" ]]; then
            log_warning "Volume $volume_name appears empty ($volume_size). Skipping."
            return
        fi
        
        # Translate path for nested Docker containers
        local backup_dir_host=$(translate_to_host_path "$(dirname "$backup_file")")
        docker run --rm -v "$volume_name":/data -v "$backup_dir_host":/backup alpine tar czf "/backup/$(basename "$backup_file")" -C /data .
        local backup_size=$(du -h "$backup_file" | cut -f1)
        log_success "Volume $volume_name backed up ($volume_size -> $backup_size)"
    fi
}

# Function to discover and backup all named volumes
backup_all_volumes() {
    local backup_dir="$1"
    
    log "Discovering volumes from running containers..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would discover and backup volumes"
        return
    fi
    
    # Get all named volumes from running containers
    # Updated filter to catch both prefixed and non-prefixed project volumes
    local volumes=$(docker ps --format '{{.Names}}' | while read container; do
        docker inspect "$container" 2>/dev/null | jq -r '
            .[0].Mounts[] | 
            select(.Type=="volume" and .Name != null and (
                (.Name | startswith("ai-pa_")) or 
                (.Name | startswith("pa-ecosystem_")) or
                .Name == "content-database-data" or
                .Name == "watch-history-credentials" or
                .Name == "sports-media-data" or
                .Name == "n8n_data" or
                .Name == "n8n_data_test"
            )) | .Name'
    done | sort -u)
    
    if [[ -z "$volumes" ]]; then
        log_warning "No named volumes found in running containers"
        return
    fi
    
    local count=0
    for volume in $volumes; do
        backup_volume "$volume" "$backup_dir/${volume}_${TIMESTAMP}.tar.gz"
        ((count++)) || true
        # Brief pause between volume exports to reduce memory spikes
        sleep 5
    done
    
    log_success "Backed up $count volumes"
}

# Function to backup configuration files
backup_config() {
    local config_dir="$1"
    local backup_file="$2"
    
    log "Backing up configuration: $config_dir"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would backup configuration $config_dir to $backup_file"
    else
        # Special handling for deployment/ directory to exclude backups subfolder
        if [[ "$(basename "$config_dir")" == "deployment" ]]; then
            tar czf "$backup_file" --exclude="backups" --exclude='._*' --exclude='.DS_Store' -C "$(dirname "$config_dir")" "$(basename "$config_dir")"
        else
            tar czf "$backup_file" --exclude='._*' --exclude='.DS_Store' -C "$(dirname "$config_dir")" "$(basename "$config_dir")"
        fi
        log_success "Configuration $config_dir backed up to $backup_file"
    fi
}

# Function to backup host filesystem data (not in Docker volumes)
# This captures local databases, credentials, and data files that are stored
# directly on the host filesystem rather than in Docker volumes
backup_host_data() {
    local backup_dir="$1"
    
    log "Backing up host filesystem data..."
    
    mkdir -p "$backup_dir"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would backup host filesystem data"
        return
    fi
    
    local host_backup_count=0
    
    # 1. Auto-Madden SQLite Databases and Data Files (~72 MB)
    if [[ -d "$PROJECT_ROOT/auto-madden/data" ]]; then
        log "Backing up Auto-Madden databases and data..."
        # Create a file list of what exists to include
        local auto_madden_files=""
        [[ -f "$PROJECT_ROOT/auto-madden/data/nfl_plays_2024.db" ]] && auto_madden_files="$auto_madden_files auto-madden/data/nfl_plays_2024.db"
        [[ -f "$PROJECT_ROOT/auto-madden/data/nfl_plays_2025.db" ]] && auto_madden_files="$auto_madden_files auto-madden/data/nfl_plays_2025.db"
        [[ -f "$PROJECT_ROOT/auto-madden/data/nfl_insights_2025.db" ]] && auto_madden_files="$auto_madden_files auto-madden/data/nfl_insights_2025.db"
        [[ -f "$PROJECT_ROOT/auto-madden/data/game_schedule_2024.json" ]] && auto_madden_files="$auto_madden_files auto-madden/data/game_schedule_2024.json"
        [[ -f "$PROJECT_ROOT/auto-madden/data/espn_nfl_pro_mapping.json" ]] && auto_madden_files="$auto_madden_files auto-madden/data/espn_nfl_pro_mapping.json"
        [[ -f "$PROJECT_ROOT/auto-madden/data/game_id_mapping.json" ]] && auto_madden_files="$auto_madden_files auto-madden/data/game_id_mapping.json"
        [[ -d "$PROJECT_ROOT/auto-madden/data/processed_insights" ]] && auto_madden_files="$auto_madden_files auto-madden/data/processed_insights"
        
        if [[ -n "$auto_madden_files" ]]; then
            tar czf "$backup_dir/auto-madden-data_$TIMESTAMP.tar.gz" \
                --exclude='._*' --exclude='.DS_Store' \
                -C "$PROJECT_ROOT" \
                $auto_madden_files \
                2>/dev/null || log_warning "Some Auto-Madden data files could not be backed up"
            local size=$(du -h "$backup_dir/auto-madden-data_$TIMESTAMP.tar.gz" 2>/dev/null | cut -f1)
            log_success "Auto-Madden data backed up ($size)"
            ((host_backup_count++)) || true
        else
            log_warning "No Auto-Madden data files found"
        fi
    fi
    
    # 2. Auto-Madden Credentials - Browser states with NFL+ Pro login (~210 MB)
    if [[ -d "$PROJECT_ROOT/auto-madden/credentials" ]]; then
        log "Backing up Auto-Madden credentials (browser states)..."
        tar czf "$backup_dir/auto-madden-credentials_$TIMESTAMP.tar.gz" \
            --exclude='._*' --exclude='.DS_Store' \
            -C "$PROJECT_ROOT" \
            auto-madden/credentials \
            2>/dev/null || log_warning "Auto-Madden credentials backup had issues"
        local size=$(du -h "$backup_dir/auto-madden-credentials_$TIMESTAMP.tar.gz" 2>/dev/null | cut -f1)
        log_success "Auto-Madden credentials backed up ($size)"
        ((host_backup_count++)) || true
    fi
    
    # 3. NFL Pro Scraper Credentials and Data (~58 MB)
    if [[ -d "$PROJECT_ROOT/auto-madden/nfl-pro-scraper/credentials" ]]; then
        log "Backing up NFL Pro Scraper credentials..."
        tar czf "$backup_dir/nfl-pro-scraper-credentials_$TIMESTAMP.tar.gz" \
            --exclude='._*' --exclude='.DS_Store' \
            -C "$PROJECT_ROOT" \
            auto-madden/nfl-pro-scraper/credentials \
            2>/dev/null || log_warning "NFL Pro Scraper credentials backup had issues"
        local size=$(du -h "$backup_dir/nfl-pro-scraper-credentials_$TIMESTAMP.tar.gz" 2>/dev/null | cut -f1)
        log_success "NFL Pro Scraper credentials backed up ($size)"
        ((host_backup_count++)) || true
    fi
    
    # Also backup NFL Pro Scraper data if it exists
    if [[ -d "$PROJECT_ROOT/auto-madden/nfl-pro-scraper/data" ]]; then
        log "Backing up NFL Pro Scraper data..."
        tar czf "$backup_dir/nfl-pro-scraper-data_$TIMESTAMP.tar.gz" \
            --exclude='._*' --exclude='.DS_Store' \
            -C "$PROJECT_ROOT" \
            auto-madden/nfl-pro-scraper/data \
            2>/dev/null || log_warning "NFL Pro Scraper data backup had issues"
        local size=$(du -h "$backup_dir/nfl-pro-scraper-data_$TIMESTAMP.tar.gz" 2>/dev/null | cut -f1)
        log_success "NFL Pro Scraper data backed up ($size)"
        ((host_backup_count++)) || true
    fi
    
    # 4. Sports & Media Credentials - OAuth tokens for streaming services (~2.6 MB)
    if [[ -d "$PROJECT_ROOT/sports-and-media-tools/credentials" ]]; then
        log "Backing up Sports & Media credentials (streaming service OAuth)..."
        tar czf "$backup_dir/sports-media-credentials_$TIMESTAMP.tar.gz" \
            --exclude='._*' --exclude='.DS_Store' \
            -C "$PROJECT_ROOT" \
            sports-and-media-tools/credentials \
            2>/dev/null || log_warning "Sports & Media credentials backup had issues"
        local size=$(du -h "$backup_dir/sports-media-credentials_$TIMESTAMP.tar.gz" 2>/dev/null | cut -f1)
        log_success "Sports & Media credentials backed up ($size)"
        ((host_backup_count++)) || true
    fi
    
    # 5. Sports & Media Data
    if [[ -d "$PROJECT_ROOT/sports-and-media-tools/data" ]]; then
        log "Backing up Sports & Media data..."
        tar czf "$backup_dir/sports-media-data_$TIMESTAMP.tar.gz" \
            --exclude='._*' --exclude='.DS_Store' \
            -C "$PROJECT_ROOT" \
            sports-and-media-tools/data \
            2>/dev/null || log_warning "Sports & Media data backup had issues"
        local size=$(du -h "$backup_dir/sports-media-data_$TIMESTAMP.tar.gz" 2>/dev/null | cut -f1)
        log_success "Sports & Media data backed up ($size)"
        ((host_backup_count++)) || true
    fi
    
    # 6. Letta Filesystem Repository (~31 MB)
    if [[ -d "$PROJECT_ROOT/letta_filesystem_repo" ]]; then
        log "Backing up Letta filesystem repository..."
        tar czf "$backup_dir/letta-filesystem-repo_$TIMESTAMP.tar.gz" \
            --exclude='._*' --exclude='.DS_Store' \
            -C "$PROJECT_ROOT" \
            letta_filesystem_repo \
            2>/dev/null || log_warning "Letta filesystem repo backup had issues"
        local size=$(du -h "$backup_dir/letta-filesystem-repo_$TIMESTAMP.tar.gz" 2>/dev/null | cut -f1)
        log_success "Letta filesystem repo backed up ($size)"
        ((host_backup_count++)) || true
    fi
    
    # 7. Slack auth state file
    if [[ -f "$PROJECT_ROOT/slack_auth_state.json" ]]; then
        log "Backing up Slack auth state..."
        cp "$PROJECT_ROOT/slack_auth_state.json" "$backup_dir/slack_auth_state_$TIMESTAMP.json"
        log_success "Slack auth state backed up"
        ((host_backup_count++)) || true
    fi
    
    # 8. Gmail MCP OAuth keys (if stored on host, not just in volume)
    if [[ -f "$PROJECT_ROOT/gmail-mcp/gcp-oauth.keys.json" ]]; then
        log "Backing up Gmail MCP OAuth keys..."
        cp "$PROJECT_ROOT/gmail-mcp/gcp-oauth.keys.json" "$backup_dir/gmail-mcp-oauth-keys_$TIMESTAMP.json"
        log_success "Gmail MCP OAuth keys backed up"
        ((host_backup_count++)) || true
    fi
    
    # 9. Watch History Service credentials (if stored on host)
    if [[ -d "$PROJECT_ROOT/sports-and-media-tools/watch-history-service/credentials" ]]; then
        log "Backing up Watch History Service credentials..."
        tar czf "$backup_dir/watch-history-credentials_$TIMESTAMP.tar.gz" \
            --exclude='._*' --exclude='.DS_Store' \
            -C "$PROJECT_ROOT" \
            sports-and-media-tools/watch-history-service/credentials \
            2>/dev/null || log_warning "Watch History credentials backup had issues"
        local size=$(du -h "$backup_dir/watch-history-credentials_$TIMESTAMP.tar.gz" 2>/dev/null | cut -f1)
        log_success "Watch History credentials backed up ($size)"
        ((host_backup_count++)) || true
    fi
    
    # 10. Smaug Twitter Bookmarks Archive
    if [[ -d "$PROJECT_ROOT/smaug-data" ]]; then
        log "Backing up Smaug bookmarks archive..."
        tar czf "$backup_dir/smaug-data_$TIMESTAMP.tar.gz" \
            --exclude='._*' --exclude='.DS_Store' \
            -C "$PROJECT_ROOT" \
            smaug-data \
            2>/dev/null || log_warning "Smaug data backup had issues"
        local size=$(du -h "$backup_dir/smaug-data_$TIMESTAMP.tar.gz" 2>/dev/null | cut -f1)
        log_success "Smaug bookmarks archive backed up ($size)"
        ((host_backup_count++)) || true
    fi

    log_success "Host data backup complete: $host_backup_count items backed up"
}

# Function to backup all databases dynamically
backup_all_databases() {
    local backup_dir="$1"
    
    log "Discovering and backing up all databases..."
    
    if ! is_service_running "supabase-db"; then
        log_warning "Database service is not running. Skipping database discovery."
        return
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would backup all databases"
        return
    fi
    
    # Cluster-wide backup (includes all DBs, roles, permissions)
    log "Creating cluster-wide backup with pg_dumpall..."
    docker-compose exec -T supabase-db pg_dumpall -U postgres > "$backup_dir/pg_cluster_$TIMESTAMP.sql"
    log_success "Cluster-wide backup created: pg_cluster_$TIMESTAMP.sql"

    # Let Docker VM release memory before individual dumps
    sleep 15

    # List and backup individual databases
    local databases=$(docker-compose exec -T supabase-db psql -U postgres -tA -c "SELECT datname FROM pg_database WHERE datistemplate = false AND datname != 'postgres';")

    for db in $databases; do
        log "Backing up individual database: $db"
        docker-compose exec -T supabase-db pg_dump -U postgres "$db" > "$backup_dir/${db}_$TIMESTAMP.sql"
        log_success "Database $db backed up"
        # Brief pause between dumps to reduce peak memory
        sleep 5
    done
}

# Function to backup Letta agent exports and memory blocks
backup_letta_exports() {
    local export_dir="$1"
    
    log "Backing up Letta agent exports and memory blocks..."
    
    # Determine Letta base URL (try container-internal first, then localhost)
    local LETTA_BASE_URL="${LETTA_BASE_URL:-http://letta:8283}"
    local LETTA_API_TOKEN="${LETTA_API_TOKEN:-}"
    
    # Create export directories
    mkdir -p "$export_dir/agents" "$export_dir/memory"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would backup Letta exports from $LETTA_BASE_URL"
        return
    fi
    
    # Check if Letta is accessible with detailed logging
    log "Checking Letta health at $LETTA_BASE_URL..."
    local health_response=""
    health_response=$(curl -sS --connect-timeout 5 "$LETTA_BASE_URL/v1/health/" 2>&1) || true
    
    if [[ -z "$health_response" ]] || ! echo "$health_response" | grep -q "ok\|healthy\|true" 2>/dev/null; then
        log_warning "Letta service not accessible at $LETTA_BASE_URL (response: $health_response). Trying localhost..."
        LETTA_BASE_URL="http://127.0.0.1:8283"
        health_response=$(curl -sS --connect-timeout 5 "$LETTA_BASE_URL/v1/health/" 2>&1) || true
        if [[ -z "$health_response" ]] || ! echo "$health_response" | grep -q "ok\|healthy\|true" 2>/dev/null; then
            log_warning "Letta service not accessible at localhost either. Skipping Letta exports."
            log_warning "Health response: $health_response"
            # Save diagnostic info
            echo "Letta Export Diagnostic - $(date)" > "$export_dir/LETTA_EXPORT_FAILED.txt"
            echo "Tried URLs: http://letta:8283, http://127.0.0.1:8283" >> "$export_dir/LETTA_EXPORT_FAILED.txt"
            echo "Last response: $health_response" >> "$export_dir/LETTA_EXPORT_FAILED.txt"
            return
        fi
    fi
    
    log_success "Letta service accessible at $LETTA_BASE_URL"
    log "Health response: $health_response"
    
    # Build auth header if token is provided
    local AUTH_HEADER=""
    if [[ -n "$LETTA_API_TOKEN" ]]; then
        AUTH_HEADER="Authorization: Bearer $LETTA_API_TOKEN"
    fi
    
    # Export all agents
    log "Fetching agent list..."
    local agents_response=$(mktemp)
    if [[ -n "$AUTH_HEADER" ]]; then
        curl -sSL -H "$AUTH_HEADER" "$LETTA_BASE_URL/v1/agents?limit=1000" > "$agents_response" 2>/dev/null || true
    else
        curl -sSL "$LETTA_BASE_URL/v1/agents?limit=1000" > "$agents_response" 2>/dev/null || true
    fi
    
    # Check if response is valid JSON
    if ! jq -e . >/dev/null 2>&1 < "$agents_response"; then
        log_warning "Failed to fetch agents list or invalid JSON response"
        rm "$agents_response"
        return
    fi
    
    # Letta API returns array directly, not {items: [...]}
    local agent_count=$(jq -r '. | length' "$agents_response" 2>/dev/null || echo "0")
    log "Found $agent_count agents to export"
    
    if [[ "$agent_count" -eq 0 ]]; then
        log_warning "No agents found to export"
        rm "$agents_response"
        return
    fi
    
    # Export each agent (try legacy format, then fall back to non-legacy, then retrieve)
    jq -r '.[].id' "$agents_response" 2>/dev/null | while read -r agent_id; do
        if [[ -z "$agent_id" ]]; then
            continue
        fi
        
        log "Exporting agent: $agent_id"
        local agent_file="$export_dir/agents/${agent_id}.json"
        local status_code=""
        # 1) Legacy export attempt
        if [[ -n "$AUTH_HEADER" ]]; then
            status_code=$(curl -sS -w "%{http_code}" -H "$AUTH_HEADER" \
                "$LETTA_BASE_URL/v1/agents/$agent_id/export?use_legacy_format=true" \
                -o "$agent_file" 2>/dev/null || echo "")
        else
            status_code=$(curl -sS -w "%{http_code}" \
                "$LETTA_BASE_URL/v1/agents/$agent_id/export?use_legacy_format=true" \
                -o "$agent_file" 2>/dev/null || echo "")
        fi
        # If legacy returned 200 and file doesn't look like an error JSON, accept it
        if [[ "$status_code" == "200" && -s "$agent_file" && ! $(grep -q '"detail"' "$agent_file"; echo $?) -eq 0 ]]; then
            local agent_size=$(du -h "$agent_file" | cut -f1)
            log_success "Agent $agent_id exported (legacy) ($agent_size)"
        else
            log_warning "Legacy export failed for $agent_id (status=$status_code). Trying non-legacy..."
            # 2) Non-legacy export attempt
            if [[ -n "$AUTH_HEADER" ]]; then
                status_code=$(curl -sS -w "%{http_code}" -H "$AUTH_HEADER" \
                    "$LETTA_BASE_URL/v1/agents/$agent_id/export" \
                    -o "$agent_file" 2>/dev/null || echo "")
            else
                status_code=$(curl -sS -w "%{http_code}" \
                    "$LETTA_BASE_URL/v1/agents/$agent_id/export" \
                    -o "$agent_file" 2>/dev/null || echo "")
            fi
            if [[ "$status_code" == "200" && -s "$agent_file" && ! $(grep -q '"detail"' "$agent_file"; echo $?) -eq 0 ]]; then
                local agent_size=$(du -h "$agent_file" | cut -f1)
                log_success "Agent $agent_id exported (non-legacy) ($agent_size)"
            else
                log_warning "Non-legacy export failed for $agent_id (status=$status_code). Falling back to retrieve..."
                # 3) Retrieve agent details as last resort
                if [[ -n "$AUTH_HEADER" ]]; then
                    status_code=$(curl -sS -w "%{http_code}" -H "$AUTH_HEADER" \
                        "$LETTA_BASE_URL/v1/agents/$agent_id" \
                        -o "$agent_file" 2>/dev/null || echo "")
                else
                    status_code=$(curl -sS -w "%{http_code}" \
                        "$LETTA_BASE_URL/v1/agents/$agent_id" \
                        -o "$agent_file" 2>/dev/null || echo "")
                fi
                if [[ "$status_code" == "200" && -s "$agent_file" && ! $(grep -q '"detail"' "$agent_file"; echo $?) -eq 0 ]]; then
                    local agent_size=$(du -h "$agent_file" | cut -f1)
                    log_success "Agent $agent_id retrieved as fallback ($agent_size)"
                else
                    log_warning "Agent $agent_id retrieval failed (status=$status_code) or returned error JSON"
                fi
            fi
        fi
    done
    
    rm "$agents_response"
    
    # Export memory blocks
    log "Fetching memory blocks..."
    if [[ -n "$AUTH_HEADER" ]]; then
        curl -sSL -H "$AUTH_HEADER" "$LETTA_BASE_URL/v1/blocks?limit=1000" \
            -o "$export_dir/memory/blocks_all.json" 2>/dev/null || true
    else
        curl -sSL "$LETTA_BASE_URL/v1/blocks?limit=1000" \
            -o "$export_dir/memory/blocks_all.json" 2>/dev/null || true
    fi
    
    if [[ -s "$export_dir/memory/blocks_all.json" ]]; then
        # Letta API returns array directly for blocks too
        local block_count=$(jq -r '. | length' "$export_dir/memory/blocks_all.json" 2>/dev/null || echo "0")
        log_success "Memory blocks exported: $block_count blocks"
    else
        log_warning "Memory blocks export is empty or failed"
    fi
}

# Function to record Git state
record_git_state() {
    local git_ref_file="$1"
    local repo_snapshot_file="$2"
    
    log "Recording Git state..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would record Git state"
        return
    fi
    
    # Check if we're in a Git repository
    if ! git rev-parse --git-dir >/dev/null 2>&1; then
        log_warning "Not in a Git repository. Skipping Git state capture."
        return
    fi
    
    # Record Git reference information
    cat > "$git_ref_file" << EOF
# PA Ecosystem Backup - Git Reference
# Created: $(date)

Commit: $(git rev-parse HEAD)
Branch: $(git rev-parse --abbrev-ref HEAD)
Date: $(git log -1 --format=%cd)
Author: $(git log -1 --format=%an)
Message: $(git log -1 --format=%s)

## Status:
$(git status --porcelain=v1)

## Recent Commits:
$(git log --oneline -10)
EOF
    
    log_success "Git reference saved: $git_ref_file"
    
    # Skip creating full git snapshot - redundant since GitHub already stores all commits
    # The GIT_REFERENCE.txt file above provides enough metadata to identify the exact commit
    # If source files are needed, they can be restored from GitHub using the commit hash
    log "Skipping git snapshot creation (source code already backed up in GitHub)"
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
        find "$BACKUP_PATH" -type f -name "*.tar.gz" -o -name "*.sql" -o -name "*.env" -o -name "*.json" -o -name "*.txt" | while read -r file; do
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
    mkdir -p "$BACKUP_PATH"/{databases,volumes,configs,logs,letta_exports,host_data}
    
    # Backup all databases (dynamic discovery + cluster backup)
    # This is the heaviest phase — pg_dumpall inflates Docker VM memory
    if [[ "$BACKUP_TYPE" == "full" || "$BACKUP_TYPE" == "data" ]]; then
        backup_all_databases "$BACKUP_PATH/databases"
        log "Pausing 30s to let Docker VM release memory after DB dumps..."
        sleep 30
    fi

    # Backup volumes (dynamic discovery)
    if [[ "$BACKUP_TYPE" == "full" || "$BACKUP_TYPE" == "data" ]]; then
        backup_all_volumes "$BACKUP_PATH/volumes"
        log "Pausing 15s between backup phases..."
        sleep 15
    fi

    # Backup host filesystem data (local databases, credentials, data files)
    if [[ "$BACKUP_TYPE" == "full" || "$BACKUP_TYPE" == "data" ]]; then
        backup_host_data "$BACKUP_PATH/host_data"
    fi

    # Backup configuration files
    if [[ "$BACKUP_TYPE" == "full" || "$BACKUP_TYPE" == "config" ]]; then
        backup_config ".env" "$BACKUP_PATH/configs/env_$TIMESTAMP.tar.gz" || log_warning "Config backup failed for .env, continuing..."
        backup_config "docker-compose.yml" "$BACKUP_PATH/configs/docker-compose_$TIMESTAMP.tar.gz" || log_warning "Config backup failed for docker-compose.yml, continuing..."
        backup_config "deployment/" "$BACKUP_PATH/configs/deployment_$TIMESTAMP.tar.gz" || log_warning "Config backup failed for deployment/, continuing..."
        backup_config "docs/" "$BACKUP_PATH/configs/docs_$TIMESTAMP.tar.gz" || log_warning "Config backup failed for docs/, continuing..."
    fi

    # Backup service configurations
    if [[ "$BACKUP_TYPE" == "full" || "$BACKUP_TYPE" == "services" ]]; then
        # Backup Letta agents and memory via API
        if ! backup_letta_exports "$BACKUP_PATH/letta_exports"; then
            log_warning "Letta exports failed, continuing with remaining backups..."
        fi

        # Backup n8n workflows
        if is_service_running "n8n"; then
            docker-compose exec -T n8n n8n export:workflow --backup --output=/tmp/n8n_backup.json 2>/dev/null || true
            docker cp "$(docker-compose ps -q n8n)":/tmp/n8n_backup.json "$BACKUP_PATH/configs/n8n_workflows.json" 2>/dev/null || true
        fi

        # Backup Gitea via gitea dump (application-aware, SQLite-consistent).
        # The gitea-data volume is also captured in volume backup as belt-and-suspenders;
        # the dump is the authoritative restore artifact for repos + db + config.
        if is_service_running "gitea"; then
            log "Creating Gitea application dump..."
            mkdir -p "$BACKUP_PATH/gitea"
            local dump_dir="/tmp/gitea-dump-$TIMESTAMP"
            # gitea dump runs as 'git' user; produces a single timestamped zip
            docker exec -u git gitea sh -c "mkdir -p $dump_dir && cd $dump_dir && gitea dump -c /data/gitea/conf/app.ini --type zip" >/dev/null 2>&1 || \
                log_warning "Gitea dump failed; gitea-data volume tar from backup_all_volumes is the fallback restore source"
            # Copy any produced dump out
            docker exec gitea sh -c "ls $dump_dir/*.zip 2>/dev/null | head -1" 2>/dev/null | while read dump_path; do
                if [[ -n "$dump_path" ]]; then
                    docker cp "gitea:$dump_path" "$BACKUP_PATH/gitea/$(basename $dump_path)" 2>/dev/null && \
                        log_success "Gitea dump saved: $BACKUP_PATH/gitea/$(basename $dump_path)"
                fi
            done
            # Cleanup in-container dump dir
            docker exec -u git gitea sh -c "rm -rf $dump_dir" 2>/dev/null || true
        fi
    fi
    
    # Record Git state (for all backup types)
    record_git_state "$BACKUP_PATH/GIT_REFERENCE.txt" "$BACKUP_PATH/configs/git_snapshot_$TIMESTAMP.tar.gz"
    
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
