#!/bin/bash

# PA Ecosystem Network Security Tests
# Comprehensive testing suite for network segmentation and security validation
# Created: 2025-01-21

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
TEST_RESULTS="$PROJECT_ROOT/logs/network-security-tests.json"
LOG_FILE="$PROJECT_ROOT/logs/network-security-tests.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Function to log messages
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOG_FILE"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO:${NC} $1" | tee -a "$LOG_FILE"
}

# Function to run a test
run_test() {
    local test_name="$1"
    local test_command="$2"
    local expected_result="$3"
    
    ((TOTAL_TESTS++))
    info "Running test: $test_name"
    
    if eval "$test_command"; then
        if [ "$expected_result" = "pass" ]; then
            log "✓ PASS: $test_name"
            ((PASSED_TESTS++))
            return 0
        else
            error "✗ FAIL: $test_name (unexpected success)"
            ((FAILED_TESTS++))
            return 1
        fi
    else
        if [ "$expected_result" = "fail" ]; then
            log "✓ PASS: $test_name (correctly failed)"
            ((PASSED_TESTS++))
            return 0
        else
            error "✗ FAIL: $test_name (unexpected failure)"
            ((FAILED_TESTS++))
            return 1
        fi
    fi
}

# Function to test network connectivity
test_network_connectivity() {
    local source_service="$1"
    local target_service="$2"
    local target_port="$3"
    local timeout="${4:-5}"
    
    # Check if containers are running
    if ! docker ps | grep -q "$source_service"; then
        return 1
    fi
    
    if ! docker ps | grep -q "$target_service"; then
        return 1
    fi
    
    # Test connectivity
    if docker exec "$source_service" timeout "$timeout" nc -z "$target_service" "$target_port" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Function to test network isolation
test_network_isolation() {
    log "Testing network isolation..."
    
    # Test 1: Frontend should not access database
    run_test "Frontend to Database Isolation" \
        "test_network_connectivity open-webui supabase-db 5432" \
        "fail"
    
    # Test 2: External should not access MCP services
    run_test "External to MCP Isolation" \
        "test_network_connectivity cloudflare-tunnel gmail-mcp-server 8080" \
        "fail"
    
    # Test 3: External should not access AI services
    run_test "External to AI Isolation" \
        "test_network_connectivity cloudflare-tunnel letta 8283" \
        "fail"
    
    # Test 4: Database should not access frontend
    run_test "Database to Frontend Isolation" \
        "test_network_connectivity supabase-db open-webui 8080" \
        "fail"
}

# Function to test allowed connectivity
test_allowed_connectivity() {
    log "Testing allowed connectivity..."
    
    # Test 1: Backend should access database
    run_test "Backend to Database Access" \
        "test_network_connectivity n8n supabase-db 5432" \
        "pass"
    
    # Test 2: Frontend should access backend
    run_test "Frontend to Backend Access" \
        "test_network_connectivity open-webui n8n 5678" \
        "pass"
    
    # Test 3: AI services should access MCP
    run_test "AI to MCP Access" \
        "test_network_connectivity letta gmail-mcp-server 8080" \
        "pass"
    
    # Test 4: Monitoring should access all services
    run_test "Monitoring to Services Access" \
        "test_network_connectivity health-monitor gmail-mcp-server 8080" \
        "pass"
}

# Function to test network segmentation
test_network_segmentation() {
    log "Testing network segmentation..."
    
    # Test 1: All networks should exist
    local networks=(
        "pa-database-tier"
        "pa-supabase-internal"
        "pa-backend-tier"
        "pa-mcp-tier"
        "pa-frontend-tier"
        "pa-external-tier"
        "pa-monitoring-tier"
        "pa-ai-tier"
    )
    
    for network in "${networks[@]}"; do
        run_test "Network $network exists" \
            "docker network ls | grep -q '$network'" \
            "pass"
    done
    
    # Test 2: Services should be in correct networks
    run_test "Database in database tier" \
        "docker inspect supabase-db | grep -q 'pa-database-tier'" \
        "pass"
    
    run_test "MCP services in MCP tier" \
        "docker inspect gmail-mcp-server | grep -q 'pa-mcp-tier'" \
        "pass"
    
    run_test "Frontend in frontend tier" \
        "docker inspect open-webui | grep -q 'pa-frontend-tier'" \
        "pass"
}

# Function to test firewall policies
test_firewall_policies() {
    log "Testing firewall policies..."
    
    # Test 1: ICC should be disabled on all networks
    local networks=(
        "pa-database-tier"
        "pa-mcp-tier"
        "pa-ai-tier"
        "pa-monitoring-tier"
    )
    
    for network in "${networks[@]}"; do
        run_test "ICC disabled on $network" \
            "docker network inspect '$network' | grep -q '\"enable_icc\": false'" \
            "pass"
    done
    
    # Test 2: IP masquerading should be enabled
    for network in "${networks[@]}"; do
        run_test "IP masquerading enabled on $network" \
            "docker network inspect '$network' | grep -q '\"enable_ip_masquerade\": true'" \
            "pass"
    done
}

# Function to test service discovery
test_service_discovery() {
    log "Testing service discovery..."
    
    # Test 1: Services should resolve by name
    run_test "Database name resolution" \
        "docker exec n8n nslookup supabase-db" \
        "pass"
    
    run_test "MCP name resolution" \
        "docker exec letta nslookup gmail-mcp-server" \
        "pass"
    
    # Test 2: Services should not resolve across isolated tiers
    run_test "Cross-tier name resolution blocked" \
        "docker exec open-webui nslookup supabase-db" \
        "fail"
}

# Function to test security labels
test_security_labels() {
    log "Testing security labels..."
    
    # Test 1: Services should have correct security labels
    run_test "Database security labels" \
        "docker inspect supabase-db | grep -q '\"security\": \"high\"'" \
        "pass"
    
    run_test "MCP security labels" \
        "docker inspect gmail-mcp-server | grep -q '\"security\": \"high\"'" \
        "pass"
    
    run_test "Frontend security labels" \
        "docker inspect open-webui | grep -q '\"security\": \"medium\"'" \
        "pass"
    
    # Test 2: Networks should have security labels
    run_test "Network security labels" \
        "docker network inspect pa-database-tier | grep -q '\"security\": \"high\"'" \
        "pass"
}

# Function to test port restrictions
test_port_restrictions() {
    log "Testing port restrictions..."
    
    # Test 1: Only required ports should be open
    run_test "Database port 5432 open" \
        "test_network_connectivity n8n supabase-db 5432" \
        "pass"
    
    run_test "MCP port 8080 open" \
        "test_network_connectivity letta gmail-mcp-server 8080" \
        "pass"
    
    # Test 2: Unauthorized ports should be blocked
    run_test "Unauthorized port 22 blocked" \
        "test_network_connectivity open-webui supabase-db 22" \
        "fail"
}

# Function to test monitoring access
test_monitoring_access() {
    log "Testing monitoring access..."
    
    # Test 1: Monitoring should access all services
    run_test "Monitoring to database" \
        "test_network_connectivity health-monitor supabase-db 5432" \
        "pass"
    
    run_test "Monitoring to MCP services" \
        "test_network_connectivity health-monitor gmail-mcp-server 8080" \
        "pass"
    
    run_test "Monitoring to AI services" \
        "test_network_connectivity health-monitor letta 8283" \
        "pass"
    
    # Test 2: Non-monitoring services should not access monitoring
    run_test "Non-monitoring to monitoring isolation" \
        "test_network_connectivity open-webui health-monitor 8080" \
        "fail"
}

# Function to generate test report
generate_test_report() {
    log "Generating test report..."
    
    local pass_rate=$((PASSED_TESTS * 100 / TOTAL_TESTS))
    
    cat > "$TEST_RESULTS" << EOF
{
  "test_metadata": {
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "test_suite": "network_security",
    "project_root": "$PROJECT_ROOT"
  },
  "test_summary": {
    "total_tests": $TOTAL_TESTS,
    "passed_tests": $PASSED_TESTS,
    "failed_tests": $FAILED_TESTS,
    "pass_rate": $pass_rate
  },
  "test_results": {
    "network_isolation": "$([ $FAILED_TESTS -eq 0 ] && echo "PASSED" || echo "FAILED")",
    "connectivity": "$([ $PASSED_TESTS -gt 0 ] && echo "FUNCTIONAL" || echo "BROKEN")",
    "security_policies": "$([ $FAILED_TESTS -eq 0 ] && echo "ENFORCED" || echo "VIOLATED")"
  },
  "recommendations": [
    $([ $FAILED_TESTS -gt 0 ] && echo '"Review failed tests and fix network configuration issues"')
    $([ $PASSED_TESTS -eq $TOTAL_TESTS ] && echo '"All tests passed - network security is properly configured"')
  ]
}
EOF
    
    log "✓ Test report generated: $TEST_RESULTS"
}

# Function to print test summary
print_test_summary() {
    log "Network Security Test Summary"
    log "============================"
    
    local pass_rate=$((PASSED_TESTS * 100 / TOTAL_TESTS))
    
    echo "Total Tests: $TOTAL_TESTS"
    echo "Passed: $PASSED_TESTS"
    echo "Failed: $FAILED_TESTS"
    echo "Pass Rate: $pass_rate%"
    echo ""
    
    if [ $FAILED_TESTS -eq 0 ]; then
        log "✓ All network security tests passed!"
        echo ""
        echo "Network Security Status:"
        echo "  - Network isolation: ✓ Working"
        echo "  - Firewall policies: ✓ Enforced"
        echo "  - Service connectivity: ✓ Functional"
        echo "  - Security controls: ✓ Active"
    else
        warning "Network security tests failed!"
        echo ""
        echo "Issues found:"
        echo "  - Failed tests: $FAILED_TESTS"
        echo "  - Pass rate: $pass_rate%"
        echo ""
        echo "Review the detailed test results and fix configuration issues."
    fi
}

# Function to show help
show_help() {
    echo "PA Ecosystem Network Security Tests"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  run-all                   Run all network security tests"
    echo "  test-isolation           Test network isolation only"
    echo "  test-connectivity        Test allowed connectivity only"
    echo "  test-segmentation        Test network segmentation only"
    echo "  test-firewall            Test firewall policies only"
    echo "  test-discovery           Test service discovery only"
    echo "  test-labels              Test security labels only"
    echo "  test-ports               Test port restrictions only"
    echo "  test-monitoring          Test monitoring access only"
    echo "  help                     Show this help message"
    echo ""
    echo "Options:"
    echo "  --verbose                Enable verbose output"
    echo "  --report-only            Generate report without running tests"
    echo ""
    echo "Examples:"
    echo "  $0 run-all               # Run all tests"
    echo "  $0 test-isolation        # Test isolation only"
    echo "  $0 --verbose             # Run with verbose output"
}

# Main function
main() {
    local command="$1"
    shift
    
    # Parse options
    while [[ $# -gt 0 ]]; do
        case $1 in
            --verbose)
                set -x
                shift
                ;;
            --report-only)
                generate_test_report
                print_test_summary
                exit 0
                ;;
            *)
                break
                ;;
        esac
    done
    
    # Initialize logging
    mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$TEST_RESULTS")"
    
    log "Network Security Tests - $(date)"
    log "================================"
    
    # Check prerequisites
    if ! docker info &>/dev/null; then
        error "Docker is not running"
        exit 1
    fi
    
    # Reset test counters
    TOTAL_TESTS=0
    PASSED_TESTS=0
    FAILED_TESTS=0
    
    # Execute command
    case "$command" in
        "run-all")
            test_network_isolation
            test_allowed_connectivity
            test_network_segmentation
            test_firewall_policies
            test_service_discovery
            test_security_labels
            test_port_restrictions
            test_monitoring_access
            ;;
        "test-isolation")
            test_network_isolation
            ;;
        "test-connectivity")
            test_allowed_connectivity
            ;;
        "test-segmentation")
            test_network_segmentation
            ;;
        "test-firewall")
            test_firewall_policies
            ;;
        "test-discovery")
            test_service_discovery
            ;;
        "test-labels")
            test_security_labels
            ;;
        "test-ports")
            test_port_restrictions
            ;;
        "test-monitoring")
            test_monitoring_access
            ;;
        "help"|"--help"|"-h")
            show_help
            exit 0
            ;;
        *)
            error "Unknown command: $command"
            show_help
            exit 1
            ;;
    esac
    
    # Generate report and summary
    generate_test_report
    print_test_summary
    
    # Exit with appropriate code
    if [ $FAILED_TESTS -eq 0 ]; then
        exit 0
    else
        exit 1
    fi
}

# Run main function
main "$@"
