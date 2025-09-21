#!/bin/bash

# PA Ecosystem Requirements Validation Script
# This script validates that the system meets all requirements for PA ecosystem deployment

set -uo pipefail

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

# Validation results
VALIDATION_PASSED=true
WARNINGS=0
ERRORS=0

# Check if running as root (not recommended)
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_warning "Running as root. Consider using a non-root user with docker group access."
        ((WARNINGS++))
    fi
}

# Check operating system
check_os() {
    log_info "Checking operating system..."
    
    # Detect OS
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS_NAME="$NAME"
        OS_VERSION="$VERSION_ID"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS_NAME="macOS"
        OS_VERSION=$(sw_vers -productVersion 2>/dev/null || echo "unknown")
    elif [[ -f /etc/redhat-release ]]; then
        OS_NAME="Red Hat"
        OS_VERSION=$(cat /etc/redhat-release | cut -d' ' -f3)
    else
        OS_NAME="Unknown"
        OS_VERSION="unknown"
    fi
    
    case "$OS_NAME" in
        "Ubuntu")
            if [[ "$OS_VERSION" == "20.04" || "$OS_VERSION" == "22.04" ]]; then
                log_success "Supported OS: $OS_NAME $OS_VERSION"
            else
                log_warning "OS version $OS_VERSION may not be fully supported. Recommended: Ubuntu 20.04 LTS or 22.04 LTS"
                ((WARNINGS++))
            fi
            ;;
        "CentOS Linux")
            if [[ "$OS_VERSION" == "8" ]]; then
                log_success "Supported OS: $OS_NAME $OS_VERSION"
            else
                log_warning "OS version $OS_VERSION may not be fully supported. Recommended: CentOS 8"
                ((WARNINGS++))
            fi
            ;;
        "Debian GNU/Linux")
            if [[ "$OS_VERSION" == "11" ]]; then
                log_success "Supported OS: $OS_NAME $OS_VERSION"
            else
                log_warning "OS version $OS_VERSION may not be fully supported. Recommended: Debian 11"
                ((WARNINGS++))
            fi
            ;;
        "macOS")
            log_warning "macOS detected: $OS_VERSION. This script is designed for Linux deployment. Use Docker Desktop for testing."
            ((WARNINGS++))
            ;;
        *)
            log_warning "Unsupported OS: $OS_NAME $OS_VERSION. Supported: Ubuntu 20.04/22.04, CentOS 8, Debian 11"
            ((WARNINGS++))
            ;;
    esac
}

# Check hardware requirements
check_hardware() {
    log_info "Checking hardware requirements..."
    
    # Check CPU cores
    if command -v nproc >/dev/null 2>&1; then
        CPU_CORES=$(nproc)
    elif command -v sysctl >/dev/null 2>&1; then
        CPU_CORES=$(sysctl -n hw.ncpu)
    else
        CPU_CORES=$(grep -c ^processor /proc/cpuinfo 2>/dev/null || echo "unknown")
    fi
    
    if [[ "$CPU_CORES" != "unknown" && $CPU_CORES -ge 4 ]]; then
        log_success "CPU cores: $CPU_CORES (minimum: 4)"
    elif [[ "$CPU_CORES" != "unknown" ]]; then
        log_error "Insufficient CPU cores: $CPU_CORES (minimum: 4)"
        VALIDATION_PASSED=false
        ((ERRORS++))
    else
        log_warning "Cannot determine CPU core count"
        ((WARNINGS++))
    fi
    
    # Check RAM
    if command -v free >/dev/null 2>&1; then
        RAM_GB=$(free -g | awk '/^Mem:/{print $2}')
    elif command -v sysctl >/dev/null 2>&1; then
        RAM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
    else
        RAM_GB="unknown"
    fi
    
    if [[ "$RAM_GB" != "unknown" && $RAM_GB -ge 8 ]]; then
        log_success "RAM: ${RAM_GB}GB (minimum: 8GB)"
    elif [[ "$RAM_GB" != "unknown" ]]; then
        log_error "Insufficient RAM: ${RAM_GB}GB (minimum: 8GB)"
        VALIDATION_PASSED=false
        ((ERRORS++))
    else
        log_warning "Cannot check RAM"
        ((WARNINGS++))
    fi
    
    # Check disk space
    if command -v df >/dev/null 2>&1; then
        if df -BG . >/dev/null 2>&1; then
            # Linux df with -BG option
            DISK_SPACE_GB=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
        else
            # macOS df without -BG option
            DISK_SPACE_KB=$(df -k . | awk 'NR==2 {print $4}')
            DISK_SPACE_GB=$((DISK_SPACE_KB / 1024 / 1024))
        fi
        
        if [[ $DISK_SPACE_GB -ge 100 ]]; then
            log_success "Available disk space: ${DISK_SPACE_GB}GB (minimum: 100GB)"
        else
            log_error "Insufficient disk space: ${DISK_SPACE_GB}GB (minimum: 100GB)"
            VALIDATION_PASSED=false
            ((ERRORS++))
        fi
    else
        log_warning "Cannot check disk space"
        ((WARNINGS++))
    fi
}

# Check Docker installation
check_docker() {
    log_info "Checking Docker installation..."
    
    if command -v docker >/dev/null 2>&1; then
        DOCKER_VERSION=$(docker --version | cut -d' ' -f3 | cut -d',' -f1)
        log_success "Docker installed: $DOCKER_VERSION"
        
        # Check if Docker daemon is running
        if docker info >/dev/null 2>&1; then
            log_success "Docker daemon is running"
        else
            log_error "Docker daemon is not running"
            VALIDATION_PASSED=false
            ((ERRORS++))
        fi
        
        # Check Docker version (minimum 20.10.0)
        DOCKER_MAJOR=$(echo $DOCKER_VERSION | cut -d'.' -f1)
        DOCKER_MINOR=$(echo $DOCKER_VERSION | cut -d'.' -f2)
        if [[ $DOCKER_MAJOR -gt 20 || ($DOCKER_MAJOR -eq 20 && $DOCKER_MINOR -ge 10) ]]; then
            log_success "Docker version is compatible"
        else
            log_error "Docker version $DOCKER_VERSION is too old. Minimum required: 20.10.0"
            VALIDATION_PASSED=false
            ((ERRORS++))
        fi
    else
        log_error "Docker is not installed"
        VALIDATION_PASSED=false
        ((ERRORS++))
    fi
}

# Check Docker Compose installation
check_docker_compose() {
    log_info "Checking Docker Compose installation..."
    
    if command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_VERSION=$(docker-compose --version | cut -d' ' -f3 | cut -d',' -f1)
        if [[ -n "$COMPOSE_VERSION" && "$COMPOSE_VERSION" != "version" ]]; then
            log_success "Docker Compose installed: $COMPOSE_VERSION"
        else
            log_success "Docker Compose installed: $(docker-compose --version)"
        fi
        
        # Check Docker Compose version (minimum 2.0.0)
        if [[ -n "$COMPOSE_VERSION" && "$COMPOSE_VERSION" != "version" ]]; then
            COMPOSE_MAJOR=$(echo $COMPOSE_VERSION | cut -d'.' -f1)
            if [[ $COMPOSE_MAJOR -ge 2 ]]; then
                log_success "Docker Compose version is compatible (minimum: 2.0.0)"
            else
                log_error "Docker Compose version $COMPOSE_VERSION is too old. Minimum required: 2.0.0"
                VALIDATION_PASSED=false
                ((ERRORS++))
            fi
        else
            log_warning "Cannot parse Docker Compose version, but it appears to be installed"
            ((WARNINGS++))
        fi
    else
        log_error "Docker Compose is not installed"
        VALIDATION_PASSED=false
        ((ERRORS++))
    fi
}

# Check required commands
check_commands() {
    log_info "Checking required commands..."
    
    local commands=("curl" "git")
    local optional_commands=("jq" "htop")
    
    for cmd in "${commands[@]}"; do
        if command -v "$cmd" >/dev/null 2>&1; then
            log_success "Required command '$cmd' is available"
        else
            log_error "Required command '$cmd' is not installed"
            VALIDATION_PASSED=false
            ((ERRORS++))
        fi
    done
    
    for cmd in "${optional_commands[@]}"; do
        if command -v "$cmd" >/dev/null 2>&1; then
            log_success "Optional command '$cmd' is available"
        else
            log_warning "Optional command '$cmd' is not installed (recommended)"
            ((WARNINGS++))
        fi
    done
}

# Check network connectivity
check_network() {
    log_info "Checking network connectivity..."
    
    # Check internet connectivity
    if curl -s --connect-timeout 10 https://www.google.com >/dev/null 2>&1; then
        log_success "Internet connectivity is working"
    else
        log_error "No internet connectivity detected"
        VALIDATION_PASSED=false
        ((ERRORS++))
    fi
    
    # Check DNS resolution
    if nslookup google.com >/dev/null 2>&1; then
        log_success "DNS resolution is working"
    else
        log_warning "DNS resolution may have issues"
        ((WARNINGS++))
    fi
}

# Check file permissions
check_permissions() {
    log_info "Checking file permissions..."
    
    # Check if user is in docker group
    if groups | grep -q docker; then
        log_success "User is in docker group"
    else
        log_warning "User is not in docker group. You may need to use 'sudo' with Docker commands"
        ((WARNINGS++))
    fi
    
    # Check if Docker socket is accessible
    if [[ -S /var/run/docker.sock ]]; then
        if [[ -r /var/run/docker.sock && -w /var/run/docker.sock ]]; then
            log_success "Docker socket is accessible"
        else
            log_warning "Docker socket permissions may be restrictive"
            ((WARNINGS++))
        fi
    else
        log_error "Docker socket not found"
        VALIDATION_PASSED=false
        ((ERRORS++))
    fi
}

# Check available ports
check_ports() {
    log_info "Checking port availability..."
    
    local ports=(80 443 8080 8081 8082 8083)
    local occupied_ports=()
    
    for port in "${ports[@]}"; do
        if netstat -tuln 2>/dev/null | grep -q ":$port "; then
            occupied_ports+=($port)
        fi
    done
    
    if [[ ${#occupied_ports[@]} -eq 0 ]]; then
        log_success "All required ports are available"
    else
        log_warning "Some ports are already in use: ${occupied_ports[*]}"
        log_warning "This may cause conflicts during deployment"
        ((WARNINGS++))
    fi
}

# Check environment file
check_environment() {
    log_info "Checking environment configuration..."
    
    if [[ -f ".env" ]]; then
        log_success "Environment file (.env) found"
        
        # Check for required environment variables
        local required_vars=(
            "POSTGRES_PASSWORD"
            "SUPABASE_ANON_KEY"
            "SUPABASE_SERVICE_KEY"
            "N8N_ENCRYPTION_KEY"
            "N8N_WEBHOOK_URL"
            "WEBHOOK_URL"
            "CLOUDFLARE_TUNNEL_TOKEN"
            "ANTHROPIC_API_KEY"
            "GEMINI_API_KEY"
            "OPENAI_API_KEY"
            "SLACK_BOT_TOKEN"
            "SLACK_APP_TOKEN"
            "LETTA_AGENT_ID"
        )
        
        local missing_vars=()
        for var in "${required_vars[@]}"; do
            if ! grep -q "^${var}=" .env; then
                missing_vars+=($var)
            fi
        done
        
        if [[ ${#missing_vars[@]} -eq 0 ]]; then
            log_success "All required environment variables are defined"
        else
            log_error "Missing required environment variables: ${missing_vars[*]}"
            VALIDATION_PASSED=false
            ((ERRORS++))
        fi
    else
        log_warning "Environment file (.env) not found. You'll need to create one before deployment"
        ((WARNINGS++))
    fi
}

# Main validation function
main() {
    echo "=========================================="
    echo "PA Ecosystem Requirements Validation"
    echo "=========================================="
    echo
    
    check_root
    check_os
    check_hardware
    check_docker
    check_docker_compose
    check_commands
    check_network
    check_permissions
    check_ports
    check_environment
    
    echo
    echo "=========================================="
    echo "Validation Summary"
    echo "=========================================="
    
    if [[ $VALIDATION_PASSED == true ]]; then
        log_success "System requirements validation PASSED"
        echo
        if [[ $WARNINGS -gt 0 ]]; then
            log_warning "Found $WARNINGS warnings (see above for details)"
        fi
        echo
        log_info "Your system is ready for PA ecosystem deployment!"
        exit 0
    else
        log_error "System requirements validation FAILED"
        echo
        log_error "Found $ERRORS errors and $WARNINGS warnings"
        echo
        log_info "Please address the errors above before proceeding with deployment"
        exit 1
    fi
}

# Run main function
main "$@"
