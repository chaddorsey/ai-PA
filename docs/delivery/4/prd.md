# PBI-4: MCP Server Standardization - Unified Integration

[View in Backlog](../backlog.md#user-content-4)

## Overview

Standardize all Model Context Protocol (MCP) servers and integrate them into the main Docker Compose configuration so that Letta can access all capabilities through a consistent interface, ensuring reliable service discovery and uniform configuration patterns across all MCP implementations.

## Problem Statement

The current MCP server deployment is fragmented and inconsistent:
- Gmail MCP server deployed in separate docker-compose.yml
- Graphiti MCP server configuration unclear
- No standardized configuration patterns across MCP servers
- Letta MCP client configuration potentially incomplete
- Inconsistent health checking and service discovery

This fragmentation creates:
- Complex configuration management across multiple locations
- Unreliable service discovery when services restart
- Inconsistent error handling and logging patterns
- Difficult troubleshooting when MCP integrations fail
- Risk of configuration drift between MCP servers

## User Stories

### Primary User Story
**As an Integration Engineer**, I want all MCP servers standardized and integrated into the main Docker Compose so that Letta can access all capabilities through a consistent interface.

### Supporting User Stories
- **As a System Administrator**, I want standardized MCP configuration so that I can manage all servers consistently
- **As a Letta User**, I want reliable tool access so that all agent capabilities are consistently available
- **As a Developer**, I want uniform MCP patterns so that adding new MCP servers follows established conventions
- **As a DevOps Engineer**, I want centralized MCP management so that service lifecycle is predictable

## Technical Approach

### Unified MCP Architecture
```yaml
# All MCP servers in main docker-compose.yml
services:
  # --- MCP Servers (Standardized) ---
  gmail-mcp-server:
    build: ./mcp-servers/gmail
    container_name: gmail-mcp
    environment:
      - MCP_SERVER_NAME=gmail-tools
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
    volumes:
      - ./mcp-servers/gmail/config:/app/config
      - ./data/google_tokens:/app/tokens
    networks: [pa-network]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      
  graphiti-mcp-server:
    build: ./mcp-servers/graphiti
    container_name: graphiti-mcp
    environment:
      - MCP_SERVER_NAME=graphiti-tools
      - NEO4J_URI=bolt://neo4j:7687
      - NEO4J_USER=${NEO4J_USER}
      - NEO4J_PASSWORD=${NEO4J_PASSWORD}
    networks: [pa-network]
    depends_on: [neo4j]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8081/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      
  rag-mcp-server:
    build: ./mcp-servers/rag
    container_name: rag-mcp
    environment:
      - MCP_SERVER_NAME=rag-tools
      - HAYHOOKS_URL=http://hayhooks:1416
    networks: [pa-network]
    depends_on: [hayhooks]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8082/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Standardized Configuration Patterns

#### 1. Common Environment Variables
```bash
# Standard across all MCP servers
MCP_SERVER_NAME=<server-name>        # Unique identifier
MCP_SERVER_PORT=<port>               # Standard port assignment
MCP_LOG_LEVEL=INFO                   # Consistent logging
MCP_HEALTH_CHECK_PATH=/health        # Standard health endpoint
```

#### 2. Directory Structure
```
mcp-servers/
├── gmail/
│   ├── Dockerfile
│   ├── src/
│   ├── config/
│   └── requirements.txt
├── graphiti/
│   ├── Dockerfile
│   ├── src/
│   ├── config/
│   └── requirements.txt
└── rag/
    ├── Dockerfile
    ├── src/
    ├── config/
    └── requirements.txt
```

#### 3. Letta MCP Configuration
```json
{
  "mcpServers": {
    "gmail-tools": {
      "command": "http",
      "args": ["http://gmail-mcp-server:8080"],
      "env": {},
      "disabled": false
    },
    "graphiti-tools": {
      "command": "http", 
      "args": ["http://graphiti-mcp-server:8081"],
      "env": {},
      "disabled": false
    },
    "rag-tools": {
      "command": "http",
      "args": ["http://rag-mcp-server:8082"], 
      "env": {},
      "disabled": false
    }
  }
}
```

### Migration Strategy

#### 1. Gmail MCP Server Migration
- Move Gmail MCP from gmail-mcp/docker-compose.yml to main compose
- Standardize configuration patterns and environment variables
- Update OAuth token management for containerized environment
- Preserve all existing Gmail functionality and credentials

#### 2. Graphiti MCP Integration
- Ensure Graphiti MCP server is properly configured in main compose
- Standardize Neo4j connection and authentication
- Implement health checks and dependency management
- Validate knowledge graph functionality

#### 3. RAG MCP Preparation
- Create RAG MCP server framework for future RAG integration
- Establish patterns for HayHooks communication
- Implement document search and ingestion tool interfaces
- Prepare for PBI-13 RAG infrastructure implementation

#### 4. Letta Client Configuration
- Update Letta MCP client configuration for all servers
- Implement service discovery via Docker DNS
- Configure retry logic and error handling
- Test tool availability and functionality

### Health Check and Monitoring
- Standardized health check endpoints for all MCP servers
- Prometheus metrics collection for MCP server performance
- Centralized logging with structured log formats
- Service dependency management with proper startup ordering

## UX/UI Considerations

### Agent Experience
- **Reliable Tool Access**: All MCP tools consistently available to Letta agents
- **Graceful Degradation**: Agent functionality continues if individual MCP servers are unavailable
- **Clear Error Messages**: Meaningful error messages when MCP tools fail
- **Performance Consistency**: Uniform response times across different MCP servers

### Administrative Interface
- **Unified Monitoring**: Single dashboard showing status of all MCP servers
- **Consistent Configuration**: Standardized patterns for MCP server configuration
- **Centralized Logging**: All MCP server logs accessible through unified logging system
- **Health Validation**: Clear health status and diagnostic information for each MCP server

## Acceptance Criteria

### Functional Requirements
- [ ] Gmail MCP server migrated from separate compose and fully functional
- [ ] All MCP servers use consistent configuration patterns and environment variables
- [ ] Letta connects to all MCP servers successfully via internal Docker network
- [ ] Health checks validate MCP server availability and readiness
- [ ] All existing MCP functionality (Gmail, Graphiti) preserved after migration
- [ ] Service discovery works via Docker DNS names (no hardcoded IPs)

### Non-Functional Requirements
- [ ] MCP server startup time under 30 seconds for each server
- [ ] Health checks respond within 5 seconds
- [ ] MCP tool responses complete within 30 seconds for typical operations
- [ ] Configuration changes can be applied without full system restart
- [ ] Error recovery and retry logic prevents temporary failures from disrupting agent workflow

### Integration Requirements
- [ ] All MCP servers integrated into unified Docker Compose configuration
- [ ] Standardized logging format across all MCP servers
- [ ] Monitoring metrics available for all MCP servers via Prometheus
- [ ] Service dependencies properly configured with depends_on
- [ ] Network isolation prevents external access to MCP servers

## Dependencies

### Technical Dependencies
- Docker Compose unification (PBI-2) for unified service deployment
- Unified Docker network for internal service communication
- Gmail OAuth credentials and token management
- Neo4j database for Graphiti MCP functionality
- Standard Docker health check capabilities

### Process Dependencies
- **Upstream**:
  - PBI-2 (Docker Compose Unification) - required for service integration
  - PBI-3 (Network Unification) - required for internal communication
- **Downstream**:
  - PBI-13 (RAG Infrastructure) - RAG MCP server follows established patterns
- **Parallel**:
  - PBI-5 (Slackbot Integration) - both require standardized service patterns

### Migration Dependencies
- Access to current Gmail MCP configuration and credentials
- Graphiti MCP server configuration documentation
- Letta MCP client configuration access
- Testing environment for validating MCP functionality

## Open Questions

1. **MCP Protocol Version**: Should all MCP servers standardize on a specific MCP protocol version?
2. **Authentication**: How should authentication be handled consistently across MCP servers?
3. **Rate Limiting**: Should rate limiting be implemented at the MCP server level or Letta level?
4. **Tool Discovery**: Should dynamic tool discovery be implemented or rely on static configuration?
5. **Error Handling**: What level of error handling and retry logic should be standardized across MCP servers?
6. **Configuration Hot-Reload**: Should MCP servers support configuration hot-reload for operational flexibility?

## Related Tasks

Tasks for this PBI will be defined in [tasks.md](./tasks.md) following the implementation approach:

1. **MCP Server Inventory and Analysis**
2. **Standardized Configuration Pattern Design**
3. **Gmail MCP Server Migration**
4. **Graphiti MCP Server Integration**
5. **RAG MCP Server Framework Creation**
6. **Letta MCP Client Configuration Update**
7. **Health Check and Monitoring Implementation**
8. **Integration Testing and Validation**
9. **Documentation and Operational Guide**

---

**Back to**: [Project Backlog](../backlog.md)
