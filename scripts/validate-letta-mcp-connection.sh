#!/bin/bash

# Letta MCP Connection Validation Script
# This script validates Letta's connection to all MCP servers

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

# Letta configuration
LETTA_PORT=8283
LETTA_MCP_URL="http://localhost:$LETTA_PORT/v1/tools/mcp/servers"
LETTA_CONFIG_FILE="./letta/letta_mcp_config.json"

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

# Function to check if Letta is running
check_letta_running() {
    print_status "INFO" "Checking if Letta is running"
    
    if curl -s --max-time $TIMEOUT "http://localhost:$LETTA_PORT/health" > /dev/null 2>&1; then
        print_status "PASS" "Letta is running and accessible" "letta"
        return 0
    else
        print_status "FAIL" "Letta is not running or not accessible" "letta"
        return 1
    fi
}

# Function to validate Letta MCP configuration file
validate_letta_config() {
    print_status "INFO" "Validating Letta MCP configuration file"
    
    # Check if config file exists
    if [ ! -f "$LETTA_CONFIG_FILE" ]; then
        print_status "FAIL" "Letta MCP configuration file not found: $LETTA_CONFIG_FILE" "letta-config"
        return 1
    fi
    
    print_status "PASS" "Letta MCP configuration file exists" "letta-config"
    
    # Validate JSON format
    if ! jq empty "$LETTA_CONFIG_FILE" 2>/dev/null; then
        print_status "FAIL" "Letta MCP configuration file is not valid JSON" "letta-config"
        return 1
    fi
    
    print_status "PASS" "Letta MCP configuration file is valid JSON" "letta-config"
    
    # Check for mcpServers section
    if ! jq -e '.mcpServers' "$LETTA_CONFIG_FILE" > /dev/null 2>&1; then
        print_status "FAIL" "Letta MCP configuration missing mcpServers section" "letta-config"
        return 1
    fi
    
    print_status "PASS" "Letta MCP configuration contains mcpServers section" "letta-config"
    
    # Validate each MCP server configuration
    local config_valid=true
    for service_name in "${!MCP_SERVERS[@]}"; do
        local port="${MCP_SERVERS[$service_name]}"
        local expected_url="http://$service_name:$port"
        
        # Check if service is configured
        if jq -e ".mcpServers.\"$service_name\"" "$LETTA_CONFIG_FILE" > /dev/null 2>&1; then
            print_status "PASS" "Service $service_name is configured" "letta-config"
            
            # Check service configuration
            local service_config=$(jq ".mcpServers.\"$service_name\"" "$LETTA_CONFIG_FILE" 2>/dev/null)
            
            # Check command field
            local command=$(echo "$service_config" | jq -r '.command // ""' 2>/dev/null)
            if [ "$command" = "http" ]; then
                print_status "PASS" "Service $service_name has correct command: $command" "letta-config"
            else
                print_status "FAIL" "Service $service_name has incorrect command: $command (expected: http)" "letta-config"
                config_valid=false
            fi
            
            # Check args field
            local args=$(echo "$service_config" | jq -r '.args[0] // ""' 2>/dev/null)
            if [ "$args" = "$expected_url" ]; then
                print_status "PASS" "Service $service_name has correct URL: $args" "letta-config"
            else
                print_status "FAIL" "Service $service_name has incorrect URL: $args (expected: $expected_url)" "letta-config"
                config_valid=false
            fi
            
            # Check disabled field
            local disabled=$(echo "$service_config" | jq -r '.disabled // false' 2>/dev/null)
            if [ "$disabled" = "false" ]; then
                print_status "PASS" "Service $service_name is enabled" "letta-config"
            else
                print_status "WARN" "Service $service_name is disabled" "letta-config"
            fi
        else
            print_status "FAIL" "Service $service_name is not configured" "letta-config"
            config_valid=false
        fi
    done
    
    if [ "$config_valid" = true ]; then
        return 0
    else
        return 1
    fi
}

# Function to test Letta MCP server discovery
test_letta_mcp_discovery() {
    print_status "INFO" "Testing Letta MCP server discovery"
    
    # Test MCP servers endpoint
    if ! curl -s --max-time $TIMEOUT "$LETTA_MCP_URL" > /dev/null 2>&1; then
        print_status "FAIL" "Letta MCP servers endpoint not accessible" "letta-mcp"
        return 1
    fi
    
    print_status "PASS" "Letta MCP servers endpoint is accessible" "letta-mcp"
    
    # Get MCP servers response
    local response
    if ! response=$(curl -s --max-time $TIMEOUT "$LETTA_MCP_URL" 2>/dev/null); then
        print_status "FAIL" "Failed to get MCP servers response" "letta-mcp"
        return 1
    fi
    
    # Validate JSON response
    if ! echo "$response" | jq empty 2>/dev/null; then
        print_status "FAIL" "MCP servers response is not valid JSON" "letta-mcp"
        return 1
    fi
    
    print_status "PASS" "MCP servers response is valid JSON" "letta-mcp"
    
    # Check if response contains servers
    if echo "$response" | jq -e '.servers' > /dev/null 2>&1; then
        print_status "PASS" "MCP servers response contains servers field" "letta-mcp"
        
        # Count configured servers
        local server_count=$(echo "$response" | jq '.servers | length' 2>/dev/null)
        print_status "INFO" "Letta has $server_count MCP servers configured" "letta-mcp"
        
        # List configured servers
        local servers=$(echo "$response" | jq -r '.servers[].name // ""' 2>/dev/null)
        if [ -n "$servers" ]; then
            print_status "INFO" "Configured servers: $servers" "letta-mcp"
        fi
    else
        print_status "WARN" "MCP servers response missing servers field" "letta-mcp"
    fi
    
    return 0
}

# Function to test Letta MCP server connectivity
test_letta_mcp_connectivity() {
    print_status "INFO" "Testing Letta MCP server connectivity"
    
    # Test each configured MCP server
    local connectivity_issues=0
    for service_name in "${!MCP_SERVERS[@]}"; do
        local port="${MCP_SERVERS[$service_name]}"
        local service_url="http://localhost:$port/health"
        
        print_status "INFO" "Testing connectivity to $service_name"
        
        # Check if service is reachable from Letta's perspective
        if curl -s --max-time $TIMEOUT "$service_url" > /dev/null 2>&1; then
            print_status "PASS" "Service $service_name is reachable" "letta-connectivity"
        else
            print_status "FAIL" "Service $service_name is not reachable" "letta-connectivity"
            ((connectivity_issues++))
        fi
    done
    
    if [ $connectivity_issues -eq 0 ]; then
        print_status "PASS" "All MCP servers are reachable from Letta" "letta-connectivity"
        return 0
    else
        print_status "FAIL" "$connectivity_issues MCP server(s) are not reachable from Letta" "letta-connectivity"
        return 1
    fi
}

# Function to test Letta MCP tool integration
test_letta_mcp_tool_integration() {
    print_status "INFO" "Testing Letta MCP tool integration"
    
    # Test if Letta can discover MCP tools
    local tools_url="http://localhost:$LETTA_PORT/v1/tools"
    if curl -s --max-time $TIMEOUT "$tools_url" > /dev/null 2>&1; then
        print_status "PASS" "Letta tools endpoint is accessible" "letta-tools"
        
        # Get tools response
        local response
        if response=$(curl -s --max-time $TIMEOUT "$tools_url" 2>/dev/null); then
            if echo "$response" | jq empty 2>/dev/null; then
                print_status "PASS" "Letta tools response is valid JSON" "letta-tools"
                
                # Check if tools are available
                local tool_count=$(echo "$response" | jq '.tools | length' 2>/dev/null || echo "0")
                if [ "$tool_count" -gt 0 ]; then
                    print_status "PASS" "Letta has $tool_count tools available" "letta-tools"
                    
                    # List available tools
                    local tools=$(echo "$response" | jq -r '.tools[].name // ""' 2>/dev/null)
                    if [ -n "$tools" ]; then
                        print_status "INFO" "Available tools: $tools" "letta-tools"
                    fi
                else
                    print_status "WARN" "No tools available in Letta" "letta-tools"
                fi
            else
                print_status "WARN" "Letta tools response is not valid JSON" "letta-tools"
            fi
        else
            print_status "WARN" "Failed to get Letta tools response" "letta-tools"
        fi
    else
        print_status "WARN" "Letta tools endpoint not accessible" "letta-tools"
    fi
    
    return 0
}

# Function to test Letta MCP configuration API
test_letta_mcp_config_api() {
    print_status "INFO" "Testing Letta MCP configuration API"
    
    # Test MCP configuration endpoint
    local config_url="http://localhost:$LETTA_PORT/v1/config/mcp"
    if curl -s --max-time $TIMEOUT "$config_url" > /dev/null 2>&1; then
        print_status "PASS" "Letta MCP configuration endpoint is accessible" "letta-config-api"
        
        # Get configuration response
        local response
        if response=$(curl -s --max-time $TIMEOUT "$config_url" 2>/dev/null); then
            if echo "$response" | jq empty 2>/dev/null; then
                print_status "PASS" "Letta MCP configuration response is valid JSON" "letta-config-api"
            else
                print_status "WARN" "Letta MCP configuration response is not valid JSON" "letta-config-api"
            fi
        else
            print_status "WARN" "Failed to get Letta MCP configuration response" "letta-config-api"
        fi
    else
        print_status "WARN" "Letta MCP configuration endpoint not accessible" "letta-config-api"
    fi
    
    return 0
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -v, --verbose           Enable verbose output"
    echo "  -t, --timeout SECONDS   Set timeout for requests (default: 10)"
    echo "  --config-file FILE      Use custom Letta config file path"
    echo
    echo "Examples:"
    echo "  $0                      # Test Letta MCP connectivity"
    echo "  $0 -v                   # Test with verbose output"
    echo "  $0 --config-file /path/to/config.json  # Use custom config file"
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
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --config-file)
            LETTA_CONFIG_FILE="$2"
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
echo "Letta MCP Connection Validation"
echo "==============================="
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

# Test Letta MCP connectivity
local exit_code=0

# Check if Letta is running
if ! check_letta_running; then
    print_status "ERROR" "Letta is not running, cannot proceed with MCP connectivity tests"
    exit 1
fi

echo

# Validate Letta MCP configuration
if ! validate_letta_config; then
    ((exit_code++))
fi

echo

# Test Letta MCP server discovery
if ! test_letta_mcp_discovery; then
    ((exit_code++))
fi

echo

# Test Letta MCP server connectivity
if ! test_letta_mcp_connectivity; then
    ((exit_code++))
fi

echo

# Test Letta MCP tool integration
if ! test_letta_mcp_tool_integration; then
    ((exit_code++))
fi

echo

# Test Letta MCP configuration API
if ! test_letta_mcp_config_api; then
    ((exit_code++))
fi

echo

# Print summary
echo "Letta MCP connection validation completed."

if [ $exit_code -eq 0 ]; then
    print_status "PASS" "All Letta MCP connection tests passed"
    exit 0
else
    print_status "FAIL" "$exit_code Letta MCP connection test(s) failed"
    exit 1
fi