#!/bin/bash

# MCP Server Integration and Letta Connectivity Validation
# This script runs comprehensive validation tests for all MCP servers and Letta integration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TIMEOUT=30
VERBOSE=false
QUICK=false
SKIP_HEALTH=false
SKIP_PROTOCOL=false
SKIP_LETTA=false

# Test results tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
SKIPPED_TESTS=0

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    local test_name=$3
    
    case $status in
        "PASS")
            echo -e "${GREEN}✓${NC} $test_name: $message"
            ((PASSED_TESTS++))
            ;;
        "FAIL")
            echo -e "${RED}✗${NC} $test_name: $message"
            ((FAILED_TESTS++))
            ;;
        "SKIP")
            echo -e "${YELLOW}⚠${NC} $test_name: $message"
            ((SKIPPED_TESTS++))
            ;;
        "INFO")
            echo -e "${BLUE}ℹ${NC} $message"
            ;;
        "ERROR")
            echo -e "${RED}✗${NC} $message"
            ;;
        "HEADER")
            echo -e "${PURPLE}▶${NC} $message"
            ;;
        "SUBTEST")
            echo -e "${CYAN}  →${NC} $message"
            ;;
    esac
    ((TOTAL_TESTS++))
}

# Function to run a test and capture results
run_test() {
    local test_name="$1"
    local test_command="$2"
    local expected_exit_code="${3:-0}"
    
    if [ "$VERBOSE" = true ]; then
        echo "Running: $test_command"
    fi
    
    if eval "$test_command" > /dev/null 2>&1; then
        local exit_code=$?
        if [ $exit_code -eq $expected_exit_code ]; then
            print_status "PASS" "Test completed successfully" "$test_name"
            return 0
        else
            print_status "FAIL" "Test failed with exit code $exit_code (expected $expected_exit_code)" "$test_name"
            return 1
        fi
    else
        local exit_code=$?
        if [ $exit_code -eq $expected_exit_code ]; then
            print_status "PASS" "Test completed as expected" "$test_name"
            return 0
        else
            print_status "FAIL" "Test failed with exit code $exit_code (expected $expected_exit_code)" "$test_name"
            return 1
        fi
    fi
}

# Function to check if a service is running
check_service_running() {
    local service_name="$1"
    local port="$2"
    
    if curl -s --max-time 5 "http://localhost:$port/health" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to wait for service to be ready
wait_for_service() {
    local service_name="$1"
    local port="$2"
    local max_attempts=30
    local attempt=1
    
    print_status "INFO" "Waiting for $service_name to be ready..."
    
    while [ $attempt -le $max_attempts ]; do
        if check_service_running "$service_name" "$port"; then
            print_status "PASS" "Service is ready" "$service_name"
            return 0
        fi
        
        if [ "$VERBOSE" = true ]; then
            echo "Attempt $attempt/$max_attempts: $service_name not ready yet..."
        fi
        
        sleep 2
        ((attempt++))
    done
    
    print_status "FAIL" "Service failed to start within timeout" "$service_name"
    return 1
}

# Function to test MCP server health
test_mcp_server_health() {
    local service_name="$1"
    local port="$2"
    local health_url="http://localhost:$port/health"
    
    print_status "HEADER" "Testing $service_name health endpoint"
    
    # Test health endpoint accessibility
    run_test "$service_name health accessibility" "curl -s --max-time $TIMEOUT '$health_url'"
    
    # Test health response format
    local health_response
    if health_response=$(curl -s --max-time $TIMEOUT "$health_url" 2>/dev/null); then
        if echo "$health_response" | grep -q '"status"'; then
            print_status "PASS" "Health response contains status field" "$service_name health format"
        else
            print_status "FAIL" "Health response missing status field" "$service_name health format"
        fi
        
        if echo "$health_response" | grep -q '"timestamp"'; then
            print_status "PASS" "Health response contains timestamp field" "$service_name health format"
        else
            print_status "FAIL" "Health response missing timestamp field" "$service_name health format"
        fi
    else
        print_status "FAIL" "Failed to get health response" "$service_name health format"
    fi
}

# Function to test MCP protocol
test_mcp_protocol() {
    local service_name="$1"
    local port="$2"
    local mcp_url="http://localhost:$port/mcp"
    
    print_status "HEADER" "Testing $service_name MCP protocol"
    
    # Test MCP endpoint accessibility
    run_test "$service_name MCP endpoint accessibility" "curl -s --max-time $TIMEOUT '$mcp_url'"
    
    # Test MCP initialization
    local init_request='{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}'
    local init_response
    if init_response=$(curl -s --max-time $TIMEOUT -X POST "$mcp_url" \
        -H "Content-Type: application/json" \
        -d "$init_request" 2>/dev/null); then
        
        if echo "$init_response" | grep -q '"jsonrpc"'; then
            print_status "PASS" "MCP initialization response is valid JSON-RPC" "$service_name MCP init"
        else
            print_status "FAIL" "MCP initialization response is not valid JSON-RPC" "$service_name MCP init"
        fi
    else
        print_status "FAIL" "Failed to get MCP initialization response" "$service_name MCP init"
    fi
    
    # Test tool discovery
    local tools_request='{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}'
    local tools_response
    if tools_response=$(curl -s --max-time $TIMEOUT -X POST "$mcp_url" \
        -H "Content-Type: application/json" \
        -d "$tools_request" 2>/dev/null); then
        
        if echo "$tools_response" | grep -q '"tools"'; then
            print_status "PASS" "MCP tools discovery response contains tools field" "$service_name MCP tools"
        else
            print_status "FAIL" "MCP tools discovery response missing tools field" "$service_name MCP tools"
        fi
    else
        print_status "FAIL" "Failed to get MCP tools discovery response" "$service_name MCP tools"
    fi
}

# Function to test Letta connectivity
test_letta_connectivity() {
    print_status "HEADER" "Testing Letta MCP connectivity"
    
    # Check if Letta is running
    if ! check_service_running "letta" "8283"; then
        print_status "SKIP" "Letta service not running, skipping connectivity tests" "Letta connectivity"
        return 0
    fi
    
    # Test Letta MCP configuration
    local letta_config_file="$PROJECT_ROOT/letta/letta_mcp_config.json"
    if [ -f "$letta_config_file" ]; then
        print_status "PASS" "Letta MCP configuration file exists" "Letta config file"
        
        # Validate JSON format
        if jq empty "$letta_config_file" 2>/dev/null; then
            print_status "PASS" "Letta MCP configuration is valid JSON" "Letta config format"
        else
            print_status "FAIL" "Letta MCP configuration is not valid JSON" "Letta config format"
        fi
    else
        print_status "FAIL" "Letta MCP configuration file not found" "Letta config file"
    fi
    
    # Test Letta MCP server discovery
    local letta_mcp_url="http://localhost:8283/v1/tools/mcp/servers"
    if curl -s --max-time $TIMEOUT "$letta_mcp_url" > /dev/null 2>&1; then
        print_status "PASS" "Letta MCP server discovery endpoint accessible" "Letta MCP discovery"
    else
        print_status "FAIL" "Letta MCP server discovery endpoint not accessible" "Letta MCP discovery"
    fi
}

# Function to test health monitor
test_health_monitor() {
    print_status "HEADER" "Testing health monitor service"
    
    # Test health monitor health endpoint
    test_mcp_server_health "health-monitor" "8083"
    
    # Test health monitor API endpoints
    local api_endpoints=(
        "overall:http://localhost:8083/api/health/overall"
        "services:http://localhost:8083/api/services"
        "alerts:http://localhost:8083/api/alerts"
    )
    
    for endpoint in "${api_endpoints[@]}"; do
        local name=$(echo "$endpoint" | cut -d: -f1)
        local url=$(echo "$endpoint" | cut -d: -f2-)
        
        run_test "health-monitor $name API" "curl -s --max-time $TIMEOUT '$url'"
    done
    
    # Test monitoring dashboard
    run_test "health-monitor dashboard" "curl -s --max-time $TIMEOUT 'http://localhost:8083/dashboard'"
}

# Function to run comprehensive validation
run_comprehensive_validation() {
    print_status "INFO" "Starting comprehensive MCP server validation"
    echo
    
    # Test individual MCP servers
    if [ "$SKIP_HEALTH" = false ]; then
        print_status "HEADER" "Phase 1: MCP Server Health Validation"
        
        test_mcp_server_health "gmail-mcp-server" "8080"
        test_mcp_server_health "graphiti-mcp-server" "8082"
        test_mcp_server_health "rag-mcp-server" "8082"
        test_health_monitor
        
        echo
    fi
    
    # Test MCP protocol
    if [ "$SKIP_PROTOCOL" = false ]; then
        print_status "HEADER" "Phase 2: MCP Protocol Validation"
        
        test_mcp_protocol "gmail-mcp-server" "8080"
        test_mcp_protocol "graphiti-mcp-server" "8082"
        test_mcp_protocol "rag-mcp-server" "8082"
        
        echo
    fi
    
    # Test Letta connectivity
    if [ "$SKIP_LETTA" = false ]; then
        print_status "HEADER" "Phase 3: Letta Integration Testing"
        
        test_letta_connectivity
        
        echo
    fi
    
    # Test end-to-end functionality
    print_status "HEADER" "Phase 4: End-to-End Integration Testing"
    
    # Test health check script
    if [ -f "$SCRIPT_DIR/health-check-all.sh" ]; then
        run_test "health check script" "$SCRIPT_DIR/health-check-all.sh --individual"
    else
        print_status "SKIP" "Health check script not found" "health check script"
    fi
    
    # Test MCP validation scripts
    if [ -f "$SCRIPT_DIR/validate-mcp-health.sh" ]; then
        run_test "MCP health validation script" "$SCRIPT_DIR/validate-mcp-health.sh"
    else
        print_status "SKIP" "MCP health validation script not found" "MCP health validation script"
    fi
    
    if [ -f "$SCRIPT_DIR/validate-mcp-protocol.sh" ]; then
        run_test "MCP protocol validation script" "$SCRIPT_DIR/validate-mcp-protocol.sh"
    else
        print_status "SKIP" "MCP protocol validation script not found" "MCP protocol validation script"
    fi
    
    if [ -f "$SCRIPT_DIR/validate-letta-mcp-connection.sh" ]; then
        run_test "Letta MCP connection validation script" "$SCRIPT_DIR/validate-letta-mcp-connection.sh"
    else
        print_status "SKIP" "Letta MCP connection validation script not found" "Letta MCP connection validation script"
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -v, --verbose           Enable verbose output"
    echo "  -q, --quick             Run quick validation (skip some tests)"
    echo "  --skip-health           Skip health validation tests"
    echo "  --skip-protocol         Skip MCP protocol validation tests"
    echo "  --skip-letta            Skip Letta connectivity tests"
    echo "  -t, --timeout SECONDS   Set timeout for requests (default: 30)"
    echo
    echo "Examples:"
    echo "  $0                      # Run all validation tests"
    echo "  $0 -v                   # Run with verbose output"
    echo "  $0 -q                   # Run quick validation"
    echo "  $0 --skip-letta         # Skip Letta connectivity tests"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -q|--quick)
            QUICK=true
            shift
            ;;
        --skip-health)
            SKIP_HEALTH=true
            shift
            ;;
        --skip-protocol)
            SKIP_PROTOCOL=true
            shift
            ;;
        --skip-letta)
            SKIP_LETTA=true
            shift
            ;;
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
echo "MCP Server Integration and Letta Connectivity Validation"
echo "========================================================"
echo

# Check if curl is available
if ! command -v curl > /dev/null 2>&1; then
    print_status "ERROR" "curl is required but not installed"
    exit 1
fi

# Check if jq is available
if ! command -v jq > /dev/null 2>&1; then
    print_status "INFO" "jq not available, some JSON validation will be skipped"
fi

# Run comprehensive validation
run_comprehensive_validation

# Print summary
echo
echo "Validation Summary"
echo "=================="
echo "Total Tests: $TOTAL_TESTS"
echo "Passed: $PASSED_TESTS"
echo "Failed: $FAILED_TESTS"
echo "Skipped: $SKIPPED_TESTS"
echo

if [ $FAILED_TESTS -eq 0 ]; then
    print_status "PASS" "All tests passed successfully!"
    exit 0
else
    print_status "FAIL" "$FAILED_TESTS test(s) failed"
    exit 1
fi