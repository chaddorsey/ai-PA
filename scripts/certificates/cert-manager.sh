#!/bin/bash

# Certificate Manager for PA Ecosystem
# Handles automated certificate provisioning, renewal, monitoring, and management

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CERT_DIR="$PROJECT_ROOT/config/tls"
LOG_DIR="$PROJECT_ROOT/logs/certificates"
MONITORING_DIR="$PROJECT_ROOT/monitoring/certificates"
BACKUP_DIR="$PROJECT_ROOT/backups/certificates"

# Certificate configuration
CERT_DAYS_VALID=90
RENEWAL_THRESHOLD_DAYS=30
ACME_DIR="/var/www/acme-challenge"
LETSENCRYPT_DIR="/etc/letsencrypt"
DOMAIN_CONFIG="$CERT_DIR/domains.conf"

# Logging
LOG_FILE="$LOG_DIR/cert-manager.log"
mkdir -p "$LOG_DIR" "$BACKUP_DIR" "$MONITORING_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] SUCCESS:${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOG_FILE"
}

# Initialize certificate management
init_cert_management() {
    log "Initializing certificate management system..."
    
    # Create necessary directories
    mkdir -p "$CERT_DIR"/{live,archive,renewal}
    mkdir -p "$ACME_DIR"
    mkdir -p "$BACKUP_DIR"
    
    # Set secure permissions
    chmod 700 "$CERT_DIR"
    chmod 755 "$ACME_DIR"
    chmod 700 "$BACKUP_DIR"
    
    # Create domain configuration if it doesn't exist
    if [[ ! -f "$DOMAIN_CONFIG" ]]; then
        cat > "$DOMAIN_CONFIG" << 'EOF'
# Domain Configuration for Certificate Management
# Format: domain_name:cert_type:validation_method:additional_domains

# Example entries:
# example.com:wildcard:dns:*.example.com
# api.example.com:single:http:
# app.example.com:single:http:www.app.example.com

EOF
        log_success "Created domain configuration file at $DOMAIN_CONFIG"
    fi
    
    log_success "Certificate management system initialized"
}

# Check if certbot is installed
check_certbot() {
    if ! command -v certbot &> /dev/null; then
        log_error "Certbot is not installed. Please install it first:"
        echo "  Ubuntu/Debian: sudo apt-get install certbot"
        echo "  CentOS/RHEL: sudo yum install certbot"
        echo "  macOS: brew install certbot"
        exit 1
    fi
    log_success "Certbot is available"
}

# Generate self-signed certificate for development
generate_self_signed_cert() {
    local domain="$1"
    local cert_path="$CERT_DIR/live/$domain"
    
    log "Generating self-signed certificate for $domain..."
    
    mkdir -p "$cert_path"
    
    # Generate private key
    openssl genrsa -out "$cert_path/privkey.pem" 4096
    
    # Generate certificate signing request
    openssl req -new -key "$cert_path/privkey.pem" -out "$cert_path/cert.csr" \
        -subj "/C=US/ST=CA/L=San Francisco/O=PA Ecosystem/OU=IT Department/CN=$domain"
    
    # Generate self-signed certificate
    openssl x509 -req -days "$CERT_DAYS_VALID" -in "$cert_path/cert.csr" \
        -signkey "$cert_path/privkey.pem" -out "$cert_path/cert.pem" \
        -extensions v3_req -extfile <(
            echo "[v3_req]"
            echo "keyUsage = keyEncipherment, dataEncipherment"
            echo "extendedKeyUsage = serverAuth"
            echo "subjectAltName = DNS:$domain"
        )
    
    # Create certificate chain
    cp "$cert_path/cert.pem" "$cert_path/chain.pem"
    cp "$cert_path/cert.pem" "$cert_path/fullchain.pem"
    
    # Set permissions
    chmod 600 "$cert_path/privkey.pem"
    chmod 644 "$cert_path/cert.pem" "$cert_path/chain.pem" "$cert_path/fullchain.pem"
    
    log_success "Self-signed certificate generated for $domain"
}

# Request Let's Encrypt certificate
request_letsencrypt_cert() {
    local domain="$1"
    local cert_type="${2:-single}"
    local validation_method="${3:-http}"
    local additional_domains="${4:-}"
    
    log "Requesting Let's Encrypt certificate for $domain..."
    
    local certbot_args=(
        certonly
        --non-interactive
        --agree-tos
        --email admin@pa-ecosystem.local
        --webroot
        --webroot-path="$ACME_DIR"
    )
    
    if [[ "$cert_type" == "wildcard" ]]; then
        certbot_args+=(--dns-cloudflare)
        validation_method="dns"
    fi
    
    if [[ "$validation_method" == "dns" ]]; then
        certbot_args+=(--dns-cloudflare)
    fi
    
    certbot_args+=(-d "$domain")
    
    # Add additional domains if specified
    if [[ -n "$additional_domains" ]]; then
        IFS=',' read -ra DOMAINS <<< "$additional_domains"
        for d in "${DOMAINS[@]}"; do
            certbot_args+=(-d "$d")
        done
    fi
    
    # Request certificate
    if certbot "${certbot_args[@]}"; then
        log_success "Let's Encrypt certificate obtained for $domain"
        
        # Create symlinks in our cert directory
        local cert_path="$CERT_DIR/live/$domain"
        mkdir -p "$cert_path"
        
        ln -sf "$LETSENCRYPT_DIR/live/$domain/privkey.pem" "$cert_path/privkey.pem"
        ln -sf "$LETSENCRYPT_DIR/live/$domain/cert.pem" "$cert_path/cert.pem"
        ln -sf "$LETSENCRYPT_DIR/live/$domain/chain.pem" "$cert_path/chain.pem"
        ln -sf "$LETSENCRYPT_DIR/live/$domain/fullchain.pem" "$cert_path/fullchain.pem"
        
        log_success "Certificate symlinks created for $domain"
    else
        log_error "Failed to obtain Let's Encrypt certificate for $domain"
        return 1
    fi
}

# Check certificate expiration
check_cert_expiration() {
    local domain="$1"
    local cert_path="$CERT_DIR/live/$domain"
    
    if [[ ! -f "$cert_path/cert.pem" ]]; then
        log_error "Certificate not found for $domain"
        return 1
    fi
    
    local expiry_date=$(openssl x509 -enddate -noout -in "$cert_path/cert.pem" | cut -d= -f2)
    local expiry_timestamp=$(date -d "$expiry_date" +%s)
    local current_timestamp=$(date +%s)
    local days_until_expiry=$(( (expiry_timestamp - current_timestamp) / 86400 ))
    
    echo "$days_until_expiry"
}

# Renew certificates
renew_certificates() {
    log "Checking certificate renewals..."
    
    local renewed_count=0
    local failed_count=0
    
    # Check all domains in configuration
    while IFS=':' read -r domain cert_type validation_method additional_domains; do
        # Skip comments and empty lines
        [[ "$domain" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$domain" ]] && continue
        
        local days_until_expiry
        days_until_expiry=$(check_cert_expiration "$domain")
        
        if [[ $? -eq 0 ]] && [[ $days_until_expiry -lt $RENEWAL_THRESHOLD_DAYS ]]; then
            log "Certificate for $domain expires in $days_until_expiry days. Renewing..."
            
            # Backup current certificate
            backup_certificate "$domain"
            
            # Renew certificate
            if certbot renew --cert-name "$domain" --quiet; then
                log_success "Certificate renewed for $domain"
                ((renewed_count++))
                
                # Restart services that use this certificate
                restart_certificate_dependent_services "$domain"
            else
                log_error "Failed to renew certificate for $domain"
                ((failed_count++))
            fi
        else
            log "Certificate for $domain is valid for $days_until_expiry days"
        fi
    done < "$DOMAIN_CONFIG"
    
    log_success "Certificate renewal completed: $renewed_count renewed, $failed_count failed"
}

# Backup certificate
backup_certificate() {
    local domain="$1"
    local cert_path="$CERT_DIR/live/$domain"
    local backup_path="$BACKUP_DIR/$domain-$(date +%Y%m%d-%H%M%S)"
    
    if [[ -d "$cert_path" ]]; then
        mkdir -p "$backup_path"
        cp -r "$cert_path"/* "$backup_path/"
        log_success "Certificate backed up to $backup_path"
    fi
}

# Restart services that depend on certificates
restart_certificate_dependent_services() {
    local domain="$1"
    
    log "Restarting services that depend on certificate for $domain..."
    
    # Restart nginx if it's running
    if systemctl is-active --quiet nginx 2>/dev/null; then
        systemctl reload nginx
        log_success "Nginx reloaded"
    fi
    
    # Restart Docker services that use certificates
    if command -v docker-compose &> /dev/null; then
        cd "$PROJECT_ROOT"
        docker-compose restart nginx proxy 2>/dev/null || true
        log_success "Docker services restarted"
    fi
}

# Validate certificate
validate_certificate() {
    local domain="$1"
    local cert_path="$CERT_DIR/live/$domain"
    
    log "Validating certificate for $domain..."
    
    if [[ ! -f "$cert_path/cert.pem" ]]; then
        log_error "Certificate file not found: $cert_path/cert.pem"
        return 1
    fi
    
    # Check certificate validity
    if openssl x509 -in "$cert_path/cert.pem" -text -noout > /dev/null 2>&1; then
        log_success "Certificate format is valid"
    else
        log_error "Certificate format is invalid"
        return 1
    fi
    
    # Check certificate chain
    if openssl verify -CAfile "$cert_path/chain.pem" "$cert_path/cert.pem" > /dev/null 2>&1; then
        log_success "Certificate chain is valid"
    else
        log_warning "Certificate chain validation failed"
    fi
    
    # Check private key matches certificate
    local cert_modulus=$(openssl x509 -noout -modulus -in "$cert_path/cert.pem" | openssl md5)
    local key_modulus=$(openssl rsa -noout -modulus -in "$cert_path/privkey.pem" | openssl md5)
    
    if [[ "$cert_modulus" == "$key_modulus" ]]; then
        log_success "Private key matches certificate"
    else
        log_error "Private key does not match certificate"
        return 1
    fi
    
    # Check certificate expiration
    local days_until_expiry
    days_until_expiry=$(check_cert_expiration "$domain")
    
    if [[ $days_until_expiry -gt 0 ]]; then
        log_success "Certificate is valid for $days_until_expiry days"
    else
        log_error "Certificate has expired"
        return 1
    fi
}

# Generate certificate report
generate_cert_report() {
    local report_file="$MONITORING_DIR/certificate-report-$(date +%Y%m%d).json"
    
    log "Generating certificate report..."
    
    cat > "$report_file" << 'EOF'
{
  "report_date": "REPLACE_DATE",
  "certificates": [
EOF
    
    local first=true
    while IFS=':' read -r domain cert_type validation_method additional_domains; do
        # Skip comments and empty lines
        [[ "$domain" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$domain" ]] && continue
        
        if [[ "$first" == true ]]; then
            first=false
        else
            echo "," >> "$report_file"
        fi
        
        local days_until_expiry
        days_until_expiry=$(check_cert_expiration "$domain" 2>/dev/null || echo "unknown")
        
        cat >> "$report_file" << EOF
    {
      "domain": "$domain",
      "type": "$cert_type",
      "validation_method": "$validation_method",
      "additional_domains": "$additional_domains",
      "days_until_expiry": $days_until_expiry,
      "status": "$(if [[ $days_until_expiry -gt $RENEWAL_THRESHOLD_DAYS ]]; then echo "healthy"; elif [[ $days_until_expiry -gt 0 ]]; then echo "warning"; else echo "expired"; fi)"
    }EOF
    done < "$DOMAIN_CONFIG"
    
    cat >> "$report_file" << 'EOF'

  ]
}
EOF
    
    # Replace date placeholder
    sed -i "s/REPLACE_DATE/$(date -Iseconds)/" "$report_file"
    
    log_success "Certificate report generated: $report_file"
}

# Monitor certificate health
monitor_certificates() {
    log "Monitoring certificate health..."
    
    local alerts=()
    
    while IFS=':' read -r domain cert_type validation_method additional_domains; do
        # Skip comments and empty lines
        [[ "$domain" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$domain" ]] && continue
        
        local days_until_expiry
        days_until_expiry=$(check_cert_expiration "$domain" 2>/dev/null || echo "unknown")
        
        if [[ "$days_until_expiry" == "unknown" ]]; then
            alerts+=("ALERT: Certificate for $domain could not be checked")
        elif [[ $days_until_expiry -lt 0 ]]; then
            alerts+=("CRITICAL: Certificate for $domain has expired")
        elif [[ $days_until_expiry -lt 7 ]]; then
            alerts+=("CRITICAL: Certificate for $domain expires in $days_until_expiry days")
        elif [[ $days_until_expiry -lt $RENEWAL_THRESHOLD_DAYS ]]; then
            alerts+=("WARNING: Certificate for $domain expires in $days_until_expiry days")
        fi
    done < "$DOMAIN_CONFIG"
    
    # Generate report
    generate_cert_report
    
    # Send alerts if any
    if [[ ${#alerts[@]} -gt 0 ]]; then
        log_warning "Certificate alerts detected:"
        for alert in "${alerts[@]}"; do
            log_warning "$alert"
        done
        
        # Send notification (implement your preferred notification method)
        send_certificate_alerts "${alerts[@]}"
    else
        log_success "All certificates are healthy"
    fi
}

# Send certificate alerts
send_certificate_alerts() {
    local alerts=("$@")
    
    # This is a placeholder for alert notification
    # Implement your preferred notification method (email, Slack, etc.)
    log "Certificate alerts would be sent here:"
    for alert in "${alerts[@]}"; do
        log "  $alert"
    done
}

# Clean up old backups
cleanup_old_backups() {
    local retention_days="${1:-30}"
    
    log "Cleaning up backups older than $retention_days days..."
    
    find "$BACKUP_DIR" -type d -mtime +$retention_days -exec rm -rf {} + 2>/dev/null || true
    
    log_success "Old backups cleaned up"
}

# Main function
main() {
    local command="${1:-help}"
    
    case "$command" in
        "init")
            init_cert_management
            ;;
        "check")
            check_certbot
            ;;
        "self-signed")
            local domain="${2:-localhost}"
            generate_self_signed_cert "$domain"
            ;;
        "request")
            local domain="${2:-}"
            local cert_type="${3:-single}"
            local validation_method="${4:-http}"
            local additional_domains="${5:-}"
            
            if [[ -z "$domain" ]]; then
                log_error "Domain is required for certificate request"
                exit 1
            fi
            
            check_certbot
            request_letsencrypt_cert "$domain" "$cert_type" "$validation_method" "$additional_domains"
            ;;
        "renew")
            check_certbot
            renew_certificates
            ;;
        "validate")
            local domain="${2:-}"
            if [[ -z "$domain" ]]; then
                log_error "Domain is required for certificate validation"
                exit 1
            fi
            validate_certificate "$domain"
            ;;
        "monitor")
            monitor_certificates
            ;;
        "report")
            generate_cert_report
            ;;
        "cleanup")
            local retention_days="${2:-30}"
            cleanup_old_backups "$retention_days"
            ;;
        "help"|*)
            echo "Certificate Manager for PA Ecosystem"
            echo ""
            echo "Usage: $0 <command> [options]"
            echo ""
            echo "Commands:"
            echo "  init                    Initialize certificate management system"
            echo "  check                   Check if certbot is installed"
            echo "  self-signed <domain>    Generate self-signed certificate"
            echo "  request <domain> [type] [validation] [additional]"
            echo "                         Request Let's Encrypt certificate"
            echo "  renew                   Renew all certificates approaching expiration"
            echo "  validate <domain>       Validate certificate for domain"
            echo "  monitor                 Monitor certificate health and generate alerts"
            echo "  report                  Generate certificate status report"
            echo "  cleanup [days]          Clean up old backups (default: 30 days)"
            echo "  help                    Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 init"
            echo "  $0 self-signed localhost"
            echo "  $0 request example.com single http"
            echo "  $0 request *.example.com wildcard dns"
            echo "  $0 renew"
            echo "  $0 validate example.com"
            echo "  $0 monitor"
            ;;
    esac
}

# Run main function with all arguments
main "$@"
