#!/bin/bash

# Health Check All MCP Servers
# This script checks the health of all MCP servers in the PA ecosystem

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
HEALTH_MONITOR_URL="http://localhost:8083"
TIMEOUT=10
VERBOSE=false

# MCP Server configurations
declare -A MCP_SERVERS=(
    ["gmail-mcp-server"]="http://localhost:8080/health"
    ["graphiti-mcp-server"]="http://localhost:8082/health"
    ["rag-mcp-server"]="http://localhost:8082/health"
)

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    local service=$3
    
    case $status in
        "HEALTHY")
            echo -e "${GREEN}✓${NC} $service: $message"
            ;;
        "UNHEALTHY")
            echo -e "${RED}✗${NC} $service: $message"
            ;;
        "DEGRADED")
            echo -e "${YELLOW}⚠${NC} $service: $message"
            ;;
        "UNKNOWN")
            echo -e "${BLUE}?${NC} $service: $message"
            ;;
        "INFO")
            echo -e "${BLUE}ℹ${NC} $message"
            ;;
        "ERROR")
            echo -e "${RED}✗${NC} $message"
            ;;
    esac
}

# Function to check individual service health
check_service_health() {
    local service_name=$1
    local health_url=$2
    
    if [ "$VERBOSE" = true ]; then
        echo "Checking $service_name at $health_url..."
    fi
    
    # Check if service is reachable
    if ! curl -s --max-time $TIMEOUT "$health_url" > /dev/null 2>&1; then
        print_status "UNHEALTHY" "Service unreachable" "$service_name"
        return 1
    fi
    
    # Get health response
    local response
    if ! response=$(curl -s --max-time $TIMEOUT "$health_url" 2>/dev/null); then
        print_status "UNHEALTHY" "Failed to get health response" "$service_name"
        return 1
    fi
    
    # Parse health response
    local status
    local version
    local uptime
    local response_time
    
    # Extract status from JSON response
    if command -v jq > /dev/null 2>&1; then
        status=$(echo "$response" | jq -r '.status // "unknown"' 2>/dev/null)
        version=$(echo "$response" | jq -r '.version // "unknown"' 2>/dev/null)
        uptime=$(echo "$response" | jq -r '.uptime // 0' 2>/dev/null)
        response_time=$(echo "$response" | jq -r '.responseTime // 0' 2>/dev/null)
    else
        # Fallback parsing without jq
        status=$(echo "$response" | grep -o '"status":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
        version=$(echo "$response" | grep -o '"version":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
        uptime=$(echo "$response" | grep -o '"uptime":[0-9.]*' | cut -d':' -f2 || echo "0")
        response_time=$(echo "$response" | grep -o '"responseTime":[0-9.]*' | cut -d':' -f2 || echo "0")
    fi
    
    # Determine health status
    case $status in
        "healthy")
            local message="Healthy (v$version, uptime: ${uptime}s"
            if [ "$response_time" != "0" ] && [ "$response_time" != "null" ]; then
                message+=", response: ${response_time}ms"
            fi
            message+=")"
            print_status "HEALTHY" "$message" "$service_name"
            return 0
            ;;
        "unhealthy")
            print_status "UNHEALTHY" "Unhealthy (v$version)" "$service_name"
            return 1
            ;;
        "degraded")
            print_status "DEGRADED" "Degraded (v$version)" "$service_name"
            return 2
            ;;
        *)
            print_status "UNKNOWN" "Unknown status: $status (v$version)" "$service_name"
            return 3
            ;;
    esac
}

# Function to check health monitor service
check_health_monitor() {
    local health_monitor_url="$HEALTH_MONITOR_URL/health"
    
    if [ "$VERBOSE" = true ]; then
        echo "Checking health monitor at $health_monitor_url..."
    fi
    
    if ! curl -s --max-time $TIMEOUT "$health_monitor_url" > /dev/null 2>&1; then
        print_status "UNHEALTHY" "Health monitor unreachable" "health-monitor"
        return 1
    fi
    
    local response
    if ! response=$(curl -s --max-time $TIMEOUT "$health_monitor_url" 2>/dev/null); then
        print_status "UNHEALTHY" "Failed to get health monitor response" "health-monitor"
        return 1
    fi
    
    local status
    if command -v jq > /dev/null 2>&1; then
        status=$(echo "$response" | jq -r '.status // "unknown"' 2>/dev/null)
    else
        status=$(echo "$response" | grep -o '"status":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
    fi
    
    if [ "$status" = "healthy" ]; then
        print_status "HEALTHY" "Health monitor is running" "health-monitor"
        return 0
    else
        print_status "UNHEALTHY" "Health monitor status: $status" "health-monitor"
        return 1
    fi
}

# Function to get overall health from health monitor
get_overall_health() {
    local overall_url="$HEALTH_MONITOR_URL/api/health/overall"
    
    if [ "$VERBOSE" = true ]; then
        echo "Getting overall health from health monitor..."
    fi
    
    if ! curl -s --max-time $TIMEOUT "$overall_url" > /dev/null 2>&1; then
        print_status "ERROR" "Failed to get overall health from health monitor"
        return 1
    fi
    
    local response
    if ! response=$(curl -s --max-time $TIMEOUT "$overall_url" 2>/dev/null); then
        print_status "ERROR" "Failed to get overall health response"
        return 1
    fi
    
    local overall_status
    local healthy_count
    local unhealthy_count
    local degraded_count
    local total_count
    
    if command -v jq > /dev/null 2>&1; then
        overall_status=$(echo "$response" | jq -r '.overall // "unknown"' 2>/dev/null)
        healthy_count=$(echo "$response" | jq -r '.healthyServices // 0' 2>/dev/null)
        unhealthy_count=$(echo "$response" | jq -r '.unhealthyServices // 0' 2>/dev/null)
        degraded_count=$(echo "$response" | jq -r '.degradedServices // 0' 2>/dev/null)
        total_count=$(echo "$response" | jq -r '.totalServices // 0' 2>/dev/null)
    else
        overall_status=$(echo "$response" | grep -o '"overall":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
        healthy_count=$(echo "$response" | grep -o '"healthyServices":[0-9]*' | cut -d':' -f2 || echo "0")
        unhealthy_count=$(echo "$response" | grep -o '"unhealthyServices":[0-9]*' | cut -d':' -f2 || echo "0")
        degraded_count=$(echo "$response" | grep -o '"degradedServices":[0-9]*' | cut -d':' -f2 || echo "0")
        total_count=$(echo "$response" | grep -o '"totalServices":[0-9]*' | cut -d':' -f2 || echo "0")
    fi
    
    echo
    print_status "INFO" "Overall Health Summary:"
    echo "  Total Services: $total_count"
    echo "  Healthy: $healthy_count"
    echo "  Degraded: $degraded_count"
    echo "  Unhealthy: $unhealthy_count"
    echo "  Overall Status: $overall_status"
    
    case $overall_status in
        "healthy")
            print_status "HEALTHY" "All services are healthy" "overall"
            return 0
            ;;
        "degraded")
            print_status "DEGRADED" "Some services are degraded" "overall"
            return 2
            ;;
        "unhealthy")
            print_status "UNHEALTHY" "Some services are unhealthy" "overall"
            return 1
            ;;
        *)
            print_status "UNKNOWN" "Overall status unknown" "overall"
            return 3
            ;;
    esac
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -v, --verbose           Enable verbose output"
    echo "  -t, --timeout SECONDS   Set timeout for health checks (default: 10)"
    echo "  -m, --monitor URL       Set health monitor URL (default: http://localhost:8083)"
    echo "  --individual            Check individual services only (skip health monitor)"
    echo "  --overall               Get overall health from health monitor only"
    echo
    echo "Examples:"
    echo "  $0                      # Check all services"
    echo "  $0 -v                   # Check with verbose output"
    echo "  $0 --individual         # Check individual services only"
    echo "  $0 --overall            # Get overall health from monitor"
}

# Parse command line arguments
INDIVIDUAL_ONLY=false
OVERALL_ONLY=false

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
        -m|--monitor)
            HEALTH_MONITOR_URL="$2"
            shift 2
            ;;
        --individual)
            INDIVIDUAL_ONLY=true
            shift
            ;;
        --overall)
            OVERALL_ONLY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
echo "PA Ecosystem Health Check"
echo "========================="
echo

# Check if curl is available
if ! command -v curl > /dev/null 2>&1; then
    print_status "ERROR" "curl is required but not installed"
    exit 1
fi

# Check individual services
if [ "$OVERALL_ONLY" = false ]; then
    print_status "INFO" "Checking individual MCP services..."
    echo
    
    local exit_code=0
    for service_name in "${!MCP_SERVERS[@]}"; do
        check_service_health "$service_name" "${MCP_SERVERS[$service_name]}"
        local service_exit_code=$?
        if [ $service_exit_code -gt $exit_code ]; then
            exit_code=$service_exit_code
        fi
    done
    
    echo
fi

# Check health monitor and get overall health
if [ "$INDIVIDUAL_ONLY" = false ]; then
    print_status "INFO" "Checking health monitor service..."
    check_health_monitor
    local monitor_exit_code=$?
    
    if [ $monitor_exit_code -eq 0 ]; then
        get_overall_health
        local overall_exit_code=$?
        if [ $overall_exit_code -gt $exit_code ]; then
            exit_code=$overall_exit_code
        fi
    else
        print_status "ERROR" "Health monitor is not available"
        exit_code=1
    fi
fi

echo
echo "Health check completed."

# Exit with appropriate code
if [ $exit_code -eq 0 ]; then
    print_status "INFO" "All systems are healthy"
    exit 0
elif [ $exit_code -eq 2 ]; then
    print_status "INFO" "Some systems are degraded"
    exit 2
else
    print_status "INFO" "Some systems are unhealthy"
    exit 1
fi

