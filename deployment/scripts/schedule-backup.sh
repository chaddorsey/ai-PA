#!/bin/bash

# PA Ecosystem Backup Scheduling Script
# Manages automated backup scheduling and retention

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/deployment/backups}"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/deployment/logs}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging
LOG_FILE="$LOG_DIR/schedule-backup-$(date +%Y%m%d_%H%M%S).log"
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
PA Ecosystem Backup Scheduling Script

USAGE:
    $0 [COMMAND] [OPTIONS]

COMMANDS:
    install                 Install backup scheduling
    uninstall              Remove backup scheduling
    status                 Show backup schedule status
    run                    Run scheduled backup
    list                   List available backups
    cleanup                Clean up old backups
    test                   Test backup configuration

OPTIONS:
    -h, --help              Show this help message
    -f, --frequency FREQ    Backup frequency (hourly, daily, weekly, monthly)
    -r, --retention DAYS    Backup retention period in days
    -t, --type TYPE         Backup type (full, incremental, config, data)
    -v, --verbose           Enable verbose output

EXAMPLES:
    $0 install --frequency daily --retention 30
    $0 install --frequency weekly --retention 90 --type full
    $0 status
    $0 run
    $0 cleanup --retention 30

EOF
}

# Function to install backup scheduling
install_schedule() {
    local frequency="${FREQUENCY:-daily}"
    local retention="${RETENTION:-30}"
    local backup_type="${BACKUP_TYPE:-full}"
    
    log "Installing backup scheduling..."
    log "Frequency: $frequency"
    log "Retention: $retention days"
    log "Type: $backup_type"
    
    # Create backup script wrapper
    cat > "$PROJECT_ROOT/deployment/scripts/backup-wrapper.sh" << EOF
#!/bin/bash
# Backup wrapper for scheduled backups

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="\$(cd "\$SCRIPT_DIR/../.." && pwd)"
BACKUP_SCRIPT="\$SCRIPT_DIR/backup.sh"
LOG_DIR="\$PROJECT_ROOT/deployment/logs"

# Create log directory
mkdir -p "\$LOG_DIR"

# Run backup
"\$BACKUP_SCRIPT" --type "$backup_type" --verbose >> "\$LOG_DIR/scheduled-backup.log" 2>&1

# Clean up old backups
"\$SCRIPT_DIR/schedule-backup.sh" cleanup --retention $retention >> "\$LOG_DIR/scheduled-backup.log" 2>&1
EOF
    
    chmod +x "$PROJECT_ROOT/deployment/scripts/backup-wrapper.sh"
    
    # Create cron job
    local cron_schedule=""
    case "$frequency" in
        hourly)
            cron_schedule="0 * * * *"
            ;;
        daily)
            cron_schedule="0 2 * * *"
            ;;
        weekly)
            cron_schedule="0 2 * * 0"
            ;;
        monthly)
            cron_schedule="0 2 1 * *"
            ;;
        *)
            log_error "Invalid frequency: $frequency"
            exit 1
            ;;
    esac
    
    # Add cron job
    local cron_job="$cron_schedule $PROJECT_ROOT/deployment/scripts/backup-wrapper.sh"
    
    # Check if cron job already exists
    if crontab -l 2>/dev/null | grep -q "backup-wrapper.sh"; then
        log_warning "Backup cron job already exists. Updating..."
        crontab -l 2>/dev/null | grep -v "backup-wrapper.sh" | crontab -
    fi
    
    # Add new cron job
    (crontab -l 2>/dev/null; echo "$cron_job") | crontab -
    
    log_success "Backup scheduling installed successfully!"
    log_success "Cron job: $cron_job"
    
    # Create backup configuration file
    cat > "$PROJECT_ROOT/deployment/config/backup-schedule.conf" << EOF
# PA Ecosystem Backup Schedule Configuration
# Created: $(date)
# Frequency: $frequency
# Retention: $retention days
# Type: $backup_type

FREQUENCY=$frequency
RETENTION=$retention
BACKUP_TYPE=$backup_type
BACKUP_DIR=$BACKUP_DIR
LOG_DIR=$LOG_DIR
EOF
    
    log_success "Backup configuration saved: $PROJECT_ROOT/deployment/config/backup-schedule.conf"
}

# Function to uninstall backup scheduling
uninstall_schedule() {
    log "Uninstalling backup scheduling..."
    
    # Remove cron job
    if crontab -l 2>/dev/null | grep -q "backup-wrapper.sh"; then
        crontab -l 2>/dev/null | grep -v "backup-wrapper.sh" | crontab -
        log_success "Cron job removed"
    else
        log_warning "No backup cron job found"
    fi
    
    # Remove backup wrapper script
    if [[ -f "$PROJECT_ROOT/deployment/scripts/backup-wrapper.sh" ]]; then
        rm "$PROJECT_ROOT/deployment/scripts/backup-wrapper.sh"
        log_success "Backup wrapper script removed"
    fi
    
    # Remove backup configuration
    if [[ -f "$PROJECT_ROOT/deployment/config/backup-schedule.conf" ]]; then
        rm "$PROJECT_ROOT/deployment/config/backup-schedule.conf"
        log_success "Backup configuration removed"
    fi
    
    log_success "Backup scheduling uninstalled successfully!"
}

# Function to show backup schedule status
show_status() {
    log "Backup Schedule Status"
    echo "===================="
    
    # Check if cron job exists
    if crontab -l 2>/dev/null | grep -q "backup-wrapper.sh"; then
        log_success "Backup cron job is installed"
        echo "Schedule: $(crontab -l 2>/dev/null | grep "backup-wrapper.sh")"
    else
        log_warning "No backup cron job found"
    fi
    
    # Check backup configuration
    if [[ -f "$PROJECT_ROOT/deployment/config/backup-schedule.conf" ]]; then
        log_success "Backup configuration found"
        cat "$PROJECT_ROOT/deployment/config/backup-schedule.conf"
    else
        log_warning "No backup configuration found"
    fi
    
    # Check backup directory
    if [[ -d "$BACKUP_DIR" ]]; then
        log_success "Backup directory exists: $BACKUP_DIR"
        local backup_count=$(find "$BACKUP_DIR" -maxdepth 1 -type d -name "pa-ecosystem-backup-*" | wc -l)
        echo "Number of backups: $backup_count"
        
        if [[ $backup_count -gt 0 ]]; then
            echo "Latest backups:"
            find "$BACKUP_DIR" -maxdepth 1 -type d -name "pa-ecosystem-backup-*" | sort -r | head -5
        fi
    else
        log_warning "Backup directory not found: $BACKUP_DIR"
    fi
}

# Function to run scheduled backup
run_backup() {
    log "Running scheduled backup..."
    
    if [[ -f "$PROJECT_ROOT/deployment/scripts/backup-wrapper.sh" ]]; then
        "$PROJECT_ROOT/deployment/scripts/backup-wrapper.sh"
        log_success "Scheduled backup completed"
    else
        log_error "Backup wrapper script not found. Run 'install' first."
        exit 1
    fi
}

# Function to list backups
list_backups() {
    log "Available Backups"
    echo "================="
    
    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_warning "Backup directory not found: $BACKUP_DIR"
        return
    fi
    
    local backup_count=$(find "$BACKUP_DIR" -maxdepth 1 -type d -name "pa-ecosystem-backup-*" | wc -l)
    
    if [[ $backup_count -eq 0 ]]; then
        log_warning "No backups found"
        return
    fi
    
    echo "Found $backup_count backups:"
    echo
    
    find "$BACKUP_DIR" -maxdepth 1 -type d -name "pa-ecosystem-backup-*" | sort -r | while read -r backup; do
        local backup_name=$(basename "$backup")
        local backup_size=$(du -sh "$backup" | cut -f1)
        local backup_date=$(stat -c %y "$backup" | cut -d' ' -f1)
        local backup_time=$(stat -c %y "$backup" | cut -d' ' -f2 | cut -d'.' -f1)
        
        echo "  $backup_name"
        echo "    Size: $backup_size"
        echo "    Date: $backup_date $backup_time"
        echo
    done
}

# Function to clean up old backups
cleanup_backups() {
    local retention="${RETENTION:-30}"
    
    log "Cleaning up backups older than $retention days..."
    
    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_warning "Backup directory not found: $BACKUP_DIR"
        return
    fi
    
    # Find old backups
    local old_backups=$(find "$BACKUP_DIR" -maxdepth 1 -type d -name "pa-ecosystem-backup-*" -mtime +$retention)
    
    if [[ -z "$old_backups" ]]; then
        log_success "No old backups to clean up"
        return
    fi
    
    local count=0
    echo "$old_backups" | while read -r backup; do
        if [[ -n "$backup" ]]; then
            log "Removing old backup: $(basename "$backup")"
            rm -rf "$backup"
            ((count++))
        fi
    done
    
    log_success "Cleaned up $count old backups"
}

# Function to test backup configuration
test_backup() {
    log "Testing backup configuration..."
    
    # Test backup script
    if [[ -f "$PROJECT_ROOT/deployment/scripts/backup.sh" ]]; then
        log_success "Backup script found"
    else
        log_error "Backup script not found"
        return 1
    fi
    
    # Test backup directory
    if [[ -d "$BACKUP_DIR" ]]; then
        log_success "Backup directory exists: $BACKUP_DIR"
    else
        log_warning "Backup directory not found, creating: $BACKUP_DIR"
        mkdir -p "$BACKUP_DIR"
    fi
    
    # Test Docker
    if docker info >/dev/null 2>&1; then
        log_success "Docker is running"
    else
        log_error "Docker is not running"
        return 1
    fi
    
    # Test docker-compose
    if command -v docker-compose >/dev/null 2>&1; then
        log_success "docker-compose is available"
    else
        log_error "docker-compose is not available"
        return 1
    fi
    
    # Test dry run
    log "Running backup dry run..."
    if "$PROJECT_ROOT/deployment/scripts/backup.sh" --dry-run; then
        log_success "Backup dry run completed successfully"
    else
        log_error "Backup dry run failed"
        return 1
    fi
    
    log_success "Backup configuration test completed successfully!"
}

# Parse command line arguments
COMMAND=""
FREQUENCY=""
RETENTION=""
BACKUP_TYPE=""
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -f|--frequency)
            FREQUENCY="$2"
            shift 2
            ;;
        -r|--retention)
            RETENTION="$2"
            shift 2
            ;;
        -t|--type)
            BACKUP_TYPE="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        install|uninstall|status|run|list|cleanup|test)
            COMMAND="$1"
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Check if command is specified
if [[ -z "$COMMAND" ]]; then
    log_error "Command is required"
    show_help
    exit 1
fi

# Execute command
case "$COMMAND" in
    install)
        install_schedule
        ;;
    uninstall)
        uninstall_schedule
        ;;
    status)
        show_status
        ;;
    run)
        run_backup
        ;;
    list)
        list_backups
        ;;
    cleanup)
        cleanup_backups
        ;;
    test)
        test_backup
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        show_help
        exit 1
        ;;
esac
