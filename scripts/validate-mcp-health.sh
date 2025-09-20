#!/bin/bash

# MCP Health Validation Script
# This script validates the health endpoints of all MCP servers

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
    ["health-monitor"]="8083"
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

# Function to validate health response format
validate_health_response() {
    local service_name="$1"
    local health_url="$2"
    local response="$3"
    
    local validation_passed=true
    
    # Check if response is valid JSON
    if ! echo "$response" | jq empty 2>/dev/null; then
        print_status "FAIL" "Health response is not valid JSON" "$service_name"
        return 1
    fi
    
    # Check required fields
    local required_fields=("status" "timestamp" "service" "version" "uptime")
    for field in "${required_fields[@]}"; do
        if ! echo "$response" | jq -e ".$field" > /dev/null 2>&1; then
            print_status "FAIL" "Health response missing required field: $field" "$service_name"
            validation_passed=false
        fi
    done
    
    # Check status value
    local status=$(echo "$response" | jq -r '.status // "unknown"' 2>/dev/null)
    if [[ "$status" =~ ^(healthy|unhealthy|degraded)$ ]]; then
        print_status "PASS" "Health status is valid: $status" "$service_name"
    else
        print_status "FAIL" "Health status is invalid: $status" "$service_name"
        validation_passed=false
    fi
    
    # Check timestamp format
    local timestamp=$(echo "$response" | jq -r '.timestamp // ""' 2>/dev/null)
    if [[ "$timestamp" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2} ]]; then
        print_status "PASS" "Timestamp format is valid" "$service_name"
    else
        print_status "FAIL" "Timestamp format is invalid: $timestamp" "$service_name"
        validation_passed=false
    fi
    
    # Check uptime is numeric
    local uptime=$(echo "$response" | jq -r '.uptime // 0' 2>/dev/null)
    if [[ "$uptime" =~ ^[0-9]+\.?[0-9]*$ ]]; then
        print_status "PASS" "Uptime is numeric: $uptime" "$service_name"
    else
        print_status "FAIL" "Uptime is not numeric: $uptime" "$service_name"
        validation_passed=false
    fi
    
    # Check dependencies if present
    if echo "$response" | jq -e '.dependencies' > /dev/null 2>&1; then
        local dependencies=$(echo "$response" | jq -r '.dependencies' 2>/dev/null)
        if echo "$dependencies" | jq empty 2>/dev/null; then
            print_status "PASS" "Dependencies field is valid JSON object" "$service_name"
        else
            print_status "FAIL" "Dependencies field is not valid JSON object" "$service_name"
            validation_passed=false
        fi
    fi
    
    # Check response time if present
    if echo "$response" | jq -e '.responseTime' > /dev/null 2>&1; then
        local response_time=$(echo "$response" | jq -r '.responseTime' 2>/dev/null)
        if [[ "$response_time" =~ ^[0-9]+\.?[0-9]*$ ]]; then
            print_status "PASS" "Response time is numeric: ${response_time}ms" "$service_name"
        else
            print_status "FAIL" "Response time is not numeric: $response_time" "$service_name"
            validation_passed=false
        fi
    fi
    
    if [ "$validation_passed" = true ]; then
        return 0
    else
        return 1
    fi
}

# Function to test service health
test_service_health() {
    local service_name="$1"
    local port="$2"
    local health_url="http://localhost:$port/health"
    
    print_status "INFO" "Testing $service_name health endpoint"
    
    # Test if service is reachable
    if ! curl -s --max-time $TIMEOUT "$health_url" > /dev/null 2>&1; then
        print_status "FAIL" "Service is not reachable" "$service_name"
        return 1
    fi
    
    # Get health response
    local response
    if ! response=$(curl -s --max-time $TIMEOUT "$health_url" 2>/dev/null); then
        print_status "FAIL" "Failed to get health response" "$service_name"
        return 1
    fi
    
    # Validate health response format
    if validate_health_response "$service_name" "$health_url" "$response"; then
        print_status "PASS" "Health response validation passed" "$service_name"
        
        # Check if service is healthy
        local status=$(echo "$response" | jq -r '.status // "unknown"' 2>/dev/null)
        if [ "$status" = "healthy" ]; then
            print_status "PASS" "Service is healthy" "$service_name"
            return 0
        elif [ "$status" = "degraded" ]; then
            print_status "WARN" "Service is degraded" "$service_name"
            return 2
        else
            print_status "FAIL" "Service is unhealthy: $status" "$service_name"
            return 1
        fi
    else
        print_status "FAIL" "Health response validation failed" "$service_name"
        return 1
    fi
}

# Function to test health monitor specific endpoints
test_health_monitor_endpoints() {
    local base_url="http://localhost:8083"
    
    print_status "INFO" "Testing health monitor specific endpoints"
    
    # Test overall health endpoint
    local overall_url="$base_url/api/health/overall"
    if curl -s --max-time $TIMEOUT "$overall_url" > /dev/null 2>&1; then
        print_status "PASS" "Overall health endpoint accessible" "health-monitor"
    else
        print_status "FAIL" "Overall health endpoint not accessible" "health-monitor"
    fi
    
    # Test services endpoint
    local services_url="$base_url/api/services"
    if curl -s --max-time $TIMEOUT "$services_url" > /dev/null 2>&1; then
        print_status "PASS" "Services endpoint accessible" "health-monitor"
    else
        print_status "FAIL" "Services endpoint not accessible" "health-monitor"
    fi
    
    # Test alerts endpoint
    local alerts_url="$base_url/api/alerts"
    if curl -s --max-time $TIMEOUT "$alerts_url" > /dev/null 2>&1; then
        print_status "PASS" "Alerts endpoint accessible" "health-monitor"
    else
        print_status "FAIL" "Alerts endpoint not accessible" "health-monitor"
    fi
    
    # Test dashboard endpoint
    local dashboard_url="$base_url/dashboard"
    if curl -s --max-time $TIMEOUT "$dashboard_url" > /dev/null 2>&1; then
        print_status "PASS" "Dashboard endpoint accessible" "health-monitor"
    else
        print_status "FAIL" "Dashboard endpoint not accessible" "health-monitor"
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -v, --verbose           Enable verbose output"
    echo "  -t, --timeout SECONDS   Set timeout for health checks (default: 10)"
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
echo "MCP Health Validation"
echo "===================="
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
    test_service_health "$service_name" "$port"
    local service_exit_code=$?
    
    if [ $service_exit_code -gt $exit_code ]; then
        exit_code=$service_exit_code
    fi
    
    echo
done

# Test health monitor specific endpoints
if [ -z "$SERVICE_FILTER" ] || [ "$SERVICE_FILTER" = "health-monitor" ]; then
    test_health_monitor_endpoints
    echo
fi

# Print summary
echo "Health validation completed."

if [ $exit_code -eq 0 ]; then
    print_status "PASS" "All health checks passed"
    exit 0
elif [ $exit_code -eq 2 ]; then
    print_status "WARN" "Some services are degraded"
    exit 2
else
    print_status "FAIL" "Some health checks failed"
    exit 1
fi