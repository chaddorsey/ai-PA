# Framework Upgrade Procedures

This directory contains framework-specific upgrade procedures for the PA Ecosystem, providing safe and tested upgrade paths for all core frameworks.

## Overview

The upgrade procedures ensure:
- **Safe Upgrades**: Tested procedures with rollback capability
- **Minimal Downtime**: Coordinated upgrades with service availability
- **Data Integrity**: Configuration and data migration validation
- **Compatibility**: Version compatibility checking and validation

## Framework-Specific Procedures

### Core Frameworks
- **n8n** (`n8n/`) - Workflow automation framework
- **Letta** (`letta/`) - AI agent framework  
- **Graphiti** (`graphiti/`) - Knowledge graph framework

### Support Scripts
- **coordination/** - Service coordination and orchestration
- **validation/** - Upgrade validation and testing
- **rollback/** - Rollback procedures and recovery

## Quick Start

### 1. Pre-Upgrade Checklist
```bash
# Run pre-upgrade validation
./scripts/upgrades/validation/pre-upgrade-check.sh

# Create system backup
./scripts/backup/create-backup.sh --pre-upgrade
```

### 2. Framework Upgrade
```bash
# Upgrade specific framework
./scripts/upgrades/n8n/upgrade-n8n.sh --version 1.110.0
./scripts/upgrades/letta/upgrade-letta.sh --version 0.12.0
./scripts/upgrades/graphiti/upgrade-graphiti.sh --version 0.19.0
```

### 3. Post-Upgrade Validation
```bash
# Validate upgrade success
./scripts/upgrades/validation/post-upgrade-validation.sh

# Run system health checks
./scripts/health-check-all.sh
```

## Safety Guidelines

### Before Any Upgrade
1. **Backup Current State**: Always create full system backup
2. **Review Release Notes**: Check for breaking changes
3. **Test in Staging**: Validate procedures in test environment
4. **Schedule Maintenance**: Plan for minimal downtime

### During Upgrade
1. **Follow Procedures**: Execute steps in exact order
2. **Monitor Progress**: Watch for errors or warnings
3. **Validate Each Step**: Confirm success before proceeding
4. **Document Issues**: Log any problems encountered

### After Upgrade
1. **Validate Functionality**: Test all critical workflows
2. **Monitor Performance**: Check system health and metrics
3. **Update Documentation**: Record version changes
4. **Clean Up**: Remove old containers and images

## Emergency Procedures

### Quick Rollback
```bash
# Rollback to previous version
./scripts/upgrades/rollback/emergency-rollback.sh --framework <framework> --target-version <version>
```

### System Recovery
```bash
# Restore from backup
./scripts/backup/restore-backup.sh --backup-id <backup-id>
```

## Support

For upgrade issues:
1. Check the troubleshooting section in each framework's documentation
2. Review the upgrade logs in `/var/log/upgrades/`
3. Consult the rollback procedures if needed
4. Contact the operations team for assistance

## Contributing

When adding new frameworks:
1. Create framework-specific upgrade directory
2. Follow the established procedure template
3. Include validation and rollback procedures
4. Update this README with new framework information
