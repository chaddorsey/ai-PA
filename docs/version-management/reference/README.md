# Version Management Reference

This directory contains quick reference materials, cheat sheets, and lookup tables for version management operations in the PA Ecosystem.

## Table of Contents

1. [Quick Reference](#quick-reference)
2. [Command Cheat Sheets](#command-cheat-sheets)
3. [Version Information](#version-information)
4. [Configuration Reference](#configuration-reference)
5. [API Reference](#api-reference)
6. [Troubleshooting Quick Reference](#troubleshooting-quick-reference)

## Quick Reference

### Essential Commands

#### Version Management
```bash
# Check current versions
./scripts/version-management/detect-versions.sh

# Validate version compliance
./scripts/version-management/validate-versions.sh

# Update version lock file
./scripts/version-management/update-versions.sh
```

#### Upgrade Operations
```bash
# Pre-upgrade validation
./scripts/upgrades/validation/pre-upgrade-check.sh

# Upgrade specific framework
./scripts/upgrades/<framework>/upgrade-<framework>.sh --version <version>

# Multi-framework upgrade
./scripts/upgrades/coordination/upgrade-all.sh --frameworks "n8n,letta,graphiti"
```

#### Rollback Operations
```bash
# Emergency rollback
./scripts/rollback/emergency-rollback.sh --framework <framework> --target-version <version>

# Multi-framework rollback
./scripts/rollback/coordination/rollback-all.sh --frameworks "n8n,letta,graphiti"
```

#### Compatibility Testing
```bash
# Run all compatibility tests
./scripts/compatibility/run-all-compatibility-tests.sh --generate-report

# Test specific framework
./scripts/compatibility/validate-compatibility.sh --framework <framework>
```

### Service Endpoints

#### Health Check Endpoints
```bash
# n8n health
curl http://localhost:5678/health

# Letta health
curl http://localhost:8283/v1/health/

# Graphiti health
curl http://localhost:8082/health
```

#### API Endpoints
```bash
# n8n workflows
curl http://localhost:5678/rest/workflows

# Letta agents
curl http://localhost:8283/v1/agents

# Graphiti MCP
curl http://localhost:8082/mcp
```

## Command Cheat Sheets

### Version Management Commands

#### Version Detection
```bash
# Detect all versions
./scripts/version-management/detect-versions.sh

# Detect specific service
./scripts/version-management/detect-versions.sh --service <service-name>

# Update detected versions
./scripts/version-management/detect-versions.sh --update-lock
```

#### Version Validation
```bash
# Validate all versions
./scripts/version-management/validate-versions.sh

# Validate specific service
./scripts/version-management/validate-versions.sh --service <service-name>

# Generate compliance report
./scripts/version-management/validate-versions.sh --generate-report
```

### Upgrade Commands

#### n8n Upgrade
```bash
# Upgrade n8n
./scripts/upgrades/n8n/upgrade-n8n.sh --version 1.110.0

# Dry run upgrade
./scripts/upgrades/n8n/upgrade-n8n.sh --version 1.110.0 --dry-run

# Force upgrade
./scripts/upgrades/n8n/upgrade-n8n.sh --version 1.110.0 --force
```

#### Letta Upgrade
```bash
# Upgrade Letta
./scripts/upgrades/letta/upgrade-letta.sh --version 0.12.0

# Dry run upgrade
./scripts/upgrades/letta/upgrade-letta.sh --version 0.12.0 --dry-run

# Force upgrade
./scripts/upgrades/letta/upgrade-letta.sh --version 0.12.0 --force
```

#### Graphiti Upgrade
```bash
# Upgrade Graphiti
./scripts/upgrades/graphiti/upgrade-graphiti.sh --version 0.19.0

# Dry run upgrade
./scripts/upgrades/graphiti/upgrade-graphiti.sh --version 0.19.0 --dry-run

# Force upgrade
./scripts/upgrades/graphiti/upgrade-graphiti.sh --version 0.19.0 --force
```

### Rollback Commands

#### Framework Rollbacks
```bash
# n8n rollback
./scripts/rollback/n8n/rollback-n8n.sh --backup-path <path>

# Letta rollback
./scripts/rollback/letta/rollback-letta.sh --backup-path <path>

# Graphiti rollback
./scripts/rollback/graphiti/rollback-graphiti.sh --backup-path <path>
```

#### Emergency Rollbacks
```bash
# Quick emergency rollback
./scripts/rollback/emergency-rollback.sh --framework <framework> --target-version <version>

# Emergency rollback with backup
./scripts/rollback/emergency-rollback.sh --framework <framework> --backup-path <path>
```

### Compatibility Commands

#### Compatibility Testing
```bash
# Test all compatibility
./scripts/compatibility/run-all-compatibility-tests.sh

# Test specific framework
./scripts/compatibility/validate-compatibility.sh --framework <framework>

# Test API compatibility
./scripts/compatibility/api-compatibility-test.sh --framework <framework>

# Test database compatibility
./scripts/compatibility/database-compatibility-test.sh --framework <framework>
```

## Version Information

### Current Versions

#### Core Frameworks
| Framework | Current Version | Upgrade Path | Last Updated |
|-----------|----------------|--------------|--------------|
| n8n | 1.109.2 | Minor | 2025-01-21 |
| Letta | 0.11.7 | Minor | 2025-01-21 |
| Graphiti | 0.18.9 | Patch | 2025-01-21 |

#### Infrastructure Services
| Service | Current Version | Upgrade Path | Last Updated |
|---------|----------------|--------------|--------------|
| PostgreSQL | 15.8.1.060 | Major | 2025-01-21 |
| Neo4j | 5.26 | Major | 2025-01-21 |
| Docker | 24.0.7 | Minor | 2025-01-21 |

#### MCP Servers
| Server | Current Version | Upgrade Path | Last Updated |
|--------|----------------|--------------|--------------|
| Gmail MCP | 1.1.11 | Minor | 2025-01-21 |
| RAG MCP | 1.0.0 | Minor | 2025-01-21 |
| Health Monitor | 1.0.0 | Minor | 2025-01-21 |

### Version Compatibility Matrix

#### n8n Compatibility
| n8n Version | PostgreSQL | Neo4j | Docker | Status |
|-------------|------------|-------|--------|--------|
| 1.109.2 | 15.8.x | 5.26 | 24.0.x | Compatible |
| 1.110.0 | 15.8.x | 5.26 | 24.0.x | Compatible |
| 1.111.0 | 15.8.x | 5.26 | 24.0.x | Unknown |

#### Letta Compatibility
| Letta Version | PostgreSQL | Neo4j | Docker | Status |
|---------------|------------|-------|--------|--------|
| 0.11.7 | 15.8.x | 5.26 | 24.0.x | Compatible |
| 0.12.0 | 15.8.x | 5.26 | 24.0.x | Unknown |
| 0.13.0 | 15.8.x | 5.26 | 24.0.x | Unknown |

#### Graphiti Compatibility
| Graphiti Version | PostgreSQL | Neo4j | Docker | Status |
|------------------|------------|-------|--------|--------|
| 0.18.9 | 15.8.x | 5.26 | 24.0.x | Compatible |
| 0.19.0 | 15.8.x | 5.26 | 24.0.x | Unknown |
| 0.20.0 | 15.8.x | 5.26 | 24.0.x | Unknown |

## Configuration Reference

### Version Lock File Structure

#### Basic Structure
```yaml
services:
  <service-name>:
    image: "<image-name>"
    tag: "<tag>"
    version: "<version>"
    locked: true/false
    upgrade_path: "<path>"
    notes: "<notes>"

metadata:
  total_services: <count>
  locked_services: <count>
  unlocked_services: <count>
  critical_services_unlocked: <count>
  last_updated: "<timestamp>"
```

#### Service Configuration
```yaml
n8n:
  image: "docker.n8n.io/n8nio/n8n"
  tag: "1.109.2"
  version: "1.109.2"
  locked: true
  upgrade_path: "minor"
  notes: "Current stable version"
```

### Compatibility Matrix Structure

#### Basic Structure
```yaml
frameworks:
  <framework-name>:
    versions:
      <version>:
        compatibility_status: "<status>"
        tested_combinations: []
        known_issues: []
        upgrade_recommendations: []

infrastructure:
  <infrastructure-name>:
    versions:
      <version>:
        compatibility_status: "<status>"
        supported_frameworks: []
        upgrade_path: "<path>"
```

#### Framework Configuration
```yaml
frameworks:
  n8n:
    versions:
      "1.109.2":
        compatibility_status: "compatible"
        tested_combinations: ["postgresql:15.8.x", "neo4j:5.26"]
        known_issues: []
        upgrade_recommendations: ["minor"]
```

## API Reference

### Version Management APIs

#### Version Detection API
```bash
# Detect all versions
GET /api/versions/detect

# Detect specific service
GET /api/versions/detect?service=<service-name>

# Update version lock
POST /api/versions/update-lock
```

#### Upgrade API
```bash
# Start upgrade
POST /api/upgrades/start
{
  "framework": "<framework-name>",
  "target_version": "<version>",
  "dry_run": false
}

# Check upgrade status
GET /api/upgrades/status/<upgrade-id>

# Cancel upgrade
POST /api/upgrades/cancel/<upgrade-id>
```

#### Rollback API
```bash
# Start rollback
POST /api/rollback/start
{
  "framework": "<framework-name>",
  "target_version": "<version>",
  "backup_path": "<path>"
}

# Check rollback status
GET /api/rollback/status/<rollback-id>
```

### Service Health APIs

#### Health Check Endpoints
```bash
# n8n health
GET http://localhost:5678/health
Response: {"status": "healthy", "version": "1.109.2"}

# Letta health
GET http://localhost:8283/v1/health/
Response: {"status": "healthy", "version": "0.11.7", "database": "healthy"}

# Graphiti health
GET http://localhost:8082/health
Response: {"status": "healthy", "version": "0.18.9"}
```

#### Service Information APIs
```bash
# n8n workflows
GET http://localhost:5678/rest/workflows
Response: [{"id": "1", "name": "workflow1", ...}]

# Letta agents
GET http://localhost:8283/v1/agents
Response: [{"id": "1", "name": "agent1", ...}]

# Graphiti MCP
GET http://localhost:8082/mcp
Response: {"status": "active", "endpoints": [...]}
```

## Troubleshooting Quick Reference

### Common Issues and Solutions

#### Version Detection Issues
| Issue | Solution |
|-------|----------|
| Container not running | `docker compose up -d <service>` |
| Version command failed | Check container health |
| Network issues | Check Docker networking |

#### Upgrade Issues
| Issue | Solution |
|-------|----------|
| Upgrade script fails | Check logs, fix prerequisites |
| Service won't start | Check configuration, rollback |
| Database migration fails | Fix connectivity, rollback DB |

#### Rollback Issues
| Issue | Solution |
|-------|----------|
| Backup not found | Create emergency backup |
| Rollback script fails | Manual rollback, emergency procedures |
| Data corruption | Data recovery, service recovery |

### Emergency Commands

#### Quick Emergency Response
```bash
# Emergency rollback
./scripts/rollback/emergency-rollback.sh --framework <framework> --target-version <version>

# System health check
./scripts/health-check-all.sh

# Service restart
docker compose restart <service>

# Container logs
docker logs <container-name>
```

#### Diagnostic Commands
```bash
# Check system resources
htop
df -h
free -h

# Check Docker status
docker ps
docker stats
docker network ls

# Check service endpoints
curl <endpoint>
telnet <host> <port>
```

### Log Locations

#### System Logs
| Service | Log Location |
|---------|--------------|
| n8n | `/var/log/n8n/` |
| Letta | `/var/log/letta/` |
| Graphiti | `/var/log/graphiti/` |
| System | `/var/log/` |

#### Version Management Logs
| Operation | Log Location |
|-----------|--------------|
| Upgrades | `/var/log/upgrades/` |
| Rollbacks | `/var/log/rollback/` |
| Compatibility | `/var/log/compatibility/` |
| Version Management | `/var/log/version-management/` |

### Contact Information

#### Internal Support
| Team | Contact | Response Time |
|------|---------|---------------|
| Operations | operations@company.com | 1 hour |
| Development | dev@company.com | 4 hours |
| Architecture | arch@company.com | 8 hours |

#### Emergency Contacts
| Level | Contact | Response Time |
|-------|---------|---------------|
| Critical | +1-XXX-XXX-XXXX | Immediate |
| High | operations@company.com | 1 hour |
| Medium | dev@company.com | 4 hours |

## Best Practices Quick Reference

### Upgrade Best Practices
1. **Always backup before upgrades**
2. **Test upgrades in staging first**
3. **Follow upgrade procedures exactly**
4. **Validate each step before proceeding**
5. **Monitor system health during upgrades**

### Rollback Best Practices
1. **Have rollback procedures ready**
2. **Test rollback procedures regularly**
3. **Keep backups current and validated**
4. **Document rollback decisions**
5. **Monitor system after rollback**

### Compatibility Best Practices
1. **Check compatibility matrix before upgrades**
2. **Test compatibility in staging**
3. **Update compatibility matrix regularly**
4. **Document known issues**
5. **Plan for compatibility breaks**

## Conclusion

This reference guide provides quick access to:
- **Essential Commands**: Most commonly used version management commands
- **Version Information**: Current versions and compatibility matrix
- **Configuration Reference**: File structures and examples
- **API Reference**: Service endpoints and APIs
- **Troubleshooting**: Quick solutions for common issues

Keep this reference handy for quick lookups during version management operations.
