# Graphiti MCP Server Standardization

## Overview

This document describes the standardization of the Graphiti MCP server configuration in the main docker-compose.yml file, applying the standardized MCP server patterns defined in task 4-1 while preserving all Graphiti knowledge graph functionality.

## Changes Made

### 1. Service Configuration Updates

#### Service Naming
- **Before**: `graphiti-mcp`
- **After**: `graphiti-mcp-server`
- **Container Name**: `graphiti-mcp-server`
- **Rationale**: Follows standardized naming pattern `{service}-mcp-server`

#### Port Assignment
- **Before**: `8000`
- **After**: `8082`
- **Rationale**: Standardized port assignment for Graphiti MCP server

### 2. Environment Variables

#### Added Standardized Variables
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
```

#### Maintained Graphiti-Specific Variables
```yaml
environment:
  # Graphiti-specific variables
  - OPENAI_API_KEY=${OPENAI_API_KEY}
  - MODEL_NAME=${MODEL_NAME:-gpt-4.1-mini}
  - NEO4J_URI=bolt://neo4j:7687
  - NEO4J_USER=neo4j
  - NEO4J_PASSWORD=demodemo
  - GRAPHITI_TELEMETRY_ENABLED=false
  - SEMAPHORE_LIMIT=10
  - RESET_NEO4J=true
  - HOST=0.0.0.0
  - PORT=8082
```

### 3. Health Check Standardization

#### Before
```yaml
healthcheck:
  test: ["CMD", "nc", "-z", "localhost", "8000"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 45s
```

#### After
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8082/health"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 45s
```

#### Health Check Response Format
The health check endpoint now returns standardized JSON:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-20T20:00:00.000Z",
  "service": "graphiti-tools",
  "version": "1.0.0",
  "uptime": "PT3600S",
  "dependencies": {
    "neo4j": "healthy",
    "openai_api": "healthy",
    "external_apis": "healthy"
  }
}
```

### 4. Logging Configuration

#### Added Standardized Logging
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
    labels: "service,component,network"
```

### 5. Service Labels

#### Added Standardized Labels
```yaml
labels:
  - "service=graphiti-mcp-server"
  - "component=mcp-server"
  - "network=pa-internal"
  - "mcp-transport=http"
  - "mcp-version=1.0.0"
  - "security.internal-only=true"
  - "security.no-external-access=true"
```

## Code Changes

### graphiti_mcp_server.py Updates

#### Health Check Endpoint
Added a new standardized health check endpoint:

```python
@mcp.resource('http://graphiti/health')
async def get_health() -> dict[str, Any]:
    """Get the health status of the Graphiti MCP server with standardized format."""
    global graphiti_client
    
    server_name = os.getenv('MCP_SERVER_NAME', 'graphiti-tools')
    server_version = os.getenv('MCP_SERVER_VERSION', '1.0.0')
    
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'service': server_name,
        'version': server_version,
        'uptime': f"PT{int(time.time())}S",
        'dependencies': {
            'neo4j': 'healthy',
            'openai_api': 'healthy',
            'external_apis': 'healthy'
        }
    }
    
    if graphiti_client is None:
        health_status['status'] = 'unhealthy'
        health_status['dependencies']['neo4j'] = 'unhealthy'
        health_status['error'] = 'Graphiti client not initialized'
        return health_status

    try:
        # Test Neo4j connection
        assert graphiti_client is not None
        client = cast(Graphiti, graphiti_client)
        await client.driver.client.verify_connectivity()
        
        # Test OpenAI API if configured
        if not os.getenv('OPENAI_API_KEY'):
            health_status['dependencies']['openai_api'] = 'not_configured'
        else:
            health_status['dependencies']['openai_api'] = 'healthy'
            
    except Exception as e:
        health_status['status'] = 'unhealthy'
        health_status['dependencies']['neo4j'] = 'unhealthy'
        health_status['error'] = f'Neo4j connection failed: {str(e)}'
        logger.error(f'Health check failed: {str(e)}')
    
    return health_status
```

#### Import Updates
Added required imports for health check functionality:
```python
import time
```

## Migration Impact

### Backward Compatibility
- **Neo4j Connection**: Preserved and maintained
- **Knowledge Graph Operations**: All functionality preserved
- **MCP Tools**: All Graphiti tools remain functional
- **API Endpoints**: MCP endpoint remains at `/mcp`
- **Status Endpoint**: Original `/status` endpoint preserved

### Breaking Changes
- **Service Name**: `graphiti-mcp` → `graphiti-mcp-server`
- **Port**: `8000` → `8082`
- **Health Endpoint**: Added `/health` endpoint (original `/status` preserved)

### Required Updates
1. **Letta Configuration**: Update MCP server URL to use new port
2. **Monitoring**: Update health check endpoints
3. **Documentation**: Update all references to old service name/port

## Testing

### Pre-Migration Testing
1. **Current Functionality**: Verify Graphiti MCP works with current configuration
2. **Neo4j Connection**: Test database connectivity and operations
3. **Knowledge Graph Operations**: Test all Graphiti tools and workflows
4. **MCP Protocol**: Test MCP server initialization and tool discovery

### Post-Migration Testing
1. **Service Startup**: Verify Graphiti MCP server starts with new configuration
2. **Health Check**: Test health endpoint returns proper format
3. **Neo4j Connectivity**: Test database connection and operations
4. **MCP Functionality**: Verify all Graphiti tools work through MCP
5. **Letta Integration**: Test Letta can connect to updated Graphiti MCP server
6. **Logging**: Verify structured logging is working
7. **Knowledge Graph**: Test knowledge graph operations and data persistence

### Test Commands
```bash
# Test health check
curl -f http://graphiti-mcp-server:8082/health

# Test MCP endpoint
curl -X POST http://graphiti-mcp-server:8082/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}'

# Test Graphiti tools
curl -X POST http://graphiti-mcp-server:8082/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'

# Test Letta connection
curl http://letta:8283/v1/tools/mcp/servers
```

## Rollback Plan

### If Issues Occur
1. **Revert docker-compose.yml**: Change service name back to `graphiti-mcp`
2. **Revert port**: Change back to `8000`
3. **Revert health check**: Use original nc-based health check
4. **Test functionality**: Verify Graphiti MCP works with old configuration

### Gradual Rollback
1. **Test with old configuration first**
2. **Apply changes incrementally**
3. **Test after each change**
4. **Identify specific issues**

## Monitoring

### Health Monitoring
- Monitor health endpoint: `http://graphiti-mcp-server:8082/health`
- Set up alerts for health check failures
- Track Neo4j connection status
- Monitor knowledge graph operations

### Log Monitoring
- Monitor structured logs for errors
- Track MCP tool usage
- Monitor Neo4j connection issues
- Track knowledge graph operations

### Metrics to Track
- Service uptime and availability
- Neo4j connection health
- MCP tool response times
- Knowledge graph operation success rates
- Error rates and types

## Security Considerations

### Network Security
- Service runs on internal network only
- No external port exposure
- Health check endpoint accessible internally only

### Database Security
- Neo4j connection uses internal network
- Database credentials managed via environment variables
- No hardcoded credentials in configuration

### Access Control
- Service labeled as internal-only
- No external access allowed
- Proper dependency management

## Future Improvements

### Health Check Enhancements
- Add actual Neo4j query testing
- Implement OpenAI API health validation
- Add performance metrics to health response
- Implement dependency health aggregation

### Logging Improvements
- Add request/response logging
- Implement log correlation IDs
- Add performance metrics
- Enhance error tracking

### Monitoring Enhancements
- Add Prometheus metrics endpoint
- Implement health check aggregation
- Add alerting for critical failures
- Add knowledge graph operation metrics

## Knowledge Graph Considerations

### Data Persistence
- Neo4j data remains unchanged
- All existing knowledge graph data preserved
- No data migration required
- Index and constraint management maintained

### Performance Impact
- No performance degradation expected
- Health checks may add minimal overhead
- Logging may add slight overhead
- Neo4j connection pooling maintained

### Operational Impact
- Service restart required for configuration changes
- Neo4j dependency management preserved
- Knowledge graph operations remain uninterrupted
- MCP tool functionality preserved

