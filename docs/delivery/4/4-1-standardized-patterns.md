# Standardized MCP Server Configuration Patterns

## Overview

This document defines standardized configuration patterns for MCP servers in the unified Docker Compose setup. These patterns ensure consistency, maintainability, and operational excellence across all MCP implementations.

## 1. Service Naming Standards

### Container Naming Convention
```yaml
# Pattern: {service}-mcp-server
gmail-mcp-server:
slack-mcp-server:
graphiti-mcp-server:
rag-mcp-server:
```

### Service Labeling
```yaml
labels:
  - "service={service}-mcp-server"
  - "component=mcp-server"
  - "network=pa-internal"
  - "mcp-transport={http|stdio}"
  - "mcp-version={version}"
```

## 2. Environment Variable Standards

### Common Environment Variables
All MCP servers should support these standardized environment variables:

```yaml
environment:
  # MCP Server Identity
  - MCP_SERVER_NAME={service}-tools
  - MCP_SERVER_VERSION={version}
  - MCP_SERVER_DESCRIPTION={description}
  
  # Network Configuration
  - MCP_SERVER_HOST=0.0.0.0
  - MCP_SERVER_PORT={port}
  - MCP_SERVER_PATH=/mcp
  
  # Logging Configuration
  - MCP_LOG_LEVEL=INFO
  - MCP_LOG_FORMAT=json
  
  # Health Check Configuration
  - MCP_HEALTH_CHECK_PATH=/health
  - MCP_HEALTH_CHECK_INTERVAL=30s
  - MCP_HEALTH_CHECK_TIMEOUT=5s
  - MCP_HEALTH_CHECK_RETRIES=3
  - MCP_HEALTH_CHECK_START_PERIOD=30s
```

### Service-Specific Environment Variables
Use service-specific prefixes for unique configuration:

```yaml
# Gmail MCP
environment:
  - GMAIL_OAUTH_PATH=/app/config/gcp-oauth.keys.json
  - GMAIL_CREDENTIALS_PATH=/app/data/credentials.json

# Graphiti MCP
environment:
  - NEO4J_URI=bolt://neo4j:7687
  - NEO4J_USER=neo4j
  - NEO4J_PASSWORD=${NEO4J_PASSWORD}
  - OPENAI_API_KEY=${OPENAI_API_KEY}

# Slack MCP
environment:
  - SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}
  - SLACK_APP_TOKEN=${SLACK_APP_TOKEN}
```

## 3. Health Check Standards

### Standardized Health Check Configuration
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:${MCP_SERVER_PORT}${MCP_HEALTH_CHECK_PATH}"]
  interval: ${MCP_HEALTH_CHECK_INTERVAL}
  timeout: ${MCP_HEALTH_CHECK_TIMEOUT}
  retries: ${MCP_HEALTH_CHECK_RETRIES}
  start_period: ${MCP_HEALTH_CHECK_START_PERIOD}
```

### Health Check Response Format
All MCP servers should implement a `/health` endpoint that returns:

```json
{
  "status": "healthy|unhealthy",
  "timestamp": "2025-01-20T19:00:00Z",
  "service": "{service}-mcp-server",
  "version": "{version}",
  "uptime": "PT1H30M45S",
  "dependencies": {
    "database": "healthy|unhealthy|not_required",
    "external_apis": "healthy|unhealthy|not_required"
  }
}
```

## 4. Network Configuration Standards

### Standard Network Configuration
```yaml
networks: [pa-network]
depends_on:
  {dependency}:
    condition: service_healthy
```

### Port Assignment Standards
- **Gmail MCP**: 8080
- **Slack MCP**: 8081  
- **Graphiti MCP**: 8082
- **RAG MCP**: 8083
- **Future MCPs**: 8084+

## 5. Volume Management Standards

### Standard Volume Patterns
```yaml
volumes:
  # Configuration files (read-only)
  - ./mcp-servers/{service}/config:/app/config:ro
  
  # Persistent data
  - {service}-mcp-data:/app/data
  
  # Cache files
  - {service}-mcp-cache:/app/cache
```

### Volume Naming Convention
- Configuration: `{service}-mcp-config`
- Data: `{service}-mcp-data`
- Cache: `{service}-mcp-cache`
- Logs: `{service}-mcp-logs`

## 6. Logging Standards

### Standardized Logging Configuration
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
    labels: "service,component,network"
```

### Log Format Standards
All MCP servers should use structured JSON logging:

```json
{
  "timestamp": "2025-01-20T19:00:00.000Z",
  "level": "INFO",
  "service": "gmail-mcp-server",
  "component": "mcp-server",
  "message": "MCP server started successfully",
  "mcp_server_name": "gmail-tools",
  "mcp_server_version": "1.0.0",
  "mcp_transport": "http",
  "mcp_port": 8080
}
```

## 7. Security Standards

### User Context Standards
```yaml
# Prefer non-root user when possible
user: "1000:1000"
# Or explicit root when required
user: root
```

### Security Labels
```yaml
labels:
  - "security.internal-only=true"
  - "security.no-external-access=true"
  - "security.requires-auth=false"
```

## 8. Restart and Resource Standards

### Restart Policy
```yaml
restart: unless-stopped
```

### Resource Limits (Optional)
```yaml
deploy:
  resources:
    limits:
      memory: 512M
      cpus: '0.5'
    reservations:
      memory: 256M
      cpus: '0.25'
```

## 9. MCP Server Implementation Standards

### HTTP Transport Implementation
All MCP servers should implement:

1. **Health Endpoint**: `GET /health`
2. **MCP Endpoint**: `POST /mcp` (or configurable path)
3. **Metrics Endpoint**: `GET /metrics` (optional)
4. **Status Endpoint**: `GET /status` (optional)

### MCP Protocol Compliance
- Support MCP protocol version 1.0+
- Implement proper error handling
- Support both HTTP and stdio transports
- Provide proper MCP server capabilities

## 10. Configuration Template

### Complete MCP Server Template
```yaml
{service}-mcp-server:
  build:
    context: ./mcp-servers/{service}
    dockerfile: Dockerfile
  container_name: {service}-mcp-server
  restart: unless-stopped
  networks: [pa-network]
  depends_on:
    {dependency}:
      condition: service_healthy
  user: "1000:1000"  # or root if required
  working_dir: /app
  environment:
    # Common MCP variables
    - MCP_SERVER_NAME={service}-tools
    - MCP_SERVER_VERSION={version}
    - MCP_SERVER_DESCRIPTION={description}
    - MCP_SERVER_HOST=0.0.0.0
    - MCP_SERVER_PORT={port}
    - MCP_SERVER_PATH=/mcp
    - MCP_LOG_LEVEL=INFO
    - MCP_LOG_FORMAT=json
    - MCP_HEALTH_CHECK_PATH=/health
    - MCP_HEALTH_CHECK_INTERVAL=30s
    - MCP_HEALTH_CHECK_TIMEOUT=5s
    - MCP_HEALTH_CHECK_RETRIES=3
    - MCP_HEALTH_CHECK_START_PERIOD=30s
    
    # Service-specific variables
    - {SERVICE_SPECIFIC_VARIABLES}
    
  volumes:
    - ./mcp-servers/{service}/config:/app/config:ro
    - {service}-mcp-data:/app/data
    - {service}-mcp-cache:/app/cache
    
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:${MCP_SERVER_PORT}${MCP_HEALTH_CHECK_PATH}"]
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
    - "service={service}-mcp-server"
    - "component=mcp-server"
    - "network=pa-internal"
    - "mcp-transport=http"
    - "mcp-version={version}"
    - "security.internal-only=true"
    - "security.no-external-access=true"
```

## 11. Directory Structure Standards

### MCP Server Directory Structure
```
mcp-servers/
├── {service}/
│   ├── Dockerfile
│   ├── src/
│   │   ├── index.js          # or main.py
│   │   ├── server-http.js    # HTTP transport
│   │   └── server-stdio.js   # stdio transport
│   ├── config/
│   │   ├── default.json
│   │   └── production.json
│   ├── requirements.txt      # or package.json
│   └── README.md
```

## 12. Validation Checklist

### Pre-Deployment Validation
- [ ] Service name follows naming convention
- [ ] All required environment variables are set
- [ ] Health check endpoint is implemented
- [ ] Logging is configured and structured
- [ ] Security labels are applied
- [ ] Volume mounts are properly configured
- [ ] Network configuration is correct
- [ ] Dependencies are properly declared
- [ ] MCP protocol compliance is verified

### Post-Deployment Validation
- [ ] Service starts successfully
- [ ] Health check passes
- [ ] MCP tools are discoverable
- [ ] Logs are properly formatted
- [ ] Service responds to MCP requests
- [ ] Dependencies are accessible
- [ ] Performance meets requirements

