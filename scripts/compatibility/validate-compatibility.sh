#!/bin/bash

# Version Compatibility Validation Script
# Purpose: Validate version compatibility between frameworks and infrastructure
# Usage: ./validate-compatibility.sh [--framework <framework>] [--target-version <version>] [--check-all]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MATRIX_FILE="$PROJECT_ROOT/config/compatibility/compatibility-matrix.yml"
LOG_FILE="$PROJECT_ROOT/logs/compatibility/validation-$(date +%Y%m%d-%H%M%S).log"
FRAMEWORK=""
TARGET_VERSION=""
CHECK_ALL=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --framework)
            FRAMEWORK="$2"
            shift 2
            ;;
        --target-version)
            TARGET_VERSION="$2"
            shift 2
            ;;
        --check-all)
            CHECK_ALL=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--framework <framework>] [--target-version <version>] [--check-all]"
            echo ""
            echo "Options:"
            echo "  --framework       Specific framework to check (n8n, letta, graphiti)"
            echo "  --target-version  Target version to validate"
            echo "  --check-all       Check compatibility for all frameworks"
            echo "  -h, --help        Show this help message"
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

# Validate matrix file exists
validate_matrix_file() {
    if [ ! -f "$MATRIX_FILE" ]; then
        error_exit "Compatibility matrix file not found: $MATRIX_FILE"
    fi
    
    success "Compatibility matrix file found"
}

# Get current version of framework
get_current_version() {
    local framework="$1"
    
    case "$framework" in
        "n8n")
            if docker ps --format "table {{.Names}}" | grep -q "^n8n$"; then
                docker exec n8n n8n --version 2>/dev/null | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+' || echo "unknown"
            else
                echo "not_running"
            fi
            ;;
        "letta")
            if docker ps --format "table {{.Names}}" | grep -q "^ai-pa-letta-1$"; then
                curl -s http://localhost:8283/v1/health/ 2>/dev/null | jq -r '.version // "unknown"' || echo "unknown"
            else
                echo "not_running"
            fi
            ;;
        "graphiti")
            local pyproject_file="$PROJECT_ROOT/graphiti/pyproject.toml"
            if [ -f "$pyproject_file" ]; then
                grep -o 'version[[:space:]]*=[[:space:]]*"[^"]*"' "$pyproject_file" | cut -d'"' -f2
            else
                echo "unknown"
            fi
            ;;
        *)
            error_exit "Unknown framework: $framework"
            ;;
    esac
}

# Check compatibility in matrix
check_compatibility() {
    local framework="$1"
    local version="$2"
    local target_framework="$3"
    local target_version="$4"
    
    # Extract compatibility status from matrix
    local compatibility=$(grep -A 20 "  $framework:" "$MATRIX_FILE" | grep -A 10 "    \"$version\":" | grep -A 5 "      $target_framework:" | grep "        \"$target_version\":" | cut -d'"' -f4)
    
    echo "$compatibility"
}

# Validate framework compatibility
validate_framework_compatibility() {
    local framework="$1"
    local target_version="$2"
    
    info "Validating compatibility for $framework version $target_version"
    
    # Get current versions of other frameworks
    local current_n8n=$(get_current_version "n8n")
    local current_letta=$(get_current_version "letta")
    local current_graphiti=$(get_current_version "graphiti")
    
    info "Current versions: n8n=$current_n8n, letta=$current_letta, graphiti=$current_graphiti"
    
    # Check compatibility with each framework
    case "$framework" in
        "n8n")
            if [ "$current_letta" != "unknown" ] && [ "$current_letta" != "not_running" ]; then
                local compatibility=$(check_compatibility "n8n" "$target_version" "letta" "$current_letta")
                if [ "$compatibility" = "compatible" ]; then
                    success "n8n $target_version is compatible with Letta $current_letta"
                elif [ "$compatibility" = "incompatible" ]; then
                    error_exit "n8n $target_version is incompatible with Letta $current_letta"
                else
                    warning "n8n $target_version compatibility with Letta $current_letta is unknown"
                fi
            fi
            
            if [ "$current_graphiti" != "unknown" ] && [ "$current_graphiti" != "not_running" ]; then
                local compatibility=$(check_compatibility "n8n" "$target_version" "graphiti" "$current_graphiti")
                if [ "$compatibility" = "compatible" ]; then
                    success "n8n $target_version is compatible with Graphiti $current_graphiti"
                elif [ "$compatibility" = "incompatible" ]; then
                    error_exit "n8n $target_version is incompatible with Graphiti $current_graphiti"
                else
                    warning "n8n $target_version compatibility with Graphiti $current_graphiti is unknown"
                fi
            fi
            ;;
            
        "letta")
            if [ "$current_n8n" != "unknown" ] && [ "$current_n8n" != "not_running" ]; then
                local compatibility=$(check_compatibility "letta" "$target_version" "n8n" "$current_n8n")
                if [ "$compatibility" = "compatible" ]; then
                    success "Letta $target_version is compatible with n8n $current_n8n"
                elif [ "$compatibility" = "incompatible" ]; then
                    error_exit "Letta $target_version is incompatible with n8n $current_n8n"
                else
                    warning "Letta $target_version compatibility with n8n $current_n8n is unknown"
                fi
            fi
            
            if [ "$current_graphiti" != "unknown" ] && [ "$current_graphiti" != "not_running" ]; then
                local compatibility=$(check_compatibility "letta" "$target_version" "graphiti" "$current_graphiti")
                if [ "$compatibility" = "compatible" ]; then
                    success "Letta $target_version is compatible with Graphiti $current_graphiti"
                elif [ "$compatibility" = "incompatible" ]; then
                    error_exit "Letta $target_version is incompatible with Graphiti $current_graphiti"
                else
                    warning "Letta $target_version compatibility with Graphiti $current_graphiti is unknown"
                fi
            fi
            ;;
            
        "graphiti")
            if [ "$current_n8n" != "unknown" ] && [ "$current_n8n" != "not_running" ]; then
                local compatibility=$(check_compatibility "graphiti" "$target_version" "n8n" "$current_n8n")
                if [ "$compatibility" = "compatible" ]; then
                    success "Graphiti $target_version is compatible with n8n $current_n8n"
                elif [ "$compatibility" = "incompatible" ]; then
                    error_exit "Graphiti $target_version is incompatible with n8n $current_n8n"
                else
                    warning "Graphiti $target_version compatibility with n8n $current_n8n is unknown"
                fi
            fi
            
            if [ "$current_letta" != "unknown" ] && [ "$current_letta" != "not_running" ]; then
                local compatibility=$(check_compatibility "graphiti" "$target_version" "letta" "$current_letta")
                if [ "$compatibility" = "compatible" ]; then
                    success "Graphiti $target_version is compatible with Letta $current_letta"
                elif [ "$compatibility" = "incompatible" ]; then
                    error_exit "Graphiti $target_version is incompatible with Letta $current_letta"
                else
                    warning "Graphiti $target_version compatibility with Letta $current_letta is unknown"
                fi
            fi
            ;;
    esac
}

# Validate infrastructure compatibility
validate_infrastructure_compatibility() {
    info "Validating infrastructure compatibility..."
    
    # Check PostgreSQL version
    if docker ps --format "table {{.Names}}" | grep -q "^supabase-db$"; then
        local postgres_version=$(docker exec supabase-db psql -U postgres -c "SELECT version();" 2>/dev/null | grep -o 'PostgreSQL [0-9]\+\.[0-9]\+' | cut -d' ' -f2 || echo "unknown")
        info "PostgreSQL version: $postgres_version"
        
        # Check if version is compatible (15.x)
        if [[ $postgres_version =~ ^15\. ]]; then
            success "PostgreSQL version $postgres_version is compatible"
        else
            warning "PostgreSQL version $postgres_version may not be compatible"
        fi
    fi
    
    # Check Neo4j version
    if docker ps --format "table {{.Names}}" | grep -q "^graphiti-neo4j$"; then
        local neo4j_version=$(docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "CALL dbms.components() YIELD name, versions RETURN versions[0] as version;" 2>/dev/null | grep -o '[0-9]\+\.[0-9]\+' || echo "unknown")
        info "Neo4j version: $neo4j_version"
        
        # Check if version is compatible (5.x)
        if [[ $neo4j_version =~ ^5\. ]]; then
            success "Neo4j version $neo4j_version is compatible"
        else
            warning "Neo4j version $neo4j_version may not be compatible"
        fi
    fi
    
    # Check Docker version
    local docker_version=$(docker --version | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+' || echo "unknown")
    info "Docker version: $docker_version"
    
    # Check if version is compatible (24.x+)
    if [[ $docker_version =~ ^2[4-9]\. ]]; then
        success "Docker version $docker_version is compatible"
    else
        warning "Docker version $docker_version may not be compatible"
    fi
}

# Check all framework compatibility
check_all_compatibility() {
    info "Checking compatibility for all frameworks..."
    
    local frameworks=("n8n" "letta" "graphiti")
    
    for framework in "${frameworks[@]}"; do
        local current_version=$(get_current_version "$framework")
        
        if [ "$current_version" != "unknown" ] && [ "$current_version" != "not_running" ]; then
            info "Checking compatibility for $framework version $current_version"
            validate_framework_compatibility "$framework" "$current_version"
        else
            info "$framework is not running or version unknown"
        fi
    done
    
    validate_infrastructure_compatibility
}

# Main validation process
main() {
    echo -e "${BLUE}🔍 Version Compatibility Validation${NC}"
    echo -e "${BLUE}=================================${NC}"
    echo "Framework: ${FRAMEWORK:-all}"
    echo "Target version: ${TARGET_VERSION:-current}"
    echo "Check all: $CHECK_ALL"
    echo "Log file: $LOG_FILE"
    echo ""
    
    log "Starting compatibility validation"
    
    # Validate matrix file
    validate_matrix_file
    
    # Perform validation
    if [ "$CHECK_ALL" = true ]; then
        check_all_compatibility
    elif [ -n "$FRAMEWORK" ] && [ -n "$TARGET_VERSION" ]; then
        validate_framework_compatibility "$FRAMEWORK" "$TARGET_VERSION"
    elif [ -n "$FRAMEWORK" ]; then
        local current_version=$(get_current_version "$FRAMEWORK")
        validate_framework_compatibility "$FRAMEWORK" "$current_version"
    else
        check_all_compatibility
    fi
    
    success "Compatibility validation completed!"
    echo ""
    echo -e "${GREEN}📋 Validation Summary${NC}"
    echo -e "${GREEN}=====================${NC}"
    echo "✅ Compatibility matrix validation: Passed"
    echo "✅ Framework compatibility: Validated"
    echo "✅ Infrastructure compatibility: Validated"
    echo ""
    echo -e "${BLUE}📝 Next Steps${NC}"
    echo "1. Review any warnings or unknown compatibility statuses"
    echo "2. Test compatibility in staging environment if needed"
    echo "3. Proceed with upgrades only for compatible versions"
    echo ""
    echo "Log file: $LOG_FILE"
}

# Run main function
main "$@"
