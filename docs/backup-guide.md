# PA Ecosystem Backup and Restore Guide

**Comprehensive guide for backing up and restoring the PA ecosystem**

This guide provides complete instructions for backing up and restoring all components of the PA ecosystem, ensuring data safety and system recovery capabilities.

## 📋 Table of Contents

1. [Backup Overview](#backup-overview)
2. [Backup Components](#backup-components)
3. [Backup Scripts](#backup-scripts)
4. [Backup Procedures](#backup-procedures)
5. [Restore Procedures](#restore-procedures)
6. [Backup Scheduling](#backup-scheduling)
7. [Backup Verification](#backup-verification)
8. [Troubleshooting](#troubleshooting)
9. [Best Practices](#best-practices)

## 🔄 Backup Overview

### What Gets Backed Up

The PA ecosystem backup system captures all critical data and configurations:

#### **Databases**
- **PostgreSQL**: Main application database
- **Letta Database**: AI agent memory and configurations
- **n8n Database**: Workflow configurations and execution history

#### **Data Volumes**
- **Letta Data**: AI agent memory, blocks, and core memory
- **n8n Data**: Workflow definitions and execution data
- **Open WebUI Data**: User data, conversations, and settings
- **Neo4j Data**: Graph database for relationships
- **Supabase Storage**: File storage and media

#### **Configuration Files**
- **Environment Variables**: `.env` file with all settings
- **Docker Compose**: Service definitions and configurations
- **Deployment Scripts**: All deployment and management scripts
- **Documentation**: System documentation and guides

#### **Service Configurations**
- **Letta Agent**: Agent configuration and memory files
- **n8n Workflows**: Workflow definitions and settings
- **Service Settings**: Individual service configurations

### Backup Types

#### **Full Backup**
- All databases, volumes, and configurations
- Complete system state capture
- Recommended for major updates or migrations

#### **Incremental Backup**
- Only changed data since last backup
- Faster and more storage-efficient
- Suitable for regular scheduled backups

#### **Configuration-Only Backup**
- Only configuration files and settings
- Quick backup for configuration changes
- Useful for testing and development

#### **Data-Only Backup**
- Only databases and data volumes
- Excludes configuration files
- Useful for data migration

## 🗄️ Backup Components

### Database Backups

#### PostgreSQL Databases
```bash
# Main application database
postgres_YYYYMMDD_HHMMSS.sql

# Letta AI agent database
letta_YYYYMMDD_HHMMSS.sql

# n8n workflow database
n8n_YYYYMMDD_HHMMSS.sql
```

#### Neo4j Database
```bash
# Graph database backup
neo4j_data_YYYYMMDD_HHMMSS.tar.gz
```

### Volume Backups

#### Application Data
```bash
# Letta AI agent data
letta_data_YYYYMMDD_HHMMSS.tar.gz

# n8n workflow data
n8n_data_YYYYMMDD_HHMMSS.tar.gz

# Open WebUI data
openwebui_data_YYYYMMDD_HHMMSS.tar.gz

# Supabase storage
supabase_storage_YYYYMMDD_HHMMSS.tar.gz
```

### Configuration Backups

#### System Configuration
```bash
# Environment variables
env_YYYYMMDD_HHMMSS.tar.gz

# Docker Compose configuration
docker-compose_YYYYMMDD_HHMMSS.tar.gz

# Deployment scripts
deployment_YYYYMMDD_HHMMSS.tar.gz

# Documentation
docs_YYYYMMDD_HHMMSS.tar.gz
```

#### Service Configuration
```bash
# Letta agent configuration
letta_agent.json
letta_blocks.json
letta_core_memory.json

# n8n workflow configuration
n8n_workflows.json
```

## 🛠️ Backup Scripts

### Main Backup Script

#### `deployment/scripts/backup.sh`
**Primary backup script for all backup operations**

```bash
# Full backup
./deployment/scripts/backup.sh

# Dry run (show what would be backed up)
./deployment/scripts/backup.sh --dry-run

# Incremental backup
./deployment/scripts/backup.sh --incremental

# Configuration only
./deployment/scripts/backup.sh --config-only

# Data only
./deployment/scripts/backup.sh --data-only

# Custom output directory
./deployment/scripts/backup.sh --output /custom/backup/dir

# Custom backup name
./deployment/scripts/backup.sh --name my-backup
```

#### Options
- `--dry-run`: Show what would be backed up without doing it
- `--full`: Perform full backup (default)
- `--incremental`: Perform incremental backup
- `--config-only`: Backup only configuration files
- `--data-only`: Backup only data volumes
- `--services-only`: Backup only service configurations
- `--output DIR`: Specify backup output directory
- `--name NAME`: Specify backup name
- `--verbose`: Enable verbose output
- `--quiet`: Suppress output except errors

### Restore Script

#### `deployment/scripts/restore.sh`
**Primary restore script for all restore operations**

```bash
# Restore from latest backup
./deployment/scripts/restore.sh latest

# Restore from specific backup
./deployment/scripts/restore.sh /backups/backup-20240121_120000

# Dry run (show what would be restored)
./deployment/scripts/restore.sh --dry-run latest

# Force restore (stop services automatically)
./deployment/scripts/restore.sh --force latest

# Configuration only
./deployment/scripts/restore.sh --config-only latest

# Data only
./deployment/scripts/restore.sh --data-only latest
```

#### Options
- `--dry-run`: Show what would be restored without doing it
- `--force`: Force restore even if services are running
- `--config-only`: Restore only configuration files
- `--data-only`: Restore only data volumes
- `--services-only`: Restore only service configurations
- `--verbose`: Enable verbose output
- `--quiet`: Suppress output except errors
- `--yes`: Skip confirmation prompts

### Backup Scheduling Script

#### `deployment/scripts/schedule-backup.sh`
**Manages automated backup scheduling and retention**

```bash
# Install daily backups with 30-day retention
./deployment/scripts/schedule-backup.sh install --frequency daily --retention 30

# Install weekly backups with 90-day retention
./deployment/scripts/schedule-backup.sh install --frequency weekly --retention 90

# Show backup schedule status
./deployment/scripts/schedule-backup.sh status

# Run scheduled backup manually
./deployment/scripts/schedule-backup.sh run

# List all backups
./deployment/scripts/schedule-backup.sh list

# Clean up old backups
./deployment/scripts/schedule-backup.sh cleanup --retention 30

# Test backup configuration
./deployment/scripts/schedule-backup.sh test
```

#### Commands
- `install`: Install backup scheduling
- `uninstall`: Remove backup scheduling
- `status`: Show backup schedule status
- `run`: Run scheduled backup
- `list`: List available backups
- `cleanup`: Clean up old backups
- `test`: Test backup configuration

### Backup Verification Script

#### `deployment/scripts/verify-backup.sh`
**Verifies backup integrity and completeness**

```bash
# Verify latest backup
./deployment/scripts/verify-backup.sh --latest

# Verify specific backup
./deployment/scripts/verify-backup.sh /backups/backup-20240121_120000

# Verify all backups
./deployment/scripts/verify-backup.sh --all

# Verify with integrity check
./deployment/scripts/verify-backup.sh --latest --check-integrity

# Verify with size check
./deployment/scripts/verify-backup.sh --latest --check-size
```

#### Options
- `--all`: Verify all backups
- `--latest`: Verify latest backup only
- `--check-integrity`: Check file integrity (checksums)
- `--check-size`: Check backup sizes
- `--check-manifest`: Check backup manifest
- `--verbose`: Enable verbose output
- `--quiet`: Suppress output except errors

## 📋 Backup Procedures

### Manual Backup

#### Step 1: Prepare for Backup
```bash
# Check system status
docker-compose ps

# Check disk space
df -h

# Check backup directory
ls -la deployment/backups/
```

#### Step 2: Run Backup
```bash
# Full backup
./deployment/scripts/backup.sh

# Or with specific options
./deployment/scripts/backup.sh --verbose --name my-backup
```

#### Step 3: Verify Backup
```bash
# Verify backup integrity
./deployment/scripts/verify-backup.sh --latest --check-integrity

# Check backup contents
ls -la deployment/backups/latest/
```

### Automated Backup

#### Step 1: Install Backup Scheduling
```bash
# Install daily backups
./deployment/scripts/schedule-backup.sh install --frequency daily --retention 30

# Check status
./deployment/scripts/schedule-backup.sh status
```

#### Step 2: Monitor Backups
```bash
# List backups
./deployment/scripts/schedule-backup.sh list

# Check backup logs
tail -f deployment/logs/scheduled-backup.log
```

#### Step 3: Test Backup
```bash
# Test backup configuration
./deployment/scripts/schedule-backup.sh test

# Run manual backup
./deployment/scripts/schedule-backup.sh run
```

### Emergency Backup

#### Quick Backup
```bash
# Quick configuration backup
./deployment/scripts/backup.sh --config-only --name emergency-config

# Quick data backup
./deployment/scripts/backup.sh --data-only --name emergency-data
```

#### Critical Data Backup
```bash
# Backup only critical databases
docker-compose exec supabase-db pg_dump -U postgres postgres > emergency_postgres.sql
docker-compose exec supabase-db pg_dump -U postgres letta > emergency_letta.sql
```

## 🔄 Restore Procedures

### Full System Restore

#### Step 1: Prepare for Restore
```bash
# Check available backups
./deployment/scripts/schedule-backup.sh list

# Verify backup integrity
./deployment/scripts/verify-backup.sh --latest --check-integrity

# Stop services
docker-compose down
```

#### Step 2: Run Restore
```bash
# Restore from latest backup
./deployment/scripts/restore.sh --force latest

# Or restore from specific backup
./deployment/scripts/restore.sh --force /backups/backup-20240121_120000
```

#### Step 3: Verify Restore
```bash
# Check service status
docker-compose ps

# Run health check
./deployment/scripts/health-check.sh

# Test functionality
curl -f http://localhost:8283/v1/health/
```

### Partial Restore

#### Configuration Only
```bash
# Restore only configuration
./deployment/scripts/restore.sh --config-only latest

# Restart services
docker-compose restart
```

#### Data Only
```bash
# Stop services
docker-compose down

# Restore only data
./deployment/scripts/restore.sh --data-only latest

# Start services
docker-compose up -d
```

### Emergency Restore

#### Quick Restore
```bash
# Restore with force
./deployment/scripts/restore.sh --force --yes latest
```

#### Manual Restore
```bash
# Restore specific components
docker-compose exec supabase-db psql -U postgres postgres < backup_postgres.sql
docker-compose exec supabase-db psql -U postgres letta < backup_letta.sql
```

## ⏰ Backup Scheduling

### Schedule Types

#### Hourly Backups
```bash
# Install hourly backups
./deployment/scripts/schedule-backup.sh install --frequency hourly --retention 7
```

#### Daily Backups
```bash
# Install daily backups
./deployment/scripts/schedule-backup.sh install --frequency daily --retention 30
```

#### Weekly Backups
```bash
# Install weekly backups
./deployment/scripts/schedule-backup.sh install --frequency weekly --retention 90
```

#### Monthly Backups
```bash
# Install monthly backups
./deployment/scripts/schedule-backup.sh install --frequency monthly --retention 365
```

### Retention Policies

#### Short-term Retention (7-30 days)
- Hourly backups: 7 days
- Daily backups: 30 days
- For development and testing

#### Medium-term Retention (30-90 days)
- Daily backups: 30 days
- Weekly backups: 90 days
- For production systems

#### Long-term Retention (90-365 days)
- Weekly backups: 90 days
- Monthly backups: 365 days
- For compliance and archival

### Monitoring

#### Check Schedule Status
```bash
# Show schedule status
./deployment/scripts/schedule-backup.sh status

# Check cron jobs
crontab -l
```

#### Monitor Backup Logs
```bash
# Check backup logs
tail -f deployment/logs/scheduled-backup.log

# Check system logs
journalctl -u cron
```

## ✅ Backup Verification

### Verification Types

#### Basic Verification
```bash
# Verify latest backup
./deployment/scripts/verify-backup.sh --latest
```

#### Integrity Verification
```bash
# Verify with integrity check
./deployment/scripts/verify-backup.sh --latest --check-integrity
```

#### Complete Verification
```bash
# Verify all backups
./deployment/scripts/verify-backup.sh --all --check-integrity --check-size
```

### Verification Checks

#### File Integrity
- Archive integrity (tar.gz files)
- SQL file validity
- JSON file validity
- File completeness

#### Backup Structure
- Required directories present
- Backup files present
- Manifest file present
- File permissions correct

#### Size Verification
- Total backup size
- Individual component sizes
- Unusually small backups detected
- Storage usage monitoring

## 🐛 Troubleshooting

### Common Issues

#### Backup Fails
```bash
# Check Docker status
docker info

# Check disk space
df -h

# Check backup logs
tail -f deployment/logs/backup-*.log
```

#### Restore Fails
```bash
# Check backup integrity
./deployment/scripts/verify-backup.sh --latest

# Check service status
docker-compose ps

# Check restore logs
tail -f deployment/logs/restore-*.log
```

#### Schedule Issues
```bash
# Check cron status
systemctl status cron

# Check cron jobs
crontab -l

# Test backup manually
./deployment/scripts/schedule-backup.sh run
```

### Recovery Procedures

#### Corrupted Backup
```bash
# Verify backup integrity
./deployment/scripts/verify-backup.sh --latest --check-integrity

# Try alternative backup
./deployment/scripts/restore.sh --force /backups/backup-YYYYMMDD_HHMMSS
```

#### Missing Backup
```bash
# List available backups
./deployment/scripts/schedule-backup.sh list

# Check backup directory
ls -la deployment/backups/

# Restore from available backup
./deployment/scripts/restore.sh --force /backups/available-backup
```

## 📚 Best Practices

### Backup Strategy

#### 3-2-1 Rule
- **3 copies** of important data
- **2 different media types**
- **1 offsite backup**

#### Backup Frequency
- **Development**: Daily backups
- **Production**: Hourly + daily backups
- **Critical Systems**: Continuous + hourly backups

#### Retention Policy
- **Short-term**: 7-30 days (quick recovery)
- **Medium-term**: 30-90 days (point-in-time recovery)
- **Long-term**: 90-365 days (compliance)

### Security

#### Backup Encryption
```bash
# Encrypt sensitive backups
gpg --symmetric --cipher-algo AES256 backup.tar.gz
```

#### Access Control
```bash
# Secure backup directory
chmod 700 deployment/backups/
chown root:root deployment/backups/
```

#### Offsite Storage
```bash
# Sync to remote storage
rsync -avz deployment/backups/ user@remote:/backups/
```

### Monitoring

#### Backup Monitoring
```bash
# Monitor backup success
./deployment/scripts/schedule-backup.sh status

# Check backup logs
tail -f deployment/logs/scheduled-backup.log
```

#### Storage Monitoring
```bash
# Monitor disk usage
df -h deployment/backups/

# Clean up old backups
./deployment/scripts/schedule-backup.sh cleanup --retention 30
```

### Testing

#### Regular Testing
```bash
# Test backup weekly
./deployment/scripts/schedule-backup.sh test

# Test restore monthly
./deployment/scripts/restore.sh --dry-run latest
```

#### Disaster Recovery Testing
```bash
# Test full restore
./deployment/scripts/restore.sh --force latest

# Verify system functionality
./deployment/scripts/health-check.sh
```

---

**🎉 Backup System Complete!** This comprehensive backup and restore system ensures your PA ecosystem data is safe and recoverable. Follow the procedures and best practices to maintain data integrity and system reliability.
