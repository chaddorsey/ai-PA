# MCP Server Configuration Analysis

## Current MCP Server Implementations

### 1. Gmail MCP Server

**Location**: `docker-compose.yml` lines 358-377, `gmail-mcp/` directory

**Configuration**:
```yaml
gmail:
  build:
    context: ./gmail-mcp
    dockerfile: Dockerfile
  image: gmail-mcp-server
  networks: [pa-network]
  volumes:
    - mcp-gmail:/gmail-server
    - ./gmail-mcp/gcp-oauth.keys.json:/gcp-oauth.keys.json:ro
  environment:
    GMAIL_OAUTH_PATH: /gcp-oauth.keys.json
    GMAIL_CREDENTIALS_PATH: /gmail-server/credentials.json
    PORT: 7331
  healthcheck:
    test: ["CMD", "nc", "-z", "localhost", "7331"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 30s
```

**Key Characteristics**:
- **Transport**: HTTP (port 7331)
- **Build**: Custom Dockerfile from `gmail-mcp/` directory
- **Dependencies**: None (standalone)
- **Volumes**: 
  - `mcp-gmail` for credentials storage
  - OAuth keys mounted as read-only
- **Environment Variables**: Gmail-specific (OAuth paths, port)
- **Health Check**: Simple port check using `nc`

**Dockerfile Analysis**:
- Base: `node:20-slim`
- Exposes port 7331
- Uses `server-http.js` as entry point
- Environment variables set for Gmail OAuth

### 2. Graphiti MCP Server

**Location**: `docker-compose.yml` lines 191-221, `graphiti/mcp_server/` directory

**Configuration**:
```yaml
graphiti-mcp:
  build:
    context: /Users/chaddorsey/dev/ai-PA/graphiti/mcp_server
  container_name: graphiti-mcp
  user: root
  restart: unless-stopped
  networks: [pa-network]
  depends_on:
    neo4j:
      condition: service_healthy
  working_dir: /app
  entrypoint: ["/root/.local/bin/uv","run","graphiti_mcp_server.py"]
  environment:
    OPENAI_API_KEY: "${OPENAI_API_KEY}"
    MODEL_NAME: "${MODEL_NAME:-gpt-4.1-mini}"
    NEO4J_URI: bolt://neo4j:7687
    NEO4J_USER: neo4j
    NEO4J_PASSWORD: demodemo
    GRAPHITI_TELEMETRY_ENABLED: "false"
    SEMAPHORE_LIMIT: "10"
    RESET_NEO4J: "true"
    HOST: "0.0.0.0"
    PORT: "8000"
  healthcheck:
    test: ["CMD", "nc", "-z", "localhost", "8000"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 45s
```

**Key Characteristics**:
- **Transport**: HTTP (port 8000) with SSE support
- **Build**: Custom Dockerfile from `graphiti/mcp_server/` directory
- **Dependencies**: Neo4j database (service dependency)
- **Volumes**: None (uses environment variables)
- **Environment Variables**: Extensive (OpenAI, Neo4j, Graphiti-specific)
- **Health Check**: Simple port check using `nc`

**Dockerfile Analysis**:
- Base: `python:3.12-slim`
- Uses `uv` for Python package management
- Exposes port 8000
- Runs as non-root user
- Supports both stdio and SSE transports

### 3. Slack MCP Server

**Location**: `docker-compose.yml` lines 339-356

**Configuration**:
```yaml
slack-mcp-server:
  image: ghcr.io/korotovsky/slack-mcp-server:latest
  restart: unless-stopped
  networks: [pa-network]
  volumes:
    - users_cache:/app/mcp-server/.users_cache.json
    - channels_cache:/app/mcp-server/.channels_cache.json
  env_file:
    - .env
  environment:
    SLACK_MCP_HOST: "0.0.0.0"
    SLACK_MCP_PORT: "3001"
  healthcheck:
    test: ["CMD", "nc", "-z", "localhost", "3001"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 30s
```

**Key Characteristics**:
- **Transport**: HTTP (port 3001)
- **Build**: Pre-built image from GitHub Container Registry
- **Dependencies**: None (standalone)
- **Volumes**: Cache files for users and channels
- **Environment Variables**: Minimal (host, port)
- **Health Check**: Simple port check using `nc`

## Configuration Inconsistencies Identified

### 1. Environment Variable Patterns
- **Gmail**: Uses `GMAIL_*` prefix, `PORT` for port
- **Graphiti**: Uses `NEO4J_*`, `OPENAI_*`, `GRAPHITI_*` prefixes, `HOST`/`PORT` for network
- **Slack**: Uses `SLACK_MCP_*` prefix, `SLACK_MCP_HOST`/`SLACK_MCP_PORT` for network

### 2. Health Check Patterns
- **Gmail**: 30s interval, 5s timeout, 3 retries, 30s start_period
- **Graphiti**: 30s interval, 5s timeout, 3 retries, 45s start_period
- **Slack**: 30s interval, 5s timeout, 3 retries, 30s start_period

### 3. Port Assignment
- **Gmail**: 7331
- **Graphiti**: 8000
- **Slack**: 3001

### 4. Service Naming
- **Gmail**: `gmail` (simple)
- **Graphiti**: `graphiti-mcp` (with suffix)
- **Slack**: `slack-mcp-server` (with suffix)

### 5. Volume Management
- **Gmail**: Uses named volume + bind mount for OAuth keys
- **Graphiti**: No volumes (environment variables only)
- **Slack**: Uses named volumes for cache files

### 6. Dependencies
- **Gmail**: None
- **Graphiti**: Depends on Neo4j with health check condition
- **Slack**: None

### 7. Restart Policies
- **Gmail**: Not specified (default)
- **Graphiti**: `unless-stopped`
- **Slack**: `unless-stopped`

### 8. User Context
- **Gmail**: Default (root)
- **Graphiti**: `user: root` (explicit)
- **Slack**: Default (root)

## Transport Protocol Analysis

### HTTP Transport (All Current Servers)
- All three MCP servers use HTTP transport
- Gmail: Express.js server with MCP SDK
- Graphiti: FastMCP with SSE support
- Slack: Unknown implementation (pre-built image)

### MCP Protocol Support
- **Gmail**: Uses `@modelcontextprotocol/sdk` with HTTP transport
- **Graphiti**: Uses `FastMCP` with both stdio and SSE support
- **Slack**: Unknown (pre-built image)

## Network Configuration Analysis

### Current Network Setup
- All MCP servers use `pa-network` (pa-internal)
- Network is properly configured with bridge driver
- Subnet: 172.20.0.0/16
- Gateway: 172.20.0.1

### Service Discovery
- Services can communicate via container names
- No hardcoded IPs (good practice)
- DNS resolution works within the network

## Volume and Data Management

### Volume Patterns
1. **Named Volumes**: Used for persistent data (credentials, cache)
2. **Bind Mounts**: Used for configuration files (OAuth keys)
3. **No Volumes**: Used when data is managed via environment variables

### Data Persistence
- **Gmail**: OAuth credentials and tokens
- **Graphiti**: No persistent data (uses Neo4j)
- **Slack**: User and channel cache

## Health Check Analysis

### Current Health Check Implementation
- All use `nc` (netcat) for port checking
- Consistent timing patterns (30s interval, 5s timeout, 3 retries)
- Different start periods (30s for Gmail/Slack, 45s for Graphiti)

### Health Check Limitations
- Only checks if port is open, not if service is functional
- No application-level health validation
- No MCP protocol-specific health checks

## Logging and Monitoring

### Current Logging
- **Gmail**: Console logging via Express.js
- **Graphiti**: Structured logging with Python logging module
- **Slack**: Unknown (pre-built image)

### Monitoring Gaps
- No standardized logging format
- No centralized log collection
- No metrics collection
- No service labeling for monitoring

## Security Considerations

### Current Security Posture
- All services run on internal network only
- No external port exposure
- OAuth keys mounted as read-only
- No explicit security scanning

### Security Gaps
- No explicit user context standardization
- No security labeling
- No secrets management standardization
- No TLS/SSL configuration

## Recommendations for Standardization

### 1. Environment Variable Standardization
- Use consistent prefixes: `MCP_SERVER_*` for common variables
- Standardize port configuration: `MCP_SERVER_PORT`
- Standardize host configuration: `MCP_SERVER_HOST`
- Use service-specific prefixes for unique variables

### 2. Health Check Standardization
- Implement application-level health checks
- Standardize timing parameters
- Add MCP protocol validation
- Create health check response format standards

### 3. Service Naming Standardization
- Use consistent naming pattern: `{service}-mcp-server`
- Standardize container names
- Use consistent service labels

### 4. Volume Management Standardization
- Standardize volume naming patterns
- Create volume management guidelines
- Standardize mount point conventions

### 5. Network Configuration Standardization
- Ensure all MCP servers use internal network only
- Standardize service discovery patterns
- Implement consistent dependency management

### 6. Logging and Monitoring Standardization
- Implement structured logging across all servers
- Add service labeling for monitoring
- Create centralized log collection
- Implement metrics collection

### 7. Security Standardization
- Standardize user context (non-root where possible)
- Implement security labeling
- Create secrets management patterns
- Add security scanning procedures

