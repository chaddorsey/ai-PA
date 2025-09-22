#!/bin/bash
set -e

# Workflow Testing Script
# This script tests critical workflows in the PA ecosystem

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$PROJECT_ROOT/logs/testing"

# Create necessary directories
mkdir -p "$LOGS_DIR"

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOGS_DIR/workflow-test-$(date +%Y%m%d).log"
}

# Success logging
log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] SUCCESS:${NC} $1" | tee -a "$LOGS_DIR/workflow-test-$(date +%Y%m%d).log"
}

# Error logging
log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOGS_DIR/workflow-test-$(date +%Y%m%d).log"
}

# Warning logging
log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOGS_DIR/workflow-test-$(date +%Y%m%d).log"
}

# Test result tracking
TEST_RESULTS=()
TOTAL_TESTS=0
FAILED_TESTS=0

# Add test result
add_result() {
    local test_name="$1"
    local status="$2"
    local message="$3"
    
    TEST_RESULTS+=("$test_name:$status:$message")
    ((TOTAL_TESTS++))
    
    if [[ "$status" == "FAIL" ]]; then
        ((FAILED_TESTS++))
    fi
}

# Test HTTP endpoint
test_http_endpoint() {
    local url="$1"
    local expected_status="$2"
    local test_name="$3"
    
    log "Testing HTTP endpoint: $url"
    
    local response_code=$(curl -s -o /dev/null -w "%{http_code}" "$url" || echo "000")
    
    if [[ "$response_code" == "$expected_status" ]]; then
        log_success "HTTP test passed: $url (status: $response_code)"
        add_result "$test_name" "PASS" "HTTP endpoint returned expected status: $response_code"
    else
        log_error "HTTP test failed: $url (expected: $expected_status, got: $response_code)"
        add_result "$test_name" "FAIL" "HTTP endpoint returned unexpected status: $response_code"
    fi
}

# Test database connectivity
test_database_connectivity() {
    local compose_file="$1"
    local test_name="database-connectivity"
    
    log "Testing database connectivity..."
    
    local container_name=$(docker-compose -f "$compose_file" ps -q supabase-db)
    
    if [[ -z "$container_name" ]]; then
        log_error "Database container not found"
        add_result "$test_name" "FAIL" "Database container not found"
        return 1
    fi
    
    # Test basic connectivity
    if docker exec "$container_name" pg_isready -U postgres > /dev/null 2>&1; then
        log_success "Database connectivity test passed"
        add_result "$test_name" "PASS" "Database is accepting connections"
    else
        log_error "Database connectivity test failed"
        add_result "$test_name" "FAIL" "Database is not accepting connections"
        return 1
    fi
    
    # Test database queries
    local query_result=$(docker exec "$container_name" psql -U postgres -d postgres -t -c "SELECT 1;" 2>/dev/null | tr -d ' ')
    
    if [[ "$query_result" == "1" ]]; then
        log_success "Database query test passed"
        add_result "$test_name" "PASS" "Database queries are working"
    else
        log_error "Database query test failed"
        add_result "$test_name" "FAIL" "Database queries are not working"
    fi
}

# Test Letta API
test_letta_api() {
    local base_url="$1"
    local test_name="letta-api"
    
    log "Testing Letta API..."
    
    # Test health endpoint
    test_http_endpoint "$base_url/v1/health/" "200" "letta-health"
    
    # Test API endpoints
    test_http_endpoint "$base_url/v1/agents" "200" "letta-agents"
    test_http_endpoint "$base_url/v1/memory" "200" "letta-memory"
    
    # Test if Letta can process a simple request
    local response=$(curl -s -X POST "$base_url/v1/chat" \
        -H "Content-Type: application/json" \
        -d '{"message": "Hello", "agent_id": "test"}' 2>/dev/null || echo "ERROR")
    
    if [[ "$response" != "ERROR" ]]; then
        log_success "Letta API test passed"
        add_result "$test_name" "PASS" "Letta API is responding to requests"
    else
        log_error "Letta API test failed"
        add_result "$test_name" "FAIL" "Letta API is not responding to requests"
    fi
}

# Test Open WebUI
test_open_webui() {
    local base_url="$1"
    local test_name="open-webui"
    
    log "Testing Open WebUI..."
    
    # Test health endpoint
    test_http_endpoint "$base_url/health" "200" "open-webui-health"
    
    # Test main page
    test_http_endpoint "$base_url/" "200" "open-webui-main"
    
    # Test API endpoints
    test_http_endpoint "$base_url/api/v1/health" "200" "open-webui-api"
}

# Test n8n
test_n8n() {
    local base_url="$1"
    local test_name="n8n"
    
    log "Testing n8n..."
    
    # Test health endpoint
    test_http_endpoint "$base_url/healthz" "200" "n8n-health"
    
    # Test main page
    test_http_endpoint "$base_url/" "200" "n8n-main"
    
    # Test API endpoints
    test_http_endpoint "$base_url/api/v1/health" "200" "n8n-api"
}

# Test MCP servers
test_mcp_servers() {
    local compose_file="$1"
    local test_name="mcp-servers"
    
    log "Testing MCP servers..."
    
    # Test Graphiti MCP server
    local graphiti_container=$(docker-compose -f "$compose_file" ps -q graphiti-mcp-server)
    if [[ -n "$graphiti_container" ]]; then
        test_http_endpoint "http://localhost:8082/health" "200" "graphiti-mcp-health"
    else
        log_warning "Graphiti MCP server not found"
        add_result "$test_name" "WARN" "Graphiti MCP server not found"
    fi
    
    # Test RAG MCP server
    local rag_container=$(docker-compose -f "$compose_file" ps -q rag-mcp-server)
    if [[ -n "$rag_container" ]]; then
        test_http_endpoint "http://localhost:8082/health" "200" "rag-mcp-health"
    else
        log_warning "RAG MCP server not found"
        add_result "$test_name" "WARN" "RAG MCP server not found"
    fi
    
    # Test Gmail MCP server
    local gmail_container=$(docker-compose -f "$compose_file" ps -q gmail-mcp-server)
    if [[ -n "$gmail_container" ]]; then
        test_http_endpoint "http://localhost:8080/health" "200" "gmail-mcp-health"
    else
        log_warning "Gmail MCP server not found"
        add_result "$test_name" "WARN" "Gmail MCP server not found"
    fi
}

# Test Slackbot
test_slackbot() {
    local base_url="$1"
    local test_name="slackbot"
    
    log "Testing Slackbot..."
    
    # Test health endpoint
    test_http_endpoint "$base_url/health" "200" "slackbot-health"
    
    # Test if Slackbot is responding
    local response=$(curl -s "$base_url/health" 2>/dev/null || echo "ERROR")
    
    if [[ "$response" != "ERROR" ]]; then
        log_success "Slackbot test passed"
        add_result "$test_name" "PASS" "Slackbot is responding"
    else
        log_error "Slackbot test failed"
        add_result "$test_name" "FAIL" "Slackbot is not responding"
    fi
}

# Test end-to-end workflow
test_end_to_end_workflow() {
    local compose_file="$1"
    local test_name="end-to-end-workflow"
    
    log "Testing end-to-end workflow..."
    
    # Test if all services can communicate
    local services=("supabase-db" "n8n" "letta" "open-webui")
    local all_healthy=true
    
    for service in "${services[@]}"; do
        local container_name=$(docker-compose -f "$compose_file" ps -q "$service")
        
        if [[ -n "$container_name" ]]; then
            local status=$(docker-compose -f "$compose_file" ps --format json | jq -r ".[] | select(.Name == \"$service\") | .State")
            
            if [[ "$status" != "running" ]]; then
                log_error "Service $service is not running (status: $status)"
                all_healthy=false
            fi
        else
            log_error "Service $service container not found"
            all_healthy=false
        fi
    done
    
    if [[ "$all_healthy" == "true" ]]; then
        log_success "End-to-end workflow test passed"
        add_result "$test_name" "PASS" "All services are running and healthy"
    else
        log_error "End-to-end workflow test failed"
        add_result "$test_name" "FAIL" "Some services are not running or healthy"
    fi
}

# Test performance
test_performance() {
    local compose_file="$1"
    local test_name="performance"
    
    log "Testing performance..."
    
    # Check memory usage
    local memory_usage=$(docker stats --no-stream --format "table {{.MemUsage}}" | tail -n +2 | awk '{sum += $1} END {print sum}')
    log "Total memory usage: $memory_usage"
    
    # Check CPU usage
    local cpu_usage=$(docker stats --no-stream --format "table {{.CPUPerc}}" | tail -n +2 | awk '{sum += $1} END {print sum}')
    log "Total CPU usage: $cpu_usage%"
    
    # Check response times
    local start_time=$(date +%s%N)
    test_http_endpoint "http://localhost:8283/v1/health/" "200" "letta-response-time"
    local end_time=$(date +%s%N)
    local response_time=$(( (end_time - start_time) / 1000000 ))
    
    log "Letta response time: ${response_time}ms"
    
    if [[ $response_time -lt 1000 ]]; then
        log_success "Performance test passed"
        add_result "$test_name" "PASS" "Response time is acceptable: ${response_time}ms"
    else
        log_warning "Performance test warning: response time is slow: ${response_time}ms"
        add_result "$test_name" "WARN" "Response time is slow: ${response_time}ms"
    fi
}

# Generate test report
generate_report() {
    log "Generating workflow test report..."
    
    local report_file="$LOGS_DIR/workflow-test-report-$(date +%Y%m%d-%H%M%S).txt"
    
    {
        echo "PA Ecosystem Workflow Test Report"
        echo "Generated: $(date)"
        echo "Environment: $ENVIRONMENT"
        echo "Total Tests: $TOTAL_TESTS"
        echo "Failed Tests: $FAILED_TESTS"
        echo "Success Rate: $(( (TOTAL_TESTS - FAILED_TESTS) * 100 / TOTAL_TESTS ))%"
        echo ""
        echo "Detailed Results:"
        echo "=================="
        
        for result in "${TEST_RESULTS[@]}"; do
            IFS=':' read -r test_name status message <<< "$result"
            echo "$test_name: $status - $message"
        done
    } > "$report_file"
    
    log_success "Workflow test report generated: $report_file"
    
    # Display summary
    echo ""
    echo "Workflow Test Summary:"
    echo "====================="
    echo "Total Tests: $TOTAL_TESTS"
    echo "Failed Tests: $FAILED_TESTS"
    echo "Success Rate: $(( (TOTAL_TESTS - FAILED_TESTS) * 100 / TOTAL_TESTS ))%"
    echo ""
    
    if [[ $FAILED_TESTS -eq 0 ]]; then
        log_success "All workflow tests passed!"
        return 0
    else
        log_error "$FAILED_TESTS workflow tests failed"
        return 1
    fi
}

# Main execution
main() {
    local environment="production"
    local compose_file="docker-compose.yml"
    local base_url="http://localhost"
    
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
            --base-url)
                base_url="$2"
                shift 2
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
    
    log "Starting workflow tests for $environment environment..."
    log "Using compose file: $compose_file"
    log "Base URL: $base_url"
    
    # Change to project root
    cd "$PROJECT_ROOT"
    
    # Run workflow tests
    test_database_connectivity "$compose_file"
    test_letta_api "$base_url:8283"
    test_open_webui "$base_url:8080"
    test_n8n "$base_url:5678"
    test_mcp_servers "$compose_file"
    test_slackbot "$base_url:8081"
    test_end_to_end_workflow "$compose_file"
    test_performance "$compose_file"
    
    # Generate report
    generate_report
}

# Help function
show_help() {
    echo "Workflow Testing Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --environment <env>  Specify environment (production|staging)"
    echo "  --staging           Test staging environment"
    echo "  --production        Test production environment (default)"
    echo "  --base-url <url>    Specify base URL for testing (default: http://localhost)"
    echo "  -h, --help          Show this help message"
    echo ""
    echo "This script tests critical workflows in the PA ecosystem."
}

# Run main function
main "$@"
