# Letta MCP Configuration Documentation

## Overview

This document describes the Letta MCP server configuration for the unified PA ecosystem. The configuration enables Letta to connect to all MCP servers via the internal Docker network using standardized naming and port conventions.

## Configuration Files

### 1. Legacy JSON Configuration (Deprecated)
**File**: `letta/letta_mcp_config.json`

This file contains the legacy JSON configuration format. While Letta no longer officially supports this format, it may still work for self-hosted deployments.

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

### 2. API-Based Configuration (Recommended)
**File**: `letta/configure_mcp_servers.py`

This Python script uses the Letta API to programmatically configure MCP servers. This is the recommended approach for production deployments.

**Features**:
- Uses Streamable HTTP transport (recommended)
- Automatic server discovery and health checking
- Error handling and retry logic
- Support for custom headers and authentication

**Usage**:
```bash
# Run the configuration script
python configure_mcp_servers.py

# Or use the shell script wrapper
./configure_mcp.sh
```

## MCP Server Configuration

### Server Endpoints

| Server Name | Service Name | Port | Endpoint | Description |
|-------------|--------------|------|----------|-------------|
| gmail-tools | gmail-mcp-server | 8080 | `/mcp` | Gmail integration tools |
| slack-tools | slack-mcp-server | 8081 | `/mcp` | Slack integration tools |
| graphiti-tools | graphiti-mcp-server | 8082 | `/mcp` | Knowledge graph tools |
| rag-tools | rag-mcp-server | 8083 | `/mcp` | RAG document search tools |

### Network Configuration

All MCP servers are configured to use:
- **Network**: `pa-internal` (internal Docker network)
- **Transport**: Streamable HTTP
- **Service Discovery**: Docker DNS names
- **Authentication**: None (internal network only)

### Health Check Endpoints

Each MCP server exposes a health check endpoint:
- Gmail: `http://gmail-mcp-server:8080/health`
- Slack: `http://slack-mcp-server:8081/health`
- Graphiti: `http://graphiti-mcp-server:8082/health`
- RAG: `http://rag-mcp-server:8083/health`

## Configuration Process

### 1. Automatic Configuration

The configuration script automatically:
1. Tests connection to Letta server
2. Lists existing MCP servers
3. Adds new MCP servers (skips existing ones)
4. Tests each MCP server connection
5. Reports configuration status

### 2. Manual Configuration

If automatic configuration fails, you can manually configure MCP servers using:

#### Option A: Letta ADE (Agent Development Environment)
1. Access Letta web interface
2. Navigate to Tool Manager → Add MCP Server
3. Select "Streamable HTTP"
4. Configure each server with the appropriate URL

#### Option B: Letta API
```bash
# Add Gmail MCP server
curl -X PUT http://letta:8283/v1/tools/mcp/servers \
  -H "Content-Type: application/json" \
  -d '{
    "server_name": "gmail-tools",
    "type": "streamable_http",
    "server_url": "http://gmail-mcp-server:8080/mcp"
  }'
```

## Troubleshooting

### Common Issues

1. **Letta Server Not Ready**
   - Wait for Letta to fully start
   - Check Letta health endpoint: `curl http://letta:8283/v1/health/`

2. **MCP Server Not Accessible**
   - Verify MCP server is running: `docker ps | grep mcp`
   - Check MCP server health: `curl http://{server}:{port}/health`
   - Verify network connectivity within Docker

3. **Configuration Not Applied**
   - Check Letta logs for errors
   - Verify API endpoint accessibility
   - Test individual MCP server connections

### Debugging Commands

```bash
# Check Letta status
curl http://letta:8283/v1/health/

# List configured MCP servers
curl http://letta:8283/v1/tools/mcp/servers

# Test specific MCP server
curl -X POST http://letta:8283/v1/tools/mcp/servers/{server_name}/test

# Check Docker network connectivity
docker exec -it letta curl http://gmail-mcp-server:8080/health
```

## Security Considerations

### Network Security
- All MCP servers run on internal Docker network only
- No external port exposure
- Service-to-service communication via Docker DNS

### Authentication
- No authentication required for internal network communication
- MCP servers can implement their own authentication if needed
- Letta includes agent ID in request headers (`x-agent-id`)

## Monitoring and Maintenance

### Health Monitoring
- Monitor MCP server health endpoints
- Set up alerts for health check failures
- Track MCP server response times

### Log Monitoring
- Centralize logs from all MCP servers
- Monitor for connection errors
- Track tool usage and performance

### Regular Maintenance
- Update MCP server configurations as needed
- Monitor for new MCP server versions
- Review and update security settings

## Future Extensions

### Adding New MCP Servers
1. Add server configuration to `MCP_SERVERS` in `configure_mcp_servers.py`
2. Update port assignments if needed
3. Run configuration script
4. Test new server functionality

### Configuration Updates
1. Modify server configurations in the script
2. Re-run configuration script
3. Verify changes are applied
4. Test updated functionality

## References

- [Letta MCP Documentation](https://docs.letta.com/guides/mcp/)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Docker Networking](https://docs.docker.com/network/)
