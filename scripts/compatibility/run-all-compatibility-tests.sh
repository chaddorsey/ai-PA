#!/bin/bash

# Comprehensive Compatibility Testing Script
# Purpose: Run all compatibility tests and generate comprehensive reports
# Usage: ./run-all-compatibility-tests.sh [--framework <framework>] [--generate-report]

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
LOG_FILE="/var/log/compatibility/comprehensive-test-$(date +%Y%m%d-%H%M%S).log"
REPORT_DIR="/var/reports/compatibility"
FRAMEWORK=""
GENERATE_REPORT=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --framework)
            FRAMEWORK="$2"
            shift 2
            ;;
        --generate-report)
            GENERATE_REPORT=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--framework <framework>] [--generate-report]"
            echo ""
            echo "Options:"
            echo "  --framework       Specific framework to test (n8n, letta, graphiti)"
            echo "  --generate-report Generate comprehensive compatibility report"
            echo "  -h, --help        Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Create log and report directories
mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$REPORT_DIR"

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

# Test results tracking
declare -A TEST_RESULTS
declare -A TEST_DURATIONS

# Run test and track results
run_test() {
    local test_name="$1"
    local test_script="$2"
    local test_args="$3"
    
    info "Running $test_name..."
    
    local start_time=$(date +%s)
    local test_log="/tmp/${test_name//[^a-zA-Z0-9]/_}_$(date +%Y%m%d_%H%M%S).log"
    
    if "$test_script" $test_args > "$test_log" 2>&1; then
        TEST_RESULTS["$test_name"]="PASSED"
        success "$test_name completed successfully"
    else
        TEST_RESULTS["$test_name"]="FAILED"
        warning "$test_name failed - check log: $test_log"
    fi
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    TEST_DURATIONS["$test_name"]="$duration"
    
    info "$test_name completed in ${duration}s"
}

# Generate compatibility report
generate_report() {
    local report_file="$REPORT_DIR/compatibility-report-$(date +%Y%m%d-%H%M%S).md"
    
    info "Generating compatibility report: $report_file"
    
    cat > "$report_file" << EOF
# PA Ecosystem Compatibility Report

**Generated**: $(date)
**Test Duration**: $(date -d "@$(($(date +%s) - START_TIME))" -u +%H:%M:%S)
**Framework Focus**: ${FRAMEWORK:-all}

## Executive Summary

This report provides a comprehensive overview of compatibility testing results for the PA Ecosystem frameworks.

### Overall Results

EOF

    # Add test results summary
    local total_tests=0
    local passed_tests=0
    local failed_tests=0
    
    for test_name in "${!TEST_RESULTS[@]}"; do
        total_tests=$((total_tests + 1))
        if [ "${TEST_RESULTS[$test_name]}" = "PASSED" ]; then
            passed_tests=$((passed_tests + 1))
        else
            failed_tests=$((failed_tests + 1))
        fi
    done
    
    cat >> "$report_file" << EOF
- **Total Tests**: $total_tests
- **Passed**: $passed_tests
- **Failed**: $failed_tests
- **Success Rate**: $(( passed_tests * 100 / total_tests ))%

## Detailed Test Results

| Test Name | Status | Duration | Notes |
|-----------|--------|----------|-------|
EOF

    for test_name in "${!TEST_RESULTS[@]}"; do
        local status="${TEST_RESULTS[$test_name]}"
        local duration="${TEST_DURATIONS[$test_name]}"
        local status_emoji=$([ "$status" = "PASSED" ] && echo "✅" || echo "❌")
        
        echo "| $test_name | $status_emoji $status | ${duration}s | |" >> "$report_file"
    done

    cat >> "$report_file" << EOF

## Recommendations

### Immediate Actions
EOF

    # Add recommendations based on test results
    local has_failures=false
    for test_name in "${!TEST_RESULTS[@]}"; do
        if [ "${TEST_RESULTS[$test_name]}" = "FAILED" ]; then
            has_failures=true
            break
        fi
    done

    if [ "$has_failures" = true ]; then
        cat >> "$report_file" << EOF
- **Address Failed Tests**: Review and resolve failed compatibility tests
- **Staging Validation**: Test failed components in staging environment
- **Documentation Update**: Update compatibility matrix with test results
EOF
    else
        cat >> "$report_file" << EOF
- **Proceed with Confidence**: All compatibility tests passed
- **Production Ready**: System is ready for production deployment
- **Regular Testing**: Schedule regular compatibility testing
EOF
    fi

    cat >> "$report_file" << EOF

### Long-term Actions
- **Automated Testing**: Implement automated compatibility testing in CI/CD
- **Monitoring**: Set up compatibility monitoring and alerting
- **Documentation**: Maintain up-to-date compatibility documentation

## Test Logs

All test logs are available in: \`$(dirname "$LOG_FILE")\`

## Next Steps

1. Review this report with the development team
2. Address any failed tests
3. Update compatibility matrix based on results
4. Schedule regular compatibility testing

---
*Report generated by PA Ecosystem Compatibility Testing System*
EOF

    success "Compatibility report generated: $report_file"
    echo "$report_file"
}

# Main compatibility testing process
main() {
    local START_TIME=$(date +%s)
    
    echo -e "${BLUE}🔍 Comprehensive Compatibility Testing${NC}"
    echo -e "${BLUE}=====================================${NC}"
    echo "Framework: ${FRAMEWORK:-all}"
    echo "Generate report: $GENERATE_REPORT"
    echo "Log file: $LOG_FILE"
    echo ""
    
    log "Starting comprehensive compatibility testing"
    
    # Run all compatibility tests
    info "Running all compatibility tests..."
    
    # 1. Version compatibility validation
    run_test "Version Compatibility Validation" \
        "$SCRIPT_DIR/validate-compatibility.sh" \
        "$([ -n "$FRAMEWORK" ] && echo "--framework $FRAMEWORK" || echo "--check-all")"
    
    # 2. API compatibility testing
    run_test "API Compatibility Testing" \
        "$SCRIPT_DIR/api-compatibility-test.sh" \
        "$([ -n "$FRAMEWORK" ] && echo "--framework $FRAMEWORK" || echo "")"
    
    # 3. Database compatibility testing
    run_test "Database Compatibility Testing" \
        "$SCRIPT_DIR/database-compatibility-test.sh" \
        "$([ -n "$FRAMEWORK" ] && echo "--framework $FRAMEWORK" || echo "")"
    
    # 4. Integration compatibility testing
    run_test "Integration Compatibility Testing" \
        "$SCRIPT_DIR/integration-compatibility-test.sh" \
        "$([ -n "$FRAMEWORK" ] && echo "--framework $FRAMEWORK" || echo "")"
    
    # Generate report if requested
    if [ "$GENERATE_REPORT" = true ]; then
        local report_file=$(generate_report)
        echo ""
        echo -e "${GREEN}📊 Compatibility Report Generated${NC}"
        echo -e "${GREEN}===============================${NC}"
        echo "Report file: $report_file"
    fi
    
    # Summary
    echo ""
    echo -e "${GREEN}📋 Compatibility Testing Summary${NC}"
    echo -e "${GREEN}================================${NC}"
    
    local total_tests=0
    local passed_tests=0
    local failed_tests=0
    
    for test_name in "${!TEST_RESULTS[@]}"; do
        total_tests=$((total_tests + 1))
        local status="${TEST_RESULTS[$test_name]}"
        local duration="${TEST_DURATIONS[$test_name]}"
        
        if [ "$status" = "PASSED" ]; then
            passed_tests=$((passed_tests + 1))
            echo -e "✅ $test_name: ${GREEN}PASSED${NC} (${duration}s)"
        else
            failed_tests=$((failed_tests + 1))
            echo -e "❌ $test_name: ${RED}FAILED${NC} (${duration}s)"
        fi
    done
    
    echo ""
    echo -e "${BLUE}📊 Overall Results${NC}"
    echo -e "${BLUE}=================${NC}"
    echo "Total tests: $total_tests"
    echo "Passed: $passed_tests"
    echo "Failed: $failed_tests"
    echo "Success rate: $(( passed_tests * 100 / total_tests ))%"
    
    local total_duration=$(($(date +%s) - START_TIME))
    echo "Total duration: ${total_duration}s"
    
    echo ""
    echo -e "${BLUE}📝 Next Steps${NC}"
    echo -e "${BLUE}=============${NC}"
    echo "1. Review test results and logs"
    echo "2. Address any failed tests"
    echo "3. Update compatibility matrix"
    echo "4. Schedule regular compatibility testing"
    
    if [ "$GENERATE_REPORT" = true ]; then
        echo "5. Review generated compatibility report"
    fi
    
    echo ""
    echo "Log file: $LOG_FILE"
    
    # Exit with appropriate code
    if [ "$failed_tests" -gt 0 ]; then
        warning "Some compatibility tests failed"
        exit 1
    else
        success "All compatibility tests passed!"
        exit 0
    fi
}

# Run main function
main "$@"
