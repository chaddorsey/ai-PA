#!/bin/bash

# System Recovery Script
# This script can restore basic system functionality

set -e

# Colors for output
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

# Check system status
check_system_status() {
    log_info "Checking system status..."
    
    echo "=== System Resources ==="
    uptime
    df -h
    echo ""
    
    echo "=== Memory Usage ==="
    free -h 2>/dev/null || vm_stat
    echo ""
    
    echo "=== Network Interfaces ==="
    ifconfig | grep -E "inet.*broadcast"
    echo ""
}

# Check Docker status
check_docker_status() {
    log_info "Checking Docker status..."
    
    if docker info >/dev/null 2>&1; then
        log_success "Docker is running"
        echo "=== Docker Status ==="
        docker ps -a
        echo ""
    else
        log_warning "Docker is not running"
        return 1
    fi
}

# Start Docker if needed
start_docker() {
    if ! docker info >/dev/null 2>&1; then
        log_info "Starting Docker..."
        if open -a Docker; then
            log_info "Waiting for Docker to start..."
            sleep 30
            
            # Wait for Docker to be ready
            local attempts=0
            while ! docker info >/dev/null 2>&1 && [[ $attempts -lt 10 ]]; do
                log_info "Waiting for Docker to be ready... (attempt $((attempts + 1))/10)"
                sleep 10
                attempts=$((attempts + 1))
            done
            
            if docker info >/dev/null 2>&1; then
                log_success "Docker started successfully"
            else
                log_error "Docker failed to start"
                return 1
            fi
        else
            log_error "Failed to start Docker"
            return 1
        fi
    fi
}

# Check network connectivity
check_network() {
    log_info "Checking network connectivity..."
    
    if ping -c 3 8.8.8.8 >/dev/null 2>&1; then
        log_success "Network connectivity is working"
    else
        log_warning "Network connectivity issues detected"
    fi
}

# Check critical ports
check_ports() {
    log_info "Checking critical ports..."
    
    local ports=(22 80 443 21115 21116 21117 21118 21119 5678 8080 8283 9000 9090)
    local open_ports=()
    local closed_ports=()
    
    for port in "${ports[@]}"; do
        if lsof -i :$port >/dev/null 2>&1; then
            open_ports+=($port)
        else
            closed_ports+=($port)
        fi
    done
    
    if [[ ${#open_ports[@]} -gt 0 ]]; then
        log_success "Open ports: ${open_ports[*]}"
    fi
    
    if [[ ${#closed_ports[@]} -gt 0 ]]; then
        log_warning "Closed ports: ${closed_ports[*]}"
    fi
}

# Restart Docker services
restart_docker_services() {
    log_info "Restarting Docker services..."
    
    # Change to project directory
    cd /Users/dorseyhomeserver/ai-PA
    
    # Stop all services
    log_info "Stopping all services..."
    docker-compose down
    
    # Clean up (optional)
    log_info "Cleaning up Docker system..."
    docker system prune -f
    
    # Restart services
    log_info "Restarting services..."
    if docker-compose up -d; then
        log_success "Services restarted successfully"
    else
        log_error "Failed to restart services"
        return 1
    fi
    
    # Wait for services to start
    log_info "Waiting for services to start..."
    sleep 30
    
    # Verify services
    log_info "Verifying services..."
    docker-compose ps
}

# Check service health
check_service_health() {
    log_info "Checking service health..."
    
    local services=(
        "http://localhost:8083/health:Health Monitor"
        "http://localhost:5678/healthz:n8n"
        "http://localhost:8283/v1/health/:Letta"
        "http://localhost:8080/health:Open WebUI"
        "http://localhost:9000/api/status:Portainer"
        "http://localhost:9090/login:Cockpit"
    )
    
    for service in "${services[@]}"; do
        local url=$(echo $service | cut -d: -f1-3)
        local name=$(echo $service | cut -d: -f4)
        
        if curl -f -s "$url" >/dev/null 2>&1; then
            log_success "$name is healthy"
        else
            log_warning "$name is not responding"
        fi
    done
}

# Display recovery summary
display_summary() {
    echo ""
    echo "=========================================="
    echo "SYSTEM RECOVERY SUMMARY"
    echo "=========================================="
    echo "System Uptime: $(uptime | awk '{print $3,$4}' | sed 's/,//')"
    echo "Docker Status: $(docker info >/dev/null 2>&1 && echo "Running" || echo "Not Running")"
    echo "Services Status:"
    docker-compose ps 2>/dev/null || echo "Docker Compose not available"
    echo ""
    echo "Access Methods:"
    echo "- SSH: ssh $USER@$(ifconfig | grep -E "inet.*broadcast" | awk '{print $2}' | head -1)"
    echo "- RustDesk: rustdesk.cd-ai-pa.work:21116"
    echo "- Portainer: http://localhost:9000"
    echo "- Cockpit: http://localhost:9090"
    echo "=========================================="
    echo ""
}

# Main execution
main() {
    echo "=========================================="
    echo "SYSTEM RECOVERY SCRIPT"
    echo "=========================================="
    echo ""
    
    check_system_status
    check_network
    check_ports
    start_docker
    check_docker_status
    restart_docker_services
    check_service_health
    display_summary
    
    log_success "System recovery completed!"
}

# Run main function
main "$@"

