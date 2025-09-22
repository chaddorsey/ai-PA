#!/bin/bash
set -e

# Health Check Script
# This script performs comprehensive health checks on the PA ecosystem

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$PROJECT_ROOT/logs/health"

# Create necessary directories
mkdir -p "$LOGS_DIR"

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOGS_DIR/health-check-$(date +%Y%m%d).log"
}

# Success logging
log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] SUCCESS:${NC} $1" | tee -a "$LOGS_DIR/health-check-$(date +%Y%m%d).log"
}

# Error logging
log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOGS_DIR/health-check-$(date +%Y%m%d).log"
}

# Warning logging
log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOGS_DIR/health-check-$(date +%Y%m%d).log"
}

# Health check result tracking
HEALTH_CHECK_RESULTS=()
TOTAL_CHECKS=0
FAILED_CHECKS=0

# Add health check result
add_result() {
    local service="$1"
    local status="$2"
    local message="$3"
    
    HEALTH_CHECK_RESULTS+=("$service:$status:$message")
    ((TOTAL_CHECKS++))
    
    if [[ "$status" == "FAIL" ]]; then
        ((FAILED_CHECKS++))
    fi
}

# Check Docker service
check_docker() {
    log "Checking Docker service..."
    
    if docker info > /dev/null 2>&1; then
        log_success "Docker service is running"
        add_result "docker" "PASS" "Docker service is running"
    else
        log_error "Docker service is not running"
        add_result "docker" "FAIL" "Docker service is not running"
        return 1
    fi
}

# Check Docker Compose file
check_docker_compose() {
    local compose_file="$1"
    local environment="$2"
    
    log "Checking Docker Compose file: $compose_file"
    
    if [[ ! -f "$compose_file" ]]; then
        log_error "Docker Compose file not found: $compose_file"
        add_result "docker-compose" "FAIL" "Docker Compose file not found: $compose_file"
        return 1
    fi
    
    # Validate compose file syntax
    if docker-compose -f "$compose_file" config > /dev/null 2>&1; then
        log_success "Docker Compose file is valid"
        add_result "docker-compose" "PASS" "Docker Compose file is valid"
    else
        log_error "Docker Compose file has syntax errors"
        add_result "docker-compose" "FAIL" "Docker Compose file has syntax errors"
        return 1
    fi
}

# Check service health
check_service_health() {
    local service_name="$1"
    local compose_file="$2"
    local health_endpoint="$3"
    local expected_status="$4"
    
    log "Checking service health: $service_name"
    
    # Check if service is running
    local service_status=$(docker-compose -f "$compose_file" ps --format json | jq -r ".[] | select(.Name == \"$service_name\") | .State")
    
    if [[ "$service_status" != "running" ]]; then
        log_error "Service $service_name is not running (status: $service_status)"
        add_result "$service_name" "FAIL" "Service is not running (status: $service_status)"
        return 1
    fi
    
    # Check health endpoint if provided
    if [[ -n "$health_endpoint" ]]; then
        local container_name=$(docker-compose -f "$compose_file" ps -q "$service_name")
        
        if [[ -n "$container_name" ]]; then
            if docker exec "$container_name" curl -f "$health_endpoint" > /dev/null 2>&1; then
                log_success "Service $service_name health check passed"
                add_result "$service_name" "PASS" "Health check passed"
            else
                log_error "Service $service_name health check failed"
                add_result "$service_name" "FAIL" "Health check failed"
                return 1
            fi
        else
            log_warning "Container for service $service_name not found"
            add_result "$service_name" "WARN" "Container not found"
        fi
    else
        log_success "Service $service_name is running"
        add_result "$service_name" "PASS" "Service is running"
    fi
}

# Check database connectivity
check_database() {
    local compose_file="$1"
    local db_service="$2"
    
    log "Checking database connectivity..."
    
    local container_name=$(docker-compose -f "$compose_file" ps -q "$db_service")
    
    if [[ -z "$container_name" ]]; then
        log_error "Database container not found: $db_service"
        add_result "database" "FAIL" "Database container not found"
        return 1
    fi
    
    # Check if database is accepting connections
    if docker exec "$container_name" pg_isready -U postgres > /dev/null 2>&1; then
        log_success "Database is accepting connections"
        add_result "database" "PASS" "Database is accepting connections"
    else
        log_error "Database is not accepting connections"
        add_result "database" "FAIL" "Database is not accepting connections"
        return 1
    fi
    
    # Check database size
    local db_size=$(docker exec "$container_name" psql -U postgres -d postgres -t -c "SELECT pg_database_size('postgres');" | tr -d ' ')
    log "Database size: $db_size bytes"
    add_result "database" "PASS" "Database size: $db_size bytes"
}

# Check network connectivity
check_network() {
    local compose_file="$1"
    local network_name="$2"
    
    log "Checking network connectivity..."
    
    # Check if network exists
    if docker network ls | grep -q "$network_name"; then
        log_success "Network $network_name exists"
        add_result "network" "PASS" "Network $network_name exists"
    else
        log_error "Network $network_name does not exist"
        add_result "network" "FAIL" "Network $network_name does not exist"
        return 1
    fi
    
    # Check network connectivity between services
    local services=("supabase-db" "n8n" "letta" "open-webui")
    
    for service in "${services[@]}"; do
        local container_name=$(docker-compose -f "$compose_file" ps -q "$service")
        
        if [[ -n "$container_name" ]]; then
            # Check if container can reach other services
            if docker exec "$container_name" ping -c 1 supabase-db > /dev/null 2>&1; then
                log_success "Service $service can reach database"
                add_result "network-$service" "PASS" "Can reach database"
            else
                log_warning "Service $service cannot reach database"
                add_result "network-$service" "WARN" "Cannot reach database"
            fi
        fi
    done
}

# Check resource usage
check_resources() {
    local compose_file="$1"
    
    log "Checking resource usage..."
    
    # Check memory usage
    local memory_usage=$(docker stats --no-stream --format "table {{.MemUsage}}" | tail -n +2 | awk '{sum += $1} END {print sum}')
    log "Total memory usage: $memory_usage"
    
    # Check disk usage
    local disk_usage=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    log "Disk usage: $disk_usage%"
    
    if [[ $disk_usage -gt 80 ]]; then
        log_warning "Disk usage is high: $disk_usage%"
        add_result "resources" "WARN" "Disk usage is high: $disk_usage%"
    else
        log_success "Disk usage is acceptable: $disk_usage%"
        add_result "resources" "PASS" "Disk usage is acceptable: $disk_usage%"
    fi
}

# Check external connectivity
check_external_connectivity() {
    log "Checking external connectivity..."
    
    # Check internet connectivity
    if ping -c 1 8.8.8.8 > /dev/null 2>&1; then
        log_success "Internet connectivity is working"
        add_result "external" "PASS" "Internet connectivity is working"
    else
        log_warning "Internet connectivity issues"
        add_result "external" "WARN" "Internet connectivity issues"
    fi
    
    # Check DNS resolution
    if nslookup google.com > /dev/null 2>&1; then
        log_success "DNS resolution is working"
        add_result "external" "PASS" "DNS resolution is working"
    else
        log_warning "DNS resolution issues"
        add_result "external" "WARN" "DNS resolution issues"
    fi
}

# Check logs for errors
check_logs() {
    local compose_file="$1"
    
    log "Checking logs for errors..."
    
    # Get all running services
    local services=$(docker-compose -f "$compose_file" ps --format json | jq -r '.[] | select(.State == "running") | .Name')
    
    for service in $services; do
        local container_name=$(docker-compose -f "$compose_file" ps -q "$service")
        
        if [[ -n "$container_name" ]]; then
            # Check for error logs in the last 10 minutes
            local error_count=$(docker logs --since 10m "$container_name" 2>&1 | grep -i error | wc -l)
            
            if [[ $error_count -gt 0 ]]; then
                log_warning "Service $service has $error_count errors in the last 10 minutes"
                add_result "logs-$service" "WARN" "$error_count errors in last 10 minutes"
            else
                log_success "Service $service has no recent errors"
                add_result "logs-$service" "PASS" "No recent errors"
            fi
        fi
    done
}

# Generate health report
generate_report() {
    log "Generating health check report..."
    
    local report_file="$LOGS_DIR/health-report-$(date +%Y%m%d-%H%M%S).txt"
    
    {
        echo "PA Ecosystem Health Check Report"
        echo "Generated: $(date)"
        echo "Environment: $ENVIRONMENT"
        echo "Total Checks: $TOTAL_CHECKS"
        echo "Failed Checks: $FAILED_CHECKS"
        echo "Success Rate: $(( (TOTAL_CHECKS - FAILED_CHECKS) * 100 / TOTAL_CHECKS ))%"
        echo ""
        echo "Detailed Results:"
        echo "=================="
        
        for result in "${HEALTH_CHECK_RESULTS[@]}"; do
            IFS=':' read -r service status message <<< "$result"
            echo "$service: $status - $message"
        done
    } > "$report_file"
    
    log_success "Health check report generated: $report_file"
    
    # Display summary
    echo ""
    echo "Health Check Summary:"
    echo "===================="
    echo "Total Checks: $TOTAL_CHECKS"
    echo "Failed Checks: $FAILED_CHECKS"
    echo "Success Rate: $(( (TOTAL_CHECKS - FAILED_CHECKS) * 100 / TOTAL_CHECKS ))%"
    echo ""
    
    if [[ $FAILED_CHECKS -eq 0 ]]; then
        log_success "All health checks passed!"
        return 0
    else
        log_error "$FAILED_CHECKS health checks failed"
        return 1
    fi
}

# Main execution
main() {
    local environment="production"
    local compose_file="docker-compose.yml"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --environment)
                environment="$2"
                shift 2
                ;;
            --staging)
                environment="staging"
                compose_file="docker-compose.staging.yml"
                shift
                ;;
            --production)
                environment="production"
                compose_file="docker-compose.yml"
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    ENVIRONMENT="$environment"
    
    log "Starting health check for $environment environment..."
    log "Using compose file: $compose_file"
    
    # Change to project root
    cd "$PROJECT_ROOT"
    
    # Perform health checks
    check_docker
    check_docker_compose "$compose_file" "$environment"
    
    # Check core services
    check_service_health "supabase-db" "$compose_file" "http://localhost:5432" "running"
    check_service_health "n8n" "$compose_file" "http://localhost:5678/healthz" "running"
    check_service_health "letta" "$compose_file" "http://localhost:8283/v1/health/" "running"
    check_service_health "open-webui" "$compose_file" "http://localhost:8080/health" "running"
    
    # Check additional services if they exist
    if docker-compose -f "$compose_file" ps -q slackbot > /dev/null 2>&1; then
        check_service_health "slackbot" "$compose_file" "http://localhost:8081/health" "running"
    fi
    
    if docker-compose -f "$compose_file" ps -q health-monitor > /dev/null 2>&1; then
        check_service_health "health-monitor" "$compose_file" "http://localhost:8083/health" "running"
    fi
    
    # Check database connectivity
    check_database "$compose_file" "supabase-db"
    
    # Check network connectivity
    if [[ "$environment" == "production" ]]; then
        check_network "$compose_file" "pa-internal"
    else
        check_network "$compose_file" "pa-staging"
    fi
    
    # Check resources
    check_resources "$compose_file"
    
    # Check external connectivity
    check_external_connectivity
    
    # Check logs
    check_logs "$compose_file"
    
    # Generate report
    generate_report
}

# Help function
show_help() {
    echo "Health Check Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --environment <env>  Specify environment (production|staging)"
    echo "  --staging           Check staging environment"
    echo "  --production        Check production environment (default)"
    echo "  -h, --help          Show this help message"
    echo ""
    echo "This script performs comprehensive health checks on the PA ecosystem."
}

# Run main function
main "$@"
