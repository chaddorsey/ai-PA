#!/bin/bash

# PA Ecosystem Backup Verification Script
# Verifies backup integrity and completeness

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
LOG_FILE="$LOG_DIR/verify-backup-$(date +%Y%m%d_%H%M%S).log"
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
PA Ecosystem Backup Verification Script

USAGE:
    $0 [OPTIONS] BACKUP_PATH

ARGUMENTS:
    BACKUP_PATH            Path to backup directory or backup name

OPTIONS:
    -h, --help              Show this help message
    -a, --all               Verify all backups
    -l, --latest            Verify latest backup only
    -c, --check-integrity   Check file integrity (checksums)
    -s, --check-size        Check backup sizes
    -m, --check-manifest    Check backup manifest
    -v, --verbose           Enable verbose output
    -q, --quiet             Suppress output except errors

EXAMPLES:
    $0 latest               # Verify latest backup
    $0 /backups/backup-20240121_120000  # Verify specific backup
    $0 --all                # Verify all backups
    $0 --latest --check-integrity  # Verify latest with integrity check

EOF
}

# Parse command line arguments
VERIFY_ALL=false
VERIFY_LATEST=false
CHECK_INTEGRITY=false
CHECK_SIZE=false
CHECK_MANIFEST=false
VERBOSE=false
QUIET=false
BACKUP_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -a|--all)
            VERIFY_ALL=true
            shift
            ;;
        -l|--latest)
            VERIFY_LATEST=true
            shift
            ;;
        -c|--check-integrity)
            CHECK_INTEGRITY=true
            shift
            ;;
        -s|--check-size)
            CHECK_SIZE=true
            shift
            ;;
        -m|--check-manifest)
            CHECK_MANIFEST=true
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

# Function to verify backup manifest
verify_manifest() {
    local backup_path="$1"
    local manifest_file="$backup_path/BACKUP_MANIFEST.md"
    
    log "Verifying backup manifest: $manifest_file"
    
    if [[ ! -f "$manifest_file" ]]; then
        log_error "Backup manifest not found: $manifest_file"
        return 1
    fi
    
    log_success "Backup manifest found"
    
    if [[ "$CHECK_MANIFEST" == "true" ]]; then
        # Check manifest content
        if grep -q "PA Ecosystem Backup Manifest" "$manifest_file"; then
            log_success "Manifest header found"
        else
            log_error "Invalid manifest header"
            return 1
        fi
        
        if grep -q "Backup Type:" "$manifest_file"; then
            log_success "Backup type information found"
        else
            log_warning "Backup type information missing"
        fi
        
        if grep -q "Backup Contents:" "$manifest_file"; then
            log_success "Backup contents section found"
        else
            log_warning "Backup contents section missing"
        fi
    fi
    
    return 0
}

# Function to verify backup structure
verify_structure() {
    local backup_path="$1"
    
    log "Verifying backup structure: $backup_path"
    
    # Check required directories
    local required_dirs=("databases" "volumes" "configs")
    for dir in "${required_dirs[@]}"; do
        if [[ -d "$backup_path/$dir" ]]; then
            log_success "Directory found: $dir"
        else
            log_error "Required directory missing: $dir"
            return 1
        fi
    done
    
    # Check for backup files
    local backup_files=$(find "$backup_path" -type f \( -name "*.sql" -o -name "*.tar.gz" -o -name "*.json" \) | wc -l)
    if [[ $backup_files -gt 0 ]]; then
        log_success "Found $backup_files backup files"
    else
        log_error "No backup files found"
        return 1
    fi
    
    return 0
}

# Function to verify file integrity
verify_integrity() {
    local backup_path="$1"
    
    log "Verifying file integrity: $backup_path"
    
    # Check tar.gz files
    find "$backup_path" -name "*.tar.gz" | while read -r file; do
        if tar -tzf "$file" >/dev/null 2>&1; then
            log_success "Archive integrity verified: $(basename "$file")"
        else
            log_error "Archive integrity failed: $(basename "$file")"
            return 1
        fi
    done
    
    # Check SQL files
    find "$backup_path" -name "*.sql" | while read -r file; do
        if [[ -s "$file" ]]; then
            log_success "SQL file verified: $(basename "$file")"
        else
            log_error "Empty SQL file: $(basename "$file")"
            return 1
        fi
    done
    
    # Check JSON files
    find "$backup_path" -name "*.json" | while read -r file; do
        if jq empty "$file" 2>/dev/null; then
            log_success "JSON file verified: $(basename "$file")"
        else
            log_error "Invalid JSON file: $(basename "$file")"
            return 1
        fi
    done
    
    return 0
}

# Function to verify backup size
verify_size() {
    local backup_path="$1"
    
    log "Verifying backup size: $backup_path"
    
    local total_size=$(du -sh "$backup_path" | cut -f1)
    log_success "Total backup size: $total_size"
    
    if [[ "$CHECK_SIZE" == "true" ]]; then
        # Check individual component sizes
        for dir in "databases" "volumes" "configs"; do
            if [[ -d "$backup_path/$dir" ]]; then
                local dir_size=$(du -sh "$backup_path/$dir" | cut -f1)
                log_success "Directory size ($dir): $dir_size"
            fi
        done
        
        # Check for unusually small backups
        local size_bytes=$(du -s "$backup_path" | cut -f1)
        if [[ $size_bytes -lt 1000000 ]]; then  # Less than 1MB
            log_warning "Backup size is unusually small: $total_size"
        fi
    fi
    
    return 0
}

# Function to verify specific backup
verify_backup() {
    local backup_path="$1"
    
    log "Verifying backup: $backup_path"
    
    if [[ ! -d "$backup_path" ]]; then
        log_error "Backup directory not found: $backup_path"
        return 1
    fi
    
    local verification_passed=true
    
    # Verify manifest
    if ! verify_manifest "$backup_path"; then
        verification_passed=false
    fi
    
    # Verify structure
    if ! verify_structure "$backup_path"; then
        verification_passed=false
    fi
    
    # Verify integrity
    if [[ "$CHECK_INTEGRITY" == "true" ]]; then
        if ! verify_integrity "$backup_path"; then
            verification_passed=false
        fi
    fi
    
    # Verify size
    if ! verify_size "$backup_path"; then
        verification_passed=false
    fi
    
    if [[ "$verification_passed" == "true" ]]; then
        log_success "Backup verification passed: $backup_path"
        return 0
    else
        log_error "Backup verification failed: $backup_path"
        return 1
    fi
}

# Function to verify all backups
verify_all_backups() {
    log "Verifying all backups in: $BACKUP_DIR"
    
    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_error "Backup directory not found: $BACKUP_DIR"
        return 1
    fi
    
    local total_backups=0
    local passed_backups=0
    local failed_backups=0
    
    find "$BACKUP_DIR" -maxdepth 1 -type d -name "pa-ecosystem-backup-*" | sort | while read -r backup; do
        ((total_backups++))
        
        if verify_backup "$backup"; then
            ((passed_backups++))
        else
            ((failed_backups++))
        fi
    done
    
    log "Verification Summary:"
    log "  Total backups: $total_backups"
    log "  Passed: $passed_backups"
    log "  Failed: $failed_backups"
    
    if [[ $failed_backups -eq 0 ]]; then
        log_success "All backups verified successfully!"
        return 0
    else
        log_error "Some backups failed verification"
        return 1
    fi
}

# Function to verify latest backup
verify_latest_backup() {
    log "Verifying latest backup in: $BACKUP_DIR"
    
    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_error "Backup directory not found: $BACKUP_DIR"
        return 1
    fi
    
    local latest_backup=$(find "$BACKUP_DIR" -maxdepth 1 -type d -name "pa-ecosystem-backup-*" | sort -r | head -1)
    
    if [[ -z "$latest_backup" ]]; then
        log_error "No backups found in: $BACKUP_DIR"
        return 1
    fi
    
    log "Latest backup: $latest_backup"
    
    if verify_backup "$latest_backup"; then
        log_success "Latest backup verification passed"
        return 0
    else
        log_error "Latest backup verification failed"
        return 1
    fi
}

# Main function
main() {
    log "Starting backup verification..."
    
    # Resolve backup path
    if [[ -n "$BACKUP_PATH" ]]; then
        if [[ "$BACKUP_PATH" == "latest" ]]; then
            BACKUP_PATH="$BACKUP_DIR/latest"
        fi
        
        if [[ ! -d "$BACKUP_PATH" ]]; then
            log_error "Backup not found: $BACKUP_PATH"
            exit 1
        fi
        
        verify_backup "$BACKUP_PATH"
    elif [[ "$VERIFY_ALL" == "true" ]]; then
        verify_all_backups
    elif [[ "$VERIFY_LATEST" == "true" ]]; then
        verify_latest_backup
    else
        log_error "No backup specified. Use --latest, --all, or specify a backup path."
        show_help
        exit 1
    fi
}

# Error handling
trap 'log_error "Verification failed at line $LINENO"' ERR

# Run main function
main "$@"
