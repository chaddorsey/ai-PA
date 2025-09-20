# PBI-11: Framework Version Management - Controlled Upgrade Paths

[View in Backlog](../backlog.md#user-content-11)

## Overview

Implement framework version management with controlled upgrade paths for n8n, Letta, and Graphiti so that the system can safely update to newer versions while maintaining cutting-edge features and system reliability through proper version pinning, compatibility testing, and rollback procedures.

## Problem Statement

The current system lacks systematic version management for critical frameworks:
- No version pinning for n8n, Letta, or Graphiti containers
- Manual upgrade processes without safety validation
- No compatibility testing between framework versions
- Risk of breaking changes disrupting production workflows
- Difficult rollback when upgrades cause issues

This creates operational risks:
- Unexpected breaking changes from automatic updates
- Complex manual upgrade procedures prone to errors
- No systematic way to test framework compatibility
- Potential data loss or corruption during failed upgrades
- Extended downtime during troubleshooting upgrade issues

## User Stories

### Primary User Story
**As a System Administrator**, I want framework version management with controlled upgrade paths so that I can safely update n8n, Letta, and Graphiti while maintaining cutting-edge features and system reliability.

### Supporting User Stories
- **As a DevOps Engineer**, I want version lock files so that deployments are reproducible and predictable
- **As a Product Owner**, I want controlled access to new features so that I can evaluate benefits while managing risks
- **As a User**, I want system stability so that upgrades don't disrupt my workflows
- **As an Operations Engineer**, I want quick rollback capability so that failed upgrades can be reverted rapidly

## Technical Approach

### Version Lock Framework
```yaml
# config/versions.yml - Central version management
frameworks:
  n8n:
    current_version: "1.109.2"
    latest_available: "1.111.0"
    upgrade_status: "ready"
    last_tested: "2025-09-19"
    breaking_changes: false
    
  letta:
    current_version: "0.4.0"
    latest_available: "0.4.1"
    upgrade_status: "pending_review"
    last_tested: null
    breaking_changes: unknown
    
  graphiti:
    current_version: "0.3.1"
    latest_available: "0.3.2"
    upgrade_status: "not_ready"
    last_tested: null
    breaking_changes: true
    
upgrade_policies:
  auto_minor_updates: false
  auto_patch_updates: false
  require_manual_approval: true
  testing_required: true
```

### Docker Compose Integration
```yaml
# Version-pinned services with upgrade support
services:
  n8n:
    image: docker.n8n.io/n8nio/n8n:${N8N_VERSION:-1.109.2}
    environment:
      - N8N_UPGRADE_VALIDATION=true
    volumes:
      - ./config/versions.lock:/app/versions.lock:ro
      
  letta:
    image: letta/letta:${LETTA_VERSION:-0.4.0}
    environment:
      - LETTA_VERSION_CHECK=enabled
      
  graphiti:
    build:
      context: ./graphiti
      target: ${GRAPHITI_VERSION:-v0.3.1}
    environment:
      - GRAPHITI_VERSION_VALIDATION=true
```

### Upgrade Workflow Process

#### 1. Version Discovery and Analysis
```bash
# Automated version checking
./scripts/check-framework-versions.sh
```
- Check for new releases of n8n, Letta, Graphiti
- Parse release notes for breaking changes
- Assess compatibility with current configuration
- Generate upgrade recommendations

#### 2. Pre-Upgrade Validation
```bash
# Pre-upgrade compatibility check
./scripts/pre-upgrade-check.sh n8n 1.111.0
```
- Validate configuration compatibility
- Check database schema requirements
- Analyze custom workflows and integrations
- Generate compatibility report

#### 3. Staged Upgrade Testing
```bash
# Deploy to staging environment
UPGRADE_STAGING=true docker compose up n8n
```
- Deploy new version in isolated staging environment
- Run automated workflow validation tests
- Perform database migration testing
- Validate API compatibility

#### 4. Production Upgrade Execution
```bash
# Controlled production upgrade
./scripts/upgrade-framework.sh n8n 1.111.0
```
- Create automatic backup before upgrade
- Execute version update with monitoring
- Validate post-upgrade functionality
- Update version lock file

#### 5. Rollback Capability
```bash
# Quick rollback if issues detected
./scripts/rollback-framework.sh n8n 1.109.2
```
- Restore previous container version
- Restore database from pre-upgrade backup
- Validate system functionality
- Update version tracking

### Version Compatibility Matrix
```yaml
# Framework interdependency tracking
compatibility:
  n8n_1.111.0:
    postgres: ">=15.0"
    node: ">=18.0"
    letta_integration: "0.4.0+"
    breaking_changes:
      - "Workflow API v1 deprecated"
      - "New authentication requirements"
      
  letta_0.4.1:
    postgres: ">=15.0" 
    pgvector: ">=0.5.0"
    python: ">=3.11"
    openai: ">=1.0.0"
    breaking_changes:
      - "MCP protocol updated to v0.3"
      - "Agent memory format changed"
```

### Automated Testing Integration
- **Workflow Validation**: Automated testing of critical n8n workflows
- **Agent Functionality**: Validation of Letta agent capabilities
- **MCP Integration**: Testing of all MCP server communications
- **Database Migration**: Automated schema migration testing
- **Performance Benchmarking**: Pre/post upgrade performance comparison

## UX/UI Considerations

### Administrative Interface
- **Version Dashboard**: Clear overview of current vs available versions
- **Upgrade Status**: Visual indication of upgrade readiness and risks
- **Release Notes**: Integrated access to framework release notes and change logs
- **Testing Results**: Clear reporting of upgrade validation test results

### Upgrade Experience
- **Risk Assessment**: Clear communication of upgrade risks and benefits
- **Progress Tracking**: Real-time progress updates during upgrade process
- **Rollback Options**: Easy access to rollback procedures if needed
- **Minimal Downtime**: Optimized procedures to minimize service disruption

## Acceptance Criteria

### Functional Requirements
- [ ] Version lock file maintains current working versions for all frameworks
- [ ] Upgrade procedures documented and tested for n8n, Letta, and Graphiti
- [ ] Version compatibility matrix maintained and validated
- [ ] Rollback procedures tested and documented with <5 minute recovery time
- [ ] Automated version checking identifies new releases within 24 hours
- [ ] Pre-upgrade validation detects configuration compatibility issues

### Non-Functional Requirements
- [ ] Upgrade process completes within 15 minutes for typical version updates
- [ ] Rollback procedures restore service within 5 minutes
- [ ] Version checking and validation scripts execute within 2 minutes
- [ ] Framework documentation accessible and integrated with upgrade workflows
- [ ] Upgrade automation reduces manual intervention by 80%

### Operational Requirements
- [ ] All upgrades require explicit manual approval
- [ ] Comprehensive backups created before any version changes
- [ ] Upgrade audit trail maintained with timestamps and user attribution
- [ ] Post-upgrade validation confirms all services operational
- [ ] Configuration templates updated for new versions as needed

## Dependencies

### Technical Dependencies
- Docker Engine with support for version pinning
- Backup infrastructure for pre-upgrade data protection
- Testing environment for upgrade validation
- Network access for downloading new framework versions
- Administrative access for framework configuration updates

### Process Dependencies
- **Upstream**:
  - PBI-1 (Database Consolidation) - required for unified backup procedures
  - PBI-2 (Docker Compose Unification) - required for version management integration
- **Downstream**:
  - PBI-12 (Upgrade Infrastructure) - builds on version management foundation
- **Parallel**:
  - Framework-specific upgrade testing requires operational system

### External Dependencies
- Framework release schedules and documentation (n8n, Letta, Graphiti)
- Docker registry access for pulling new images
- GitHub/GitLab access for release notes and source code
- Framework community resources and support channels

## Open Questions

1. **Auto-Updates**: Should patch-level updates be automatically applied or require manual approval?
2. **Testing Scope**: What level of automated testing is sufficient for upgrade validation?
3. **Rollback Window**: How long should previous versions be maintained for rollback capability?
4. **Beta Testing**: Should pre-release versions be tested in staging environments?
5. **Integration Testing**: How should cross-framework compatibility be validated?
6. **Security Updates**: Should security-related updates follow expedited approval processes?

## Related Tasks

Tasks for this PBI will be defined in [tasks.md](./tasks.md) following the implementation approach:

1. **Version Management Framework Design**
2. **Version Lock File Implementation**
3. **Automated Version Discovery**
4. **Pre-Upgrade Validation Scripts**
5. **Upgrade Workflow Implementation**
6. **Rollback Procedure Development**
7. **Testing and Validation Framework**
8. **Documentation and Operational Procedures**

---

**Back to**: [Project Backlog](../backlog.md)
