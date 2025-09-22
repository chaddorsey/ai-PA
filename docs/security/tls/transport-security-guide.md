# Transport Security and Certificate Management Guide

## Overview

This guide provides comprehensive documentation for the Transport Security and Certificate Management system implemented for the PA Ecosystem. The system ensures secure communication through TLS/SSL encryption, automated certificate management, and comprehensive security monitoring.

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Certificate Management](#certificate-management)
3. [TLS/SSL Configuration](#tlsssl-configuration)
4. [Security Features](#security-features)
5. [Monitoring and Alerting](#monitoring-and-alerting)
6. [Testing and Validation](#testing-and-validation)
7. [Troubleshooting](#troubleshooting)
8. [Best Practices](#best-practices)

## System Architecture

### Components

The transport security system consists of the following key components:

- **Certificate Manager** (`scripts/certificates/cert-manager.sh`)
- **TLS Configuration Manager** (`scripts/certificates/tls-config-manager.sh`)
- **TLS Security Testing Suite** (`tests/security/tls/tls-security-tests.sh`)
- **Configuration Files** (`config/tls/`)
- **Monitoring System** (`monitoring/certificates/`)

### Directory Structure

```
config/tls/
├── live/                    # Live certificates (symlinks)
├── archive/                 # Archived certificates
├── renewal/                 # Certificate renewal configuration
├── domains.conf            # Domain configuration
├── openssl.conf            # OpenSSL configuration
└── tls-monitoring.conf     # Monitoring configuration

scripts/certificates/
├── cert-manager.sh         # Certificate management script
└── tls-config-manager.sh   # TLS configuration management

tests/security/tls/
└── tls-security-tests.sh   # TLS security testing suite

monitoring/certificates/
└── certificate-report-*.json # Certificate monitoring reports
```

## Certificate Management

### Certificate Types

The system supports two types of certificates:

1. **Self-Signed Certificates** - For development and testing
2. **Let's Encrypt Certificates** - For production environments

### Certificate Lifecycle

#### 1. Initial Setup

```bash
# Initialize certificate management system
./scripts/certificates/cert-manager.sh init

# Generate self-signed certificate for development
./scripts/certificates/cert-manager.sh self-signed localhost
```

#### 2. Production Certificate Request

```bash
# Request Let's Encrypt certificate
./scripts/certificates/cert-manager.sh request example.com single http

# Request wildcard certificate
./scripts/certificates/cert-manager.sh request *.example.com wildcard dns
```

#### 3. Certificate Renewal

```bash
# Manual renewal
./scripts/certificates/cert-manager.sh renew

# Automated renewal (via cron)
0 2 * * * /path/to/scripts/certificates/cert-manager.sh renew
```

### Domain Configuration

Configure domains in `config/tls/domains.conf`:

```
# Format: domain_name:cert_type:validation_method:additional_domains
example.com:single:http:
api.example.com:single:http:www.api.example.com
*.example.com:wildcard:dns:example.com
```

### Certificate Validation

```bash
# Validate certificate
./scripts/certificates/cert-manager.sh validate example.com

# Generate certificate report
./scripts/certificates/cert-manager.sh report
```

## TLS/SSL Configuration

### Configuration Management

```bash
# Generate TLS configurations
./scripts/certificates/tls-config-manager.sh generate all

# Validate configuration
./scripts/certificates/tls-config-manager.sh validate /path/to/config

# Apply configuration to services
./scripts/certificates/tls-config-manager.sh apply nginx
```

### Security Settings

#### Protocol Configuration
- **Minimum TLS Version**: 1.2
- **Preferred TLS Version**: 1.3
- **Disabled Protocols**: SSLv3, TLS 1.0, TLS 1.1

#### Cipher Suites
- **TLS 1.3**: `TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256`
- **TLS 1.2**: `ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-RSA-AES128-GCM-SHA256`

#### Security Headers
- **HSTS**: `max-age=31536000; includeSubDomains; preload`
- **X-Frame-Options**: `SAMEORIGIN`
- **X-Content-Type-Options**: `nosniff`
- **X-XSS-Protection**: `1; mode=block`
- **Content-Security-Policy**: Comprehensive policy for XSS protection

### Nginx Configuration

Example TLS configuration for Nginx:

```nginx
# SSL Configuration
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-RSA-AES128-GCM-SHA256;
ssl_prefer_server_ciphers off;

# SSL Session Configuration
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;
ssl_session_tickets off;

# OCSP Stapling
ssl_stapling on;
ssl_stapling_verify on;

# Security Headers
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
```

## Security Features

### 1. Perfect Forward Secrecy (PFS)
- ECDHE key exchange for all connections
- Ephemeral keys that are discarded after use
- Protection against future key compromise

### 2. Certificate Transparency
- Monitoring of certificate issuance
- Detection of unauthorized certificates
- Compliance with CT requirements

### 3. OCSP Stapling
- Real-time certificate validation
- Reduced latency for certificate checks
- Improved privacy protection

### 4. HSTS (HTTP Strict Transport Security)
- Enforced HTTPS connections
- Protection against protocol downgrade attacks
- Browser-side security enforcement

### 5. Certificate Pinning
- Protection against compromised CAs
- Enhanced security for critical services
- Reduced attack surface

## Monitoring and Alerting

### Certificate Monitoring

```bash
# Monitor certificate health
./scripts/certificates/cert-manager.sh monitor

# Generate monitoring report
./scripts/certificates/tls-config-manager.sh report
```

### Alert Conditions

The system monitors for the following conditions:

- **Certificate Expiration**: Alerts when certificates expire within 30 days
- **Certificate Validation Failures**: Alerts on certificate validation errors
- **TLS Configuration Issues**: Alerts on misconfigured TLS settings
- **Security Vulnerabilities**: Alerts on detected security issues

### Monitoring Dashboard

Certificate status is tracked in JSON format:

```json
{
  "report_date": "2025-01-21T10:30:00Z",
  "certificates": [
    {
      "domain": "example.com",
      "type": "single",
      "validation_method": "http",
      "days_until_expiry": 45,
      "status": "healthy"
    }
  ]
}
```

## Testing and Validation

### Automated Testing

```bash
# Run comprehensive TLS security tests
./tests/security/tls/tls-security-tests.sh all

# Test specific components
./tests/security/tls/tls-security-tests.sh certificate example.com
./tests/security/tls/tls-security-tests.sh connection example.com 443
./tests/security/tls/tls-security-tests.sh vulnerabilities example.com 443
```

### Test Coverage

The testing suite covers:

1. **Certificate Validity**
   - Format validation
   - Expiration checking
   - Chain validation
   - Private key matching

2. **TLS Connection Security**
   - Protocol support
   - Cipher suite strength
   - Connection establishment

3. **Security Headers**
   - Header presence
   - Header configuration
   - Security policy compliance

4. **Vulnerability Testing**
   - Heartbleed detection
   - POODLE vulnerability
   - BEAST vulnerability
   - Weak cipher detection

5. **OCSP Stapling**
   - OCSP response validation
   - Stapling implementation

### Test Results

Test results are generated in JSON format with detailed security scores and recommendations.

## Troubleshooting

### Common Issues

#### 1. Certificate Installation Issues

**Problem**: Certificate files not found
```bash
# Check certificate path
ls -la /path/to/certificates/

# Validate certificate
openssl x509 -in certificate.crt -text -noout
```

**Solution**: Ensure certificate files are in the correct location and have proper permissions.

#### 2. TLS Handshake Failures

**Problem**: TLS connection fails
```bash
# Test TLS connection
openssl s_client -connect example.com:443 -servername example.com

# Check protocol support
openssl s_client -connect example.com:443 -tls1_3
```

**Solution**: Verify TLS configuration and protocol support.

#### 3. Certificate Chain Issues

**Problem**: Certificate chain validation fails
```bash
# Verify certificate chain
openssl verify -CAfile ca-bundle.crt certificate.crt

# Check intermediate certificates
openssl x509 -in intermediate.crt -text -noout
```

**Solution**: Ensure complete certificate chain is provided.

#### 4. OCSP Stapling Issues

**Problem**: OCSP stapling not working
```bash
# Test OCSP stapling
openssl s_client -connect example.com:443 -status

# Check OCSP responder
openssl ocsp -issuer ca.crt -cert certificate.crt -url http://ocsp.example.com
```

**Solution**: Verify OCSP configuration and responder availability.

### Debug Commands

```bash
# Certificate information
openssl x509 -in certificate.crt -text -noout

# TLS connection details
openssl s_client -connect host:port -servername host

# Cipher suite information
openssl ciphers -v

# Protocol support
openssl s_client -connect host:port -tls1_2
openssl s_client -connect host:port -tls1_3
```

## Best Practices

### 1. Certificate Management

- **Regular Renewal**: Set up automated certificate renewal
- **Backup Strategy**: Maintain secure backups of certificates
- **Monitoring**: Monitor certificate expiration and health
- **Documentation**: Keep detailed records of certificate configurations

### 2. TLS Configuration

- **Strong Protocols**: Use TLS 1.2 minimum, prefer TLS 1.3
- **Secure Ciphers**: Use only strong cipher suites
- **Perfect Forward Secrecy**: Enable PFS for all connections
- **Security Headers**: Implement comprehensive security headers

### 3. Security Monitoring

- **Regular Testing**: Run security tests regularly
- **Vulnerability Scanning**: Monitor for known vulnerabilities
- **Performance Monitoring**: Track TLS performance metrics
- **Incident Response**: Have procedures for security incidents

### 4. Compliance

- **Standards Compliance**: Follow industry security standards
- **Audit Trails**: Maintain comprehensive audit logs
- **Documentation**: Keep security documentation current
- **Training**: Ensure team members are trained on security procedures

### 5. Operational Excellence

- **Automation**: Automate routine security tasks
- **Monitoring**: Implement comprehensive monitoring
- **Alerting**: Set up appropriate alerting mechanisms
- **Testing**: Regular security testing and validation

## Integration with PA Ecosystem

### Docker Integration

The TLS system integrates with Docker services through:

```yaml
# docker-compose.tls.yml
services:
  nginx:
    volumes:
      - ./tls/live:/etc/ssl/certs:ro
      - ./tls/live:/etc/ssl/private:ro
    environment:
      - TLS_ENABLED=true
```

### Service Integration

Services are configured to use TLS through environment variables:

```bash
# Environment variables
TLS_ENABLED=true
TLS_CERT_PATH=/etc/ssl/certs/service.crt
TLS_KEY_PATH=/etc/ssl/private/service.key
```

### Monitoring Integration

TLS monitoring integrates with the overall monitoring system:

- **Health Checks**: TLS health is included in service health checks
- **Metrics**: TLS metrics are collected and reported
- **Alerting**: TLS alerts are integrated with the alerting system
- **Dashboards**: TLS status is displayed in monitoring dashboards

## Conclusion

The Transport Security and Certificate Management system provides comprehensive security for the PA Ecosystem through:

- Automated certificate management
- Strong TLS/SSL configuration
- Comprehensive security monitoring
- Regular security testing
- Best practices implementation

This system ensures that all communications within the PA Ecosystem are secure, monitored, and compliant with security standards.
