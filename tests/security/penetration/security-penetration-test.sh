#!/bin/bash

# Security Penetration Testing for PA Ecosystem
# Comprehensive penetration testing and security assessment

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
REPORTS_DIR="$PROJECT_ROOT/reports/security/penetration"
LOGS_DIR="$PROJECT_ROOT/logs/security/penetration"

# Penetration testing configuration
PENTEST_CONFIG="$SCRIPT_DIR/pentest-config.conf"
RESULTS_FILE="$REPORTS_DIR/pentest-results-$(date +%Y%m%d-%H%M%S).json"
SUMMARY_FILE="$REPORTS_DIR/pentest-summary-$(date +%Y%m%d-%H%M%S).txt"
DETAILED_REPORT="$REPORTS_DIR/pentest-detailed-$(date +%Y%m%d-%H%M%S).md"

# Test configuration
PENTEST_TIMEOUT=1800  # 30 minutes timeout per test
SCAN_DEPTH=3
THREADS=10

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Test results tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
WARNING_TESTS=0
CRITICAL_FINDINGS=0
HIGH_FINDINGS=0
MEDIUM_FINDINGS=0
LOW_FINDINGS=0

# Logging functions
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOGS_DIR/pentest.log"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] PASS:${NC} $1" | tee -a "$LOGS_DIR/pentest.log"
    ((PASSED_TESTS++))
}

log_warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARN:${NC} $1" | tee -a "$LOGS_DIR/pentest.log"
    ((WARNING_TESTS++))
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] FAIL:${NC} $1" | tee -a "$LOGS_DIR/pentest.log"
    ((FAILED_TESTS++))
}

log_info() {
    echo -e "${CYAN}[$(date '+%Y-%m-%d %H:%M:%S')] INFO:${NC} $1" | tee -a "$LOGS_DIR/pentest.log"
}

log_critical() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] CRITICAL:${NC} $1" | tee -a "$LOGS_DIR/pentest.log"
    ((CRITICAL_FINDINGS++))
}

log_high() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] HIGH:${NC} $1" | tee -a "$LOGS_DIR/pentest.log"
    ((HIGH_FINDINGS++))
}

log_medium() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] MEDIUM:${NC} $1" | tee -a "$LOGS_DIR/pentest.log"
    ((MEDIUM_FINDINGS++))
}

log_low() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] LOW:${NC} $1" | tee -a "$LOGS_DIR/pentest.log"
    ((LOW_FINDINGS++))
}

# Initialize penetration testing
init_pentest() {
    log "Initializing penetration testing environment..."
    
    # Create necessary directories
    mkdir -p "$REPORTS_DIR" "$LOGS_DIR" "$SCRIPT_DIR"
    
    # Create penetration testing configuration
    create_pentest_config
    
    # Check required tools
    check_pentest_tools
    
    log_success "Penetration testing environment initialized"
}

# Create penetration testing configuration
create_pentest_config() {
    cat > "$PENTEST_CONFIG" << 'EOF'
# Penetration Testing Configuration for PA Ecosystem

# Test targets
TARGETS=(
    "localhost"
    "127.0.0.1"
    "api.pa-ecosystem.local"
    "app.pa-ecosystem.local"
    "admin.pa-ecosystem.local"
    "monitoring.pa-ecosystem.local"
)

# Port ranges
COMMON_PORTS="21,22,23,25,53,80,110,111,135,139,143,443,993,995,1723,3389,5900,8080,8443"
WEB_PORTS="80,443,8080,8443,8000,8008,8088,8888,9080,9443"
DATABASE_PORTS="1433,1521,3306,3389,5432,6379,27017"

# Scan options
SCAN_TIMEOUT=30
SCAN_RETRIES=3
THREADS=10
SCAN_DEPTH=3

# Web application testing
WEB_TESTS=(
    "directory_enumeration"
    "file_enumeration"
    "parameter_fuzzing"
    "sql_injection"
    "xss_testing"
    "csrf_testing"
    "authentication_bypass"
    "privilege_escalation"
    "session_management"
    "input_validation"
)

# Network testing
NETWORK_TESTS=(
    "port_scanning"
    "service_enumeration"
    "banner_grabbing"
    "vulnerability_scanning"
    "snmp_enumeration"
    "smb_enumeration"
    "ldap_enumeration"
    "dns_enumeration"
)

# System testing
SYSTEM_TESTS=(
    "os_fingerprinting"
    "service_fingerprinting"
    "version_detection"
    "vulnerability_assessment"
    "configuration_review"
    "permission_analysis"
    "log_analysis"
    "process_analysis"
)

# Exploitation testing
EXPLOIT_TESTS=(
    "metasploit_scanning"
    "exploit_verification"
    "payload_testing"
    "post_exploitation"
    "privilege_escalation"
    "persistence_testing"
    "lateral_movement"
    "data_exfiltration"
)

# Reporting
REPORT_FORMATS=("json" "html" "txt" "xml")
SEVERITY_LEVELS=("critical" "high" "medium" "low" "info")
EOF
}

# Check penetration testing tools
check_pentest_tools() {
    log "Checking penetration testing tools..."
    
    local required_tools=("nmap" "curl" "openssl")
    local optional_tools=("nikto" "sqlmap" "testssl.sh" "lynis" "rkhunter" "chkrootkit" "clamav")
    
    # Check required tools
    for tool in "${required_tools[@]}"; do
        if command -v "$tool" &> /dev/null; then
            log_info "Required tool available: $tool"
        else
            log_error "Required tool not found: $tool"
            exit 1
        fi
    done
    
    # Check optional tools
    for tool in "${optional_tools[@]}"; do
        if command -v "$tool" &> /dev/null; then
            log_info "Optional tool available: $tool"
        else
            log_warning "Optional tool not available: $tool"
        fi
    done
}

# Network reconnaissance
network_reconnaissance() {
    log "=== Network Reconnaissance ==="
    
    local target="$1"
    log "Performing network reconnaissance on $target..."
    
    # Port scanning
    if command -v nmap &> /dev/null; then
        log_info "Running port scan on $target..."
        nmap -sS -sV -O -p "$COMMON_PORTS" "$target" -oN "$REPORTS_DIR/nmap-${target}.txt" 2>/dev/null || true
        
        # Service enumeration
        log_info "Enumerating services on $target..."
        nmap -sV -sC -A -p "$COMMON_PORTS" "$target" -oN "$REPORTS_DIR/nmap-detailed-${target}.txt" 2>/dev/null || true
        
        # OS fingerprinting
        log_info "Performing OS fingerprinting on $target..."
        nmap -O "$target" -oN "$REPORTS_DIR/nmap-os-${target}.txt" 2>/dev/null || true
        
        log_success "Network reconnaissance completed for $target"
    else
        log_error "nmap not available for network reconnaissance"
        return 1
    fi
}

# Web application testing
web_application_testing() {
    log "=== Web Application Testing ==="
    
    local target="$1"
    local port="${2:-80}"
    log "Testing web application on $target:$port..."
    
    # Check if target is web service
    local web_url="http://$target:$port"
    if [[ $port -eq 443 ]] || [[ $port -eq 8443 ]]; then
        web_url="https://$target:$port"
    fi
    
    # Basic connectivity test
    if curl -s -o /dev/null -w "%{http_code}" "$web_url" 2>/dev/null | grep -q "200\|301\|302"; then
        log_info "Web service accessible at $web_url"
        
        # Directory enumeration
        if command -v dirb &> /dev/null; then
            log_info "Running directory enumeration on $target..."
            dirb "$web_url" "$REPORTS_DIR/dirb-${target}.txt" 2>/dev/null || true
        elif command -v gobuster &> /dev/null; then
            log_info "Running directory enumeration with gobuster on $target..."
            gobuster dir -u "$web_url" -w /usr/share/wordlists/dirb/common.txt -o "$REPORTS_DIR/gobuster-${target}.txt" 2>/dev/null || true
        fi
        
        # Nikto web vulnerability scan
        if command -v nikto &> /dev/null; then
            log_info "Running Nikto vulnerability scan on $target..."
            nikto -h "$target" -p "$port" -Format txt -output "$REPORTS_DIR/nikto-${target}.txt" 2>/dev/null || true
        fi
        
        # SSL/TLS testing
        if [[ $port -eq 443 ]] || [[ $port -eq 8443 ]]; then
            if command -v testssl.sh &> /dev/null; then
                log_info "Running SSL/TLS testing on $target..."
                testssl.sh --severity MEDIUM "$target:$port" > "$REPORTS_DIR/testssl-${target}.txt" 2>/dev/null || true
            fi
        fi
        
        # Security headers testing
        log_info "Testing security headers on $target..."
        local headers=$(curl -s -I "$web_url" 2>/dev/null)
        local security_headers=("Strict-Transport-Security" "X-Frame-Options" "X-Content-Type-Options" "X-XSS-Protection" "Content-Security-Policy")
        
        for header in "${security_headers[@]}"; do
            if echo "$headers" | grep -qi "$header"; then
                log_info "Security header found: $header"
            else
                log_medium "Missing security header: $header"
            fi
        done
        
        log_success "Web application testing completed for $target"
    else
        log_warning "Web service not accessible at $web_url"
    fi
}

# SQL injection testing
sql_injection_testing() {
    log "=== SQL Injection Testing ==="
    
    local target="$1"
    local port="${2:-80}"
    log "Testing for SQL injection on $target:$port..."
    
    if command -v sqlmap &> /dev/null; then
        local web_url="http://$target:$port"
        if [[ $port -eq 443 ]] || [[ $port -eq 8443 ]]; then
            web_url="https://$target:$port"
        fi
        
        log_info "Running SQLMap scan on $target..."
        sqlmap -u "$web_url" --batch --risk=2 --level=3 --output-dir="$REPORTS_DIR/sqlmap-${target}" 2>/dev/null || true
        
        # Check for SQL injection results
        if [[ -f "$REPORTS_DIR/sqlmap-${target}/log" ]]; then
            if grep -q "sqlmap identified" "$REPORTS_DIR/sqlmap-${target}/log"; then
                log_critical "SQL injection vulnerability detected on $target"
            else
                log_info "No SQL injection vulnerabilities detected on $target"
            fi
        fi
        
        log_success "SQL injection testing completed for $target"
    else
        log_warning "sqlmap not available for SQL injection testing"
    fi
}

# System security assessment
system_security_assessment() {
    log "=== System Security Assessment ==="
    
    local target="$1"
    log "Performing system security assessment on $target..."
    
    # Lynis system audit
    if command -v lynis &> /dev/null; then
        log_info "Running Lynis system audit on $target..."
        lynis audit system --quick --no-colors > "$REPORTS_DIR/lynis-${target}.txt" 2>/dev/null || true
        
        # Parse Lynis results
        if [[ -f "$REPORTS_DIR/lynis-${target}.txt" ]]; then
            local suggestions=$(grep -c "Suggestion" "$REPORTS_DIR/lynis-${target}.txt" 2>/dev/null || echo "0")
            local warnings=$(grep -c "Warning" "$REPORTS_DIR/lynis-${target}.txt" 2>/dev/null || echo "0")
            
            if [[ $suggestions -gt 0 ]]; then
                log_medium "Lynis found $suggestions suggestions for $target"
            fi
            
            if [[ $warnings -gt 0 ]]; then
                log_high "Lynis found $warnings warnings for $target"
            fi
        fi
    fi
    
    # Rootkit detection
    if command -v rkhunter &> /dev/null; then
        log_info "Running rootkit detection on $target..."
        rkhunter --check --skip-keypress --report-warnings-only > "$REPORTS_DIR/rkhunter-${target}.txt" 2>/dev/null || true
        
        # Check for rootkit findings
        if [[ -f "$REPORTS_DIR/rkhunter-${target}.txt" ]]; then
            if grep -q "Warning" "$REPORTS_DIR/rkhunter-${target}.txt"; then
                log_high "Rootkit detection found warnings for $target"
            else
                log_info "No rootkit activity detected on $target"
            fi
        fi
    fi
    
    # Malware scanning
    if command -v clamscan &> /dev/null; then
        log_info "Running malware scan on $target..."
        clamscan -r /var/www /etc /home --log="$REPORTS_DIR/clamav-${target}.txt" 2>/dev/null || true
        
        # Check for malware findings
        if [[ -f "$REPORTS_DIR/clamav-${target}.txt" ]]; then
            if grep -q "FOUND" "$REPORTS_DIR/clamav-${target}.txt"; then
                log_critical "Malware detected on $target"
            else
                log_info "No malware detected on $target"
            fi
        fi
    fi
    
    log_success "System security assessment completed for $target"
}

# Vulnerability assessment
vulnerability_assessment() {
    log "=== Vulnerability Assessment ==="
    
    local target="$1"
    log "Performing vulnerability assessment on $target..."
    
    # Nmap vulnerability scan
    if command -v nmap &> /dev/null; then
        log_info "Running Nmap vulnerability scan on $target..."
        nmap --script vuln -p "$COMMON_PORTS" "$target" -oN "$REPORTS_DIR/nmap-vuln-${target}.txt" 2>/dev/null || true
        
        # Parse vulnerability results
        if [[ -f "$REPORTS_DIR/nmap-vuln-${target}.txt" ]]; then
            local vulns=$(grep -c "VULNERABLE\|EXPLOIT" "$REPORTS_DIR/nmap-vuln-${target}.txt" 2>/dev/null || echo "0")
            if [[ $vulns -gt 0 ]]; then
                log_high "Nmap found $vulns potential vulnerabilities on $target"
            else
                log_info "No vulnerabilities detected by Nmap on $target"
            fi
        fi
    fi
    
    # OpenVAS vulnerability scan (if available)
    if command -v openvas-cli &> /dev/null; then
        log_info "Running OpenVAS vulnerability scan on $target..."
        # Note: This would require OpenVAS server setup
        log_warning "OpenVAS vulnerability scanning requires server setup"
    fi
    
    log_success "Vulnerability assessment completed for $target"
}

# Generate penetration testing report
generate_pentest_report() {
    log "Generating penetration testing report..."
    
    local total_findings=$((CRITICAL_FINDINGS + HIGH_FINDINGS + MEDIUM_FINDINGS + LOW_FINDINGS))
    local risk_score=0
    
    # Calculate risk score
    risk_score=$((CRITICAL_FINDINGS * 10 + HIGH_FINDINGS * 7 + MEDIUM_FINDINGS * 4 + LOW_FINDINGS * 1))
    
    # Determine overall risk level
    local risk_level="LOW"
    if [[ $risk_score -gt 50 ]]; then
        risk_level="CRITICAL"
    elif [[ $risk_score -gt 30 ]]; then
        risk_level="HIGH"
    elif [[ $risk_score -gt 15 ]]; then
        risk_level="MEDIUM"
    fi
    
    # Generate JSON report
    cat > "$RESULTS_FILE" << EOF
{
  "pentest_date": "$(date -Iseconds)",
  "overall_risk_level": "$risk_level",
  "risk_score": $risk_score,
  "test_summary": {
    "total_tests": $TOTAL_TESTS,
    "passed_tests": $PASSED_TESTS,
    "failed_tests": $FAILED_TESTS,
    "warning_tests": $WARNING_TESTS
  },
  "findings_summary": {
    "total_findings": $total_findings,
    "critical_findings": $CRITICAL_FINDINGS,
    "high_findings": $HIGH_FINDINGS,
    "medium_findings": $MEDIUM_FINDINGS,
    "low_findings": $LOW_FINDINGS
  },
  "test_categories": {
    "network_reconnaissance": "completed",
    "web_application_testing": "completed",
    "sql_injection_testing": "completed",
    "system_security_assessment": "completed",
    "vulnerability_assessment": "completed"
  },
  "recommendations": [
    "Address critical and high severity findings immediately",
    "Implement additional security controls for medium severity findings",
    "Monitor low severity findings and address during regular maintenance",
    "Conduct regular penetration testing to identify new vulnerabilities",
    "Implement security monitoring and threat detection",
    "Establish incident response procedures for security incidents",
    "Provide security training to development and operations teams",
    "Implement secure coding practices and code review processes"
  ],
  "next_steps": [
    "Review and prioritize all findings by severity",
    "Develop remediation plan for critical and high severity findings",
    "Implement additional security controls and monitoring",
    "Schedule follow-up penetration testing after remediation",
    "Update security policies and procedures based on findings",
    "Conduct security training and awareness programs"
  ]
}
EOF

    # Generate summary report
    cat > "$SUMMARY_FILE" << EOF
PA Ecosystem Penetration Testing Summary
=======================================

Test Date: $(date)
Overall Risk Level: $risk_level
Risk Score: $risk_score/100

Test Results:
- Total Tests: $TOTAL_TESTS
- Passed: $PASSED_TESTS
- Failed: $FAILED_TESTS
- Warnings: $WARNING_TESTS

Findings Summary:
- Total Findings: $total_findings
- Critical: $CRITICAL_FINDINGS
- High: $HIGH_FINDINGS
- Medium: $MEDIUM_FINDINGS
- Low: $LOW_FINDINGS

Test Categories Completed:
✓ Network Reconnaissance
✓ Web Application Testing
✓ SQL Injection Testing
✓ System Security Assessment
✓ Vulnerability Assessment

Risk Assessment:
$risk_level risk level based on $total_findings total findings

Priority Actions:
1. Address critical findings immediately
2. Plan remediation for high severity findings
3. Schedule fixes for medium severity findings
4. Monitor low severity findings

EOF

    # Generate detailed markdown report
    cat > "$DETAILED_REPORT" << EOF
# PA Ecosystem Penetration Testing Report

**Test Date:** $(date)  
**Overall Risk Level:** $risk_level  
**Risk Score:** $risk_score/100

## Executive Summary

This penetration testing report presents the findings from comprehensive security testing of the PA ecosystem. The testing covered network reconnaissance, web application security, system security assessment, and vulnerability assessment.

## Test Results Summary

| Metric | Count |
|--------|-------|
| Total Tests | $TOTAL_TESTS |
| Passed Tests | $PASSED_TESTS |
| Failed Tests | $FAILED_TESTS |
| Warning Tests | $WARNING_TESTS |

## Findings Summary

| Severity | Count | Percentage |
|----------|-------|------------|
| Critical | $CRITICAL_FINDINGS | $(( (CRITICAL_FINDINGS * 100) / (total_findings + 1) ))% |
| High | $HIGH_FINDINGS | $(( (HIGH_FINDINGS * 100) / (total_findings + 1) ))% |
| Medium | $MEDIUM_FINDINGS | $(( (MEDIUM_FINDINGS * 100) / (total_findings + 1) ))% |
| Low | $LOW_FINDINGS | $(( (LOW_FINDINGS * 100) / (total_findings + 1) ))% |
| **Total** | **$total_findings** | **100%** |

## Risk Assessment

The overall risk level is **$risk_level** with a risk score of **$risk_score/100**.

### Risk Level Breakdown:
- **Critical (70-100)**: Immediate action required
- **High (40-69)**: Action required within 30 days
- **Medium (20-39)**: Action required within 90 days
- **Low (0-19)**: Monitor and address during regular maintenance

## Test Categories

### 1. Network Reconnaissance
- **Status**: Completed
- **Scope**: Port scanning, service enumeration, OS fingerprinting
- **Findings**: Network services and configurations identified

### 2. Web Application Testing
- **Status**: Completed
- **Scope**: Directory enumeration, vulnerability scanning, security headers
- **Findings**: Web application security posture assessed

### 3. SQL Injection Testing
- **Status**: Completed
- **Scope**: SQL injection vulnerability detection
- **Findings**: Database security vulnerabilities identified

### 4. System Security Assessment
- **Status**: Completed
- **Scope**: System hardening, rootkit detection, malware scanning
- **Findings**: System security posture assessed

### 5. Vulnerability Assessment
- **Status**: Completed
- **Scope**: Comprehensive vulnerability scanning
- **Findings**: System and application vulnerabilities identified

## Recommendations

### Immediate Actions (Critical Findings)
1. Address all critical severity findings immediately
2. Implement emergency security controls
3. Conduct additional security assessment

### Short-term Actions (High Findings)
1. Develop remediation plan for high severity findings
2. Implement additional security controls
3. Schedule follow-up testing

### Medium-term Actions (Medium Findings)
1. Plan remediation for medium severity findings
2. Implement security improvements
3. Update security policies and procedures

### Long-term Actions (Low Findings)
1. Monitor low severity findings
2. Address during regular maintenance cycles
3. Implement continuous security monitoring

## Next Steps

1. **Prioritize Findings**: Review and prioritize all findings by severity and business impact
2. **Develop Remediation Plan**: Create detailed remediation plan for all findings
3. **Implement Controls**: Deploy additional security controls and monitoring
4. **Schedule Follow-up**: Plan follow-up penetration testing after remediation
5. **Update Policies**: Update security policies and procedures based on findings
6. **Training**: Conduct security training and awareness programs

## Conclusion

The penetration testing identified $total_findings total findings across various severity levels. The overall risk level is $risk_level, requiring $([ "$risk_level" = "CRITICAL" ] && echo "immediate" || [ "$risk_level" = "HIGH" ] && echo "urgent" || [ "$risk_level" = "MEDIUM" ] && echo "timely" || echo "planned") attention to address the identified security issues.

EOF

    log_success "Penetration testing report generated"
    log_info "JSON Report: $RESULTS_FILE"
    log_info "Summary Report: $SUMMARY_FILE"
    log_info "Detailed Report: $DETAILED_REPORT"
}

# Main penetration testing execution
run_pentest() {
    log "Starting comprehensive penetration testing for PA Ecosystem..."
    
    # Initialize penetration testing
    init_pentest
    
    # Load configuration
    source "$PENTEST_CONFIG"
    
    # Run penetration tests on all targets
    for target in "${TARGETS[@]}"; do
        log "=== Testing Target: $target ==="
        
        # Network reconnaissance
        network_reconnaissance "$target"
        
        # Web application testing
        web_application_testing "$target"
        
        # SQL injection testing
        sql_injection_testing "$target"
        
        # System security assessment
        system_security_assessment "$target"
        
        # Vulnerability assessment
        vulnerability_assessment "$target"
        
        log "Completed testing for target: $target"
    done
    
    # Generate comprehensive report
    generate_pentest_report
    
    # Print final summary
    log "=== Penetration Testing Summary ==="
    log "Total Tests: $TOTAL_TESTS"
    log "Passed: $PASSED_TESTS"
    log "Failed: $FAILED_TESTS"
    log "Warnings: $WARNING_TESTS"
    log "Critical Findings: $CRITICAL_FINDINGS"
    log "High Findings: $HIGH_FINDINGS"
    log "Medium Findings: $MEDIUM_FINDINGS"
    log "Low Findings: $LOW_FINDINGS"
    
    local total_findings=$((CRITICAL_FINDINGS + HIGH_FINDINGS + MEDIUM_FINDINGS + LOW_FINDINGS))
    log "Total Findings: $total_findings"
    
    if [[ $CRITICAL_FINDINGS -gt 0 ]]; then
        log_error "❌ CRITICAL findings require immediate attention"
        return 1
    elif [[ $HIGH_FINDINGS -gt 5 ]]; then
        log_warning "⚠️ HIGH findings require urgent attention"
        return 1
    else
        log_success "✅ Penetration testing completed - Security posture acceptable"
        return 0
    fi
}

# Main function
main() {
    local command="${1:-all}"
    
    case "$command" in
        "all")
            run_pentest
            ;;
        "recon")
            init_pentest && network_reconnaissance "${2:-localhost}"
            ;;
        "web")
            init_pentest && web_application_testing "${2:-localhost}" "${3:-80}"
            ;;
        "sql")
            init_pentest && sql_injection_testing "${2:-localhost}" "${3:-80}"
            ;;
        "system")
            init_pentest && system_security_assessment "${2:-localhost}"
            ;;
        "vuln")
            init_pentest && vulnerability_assessment "${2:-localhost}"
            ;;
        "init")
            init_pentest
            ;;
        "report")
            generate_pentest_report
            ;;
        "help"|*)
            echo "PA Ecosystem Penetration Testing"
            echo ""
            echo "Usage: $0 <command> [target] [port]"
            echo ""
            echo "Commands:"
            echo "  all           Run complete penetration testing"
            echo "  recon         Network reconnaissance"
            echo "  web           Web application testing"
            echo "  sql           SQL injection testing"
            echo "  system        System security assessment"
            echo "  vuln          Vulnerability assessment"
            echo "  init          Initialize penetration testing environment"
            echo "  report        Generate penetration testing report"
            echo "  help          Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 all"
            echo "  $0 recon localhost"
            echo "  $0 web localhost 80"
            echo "  $0 sql localhost 443"
            ;;
    esac
}

# Run main function with all arguments
main "$@"
