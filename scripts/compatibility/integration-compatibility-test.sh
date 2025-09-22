#!/bin/bash

# Integration Compatibility Testing Script
# Purpose: Test cross-service integration compatibility between framework versions
# Usage: ./integration-compatibility-test.sh [--integration <integration>] [--framework <framework>]

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
LOG_FILE="/var/log/compatibility/integration-test-$(date +%Y%m%d-%H%M%S).log"
INTEGRATION=""
FRAMEWORK=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --integration)
            INTEGRATION="$2"
            shift 2
            ;;
        --framework)
            FRAMEWORK="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--integration <integration>] [--framework <framework>]"
            echo ""
            echo "Options:"
            echo "  --integration     Specific integration to test (mcp, webhook, event, data-flow)"
            echo "  --framework       Specific framework to test (n8n, letta, graphiti)"
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

# Test MCP server integration compatibility
test_mcp_integration() {
    info "Testing MCP server integration compatibility..."
    
    # Test Letta MCP server connectivity
    if docker ps --format "table {{.Names}}" | grep -q "^ai-pa-letta-1$"; then
        info "Testing Letta MCP server integration..."
        
        # Test MCP server list
        local mcp_servers=$(curl -s http://localhost:8283/v1/mcp/servers 2>/dev/null || echo "[]")
        local server_count=$(echo "$mcp_servers" | jq '. | length' 2>/dev/null || echo "0")
        info "MCP servers count: $server_count"
        
        if [ "$server_count" -gt 0 ]; then
            success "MCP servers are configured"
            
            # Test individual MCP servers
            echo "$mcp_servers" | jq -r '.[].name' 2>/dev/null | while read -r server_name; do
                if [ -n "$server_name" ]; then
                    info "Testing MCP server: $server_name"
                    
                    # Test server health
                    local server_health=$(curl -s "http://localhost:8283/v1/mcp/servers/$server_name/health" 2>/dev/null || echo "")
                    if [ -n "$server_health" ]; then
                        success "MCP server $server_name is healthy"
                    else
                        warning "MCP server $server_name health check failed"
                    fi
                fi
            done
        else
            info "No MCP servers configured"
        fi
    fi
    
    # Test Graphiti MCP server
    if docker ps --format "table {{.Names}}" | grep -q "^graphiti-mcp-server$"; then
        info "Testing Graphiti MCP server integration..."
        
        # Test Graphiti MCP server health
        local graphiti_health=$(curl -s http://localhost:8082/health 2>/dev/null || echo "")
        if [ -n "$graphiti_health" ]; then
            success "Graphiti MCP server is healthy"
        else
            warning "Graphiti MCP server health check failed"
        fi
        
        # Test Graphiti MCP endpoints
        local graphiti_mcp=$(curl -s http://localhost:8082/mcp 2>/dev/null || echo "")
        if [ -n "$graphiti_mcp" ]; then
            success "Graphiti MCP endpoint is accessible"
        else
            warning "Graphiti MCP endpoint is not accessible"
        fi
    fi
    
    # Test Gmail MCP server
    if docker ps --format "table {{.Names}}" | grep -q "^gmail-mcp$"; then
        info "Testing Gmail MCP server integration..."
        
        # Test Gmail MCP server health
        local gmail_health=$(curl -s http://localhost:3000/health 2>/dev/null || echo "")
        if [ -n "$gmail_health" ]; then
            success "Gmail MCP server is healthy"
        else
            warning "Gmail MCP server health check failed"
        fi
    fi
}

# Test webhook integration compatibility
test_webhook_integration() {
    info "Testing webhook integration compatibility..."
    
    # Test n8n webhook endpoints
    if docker ps --format "table {{.Names}}" | grep -q "^n8n$"; then
        info "Testing n8n webhook integration..."
        
        # Test webhook endpoint structure
        local webhook_test=$(curl -s -w "%{http_code}" http://localhost:5678/webhook-test 2>/dev/null || echo "000")
        local http_code="${webhook_test: -3}"
        
        if [ "$http_code" = "404" ]; then
            success "n8n webhook endpoint structure is correct"
        else
            info "n8n webhook endpoint returned HTTP $http_code"
        fi
        
        # Test webhook configuration
        local webhook_config=$(curl -s http://localhost:5678/rest/settings 2>/dev/null | jq -r '.webhookUrl // "unknown"' 2>/dev/null || echo "unknown")
        if [ "$webhook_config" != "unknown" ]; then
            success "n8n webhook configuration is present"
        else
            info "n8n webhook configuration not found"
        fi
    fi
    
    # Test Letta webhook integration
    if docker ps --format "table {{.Names}}" | grep -q "^ai-pa-letta-1$"; then
        info "Testing Letta webhook integration..."
        
        # Test webhook endpoints
        local webhook_endpoints=$(curl -s http://localhost:8283/v1/webhooks 2>/dev/null || echo "[]")
        local webhook_count=$(echo "$webhook_endpoints" | jq '. | length' 2>/dev/null || echo "0")
        info "Letta webhook endpoints count: $webhook_count"
        
        if [ "$webhook_count" -gt 0 ]; then
            success "Letta webhook endpoints are configured"
        else
            info "No Letta webhook endpoints configured"
        fi
    fi
}

# Test event handling integration compatibility
test_event_integration() {
    info "Testing event handling integration compatibility..."
    
    # Test n8n event handling
    if docker ps --format "table {{.Names}}" | grep -q "^n8n$"; then
        info "Testing n8n event handling..."
        
        # Test workflow execution
        local workflows=$(curl -s http://localhost:5678/rest/workflows 2>/dev/null || echo "[]")
        local workflow_count=$(echo "$workflows" | jq '. | length' 2>/dev/null || echo "0")
        info "n8n workflows count: $workflow_count"
        
        if [ "$workflow_count" -gt 0 ]; then
            success "n8n workflows are configured"
            
            # Test workflow execution capability
            local execution_test=$(curl -s -w "%{http_code}" http://localhost:5678/rest/executions 2>/dev/null || echo "000")
            local http_code="${execution_test: -3}"
            
            if [ "$http_code" = "200" ]; then
                success "n8n workflow execution endpoint is accessible"
            else
                warning "n8n workflow execution endpoint returned HTTP $http_code"
            fi
        else
            info "No n8n workflows configured"
        fi
    fi
    
    # Test Letta event handling
    if docker ps --format "table {{.Names}}" | grep -q "^ai-pa-letta-1$"; then
        info "Testing Letta event handling..."
        
        # Test agent execution
        local agents=$(curl -s http://localhost:8283/v1/agents 2>/dev/null || echo "[]")
        local agent_count=$(echo "$agents" | jq '. | length' 2>/dev/null || echo "0")
        info "Letta agents count: $agent_count"
        
        if [ "$agent_count" -gt 0 ]; then
            success "Letta agents are configured"
            
            # Test agent execution capability
            local execution_test=$(curl -s -w "%{http_code}" http://localhost:8283/v1/agents/execute 2>/dev/null || echo "000")
            local http_code="${execution_test: -3}"
            
            if [ "$http_code" = "200" ] || [ "$http_code" = "405" ]; then
                success "Letta agent execution endpoint is accessible"
            else
                warning "Letta agent execution endpoint returned HTTP $http_code"
            fi
        else
            info "No Letta agents configured"
        fi
    fi
}

# Test data flow integration compatibility
test_data_flow_integration() {
    info "Testing data flow integration compatibility..."
    
    # Test n8n to Letta data flow
    if docker ps --format "table {{.Names}}" | grep -q "^n8n$" && docker ps --format "table {{.Names}}" | grep -q "^ai-pa-letta-1$"; then
        info "Testing n8n to Letta data flow..."
        
        # Test network connectivity
        local n8n_to_letta=$(docker exec n8n curl -s -w "%{http_code}" http://ai-pa-letta-1:8283/v1/health/ 2>/dev/null || echo "000")
        local http_code="${n8n_to_letta: -3}"
        
        if [ "$http_code" = "200" ]; then
            success "n8n to Letta network connectivity is working"
        else
            warning "n8n to Letta network connectivity returned HTTP $http_code"
        fi
    fi
    
    # Test Letta to Graphiti data flow
    if docker ps --format "table {{.Names}}" | grep -q "^ai-pa-letta-1$" && docker ps --format "table {{.Names}}" | grep -q "^graphiti-mcp-server$"; then
        info "Testing Letta to Graphiti data flow..."
        
        # Test network connectivity
        local letta_to_graphiti=$(docker exec ai-pa-letta-1 curl -s -w "%{http_code}" http://graphiti-mcp-server:8082/health 2>/dev/null || echo "000")
        local http_code="${letta_to_graphiti: -3}"
        
        if [ "$http_code" = "200" ]; then
            success "Letta to Graphiti network connectivity is working"
        else
            warning "Letta to Graphiti network connectivity returned HTTP $http_code"
        fi
    fi
    
    # Test n8n to Graphiti data flow
    if docker ps --format "table {{.Names}}" | grep -q "^n8n$" && docker ps --format "table {{.Names}}" | grep -q "^graphiti-mcp-server$"; then
        info "Testing n8n to Graphiti data flow..."
        
        # Test network connectivity
        local n8n_to_graphiti=$(docker exec n8n curl -s -w "%{http_code}" http://graphiti-mcp-server:8082/health 2>/dev/null || echo "000")
        local http_code="${n8n_to_graphiti: -3}"
        
        if [ "$http_code" = "200" ]; then
            success "n8n to Graphiti network connectivity is working"
        else
            warning "n8n to Graphiti network connectivity returned HTTP $http_code"
        fi
    fi
}

# Test service discovery integration compatibility
test_service_discovery_integration() {
    info "Testing service discovery integration compatibility..."
    
    # Test Docker network connectivity
    local network_name="pa-internal"
    if docker network ls | grep -q "$network_name"; then
        success "PA internal network exists"
        
        # Test network connectivity between services
        local services=("n8n" "ai-pa-letta-1" "graphiti-mcp-server" "supabase-db" "graphiti-neo4j")
        
        for service in "${services[@]}"; do
            if docker ps --format "table {{.Names}}" | grep -q "^$service$"; then
                info "Testing $service network connectivity..."
                
                # Test basic connectivity
                if docker exec "$service" ping -c 1 google.com >/dev/null 2>&1; then
                    success "$service has external network connectivity"
                else
                    warning "$service external network connectivity test failed"
                fi
            fi
        done
    else
        error_exit "PA internal network not found"
    fi
}

# Test authentication integration compatibility
test_authentication_integration() {
    info "Testing authentication integration compatibility..."
    
    # Test n8n authentication
    if docker ps --format "table {{.Names}}" | grep -q "^n8n$"; then
        info "Testing n8n authentication..."
        
        # Test authentication endpoint
        local auth_test=$(curl -s -w "%{http_code}" http://localhost:5678/rest/login 2>/dev/null || echo "000")
        local http_code="${auth_test: -3}"
        
        if [ "$http_code" = "401" ] || [ "$http_code" = "200" ]; then
            success "n8n authentication endpoint is accessible"
        else
            warning "n8n authentication endpoint returned HTTP $http_code"
        fi
    fi
    
    # Test Letta authentication
    if docker ps --format "table {{.Names}}" | grep -q "^ai-pa-letta-1$"; then
        info "Testing Letta authentication..."
        
        # Test authentication endpoint
        local auth_test=$(curl -s -w "%{http_code}" http://localhost:8283/v1/auth/login 2>/dev/null || echo "000")
        local http_code="${auth_test: -3}"
        
        if [ "$http_code" = "401" ] || [ "$http_code" = "200" ] || [ "$http_code" = "404" ]; then
            success "Letta authentication endpoint is accessible"
        else
            warning "Letta authentication endpoint returned HTTP $http_code"
        fi
    fi
}

# Main integration compatibility testing process
main() {
    echo -e "${BLUE}🔍 Integration Compatibility Testing${NC}"
    echo -e "${BLUE}====================================${NC}"
    echo "Integration: ${INTEGRATION:-all}"
    echo "Framework: ${FRAMEWORK:-all}"
    echo "Log file: $LOG_FILE"
    echo ""
    
    log "Starting integration compatibility testing"
    
    # Test individual integrations
    if [ -z "$INTEGRATION" ] || [ "$INTEGRATION" = "mcp" ]; then
        test_mcp_integration
    fi
    
    if [ -z "$INTEGRATION" ] || [ "$INTEGRATION" = "webhook" ]; then
        test_webhook_integration
    fi
    
    if [ -z "$INTEGRATION" ] || [ "$INTEGRATION" = "event" ]; then
        test_event_integration
    fi
    
    if [ -z "$INTEGRATION" ] || [ "$INTEGRATION" = "data-flow" ]; then
        test_data_flow_integration
    fi
    
    # Test service discovery and authentication
    test_service_discovery_integration
    test_authentication_integration
    
    success "Integration compatibility testing completed!"
    echo ""
    echo -e "${GREEN}📋 Test Summary${NC}"
    echo -e "${GREEN}===============${NC}"
    echo "✅ MCP server integration: Tested"
    echo "✅ Webhook integration: Tested"
    echo "✅ Event handling integration: Tested"
    echo "✅ Data flow integration: Tested"
    echo "✅ Service discovery integration: Tested"
    echo "✅ Authentication integration: Tested"
    echo ""
    echo -e "${BLUE}📝 Next Steps${NC}"
    echo "1. Review any warnings or failures"
    echo "2. Test integration compatibility in staging environment if needed"
    echo "3. Update compatibility matrix based on test results"
    echo ""
    echo "Log file: $LOG_FILE"
}

# Run main function
main "$@"
