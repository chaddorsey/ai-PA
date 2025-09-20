#!/bin/bash

# MCP Protocol Validation Script
# This script validates MCP protocol implementation across all MCP servers

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
TIMEOUT=10
VERBOSE=false

# MCP Server configurations
declare -A MCP_SERVERS=(
    ["gmail-mcp-server"]="8080"
    ["graphiti-mcp-server"]="8082"
    ["rag-mcp-server"]="8082"
)

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    local service=$3
    
    case $status in
        "PASS")
            echo -e "${GREEN}✓${NC} $service: $message"
            ;;
        "FAIL")
            echo -e "${RED}✗${NC} $service: $message"
            ;;
        "WARN")
            echo -e "${YELLOW}⚠${NC} $service: $message"
            ;;
        "INFO")
            echo -e "${BLUE}ℹ${NC} $message"
            ;;
        "ERROR")
            echo -e "${RED}✗${NC} $message"
            ;;
    esac
}

# Function to validate JSON-RPC response
validate_jsonrpc_response() {
    local service_name="$1"
    local response="$2"
    local expected_id="$3"
    
    # Check if response is valid JSON
    if ! echo "$response" | jq empty 2>/dev/null; then
        print_status "FAIL" "Response is not valid JSON" "$service_name"
        return 1
    fi
    
    # Check JSON-RPC version
    local jsonrpc=$(echo "$response" | jq -r '.jsonrpc // ""' 2>/dev/null)
    if [ "$jsonrpc" = "2.0" ]; then
        print_status "PASS" "JSON-RPC version is correct: $jsonrpc" "$service_name"
    else
        print_status "FAIL" "JSON-RPC version is incorrect: $jsonrpc" "$service_name"
        return 1
    fi
    
    # Check ID field
    local id=$(echo "$response" | jq -r '.id // ""' 2>/dev/null)
    if [ "$id" = "$expected_id" ]; then
        print_status "PASS" "Response ID matches request ID: $id" "$service_name"
    else
        print_status "FAIL" "Response ID does not match request ID: $id (expected: $expected_id)" "$service_name"
        return 1
    fi
    
    return 0
}

# Function to test MCP initialization
test_mcp_initialization() {
    local service_name="$1"
    local port="$2"
    local mcp_url="http://localhost:$port/mcp"
    
    print_status "INFO" "Testing MCP initialization for $service_name"
    
    # Prepare initialization request
    local init_request='{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}'
    
    # Send initialization request
    local response
    if ! response=$(curl -s --max-time $TIMEOUT -X POST "$mcp_url" \
        -H "Content-Type: application/json" \
        -d "$init_request" 2>/dev/null); then
        print_status "FAIL" "Failed to send initialization request" "$service_name"
        return 1
    fi
    
    # Validate JSON-RPC response
    if ! validate_jsonrpc_response "$service_name" "$response" "1"; then
        return 1
    fi
    
    # Check for result or error
    if echo "$response" | jq -e '.result' > /dev/null 2>&1; then
        print_status "PASS" "Initialization response contains result" "$service_name"
        
        # Check for capabilities
        local capabilities=$(echo "$response" | jq -r '.result.capabilities // {}' 2>/dev/null)
        if echo "$capabilities" | jq empty 2>/dev/null; then
            print_status "PASS" "Capabilities field is valid JSON object" "$service_name"
        else
            print_status "WARN" "Capabilities field is not valid JSON object" "$service_name"
        fi
    elif echo "$response" | jq -e '.error' > /dev/null 2>&1; then
        local error_code=$(echo "$response" | jq -r '.error.code // ""' 2>/dev/null)
        local error_message=$(echo "$response" | jq -r '.error.message // ""' 2>/dev/null)
        print_status "FAIL" "Initialization failed with error: $error_code - $error_message" "$service_name"
        return 1
    else
        print_status "FAIL" "Initialization response missing result or error" "$service_name"
        return 1
    fi
    
    return 0
}

# Function to test MCP tool discovery
test_mcp_tool_discovery() {
    local service_name="$1"
    local port="$2"
    local mcp_url="http://localhost:$port/mcp"
    
    print_status "INFO" "Testing MCP tool discovery for $service_name"
    
    # Prepare tools list request
    local tools_request='{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}'
    
    # Send tools list request
    local response
    if ! response=$(curl -s --max-time $TIMEOUT -X POST "$mcp_url" \
        -H "Content-Type: application/json" \
        -d "$tools_request" 2>/dev/null); then
        print_status "FAIL" "Failed to send tools list request" "$service_name"
        return 1
    fi
    
    # Validate JSON-RPC response
    if ! validate_jsonrpc_response "$service_name" "$response" "2"; then
        return 1
    fi
    
    # Check for result or error
    if echo "$response" | jq -e '.result' > /dev/null 2>&1; then
        print_status "PASS" "Tools list response contains result" "$service_name"
        
        # Check for tools array
        local tools=$(echo "$response" | jq -r '.result.tools // []' 2>/dev/null)
        if echo "$tools" | jq -e 'type == "array"' > /dev/null 2>&1; then
            local tool_count=$(echo "$tools" | jq 'length' 2>/dev/null)
            print_status "PASS" "Tools array is valid with $tool_count tools" "$service_name"
            
            # Validate each tool
            if [ "$tool_count" -gt 0 ]; then
                local tool_names=$(echo "$tools" | jq -r '.[].name // ""' 2>/dev/null)
                print_status "INFO" "Available tools: $tool_names" "$service_name"
                
                # Check tool structure
                local valid_tools=0
                for i in $(seq 0 $((tool_count - 1))); do
                    local tool=$(echo "$tools" | jq ".[$i]" 2>/dev/null)
                    if echo "$tool" | jq -e '.name and .description' > /dev/null 2>&1; then
                        ((valid_tools++))
                    fi
                done
                
                if [ "$valid_tools" -eq "$tool_count" ]; then
                    print_status "PASS" "All tools have required fields (name, description)" "$service_name"
                else
                    print_status "WARN" "Some tools missing required fields ($valid_tools/$tool_count valid)" "$service_name"
                fi
            else
                print_status "WARN" "No tools available" "$service_name"
            fi
        else
            print_status "FAIL" "Tools field is not an array" "$service_name"
            return 1
        fi
    elif echo "$response" | jq -e '.error' > /dev/null 2>&1; then
        local error_code=$(echo "$response" | jq -r '.error.code // ""' 2>/dev/null)
        local error_message=$(echo "$response" | jq -r '.error.message // ""' 2>/dev/null)
        print_status "FAIL" "Tool discovery failed with error: $error_code - $error_message" "$service_name"
        return 1
    else
        print_status "FAIL" "Tool discovery response missing result or error" "$service_name"
        return 1
    fi
    
    return 0
}

# Function to test MCP tool execution
test_mcp_tool_execution() {
    local service_name="$1"
    local port="$2"
    local mcp_url="http://localhost:$port/mcp"
    
    print_status "INFO" "Testing MCP tool execution for $service_name"
    
    # First, get available tools
    local tools_request='{"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}'
    local tools_response
    if ! tools_response=$(curl -s --max-time $TIMEOUT -X POST "$mcp_url" \
        -H "Content-Type: application/json" \
        -d "$tools_request" 2>/dev/null); then
        print_status "FAIL" "Failed to get tools list for execution test" "$service_name"
        return 1
    fi
    
    # Extract first available tool
    local first_tool=$(echo "$tools_response" | jq -r '.result.tools[0].name // ""' 2>/dev/null)
    if [ -z "$first_tool" ]; then
        print_status "WARN" "No tools available for execution test" "$service_name"
        return 0
    fi
    
    print_status "INFO" "Testing tool execution with: $first_tool" "$service_name"
    
    # Prepare tool call request
    local tool_call_request="{\"jsonrpc\": \"2.0\", \"id\": 4, \"method\": \"tools/call\", \"params\": {\"name\": \"$first_tool\", \"arguments\": {}}}"
    
    # Send tool call request
    local response
    if ! response=$(curl -s --max-time $TIMEOUT -X POST "$mcp_url" \
        -H "Content-Type: application/json" \
        -d "$tool_call_request" 2>/dev/null); then
        print_status "FAIL" "Failed to send tool call request" "$service_name"
        return 1
    fi
    
    # Validate JSON-RPC response
    if ! validate_jsonrpc_response "$service_name" "$response" "4"; then
        return 1
    fi
    
    # Check for result or error
    if echo "$response" | jq -e '.result' > /dev/null 2>&1; then
        print_status "PASS" "Tool execution response contains result" "$service_name"
        
        # Check for content array
        local content=$(echo "$response" | jq -r '.result.content // []' 2>/dev/null)
        if echo "$content" | jq -e 'type == "array"' > /dev/null 2>&1; then
            print_status "PASS" "Tool execution result contains content array" "$service_name"
        else
            print_status "WARN" "Tool execution result missing content array" "$service_name"
        fi
    elif echo "$response" | jq -e '.error' > /dev/null 2>&1; then
        local error_code=$(echo "$response" | jq -r '.error.code // ""' 2>/dev/null)
        local error_message=$(echo "$response" | jq -r '.error.message // ""' 2>/dev/null)
        print_status "WARN" "Tool execution failed with error: $error_code - $error_message" "$service_name"
        # Tool execution errors are not necessarily failures in protocol validation
    else
        print_status "FAIL" "Tool execution response missing result or error" "$service_name"
        return 1
    fi
    
    return 0
}

# Function to test MCP error handling
test_mcp_error_handling() {
    local service_name="$1"
    local port="$2"
    local mcp_url="http://localhost:$port/mcp"
    
    print_status "INFO" "Testing MCP error handling for $service_name"
    
    # Test invalid method
    local invalid_request='{"jsonrpc": "2.0", "id": 5, "method": "invalid_method", "params": {}}'
    
    local response
    if ! response=$(curl -s --max-time $TIMEOUT -X POST "$mcp_url" \
        -H "Content-Type: application/json" \
        -d "$invalid_request" 2>/dev/null); then
        print_status "FAIL" "Failed to send invalid method request" "$service_name"
        return 1
    fi
    
    # Validate JSON-RPC response
    if ! validate_jsonrpc_response "$service_name" "$response" "5"; then
        return 1
    fi
    
    # Check for error response
    if echo "$response" | jq -e '.error' > /dev/null 2>&1; then
        print_status "PASS" "Invalid method correctly returns error" "$service_name"
        
        local error_code=$(echo "$response" | jq -r '.error.code // ""' 2>/dev/null)
        if [ -n "$error_code" ]; then
            print_status "PASS" "Error response contains error code: $error_code" "$service_name"
        else
            print_status "WARN" "Error response missing error code" "$service_name"
        fi
    else
        print_status "WARN" "Invalid method did not return error response" "$service_name"
    fi
    
    return 0
}

# Function to test service MCP protocol
test_service_mcp_protocol() {
    local service_name="$1"
    local port="$2"
    
    print_status "INFO" "Testing MCP protocol for $service_name"
    
    local exit_code=0
    
    # Test MCP initialization
    if ! test_mcp_initialization "$service_name" "$port"; then
        ((exit_code++))
    fi
    
    # Test MCP tool discovery
    if ! test_mcp_tool_discovery "$service_name" "$port"; then
        ((exit_code++))
    fi
    
    # Test MCP tool execution
    if ! test_mcp_tool_execution "$service_name" "$port"; then
        ((exit_code++))
    fi
    
    # Test MCP error handling
    if ! test_mcp_error_handling "$service_name" "$port"; then
        ((exit_code++))
    fi
    
    return $exit_code
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -v, --verbose           Enable verbose output"
    echo "  -t, --timeout SECONDS   Set timeout for requests (default: 10)"
    echo "  --service SERVICE       Test specific service only"
    echo
    echo "Examples:"
    echo "  $0                      # Test all services"
    echo "  $0 -v                   # Test with verbose output"
    echo "  $0 --service gmail-mcp-server  # Test specific service"
}

# Parse command line arguments
SERVICE_FILTER=""

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
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --service)
            SERVICE_FILTER="$2"
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
echo "MCP Protocol Validation"
echo "======================="
echo

# Check if curl is available
if ! command -v curl > /dev/null 2>&1; then
    print_status "ERROR" "curl is required but not installed"
    exit 1
fi

# Check if jq is available
if ! command -v jq > /dev/null 2>&1; then
    print_status "ERROR" "jq is required for JSON validation"
    exit 1
fi

# Test services
local exit_code=0
for service_name in "${!MCP_SERVERS[@]}"; do
    # Skip if service filter is specified and doesn't match
    if [ -n "$SERVICE_FILTER" ] && [ "$service_name" != "$SERVICE_FILTER" ]; then
        continue
    fi
    
    local port="${MCP_SERVERS[$service_name]}"
    test_service_mcp_protocol "$service_name" "$port"
    local service_exit_code=$?
    
    if [ $service_exit_code -gt $exit_code ]; then
        exit_code=$service_exit_code
    fi
    
    echo
done

# Print summary
echo "MCP protocol validation completed."

if [ $exit_code -eq 0 ]; then
    print_status "PASS" "All MCP protocol tests passed"
    exit 0
else
    print_status "FAIL" "$exit_code MCP protocol test(s) failed"
    exit 1
fi