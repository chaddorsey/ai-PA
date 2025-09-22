#!/bin/bash

# TLS/SSL Security Testing Suite for PA Ecosystem
# Comprehensive testing of TLS/SSL implementation and security

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
TLS_CONFIG_DIR="$PROJECT_ROOT/config/tls"
TEST_RESULTS_DIR="$PROJECT_ROOT/test-results/tls"
CERT_DIR="$TLS_CONFIG_DIR/live"

# Test configuration
TEST_DOMAINS=("localhost" "api.pa-ecosystem.local" "app.pa-ecosystem.local")
TEST_PORTS=(443 8443 9443)
SSL_LABS_API_URL="https://api.ssllabs.com/api/v3/analyze"
TEST_TIMEOUT=30

# Logging
LOG_FILE="$TEST_RESULTS_DIR/tls-security-tests.log"
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

# Check if required tools are available
check_prerequisites() {
    log "Checking prerequisites..."
    
    local required_tools=("openssl" "curl" "nmap" "testssl.sh")
    local missing_tools=()
    
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            missing_tools+=("$tool")
        fi
    done
    
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        log_warning "Missing tools: ${missing_tools[*]}"
        log "Install missing tools for comprehensive testing:"
        for tool in "${missing_tools[@]}"; do
            case "$tool" in
                "openssl")
                    echo "  Ubuntu/Debian: sudo apt-get install openssl"
                    echo "  macOS: brew install openssl"
                    ;;
                "curl")
                    echo "  Ubuntu/Debian: sudo apt-get install curl"
                    echo "  macOS: brew install curl"
                    ;;
                "nmap")
                    echo "  Ubuntu/Debian: sudo apt-get install nmap"
                    echo "  macOS: brew install nmap"
                    ;;
                "testssl.sh")
                    echo "  Download from: https://testssl.sh/"
                    ;;
            esac
        done
    else
        log_success "All required tools are available"
    fi
}

# Test certificate validity
test_certificate_validity() {
    local domain="$1"
    local cert_path="$CERT_DIR/$domain/cert.pem"
    
    if [[ ! -f "$cert_path" ]]; then
        log_error "Certificate file not found for $domain: $cert_path"
        return 1
    fi
    
    # Test certificate format
    if ! openssl x509 -in "$cert_path" -text -noout > /dev/null 2>&1; then
        log_error "Invalid certificate format for $domain"
        return 1
    fi
    
    # Test certificate expiration
    local expiry_date=$(openssl x509 -enddate -noout -in "$cert_path" | cut -d= -f2)
    local expiry_timestamp=$(date -d "$expiry_date" +%s)
    local current_timestamp=$(date +%s)
    local days_until_expiry=$(( (expiry_timestamp - current_timestamp) / 86400 ))
    
    if [[ $days_until_expiry -lt 0 ]]; then
        log_error "Certificate for $domain has expired"
        return 1
    elif [[ $days_until_expiry -lt 30 ]]; then
        log_warning "Certificate for $domain expires in $days_until_expiry days"
    fi
    
    # Test certificate chain
    local chain_path="$CERT_DIR/$domain/chain.pem"
    if [[ -f "$chain_path" ]]; then
        if ! openssl verify -CAfile "$chain_path" "$cert_path" > /dev/null 2>&1; then
            log_error "Certificate chain validation failed for $domain"
            return 1
        fi
    fi
    
    # Test private key match
    local key_path="$CERT_DIR/$domain/privkey.pem"
    if [[ -f "$key_path" ]]; then
        local cert_modulus=$(openssl x509 -noout -modulus -in "$cert_path" | openssl md5)
        local key_modulus=$(openssl rsa -noout -modulus -in "$key_path" | openssl md5)
        
        if [[ "$cert_modulus" != "$key_modulus" ]]; then
            log_error "Private key does not match certificate for $domain"
            return 1
        fi
    fi
    
    log_success "Certificate validity test passed for $domain"
    return 0
}

# Test TLS connection
test_tls_connection() {
    local domain="$1"
    local port="${2:-443}"
    
    # Test basic SSL connection
    if ! echo | timeout "$TEST_TIMEOUT" openssl s_client -connect "$domain:$port" -servername "$domain" -quiet 2>/dev/null | grep -q "Verify return code: 0"; then
        log_error "TLS connection failed for $domain:$port"
        return 1
    fi
    
    # Test protocol versions
    local protocols=("tls1" "tls1_1" "tls1_2" "tls1_3")
    local supported_protocols=()
    
    for protocol in "${protocols[@]}"; do
        if echo | timeout "$TEST_TIMEOUT" openssl s_client -connect "$domain:$port" -servername "$domain" -"$protocol" 2>/dev/null | grep -q "Verify return code: 0"; then
            supported_protocols+=("$protocol")
        fi
    done
    
    # Check for weak protocols
    local weak_protocols=("tls1" "tls1_1")
    for weak_protocol in "${weak_protocols[@]}"; do
        if [[ " ${supported_protocols[*]} " =~ " $weak_protocol " ]]; then
            log_warning "Weak protocol $weak_protocol is supported for $domain:$port"
        fi
    done
    
    # Check for strong protocols
    local strong_protocols=("tls1_2" "tls1_3")
    local has_strong_protocol=false
    for strong_protocol in "${strong_protocols[@]}"; do
        if [[ " ${supported_protocols[*]} " =~ " $strong_protocol " ]]; then
            has_strong_protocol=true
            break
        fi
    done
    
    if [[ "$has_strong_protocol" == false ]]; then
        log_error "No strong TLS protocols supported for $domain:$port"
        return 1
    fi
    
    log_success "TLS connection test passed for $domain:$port"
    return 0
}

# Test cipher suites
test_cipher_suites() {
    local domain="$1"
    local port="${2:-443}"
    
    # Get supported cipher suites
    local cipher_output=$(echo | timeout "$TEST_TIMEOUT" openssl s_client -connect "$domain:$port" -servername "$domain" -cipher 'ALL:COMPLEMENTOFALL' 2>/dev/null | grep -A 100 "Cipher suites")
    
    if [[ -z "$cipher_output" ]]; then
        log_error "Could not retrieve cipher suites for $domain:$port"
        return 1
    fi
    
    # Check for weak ciphers
    local weak_ciphers=("RC4" "DES" "3DES" "MD5" "SHA1" "NULL" "EXPORT")
    local found_weak_ciphers=()
    
    for weak_cipher in "${weak_ciphers[@]}"; do
        if echo "$cipher_output" | grep -i "$weak_cipher" > /dev/null; then
            found_weak_ciphers+=("$weak_cipher")
        fi
    done
    
    if [[ ${#found_weak_ciphers[@]} -gt 0 ]]; then
        log_warning "Weak ciphers found for $domain:$port: ${found_weak_ciphers[*]}"
    fi
    
    # Check for strong ciphers
    local strong_ciphers=("AES256" "AES128" "CHACHA20" "POLY1305")
    local found_strong_ciphers=()
    
    for strong_cipher in "${strong_ciphers[@]}"; do
        if echo "$cipher_output" | grep -i "$strong_cipher" > /dev/null; then
            found_strong_ciphers+=("$strong_cipher")
        fi
    done
    
    if [[ ${#found_strong_ciphers[@]} -eq 0 ]]; then
        log_error "No strong ciphers found for $domain:$port"
        return 1
    fi
    
    log_success "Cipher suite test passed for $domain:$port"
    return 0
}

# Test security headers
test_security_headers() {
    local domain="$1"
    local port="${2:-443}"
    
    local headers=$(curl -I -s -k "https://$domain:$port" --max-time "$TEST_TIMEOUT" 2>/dev/null || echo "")
    
    if [[ -z "$headers" ]]; then
        log_error "Could not retrieve headers for $domain:$port"
        return 1
    fi
    
    # Required security headers
    local required_headers=(
        "Strict-Transport-Security"
        "X-Frame-Options"
        "X-Content-Type-Options"
        "X-XSS-Protection"
        "Content-Security-Policy"
    )
    
    local missing_headers=()
    for header in "${required_headers[@]}"; do
        if ! echo "$headers" | grep -i "$header" > /dev/null; then
            missing_headers+=("$header")
        fi
    done
    
    if [[ ${#missing_headers[@]} -gt 0 ]]; then
        log_warning "Missing security headers for $domain:$port: ${missing_headers[*]}"
    fi
    
    # Check HSTS configuration
    if echo "$headers" | grep -i "Strict-Transport-Security" > /dev/null; then
        local hsts_header=$(echo "$headers" | grep -i "Strict-Transport-Security" | head -1)
        if [[ "$hsts_header" =~ max-age=([0-9]+) ]]; then
            local max_age="${BASH_REMATCH[1]}"
            if [[ $max_age -lt 31536000 ]]; then  # Less than 1 year
                log_warning "HSTS max-age is too short for $domain:$port: $max_age"
            fi
        fi
    fi
    
    log_success "Security headers test completed for $domain:$port"
    return 0
}

# Test OCSP stapling
test_ocsp_stapling() {
    local domain="$1"
    local port="${2:-443}"
    
    local ocsp_output=$(echo | timeout "$TEST_TIMEOUT" openssl s_client -connect "$domain:$port" -servername "$domain" -status 2>/dev/null | grep -A 10 "OCSP Response")
    
    if [[ -z "$ocsp_output" ]]; then
        log_warning "OCSP stapling not implemented for $domain:$port"
        return 1
    fi
    
    if echo "$ocsp_output" | grep -i "good" > /dev/null; then
        log_success "OCSP stapling test passed for $domain:$port"
        return 0
    else
        log_error "OCSP stapling validation failed for $domain:$port"
        return 1
    fi
}

# Test for common vulnerabilities
test_vulnerabilities() {
    local domain="$1"
    local port="${2:-443}"
    
    # Test for Heartbleed vulnerability
    if echo | timeout "$TEST_TIMEOUT" openssl s_client -connect "$domain:$port" -servername "$domain" -tlsextdebug 2>/dev/null | grep -q "heartbeat"; then
        log_warning "Heartbeat extension detected for $domain:$port (potential Heartbleed vulnerability)"
    fi
    
    # Test for POODLE vulnerability (SSLv3)
    if echo | timeout "$TEST_TIMEOUT" openssl s_client -connect "$domain:$port" -servername "$domain" -ssl3 2>/dev/null | grep -q "Verify return code: 0"; then
        log_error "SSLv3 is supported for $domain:$port (POODLE vulnerability)"
        return 1
    fi
    
    # Test for BEAST vulnerability
    local cipher_output=$(echo | timeout "$TEST_TIMEOUT" openssl s_client -connect "$domain:$port" -servername "$domain" 2>/dev/null | grep "Cipher")
    if echo "$cipher_output" | grep -E "(CBC|RC4)" > /dev/null; then
        log_warning "Potentially vulnerable cipher suites detected for $domain:$port"
    fi
    
    log_success "Vulnerability test completed for $domain:$port"
    return 0
}

# Run comprehensive TLS test for a domain
test_domain_tls() {
    local domain="$1"
    local port="${2:-443}"
    
    log "Testing TLS security for $domain:$port..."
    
    # Run all TLS tests
    test_certificate_validity "$domain"
    test_tls_connection "$domain" "$port"
    test_cipher_suites "$domain" "$port"
    test_security_headers "$domain" "$port"
    test_ocsp_stapling "$domain" "$port"
    test_vulnerabilities "$domain" "$port"
    
    log "TLS testing completed for $domain:$port"
}

# Generate test report
generate_test_report() {
    local report_file="$TEST_RESULTS_DIR/tls-security-report-$(date +%Y%m%d-%H%M%S).json"
    
    log "Generating TLS security test report..."
    
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
    "certificate_tests": "completed",
    "tls_connection_tests": "completed",
    "cipher_suite_tests": "completed",
    "security_header_tests": "completed",
    "ocsp_stapling_tests": "completed",
    "vulnerability_tests": "completed"
  },
  "recommendations": [
    "Ensure all certificates are valid and not expired",
    "Disable weak TLS protocols (SSLv3, TLS 1.0, TLS 1.1)",
    "Use strong cipher suites only",
    "Implement all required security headers",
    "Enable OCSP stapling for better performance",
    "Regularly test for known vulnerabilities",
    "Implement certificate pinning for critical services",
    "Monitor certificate expiration and auto-renewal"
  ],
  "security_score": "$(( (PASSED_TESTS * 100) / TOTAL_TESTS ))/100"
}
EOF
    
    log_success "TLS security test report generated: $report_file"
}

# Main test execution
run_all_tests() {
    log "Starting comprehensive TLS security testing..."
    
    # Check prerequisites
    check_prerequisites
    
    # Test each domain and port combination
    for domain in "${TEST_DOMAINS[@]}"; do
        for port in "${TEST_PORTS[@]}"; do
            # Check if service is running on this port
            if nc -z "$domain" "$port" 2>/dev/null; then
                test_domain_tls "$domain" "$port"
            else
                log_warning "Service not running on $domain:$port - skipping tests"
            fi
        done
    done
    
    # Generate final report
    generate_test_report
    
    # Print summary
    log "TLS Security Testing Summary:"
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
        log_success "All TLS security tests passed!"
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
        "certificate")
            local domain="${2:-localhost}"
            test_certificate_validity "$domain"
            ;;
        "connection")
            local domain="${2:-localhost}"
            local port="${3:-443}"
            test_tls_connection "$domain" "$port"
            ;;
        "ciphers")
            local domain="${2:-localhost}"
            local port="${3:-443}"
            test_cipher_suites "$domain" "$port"
            ;;
        "headers")
            local domain="${2:-localhost}"
            local port="${3:-443}"
            test_security_headers "$domain" "$port"
            ;;
        "vulnerabilities")
            local domain="${2:-localhost}"
            local port="${3:-443}"
            test_vulnerabilities "$domain" "$port"
            ;;
        "help"|*)
            echo "TLS/SSL Security Testing Suite for PA Ecosystem"
            echo ""
            echo "Usage: $0 <command> [options]"
            echo ""
            echo "Commands:"
            echo "  all                     Run all TLS security tests"
            echo "  certificate [domain]    Test certificate validity"
            echo "  connection [domain] [port] Test TLS connection"
            echo "  ciphers [domain] [port] Test cipher suites"
            echo "  headers [domain] [port] Test security headers"
            echo "  vulnerabilities [domain] [port] Test for vulnerabilities"
            echo "  help                    Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 all"
            echo "  $0 certificate localhost"
            echo "  $0 connection api.example.com 443"
            echo "  $0 ciphers app.example.com 8443"
            ;;
    esac
}

# Run main function with all arguments
main "$@"
