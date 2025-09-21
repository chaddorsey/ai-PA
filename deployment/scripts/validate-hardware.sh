#!/bin/bash

# Hardware Requirements Validation Script
# Validates hardware requirements for PA ecosystem deployment

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

# Check CPU cores
check_cpu() {
    log_info "Checking CPU requirements..."
    
    # Get CPU cores
    if command -v nproc >/dev/null 2>&1; then
        CPU_CORES=$(nproc)
    elif command -v sysctl >/dev/null 2>&1; then
        CPU_CORES=$(sysctl -n hw.ncpu)
    else
        CPU_CORES=$(grep -c ^processor /proc/cpuinfo 2>/dev/null || echo "unknown")
    fi
    
    # Get CPU model
    if [[ -f /proc/cpuinfo ]]; then
        CPU_MODEL=$(grep "model name" /proc/cpuinfo | head -1 | cut -d: -f2 | xargs)
    elif command -v sysctl >/dev/null 2>&1; then
        CPU_MODEL=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "unknown")
    else
        CPU_MODEL="unknown"
    fi
    
    echo "  CPU Model: $CPU_MODEL"
    echo "  CPU Cores: $CPU_CORES"
    
    if [[ "$CPU_CORES" != "unknown" && $CPU_CORES -ge 8 ]]; then
        log_success "CPU cores: $CPU_CORES (recommended: 8+)"
    elif [[ "$CPU_CORES" != "unknown" && $CPU_CORES -ge 4 ]]; then
        log_warning "CPU cores: $CPU_CORES (minimum: 4, recommended: 8+)"
        ((WARNINGS++))
    elif [[ "$CPU_CORES" != "unknown" ]]; then
        log_error "Insufficient CPU cores: $CPU_CORES (minimum: 4)"
        VALIDATION_PASSED=false
        ((ERRORS++))
    else
        log_warning "Cannot determine CPU core count"
        ((WARNINGS++))
    fi
    
    # Check CPU frequency if available
    if [[ -f /proc/cpuinfo ]]; then
        CPU_FREQ=$(grep "cpu MHz" /proc/cpuinfo | head -1 | cut -d: -f2 | xargs)
        if [[ -n "$CPU_FREQ" ]]; then
            CPU_GHZ=$(echo "scale=1; $CPU_FREQ/1000" | bc -l 2>/dev/null || echo "unknown")
            echo "  CPU Frequency: ${CPU_GHZ}GHz"
        fi
    elif command -v sysctl >/dev/null 2>&1; then
        CPU_FREQ=$(sysctl -n hw.cpufrequency 2>/dev/null || echo "0")
        if [[ "$CPU_FREQ" != "0" ]]; then
            CPU_GHZ=$(echo "scale=1; $CPU_FREQ/1000000000" | bc -l 2>/dev/null || echo "unknown")
            echo "  CPU Frequency: ${CPU_GHZ}GHz"
        fi
    fi
}

# Check RAM
check_ram() {
    log_info "Checking RAM requirements..."
    
    if command -v free >/dev/null 2>&1; then
        RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
        RAM_GB=$((RAM_KB / 1024 / 1024))
        
        echo "  Total RAM: ${RAM_GB}GB"
        
        if [[ $RAM_GB -ge 16 ]]; then
            log_success "RAM: ${RAM_GB}GB (recommended: 16GB+)"
        elif [[ $RAM_GB -ge 8 ]]; then
            log_warning "RAM: ${RAM_GB}GB (minimum: 8GB, recommended: 16GB+)"
            ((WARNINGS++))
        else
            log_error "Insufficient RAM: ${RAM_GB}GB (minimum: 8GB)"
            VALIDATION_PASSED=false
            ((ERRORS++))
        fi
        
        # Check available RAM
        AVAIL_KB=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
        AVAIL_GB=$((AVAIL_KB / 1024 / 1024))
        echo "  Available RAM: ${AVAIL_GB}GB"
        
        if [[ $AVAIL_GB -lt 4 ]]; then
            log_warning "Low available RAM: ${AVAIL_GB}GB (recommended: 4GB+ available)"
            ((WARNINGS++))
        fi
    elif command -v sysctl >/dev/null 2>&1; then
        RAM_BYTES=$(sysctl -n hw.memsize)
        RAM_GB=$((RAM_BYTES / 1024 / 1024 / 1024))
        
        echo "  Total RAM: ${RAM_GB}GB"
        
        if [[ $RAM_GB -ge 16 ]]; then
            log_success "RAM: ${RAM_GB}GB (recommended: 16GB+)"
        elif [[ $RAM_GB -ge 8 ]]; then
            log_warning "RAM: ${RAM_GB}GB (minimum: 8GB, recommended: 16GB+)"
            ((WARNINGS++))
        else
            log_error "Insufficient RAM: ${RAM_GB}GB (minimum: 8GB)"
            VALIDATION_PASSED=false
            ((ERRORS++))
        fi
    else
        log_error "Cannot check RAM (free or sysctl command not available)"
        VALIDATION_PASSED=false
        ((ERRORS++))
    fi
}

# Check disk space
check_disk() {
    log_info "Checking disk space requirements..."
    
    # Check current directory disk space
    if df -BG . >/dev/null 2>&1; then
        # Linux df with -BG option
        DISK_SPACE_GB=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
    else
        # macOS df without -BG option
        DISK_SPACE_KB=$(df -k . | awk 'NR==2 {print $4}')
        DISK_SPACE_GB=$((DISK_SPACE_KB / 1024 / 1024))
    fi
    
    echo "  Available disk space: ${DISK_SPACE_GB}GB"
    
    if [[ $DISK_SPACE_GB -ge 200 ]]; then
        log_success "Disk space: ${DISK_SPACE_GB}GB (recommended: 200GB+)"
    elif [[ $DISK_SPACE_GB -ge 100 ]]; then
        log_warning "Disk space: ${DISK_SPACE_GB}GB (minimum: 100GB, recommended: 200GB+)"
        ((WARNINGS++))
    else
        log_error "Insufficient disk space: ${DISK_SPACE_GB}GB (minimum: 100GB)"
        VALIDATION_PASSED=false
        ((ERRORS++))
    fi
    
    # Check if we're on an SSD (if possible)
    if command -v lsblk >/dev/null 2>&1; then
        ROOT_DEVICE=$(df . | awk 'NR==2 {print $1}' | sed 's/[0-9]*$//')
        if [[ -n "$ROOT_DEVICE" ]]; then
            DEVICE_TYPE=$(lsblk -d -o ROTA "$ROOT_DEVICE" 2>/dev/null | tail -1 | xargs)
            if [[ "$DEVICE_TYPE" == "0" ]]; then
                log_success "Storage device appears to be SSD (recommended)"
            elif [[ "$DEVICE_TYPE" == "1" ]]; then
                log_warning "Storage device appears to be HDD (SSD recommended for better performance)"
                ((WARNINGS++))
            fi
        fi
    fi
}

# Check system load
check_load() {
    log_info "Checking system load..."
    
    if command -v uptime >/dev/null 2>&1; then
        LOAD_AVG=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//')
        
        # Get CPU cores
        if command -v nproc >/dev/null 2>&1; then
            CPU_CORES=$(nproc)
        elif command -v sysctl >/dev/null 2>&1; then
            CPU_CORES=$(sysctl -n hw.ncpu)
        else
            CPU_CORES=$(grep -c ^processor /proc/cpuinfo 2>/dev/null || echo "1")
        fi
        
        echo "  Load average: $LOAD_AVG"
        echo "  CPU cores: $CPU_CORES"
        
        # Convert load average to float for comparison
        LOAD_FLOAT=$(echo "$LOAD_AVG" | bc -l 2>/dev/null || echo "0")
        CORES_FLOAT=$(echo "$CPU_CORES" | bc -l 2>/dev/null || echo "1")
        
        if (( $(echo "$LOAD_FLOAT < $CORES_FLOAT" | bc -l 2>/dev/null || echo "0") )); then
            log_success "System load is acceptable"
        else
            log_warning "High system load detected: $LOAD_AVG (consider reducing load before deployment)"
            ((WARNINGS++))
        fi
    else
        log_warning "Cannot check system load (uptime command not available)"
        ((WARNINGS++))
    fi
}

# Check swap space
check_swap() {
    log_info "Checking swap space..."
    
    if command -v swapon >/dev/null 2>&1; then
        SWAP_INFO=$(swapon --show=NAME,SIZE --noheadings 2>/dev/null || true)
        
        if [[ -n "$SWAP_INFO" ]]; then
            SWAP_SIZE=$(echo "$SWAP_INFO" | awk '{sum+=$2} END {print sum}' 2>/dev/null || echo "0")
            echo "  Swap size: ${SWAP_SIZE}KB"
            
            if [[ $SWAP_SIZE -gt 0 ]]; then
                log_success "Swap space is configured"
            else
                log_warning "No swap space configured (recommended for stability)"
                ((WARNINGS++))
            fi
        else
            log_warning "No swap space configured (recommended for stability)"
            ((WARNINGS++))
        fi
    else
        log_warning "Cannot check swap space (swapon command not available)"
        ((WARNINGS++))
    fi
}

# Main validation function
main() {
    echo "=========================================="
    echo "Hardware Requirements Validation"
    echo "=========================================="
    echo
    
    check_cpu
    echo
    check_ram
    echo
    check_disk
    echo
    check_load
    echo
    check_swap
    
    echo
    echo "=========================================="
    echo "Hardware Validation Summary"
    echo "=========================================="
    
    if [[ $VALIDATION_PASSED == true ]]; then
        log_success "Hardware requirements validation PASSED"
        if [[ $WARNINGS -gt 0 ]]; then
            log_warning "Found $WARNINGS warnings (see above for details)"
        fi
        exit 0
    else
        log_error "Hardware requirements validation FAILED"
        log_error "Found $ERRORS errors and $WARNINGS warnings"
        exit 1
    fi
}

# Run main function
main "$@"
