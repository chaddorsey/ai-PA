#!/bin/bash

# Dependencies Validation Script
# Validates software dependencies for PA ecosystem deployment

set -euo pipefail

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

# Check Docker installation and version
check_docker() {
    log_info "Checking Docker installation..."
    
    if command -v docker >/dev/null 2>&1; then
        DOCKER_VERSION=$(docker --version | cut -d' ' -f3 | cut -d',' -f1)
        log_success "Docker installed: $DOCKER_VERSION"
        
        # Check Docker version (minimum 20.10.0)
        DOCKER_MAJOR=$(echo $DOCKER_VERSION | cut -d'.' -f1)
        DOCKER_MINOR=$(echo $DOCKER_VERSION | cut -d'.' -f2)
        
        if [[ $DOCKER_MAJOR -gt 20 || ($DOCKER_MAJOR -eq 20 && $DOCKER_MINOR -ge 10) ]]; then
            log_success "Docker version is compatible (minimum: 20.10.0)"
        else
            log_error "Docker version $DOCKER_VERSION is too old. Minimum required: 20.10.0"
            VALIDATION_PASSED=false
            ((ERRORS++))
        fi
        
        # Check if Docker daemon is running
        if docker info >/dev/null 2>&1; then
            log_success "Docker daemon is running"
            
            # Check Docker daemon version
            DAEMON_VERSION=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unknown")
            if [[ "$DAEMON_VERSION" != "unknown" ]]; then
                log_success "Docker daemon version: $DAEMON_VERSION"
            fi
        else
            log_error "Docker daemon is not running"
            VALIDATION_PASSED=false
            ((ERRORS++))
        fi
        
        # Check Docker Compose plugin
        if docker compose version >/dev/null 2>&1; then
            COMPOSE_PLUGIN_VERSION=$(docker compose version --short 2>/dev/null || echo "unknown")
            log_success "Docker Compose plugin available: $COMPOSE_PLUGIN_VERSION"
        else
            log_warning "Docker Compose plugin not available (will check standalone version)"
            ((WARNINGS++))
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
    
    # Check for Docker Compose plugin first
    if docker compose version >/dev/null 2>&1; then
        COMPOSE_VERSION=$(docker compose version --short 2>/dev/null || echo "unknown")
        log_success "Docker Compose plugin: $COMPOSE_VERSION"
        return 0
    fi
    
    # Check for standalone Docker Compose
    if command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_VERSION=$(docker-compose --version | cut -d' ' -f3 | cut -d',' -f1)
        log_success "Docker Compose standalone: $COMPOSE_VERSION"
        
        # Check Docker Compose version (minimum 2.0.0)
        COMPOSE_MAJOR=$(echo $COMPOSE_VERSION | cut -d'.' -f1)
        if [[ $COMPOSE_MAJOR -ge 2 ]]; then
            log_success "Docker Compose version is compatible (minimum: 2.0.0)"
        else
            log_error "Docker Compose version $COMPOSE_VERSION is too old. Minimum required: 2.0.0"
            VALIDATION_PASSED=false
            ((ERRORS++))
        fi
    else
        log_error "Docker Compose is not installed (plugin or standalone)"
        VALIDATION_PASSED=false
        ((ERRORS++))
    fi
}

# Check required commands
check_required_commands() {
    log_info "Checking required commands..."
    
    local commands=("curl" "git")
    
    for cmd in "${commands[@]}"; do
        if command -v "$cmd" >/dev/null 2>&1; then
            VERSION=$($cmd --version 2>/dev/null | head -1 | cut -d' ' -f2- || echo "unknown")
            log_success "Required command '$cmd': $VERSION"
        else
            log_error "Required command '$cmd' is not installed"
            VALIDATION_PASSED=false
            ((ERRORS++))
        fi
    done
}

# Check optional commands
check_optional_commands() {
    log_info "Checking optional commands..."
    
    local commands=("jq" "htop" "nc" "netstat")
    
    for cmd in "${commands[@]}"; do
        if command -v "$cmd" >/dev/null 2>&1; then
            VERSION=$($cmd --version 2>/dev/null | head -1 | cut -d' ' -f2- || echo "available")
            log_success "Optional command '$cmd': $VERSION"
        else
            log_warning "Optional command '$cmd' is not installed (recommended)"
            ((WARNINGS++))
        fi
    done
}

# Check package manager
check_package_manager() {
    log_info "Checking package manager..."
    
    if command -v apt >/dev/null 2>&1; then
        log_success "Package manager: apt (Ubuntu/Debian)"
    elif command -v yum >/dev/null 2>&1; then
        log_success "Package manager: yum (CentOS/RHEL)"
    elif command -v dnf >/dev/null 2>&1; then
        log_success "Package manager: dnf (Fedora/CentOS 8+)"
    elif command -v zypper >/dev/null 2>&1; then
        log_success "Package manager: zypper (openSUSE)"
    else
        log_warning "Unknown package manager (may affect installation scripts)"
        ((WARNINGS++))
    fi
}

# Check system libraries
check_system_libraries() {
    log_info "Checking system libraries..."
    
    # Check for common libraries
    local libraries=("libc6" "libssl" "libffi")
    
    for lib in "${libraries[@]}"; do
        if ldconfig -p 2>/dev/null | grep -q "$lib"; then
            log_success "Library '$lib' is available"
        else
            log_warning "Library '$lib' may not be available (check with package manager)"
            ((WARNINGS++))
        fi
    done
}

# Check Python (if available)
check_python() {
    log_info "Checking Python installation..."
    
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
        log_success "Python3 available: $PYTHON_VERSION"
        
        # Check Python version (minimum 3.8)
        PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
        PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
        
        if [[ $PYTHON_MAJOR -gt 3 || ($PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -ge 8) ]]; then
            log_success "Python version is compatible (minimum: 3.8)"
        else
            log_warning "Python version $PYTHON_VERSION may be too old (minimum: 3.8)"
            ((WARNINGS++))
        fi
    else
        log_warning "Python3 is not installed (required for some services)"
        ((WARNINGS++))
    fi
}

# Check Node.js (if available)
check_nodejs() {
    log_info "Checking Node.js installation..."
    
    if command -v node >/dev/null 2>&1; then
        NODE_VERSION=$(node --version 2>&1 | cut -d'v' -f2)
        log_success "Node.js available: v$NODE_VERSION"
        
        # Check Node.js version (minimum 16)
        NODE_MAJOR=$(echo $NODE_VERSION | cut -d'.' -f1)
        
        if [[ $NODE_MAJOR -ge 16 ]]; then
            log_success "Node.js version is compatible (minimum: 16)"
        else
            log_warning "Node.js version $NODE_VERSION may be too old (minimum: 16)"
            ((WARNINGS++))
        fi
    else
        log_warning "Node.js is not installed (required for some services)"
        ((WARNINGS++))
    fi
}

# Check available disk space for Docker
check_docker_space() {
    log_info "Checking Docker storage space..."
    
    if docker info >/dev/null 2>&1; then
        # Get Docker root directory
        DOCKER_ROOT=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo "/var/lib/docker")
        
        if [[ -d "$DOCKER_ROOT" ]]; then
            DOCKER_SPACE_KB=$(df "$DOCKER_ROOT" | awk 'NR==2 {print $4}')
            DOCKER_SPACE_GB=$((DOCKER_SPACE_KB / 1024 / 1024))
            
            echo "  Docker storage space: ${DOCKER_SPACE_GB}GB"
            
            if [[ $DOCKER_SPACE_GB -ge 50 ]]; then
                log_success "Docker storage space is sufficient (recommended: 50GB+)"
            elif [[ $DOCKER_SPACE_GB -ge 20 ]]; then
                log_warning "Docker storage space may be limited: ${DOCKER_SPACE_GB}GB (recommended: 50GB+)"
                ((WARNINGS++))
            else
                log_error "Insufficient Docker storage space: ${DOCKER_SPACE_GB}GB (minimum: 20GB)"
                VALIDATION_PASSED=false
                ((ERRORS++))
            fi
        else
            log_warning "Cannot determine Docker storage space"
            ((WARNINGS++))
        fi
    else
        log_warning "Cannot check Docker storage (daemon not running)"
        ((WARNINGS++))
    fi
}

# Main validation function
main() {
    echo "=========================================="
    echo "Dependencies Validation"
    echo "=========================================="
    echo
    
    check_docker
    echo
    check_docker_compose
    echo
    check_required_commands
    echo
    check_optional_commands
    echo
    check_package_manager
    echo
    check_system_libraries
    echo
    check_python
    echo
    check_nodejs
    echo
    check_docker_space
    
    echo
    echo "=========================================="
    echo "Dependencies Validation Summary"
    echo "=========================================="
    
    if [[ $VALIDATION_PASSED == true ]]; then
        log_success "Dependencies validation PASSED"
        if [[ $WARNINGS -gt 0 ]]; then
            log_warning "Found $WARNINGS warnings (see above for details)"
        fi
        exit 0
    else
        log_error "Dependencies validation FAILED"
        log_error "Found $ERRORS errors and $WARNINGS warnings"
        exit 1
    fi
}

# Run main function
main "$@"
