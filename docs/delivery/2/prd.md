# PBI-2: Docker Compose Unification - Single Configuration Management

[View in Backlog](../backlog.md#user-content-2)

## Overview

Unify all services from fragmented Docker Compose configurations into a single, comprehensive docker-compose.yml file that enables one-command deployment and management of the entire PA ecosystem, ensuring proper service dependencies and health validation.

## Problem Statement

The current system has fragmented Docker deployments:
- Main docker-compose.yml with core services (Supabase, n8n, Letta, etc.)
- Separate gmail-mcp/docker-compose.yml for Gmail MCP server
- Standalone Slackbot application not containerized
- Services configured with external networking assumptions

This fragmentation creates:
- Complex deployment procedures requiring multiple commands
- Inconsistent service lifecycle management
- Difficult dependency management between services
- Complicated troubleshooting when services fail to interconnect

## User Stories

### Primary User Story
**As a DevOps Engineer**, I want all services unified in a single Docker Compose configuration so that I can deploy and manage the entire PA ecosystem with one command.

### Supporting User Stories
- **As a System Administrator**, I want single-command deployment so that system recovery and new installations are simplified
- **As a Developer**, I want consistent service discovery so that services can reliably find and communicate with each other
- **As a Home Server Owner**, I want simplified management so that I can maintain the system without deep Docker expertise

## Technical Approach

### Unified Service Architecture
```yaml
# Single docker-compose.yml containing all services
version: "3.9"

services:
  # --- Database Layer ---
  supabase-db:          # Unified PostgreSQL with all schemas
  
  # --- Core AI Services ---
  letta:                # AI agent framework
  
  # --- MCP Servers (Unified) ---
  gmail-mcp-server:     # Gmail integration (migrated from separate compose)
  slack-mcp-server:     # Slack integration  
  graphiti-mcp-server:  # Knowledge graph integration
  rag-mcp-server:       # RAG integration (future)
  
  # --- Application Services ---
  slackbot:             # Slack bot (newly containerized)
  n8n:                  # Workflow automation
  open-webui:           # AI interface
  
  # --- RAG Infrastructure ---
  hayhooks:             # Haystack REST API server
  
  # --- Infrastructure Services ---
  cloudflared:          # External access tunnel
  supabase-rest:        # Supabase REST API
  supabase-realtime:    # Supabase realtime
  supabase-storage:     # Supabase storage
  
  # --- Monitoring & Operations ---
  prometheus:           # Metrics collection
  grafana:              # Metrics visualization

networks:
  pa-network:
    name: pa-internal
    driver: bridge

volumes:
  supabase_db:
  n8n_data:
  open-webui:
  letta_data:
  cloudflared_data:
```

### Migration Strategy
1. **Service Inventory and Dependency Mapping**
   - Document all current services and their configurations
   - Map inter-service dependencies and communication patterns
   - Identify external networking requirements

2. **Gmail MCP Integration**
   - Migrate Gmail MCP server from gmail-mcp/docker-compose.yml
   - Update configuration for internal network communication
   - Preserve OAuth and credential management

3. **Slackbot Containerization**
   - Create Dockerfile for Slackbot application
   - Configure for internal Letta communication
   - Maintain all current Slack functionality

4. **Network Unification**
   - Create unified pa-internal network
   - Update all service configurations for internal communication
   - Remove external networking dependencies

5. **Health Check Implementation**
   - Add health checks for all services
   - Configure dependency ordering with depends_on
   - Implement startup validation procedures

### Configuration Management
- Environment-based configuration via .env files
- Service-specific configuration files mounted as volumes
- Secrets managed through Docker secrets or environment variables
- Template configurations for different deployment environments

## UX/UI Considerations

### Deployment Experience
- **Single Command**: `docker compose up -d` deploys entire ecosystem
- **Clear Status**: Health checks provide clear service status
- **Graceful Startup**: Services start in proper dependency order
- **Easy Troubleshooting**: Unified logging and status checking

### Administrative Interface
- Unified service management through Docker Compose commands
- Consistent log aggregation across all services
- Standardized health monitoring endpoints
- Clear documentation for common administrative tasks

## Acceptance Criteria

### Functional Requirements
- [ ] Single docker-compose.yml contains all services previously in separate configurations
- [ ] One-command deployment (`docker compose up`) successfully starts entire ecosystem
- [ ] All inter-service communication works via internal Docker network
- [ ] Gmail MCP server functionality preserved after migration
- [ ] Slackbot functionality preserved after containerization
- [ ] Service dependencies properly configured with health checks

### Non-Functional Requirements
- [ ] Complete system startup within 5 minutes from cold start
- [ ] Service startup order respects dependencies (database → core services → applications)
- [ ] Health checks validate service readiness before marking as healthy
- [ ] Configuration supports different environments (development, production)
- [ ] Resource usage optimized compared to current fragmented approach

### Operational Requirements
- [ ] Migration from current setup can be performed with minimal downtime
- [ ] Rollback procedures documented and tested
- [ ] Service logs accessible via standard Docker logging
- [ ] Monitoring endpoints exposed for all services
- [ ] Documentation updated for new deployment procedures

## Dependencies

### Technical Dependencies
- Docker Engine 20.10+ with Compose v2
- Unified PostgreSQL database (PBI-1)
- Network infrastructure configuration
- Service configuration templates and environment files

### Process Dependencies
- **Upstream**: 
  - PBI-1 (Database Consolidation) - required for unified database configuration
- **Downstream**:
  - PBI-3 (Network Unification) - builds on Docker Compose foundation  
  - PBI-4 (MCP Standardization) - depends on unified service deployment
  - PBI-5 (Slackbot Integration) - requires containerization foundation

### Migration Dependencies
- Access to current gmail-mcp configuration and credentials
- Slackbot application code and dependencies
- Current service configuration backup
- Testing environment for validation

## Open Questions

1. **Service Scaling**: Should the unified compose support service scaling for future load requirements?
2. **Environment Separation**: How should development vs production configurations be managed?
3. **Secret Management**: Should we implement Docker secrets or continue with environment variables?
4. **Backup Integration**: Should backup procedures be integrated into the compose configuration?
5. **Monitoring Integration**: What level of monitoring should be built into the base compose file?

## Related Tasks

Tasks for this PBI will be defined in [tasks.md](./tasks.md) following the implementation approach:

1. **Service Inventory and Dependency Analysis**
2. **Gmail MCP Migration Planning**
3. **Slackbot Containerization**
4. **Unified Docker Compose Creation**
5. **Network Configuration Implementation**
6. **Health Check Implementation**
7. **Migration Testing and Validation**
8. **Documentation and Deployment Guide**

---

**Back to**: [Project Backlog](../backlog.md)
