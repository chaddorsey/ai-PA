#!/bin/bash

# PA Ecosystem Maintenance Script
# Comprehensive maintenance procedures and automation

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/deployment/logs}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/deployment/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging
LOG_FILE="$LOG_DIR/maintenance-$TIMESTAMP.log"
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

log_info() {
    echo -e "${CYAN}[$(date '+%Y-%m-%d %H:%M:%S')] ℹ${NC} $1" | tee -a "$LOG_FILE"
}

# Help function
show_help() {
    cat << EOF
PA Ecosystem Maintenance Script

USAGE:
    $0 [OPTIONS] [TASK]

ARGUMENTS:
    TASK                   Specific maintenance task to run (optional)

OPTIONS:
    -h, --help              Show this help message
    -a, --all               Run all maintenance tasks
    -d, --daily             Run daily maintenance tasks
    -w, --weekly            Run weekly maintenance tasks
    -m, --monthly           Run monthly maintenance tasks
    -y, --yearly            Run yearly maintenance tasks
    -c, --cleanup           Run cleanup tasks only
    -b, --backup            Run backup tasks only
    -u, --update            Run update tasks only
    -v, --verbose           Enable verbose output
    -q, --quiet             Suppress output except errors
    -f, --force             Force maintenance tasks without confirmation
    -o, --output FILE       Save output to file

TASKS:
    system-update           Update system packages and dependencies
    docker-cleanup          Clean up Docker images, containers, and volumes
    log-rotation            Rotate and compress log files
    database-maintenance    Optimize and maintain databases
    backup-verification     Verify backup integrity and completeness
    security-update         Update security patches and configurations
    performance-optimization Optimize system and application performance
    monitoring-setup        Set up monitoring and alerting
    health-check            Run comprehensive health checks
    configuration-audit     Audit and validate configurations

EXAMPLES:
    $0 --daily              # Run daily maintenance tasks
    $0 --weekly             # Run weekly maintenance tasks
    $0 --cleanup            # Run cleanup tasks only
    $0 system-update        # Update system packages
    $0 docker-cleanup       # Clean up Docker resources
    $0 --all --verbose      # Run all maintenance with verbose output

EOF
}

# Parse command line arguments
RUN_ALL=false
RUN_DAILY=false
RUN_WEEKLY=false
RUN_MONTHLY=false
RUN_YEARLY=false
RUN_CLEANUP=false
RUN_BACKUP=false
RUN_UPDATE=false
VERBOSE=false
QUIET=false
FORCE=false
OUTPUT_FILE=""
TASK=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -a|--all)
            RUN_ALL=true
            shift
            ;;
        -d|--daily)
            RUN_DAILY=true
            shift
            ;;
        -w|--weekly)
            RUN_WEEKLY=true
            shift
            ;;
        -m|--monthly)
            RUN_MONTHLY=true
            shift
            ;;
        -y|--yearly)
            RUN_YEARLY=true
            shift
            ;;
        -c|--cleanup)
            RUN_CLEANUP=true
            shift
            ;;
        -b|--backup)
            RUN_BACKUP=true
            shift
            ;;
        -u|--update)
            RUN_UPDATE=true
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
        -f|--force)
            FORCE=true
            shift
            ;;
        -o|--output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -*)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
        *)
            if [[ -z "$TASK" ]]; then
                TASK="$1"
            else
                log_error "Multiple tasks specified: $TASK and $1"
                exit 1
            fi
            shift
            ;;
    esac
done

# Set default behavior
if [[ "$RUN_ALL" == "false" && "$RUN_DAILY" == "false" && "$RUN_WEEKLY" == "false" && "$RUN_MONTHLY" == "false" && "$RUN_YEARLY" == "false" && "$RUN_CLEANUP" == "false" && "$RUN_BACKUP" == "false" && "$RUN_UPDATE" == "false" && -z "$TASK" ]]; then
    RUN_DAILY=true
fi

# Function to confirm action
confirm_action() {
    if [[ "$FORCE" == "true" ]]; then
        return 0
    fi
    
    local message="$1"
    echo -n "$message (y/N): "
    read -r response
    case "$response" in
        [yY]|[yY][eE][sS])
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# Function to update system packages
update_system() {
    log "Updating system packages..."
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew >/dev/null 2>&1; then
            log "Updating Homebrew packages..."
            brew update
            brew upgrade
            brew cleanup
            log_success "Homebrew packages updated"
        else
            log_warning "Homebrew not found, skipping package updates"
        fi
    elif [[ -f /etc/debian_version ]]; then
        # Debian/Ubuntu
        log "Updating APT packages..."
        sudo apt update
        sudo apt upgrade -y
        sudo apt autoremove -y
        sudo apt autoclean
        log_success "APT packages updated"
    elif [[ -f /etc/redhat-release ]]; then
        # CentOS/RHEL
        log "Updating DNF packages..."
        sudo dnf update -y
        sudo dnf autoremove -y
        sudo dnf clean all
        log_success "DNF packages updated"
    else
        log_warning "Unknown package manager, skipping system updates"
    fi
}

# Function to clean up Docker resources
cleanup_docker() {
    log "Cleaning up Docker resources..."
    
    # Remove unused containers
    log "Removing stopped containers..."
    docker container prune -f
    
    # Remove unused images
    log "Removing unused images..."
    docker image prune -f
    
    # Remove unused volumes
    log "Removing unused volumes..."
    docker volume prune -f
    
    # Remove unused networks
    log "Removing unused networks..."
    docker network prune -f
    
    # System cleanup
    log "Running Docker system cleanup..."
    docker system prune -f
    
    log_success "Docker cleanup completed"
}

# Function to rotate logs
rotate_logs() {
    log "Rotating log files..."
    
    # Create log rotation directory
    local log_rotation_dir="$LOG_DIR/rotated"
    mkdir -p "$log_rotation_dir"
    
    # Find log files older than 7 days
    find "$LOG_DIR" -name "*.log" -mtime +7 -type f | while read -r log_file; do
        local basename=$(basename "$log_file")
        local timestamp=$(date +%Y%m%d_%H%M%S)
        local rotated_file="$log_rotation_dir/${basename%.log}-$timestamp.log"
        
        # Compress and move log file
        gzip -c "$log_file" > "${rotated_file}.gz"
        rm "$log_file"
        
        log_info "Rotated: $basename -> ${basename%.log}-$timestamp.log.gz"
    done
    
    # Clean up rotated logs older than 30 days
    find "$log_rotation_dir" -name "*.gz" -mtime +30 -type f -delete
    
    log_success "Log rotation completed"
}

# Function to maintain databases
maintain_databases() {
    log "Maintaining databases..."
    
    # PostgreSQL maintenance
    if docker-compose ps supabase-db | grep -q "Up"; then
        log "Maintaining PostgreSQL database..."
        
        # Analyze tables
        docker-compose exec supabase-db psql -U postgres -c "ANALYZE;"
        
        # Vacuum database
        docker-compose exec supabase-db psql -U postgres -c "VACUUM;"
        
        # Check database size
        local db_size=$(docker-compose exec supabase-db psql -U postgres -t -c "SELECT pg_size_pretty(pg_database_size('postgres'));")
        log_info "PostgreSQL database size: $db_size"
        
        log_success "PostgreSQL maintenance completed"
    else
        log_warning "PostgreSQL database not running, skipping maintenance"
    fi
    
    # Neo4j maintenance
    if docker-compose ps neo4j | grep -q "Up"; then
        log "Maintaining Neo4j database..."
        
        # Check Neo4j status
        if docker-compose exec neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
            # Run Neo4j maintenance queries
            docker-compose exec neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "CALL apoc.warmup.run();"
            
            log_success "Neo4j maintenance completed"
        else
            log_warning "Neo4j database not accessible, skipping maintenance"
        fi
    else
        log_warning "Neo4j database not running, skipping maintenance"
    fi
}

# Function to verify backups
verify_backups() {
    log "Verifying backups..."
    
    if [[ -f "$PROJECT_ROOT/deployment/scripts/verify-backup.sh" ]]; then
        # Run backup verification
        if "$PROJECT_ROOT/deployment/scripts/verify-backup.sh" --latest >> "$LOG_FILE" 2>&1; then
            log_success "Backup verification completed successfully"
        else
            log_error "Backup verification failed"
        fi
    else
        log_warning "Backup verification script not found"
    fi
    
    # Check backup directory size
    if [[ -d "$BACKUP_DIR" ]]; then
        local backup_size=$(du -sh "$BACKUP_DIR" | cut -f1)
        log_info "Backup directory size: $backup_size"
        
        # Check for old backups
        local old_backups=$(find "$BACKUP_DIR" -name "backup-*" -mtime +30 -type d | wc -l)
        if [[ $old_backups -gt 0 ]]; then
            log_warning "Found $old_backups old backups (>30 days)"
        fi
    fi
}

# Function to update security patches
update_security() {
    log "Updating security patches..."
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS security updates
        log "Checking for macOS security updates..."
        softwareupdate -l
    elif [[ -f /etc/debian_version ]]; then
        # Debian/Ubuntu security updates
        log "Installing security updates..."
        sudo apt update
        sudo apt upgrade -y --only-upgrade
        sudo apt autoremove -y
    elif [[ -f /etc/redhat-release ]]; then
        # CentOS/RHEL security updates
        log "Installing security updates..."
        sudo dnf update --security -y
        sudo dnf autoremove -y
    fi
    
    # Update Docker images
    log "Updating Docker images..."
    docker-compose pull
    
    log_success "Security updates completed"
}

# Function to optimize performance
optimize_performance() {
    log "Optimizing system performance..."
    
    # Check system resources
    local cpu_cores
    local total_mem
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        cpu_cores=$(sysctl -n hw.ncpu)
        total_mem=$(sysctl -n hw.memsize)
        total_mem=$((total_mem / 1024 / 1024 / 1024))
    else
        cpu_cores=$(nproc)
        total_mem=$(grep MemTotal /proc/meminfo | awk '{print $2}')
        total_mem=$((total_mem / 1024 / 1024))
    fi
    
    log_info "System resources: ${cpu_cores} CPU cores, ${total_mem}GB RAM"
    
    # Check Docker resource usage
    log "Checking Docker resource usage..."
    docker stats --no-stream | tee -a "$LOG_FILE"
    
    # Optimize Docker settings
    log "Optimizing Docker settings..."
    
    # Check if Docker daemon is running
    if docker info >/dev/null 2>&1; then
        # Set Docker memory limits if not set
        local docker_memory_limit=$(docker info | grep "Total Memory" | awk '{print $3}')
        if [[ -z "$docker_memory_limit" ]]; then
            log_info "Docker memory limit not set"
        else
            log_info "Docker memory limit: $docker_memory_limit"
        fi
    fi
    
    # Clean up temporary files
    log "Cleaning up temporary files..."
    find /tmp -name "*.tmp" -mtime +7 -delete 2>/dev/null || true
    find "$PROJECT_ROOT" -name "*.tmp" -mtime +7 -delete 2>/dev/null || true
    
    log_success "Performance optimization completed"
}

# Function to set up monitoring
setup_monitoring() {
    log "Setting up monitoring..."
    
    # Check if monitoring is already set up
    if [[ -f "$PROJECT_ROOT/deployment/scripts/health-check.sh" ]]; then
        log "Health check script found"
        
        # Set up cron job for health checks
        local cron_job="*/5 * * * * $PROJECT_ROOT/deployment/scripts/health-check.sh >> $LOG_DIR/health-check.log 2>&1"
        
        # Check if cron job already exists
        if crontab -l 2>/dev/null | grep -q "health-check.sh"; then
            log_info "Health check cron job already exists"
        else
            # Add cron job
            (crontab -l 2>/dev/null; echo "$cron_job") | crontab -
            log_success "Health check cron job added"
        fi
    else
        log_warning "Health check script not found"
    fi
    
    # Set up log monitoring
    local log_monitor_job="0 0 * * * $PROJECT_ROOT/deployment/scripts/maintenance.sh --cleanup >> $LOG_DIR/maintenance.log 2>&1"
    
    if crontab -l 2>/dev/null | grep -q "maintenance.sh"; then
        log_info "Maintenance cron job already exists"
    else
        (crontab -l 2>/dev/null; echo "$log_monitor_job") | crontab -
        log_success "Maintenance cron job added"
    fi
    
    log_success "Monitoring setup completed"
}

# Function to run health checks
run_health_checks() {
    log "Running health checks..."
    
    if [[ -f "$PROJECT_ROOT/deployment/scripts/health-check.sh" ]]; then
        if "$PROJECT_ROOT/deployment/scripts/health-check.sh" >> "$LOG_FILE" 2>&1; then
            log_success "Health checks completed successfully"
        else
            log_error "Health checks failed"
        fi
    else
        log_warning "Health check script not found"
    fi
    
    # Check service status
    log "Checking service status..."
    docker-compose ps | tee -a "$LOG_FILE"
}

# Function to audit configurations
audit_configurations() {
    log "Auditing configurations..."
    
    # Check .env file
    if [[ -f "$PROJECT_ROOT/.env" ]]; then
        log "Checking .env file..."
        
        # Check for placeholder values
        local placeholder_count=$(grep -c "CHANGE_ME_" "$PROJECT_ROOT/.env" || true)
        if [[ $placeholder_count -gt 0 ]]; then
            log_warning "Found $placeholder_count placeholder values in .env file"
        else
            log_success "No placeholder values found in .env file"
        fi
        
        # Check for required variables
        local required_vars=("OPENAI_API_KEY" "POSTGRES_PASSWORD" "N8N_ENCRYPTION_KEY")
        for var in "${required_vars[@]}"; do
            if grep -q "^$var=" "$PROJECT_ROOT/.env"; then
                log_success "Required variable $var is set"
            else
                log_error "Required variable $var is missing"
            fi
        done
    else
        log_error ".env file not found"
    fi
    
    # Check docker-compose.yml
    if [[ -f "$PROJECT_ROOT/docker-compose.yml" ]]; then
        log "Validating docker-compose.yml..."
        if docker-compose config >/dev/null 2>&1; then
            log_success "docker-compose.yml is valid"
        else
            log_error "docker-compose.yml has syntax errors"
        fi
    else
        log_error "docker-compose.yml not found"
    fi
    
    log_success "Configuration audit completed"
}

# Function to run daily maintenance
run_daily_maintenance() {
    log "Running daily maintenance tasks..."
    
    # Health checks
    run_health_checks
    
    # Log rotation
    rotate_logs
    
    # Docker cleanup
    cleanup_docker
    
    # Database maintenance
    maintain_databases
    
    # Performance optimization
    optimize_performance
    
    log_success "Daily maintenance completed"
}

# Function to run weekly maintenance
run_weekly_maintenance() {
    log "Running weekly maintenance tasks..."
    
    # Run daily maintenance first
    run_daily_maintenance
    
    # System updates
    update_system
    
    # Backup verification
    verify_backups
    
    # Configuration audit
    audit_configurations
    
    log_success "Weekly maintenance completed"
}

# Function to run monthly maintenance
run_monthly_maintenance() {
    log "Running monthly maintenance tasks..."
    
    # Run weekly maintenance first
    run_weekly_maintenance
    
    # Security updates
    update_security
    
    # Comprehensive cleanup
    cleanup_docker
    
    # Full system optimization
    optimize_performance
    
    log_success "Monthly maintenance completed"
}

# Function to run yearly maintenance
run_yearly_maintenance() {
    log "Running yearly maintenance tasks..."
    
    # Run monthly maintenance first
    run_monthly_maintenance
    
    # Full system update
    update_system
    
    # Complete backup verification
    verify_backups
    
    # Full configuration audit
    audit_configurations
    
    # Setup monitoring
    setup_monitoring
    
    log_success "Yearly maintenance completed"
}

# Function to run specific task
run_task() {
    local task="$1"
    
    case "$task" in
        system-update)
            update_system
            ;;
        docker-cleanup)
            cleanup_docker
            ;;
        log-rotation)
            rotate_logs
            ;;
        database-maintenance)
            maintain_databases
            ;;
        backup-verification)
            verify_backups
            ;;
        security-update)
            update_security
            ;;
        performance-optimization)
            optimize_performance
            ;;
        monitoring-setup)
            setup_monitoring
            ;;
        health-check)
            run_health_checks
            ;;
        configuration-audit)
            audit_configurations
            ;;
        *)
            log_error "Unknown task: $task"
            return 1
            ;;
    esac
}

# Main function
main() {
    log "Starting PA Ecosystem maintenance..."
    log "Maintenance log: $LOG_FILE"
    
    # Run maintenance tasks based on options
    if [[ "$RUN_ALL" == "true" ]]; then
        run_yearly_maintenance
    elif [[ "$RUN_DAILY" == "true" ]]; then
        run_daily_maintenance
    elif [[ "$RUN_WEEKLY" == "true" ]]; then
        run_weekly_maintenance
    elif [[ "$RUN_MONTHLY" == "true" ]]; then
        run_monthly_maintenance
    elif [[ "$RUN_YEARLY" == "true" ]]; then
        run_yearly_maintenance
    elif [[ "$RUN_CLEANUP" == "true" ]]; then
        cleanup_docker
        rotate_logs
    elif [[ "$RUN_BACKUP" == "true" ]]; then
        verify_backups
    elif [[ "$RUN_UPDATE" == "true" ]]; then
        update_system
        update_security
    elif [[ -n "$TASK" ]]; then
        run_task "$TASK"
    fi
    
    log_success "Maintenance completed successfully!"
    log_success "Maintenance log: $LOG_FILE"
    
    # Save output to file if requested
    if [[ -n "$OUTPUT_FILE" ]]; then
        cp "$LOG_FILE" "$OUTPUT_FILE"
        log_success "Output saved to: $OUTPUT_FILE"
    fi
}

# Error handling
trap 'log_error "Maintenance failed at line $LINENO"' ERR

# Run main function
main "$@"
