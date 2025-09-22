# Security Setup and Configuration Guide

## Overview

This guide provides comprehensive step-by-step instructions for setting up and configuring the security infrastructure for the PA Ecosystem. It covers all aspects of security implementation from initial setup to ongoing maintenance.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Security Setup](#initial-security-setup)
3. [Secrets Management Setup](#secrets-management-setup)
4. [Network Security Configuration](#network-security-configuration)
5. [Transport Security Setup](#transport-security-setup)
6. [Security Monitoring Setup](#security-monitoring-setup)
7. [Security Validation](#security-validation)
8. [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- **Operating System**: Linux (Ubuntu 20.04+ recommended)
- **Memory**: Minimum 8GB RAM, 16GB recommended
- **Storage**: Minimum 100GB available disk space
- **Network**: Stable internet connection for certificate management

### Required Software

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y \
    openssl \
    curl \
    wget \
    git \
    jq \
    nmap \
    netstat-nat \
    ufw \
    fail2ban \
    logrotate \
    rsyslog \
    docker \
    docker-compose \
    certbot \
    python3-certbot-nginx

# Install additional security tools
sudo apt install -y \
    auditd \
    aide \
    chkrootkit \
    rkhunter \
    clamav \
    lynis
```

### Directory Structure

```bash
# Create security directories
sudo mkdir -p /etc/pa-security/{secrets,network,tls,monitoring,logs}
sudo mkdir -p /var/log/pa-security/{events,threats,vulnerabilities,incidents}
sudo mkdir -p /var/backups/pa-security/{secrets,certificates,configs}
sudo mkdir -p /opt/pa-security/{scripts,tools,reports}

# Set proper permissions
sudo chmod 750 /etc/pa-security
sudo chmod 700 /etc/pa-security/secrets
sudo chmod 640 /etc/pa-security/*/*
sudo chown -R root:root /etc/pa-security
```

## Initial Security Setup

### 1. System Hardening

#### Firewall Configuration

```bash
# Enable UFW firewall
sudo ufw enable

# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (adjust port as needed)
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow Docker networks (adjust as needed)
sudo ufw allow from 172.20.0.0/16

# Check status
sudo ufw status verbose
```

#### SSH Hardening

```bash
# Edit SSH configuration
sudo nano /etc/ssh/sshd_config

# Add/modify these settings:
Port 2222                    # Change default port
PermitRootLogin no          # Disable root login
PasswordAuthentication no   # Disable password auth
PubkeyAuthentication yes    # Enable key authentication
X11Forwarding no           # Disable X11 forwarding
MaxAuthTries 3             # Limit authentication attempts
ClientAliveInterval 300    # Set connection timeout
ClientAliveCountMax 2      # Set connection count

# Restart SSH service
sudo systemctl restart sshd
```

#### System Updates and Patches

```bash
# Configure automatic security updates
sudo apt install unattended-upgrades
sudo dpkg-reconfigure unattended-upgrades

# Enable automatic security updates
echo 'Unattended-Upgrade::Automatic-Reboot "false";' | sudo tee -a /etc/apt/apt.conf.d/50unattended-upgrades
```

### 2. User Account Security

```bash
# Create dedicated security user
sudo useradd -m -s /bin/bash pa-security
sudo usermod -aG sudo pa-security
sudo usermod -aG docker pa-security

# Set up SSH keys for security user
sudo -u pa-security mkdir -p /home/pa-security/.ssh
sudo -u pa-security chmod 700 /home/pa-security/.ssh

# Add SSH public key (replace with actual key)
sudo -u pa-security tee /home/pa-security/.ssh/authorized_keys << 'EOF'
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC... pa-security@pa-ecosystem.local
EOF

sudo -u pa-security chmod 600 /home/pa-security/.ssh/authorized_keys
```

### 3. Logging Configuration

```bash
# Configure rsyslog for security logging
sudo tee /etc/rsyslog.d/50-pa-security.conf << 'EOF'
# PA Ecosystem Security Logging
local0.*    /var/log/pa-security/security.log
local1.*    /var/log/pa-security/auth.log
local2.*    /var/log/pa-security/network.log
local3.*    /var/log/pa-security/app.log

# Security event forwarding
*.* @@log-server.pa-ecosystem.local:514
EOF

# Restart rsyslog
sudo systemctl restart rsyslog
```

## Secrets Management Setup

### 1. Initialize Secrets Management

```bash
# Navigate to project directory
cd /path/to/pa-ecosystem

# Initialize secrets management
./scripts/secrets/secrets-manager.sh init

# Set master key (generate secure random key)
export PA_SECRETS_MASTER_KEY=$(openssl rand -base64 32)
echo "PA_SECRETS_MASTER_KEY=$PA_SECRETS_MASTER_KEY" | sudo tee -a /etc/environment

# Create secure environment template
cp docs/security/secrets/secure-env-template.md config/secrets/.env.template
```

### 2. Configure Credential Storage

```bash
# Create encrypted credential storage
sudo mkdir -p /etc/pa-security/secrets/encrypted
sudo chmod 700 /etc/pa-security/secrets/encrypted

# Generate initial credentials
./scripts/secrets/secrets-manager.sh generate-db-password
./scripts/secrets/secrets-manager.sh generate-api-keys
./scripts/secrets/secrets-manager.sh generate-jwt-secret

# Set up credential rotation
sudo crontab -e
# Add: 0 2 * * 0 /path/to/pa-ecosystem/scripts/secrets/credential-rotation.sh
```

### 3. Environment Configuration

```bash
# Create secure environment file
sudo tee /etc/pa-security/.env << 'EOF'
# PA Ecosystem Security Configuration
PA_SECRETS_MASTER_KEY=${PA_SECRETS_MASTER_KEY}
PA_DB_PASSWORD=$(./scripts/secrets/secrets-manager.sh get db-password)
PA_API_SECRET=$(./scripts/secrets/secrets-manager.sh get api-secret)
PA_JWT_SECRET=$(./scripts/secrets/secrets-manager.sh get jwt-secret)

# Security settings
PA_SECURITY_LEVEL=production
PA_LOG_LEVEL=INFO
PA_ENCRYPTION_ENABLED=true
PA_AUDIT_LOGGING=true
EOF

sudo chmod 600 /etc/pa-security/.env
```

## Network Security Configuration

### 1. Network Segmentation Setup

```bash
# Navigate to project directory
cd /path/to/pa-ecosystem

# Initialize network security
./scripts/network/network-security.sh init

# Create secure network configuration
cp config/network/docker-compose.secure.yml docker-compose.yml

# Set up firewall policies
./scripts/network/network-security.sh configure-firewall

# Validate network isolation
./scripts/network/network-security.sh validate-isolation
```

### 2. Docker Network Configuration

```bash
# Create secure Docker networks
docker network create --driver bridge \
    --subnet=172.20.1.0/24 \
    --opt com.docker.network.bridge.name=pa-database \
    --opt com.docker.network.bridge.enable_icc=false \
    pa-database-net

docker network create --driver bridge \
    --subnet=172.20.2.0/24 \
    --opt com.docker.network.bridge.name=pa-supabase \
    --opt com.docker.network.bridge.enable_icc=false \
    pa-supabase-net

# Continue for all network tiers...
```

### 3. Network Monitoring

```bash
# Set up network monitoring
sudo tee /etc/pa-security/network-monitoring.conf << 'EOF'
# Network Monitoring Configuration
MONITOR_INTERFACES=eth0,eth1
MONITOR_PORTS=22,80,443,5432,6379
ALERT_THRESHOLD_CONNECTIONS=1000
ALERT_THRESHOLD_BANDWIDTH=1000
LOG_NETWORK_EVENTS=true
EOF
```

## Transport Security Setup

### 1. Certificate Management

```bash
# Navigate to project directory
cd /path/to/pa-ecosystem

# Initialize certificate management
./scripts/certificates/cert-manager.sh init-self-signed localhost
./scripts/certificates/cert-manager.sh init-self-signed api.pa-ecosystem.local
./scripts/certificates/cert-manager.sh init-self-signed app.pa-ecosystem.local

# For production, use Let's Encrypt
# ./scripts/certificates/cert-manager.sh init-le api.pa-ecosystem.local
# ./scripts/certificates/cert-manager.sh init-le app.pa-ecosystem.local
```

### 2. TLS Configuration

```bash
# Configure TLS settings
./scripts/certificates/tls-config-manager.sh gen-openssl-config api.pa-ecosystem.local
./scripts/certificates/tls-config-manager.sh config-nginx api.pa-ecosystem.local
./scripts/certificates/tls-config-manager.sh config-docker-compose docker-compose.yml api-service

# Validate TLS configuration
./scripts/certificates/tls-config-manager.sh validate nginx api.pa-ecosystem.local
```

### 3. Security Headers

```bash
# Configure security headers in Nginx
sudo tee /etc/nginx/conf.d/security-headers.conf << 'EOF'
# Security Headers Configuration
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self';" always;
EOF

# Test Nginx configuration
sudo nginx -t
sudo systemctl reload nginx
```

## Security Monitoring Setup

### 1. Initialize Security Monitoring

```bash
# Navigate to project directory
cd /path/to/pa-ecosystem

# Initialize security monitoring
./scripts/security/security-monitor.sh init

# Configure monitoring settings
sudo tee /etc/pa-security/monitoring.conf << 'EOF'
# Security Monitoring Configuration
THREAT_SCAN_INTERVAL=300
VULN_SCAN_INTERVAL=86400
LOG_ANALYSIS_INTERVAL=60
ALERT_EMAIL=security@pa-ecosystem.local
ALERT_THRESHOLD_CRITICAL=10
ALERT_THRESHOLD_WARNING=5
EOF
```

### 2. Configure Threat Detection

```bash
# Customize threat detection rules
sudo nano monitoring/security/threat-detection-rules.conf

# Add custom rules for your environment
# Example: Custom application-specific threats
RULE_CUSTOM_APP_THREAT=(
    "name=Custom Application Threat"
    "pattern=suspicious_pattern_here"
    "threshold=3"
    "timeframe=300"
    "severity=high"
    "action=alert,block"
)
```

### 3. Set Up Log Monitoring

```bash
# Configure log sources
sudo tee /etc/pa-security/log-sources.conf << 'EOF'
# Log Sources Configuration
LOG_SOURCES=(
    "/var/log/auth.log"
    "/var/log/syslog"
    "/var/log/nginx/access.log"
    "/var/log/nginx/error.log"
    "/var/log/mysql/error.log"
    "/var/log/postgresql/postgresql.log"
    "/var/log/docker.log"
    "/var/log/pa-security/security.log"
)
EOF

# Set up log rotation
sudo tee /etc/logrotate.d/pa-security-logs << 'EOF'
/var/log/pa-security/*.log {
    daily
    missingok
    rotate 90
    compress
    delaycompress
    notifempty
    create 640 pa-security pa-security
    postrotate
        /bin/kill -HUP `cat /var/run/rsyslogd.pid 2> /dev/null` 2> /dev/null || true
    endscript
}
EOF
```

### 4. Start Security Monitoring

```bash
# Start security monitoring service
sudo tee /etc/systemd/system/pa-security-monitor.service << 'EOF'
[Unit]
Description=PA Ecosystem Security Monitor
After=network.target docker.service

[Service]
Type=simple
User=pa-security
Group=pa-security
WorkingDirectory=/path/to/pa-ecosystem
ExecStart=/path/to/pa-ecosystem/scripts/security/security-monitor.sh start
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable pa-security-monitor
sudo systemctl start pa-security-monitor
```

## Security Validation

### 1. Run Security Tests

```bash
# Navigate to project directory
cd /path/to/pa-ecosystem

# Run comprehensive security tests
./tests/security/monitoring/security-monitoring-tests.sh all
./tests/security/network/network-security-tests.sh all
./tests/security/tls/tls-security-tests.sh all

# Run secrets management tests
./scripts/audit/credential-audit.sh scan-all
```

### 2. Security Configuration Validation

```bash
# Validate all security configurations
./scripts/security/security-monitor.sh status
./scripts/network/network-security.sh status
./scripts/certificates/cert-manager.sh check-all

# Generate security report
./scripts/security/security-monitor.sh report
```

### 3. Compliance Check

```bash
# Run compliance validation
sudo lynis audit system
sudo rkhunter --check
sudo chkrootkit
sudo aide --check
```

## Troubleshooting

### Common Issues

#### 1. Secrets Management Issues

**Problem**: Cannot decrypt secrets
```bash
# Check master key
echo $PA_SECRETS_MASTER_KEY

# Verify secrets directory permissions
ls -la /etc/pa-security/secrets/

# Test secrets manager
./scripts/secrets/secrets-manager.sh list
```

**Solution**: Ensure master key is set and permissions are correct

#### 2. Network Isolation Issues

**Problem**: Services cannot communicate
```bash
# Check Docker networks
docker network ls
docker network inspect pa-database-net

# Test network connectivity
docker run --rm --network pa-database-net alpine ping -c 3 database-service
```

**Solution**: Verify network configuration and service placement

#### 3. Certificate Issues

**Problem**: TLS handshake failures
```bash
# Check certificate validity
openssl x509 -in /etc/ssl/certs/pa-ecosystem/api.pa-ecosystem.local.crt -text -noout

# Test TLS connection
openssl s_client -connect api.pa-ecosystem.local:443 -servername api.pa-ecosystem.local
```

**Solution**: Verify certificate installation and configuration

#### 4. Monitoring Issues

**Problem**: Security monitoring not working
```bash
# Check monitoring service status
sudo systemctl status pa-security-monitor

# View monitoring logs
tail -f /var/log/pa-security/security-monitor.log

# Test monitoring manually
./scripts/security/security-monitor.sh monitor
```

**Solution**: Verify service configuration and log permissions

### Debug Commands

```bash
# Check system security status
sudo systemctl status fail2ban ufw ssh

# View security logs
sudo tail -f /var/log/auth.log /var/log/syslog

# Check network status
sudo netstat -tlnp
sudo ss -tlnp

# Verify Docker security
docker info | grep -i security
docker system df
```

## Maintenance

### Regular Maintenance Tasks

#### Daily
- Review security alerts and logs
- Check certificate expiration status
- Monitor system performance

#### Weekly
- Run vulnerability scans
- Review access logs
- Update threat detection rules

#### Monthly
- Rotate credentials
- Update security policies
- Review compliance status
- Conduct security training

#### Quarterly
- Full security audit
- Penetration testing
- Disaster recovery testing
- Security policy review

### Backup and Recovery

```bash
# Create security configuration backup
sudo tar -czf /var/backups/pa-security/config-$(date +%Y%m%d).tar.gz /etc/pa-security/

# Backup certificates
sudo tar -czf /var/backups/pa-security/certs-$(date +%Y%m%d).tar.gz /etc/ssl/certs/pa-ecosystem/

# Backup logs
sudo tar -czf /var/backups/pa-security/logs-$(date +%Y%m%d).tar.gz /var/log/pa-security/
```

## Conclusion

This guide provides comprehensive instructions for setting up and configuring the security infrastructure for the PA Ecosystem. Follow these steps carefully and validate each configuration before proceeding to the next step. Regular maintenance and monitoring are essential for maintaining security effectiveness.

For additional support, refer to the troubleshooting section or consult the security team documentation.
