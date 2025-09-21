#!/bin/bash

# PA Ecosystem Diagnostic Script
# Comprehensive system diagnostics and troubleshooting

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/deployment/logs}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging
LOG_FILE="$LOG_DIR/diagnose-$TIMESTAMP.log"
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
PA Ecosystem Diagnostic Script

USAGE:
    $0 [OPTIONS] [COMPONENT]

ARGUMENTS:
    COMPONENT              Specific component to diagnose (optional)

OPTIONS:
    -h, --help              Show this help message
    -a, --all               Run all diagnostic checks
    -s, --system            Run system-level diagnostics
    -d, --docker            Run Docker diagnostics
    -n, --network           Run network diagnostics
    -c, --config            Run configuration diagnostics
    -l, --logs              Run log analysis
    -p, --performance       Run performance diagnostics
    -v, --verbose           Enable verbose output
    -q, --quiet             Suppress output except errors
    -o, --output FILE       Save output to file

COMPONENTS:
    letta                   Letta AI agent
    openwebui              Open WebUI
    n8n                    n8n workflow engine
    slackbot               Slack bot
    gmail-mcp              Gmail MCP server
    hayhooks               Hayhooks service
    health-monitor         Health monitor
    supabase-db            PostgreSQL database
    neo4j                  Neo4j database

EXAMPLES:
    $0 --all                # Run all diagnostics
    $0 --system             # System-level diagnostics only
    $0 letta                # Diagnose Letta AI agent
    $0 --network --verbose  # Network diagnostics with verbose output

EOF
}

# Parse command line arguments
RUN_ALL=false
RUN_SYSTEM=false
RUN_DOCKER=false
RUN_NETWORK=false
RUN_CONFIG=false
RUN_LOGS=false
RUN_PERFORMANCE=false
VERBOSE=false
QUIET=false
OUTPUT_FILE=""
COMPONENT=""

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
        -s|--system)
            RUN_SYSTEM=true
            shift
            ;;
        -d|--docker)
            RUN_DOCKER=true
            shift
            ;;
        -n|--network)
            RUN_NETWORK=true
            shift
            ;;
        -c|--config)
            RUN_CONFIG=true
            shift
            ;;
        -l|--logs)
            RUN_LOGS=true
            shift
            ;;
        -p|--performance)
            RUN_PERFORMANCE=true
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
            if [[ -z "$COMPONENT" ]]; then
                COMPONENT="$1"
            else
                log_error "Multiple components specified: $COMPONENT and $1"
                exit 1
            fi
            shift
            ;;
    esac
done

# Set default behavior
if [[ "$RUN_ALL" == "false" && "$RUN_SYSTEM" == "false" && "$RUN_DOCKER" == "false" && "$RUN_NETWORK" == "false" && "$RUN_CONFIG" == "false" && "$RUN_LOGS" == "false" && "$RUN_PERFORMANCE" == "false" && -z "$COMPONENT" ]]; then
    RUN_ALL=true
fi

# Function to check system requirements
check_system_requirements() {
    log "Checking system requirements..."
    
    # Check OS
    if [[ -f /etc/os-release ]]; then
        local os_name=$(grep PRETTY_NAME /etc/os-release | cut -d'"' -f2)
        log_success "Operating System: $os_name"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        local os_version=$(sw_vers -productVersion)
        log_success "Operating System: macOS $os_version"
    else
        log_warning "Unknown operating system"
    fi
    
    # Check architecture
    local arch=$(uname -m)
    log_success "Architecture: $arch"
    
    # Check kernel version
    local kernel=$(uname -r)
    log_success "Kernel: $kernel"
    
    # Check available memory
    if [[ "$OSTYPE" == "darwin"* ]]; then
        local total_mem=$(sysctl -n hw.memsize)
        local total_mem_gb=$((total_mem / 1024 / 1024 / 1024))
    else
        local total_mem=$(grep MemTotal /proc/meminfo | awk '{print $2}')
        local total_mem_gb=$((total_mem / 1024 / 1024))
    fi
    
    if [[ $total_mem_gb -ge 8 ]]; then
        log_success "Memory: ${total_mem_gb}GB (sufficient)"
    else
        log_warning "Memory: ${total_mem_gb}GB (may be insufficient)"
    fi
    
    # Check available disk space
    local disk_space=$(df -h . | tail -1 | awk '{print $4}')
    log_success "Available disk space: $disk_space"
    
    # Check CPU cores
    if [[ "$OSTYPE" == "darwin"* ]]; then
        local cpu_cores=$(sysctl -n hw.ncpu)
    else
        local cpu_cores=$(nproc)
    fi
    
    if [[ $cpu_cores -ge 4 ]]; then
        log_success "CPU cores: $cpu_cores (sufficient)"
    else
        log_warning "CPU cores: $cpu_cores (may be insufficient)"
    fi
}

# Function to check Docker
check_docker() {
    log "Checking Docker installation..."
    
    # Check Docker version
    if command -v docker >/dev/null 2>&1; then
        local docker_version=$(docker --version)
        log_success "Docker: $docker_version"
    else
        log_error "Docker not installed"
        return 1
    fi
    
    # Check Docker daemon
    if docker info >/dev/null 2>&1; then
        log_success "Docker daemon is running"
    else
        log_error "Docker daemon is not running"
        return 1
    fi
    
    # Check Docker Compose
    if command -v docker-compose >/dev/null 2>&1; then
        local compose_version=$(docker-compose --version)
        log_success "Docker Compose: $compose_version"
    else
        log_error "Docker Compose not installed"
        return 1
    fi
    
    # Check Docker resources
    local docker_info=$(docker system df)
    log_info "Docker storage usage:"
    echo "$docker_info" | tee -a "$LOG_FILE"
}

# Function to check network
check_network() {
    log "Checking network connectivity..."
    
    # Check local network
    if ping -c 1 127.0.0.1 >/dev/null 2>&1; then
        log_success "Local network connectivity: OK"
    else
        log_error "Local network connectivity: FAILED"
    fi
    
    # Check external connectivity
    if ping -c 1 8.8.8.8 >/dev/null 2>&1; then
        log_success "External network connectivity: OK"
    else
        log_warning "External network connectivity: FAILED"
    fi
    
    # Check DNS resolution
    if nslookup google.com >/dev/null 2>&1; then
        log_success "DNS resolution: OK"
    else
        log_warning "DNS resolution: FAILED"
    fi
    
    # Check required ports
    local required_ports=(8283 8080 5678 8083 5432 7474 7687 8890 1416)
    for port in "${required_ports[@]}"; do
        if netstat -tlnp 2>/dev/null | grep -q ":$port "; then
            log_success "Port $port: In use"
        else
            log_warning "Port $port: Available"
        fi
    done
}

# Function to check configuration
check_configuration() {
    log "Checking configuration..."
    
    # Check .env file
    if [[ -f "$PROJECT_ROOT/.env" ]]; then
        log_success "Environment file found: .env"
        
        # Check required variables
        local required_vars=("OPENAI_API_KEY" "POSTGRES_PASSWORD" "N8N_ENCRYPTION_KEY" "SUPABASE_ANON_KEY" "SUPABASE_SERVICE_KEY")
        for var in "${required_vars[@]}"; do
            if grep -q "^$var=" "$PROJECT_ROOT/.env"; then
                local value=$(grep "^$var=" "$PROJECT_ROOT/.env" | cut -d'=' -f2)
                if [[ "$value" == "CHANGE_ME_"* ]]; then
                    log_warning "Variable $var: Not configured (placeholder value)"
                else
                    log_success "Variable $var: Configured"
                fi
            else
                log_error "Variable $var: Missing"
            fi
        done
    else
        log_error "Environment file not found: .env"
    fi
    
    # Check docker-compose.yml
    if [[ -f "$PROJECT_ROOT/docker-compose.yml" ]]; then
        log_success "Docker Compose file found: docker-compose.yml"
    else
        log_error "Docker Compose file not found: docker-compose.yml"
    fi
    
    # Validate configuration
    if [[ -f "$PROJECT_ROOT/deployment/scripts/validate-config.sh" ]]; then
        log "Running configuration validation..."
        if "$PROJECT_ROOT/deployment/scripts/validate-config.sh" >> "$LOG_FILE" 2>&1; then
            log_success "Configuration validation: PASSED"
        else
            log_error "Configuration validation: FAILED"
        fi
    fi
}

# Function to check logs
check_logs() {
    log "Checking system logs..."
    
    # Check Docker Compose logs
    if [[ -f "$PROJECT_ROOT/docker-compose.yml" ]]; then
        log "Docker Compose service status:"
        docker-compose ps | tee -a "$LOG_FILE"
        
        log "Recent Docker Compose logs:"
        docker-compose logs --tail=50 | tee -a "$LOG_FILE"
    fi
    
    # Check individual service logs
    local services=("letta" "openwebui" "n8n" "slackbot" "gmail-mcp-server" "hayhooks" "health-monitor" "supabase-db" "neo4j")
    for service in "${services[@]}"; do
        if docker-compose ps "$service" | grep -q "Up"; then
            log_success "Service $service: Running"
        else
            log_error "Service $service: Not running"
        fi
    done
}

# Function to check performance
check_performance() {
    log "Checking system performance..."
    
    # Check system load
    if [[ "$OSTYPE" == "darwin"* ]]; then
        local load_avg=$(sysctl -n vm.loadavg | awk '{print $2}')
    else
        local load_avg=$(cat /proc/loadavg | awk '{print $1}')
    fi
    
    log_info "System load average: $load_avg"
    
    # Check memory usage
    if [[ "$OSTYPE" == "darwin"* ]]; then
        local mem_info=$(vm_stat)
        log_info "Memory usage:"
        echo "$mem_info" | tee -a "$LOG_FILE"
    else
        local mem_info=$(free -h)
        log_info "Memory usage:"
        echo "$mem_info" | tee -a "$LOG_FILE"
    fi
    
    # Check disk usage
    local disk_info=$(df -h)
    log_info "Disk usage:"
    echo "$disk_info" | tee -a "$LOG_FILE"
    
    # Check Docker resource usage
    log_info "Docker container resource usage:"
    docker stats --no-stream | tee -a "$LOG_FILE"
}

# Function to check specific component
check_component() {
    local component="$1"
    
    log "Checking component: $component"
    
    case "$component" in
        letta)
            check_letta
            ;;
        openwebui)
            check_openwebui
            ;;
        n8n)
            check_n8n
            ;;
        slackbot)
            check_slackbot
            ;;
        gmail-mcp)
            check_gmail_mcp
            ;;
        hayhooks)
            check_hayhooks
            ;;
        health-monitor)
            check_health_monitor
            ;;
        supabase-db)
            check_supabase_db
            ;;
        neo4j)
            check_neo4j
            ;;
        *)
            log_error "Unknown component: $component"
            return 1
            ;;
    esac
}

# Function to check Letta
check_letta() {
    log "Checking Letta AI agent..."
    
    # Check if service is running
    if docker-compose ps letta | grep -q "Up"; then
        log_success "Letta service: Running"
        
        # Check health endpoint
        if curl -f http://localhost:8283/v1/health/ >/dev/null 2>&1; then
            log_success "Letta health endpoint: OK"
        else
            log_error "Letta health endpoint: FAILED"
        fi
        
        # Check logs
        log "Recent Letta logs:"
        docker-compose logs --tail=20 letta | tee -a "$LOG_FILE"
    else
        log_error "Letta service: Not running"
    fi
}

# Function to check Open WebUI
check_openwebui() {
    log "Checking Open WebUI..."
    
    # Check if service is running
    if docker-compose ps openwebui | grep -q "Up"; then
        log_success "Open WebUI service: Running"
        
        # Check health endpoint
        if curl -f http://localhost:8080/health >/dev/null 2>&1; then
            log_success "Open WebUI health endpoint: OK"
        else
            log_error "Open WebUI health endpoint: FAILED"
        fi
        
        # Check logs
        log "Recent Open WebUI logs:"
        docker-compose logs --tail=20 openwebui | tee -a "$LOG_FILE"
    else
        log_error "Open WebUI service: Not running"
    fi
}

# Function to check n8n
check_n8n() {
    log "Checking n8n workflow engine..."
    
    # Check if service is running
    if docker-compose ps n8n | grep -q "Up"; then
        log_success "n8n service: Running"
        
        # Check health endpoint
        if curl -f http://localhost:5678/healthz >/dev/null 2>&1; then
            log_success "n8n health endpoint: OK"
        else
            log_error "n8n health endpoint: FAILED"
        fi
        
        # Check logs
        log "Recent n8n logs:"
        docker-compose logs --tail=20 n8n | tee -a "$LOG_FILE"
    else
        log_error "n8n service: Not running"
    fi
}

# Function to check Slackbot
check_slackbot() {
    log "Checking Slack bot..."
    
    # Check if service is running
    if docker-compose ps slackbot | grep -q "Up"; then
        log_success "Slackbot service: Running"
        
        # Check logs
        log "Recent Slackbot logs:"
        docker-compose logs --tail=20 slackbot | tee -a "$LOG_FILE"
    else
        log_error "Slackbot service: Not running"
    fi
}

# Function to check Gmail MCP
check_gmail_mcp() {
    log "Checking Gmail MCP server..."
    
    # Check if service is running
    if docker-compose ps gmail-mcp-server | grep -q "Up"; then
        log_success "Gmail MCP service: Running"
        
        # Check health endpoint
        if curl -f http://localhost:8890/health >/dev/null 2>&1; then
            log_success "Gmail MCP health endpoint: OK"
        else
            log_error "Gmail MCP health endpoint: FAILED"
        fi
        
        # Check logs
        log "Recent Gmail MCP logs:"
        docker-compose logs --tail=20 gmail-mcp-server | tee -a "$LOG_FILE"
    else
        log_error "Gmail MCP service: Not running"
    fi
}

# Function to check Hayhooks
check_hayhooks() {
    log "Checking Hayhooks service..."
    
    # Check if service is running
    if docker-compose ps hayhooks | grep -q "Up"; then
        log_success "Hayhooks service: Running"
        
        # Check health endpoint
        if curl -f http://localhost:1416/health >/dev/null 2>&1; then
            log_success "Hayhooks health endpoint: OK"
        else
            log_error "Hayhooks health endpoint: FAILED"
        fi
        
        # Check logs
        log "Recent Hayhooks logs:"
        docker-compose logs --tail=20 hayhooks | tee -a "$LOG_FILE"
    else
        log_error "Hayhooks service: Not running"
    fi
}

# Function to check Health Monitor
check_health_monitor() {
    log "Checking Health Monitor..."
    
    # Check if service is running
    if docker-compose ps health-monitor | grep -q "Up"; then
        log_success "Health Monitor service: Running"
        
        # Check health endpoint
        if curl -f http://localhost:8083/health >/dev/null 2>&1; then
            log_success "Health Monitor health endpoint: OK"
        else
            log_error "Health Monitor health endpoint: FAILED"
        fi
        
        # Check logs
        log "Recent Health Monitor logs:"
        docker-compose logs --tail=20 health-monitor | tee -a "$LOG_FILE"
    else
        log_error "Health Monitor service: Not running"
    fi
}

# Function to check Supabase DB
check_supabase_db() {
    log "Checking Supabase PostgreSQL database..."
    
    # Check if service is running
    if docker-compose ps supabase-db | grep -q "Up"; then
        log_success "Supabase DB service: Running"
        
        # Check database connectivity
        if docker-compose exec supabase-db pg_isready -U postgres >/dev/null 2>&1; then
            log_success "PostgreSQL database: Ready"
        else
            log_error "PostgreSQL database: Not ready"
        fi
        
        # Check logs
        log "Recent Supabase DB logs:"
        docker-compose logs --tail=20 supabase-db | tee -a "$LOG_FILE"
    else
        log_error "Supabase DB service: Not running"
    fi
}

# Function to check Neo4j
check_neo4j() {
    log "Checking Neo4j database..."
    
    # Check if service is running
    if docker-compose ps neo4j | grep -q "Up"; then
        log_success "Neo4j service: Running"
        
        # Check database connectivity
        if docker-compose exec neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
            log_success "Neo4j database: Ready"
        else
            log_error "Neo4j database: Not ready"
        fi
        
        # Check logs
        log "Recent Neo4j logs:"
        docker-compose logs --tail=20 neo4j | tee -a "$LOG_FILE"
    else
        log_error "Neo4j service: Not running"
    fi
}

# Function to generate diagnostic report
generate_report() {
    log "Generating diagnostic report..."
    
    local report_file="$LOG_DIR/diagnostic-report-$TIMESTAMP.txt"
    
    cat > "$report_file" << EOF
# PA Ecosystem Diagnostic Report
# Generated: $(date)
# Hostname: $(hostname)
# User: $(whoami)

## System Information
EOF
    
    # Add system information
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "OS: macOS $(sw_vers -productVersion)" >> "$report_file"
        echo "Architecture: $(uname -m)" >> "$report_file"
        echo "Kernel: $(uname -r)" >> "$report_file"
        echo "Memory: $(sysctl -n hw.memsize | awk '{print $1/1024/1024/1024 " GB"}')" >> "$report_file"
        echo "CPU Cores: $(sysctl -n hw.ncpu)" >> "$report_file"
    else
        echo "OS: $(grep PRETTY_NAME /etc/os-release | cut -d'"' -f2)" >> "$report_file"
        echo "Architecture: $(uname -m)" >> "$report_file"
        echo "Kernel: $(uname -r)" >> "$report_file"
        echo "Memory: $(grep MemTotal /proc/meminfo | awk '{print $2/1024/1024 " GB"}')" >> "$report_file"
        echo "CPU Cores: $(nproc)" >> "$report_file"
    fi
    
    # Add Docker information
    echo "" >> "$report_file"
    echo "## Docker Information" >> "$report_file"
    echo "Docker Version: $(docker --version)" >> "$report_file"
    echo "Docker Compose Version: $(docker-compose --version)" >> "$report_file"
    
    # Add service status
    echo "" >> "$report_file"
    echo "## Service Status" >> "$report_file"
    docker-compose ps >> "$report_file"
    
    # Add recent logs
    echo "" >> "$report_file"
    echo "## Recent Logs" >> "$report_file"
    docker-compose logs --tail=100 >> "$report_file"
    
    log_success "Diagnostic report generated: $report_file"
}

# Main function
main() {
    log "Starting PA Ecosystem diagnostics..."
    log "Diagnostic log: $LOG_FILE"
    
    # Run system diagnostics
    if [[ "$RUN_ALL" == "true" || "$RUN_SYSTEM" == "true" ]]; then
        check_system_requirements
    fi
    
    # Run Docker diagnostics
    if [[ "$RUN_ALL" == "true" || "$RUN_DOCKER" == "true" ]]; then
        check_docker
    fi
    
    # Run network diagnostics
    if [[ "$RUN_ALL" == "true" || "$RUN_NETWORK" == "true" ]]; then
        check_network
    fi
    
    # Run configuration diagnostics
    if [[ "$RUN_ALL" == "true" || "$RUN_CONFIG" == "true" ]]; then
        check_configuration
    fi
    
    # Run log analysis
    if [[ "$RUN_ALL" == "true" || "$RUN_LOGS" == "true" ]]; then
        check_logs
    fi
    
    # Run performance diagnostics
    if [[ "$RUN_ALL" == "true" || "$RUN_PERFORMANCE" == "true" ]]; then
        check_performance
    fi
    
    # Check specific component
    if [[ -n "$COMPONENT" ]]; then
        check_component "$COMPONENT"
    fi
    
    # Generate report
    generate_report
    
    log_success "Diagnostics completed successfully!"
    log_success "Diagnostic log: $LOG_FILE"
    
    # Save output to file if requested
    if [[ -n "$OUTPUT_FILE" ]]; then
        cp "$LOG_FILE" "$OUTPUT_FILE"
        log_success "Output saved to: $OUTPUT_FILE"
    fi
}

# Error handling
trap 'log_error "Diagnostics failed at line $LINENO"' ERR

# Run main function
main "$@"
