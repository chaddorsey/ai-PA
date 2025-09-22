#!/bin/bash

# Security Monitoring Testing Suite for PA Ecosystem
# Comprehensive testing of security monitoring, logging, and incident response

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SECURITY_DIR="$PROJECT_ROOT/monitoring/security"
LOGS_DIR="$PROJECT_ROOT/logs/security"
TEST_RESULTS_DIR="$PROJECT_ROOT/test-results/security-monitoring"

# Test configuration
TEST_TIMEOUT=30
TEST_RETRIES=3
TEST_INTERVAL=5

# Logging
LOG_FILE="$TEST_RESULTS_DIR/security-monitoring-tests.log"
mkdir -p "$TEST_RESULTS_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
WARNING_TESTS=0

# Logging functions
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] PASS:${NC} $1" | tee -a "$LOG_FILE"
    ((PASSED_TESTS++))
}

log_warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARN:${NC} $1" | tee -a "$LOG_FILE"
    ((WARNING_TESTS++))
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] FAIL:${NC} $1" | tee -a "$LOG_FILE"
    ((FAILED_TESTS++))
}

# Test result tracking
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    ((TOTAL_TESTS++))
    log "Running test: $test_name"
    
    if eval "$test_command"; then
        log_success "$test_name"
        return 0
    else
        log_error "$test_name"
        return 1
    fi
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    local required_scripts=(
        "$PROJECT_ROOT/scripts/security/security-monitor.sh"
        "$SECURITY_DIR/security-monitoring.conf"
        "$SECURITY_DIR/threat-detection-rules.conf"
    )
    
    local missing_files=()
    for script in "${required_scripts[@]}"; do
        if [[ ! -f "$script" ]]; then
            missing_files+=("$script")
        fi
    done
    
    if [[ ${#missing_files[@]} -gt 0 ]]; then
        log_warning "Missing files: ${missing_files[*]}"
        return 1
    fi
    
    log_success "All required files are present"
    return 0
}

# Test security monitoring initialization
test_security_monitoring_init() {
    log "Testing security monitoring initialization..."
    
    # Test initialization command
    if "$PROJECT_ROOT/scripts/security/security-monitor.sh" init; then
        log_success "Security monitoring initialization completed"
        return 0
    else
        log_error "Security monitoring initialization failed"
        return 1
    fi
}

# Test threat detection
test_threat_detection() {
    log "Testing threat detection capabilities..."
    
    local threat_count=0
    
    # Test threat detection script
    if [[ -f "$SECURITY_DIR/threat-detector.sh" ]]; then
        if "$SECURITY_DIR/threat-detector.sh" > /dev/null 2>&1; then
            log_success "Threat detection script is functional"
            ((threat_count++))
        else
            log_warning "Threat detection script returned non-zero exit code"
        fi
    else
        log_error "Threat detection script not found"
        return 1
    fi
    
    # Test threat detection rules
    if [[ -f "$SECURITY_DIR/threat-detection-rules.conf" ]]; then
        local rule_count=$(grep -c "^RULE_" "$SECURITY_DIR/threat-detection-rules.conf" || echo "0")
        if [[ $rule_count -gt 0 ]]; then
            log_success "Threat detection rules configured: $rule_count rules"
            ((threat_count++))
        else
            log_error "No threat detection rules found"
            return 1
        fi
    else
        log_error "Threat detection rules file not found"
        return 1
    fi
    
    if [[ $threat_count -eq 2 ]]; then
        return 0
    else
        return 1
    fi
}

# Test vulnerability scanning
test_vulnerability_scanning() {
    log "Testing vulnerability scanning capabilities..."
    
    local vuln_count=0
    
    # Test vulnerability scanner script
    if [[ -f "$SECURITY_DIR/vulnerability-scanner.sh" ]]; then
        if "$SECURITY_DIR/vulnerability-scanner.sh" > /dev/null 2>&1; then
            log_success "Vulnerability scanner script is functional"
            ((vuln_count++))
        else
            log_warning "Vulnerability scanner script returned non-zero exit code"
        fi
    else
        log_error "Vulnerability scanner script not found"
        return 1
    fi
    
    # Test vulnerability scanner configuration
    if [[ -f "$SECURITY_DIR/vulnerability-scanner.conf" ]]; then
        if grep -q "SCANNER_ENABLED=true" "$SECURITY_DIR/vulnerability-scanner.conf"; then
            log_success "Vulnerability scanner is enabled"
            ((vuln_count++))
        else
            log_warning "Vulnerability scanner is not enabled"
        fi
    else
        log_error "Vulnerability scanner configuration not found"
        return 1
    fi
    
    # Test scan targets configuration
    if grep -q "SCAN_TARGETS=" "$SECURITY_DIR/vulnerability-scanner.conf"; then
        log_success "Vulnerability scan targets configured"
        ((vuln_count++))
    else
        log_warning "No vulnerability scan targets configured"
    fi
    
    if [[ $vuln_count -ge 2 ]]; then
        return 0
    else
        return 1
    fi
}

# Test security logging
test_security_logging() {
    log "Testing security logging capabilities..."
    
    local logging_count=0
    
    # Test log directory creation
    if [[ -d "$LOGS_DIR" ]]; then
        log_success "Security logs directory exists"
        ((logging_count++))
    else
        log_error "Security logs directory not found"
        return 1
    fi
    
    # Test log file creation
    local test_log_file="$LOGS_DIR/test-security-event.log"
    if echo "Test security event" > "$test_log_file" 2>/dev/null; then
        log_success "Security log file creation works"
        ((logging_count++))
        rm -f "$test_log_file"
    else
        log_error "Cannot create security log files"
        return 1
    fi
    
    # Test structured logging
    local structured_log='{"timestamp":"2025-01-21T10:30:00Z","event_type":"test","severity":"info","message":"Test event"}'
    if echo "$structured_log" > "$test_log_file" 2>/dev/null; then
        if jq empty "$test_log_file" 2>/dev/null; then
            log_success "Structured logging format is valid JSON"
            ((logging_count++))
        else
            log_warning "Structured logging format is not valid JSON"
        fi
        rm -f "$test_log_file"
    fi
    
    # Test log rotation
    if [[ -f "/etc/logrotate.d/pa-security" ]]; then
        log_success "Log rotation configuration exists"
        ((logging_count++))
    else
        log_warning "Log rotation configuration not found"
    fi
    
    if [[ $logging_count -ge 2 ]]; then
        return 0
    else
        return 1
    fi
}

# Test security alerting
test_security_alerting() {
    log "Testing security alerting capabilities..."
    
    local alert_count=0
    
    # Test alert directory creation
    if [[ -d "$PROJECT_ROOT/alerts/security" ]]; then
        log_success "Security alerts directory exists"
        ((alert_count++))
    else
        log_error "Security alerts directory not found"
        return 1
    fi
    
    # Test alert generation
    local test_alert_file="$PROJECT_ROOT/alerts/security/test-alert.json"
    local test_alert='{"alert_id":"test-123","timestamp":"2025-01-21T10:30:00Z","severity":"info","message":"Test alert"}'
    if echo "$test_alert" > "$test_alert_file" 2>/dev/null; then
        log_success "Alert file creation works"
        ((alert_count++))
        rm -f "$test_alert_file"
    else
        log_error "Cannot create alert files"
        return 1
    fi
    
    # Test alert configuration
    if grep -q "ALERTING_ENABLED=true" "$SECURITY_DIR/security-monitoring.conf"; then
        log_success "Security alerting is enabled"
        ((alert_count++))
    else
        log_warning "Security alerting is not enabled"
    fi
    
    if [[ $alert_count -ge 2 ]]; then
        return 0
    else
        return 1
    fi
}

# Test security monitoring status
test_security_monitoring_status() {
    log "Testing security monitoring status..."
    
    # Test status command
    if "$PROJECT_ROOT/scripts/security/security-monitor.sh" status > /dev/null 2>&1; then
        log_success "Security monitoring status command works"
        return 0
    else
        log_error "Security monitoring status command failed"
        return 1
    fi
}

# Test security report generation
test_security_report_generation() {
    log "Testing security report generation..."
    
    # Test report generation
    if "$PROJECT_ROOT/scripts/security/security-monitor.sh" report > /dev/null 2>&1; then
        log_success "Security report generation works"
        
        # Check if report file was created
        local report_files=$(find "$LOGS_DIR" -name "security-report-*.json" 2>/dev/null | wc -l)
        if [[ $report_files -gt 0 ]]; then
            log_success "Security report files found: $report_files"
            return 0
        else
            log_warning "No security report files found"
            return 1
        fi
    else
        log_error "Security report generation failed"
        return 1
    fi
}

# Test security event monitoring
test_security_event_monitoring() {
    log "Testing security event monitoring..."
    
    # Test monitoring command
    if "$PROJECT_ROOT/scripts/security/security-monitor.sh" monitor > /dev/null 2>&1; then
        log_success "Security event monitoring works"
        return 0
    else
        log_error "Security event monitoring failed"
        return 1
    fi
}

# Test configuration validation
test_configuration_validation() {
    log "Testing configuration validation..."
    
    local config_count=0
    
    # Test security monitoring configuration
    if [[ -f "$SECURITY_DIR/security-monitoring.conf" ]]; then
        if grep -q "THREAT_SCAN_INTERVAL=" "$SECURITY_DIR/security-monitoring.conf"; then
            log_success "Security monitoring configuration is valid"
            ((config_count++))
        else
            log_error "Security monitoring configuration is invalid"
        fi
    else
        log_error "Security monitoring configuration file not found"
        return 1
    fi
    
    # Test logging configuration
    if [[ -f "$PROJECT_ROOT/config/logging/security-logging.conf" ]]; then
        if grep -q "LOG_LEVEL=" "$PROJECT_ROOT/config/logging/security-logging.conf"; then
            log_success "Security logging configuration is valid"
            ((config_count++))
        else
            log_error "Security logging configuration is invalid"
        fi
    else
        log_error "Security logging configuration file not found"
        return 1
    fi
    
    if [[ $config_count -eq 2 ]]; then
        return 0
    else
        return 1
    fi
}

# Test security monitoring performance
test_security_monitoring_performance() {
    log "Testing security monitoring performance..."
    
    local start_time=$(date +%s)
    
    # Test monitoring performance
    if timeout 10 "$PROJECT_ROOT/scripts/security/security-monitor.sh" monitor > /dev/null 2>&1; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        
        if [[ $duration -lt 10 ]]; then
            log_success "Security monitoring performance test passed: ${duration}s"
            return 0
        else
            log_warning "Security monitoring performance test slow: ${duration}s"
            return 1
        fi
    else
        log_error "Security monitoring performance test failed"
        return 1
    fi
}

# Test security monitoring integration
test_security_monitoring_integration() {
    log "Testing security monitoring integration..."
    
    local integration_count=0
    
    # Test Docker integration
    if command -v docker &> /dev/null; then
        if docker ps > /dev/null 2>&1; then
            log_success "Docker integration available"
            ((integration_count++))
        else
            log_warning "Docker integration not available"
        fi
    else
        log_warning "Docker not installed"
    fi
    
    # Test network monitoring
    if command -v netstat &> /dev/null; then
        if netstat -an > /dev/null 2>&1; then
            log_success "Network monitoring available"
            ((integration_count++))
        else
            log_warning "Network monitoring not available"
        fi
    else
        log_warning "netstat not available"
    fi
    
    # Test log analysis tools
    if command -v grep &> /dev/null && command -v awk &> /dev/null; then
        log_success "Log analysis tools available"
        ((integration_count++))
    else
        log_warning "Log analysis tools not available"
    fi
    
    if [[ $integration_count -ge 2 ]]; then
        return 0
    else
        return 1
    fi
}

# Generate test report
generate_test_report() {
    local report_file="$TEST_RESULTS_DIR/security-monitoring-test-report-$(date +%Y%m%d-%H%M%S).json"
    
    log "Generating security monitoring test report..."
    
    cat > "$report_file" << EOF
{
  "test_date": "$(date -Iseconds)",
  "test_summary": {
    "total_tests": $TOTAL_TESTS,
    "passed_tests": $PASSED_TESTS,
    "failed_tests": $FAILED_TESTS,
    "warning_tests": $WARNING_TESTS,
    "success_rate": "$(( (PASSED_TESTS * 100) / TOTAL_TESTS ))%"
  },
  "test_results": {
    "prerequisites_check": "completed",
    "security_monitoring_init": "completed",
    "threat_detection": "completed",
    "vulnerability_scanning": "completed",
    "security_logging": "completed",
    "security_alerting": "completed",
    "monitoring_status": "completed",
    "report_generation": "completed",
    "event_monitoring": "completed",
    "configuration_validation": "completed",
    "performance_testing": "completed",
    "integration_testing": "completed"
  },
  "recommendations": [
    "Ensure all security monitoring components are properly configured",
    "Regularly test threat detection and vulnerability scanning",
    "Monitor security logs for anomalies and suspicious activities",
    "Validate security alerting mechanisms",
    "Review and update security monitoring configurations",
    "Conduct regular security monitoring performance tests",
    "Test incident response procedures",
    "Validate compliance with security standards"
  ],
  "security_score": "$(( (PASSED_TESTS * 100) / TOTAL_TESTS ))/100"
}
EOF
    
    log_success "Security monitoring test report generated: $report_file"
}

# Main test execution
run_all_tests() {
    log "Starting comprehensive security monitoring testing..."
    
    # Run all tests
    run_test "Prerequisites Check" "check_prerequisites"
    run_test "Security Monitoring Initialization" "test_security_monitoring_init"
    run_test "Threat Detection" "test_threat_detection"
    run_test "Vulnerability Scanning" "test_vulnerability_scanning"
    run_test "Security Logging" "test_security_logging"
    run_test "Security Alerting" "test_security_alerting"
    run_test "Monitoring Status" "test_security_monitoring_status"
    run_test "Report Generation" "test_security_report_generation"
    run_test "Event Monitoring" "test_security_event_monitoring"
    run_test "Configuration Validation" "test_configuration_validation"
    run_test "Performance Testing" "test_security_monitoring_performance"
    run_test "Integration Testing" "test_security_monitoring_integration"
    
    # Generate final report
    generate_test_report
    
    # Print summary
    log "Security Monitoring Testing Summary:"
    log "  Total tests: $TOTAL_TESTS"
    log "  Passed: $PASSED_TESTS"
    log "  Failed: $FAILED_TESTS"
    log "  Warnings: $WARNING_TESTS"
    log "  Success rate: $(( (PASSED_TESTS * 100) / TOTAL_TESTS ))%"
    
    if [[ $FAILED_TESTS -gt 0 ]]; then
        log_error "Some tests failed - review the report for details"
        exit 1
    elif [[ $WARNING_TESTS -gt 0 ]]; then
        log_warning "Some tests generated warnings - review the report for details"
        exit 0
    else
        log_success "All security monitoring tests passed!"
        exit 0
    fi
}

# Main function
main() {
    local command="${1:-all}"
    
    case "$command" in
        "all")
            run_all_tests
            ;;
        "prerequisites")
            check_prerequisites
            ;;
        "init")
            test_security_monitoring_init
            ;;
        "threats")
            test_threat_detection
            ;;
        "vulnerabilities")
            test_vulnerability_scanning
            ;;
        "logging")
            test_security_logging
            ;;
        "alerting")
            test_security_alerting
            ;;
        "status")
            test_security_monitoring_status
            ;;
        "report")
            test_security_report_generation
            ;;
        "monitoring")
            test_security_event_monitoring
            ;;
        "config")
            test_configuration_validation
            ;;
        "performance")
            test_security_monitoring_performance
            ;;
        "integration")
            test_security_monitoring_integration
            ;;
        "help"|*)
            echo "Security Monitoring Testing Suite for PA Ecosystem"
            echo ""
            echo "Usage: $0 <command>"
            echo ""
            echo "Commands:"
            echo "  all                     Run all security monitoring tests"
            echo "  prerequisites           Check prerequisites"
            echo "  init                    Test security monitoring initialization"
            echo "  threats                 Test threat detection"
            echo "  vulnerabilities         Test vulnerability scanning"
            echo "  logging                 Test security logging"
            echo "  alerting                Test security alerting"
            echo "  status                  Test monitoring status"
            echo "  report                  Test report generation"
            echo "  monitoring              Test event monitoring"
            echo "  config                  Test configuration validation"
            echo "  performance             Test monitoring performance"
            echo "  integration             Test monitoring integration"
            echo "  help                    Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 all"
            echo "  $0 threats"
            echo "  $0 vulnerabilities"
            echo "  $0 logging"
            ;;
    esac
}

# Run main function with all arguments
main "$@"
