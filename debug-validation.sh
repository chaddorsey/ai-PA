#!/bin/bash

# Debug script to test validation functions

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
        DISK_SPACE_GB=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
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

echo "Testing hardware check function..."
check_hardware
echo "Hardware check completed with exit code: $?"
