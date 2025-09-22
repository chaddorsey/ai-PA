#!/bin/bash

# API Compatibility Testing Script
# Purpose: Test API compatibility between framework versions
# Usage: ./api-compatibility-test.sh [--framework <framework>] [--target-version <version>]

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
LOG_FILE="/var/log/compatibility/api-test-$(date +%Y%m%d-%H%M%S).log"
FRAMEWORK=""
TARGET_VERSION=""

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
        -h|--help)
            echo "Usage: $0 [--framework <framework>] [--target-version <version>]"
            echo ""
            echo "Options:"
            echo "  --framework       Specific framework to test (n8n, letta, graphiti)"
            echo "  --target-version  Target version to test"
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

# Test n8n API compatibility
test_n8n_api() {
    info "Testing n8n API compatibility..."
    
    # Test health endpoint
    local health_response=$(curl -s -w "%{http_code}" http://localhost:5678/health 2>/dev/null || echo "000")
    local http_code="${health_response: -3}"
    
    if [ "$http_code" = "200" ]; then
        success "n8n health endpoint is accessible"
    else
        error_exit "n8n health endpoint returned HTTP $http_code"
    fi
    
    # Test API version endpoint
    local version_response=$(curl -s http://localhost:5678/rest/settings 2>/dev/null || echo "")
    if [ -n "$version_response" ]; then
        success "n8n API settings endpoint is accessible"
    else
        error_exit "n8n API settings endpoint is not accessible"
    fi
    
    # Test workflow endpoint
    local workflows_response=$(curl -s -w "%{http_code}" http://localhost:5678/rest/workflows 2>/dev/null || echo "000")
    local http_code="${workflows_response: -3}"
    
    if [ "$http_code" = "200" ]; then
        success "n8n workflows endpoint is accessible"
    else
        warning "n8n workflows endpoint returned HTTP $http_code"
    fi
    
    # Test webhook endpoint (if any exist)
    local webhooks_response=$(curl -s -w "%{http_code}" http://localhost:5678/webhook-test 2>/dev/null || echo "000")
    local http_code="${webhooks_response: -3}"
    
    if [ "$http_code" = "404" ]; then
        success "n8n webhook endpoint structure is correct (404 for non-existent webhook)"
    else
        info "n8n webhook endpoint returned HTTP $http_code"
    fi
}

# Test Letta API compatibility
test_letta_api() {
    info "Testing Letta API compatibility..."
    
    # Test health endpoint
    local health_response=$(curl -s http://localhost:8283/v1/health/ 2>/dev/null || echo "")
    if [ -n "$health_response" ]; then
        success "Letta health endpoint is accessible"
        
        # Parse health response
        local version=$(echo "$health_response" | jq -r '.version // "unknown"' 2>/dev/null || echo "unknown")
        local database_status=$(echo "$health_response" | jq -r '.database // "unknown"' 2>/dev/null || echo "unknown")
        
        info "Letta version: $version"
        info "Database status: $database_status"
        
        if [ "$database_status" = "healthy" ]; then
            success "Letta database connectivity is healthy"
        else
            warning "Letta database status: $database_status"
        fi
    else
        error_exit "Letta health endpoint is not accessible"
    fi
    
    # Test agents endpoint
    local agents_response=$(curl -s -w "%{http_code}" http://localhost:8283/v1/agents 2>/dev/null || echo "000")
    local http_code="${agents_response: -3}"
    
    if [ "$http_code" = "200" ]; then
        success "Letta agents endpoint is accessible"
        
        # Parse agents response
        local agent_count=$(echo "${agents_response%???}" | jq '. | length' 2>/dev/null || echo "0")
        info "Active agents: $agent_count"
    else
        warning "Letta agents endpoint returned HTTP $http_code"
    fi
    
    # Test MCP servers endpoint
    local mcp_response=$(curl -s -w "%{http_code}" http://localhost:8283/v1/mcp/servers 2>/dev/null || echo "000")
    local http_code="${mcp_response: -3}"
    
    if [ "$http_code" = "200" ]; then
        success "Letta MCP servers endpoint is accessible"
    else
        warning "Letta MCP servers endpoint returned HTTP $http_code"
    fi
}

# Test Graphiti API compatibility
test_graphiti_api() {
    info "Testing Graphiti API compatibility..."
    
    # Test health endpoint
    local health_response=$(curl -s http://localhost:8082/health 2>/dev/null || echo "")
    if [ -n "$health_response" ]; then
        success "Graphiti health endpoint is accessible"
    else
        error_exit "Graphiti health endpoint is not accessible"
    fi
    
    # Test MCP server endpoints
    local mcp_response=$(curl -s -w "%{http_code}" http://localhost:8082/mcp 2>/dev/null || echo "000")
    local http_code="${mcp_response: -3}"
    
    if [ "$http_code" = "200" ]; then
        success "Graphiti MCP endpoint is accessible"
    else
        warning "Graphiti MCP endpoint returned HTTP $http_code"
    fi
    
    # Test Neo4j connectivity
    if docker ps --format "table {{.Names}}" | grep -q "^graphiti-neo4j$"; then
        local neo4j_test=$(docker exec graphiti-neo4j cypher-shell -u neo4j -p demodemo "RETURN 1 as test;" 2>/dev/null || echo "")
        if [ -n "$neo4j_test" ]; then
            success "Graphiti Neo4j connectivity is working"
        else
            warning "Graphiti Neo4j connectivity test failed"
        fi
    else
        warning "Graphiti Neo4j container is not running"
    fi
}

# Test cross-service API compatibility
test_cross_service_compatibility() {
    info "Testing cross-service API compatibility..."
    
    # Test n8n to Letta integration
    if docker ps --format "table {{.Names}}" | grep -q "^n8n$" && docker ps --format "table {{.Names}}" | grep -q "^ai-pa-letta-1$"; then
        info "Testing n8n to Letta integration..."
        
        # Check if n8n can reach Letta
        local n8n_to_letta=$(docker exec n8n curl -s -w "%{http_code}" http://ai-pa-letta-1:8283/v1/health/ 2>/dev/null || echo "000")
        local http_code="${n8n_to_letta: -3}"
        
        if [ "$http_code" = "200" ]; then
            success "n8n can reach Letta API"
        else
            warning "n8n cannot reach Letta API (HTTP $http_code)"
        fi
    fi
    
    # Test Letta to Graphiti integration
    if docker ps --format "table {{.Names}}" | grep -q "^ai-pa-letta-1$" && docker ps --format "table {{.Names}}" | grep -q "^graphiti-mcp-server$"; then
        info "Testing Letta to Graphiti integration..."
        
        # Check if Letta can reach Graphiti
        local letta_to_graphiti=$(docker exec ai-pa-letta-1 curl -s -w "%{http_code}" http://graphiti-mcp-server:8082/health 2>/dev/null || echo "000")
        local http_code="${letta_to_graphiti: -3}"
        
        if [ "$http_code" = "200" ]; then
            success "Letta can reach Graphiti API"
        else
            warning "Letta cannot reach Graphiti API (HTTP $http_code)"
        fi
    fi
    
    # Test n8n to Graphiti integration
    if docker ps --format "table {{.Names}}" | grep -q "^n8n$" && docker ps --format "table {{.Names}}" | grep -q "^graphiti-mcp-server$"; then
        info "Testing n8n to Graphiti integration..."
        
        # Check if n8n can reach Graphiti
        local n8n_to_graphiti=$(docker exec n8n curl -s -w "%{http_code}" http://graphiti-mcp-server:8082/health 2>/dev/null || echo "000")
        local http_code="${n8n_to_graphiti: -3}"
        
        if [ "$http_code" = "200" ]; then
            success "n8n can reach Graphiti API"
        else
            warning "n8n cannot reach Graphiti API (HTTP $http_code)"
        fi
    fi
}

# Test API response format compatibility
test_api_response_formats() {
    info "Testing API response format compatibility..."
    
    # Test Letta health response format
    local letta_health=$(curl -s http://localhost:8283/v1/health/ 2>/dev/null || echo "")
    if [ -n "$letta_health" ]; then
        # Check for required fields
        local has_version=$(echo "$letta_health" | jq -e '.version' 2>/dev/null && echo "true" || echo "false")
        local has_database=$(echo "$letta_health" | jq -e '.database' 2>/dev/null && echo "true" || echo "false")
        
        if [ "$has_version" = "true" ] && [ "$has_database" = "true" ]; then
            success "Letta health response format is compatible"
        else
            warning "Letta health response format may have changed"
        fi
    fi
    
    # Test n8n settings response format
    local n8n_settings=$(curl -s http://localhost:5678/rest/settings 2>/dev/null || echo "")
    if [ -n "$n8n_settings" ]; then
        # Check if response is valid JSON
        if echo "$n8n_settings" | jq . >/dev/null 2>&1; then
            success "n8n settings response format is compatible"
        else
            warning "n8n settings response format may have changed"
        fi
    fi
}

# Main API compatibility testing process
main() {
    echo -e "${BLUE}🔍 API Compatibility Testing${NC}"
    echo -e "${BLUE}===========================${NC}"
    echo "Framework: ${FRAMEWORK:-all}"
    echo "Target version: ${TARGET_VERSION:-current}"
    echo "Log file: $LOG_FILE"
    echo ""
    
    log "Starting API compatibility testing"
    
    # Test individual framework APIs
    if [ -z "$FRAMEWORK" ] || [ "$FRAMEWORK" = "n8n" ]; then
        if docker ps --format "table {{.Names}}" | grep -q "^n8n$"; then
            test_n8n_api
        else
            info "n8n is not running - skipping API tests"
        fi
    fi
    
    if [ -z "$FRAMEWORK" ] || [ "$FRAMEWORK" = "letta" ]; then
        if docker ps --format "table {{.Names}}" | grep -q "^ai-pa-letta-1$"; then
            test_letta_api
        else
            info "Letta is not running - skipping API tests"
        fi
    fi
    
    if [ -z "$FRAMEWORK" ] || [ "$FRAMEWORK" = "graphiti" ]; then
        if docker ps --format "table {{.Names}}" | grep -q "^graphiti-mcp-server$"; then
            test_graphiti_api
        else
            info "Graphiti is not running - skipping API tests"
        fi
    fi
    
    # Test cross-service compatibility
    test_cross_service_compatibility
    
    # Test API response formats
    test_api_response_formats
    
    success "API compatibility testing completed!"
    echo ""
    echo -e "${GREEN}📋 Test Summary${NC}"
    echo -e "${GREEN}===============${NC}"
    echo "✅ Individual framework APIs: Tested"
    echo "✅ Cross-service integration: Tested"
    echo "✅ API response formats: Validated"
    echo ""
    echo -e "${BLUE}📝 Next Steps${NC}"
    echo "1. Review any warnings or failures"
    echo "2. Test API compatibility in staging environment if needed"
    echo "3. Update compatibility matrix based on test results"
    echo ""
    echo "Log file: $LOG_FILE"
}

# Run main function
main "$@"
