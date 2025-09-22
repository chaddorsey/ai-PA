# Framework Rollback and Recovery Procedures

This directory contains comprehensive documentation for rolling back frameworks in the PA Ecosystem.

## Overview

The rollback procedures provide safe, tested methods for rolling back core frameworks to previous versions while maintaining system stability and data integrity.

## Quick Start

### 1. Emergency Rollback
```bash
# Quick emergency rollback
./scripts/rollback/emergency-rollback.sh --framework n8n --target-version 1.109.2

# Emergency rollback with specific backup
./scripts/rollback/emergency-rollback.sh --framework letta --target-version 0.11.7 --backup-path /var/backups/upgrades/letta/letta-backup-20250121-050000
```

### 2. Framework-Specific Rollback
```bash
# n8n rollback
./scripts/rollback/n8n/rollback-n8n.sh --backup-path /var/backups/upgrades/n8n/n8n-backup-20250121-050000

# Letta rollback
./scripts/rollback/letta/rollback-letta.sh --backup-path /var/backups/upgrades/letta/letta-backup-20250121-050000

# Graphiti rollback
./scripts/rollback/graphiti/rollback-graphiti.sh --backup-path /var/backups/upgrades/graphiti/graphiti-backup-20250121-050000
```

### 3. Multi-Framework Rollback
```bash
# Sequential rollback (recommended)
./scripts/rollback/coordination/rollback-all.sh --frameworks "n8n,letta,graphiti" --backup-base-path /var/backups/upgrades

# Parallel rollback (experimental)
./scripts/rollback/coordination/rollback-all.sh --frameworks "n8n,letta,graphiti" --backup-base-path /var/backups/upgrades --parallel
```

## Framework-Specific Procedures

### n8n (Workflow Automation)

**Current Version**: 1.109.2  
**Rollback Focus**: Data volume restoration, workflow preservation, API functionality

#### Rollback Process
1. **Pre-rollback**: Validate backup integrity and database connectivity
2. **Service Stop**: Stop n8n service gracefully
3. **Data Restoration**: Restore n8n data volume from backup
4. **Configuration**: Restore Docker Compose and configuration files
5. **Service Start**: Start n8n service and validate functionality

#### Key Considerations
- **Data Volume**: n8n data is stored in Docker volumes
- **Workflow Preservation**: All workflows and configurations are restored
- **API Compatibility**: Rollback maintains API functionality
- **Database Migration**: n8n handles database migrations automatically

#### Example Rollback
```bash
# Find latest backup
find /var/backups/upgrades/n8n -name "n8n-backup-*" -type d | sort -r | head -1

# Perform rollback
./scripts/rollback/n8n/rollback-n8n.sh --backup-path /var/backups/upgrades/n8n/n8n-backup-20250121-050000
```

### Letta (AI Agent Framework)

**Current Version**: 0.11.7  
**Rollback Focus**: Database restoration, agent configuration, MCP integration

#### Rollback Process
1. **Pre-rollback**: Validate backup integrity and database connectivity
2. **Service Stop**: Stop Letta service gracefully
3. **Database Restoration**: Restore Letta database schemas and data
4. **Configuration**: Restore MCP configuration and Docker Compose
5. **Service Start**: Start Letta service and restore agent configurations
6. **Validation**: Verify agent functionality and MCP integrations

#### Key Considerations
- **Database Schemas**: Letta uses PostgreSQL schemas (letta_agents, letta_embeddings)
- **Agent State**: Agent configurations are restored via API
- **MCP Integration**: MCP server configurations are preserved
- **API Functionality**: All API endpoints are validated after rollback

#### Example Rollback
```bash
# Find latest backup
find /var/backups/upgrades/letta -name "letta-backup-*" -type d | sort -r | head -1

# Perform rollback
./scripts/rollback/letta/rollback-letta.sh --backup-path /var/backups/upgrades/letta/letta-backup-20250121-050000
```

### Graphiti (Knowledge Graph Framework)

**Current Version**: 0.18.9  
**Rollback Focus**: Source code restoration, Neo4j data, MCP server rebuild

#### Rollback Process
1. **Pre-rollback**: Validate backup integrity and Neo4j connectivity
2. **Service Stop**: Stop Graphiti MCP server
3. **Source Restoration**: Restore Graphiti source code from backup
4. **Neo4j Restoration**: Restore Neo4j data if available
5. **Configuration**: Restore MCP server configuration
6. **Rebuild**: Rebuild and start Graphiti MCP server
7. **Validation**: Verify MCP server functionality and Neo4j connectivity

#### Key Considerations
- **Source Code**: Graphiti is built from source, not Docker images
- **Neo4j Data**: Knowledge graph data is restored from dumps
- **Python Dependencies**: Dependencies are managed via pyproject.toml
- **MCP Server**: HTTP endpoint functionality is validated

#### Example Rollback
```bash
# Find latest backup
find /var/backups/upgrades/graphiti -name "graphiti-backup-*" -type d | sort -r | head -1

# Perform rollback
./scripts/rollback/graphiti/rollback-graphiti.sh --backup-path /var/backups/upgrades/graphiti/graphiti-backup-20250121-050000
```

## Rollback Scenarios

### 1. Failed Upgrade Rollback
- **Trigger**: Upgrade validation failure or service startup failure
- **Process**: Restore from pre-upgrade backup
- **Validation**: Verify service functionality and data integrity
- **Recovery**: Complete service restoration with configuration

### 2. Service Failure Rollback
- **Trigger**: Service health check failure or critical errors
- **Process**: Restore service to last known good state
- **Validation**: Service functionality and integration testing
- **Recovery**: Full service restoration with monitoring

### 3. Data Corruption Rollback
- **Trigger**: Data integrity check failure or corruption detection
- **Process**: Restore data from backup with validation
- **Validation**: Data consistency and integrity verification
- **Recovery**: Database and configuration restoration

### 4. Configuration Error Rollback
- **Trigger**: Configuration validation failure or service misconfiguration
- **Process**: Restore configuration from backup
- **Validation**: Configuration consistency and service functionality
- **Recovery**: Service configuration restoration

## Safety Guidelines

### Before Any Rollback

1. **Assess Situation**
   ```bash
   # Check service status
   docker ps
   
   # Check service logs
   docker logs <service-name>
   
   # Verify backup availability
   find /var/backups/upgrades -name "*backup-*" -type d
   ```

2. **Validate Backup**
   ```bash
   # Check backup manifest
   cat <backup-path>/backup-manifest.json
   
   # Verify backup integrity
   ls -la <backup-path>/
   ```

3. **Plan Rollback**
   - Identify the appropriate backup
   - Determine rollback strategy
   - Plan for minimal downtime
   - Notify relevant team members

### During Rollback

1. **Monitor Progress**
   - Watch rollback logs
   - Monitor service status
   - Check for errors or warnings
   - Validate each step

2. **Handle Issues**
   - Document any problems encountered
   - Use emergency procedures if needed
   - Contact operations team for assistance

### After Rollback

1. **Validate Functionality**
   ```bash
   # Run health checks
   ./scripts/health-check-all.sh
   
   # Test API endpoints
   curl http://localhost:5678/health  # n8n
   curl http://localhost:8283/v1/health/  # Letta
   curl http://localhost:8082/health  # Graphiti
   ```

2. **Monitor Performance**
   - Check system metrics
   - Monitor service logs
   - Verify all integrations work
   - Test critical workflows

## Emergency Procedures

### Quick Rollback Commands
```bash
# Emergency rollback for any framework
./scripts/rollback/emergency-rollback.sh --framework <framework> --target-version <version>

# System-wide rollback
./scripts/rollback/coordination/rollback-all.sh --frameworks "n8n,letta,graphiti" --backup-base-path /var/backups/upgrades
```

### Recovery Commands
```bash
# Restore from system backup
./scripts/backup/restore-backup.sh --backup-id <backup-id>

# Restore specific framework
./scripts/rollback/<framework>/restore-from-backup.sh --backup-path <backup-path>
```

### Emergency Contacts
- **Operations Team**: For critical rollback issues
- **Development Team**: For rollback procedure questions
- **Database Team**: For data restoration issues

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
find /var/backups/upgrades -name "*backup-*" -type d

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

#### Data Integrity Issues
```bash
# Check database connectivity
docker exec <database-container> <database-command>

# Validate data consistency
./scripts/rollback/validate-data.sh --framework <framework>
```

### Emergency Recovery
```bash
# Full system recovery
./scripts/rollback/coordination/emergency-system-rollback.sh

# Individual service recovery
./scripts/rollback/<framework>/emergency-service-recovery.sh
```

## Best Practices

### Regular Maintenance
- **Backup Verification**: Regularly verify backup integrity
- **Rollback Testing**: Test rollback procedures in staging
- **Documentation Updates**: Keep rollback procedures current
- **Team Training**: Ensure team knows rollback procedures

### Rollback Planning
- **Backup Strategy**: Maintain multiple backup points
- **Rollback Windows**: Plan rollbacks during maintenance windows
- **Communication**: Notify users of planned rollbacks
- **Testing**: Validate rollback procedures regularly

### Quality Assurance
- **Automated Testing**: Use automated tests to validate rollbacks
- **Manual Testing**: Perform manual testing of critical functionality
- **Performance Testing**: Verify performance hasn't degraded
- **Integration Testing**: Test all framework integrations

## Monitoring and Alerting

### Rollback Monitoring
- **Service Health**: Monitor service health after rollback
- **Performance Metrics**: Track performance after rollback
- **Error Monitoring**: Monitor for rollback-related issues
- **Integration Status**: Check integration status after rollback

### Alerting
- **Rollback Notifications**: Alert team of rollback events
- **Failure Alerts**: Alert on rollback failures
- **Performance Alerts**: Alert on performance degradation
- **Integration Alerts**: Alert on integration failures

## Support and Maintenance

### Regular Maintenance
- **Monthly**: Review rollback procedures
- **Quarterly**: Test rollback procedures in staging
- **Annually**: Update rollback documentation

### Monitoring
- **Rollback Success Rate**: Track rollback success rates
- **Rollback Duration**: Monitor rollback completion times
- **Error Rates**: Track rollback-related errors
- **Performance Impact**: Monitor performance after rollbacks

### Documentation Updates
- **Procedure Updates**: Keep rollback procedures updated
- **Troubleshooting**: Update troubleshooting guides
- **Best Practices**: Refine best practices based on experience

## Contributing

When adding new frameworks:
1. Create framework-specific rollback directory
2. Follow the established procedure template
3. Include validation and testing procedures
4. Update this documentation

## Related Documentation

- [Upgrade Procedures](../upgrades/README.md)
- [Version Management](../version-management/README.md)
- [Compatibility Testing](../compatibility/README.md)
- [Health Monitoring](../../monitoring/README.md)
- [Troubleshooting Guide](../../troubleshooting-guide.md)
