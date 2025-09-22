#!/bin/bash
set -e

# Promote Staging to Production Script
# This script promotes staging environment to production with validation and rollback

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
ROLLBACK_TAG="rollback-$(date +%Y%m%d-%H%M%S)"

# Create necessary directories
mkdir -p "$BACKUP_DIR" "$LOGS_DIR"

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOGS_DIR/promote-$(date +%Y%m%d).log"
}

# Success logging
log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] SUCCESS:${NC} $1" | tee -a "$LOGS_DIR/promote-$(date +%Y%m%d).log"
}

# Error logging
log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOGS_DIR/promote-$(date +%Y%m%d).log"
}

# Warning logging
log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOGS_DIR/promote-$(date +%Y%m%d).log"
}

# Confirm action
confirm_action() {
    local message="$1"
    echo -e "${YELLOW}$message${NC}"
    read -p "Do you want to continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Operation cancelled by user"
        exit 0
    fi
}

# Check if staging environment is running
check_staging() {
    log "Checking staging environment..."
    
    if docker-compose -f docker-compose.staging.yml ps -q | grep -q .; then
        log_success "Staging environment is running"
        return 0
    else
        log_error "Staging environment is not running"
        return 1
    fi
}

# Validate staging environment
validate_staging() {
    log "Validating staging environment..."
    
    # Check if all services are healthy
    local unhealthy_services=$(docker-compose -f docker-compose.staging.yml ps --format json | jq -r '.[] | select(.State != "running") | .Name' | wc -l)
    
    if [[ $unhealthy_services -gt 0 ]]; then
        log_error "$unhealthy_services staging services are not running"
        return 1
    fi
    
    # Run health checks
    if [[ -f "$SCRIPT_DIR/health-check.sh" ]]; then
        log "Running health checks..."
        if "$SCRIPT_DIR/health-check.sh" --environment staging; then
            log_success "Health checks passed"
        else
            log_error "Health checks failed"
            return 1
        fi
    else
        log_warning "Health check script not found, skipping health checks"
    fi
    
    # Run workflow tests
    if [[ -f "$SCRIPT_DIR/test-workflows.sh" ]]; then
        log "Running workflow tests..."
        if "$SCRIPT_DIR/test-workflows.sh" --environment staging; then
            log_success "Workflow tests passed"
        else
            log_error "Workflow tests failed"
            return 1
        fi
    else
        log_warning "Workflow test script not found, skipping workflow tests"
    fi
    
    log_success "Staging environment validation completed"
}

# Create production backup
backup_production() {
    log "Creating production backup..."
    
    local backup_file="$BACKUP_DIR/production-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
    
    # Create Git tag for rollback
    git tag "$ROLLBACK_TAG"
    log_success "Created rollback tag: $ROLLBACK_TAG"
    
    # Backup production database
    if docker-compose ps -q supabase-db | grep -q .; then
        log "Backing up production database..."
        docker-compose exec -T supabase-db pg_dump -U postgres postgres > "$BACKUP_DIR/production-db-$(date +%Y%m%d-%H%M%S).sql"
        log_success "Production database backed up"
    fi
    
    # Backup production volumes
    log "Backing up production volumes..."
    docker run --rm -v pa-internal_supabase_db:/data -v "$BACKUP_DIR":/backup alpine tar czf "/backup/production-volumes-$(date +%Y%m%d-%H%M%S).tar.gz" -C /data .
    log_success "Production volumes backed up"
    
    log_success "Production backup completed"
}

# Stop production environment
stop_production() {
    log "Stopping production environment..."
    
    if docker-compose ps -q | grep -q .; then
        docker-compose down
        log_success "Production environment stopped"
    else
        log "No production environment running"
    fi
}

# Deploy to production
deploy_production() {
    log "Deploying to production..."
    
    # Change to project root
    cd "$PROJECT_ROOT"
    
    # Copy staging configuration to production
    if [[ -f ".env.staging" ]]; then
        cp .env.staging .env.production
        log_success "Staging configuration copied to production"
    fi
    
    # Start production environment
    docker-compose up -d
    
    log_success "Production environment deployed"
}

# Wait for production services
wait_for_production() {
    log "Waiting for production services to be ready..."
    
    local max_attempts=30
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        log "Health check attempt $attempt/$max_attempts..."
        
        # Check if all services are healthy
        local unhealthy_services=$(docker-compose ps --format json | jq -r '.[] | select(.State != "running") | .Name' | wc -l)
        
        if [[ $unhealthy_services -eq 0 ]]; then
            log_success "All production services are healthy"
            return 0
        fi
        
        sleep 10
        ((attempt++))
    done
    
    log_error "Production services did not become healthy within expected time"
    return 1
}

# Validate production deployment
validate_production() {
    log "Validating production deployment..."
    
    # Run health checks
    if [[ -f "$SCRIPT_DIR/health-check.sh" ]]; then
        log "Running production health checks..."
        if "$SCRIPT_DIR/health-check.sh" --environment production; then
            log_success "Production health checks passed"
        else
            log_error "Production health checks failed"
            return 1
        fi
    fi
    
    # Run workflow tests
    if [[ -f "$SCRIPT_DIR/test-workflows.sh" ]]; then
        log "Running production workflow tests..."
        if "$SCRIPT_DIR/test-workflows.sh" --environment production; then
            log_success "Production workflow tests passed"
        else
            log_error "Production workflow tests failed"
            return 1
        fi
    fi
    
    log_success "Production deployment validation completed"
}

# Rollback to previous version
rollback() {
    log_error "Rolling back to previous version..."
    
    # Stop current production
    docker-compose down
    
    # Restore from backup
    if [[ -f "$SCRIPT_DIR/restore-from-backup.sh" ]]; then
        "$SCRIPT_DIR/restore-from-backup.sh" --tag "$ROLLBACK_TAG"
    else
        log_error "Restore script not found, manual rollback required"
        return 1
    fi
    
    # Start production
    docker-compose up -d
    
    log_success "Rollback completed"
}

# Cleanup staging environment
cleanup_staging() {
    log "Cleaning up staging environment..."
    
    # Stop staging environment
    docker-compose -f docker-compose.staging.yml down
    
    # Remove staging volumes (optional)
    if [[ "$CLEANUP_STAGING" == "true" ]]; then
        docker volume ls -q | grep staging | xargs docker volume rm
        log_success "Staging volumes cleaned up"
    fi
    
    log_success "Staging environment cleaned up"
}

# Main execution
main() {
    log "Starting promotion from staging to production..."
    log "Project root: $PROJECT_ROOT"
    log "Rollback tag: $ROLLBACK_TAG"
    
    # Confirm action
    confirm_action "This will promote staging to production. This action cannot be undone easily."
    
    # Check staging environment
    if ! check_staging; then
        log_error "Cannot promote: staging environment is not running"
        exit 1
    fi
    
    # Validate staging environment
    if ! validate_staging; then
        log_error "Cannot promote: staging environment validation failed"
        exit 1
    fi
    
    # Create production backup
    backup_production
    
    # Stop production environment
    stop_production
    
    # Deploy to production
    deploy_production
    
    # Wait for production services
    if ! wait_for_production; then
        log_error "Production services failed to start, initiating rollback..."
        rollback
        exit 1
    fi
    
    # Validate production deployment
    if ! validate_production; then
        log_error "Production deployment validation failed, initiating rollback..."
        rollback
        exit 1
    fi
    
    # Cleanup staging environment
    cleanup_staging
    
    log_success "Promotion to production completed successfully!"
    log "Rollback tag: $ROLLBACK_TAG"
    log "To rollback if needed: git checkout $ROLLBACK_TAG && docker-compose up -d"
}

# Help function
show_help() {
    echo "Promote Staging to Production Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help           Show this help message"
    echo "  -c, --cleanup        Clean up staging environment after promotion"
    echo "  -f, --force          Skip confirmation prompts"
    echo ""
    echo "This script promotes staging environment to production with validation"
    echo "and automatic rollback if deployment fails."
}

# Parse command line arguments
CLEANUP_STAGING=false
FORCE=false
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -c|--cleanup)
            CLEANUP_STAGING=true
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Override confirmation if force flag is set
if [[ "$FORCE" == "true" ]]; then
    confirm_action() {
        log "Force mode enabled, skipping confirmation"
    }
fi

# Run main function
main
