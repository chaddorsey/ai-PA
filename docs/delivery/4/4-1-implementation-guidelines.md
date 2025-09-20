# MCP Server Implementation Guidelines

## Overview

This document provides step-by-step guidelines for implementing the standardized MCP server configuration patterns across the existing MCP servers and for creating new MCP servers.

## Implementation Phases

### Phase 1: Apply Patterns to Existing MCP Servers

#### 1.1 Gmail MCP Server Standardization

**Current Issues**:
- Inconsistent naming (`gmail` vs `gmail-mcp-server`)
- Non-standard port (7331 vs 8080)
- Missing standardized environment variables
- Basic health check implementation

**Implementation Steps**:

1. **Update Service Name and Container Name**:
   ```yaml
   # Change from:
   gmail:
   
   # To:
   gmail-mcp-server:
     container_name: gmail-mcp-server
   ```

2. **Standardize Port Assignment**:
   ```yaml
   environment:
     - MCP_SERVER_PORT=8080
     - PORT=8080  # Keep for backward compatibility
   ```

3. **Add Standardized Environment Variables**:
   ```yaml
   environment:
     # Common MCP variables
     - MCP_SERVER_NAME=gmail-tools
     - MCP_SERVER_VERSION=1.1.11
     - MCP_SERVER_DESCRIPTION=Gmail integration tools
     - MCP_SERVER_HOST=0.0.0.0
     - MCP_SERVER_PORT=8080
     - MCP_SERVER_PATH=/mcp
     - MCP_LOG_LEVEL=INFO
     - MCP_LOG_FORMAT=json
     - MCP_HEALTH_CHECK_PATH=/health
     
     # Gmail-specific variables
     - GMAIL_OAUTH_PATH=/app/config/gcp-oauth.keys.json
     - GMAIL_CREDENTIALS_PATH=/app/data/credentials.json
   ```

4. **Update Health Check**:
   ```yaml
   healthcheck:
     test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
     interval: 30s
     timeout: 5s
     retries: 3
     start_period: 30s
   ```

5. **Add Standardized Labels**:
   ```yaml
   labels:
     - "service=gmail-mcp-server"
     - "component=mcp-server"
     - "network=pa-internal"
     - "mcp-transport=http"
     - "mcp-version=1.1.11"
     - "security.internal-only=true"
   ```

6. **Update Volume Configuration**:
   ```yaml
   volumes:
     - ./mcp-servers/gmail/config:/app/config:ro
     - gmail-mcp-data:/app/data
     - ./gmail-mcp/gcp-oauth.keys.json:/app/config/gcp-oauth.keys.json:ro
   ```

#### 1.2 Graphiti MCP Server Standardization

**Current Issues**:
- Non-standard port (8000 vs 8082)
- Missing standardized environment variables
- Inconsistent health check timing

**Implementation Steps**:

1. **Update Service Name**:
   ```yaml
   # Change from:
   graphiti-mcp:
   
   # To:
   graphiti-mcp-server:
     container_name: graphiti-mcp-server
   ```

2. **Standardize Port Assignment**:
   ```yaml
   environment:
     - MCP_SERVER_PORT=8082
     - PORT=8082  # Keep for backward compatibility
   ```

3. **Add Standardized Environment Variables**:
   ```yaml
   environment:
     # Common MCP variables
     - MCP_SERVER_NAME=graphiti-tools
     - MCP_SERVER_VERSION=1.0.0
     - MCP_SERVER_DESCRIPTION=Graphiti memory and knowledge graph tools
     - MCP_SERVER_HOST=0.0.0.0
     - MCP_SERVER_PORT=8082
     - MCP_SERVER_PATH=/mcp
     - MCP_LOG_LEVEL=INFO
     - MCP_LOG_FORMAT=json
     - MCP_HEALTH_CHECK_PATH=/health
     
     # Graphiti-specific variables
     - NEO4J_URI=bolt://neo4j:7687
     - NEO4J_USER=neo4j
     - NEO4J_PASSWORD=${NEO4J_PASSWORD}
     - OPENAI_API_KEY=${OPENAI_API_KEY}
   ```

4. **Update Health Check**:
   ```yaml
   healthcheck:
     test: ["CMD", "curl", "-f", "http://localhost:8082/health"]
     interval: 30s
     timeout: 5s
     retries: 3
     start_period: 30s
   ```

#### 1.3 Slack MCP Server Standardization

**Current Issues**:
- Non-standard port (3001 vs 8081)
- Missing standardized environment variables
- Pre-built image (limited customization)

**Implementation Steps**:

1. **Update Service Name**:
   ```yaml
   # Change from:
   slack-mcp-server:
   
   # To:
   slack-mcp-server:
     container_name: slack-mcp-server
   ```

2. **Standardize Port Assignment**:
   ```yaml
   environment:
     - MCP_SERVER_PORT=8081
     - SLACK_MCP_PORT=8081  # Keep for backward compatibility
   ```

3. **Add Standardized Environment Variables**:
   ```yaml
   environment:
     # Common MCP variables
     - MCP_SERVER_NAME=slack-tools
     - MCP_SERVER_VERSION=latest
     - MCP_SERVER_DESCRIPTION=Slack integration tools
     - MCP_SERVER_HOST=0.0.0.0
     - MCP_SERVER_PORT=8081
     - MCP_SERVER_PATH=/mcp
     - MCP_LOG_LEVEL=INFO
     - MCP_LOG_FORMAT=json
     - MCP_HEALTH_CHECK_PATH=/health
     
     # Slack-specific variables
     - SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}
     - SLACK_APP_TOKEN=${SLACK_APP_TOKEN}
   ```

### Phase 2: Create RAG MCP Server Framework

#### 2.1 Directory Structure Setup
```
mcp-servers/
├── rag/
│   ├── Dockerfile
│   ├── src/
│   │   ├── index.js
│   │   ├── server-http.js
│   │   └── server-stdio.js
│   ├── config/
│   │   ├── default.json
│   │   └── production.json
│   ├── package.json
│   └── README.md
```

#### 2.2 RAG MCP Server Configuration
```yaml
rag-mcp-server:
  build:
    context: ./mcp-servers/rag
    dockerfile: Dockerfile
  container_name: rag-mcp-server
  restart: unless-stopped
  networks: [pa-network]
  depends_on:
    hayhooks:
      condition: service_healthy
  user: "1000:1000"
  working_dir: /app
  environment:
    # Common MCP variables
    - MCP_SERVER_NAME=rag-tools
    - MCP_SERVER_VERSION=1.0.0
    - MCP_SERVER_DESCRIPTION=RAG document search and retrieval tools
    - MCP_SERVER_HOST=0.0.0.0
    - MCP_SERVER_PORT=8083
    - MCP_SERVER_PATH=/mcp
    - MCP_LOG_LEVEL=INFO
    - MCP_LOG_FORMAT=json
    - MCP_HEALTH_CHECK_PATH=/health
    
    # RAG-specific variables
    - HAYHOOKS_URL=http://hayhooks:1416
    - HAYHOOKS_API_KEY=${HAYHOOKS_API_KEY}
    - RAG_EMBEDDING_MODEL=text-embedding-3-small
    - RAG_MAX_RESULTS=10
    
  volumes:
    - ./mcp-servers/rag/config:/app/config:ro
    - rag-mcp-data:/app/data
    - rag-mcp-cache:/app/cache
    
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8083/health"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 30s
    
  logging:
    driver: "json-file"
    options:
      max-size: "10m"
      max-file: "3"
      labels: "service,component,network"
      
  labels:
    - "service=rag-mcp-server"
    - "component=mcp-server"
    - "network=pa-internal"
    - "mcp-transport=http"
    - "mcp-version=1.0.0"
    - "security.internal-only=true"
```

### Phase 3: Update Letta MCP Configuration

#### 3.1 Create Letta MCP Configuration File
```json
{
  "mcpServers": {
    "gmail-tools": {
      "command": "http",
      "args": ["http://gmail-mcp-server:8080"],
      "env": {},
      "disabled": false
    },
    "slack-tools": {
      "command": "http",
      "args": ["http://slack-mcp-server:8081"],
      "env": {},
      "disabled": false
    },
    "graphiti-tools": {
      "command": "http",
      "args": ["http://graphiti-mcp-server:8082"],
      "env": {},
      "disabled": false
    },
    "rag-tools": {
      "command": "http",
      "args": ["http://rag-mcp-server:8083"],
      "env": {},
      "disabled": false
    }
  }
}
```

#### 3.2 Update Docker Compose Volume Mount
```yaml
letta:
  volumes:
    - ./letta/letta_mcp_config.json:/root/.letta/mcp_config.json
```

## Implementation Checklist

### Pre-Implementation
- [ ] Backup current docker-compose.yml
- [ ] Create mcp-servers directory structure
- [ ] Review current MCP server implementations
- [ ] Plan port reassignments
- [ ] Prepare environment variable updates

### Gmail MCP Server
- [ ] Update service name to `gmail-mcp-server`
- [ ] Change port from 7331 to 8080
- [ ] Add standardized environment variables
- [ ] Update health check endpoint
- [ ] Add standardized labels
- [ ] Update volume configuration
- [ ] Test Gmail functionality

### Graphiti MCP Server
- [ ] Update service name to `graphiti-mcp-server`
- [ ] Change port from 8000 to 8082
- [ ] Add standardized environment variables
- [ ] Update health check timing
- [ ] Add standardized labels
- [ ] Test Graphiti functionality

### Slack MCP Server
- [ ] Update service name to `slack-mcp-server`
- [ ] Change port from 3001 to 8081
- [ ] Add standardized environment variables
- [ ] Add standardized labels
- [ ] Test Slack functionality

### RAG MCP Server
- [ ] Create directory structure
- [ ] Implement basic MCP server
- [ ] Add health check endpoint
- [ ] Configure HayHooks integration
- [ ] Test RAG functionality

### Letta Configuration
- [ ] Create letta_mcp_config.json
- [ ] Update volume mount
- [ ] Test MCP server connections
- [ ] Validate tool availability

### Post-Implementation
- [ ] Test all MCP servers start successfully
- [ ] Verify health checks pass
- [ ] Test Letta can connect to all MCP servers
- [ ] Validate tool functionality
- [ ] Check logging output
- [ ] Verify monitoring works
- [ ] Update documentation

## Testing Procedures

### 1. Individual MCP Server Testing
```bash
# Test Gmail MCP Server
curl -f http://gmail-mcp-server:8080/health

# Test Slack MCP Server  
curl -f http://slack-mcp-server:8081/health

# Test Graphiti MCP Server
curl -f http://graphiti-mcp-server:8082/health

# Test RAG MCP Server
curl -f http://rag-mcp-server:8083/health
```

### 2. MCP Protocol Testing
```bash
# Test MCP endpoint
curl -X POST http://gmail-mcp-server:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}'
```

### 3. Letta Integration Testing
- Start Letta container
- Check MCP server connections in logs
- Test tool availability through Letta interface
- Verify tool functionality

## Rollback Procedures

### If Issues Occur
1. **Stop all services**: `docker-compose down`
2. **Restore backup**: `cp docker-compose.yml.backup docker-compose.yml`
3. **Start services**: `docker-compose up -d`
4. **Verify functionality**: Test all MCP servers
5. **Investigate issues**: Check logs and configuration

### Gradual Rollback
1. **Revert one MCP server at a time**
2. **Test after each revert**
3. **Identify specific issues**
4. **Fix and retry**

## Monitoring and Maintenance

### Health Monitoring
- Set up monitoring for all MCP server health endpoints
- Configure alerts for health check failures
- Monitor MCP server resource usage

### Log Monitoring
- Centralize logs from all MCP servers
- Set up log aggregation and analysis
- Monitor for errors and performance issues

### Regular Maintenance
- Update MCP server versions regularly
- Review and update configuration patterns
- Monitor MCP protocol compliance
- Update documentation as needed
