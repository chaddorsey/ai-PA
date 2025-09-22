# Version Compatibility Management

This directory contains comprehensive documentation and tools for managing version compatibility across the PA Ecosystem frameworks.

## Overview

The version compatibility system ensures that all framework versions work together correctly, providing automated testing, validation, and reporting capabilities.

## Quick Start

### 1. Run All Compatibility Tests
```bash
# Run comprehensive compatibility testing
./scripts/compatibility/run-all-compatibility-tests.sh --generate-report

# Test specific framework
./scripts/compatibility/run-all-compatibility-tests.sh --framework n8n --generate-report
```

### 2. Validate Version Compatibility
```bash
# Validate all framework compatibility
./scripts/compatibility/validate-compatibility.sh --check-all

# Validate specific framework
./scripts/compatibility/validate-compatibility.sh --framework n8n --target-version 1.110.0
```

### 3. Test Individual Components
```bash
# API compatibility testing
./scripts/compatibility/api-compatibility-test.sh

# Database compatibility testing
./scripts/compatibility/database-compatibility-test.sh

# Integration compatibility testing
./scripts/compatibility/integration-compatibility-test.sh
```

## Compatibility Matrix

The compatibility matrix (`config/compatibility/compatibility-matrix.yml`) defines which versions of frameworks are compatible with each other.

### Matrix Structure

```yaml
compatibility_matrix:
  n8n:
    "1.109.2":
      letta:
        "0.11.7": "compatible"
        "0.12.0": "compatible"
      graphiti:
        "0.18.9": "compatible"
        "0.19.0": "compatible"
```

### Compatibility Status Values

- **compatible**: Tested and verified to work together
- **incompatible**: Known to have issues or conflicts
- **unknown**: Not yet tested - proceed with caution
- **deprecated**: Version is deprecated and should be upgraded
- **experimental**: Experimental support - use with caution

## Testing Framework

### Test Categories

#### 1. Version Compatibility Validation
- **Purpose**: Validate framework version compatibility against the matrix
- **Script**: `validate-compatibility.sh`
- **Tests**: Framework version checking, infrastructure compatibility

#### 2. API Compatibility Testing
- **Purpose**: Test API endpoints and response formats
- **Script**: `api-compatibility-test.sh`
- **Tests**: Health endpoints, API responses, cross-service connectivity

#### 3. Database Compatibility Testing
- **Purpose**: Test database schemas and connectivity
- **Script**: `database-compatibility-test.sh`
- **Tests**: PostgreSQL, Neo4j, schema compatibility, performance

#### 4. Integration Compatibility Testing
- **Purpose**: Test cross-service integrations
- **Script**: `integration-compatibility-test.sh`
- **Tests**: MCP servers, webhooks, event handling, data flow

### Test Execution

#### Individual Tests
```bash
# Run specific test category
./scripts/compatibility/api-compatibility-test.sh --framework n8n
./scripts/compatibility/database-compatibility-test.sh --database postgresql
./scripts/compatibility/integration-compatibility-test.sh --integration mcp
```

#### Comprehensive Testing
```bash
# Run all tests with reporting
./scripts/compatibility/run-all-compatibility-tests.sh --generate-report

# Test specific framework comprehensively
./scripts/compatibility/run-all-compatibility-tests.sh --framework letta --generate-report
```

## Framework-Specific Compatibility

### n8n (Workflow Automation)

**Current Version**: 1.109.2  
**Compatibility Focus**: API endpoints, webhook integration, database schemas

#### Key Compatibility Points
- **API Version**: v1 (stable)
- **Database**: PostgreSQL 15.x
- **Webhooks**: HTTP endpoint compatibility
- **Integrations**: Letta, Graphiti MCP servers

#### Testing Commands
```bash
# Test n8n compatibility
./scripts/compatibility/validate-compatibility.sh --framework n8n --target-version 1.110.0
./scripts/compatibility/api-compatibility-test.sh --framework n8n
```

### Letta (AI Agent Framework)

**Current Version**: 0.11.7  
**Compatibility Focus**: API responses, agent functionality, MCP integration

#### Key Compatibility Points
- **API Version**: v1 (stable)
- **Database**: PostgreSQL 15.x
- **MCP Integration**: Server connectivity and protocols
- **Agent State**: Persistence across upgrades

#### Testing Commands
```bash
# Test Letta compatibility
./scripts/compatibility/validate-compatibility.sh --framework letta --target-version 0.12.0
./scripts/compatibility/api-compatibility-test.sh --framework letta
```

### Graphiti (Knowledge Graph Framework)

**Current Version**: 0.18.9  
**Compatibility Focus**: Neo4j connectivity, MCP server functionality, source code compatibility

#### Key Compatibility Points
- **Database**: Neo4j 5.x
- **Python**: 3.11+
- **MCP Server**: HTTP endpoint compatibility
- **Source Code**: pyproject.toml dependencies

#### Testing Commands
```bash
# Test Graphiti compatibility
./scripts/compatibility/validate-compatibility.sh --framework graphiti --target-version 0.19.0
./scripts/compatibility/api-compatibility-test.sh --framework graphiti
```

## Infrastructure Compatibility

### Database Systems

#### PostgreSQL (Supabase)
- **Version**: 15.8.1.060
- **Compatibility**: n8n, Letta
- **Testing**: Schema compatibility, data integrity, performance

#### Neo4j
- **Version**: 5.26
- **Compatibility**: Graphiti
- **Testing**: Graph operations, APOC procedures, performance

### Container Runtime
- **Docker**: 24.0.0+
- **Compatibility**: All frameworks
- **Testing**: Container networking, volume mounts, resource limits

## Compatibility Workflow

### Before Upgrades

1. **Validate Compatibility**
   ```bash
   ./scripts/compatibility/validate-compatibility.sh --framework <framework> --target-version <version>
   ```

2. **Run Comprehensive Tests**
   ```bash
   ./scripts/compatibility/run-all-compatibility-tests.sh --framework <framework> --generate-report
   ```

3. **Review Test Results**
   - Check for any failed tests
   - Review compatibility matrix
   - Plan upgrade strategy

### During Upgrades

1. **Monitor Compatibility**
   - Watch for compatibility warnings
   - Test critical integrations
   - Validate API responses

2. **Handle Issues**
   - Use rollback procedures if needed
   - Update compatibility matrix
   - Document any issues

### After Upgrades

1. **Validate Post-Upgrade**
   ```bash
   ./scripts/compatibility/run-all-compatibility-tests.sh --generate-report
   ```

2. **Update Documentation**
   - Update compatibility matrix
   - Record test results
   - Update upgrade procedures

## Reporting and Monitoring

### Compatibility Reports

Reports are generated in `/var/reports/compatibility/` and include:

- **Executive Summary**: Overall compatibility status
- **Detailed Results**: Individual test results and durations
- **Recommendations**: Action items based on test results
- **Next Steps**: Follow-up actions and maintenance

### Log Files

All test logs are stored in `/var/log/compatibility/` with timestamps:

- `comprehensive-test-YYYYMMDD-HHMMSS.log`
- `validation-YYYYMMDD-HHMMSS.log`
- `api-test-YYYYMMDD-HHMMSS.log`
- `database-test-YYYYMMDD-HHMMSS.log`
- `integration-test-YYYYMMDD-HHMMSS.log`

### Monitoring Integration

The compatibility system integrates with:

- **Health Monitoring**: Regular compatibility checks
- **Upgrade Procedures**: Pre-upgrade validation
- **Alerting**: Compatibility failure notifications

## Best Practices

### Regular Testing
- **Daily**: Automated compatibility checks
- **Weekly**: Comprehensive compatibility testing
- **Before Upgrades**: Full compatibility validation
- **After Upgrades**: Post-upgrade compatibility verification

### Matrix Maintenance
- **Update Regularly**: Keep compatibility matrix current
- **Document Changes**: Record all compatibility updates
- **Version Tracking**: Track compatibility across versions
- **Testing Validation**: Verify matrix accuracy with testing

### Issue Resolution
- **Document Issues**: Record all compatibility problems
- **Root Cause Analysis**: Understand compatibility failures
- **Solution Development**: Create fixes for compatibility issues
- **Prevention**: Update procedures to prevent future issues

## Troubleshooting

### Common Issues

#### Compatibility Matrix Out of Date
```bash
# Update compatibility matrix
./scripts/compatibility/validate-compatibility.sh --check-all
# Review and update config/compatibility/compatibility-matrix.yml
```

#### Test Failures
```bash
# Check individual test logs
tail -f /var/log/compatibility/*.log

# Re-run specific tests
./scripts/compatibility/api-compatibility-test.sh --framework <framework>
```

#### Network Connectivity Issues
```bash
# Test network connectivity
docker network ls
docker exec <container> ping <target>

# Check service discovery
./scripts/compatibility/integration-compatibility-test.sh --integration data-flow
```

### Emergency Procedures

#### Quick Compatibility Check
```bash
# Fast compatibility validation
./scripts/compatibility/validate-compatibility.sh --check-all
```

#### Emergency Testing
```bash
# Minimal compatibility testing
./scripts/compatibility/api-compatibility-test.sh
./scripts/compatibility/database-compatibility-test.sh
```

## Contributing

### Adding New Tests
1. Create test script in `scripts/compatibility/`
2. Follow existing test patterns and structure
3. Add test to `run-all-compatibility-tests.sh`
4. Update documentation

### Updating Compatibility Matrix
1. Test new version combinations
2. Update `config/compatibility/compatibility-matrix.yml`
3. Validate matrix accuracy
4. Document changes

### Improving Test Coverage
1. Identify gaps in test coverage
2. Develop new test scenarios
3. Integrate with existing test framework
4. Update documentation

## Support

For compatibility issues:
1. Check troubleshooting documentation
2. Review test logs and reports
3. Consult compatibility matrix
4. Contact operations team for assistance

## Related Documentation

- [Upgrade Procedures](../upgrades/README.md)
- [Version Management](../version-management/README.md)
- [Health Monitoring](../../monitoring/README.md)
- [Troubleshooting Guide](../../troubleshooting-guide.md)
