#!/bin/bash

# PA Ecosystem Rollback Script
# This script rolls back a failed deployment to a clean state

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$DEPLOYMENT_DIR")"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Display help information
show_help() {
    echo "PA Ecosystem Rollback Script"
    echo ""
    echo "Usage: $0 [DEPLOYMENT_ID] [OPTIONS]"
    echo ""
    echo "Arguments:"
    echo "  DEPLOYMENT_ID    ID of the deployment to rollback (optional)"
    echo ""
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -f, --force             Force rollback without confirmation"
    echo "  -c, --clean             Clean up all deployment artifacts"
    echo "  -v, --verbose           Enable verbose output"
    echo ""
    echo "Examples:"
    echo "  $0                      # Rollback latest deployment"
    echo "  $0 pa-deploy-20250120-220500  # Rollback specific deployment"
    echo "  $0 --clean              # Clean up all artifacts"
    echo ""
}

# Parse command line arguments
parse_arguments() {
    DEPLOYMENT_ID=""
    FORCE_ROLLBACK=false
    CLEAN_ALL=false
    VERBOSE=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -f|--force)
                FORCE_ROLLBACK=true
                shift
                ;;
            -c|--clean)
                CLEAN_ALL=true
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -*)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
            *)
                if [[ -z "$DEPLOYMENT_ID" ]]; then
                    DEPLOYMENT_ID="$1"
                else
                    log_error "Multiple deployment IDs provided"
                    exit 1
                fi
                shift
                ;;
        esac
    done
}

# Find latest deployment ID if not provided
find_latest_deployment() {
    if [[ -z "$DEPLOYMENT_ID" ]]; then
        local latest_log=$(ls -t "$DEPLOYMENT_DIR/logs"/deployment-*.log 2>/dev/null | head -1)
        if [[ -n "$latest_log" ]]; then
            DEPLOYMENT_ID=$(basename "$latest_log" | sed 's/deployment-\(.*\)\.log/\1/')
            log_info "Using latest deployment ID: $DEPLOYMENT_ID"
        else
            log_error "No deployment logs found and no deployment ID provided"
            exit 1
        fi
    fi
}

# Confirm rollback
confirm_rollback() {
    if [[ "$FORCE_ROLLBACK" == "true" ]]; then
        return 0
    fi
    
    echo ""
    echo "This will rollback deployment: $DEPLOYMENT_ID"
    echo "The following actions will be performed:"
    echo "  - Stop all running services"
    echo "  - Remove containers and networks"
    echo "  - Restore previous configuration (if backup exists)"
    echo "  - Clean up deployment artifacts"
    echo ""
    
    read -p "Are you sure you want to continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Rollback cancelled by user"
        exit 0
    fi
}

# Stop all services
stop_services() {
    log_info "Stopping all services..."
    
    cd "$PROJECT_ROOT"
    
    # Stop Docker Compose services
    if [[ -f "docker-compose.yml" ]]; then
        if docker-compose ps -q | grep -q .; then
            log_info "Stopping Docker Compose services..."
            docker-compose down
            log_success "Docker Compose services stopped"
        else
            log_info "No Docker Compose services running"
        fi
    else
        log_warning "docker-compose.yml not found"
    fi
    
    # Stop any remaining containers
    local pa_containers=$(docker ps -a --filter "label=project=pa-ecosystem" -q)
    if [[ -n "$pa_containers" ]]; then
        log_info "Stopping remaining PA containers..."
        echo "$pa_containers" | xargs docker stop
        log_success "Remaining containers stopped"
    fi
}

# Remove containers and networks
remove_containers_and_networks() {
    log_info "Removing containers and networks..."
    
    # Remove PA containers
    local pa_containers=$(docker ps -a --filter "label=project=pa-ecosystem" -q)
    if [[ -n "$pa_containers" ]]; then
        log_info "Removing PA containers..."
        echo "$pa_containers" | xargs docker rm -f
        log_success "PA containers removed"
    fi
    
    # Remove PA network
    if docker network ls | grep -q "pa-internal"; then
        log_info "Removing PA network..."
        docker network rm pa-internal
        log_success "PA network removed"
    fi
    
    # Remove unused volumes (be careful with this)
    if [[ "$CLEAN_ALL" == "true" ]]; then
        log_warning "Removing unused volumes (this will delete all data)..."
        read -p "Are you sure? This will delete ALL data! (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker volume prune -f
            log_success "Unused volumes removed"
        else
            log_info "Skipping volume cleanup"
        fi
    fi
}

# Restore configuration from backup
restore_configuration() {
    log_info "Restoring configuration from backup..."
    
    local backup_file="$DEPLOYMENT_DIR/backups/config-${DEPLOYMENT_ID}.env"
    local current_env="$PROJECT_ROOT/.env"
    
    if [[ -f "$backup_file" ]]; then
        log_info "Found configuration backup: $backup_file"
        cp "$backup_file" "$current_env"
        chmod 600 "$current_env"
        log_success "Configuration restored from backup"
    else
        log_warning "No configuration backup found for deployment $DEPLOYMENT_ID"
        
        # Create a minimal .env file to prevent errors
        if [[ ! -f "$current_env" ]]; then
            log_info "Creating minimal .env file..."
            cat > "$current_env" << EOF
# Minimal PA Ecosystem Configuration
# Created during rollback

POSTGRES_PASSWORD=pa_secure_password
SUPABASE_ANON_KEY=your_anon_key_here
SUPABASE_SERVICE_KEY=your_service_key_here
N8N_ENCRYPTION_KEY=$(openssl rand -base64 32)
N8N_WEBHOOK_URL=http://localhost:5678
WEBHOOK_URL=http://localhost:5678
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
GEMINI_API_KEY=your_gemini_key_here
SLACK_BOT_TOKEN=your_slack_bot_token_here
SLACK_APP_TOKEN=your_slack_app_token_here
LETTA_AGENT_ID=your_letta_agent_id_here
CLOUDFLARE_TUNNEL_TOKEN=your_cloudflare_token_here
EOF
            chmod 600 "$current_env"
            log_success "Minimal .env file created"
        fi
    fi
}

# Clean up deployment artifacts
cleanup_artifacts() {
    log_info "Cleaning up deployment artifacts..."
    
    # Remove deployment logs
    local log_file="$DEPLOYMENT_DIR/logs/deployment-${DEPLOYMENT_ID}.log"
    if [[ -f "$log_file" ]]; then
        rm -f "$log_file"
        log_success "Deployment log removed"
    fi
    
    # Remove configuration backup
    local backup_file="$DEPLOYMENT_DIR/backups/config-${DEPLOYMENT_ID}.env"
    if [[ -f "$backup_file" ]]; then
        rm -f "$backup_file"
        log_success "Configuration backup removed"
    fi
    
    # Clean up temporary files
    find "$DEPLOYMENT_DIR" -name "*.tmp" -delete 2>/dev/null || true
    find "$DEPLOYMENT_DIR" -name "*.bak" -delete 2>/dev/null || true
    
    log_success "Deployment artifacts cleaned up"
}

# Clean up all deployment artifacts
cleanup_all() {
    log_info "Cleaning up all deployment artifacts..."
    
    # Remove all deployment logs
    if [[ -d "$DEPLOYMENT_DIR/logs" ]]; then
        rm -f "$DEPLOYMENT_DIR/logs"/*.log
        log_success "All deployment logs removed"
    fi
    
    # Remove all configuration backups
    if [[ -d "$DEPLOYMENT_DIR/backups" ]]; then
        rm -f "$DEPLOYMENT_DIR/backups"/*.env
        log_success "All configuration backups removed"
    fi
    
    # Clean up temporary files
    find "$DEPLOYMENT_DIR" -name "*.tmp" -delete 2>/dev/null || true
    find "$DEPLOYMENT_DIR" -name "*.bak" -delete 2>/dev/null || true
    
    log_success "All deployment artifacts cleaned up"
}

# Display rollback summary
show_rollback_summary() {
    echo ""
    echo -e "${GREEN}=========================================="
    echo "  Rollback Summary"
    echo "==========================================${NC}"
    echo ""
    echo "Deployment ID: $DEPLOYMENT_ID"
    echo "Status: COMPLETED"
    echo ""
    echo "Actions performed:"
    echo "  - Stopped all services"
    echo "  - Removed containers and networks"
    echo "  - Restored configuration from backup"
    echo "  - Cleaned up deployment artifacts"
    echo ""
    echo "System is now in a clean state."
    echo "You can run the deployment script again when ready."
    echo ""
}

# Main rollback function
main() {
    # Parse arguments
    parse_arguments "$@"
    
    # Find deployment ID if not provided
    find_latest_deployment
    
    # Confirm rollback
    confirm_rollback
    
    # Stop services
    stop_services
    
    # Remove containers and networks
    remove_containers_and_networks
    
    # Restore configuration
    restore_configuration
    
    # Clean up artifacts
    if [[ "$CLEAN_ALL" == "true" ]]; then
        cleanup_all
    else
        cleanup_artifacts
    fi
    
    # Show summary
    show_rollback_summary
    
    log_success "Rollback completed successfully"
}

# Run main function
main "$@"
