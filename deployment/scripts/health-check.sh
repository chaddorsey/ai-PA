#!/bin/bash

# PA Ecosystem Health Check Script
# This script checks the health of all deployed services

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

# Health check results
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0

# Check if service is running
check_service_running() {
    local service_name="$1"
    local container_name="$2"
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if docker ps --filter "name=$container_name" --filter "status=running" | grep -q "$container_name"; then
        log_success "Service $service_name is running"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        log_error "Service $service_name is not running"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        return 1
    fi
}

# Check service health endpoint
check_service_health() {
    local service_name="$1"
    local health_url="$2"
    local timeout="${3:-10}"
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if curl -s --max-time "$timeout" "$health_url" >/dev/null 2>&1; then
        log_success "Service $service_name health check passed"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        log_error "Service $service_name health check failed"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        return 1
    fi
}

# Check Docker Compose services
check_docker_compose_services() {
    log_info "Checking Docker Compose services..."
    
    cd "$PROJECT_ROOT"
    
    if [[ ! -f "docker-compose.yml" ]]; then
        log_error "docker-compose.yml not found"
        return 1
    fi
    
    # Get list of services
    local services=$(docker-compose ps --services)
    
    for service in $services; do
        local status=$(docker-compose ps "$service" --format "table" | tail -n +2 | awk '{print $3}')
        
        TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
        
        if [[ "$status" == "Up" ]]; then
            log_success "Docker Compose service $service is running"
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
        else
            log_error "Docker Compose service $service is not running (status: $status)"
            FAILED_CHECKS=$((FAILED_CHECKS + 1))
        fi
    done
}

# Check database connectivity
check_database() {
    log_info "Checking database connectivity..."
    
    local db_container="supabase-db"
    
    if ! check_service_running "PostgreSQL Database" "$db_container"; then
        return 1
    fi
    
    # Check if database is accepting connections
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if docker exec "$db_container" pg_isready -U postgres >/dev/null 2>&1; then
        log_success "Database is accepting connections"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    else
        log_error "Database is not accepting connections"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
}

# Check n8n service
check_n8n() {
    log_info "Checking n8n service..."
    
    if ! check_service_running "n8n" "n8n"; then
        return 1
    fi
    
    # Check n8n health endpoint
    check_service_health "n8n" "http://localhost:5678/healthz" 30
}

# Check Letta service
check_letta() {
    log_info "Checking Letta service..."
    
    if ! check_service_running "Letta" "letta"; then
        return 1
    fi
    
    # Check Letta health endpoint
    check_service_health "Letta" "http://localhost:8283/v1/health/" 30
}

# Check Open WebUI service
check_openwebui() {
    log_info "Checking Open WebUI service..."
    
    if ! check_service_running "Open WebUI" "open-webui"; then
        return 1
    fi
    
    # Check Open WebUI health endpoint
    check_service_health "Open WebUI" "http://localhost:8080/health" 30
}

# Check Slackbot service
check_slackbot() {
    log_info "Checking Slackbot service..."
    
    if ! check_service_running "Slackbot" "slackbot"; then
        return 1
    fi
    
    # Check Slackbot health endpoint
    check_service_health "Slackbot" "http://localhost:8081/health" 30
}

# Check MCP servers
check_mcp_servers() {
    log_info "Checking MCP servers..."
    
    local mcp_servers=("gmail-mcp-server" "graphiti-mcp-server" "rag-mcp-server" "slack-mcp-server")
    
    for server in "${mcp_servers[@]}"; do
        if ! check_service_running "MCP Server $server" "$server"; then
            WARNING_CHECKS=$((WARNING_CHECKS + 1))
        fi
    done
}

# Check Cloudflare tunnel
check_cloudflare_tunnel() {
    log_info "Checking Cloudflare tunnel..."
    
    if ! check_service_running "Cloudflare Tunnel" "cloudflare-tunnel"; then
        log_warning "Cloudflare tunnel is not running (external access may not be available)"
        WARNING_CHECKS=$((WARNING_CHECKS + 1))
    else
        log_success "Cloudflare tunnel is running"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    fi
}

# Check network connectivity
check_network() {
    log_info "Checking network connectivity..."
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if docker network ls | grep -q "pa-internal"; then
        log_success "PA internal network exists"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    else
        log_error "PA internal network not found"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
}

# Check disk space
check_disk_space() {
    log_info "Checking disk space..."
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    local available_space
    if df -BG . >/dev/null 2>&1; then
        available_space=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
    else
        available_space=$(df -k . | awk 'NR==2 {print $4}')
        available_space=$((available_space / 1024 / 1024))
    fi
    
    if [[ $available_space -ge 10 ]]; then
        log_success "Sufficient disk space available: ${available_space}GB"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    elif [[ $available_space -ge 5 ]]; then
        log_warning "Low disk space: ${available_space}GB (recommended: 10GB+)"
        WARNING_CHECKS=$((WARNING_CHECKS + 1))
    else
        log_error "Insufficient disk space: ${available_space}GB (minimum: 5GB)"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
}

# Check memory usage
check_memory() {
    log_info "Checking memory usage..."
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if command -v free >/dev/null 2>&1; then
        local used_mem=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
        if [[ $used_mem -lt 90 ]]; then
            log_success "Memory usage is acceptable: ${used_mem}%"
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
        else
            log_warning "High memory usage: ${used_mem}% (recommended: <90%)"
            WARNING_CHECKS=$((WARNING_CHECKS + 1))
        fi
    else
        log_warning "Cannot check memory usage (free command not available)"
        WARNING_CHECKS=$((WARNING_CHECKS + 1))
    fi
}

# Check Docker daemon
check_docker_daemon() {
    log_info "Checking Docker daemon..."
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if docker info >/dev/null 2>&1; then
        log_success "Docker daemon is running"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    else
        log_error "Docker daemon is not running"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
}

# Display health check summary
show_health_summary() {
    echo ""
    echo -e "${BLUE}=========================================="
    echo "  Health Check Summary"
    echo "==========================================${NC}"
    echo ""
    echo "Total checks: $TOTAL_CHECKS"
    echo -e "Passed: ${GREEN}$PASSED_CHECKS${NC}"
    echo -e "Failed: ${RED}$FAILED_CHECKS${NC}"
    echo -e "Warnings: ${YELLOW}$WARNING_CHECKS${NC}"
    echo ""
    
    if [[ $FAILED_CHECKS -eq 0 ]]; then
        if [[ $WARNING_CHECKS -eq 0 ]]; then
            log_success "All health checks passed!"
            echo ""
            echo "Your PA ecosystem is running optimally."
        else
            log_warning "Health checks passed with warnings"
            echo ""
            echo "Your PA ecosystem is running but may need attention."
        fi
    else
        log_error "Some health checks failed"
        echo ""
        echo "Your PA ecosystem has issues that need to be addressed."
        echo "Check the error messages above for details."
    fi
}

# Main health check function
main() {
    echo -e "${BLUE}=========================================="
    echo "  PA Ecosystem Health Check"
    echo "==========================================${NC}"
    echo ""
    
    # Check Docker daemon
    check_docker_daemon
    
    # Check Docker Compose services
    check_docker_compose_services
    
    # Check individual services
    check_database
    check_n8n
    check_letta
    check_openwebui
    check_slackbot
    check_mcp_servers
    check_cloudflare_tunnel
    
    # Check system resources
    check_network
    check_disk_space
    check_memory
    
    # Show summary
    show_health_summary
    
    # Exit with appropriate code
    if [[ $FAILED_CHECKS -eq 0 ]]; then
        exit 0
    else
        exit 1
    fi
}

# Run main function
main "$@"
