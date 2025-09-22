# Framework Rollback and Recovery Procedures

This directory contains comprehensive rollback and recovery procedures for the PA Ecosystem, providing safe and tested rollback capabilities for all core frameworks.

## Overview

The rollback procedures ensure:
- **Quick Recovery**: Fast rollback from failed upgrades
- **Data Integrity**: Safe data and configuration recovery
- **Minimal Downtime**: Coordinated rollback with service availability
- **Validation**: Comprehensive rollback validation and testing

## Framework-Specific Procedures

### Core Frameworks
- **n8n** (`n8n/`) - Workflow automation framework rollback
- **Letta** (`letta/`) - AI agent framework rollback  
- **Graphiti** (`graphiti/`) - Knowledge graph framework rollback

### Support Scripts
- **coordination/** - Service rollback coordination and orchestration
- **validation/** - Rollback validation and testing
- **recovery/** - Data and configuration recovery procedures

## Quick Start

### 1. Emergency Rollback
```bash
# Quick rollback to previous version
./scripts/rollback/emergency-rollback.sh --framework <framework> --target-version <version>

# Rollback with backup restoration
./scripts/rollback/emergency-rollback.sh --framework n8n --backup-path /var/backups/upgrades/n8n/n8n-backup-20250121-050000
```

### 2. Framework-Specific Rollback
```bash
# n8n rollback
./scripts/rollback/n8n/rollback-n8n.sh --backup-path <backup-path>

# Letta rollback
./scripts/rollback/letta/rollback-letta.sh --backup-path <backup-path>

# Graphiti rollback
./scripts/rollback/graphiti/rollback-graphiti.sh --backup-path <backup-path>
```

### 3. Coordinated Rollback
```bash
# Multi-framework rollback
./scripts/rollback/coordination/rollback-all.sh --frameworks "n8n,letta,graphiti" --backup-base-path <backup-path>
```

## Rollback Scenarios

### 1. Failed Upgrade Rollback
- **Trigger**: Upgrade validation failure
- **Process**: Restore from pre-upgrade backup
- **Validation**: Verify service functionality
- **Recovery**: Data and configuration integrity

### 2. Service Failure Rollback
- **Trigger**: Service health check failure
- **Process**: Restore service to last known good state
- **Validation**: Service functionality and integration
- **Recovery**: Full service restoration

### 3. Data Corruption Rollback
- **Trigger**: Data integrity check failure
- **Process**: Restore data from backup
- **Validation**: Data consistency and integrity
- **Recovery**: Database and configuration restoration

### 4. Configuration Error Rollback
- **Trigger**: Configuration validation failure
- **Process**: Restore configuration from backup
- **Validation**: Configuration consistency
- **Recovery**: Service configuration restoration

## Safety Guidelines

### Before Any Rollback
1. **Assess Situation**: Understand the failure and impact
2. **Locate Backup**: Identify appropriate backup for rollback
3. **Plan Rollback**: Determine rollback strategy and timeline
4. **Notify Team**: Alert relevant team members

### During Rollback
1. **Follow Procedures**: Execute rollback steps in exact order
2. **Monitor Progress**: Watch for errors or warnings
3. **Validate Each Step**: Confirm success before proceeding
4. **Document Issues**: Log any problems encountered

### After Rollback
1. **Validate Functionality**: Test all critical workflows
2. **Monitor Performance**: Check system health and metrics
3. **Update Documentation**: Record rollback details and lessons learned
4. **Plan Next Steps**: Determine if upgrade retry or alternative approach needed

## Emergency Procedures

### Quick Rollback Commands
```bash
# Emergency rollback for any framework
./scripts/rollback/emergency-rollback.sh --framework <framework> --target-version <version>

# System-wide rollback
./scripts/rollback/coordination/emergency-system-rollback.sh --backup-base-path <backup-path>
```

### Recovery Commands
```bash
# Restore from system backup
./scripts/backup/restore-backup.sh --backup-id <backup-id>

# Restore specific framework
./scripts/rollback/<framework>/restore-from-backup.sh --backup-path <backup-path>
```

## Rollback Validation

### Pre-Rollback Validation
- Verify backup integrity and availability
- Check rollback target version compatibility
- Validate rollback procedures and scripts
- Confirm rollback authorization and approval

### Post-Rollback Validation
- Test service functionality and integration
- Verify data integrity and consistency
- Check configuration correctness
- Validate system performance and stability

### Rollback Success Criteria
- All services are running and healthy
- Data integrity is maintained
- Configuration is consistent
- System performance is acceptable
- All integrations are working

## Troubleshooting

### Common Rollback Issues

#### Backup Not Found
```bash
# List available backups
./scripts/backup/list-backups.sh

# Create emergency backup
./scripts/backup/create-backup.sh --emergency
```

#### Rollback Script Failure
```bash
# Check rollback logs
tail -f /var/log/rollback/rollback-*.log

# Manual rollback steps
./scripts/rollback/manual-rollback-guide.sh --framework <framework>
```

#### Service Won't Start After Rollback
```bash
# Check service logs
docker logs <service-name>

# Validate service configuration
./scripts/rollback/validate-service.sh --framework <framework>
```

### Emergency Recovery
```bash
# Full system recovery
./scripts/rollback/coordination/emergency-system-rollback.sh

# Individual service recovery
./scripts/rollback/<framework>/emergency-service-recovery.sh
```

## Support

For rollback issues:
1. Check troubleshooting documentation
2. Review rollback logs in `/var/log/rollback/`
3. Consult emergency procedures if needed
4. Contact operations team for assistance

## Contributing

When adding new frameworks:
1. Create framework-specific rollback directory
2. Follow the established procedure template
3. Include validation and testing procedures
4. Update this README with new framework information
