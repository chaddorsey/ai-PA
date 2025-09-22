# Framework Upgrade Procedures

This directory contains comprehensive documentation for upgrading frameworks in the PA Ecosystem.

## Overview

The upgrade procedures provide safe, tested methods for upgrading core frameworks while maintaining system stability and data integrity.

## Quick Start

### 1. Pre-Upgrade Validation
```bash
# Validate system readiness
./scripts/upgrades/validation/pre-upgrade-check.sh

# Check specific framework
./scripts/upgrades/validation/pre-upgrade-check.sh --framework n8n
```

### 2. Single Framework Upgrade
```bash
# Upgrade n8n
./scripts/upgrades/n8n/upgrade-n8n.sh --version 1.110.0

# Upgrade Letta
./scripts/upgrades/letta/upgrade-letta.sh --version 0.12.0

# Upgrade Graphiti
./scripts/upgrades/graphiti/upgrade-graphiti.sh --version 0.19.0
```

### 3. Multi-Framework Upgrade
```bash
# Sequential upgrade (recommended)
./scripts/upgrades/coordination/upgrade-all.sh --frameworks "n8n,letta,graphiti" --sequential

# Parallel upgrade (experimental)
./scripts/upgrades/coordination/upgrade-all.sh --frameworks "n8n,letta,graphiti" --parallel
```

## Framework-Specific Procedures

### n8n (Workflow Automation)

**Current Version**: 1.109.2  
**Upgrade Path**: Minor version upgrades recommended

#### Upgrade Process
1. **Pre-upgrade**: Validate workflows and database connectivity
2. **Backup**: Create n8n data and configuration backup
3. **Upgrade**: Update Docker image and restart service
4. **Validation**: Verify workflows and API functionality

#### Key Considerations
- **Database Migration**: n8n handles database migrations automatically
- **Workflow Compatibility**: Test critical workflows after upgrade
- **API Changes**: Review release notes for API breaking changes

#### Example Upgrade
```bash
# Dry run to see what would happen
./scripts/upgrades/n8n/upgrade-n8n.sh --version 1.110.0 --dry-run

# Perform actual upgrade
./scripts/upgrades/n8n/upgrade-n8n.sh --version 1.110.0
```

### Letta (AI Agent Framework)

**Current Version**: 0.11.7  
**Upgrade Path**: Minor version upgrades recommended

#### Upgrade Process
1. **Pre-upgrade**: Validate agent functionality and database connectivity
2. **Backup**: Create agent configurations and database backup
3. **Upgrade**: Update Docker image and restart service
4. **Validation**: Verify agent functionality and MCP integrations

#### Key Considerations
- **Agent State**: Agents maintain state across upgrades
- **MCP Integration**: Verify MCP server connectivity after upgrade
- **Database Schema**: Letta handles schema migrations automatically

#### Example Upgrade
```bash
# Dry run to see what would happen
./scripts/upgrades/letta/upgrade-letta.sh --version 0.12.0 --dry-run

# Perform actual upgrade
./scripts/upgrades/letta/upgrade-letta.sh --version 0.12.0
```

### Graphiti (Knowledge Graph Framework)

**Current Version**: 0.18.9  
**Upgrade Path**: Patch version upgrades recommended

#### Upgrade Process
1. **Pre-upgrade**: Validate knowledge graph and Neo4j connectivity
2. **Backup**: Create source code and Neo4j data backup
3. **Upgrade**: Update pyproject.toml and rebuild container
4. **Validation**: Verify MCP server and knowledge graph functionality

#### Key Considerations
- **Source Code**: Graphiti is built from source, not Docker images
- **Dependencies**: Python dependencies may need updating
- **Neo4j Compatibility**: Verify Neo4j version compatibility

#### Example Upgrade
```bash
# Dry run to see what would happen
./scripts/upgrades/graphiti/upgrade-graphiti.sh --version 0.19.0 --dry-run

# Perform actual upgrade
./scripts/upgrades/graphiti/upgrade-graphiti.sh --version 0.19.0
```

## Upgrade Strategies

### Sequential Upgrades (Recommended)
- **Benefits**: Controlled, predictable, easier troubleshooting
- **Drawbacks**: Longer total upgrade time
- **Use Case**: Production environments, critical systems

### Parallel Upgrades (Experimental)
- **Benefits**: Faster total upgrade time
- **Drawbacks**: Higher complexity, harder troubleshooting
- **Use Case**: Development environments, non-critical systems

## Safety Guidelines

### Before Any Upgrade

1. **System Validation**
   ```bash
   # Run comprehensive pre-upgrade checks
   ./scripts/upgrades/validation/pre-upgrade-check.sh
   ```

2. **Backup Creation**
   ```bash
   # Create system backup
   ./scripts/backup/create-backup.sh --pre-upgrade
   ```

3. **Review Release Notes**
   - Check for breaking changes
   - Review compatibility requirements
   - Plan for any configuration changes

### During Upgrade

1. **Monitor Progress**
   - Watch upgrade logs
   - Monitor system resources
   - Check for errors or warnings

2. **Validate Each Step**
   - Confirm success before proceeding
   - Test functionality after each framework
   - Document any issues encountered

### After Upgrade

1. **Comprehensive Testing**
   ```bash
   # Run post-upgrade validation
   ./scripts/upgrades/validation/post-upgrade-validation.sh
   
   # Run health checks
   ./scripts/health-check-all.sh
   ```

2. **Performance Monitoring**
   - Monitor system metrics
   - Check for performance regressions
   - Verify all integrations work

## Troubleshooting

### Common Issues

#### Upgrade Fails
```bash
# Check logs
tail -f /var/log/upgrades/<framework>-upgrade-*.log

# Rollback if needed
./scripts/upgrades/rollback/rollback-<framework>.sh --backup-path <backup-path>
```

#### Service Won't Start
```bash
# Check container logs
docker logs <container-name>

# Check service health
./scripts/health-check-all.sh
```

#### Database Issues
```bash
# Check database connectivity
docker exec <database-container> <database-command>

# Restore from backup if needed
./scripts/backup/restore-backup.sh --backup-id <backup-id>
```

### Emergency Procedures

#### Quick Rollback
```bash
# Emergency rollback to previous version
./scripts/upgrades/rollback/emergency-rollback.sh --framework <framework> --target-version <version>
```

#### System Recovery
```bash
# Full system recovery from backup
./scripts/backup/restore-backup.sh --backup-id <backup-id>
```

## Best Practices

### Version Management
1. **Pin Versions**: Always use specific version tags, not 'latest'
2. **Test First**: Test upgrades in staging environment
3. **Document Changes**: Record version changes and any issues
4. **Monitor Dependencies**: Check for dependency updates

### Upgrade Scheduling
1. **Maintenance Windows**: Schedule upgrades during low-usage periods
2. **Staged Rollouts**: Consider staged rollouts for critical systems
3. **Communication**: Notify users of planned maintenance
4. **Rollback Planning**: Always have rollback procedures ready

### Quality Assurance
1. **Automated Testing**: Use automated tests to validate upgrades
2. **Manual Testing**: Perform manual testing of critical functionality
3. **Performance Testing**: Verify performance hasn't degraded
4. **Integration Testing**: Test all framework integrations

## Support and Maintenance

### Regular Maintenance
- **Monthly**: Review available updates
- **Quarterly**: Plan major version upgrades
- **Annually**: Review upgrade procedures and documentation

### Monitoring
- **Version Tracking**: Monitor framework versions and security updates
- **Performance Monitoring**: Track system performance after upgrades
- **Error Monitoring**: Monitor for upgrade-related issues

### Documentation Updates
- **Release Notes**: Keep upgrade procedures updated with new versions
- **Troubleshooting**: Update troubleshooting guides based on experience
- **Best Practices**: Refine best practices based on lessons learned

## Contributing

When adding new frameworks:
1. Create framework-specific upgrade directory
2. Follow the established procedure template
3. Include validation and rollback procedures
4. Update this documentation

## Emergency Contacts

For critical upgrade issues:
1. Check troubleshooting documentation
2. Review upgrade logs
3. Use rollback procedures if needed
4. Contact operations team for assistance
