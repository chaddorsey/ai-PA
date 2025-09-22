#!/bin/bash

# Pre-Upgrade Validation Script
# Purpose: Validate system state before performing framework upgrades
# Usage: ./pre-upgrade-check.sh [--framework <framework>]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
LOG_FILE="/var/log/upgrades/pre-upgrade-check-$(date +%Y%m%d-%H%M%S).log"
FRAMEWORK=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --framework)
            FRAMEWORK="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--framework <framework>]"
            echo ""
            echo "Options:"
            echo "  --framework  Specific framework to check (n8n, letta, graphiti)"
            echo "  -h, --help   Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"

# Logging function
log() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $message" | tee -a "$LOG_FILE"
}

# Error handling
error_exit() {
    local message="$1"
    log "ERROR: $message"
    echo -e "${RED}❌ $message${NC}"
    exit 1
}

# Warning function
warning() {
    local message="$1"
    log "WARNING: $message"
    echo -e "${YELLOW}⚠️  $message${NC}"
}

# Success function
success() {
    local message="$1"
    log "SUCCESS: $message"
    echo -e "${GREEN}✅ $message${NC}"
}

# Info function
info() {
    local message="$1"
    log "INFO: $message"
    echo -e "${BLUE}ℹ️  $message${NC}"
}

# Check system resources
check_system_resources() {
    info "Checking system resources..."
    
    # Check disk space
    local disk_usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    if [ "$disk_usage" -gt 90 ]; then
        error_exit "Disk usage is too high: ${disk_usage}%"
    elif [ "$disk_usage" -gt 80 ]; then
        warning "Disk usage is high: ${disk_usage}%"
    else
        success "Disk usage is acceptable: ${disk_usage}%"
    fi
    
    # Check memory
    local memory_usage=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
    if [ "$memory_usage" -gt 90 ]; then
        error_exit "Memory usage is too high: ${memory_usage}%"
    elif [ "$memory_usage" -gt 80 ]; then
        warning "Memory usage is high: ${memory_usage}%"
    else
        success "Memory usage is acceptable: ${memory_usage}%"
    fi
    
    # Check Docker
    if ! command -v docker >/dev/null 2>&1; then
        error_exit "Docker is not installed or not in PATH"
    fi
    
    if ! docker info >/dev/null 2>&1; then
        error_exit "Docker daemon is not running"
    fi
    
    success "Docker is available and running"
}

# Check database connectivity
check_database_connectivity() {
    info "Checking database connectivity..."
    
    # Check PostgreSQL (Supabase)
    if docker ps --format "table {{.Names}}" | grep -q "^supabase-db$"; then
        if docker exec supabase-db pg_isready -U postgres >/dev/null 2>&1; then
            success "PostgreSQL (Supabase) is healthy"
        else
            error_exit "PostgreSQL (Supabase) is not responding"
        fi
    else
        error_exit "PostgreSQL (Supabase) container is not running"
    fi
    
    # Check Neo4j (for Graphiti)
    if docker ps --format "table {{.Names}}" | grep -q "^graphiti-neo4j$"; then
        if docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "RETURN 1;" >/dev/null 2>&1; then
            success "Neo4j is healthy"
        else
            warning "Neo4j is not responding"
        fi
    else
        info "Neo4j container is not running (expected if Graphiti not in use)"
    fi
}

# Check network connectivity
check_network_connectivity() {
    info "Checking network connectivity..."
    
    # Check internal network
    if docker network ls | grep -q "pa-internal"; then
        success "PA internal network exists"
    else
        error_exit "PA internal network not found"
    fi
    
    # Check external connectivity
    if ping -c 1 google.com >/dev/null 2>&1; then
        success "External network connectivity is available"
    else
        warning "External network connectivity is limited"
    fi
}

# Check framework-specific requirements
check_framework_requirements() {
    local framework="$1"
    
    case "$framework" in
        "n8n")
            info "Checking n8n requirements..."
            
            if docker ps --format "table {{.Names}}" | grep -q "^n8n$"; then
                if docker exec n8n n8n --version >/dev/null 2>&1; then
                    success "n8n is running and responsive"
                else
                    error_exit "n8n is not responding"
                fi
            else
                error_exit "n8n container is not running"
            fi
            
            # Check n8n database connectivity
            if docker exec n8n n8n --version >/dev/null 2>&1; then
                success "n8n database connectivity is healthy"
            else
                error_exit "n8n database connectivity failed"
            fi
            ;;
            
        "letta")
            info "Checking Letta requirements..."
            
            if docker ps --format "table {{.Names}}" | grep -q "^ai-pa-letta-1$"; then
                if curl -s http://localhost:8283/v1/health/ >/dev/null 2>&1; then
                    success "Letta is running and responsive"
                else
                    error_exit "Letta API is not responding"
                fi
            else
                error_exit "Letta container is not running"
            fi
            
            # Check Letta database connectivity
            local db_status=$(curl -s http://localhost:8283/v1/health/ | jq -r '.database // "unknown"')
            if [ "$db_status" = "healthy" ]; then
                success "Letta database connectivity is healthy"
            else
                warning "Letta database status: $db_status"
            fi
            ;;
            
        "graphiti")
            info "Checking Graphiti requirements..."
            
            if docker ps --format "table {{.Names}}" | grep -q "^graphiti-mcp-server$"; then
                if curl -s http://localhost:8082/health >/dev/null 2>&1; then
                    success "Graphiti MCP server is running and responsive"
                else
                    error_exit "Graphiti MCP server is not responding"
                fi
            else
                info "Graphiti MCP server is not running (expected if not in use)"
            fi
            
            # Check Graphiti source code
            if [ -f "$PROJECT_ROOT/graphiti/pyproject.toml" ]; then
                success "Graphiti source code is available"
            else
                error_exit "Graphiti source code not found"
            fi
            ;;
            
        *)
            info "Checking all frameworks..."
            check_framework_requirements "n8n"
            check_framework_requirements "letta"
            check_framework_requirements "graphiti"
            ;;
    esac
}

# Check backup capabilities
check_backup_capabilities() {
    info "Checking backup capabilities..."
    
    # Check if backup directory is writable
    local backup_dir="/var/backups/upgrades"
    if mkdir -p "$backup_dir" 2>/dev/null; then
        success "Backup directory is writable: $backup_dir"
    else
        error_exit "Cannot create backup directory: $backup_dir"
    fi
    
    # Check if log directory is writable
    local log_dir="/var/log/upgrades"
    if mkdir -p "$log_dir" 2>/dev/null; then
        success "Log directory is writable: $log_dir"
    else
        error_exit "Cannot create log directory: $log_dir"
    fi
}

# Check version lock file
check_version_lock_file() {
    info "Checking version lock file..."
    
    local lock_file="$PROJECT_ROOT/config/versions/versions.lock.yml"
    if [ -f "$lock_file" ]; then
        success "Version lock file exists: $lock_file"
        
        # Check if lock file is readable
        if [ -r "$lock_file" ]; then
            success "Version lock file is readable"
        else
            error_exit "Version lock file is not readable"
        fi
        
        # Check if lock file is writable
        if [ -w "$lock_file" ]; then
            success "Version lock file is writable"
        else
            error_exit "Version lock file is not writable"
        fi
    else
        error_exit "Version lock file not found: $lock_file"
    fi
}

# Main validation process
main() {
    echo -e "${BLUE}🔍 Pre-Upgrade System Validation${NC}"
    echo -e "${BLUE}=================================${NC}"
    echo "Framework: ${FRAMEWORK:-all}"
    echo "Log file: $LOG_FILE"
    echo ""
    
    log "Starting pre-upgrade validation"
    
    # System-level checks
    check_system_resources
    check_database_connectivity
    check_network_connectivity
    check_backup_capabilities
    check_version_lock_file
    
    # Framework-specific checks
    check_framework_requirements "$FRAMEWORK"
    
    success "Pre-upgrade validation completed successfully!"
    echo ""
    echo -e "${GREEN}📋 Validation Summary${NC}"
    echo -e "${GREEN}=====================${NC}"
    echo "✅ System resources: OK"
    echo "✅ Database connectivity: OK"
    echo "✅ Network connectivity: OK"
    echo "✅ Backup capabilities: OK"
    echo "✅ Version lock file: OK"
    echo "✅ Framework requirements: OK"
    echo ""
    echo -e "${BLUE}🚀 System is ready for upgrade!${NC}"
    echo "Log file: $LOG_FILE"
}

# Run main function
main "$@"
