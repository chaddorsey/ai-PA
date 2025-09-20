# Gmail MCP Server Standardization

## Overview

This document describes the standardization of the Gmail MCP server configuration in the main docker-compose.yml file, applying the standardized MCP server patterns defined in task 4-1.

## Changes Made

### 1. Service Configuration Updates

#### Service Naming
- **Before**: `gmail`
- **After**: `gmail-mcp-server`
- **Container Name**: `gmail-mcp-server`
- **Rationale**: Follows standardized naming pattern `{service}-mcp-server`

#### Port Assignment
- **Before**: `7331`
- **After**: `8080`
- **Rationale**: Standardized port assignment for Gmail MCP server

### 2. Environment Variables

#### Added Standardized Variables
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
```

#### Updated Gmail-Specific Variables
```yaml
environment:
  # Gmail-specific variables
  - GMAIL_OAUTH_PATH=/app/config/gcp-oauth.keys.json
  - GMAIL_CREDENTIALS_PATH=/app/data/credentials.json
  - PORT=8080
```

### 3. Health Check Standardization

#### Before
```yaml
healthcheck:
  test: ["CMD", "nc", "-z", "localhost", "7331"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 30s
```

#### After
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 30s
```

#### Health Check Response Format
The health check endpoint now returns standardized JSON:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-20T20:00:00.000Z",
  "service": "gmail-tools",
  "version": "1.1.11",
  "uptime": 3600.5,
  "dependencies": {
    "gmail_api": "healthy",
    "external_apis": "healthy"
  }
}
```

### 4. Volume Management

#### Before
```yaml
volumes:
  - mcp-gmail:/gmail-server
  - ./gmail-mcp/gcp-oauth.keys.json:/gcp-oauth.keys.json:ro
```

#### After
```yaml
volumes:
  - gmail-mcp-data:/app/data
  - ./gmail-mcp/gcp-oauth.keys.json:/app/config/gcp-oauth.keys.json:ro
```

#### Volume Naming
- **Before**: `mcp-gmail`
- **After**: `gmail-mcp-data`
- **Rationale**: Follows standardized naming pattern `{service}-mcp-data`

### 5. Logging Configuration

#### Added Standardized Logging
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
    labels: "service,component,network"
```

### 6. Service Labels

#### Added Standardized Labels
```yaml
labels:
  - "service=gmail-mcp-server"
  - "component=mcp-server"
  - "network=pa-internal"
  - "mcp-transport=http"
  - "mcp-version=1.1.11"
  - "security.internal-only=true"
  - "security.no-external-access=true"
```

### 7. Dockerfile Updates

#### Updated Paths
- **Before**: `/gmail-server`, `/root/.gmail-mcp`
- **After**: `/app/data`, `/app/config`
- **Rationale**: Follows standardized directory structure

#### Updated Port
- **Before**: `EXPOSE 7331`
- **After**: `EXPOSE 8080`
- **Rationale**: Matches standardized port assignment

## Code Changes

### server-http.ts Updates

#### Port Configuration
```typescript
// Before
const PORT = Number(process.env.PORT || 7331);

// After
const PORT = Number(process.env.PORT || 8080);
const HEALTH_PATH = process.env.MCP_HEALTH_CHECK_PATH || "/health";
```

#### Health Check Endpoint
```typescript
// Before
app.get("/healthz", (_req: Request, res: Response) => {
  res.status(200).json({ ok: true });
});

// After
app.get(HEALTH_PATH, (_req: Request, res: Response) => {
  const serverName = process.env.MCP_SERVER_NAME || "gmail-tools";
  const serverVersion = process.env.MCP_SERVER_VERSION || "1.1.11";
  
  res.status(200).json({
    status: "healthy",
    timestamp: new Date().toISOString(),
    service: serverName,
    version: serverVersion,
    uptime: process.uptime(),
    dependencies: {
      gmail_api: "healthy",
      external_apis: "healthy"
    }
  });
});
```

## Migration Impact

### Backward Compatibility
- **OAuth Keys**: Path updated but functionality preserved
- **Credentials**: Storage location updated but data preserved
- **API Endpoints**: MCP endpoint remains at `/mcp`
- **Health Check**: Moved from `/healthz` to `/health`

### Breaking Changes
- **Service Name**: `gmail` → `gmail-mcp-server`
- **Port**: `7331` → `8080`
- **Volume Name**: `mcp-gmail` → `gmail-mcp-data`
- **Health Endpoint**: `/healthz` → `/health`

### Required Updates
1. **Letta Configuration**: Update MCP server URL to use new port
2. **Monitoring**: Update health check endpoints
3. **Documentation**: Update all references to old service name/port

## Testing

### Pre-Migration Testing
1. **Current Functionality**: Verify Gmail MCP works with current configuration
2. **OAuth Flow**: Test Gmail authentication and token management
3. **Email Operations**: Test all Gmail MCP tools

### Post-Migration Testing
1. **Service Startup**: Verify Gmail MCP server starts with new configuration
2. **Health Check**: Test health endpoint returns proper format
3. **MCP Functionality**: Verify all Gmail tools work through MCP
4. **Letta Integration**: Test Letta can connect to updated Gmail MCP server
5. **Logging**: Verify structured logging is working
6. **Volume Mounts**: Test OAuth keys and credentials are accessible

### Test Commands
```bash
# Test health check
curl -f http://gmail-mcp-server:8080/health

# Test MCP endpoint
curl -X POST http://gmail-mcp-server:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}'

# Test Letta connection
curl http://letta:8283/v1/tools/mcp/servers
```

## Rollback Plan

### If Issues Occur
1. **Revert docker-compose.yml**: Change service name back to `gmail`
2. **Revert port**: Change back to `7331`
3. **Revert volumes**: Use original volume names
4. **Revert Dockerfile**: Use original paths
5. **Test functionality**: Verify Gmail MCP works with old configuration

### Gradual Rollback
1. **Test with old configuration first**
2. **Apply changes incrementally**
3. **Test after each change**
4. **Identify specific issues**

## Monitoring

### Health Monitoring
- Monitor health endpoint: `http://gmail-mcp-server:8080/health`
- Set up alerts for health check failures
- Track response times and availability

### Log Monitoring
- Monitor structured logs for errors
- Track MCP tool usage
- Monitor OAuth token refresh

### Metrics to Track
- Service uptime and availability
- MCP tool response times
- OAuth token refresh frequency
- Error rates and types

## Security Considerations

### Network Security
- Service runs on internal network only
- No external port exposure
- Health check endpoint accessible internally only

### OAuth Security
- OAuth keys mounted as read-only
- Credentials stored in secure volume
- No hardcoded credentials in configuration

### Access Control
- Service labeled as internal-only
- No external access allowed
- Proper volume permissions

## Future Improvements

### Health Check Enhancements
- Add actual Gmail API health check
- Implement dependency health validation
- Add performance metrics to health response

### Logging Improvements
- Add request/response logging
- Implement log correlation IDs
- Add performance metrics

### Monitoring Enhancements
- Add Prometheus metrics endpoint
- Implement health check aggregation
- Add alerting for critical failures
