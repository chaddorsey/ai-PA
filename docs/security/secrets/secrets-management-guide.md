# PA Ecosystem Secrets Management Guide

This guide provides comprehensive documentation for the PA Ecosystem's secrets management framework, ensuring secure credential storage, rotation, and access control.

## Overview

The secrets management framework provides:
- **Encrypted Storage**: All credentials encrypted at rest using AES-256-CBC
- **Automated Rotation**: Scheduled credential rotation for enhanced security
- **Audit Logging**: Complete audit trail of credential access and changes
- **Environment Integration**: Seamless integration with Docker and application environments
- **Backup and Recovery**: Secure backup and disaster recovery procedures

## Architecture

### Components

1. **Secrets Manager** (`scripts/secrets/secrets-manager.sh`)
   - Core secrets management functionality
   - Encryption/decryption operations
   - Inventory management

2. **Credential Rotation** (`scripts/secrets/credential-rotation.sh`)
   - Automated credential rotation
   - Service restart coordination
   - Rotation scheduling

3. **Audit System** (`scripts/audit/credential-audit.sh`)
   - Security vulnerability scanning
   - Hardcoded credential detection
   - Compliance reporting

### Security Model

- **Master Key**: Single encryption key for all secrets (stored in `config/secrets/master.key`)
- **Encryption**: AES-256-CBC with base64 encoding
- **Access Control**: File system permissions (700 for directories, 600 for files)
- **Audit Trail**: Complete logging of all operations

## Quick Start

### 1. Initialize Secrets Management

```bash
# Initialize the secrets management framework
./scripts/secrets/secrets-manager.sh initialize

# Verify initialization
ls -la config/secrets/
```

### 2. Store Your First Secret

```bash
# Store a database password
./scripts/secrets/secrets-manager.sh store postgres-password "$(openssl rand -base64 32)" password 90

# Store an API key
./scripts/secrets/secrets-manager.sh store openai-api-key "sk-your-actual-api-key" token 90
```

### 3. Generate Environment Variables

```bash
# Generate .env file with all secrets
./scripts/secrets/secrets-manager.sh generate-env .env

# Verify generated file
head -10 .env
```

### 4. Run Security Audit

```bash
# Audit for security issues
./scripts/audit/credential-audit.sh

# Review audit report
ls -la logs/audits/
```

## Detailed Usage

### Secrets Manager Commands

#### Initialize Framework
```bash
./scripts/secrets/secrets-manager.sh initialize
```
- Creates master encryption key
- Sets up secrets inventory
- Configures secure directories

#### Store Secrets
```bash
# Basic usage
./scripts/secrets/secrets-manager.sh store NAME VALUE [TYPE] [ROTATION_DAYS]

# Examples
./scripts/secrets/secrets-manager.sh store postgres-password "secure123" password 90
./scripts/secrets/secrets-manager.sh store api-key "sk-123" token 180
./scripts/secrets/secrets-manager.sh store encryption-key "$(openssl rand -base64 32)" key 365
```

**Secret Types:**
- `password`: Database and service passwords
- `token`: API keys and authentication tokens
- `key`: Encryption keys and certificates
- `uuid`: Unique identifiers

#### Retrieve Secrets
```bash
# Get secret value
./scripts/secrets/secrets-manager.sh retrieve postgres-password

# Use in scripts
DB_PASSWORD=$(./scripts/secrets/secrets-manager.sh retrieve postgres-password)
```

#### List All Secrets
```bash
./scripts/secrets/secrets-manager.sh list
```

#### Rotate Secrets
```bash
# Rotate with auto-generated value
./scripts/secrets/secrets-manager.sh rotate postgres-password

# Rotate with specific value
./scripts/secrets/secrets-manager.sh rotate api-key "new-api-key-value"
```

#### Backup and Restore
```bash
# Create backup
./scripts/secrets/secrets-manager.sh backup

# Restore from backup
./scripts/secrets/secrets-manager.sh restore backups/secrets/secrets-backup-20250121_143022.tar.gz
```

### Credential Rotation

#### Check Rotation Schedule
```bash
# Check which credentials need rotation
./scripts/secrets/credential-rotation.sh check-schedule

# Show rotation status
./scripts/secrets/credential-rotation.sh status
```

#### Manual Rotation
```bash
# Rotate specific credential
./scripts/secrets/credential-rotation.sh rotate postgres-password postgres database

# Rotate all credentials
./scripts/secrets/credential-rotation.sh rotate-all
```

#### Automated Rotation
```bash
# Set up automated rotation schedule
./scripts/secrets/credential-rotation.sh setup-schedule

# Verify cron jobs
crontab -l | grep credential-rotation
```

### Security Auditing

#### Run Credential Audit
```bash
# Full security audit
./scripts/audit/credential-audit.sh

# Audit with custom output file
./scripts/audit/credential-audit.sh --output custom-audit.json

# Verbose audit
./scripts/audit/credential-audit.sh --verbose
```

#### Review Audit Results
```bash
# View latest audit report
ls -la logs/audits/credential-audit-*.json

# Parse audit results
jq '.summary' logs/audits/credential-audit-*.json
jq '.recommendations' logs/audits/credential-audit-*.json
```

## Integration with Services

### Docker Compose Integration

Update your `docker-compose.yml` to use environment variables:

```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  n8n:
    image: n8nio/n8n
    environment:
      N8N_ENCRYPTION_KEY: ${N8N_ENCRYPTION_KEY}
    volumes:
      - n8n_data:/home/node/.n8n
```

### Application Integration

#### Node.js Applications
```javascript
// Load environment variables
require('dotenv').config();

// Access secrets
const dbPassword = process.env.POSTGRES_PASSWORD;
const apiKey = process.env.OPENAI_API_KEY;
```

#### Python Applications
```python
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Access secrets
db_password = os.getenv('POSTGRES_PASSWORD')
api_key = os.getenv('OPENAI_API_KEY')
```

#### Shell Scripts
```bash
#!/bin/bash
# Load environment variables
source .env

# Use secrets
echo "Connecting to database with password: $POSTGRES_PASSWORD"
```

## Security Best Practices

### 1. Credential Storage
- **Never hardcode credentials** in code or configuration files
- **Use strong passwords** (minimum 32 characters)
- **Rotate credentials regularly** (every 90 days for critical systems)
- **Store credentials separately** from application code

### 2. Access Control
- **Limit access** to secrets management tools
- **Use least privilege** principle for credential access
- **Monitor credential usage** through audit logs
- **Implement role-based access** for different environments

### 3. Network Security
- **Use HTTPS** for all external communications
- **Implement network segmentation** to isolate services
- **Use firewall rules** to restrict access to secrets management
- **Encrypt data in transit** for all credential operations

### 4. Monitoring and Auditing
- **Enable audit logging** for all credential operations
- **Monitor for security violations** and suspicious activity
- **Regular security assessments** using credential audit tools
- **Incident response procedures** for credential breaches

### 5. Backup and Recovery
- **Regular backups** of encrypted credential storage
- **Test recovery procedures** to ensure business continuity
- **Secure backup storage** with appropriate access controls
- **Document recovery procedures** for emergency situations

## Troubleshooting

### Common Issues

#### Master Key Not Found
```bash
Error: Master key not found. Run 'initialize' first.
```
**Solution**: Run `./scripts/secrets/secrets-manager.sh initialize`

#### Permission Denied
```bash
Error: Permission denied accessing secrets directory
```
**Solution**: Check file permissions:
```bash
chmod 700 config/secrets/
chmod 600 config/secrets/*
```

#### Secret Not Found
```bash
Error: Secret 'secret-name' not found
```
**Solution**: Check if secret exists:
```bash
./scripts/secrets/secrets-manager.sh list
```

#### Decryption Failed
```bash
Error: Failed to decrypt secret
```
**Solution**: Verify master key and secret integrity:
```bash
# Check master key
ls -la config/secrets/master.key

# Verify inventory
jq '.secrets' config/secrets/inventory.json
```

### Recovery Procedures

#### Lost Master Key
If the master key is lost, all secrets must be recreated:
1. Document all required secrets
2. Reinitialize secrets management
3. Store all secrets again with new values
4. Update all service configurations

#### Corrupted Inventory
If the inventory file is corrupted:
1. Restore from backup
2. If no backup, recreate inventory and re-store secrets
3. Verify all services can access their credentials

#### Service Integration Issues
If services cannot access credentials:
1. Check environment variable names
2. Verify `.env` file generation
3. Check service restart procedures
4. Validate credential retrieval

## Compliance and Standards

### Security Standards
- **NIST Cybersecurity Framework**: Implementation of identify, protect, detect, respond, recover
- **ISO 27001**: Information security management system compliance
- **SOC 2**: Security, availability, and confidentiality controls
- **PCI DSS**: Payment card industry data security standards

### Audit Requirements
- **Credential Access Logging**: All access attempts logged
- **Rotation Compliance**: Regular credential rotation documented
- **Incident Response**: Security incident procedures documented
- **Backup Verification**: Regular backup testing and validation

### Documentation Requirements
- **Security Policies**: Comprehensive security policy documentation
- **Procedures**: Step-by-step operational procedures
- **Training Materials**: Security awareness and training documentation
- **Incident Reports**: Security incident documentation and analysis

## Advanced Features

### Custom Secret Types
```bash
# Define custom secret type
./scripts/secrets/secrets-manager.sh store custom-secret "value" custom-type 90
```

### Environment-Specific Secrets
```bash
# Development environment
./scripts/secrets/secrets-manager.sh store postgres-password-dev "dev-password"

# Production environment  
./scripts/secrets/secrets-manager.sh store postgres-password-prod "prod-password"
```

### Integration with CI/CD
```bash
# In CI/CD pipeline
./scripts/secrets/secrets-manager.sh generate-env .env.ci
docker-compose --env-file .env.ci up -d
```

### Monitoring Integration
```bash
# Health check for secrets management
./scripts/secrets/secrets-manager.sh list | grep -q "expires" && echo "OK" || echo "ERROR"
```

## Support and Maintenance

### Regular Maintenance Tasks
- **Weekly**: Check rotation schedule and expired credentials
- **Monthly**: Run security audits and review findings
- **Quarterly**: Update security policies and procedures
- **Annually**: Review and update encryption standards

### Support Resources
- **Documentation**: This guide and related security documentation
- **Scripts**: All management scripts include help and error messages
- **Logs**: Comprehensive logging for troubleshooting
- **Audit Reports**: Detailed security assessment reports

### Emergency Contacts
- **Security Team**: For security incidents and breaches
- **System Administrators**: For operational issues
- **Development Team**: For integration and configuration issues
