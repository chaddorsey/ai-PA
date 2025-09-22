# MCP Servers User Guide

## Overview

This guide provides comprehensive instructions for using MCP (Model Context Protocol) servers in the PA ecosystem. MCP servers provide specialized tools and functionality through a standardized protocol that can be accessed by AI agents like Letta.

## What are MCP Servers?

MCP servers are specialized services that expose tools and resources through the Model Context Protocol. They allow AI agents to:

- **Access External Services**: Connect to Gmail, knowledge graphs, and document stores
- **Perform Complex Operations**: Execute multi-step workflows and data processing
- **Maintain State**: Store and retrieve information across sessions
- **Integrate Seamlessly**: Work together through standardized interfaces

## Available MCP Servers

### 1. Gmail MCP Server
**Purpose**: Email management and Gmail integration
**Port**: 8080
**Tools**: 5 tools for email operations

**Available Tools**:
- `search_emails` - Search for emails with various criteria
- `send_email` - Send emails with attachments
- `get_labels` - Retrieve Gmail labels
- `create_label` - Create new Gmail labels
- `delete_label` - Delete Gmail labels

### 2. Graphiti MCP Server
**Purpose**: Knowledge graph and memory management
**Port**: 8082
**Tools**: 8 tools for memory operations

**Available Tools**:
- `add_memory` - Add new memories to the knowledge graph
- `search_memories` - Search for memories by content
- `get_memory` - Retrieve specific memories
- `update_memory` - Update existing memories
- `delete_memory` - Delete memories
- `clear_memories` - Clear all memories
- `get_status` - Get server status
- `get_health` - Get health information

### 3. RAG MCP Server
**Purpose**: Document retrieval and search
**Port**: 8082
**Tools**: 4 tools for document operations

**Available Tools**:
- `search_documents` - Search documents by text
- `retrieve_document` - Retrieve specific documents
- `index_document` - Index new documents
- `query_vector` - Vector similarity search

### 4. Health Monitor
**Purpose**: System health monitoring and alerting
**Port**: 8083
**Features**: Real-time monitoring, alerting, dashboard

## Getting Started

### Prerequisites
- Docker and Docker Compose installed
- Basic understanding of MCP protocol
- Access to the PA ecosystem

### Starting the Services

1. **Start All Services**:
   ```bash
   docker-compose up -d
   ```

2. **Check Service Status**:
   ```bash
   ./scripts/health-check-all.sh
   ```

3. **View Monitoring Dashboard**:
   Open http://localhost:8083/dashboard in your browser

### Verifying Installation

1. **Check Health Status**:
   ```bash
   curl http://localhost:8080/health  # Gmail MCP
   curl http://localhost:8082/health  # Graphiti MCP
   curl http://localhost:8082/health  # RAG MCP
   curl http://localhost:8083/health  # Health Monitor
   ```

2. **Test Tool Discovery**:
   ```bash
   curl -X POST http://localhost:8080/mcp \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'
   ```

## Using MCP Tools

### Basic Tool Usage

MCP tools are accessed through JSON-RPC requests. Here's the basic pattern:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "tool_name",
    "arguments": {
      "param1": "value1",
      "param2": "value2"
    }
  }
}
```

### Example: Searching Emails

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "search_emails",
      "arguments": {
        "query": "from:example@email.com",
        "max_results": 10
      }
    }
  }'
```

### Example: Adding a Memory

```bash
curl -X POST http://localhost:8082/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "add_memory",
      "arguments": {
        "content": "User prefers morning meetings",
        "metadata": {
          "category": "preferences",
          "importance": "high"
        }
      }
    }
  }'
```

### Example: Searching Documents

```bash
curl -X POST http://localhost:8082/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "search_documents",
      "arguments": {
        "query": "machine learning algorithms",
        "limit": 5
      }
    }
  }'
```

## Working with Letta

### Letta Integration

Letta automatically discovers and connects to MCP servers. The configuration is managed in `letta/letta_mcp_config.json`:

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
      "args": ["http://graphiti-mcp-server:8082"],
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

### Using Tools in Letta

Once configured, you can use MCP tools directly in Letta conversations:

```
User: "Search for emails from john@example.com"
Letta: I'll search for emails from john@example.com using the Gmail tools.

[Uses search_emails tool with query="from:john@example.com"]

I found 5 emails from john@example.com. Here are the most recent ones:
- Subject: Project Update (2 hours ago)
- Subject: Meeting Tomorrow (1 day ago)
- Subject: Budget Review (3 days ago)
```

## Common Workflows

### 1. Email Management Workflow

```python
# Search for important emails
search_result = call_tool("search_emails", {
    "query": "is:important",
    "max_results": 20
})

# Process each email
for email in search_result["emails"]:
    # Add to memory if important
    if email["importance"] > 0.8:
        call_tool("add_memory", {
            "content": f"Important email: {email['subject']}",
            "metadata": {
                "source": "gmail",
                "email_id": email["id"],
                "date": email["date"]
            }
        })
```

### 2. Knowledge Management Workflow

```python
# Search for relevant memories
memories = call_tool("search_memories", {
    "query": "project requirements",
    "limit": 10
})

# Search for related documents
documents = call_tool("search_documents", {
    "query": "project requirements",
    "limit": 5
})

# Combine information
combined_info = {
    "memories": memories["results"],
    "documents": documents["documents"]
}
```

### 3. Document Processing Workflow

```python
# Index a new document
index_result = call_tool("index_document", {
    "content": "Project requirements document...",
    "metadata": {
        "title": "Project Requirements",
        "author": "John Doe",
        "date": "2025-01-20"
    }
})

# Search for similar documents
similar_docs = call_tool("query_vector", {
    "query": "project requirements",
    "limit": 5,
    "threshold": 0.8
})
```

## Monitoring and Health

### Health Check Endpoints

Each MCP server provides a health endpoint:

- **Gmail MCP**: http://localhost:8080/health
- **Graphiti MCP**: http://localhost:8082/health
- **RAG MCP**: http://localhost:8082/health
- **Health Monitor**: http://localhost:8083/health

### Health Response Format

```json
{
  "status": "healthy",
  "timestamp": "2025-01-20T21:00:00.000Z",
  "service": "gmail-tools",
  "version": "1.1.11",
  "uptime": 3600.5,
  "dependencies": {
    "gmail_api": "healthy",
    "external_apis": "healthy"
  },
  "responseTime": 150
}
```

### Monitoring Dashboard

Access the monitoring dashboard at http://localhost:8083/dashboard to:

- View real-time health status of all services
- Monitor response times and performance
- Check for alerts and issues
- View service metrics and statistics

## Error Handling

### Common Error Types

1. **Service Unavailable**: MCP server is not running
2. **Tool Not Found**: Requested tool doesn't exist
3. **Invalid Arguments**: Tool arguments are incorrect
4. **Authentication Error**: Missing or invalid credentials
5. **Rate Limit Exceeded**: Too many requests

### Error Response Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32601,
    "message": "Method not found",
    "data": {
      "method": "invalid_tool"
    }
  }
}
```

### Handling Errors

```python
try:
    result = call_tool("search_emails", {"query": "test"})
except ToolError as e:
    if e.code == -32601:
        print("Tool not found")
    elif e.code == -32602:
        print("Invalid arguments")
    else:
        print(f"Error: {e.message}")
```

## Best Practices

### 1. Tool Usage
- Always validate tool arguments before calling
- Handle errors gracefully
- Use appropriate timeouts
- Cache results when possible

### 2. Memory Management
- Use meaningful memory content
- Add relevant metadata
- Regularly clean up old memories
- Use consistent categorization

### 3. Performance
- Batch operations when possible
- Use appropriate limits for searches
- Monitor response times
- Implement retry logic for failures

### 4. Security
- Never expose credentials in logs
- Use environment variables for sensitive data
- Validate all inputs
- Follow principle of least privilege

## Troubleshooting

### Common Issues

1. **Service Won't Start**
   - Check Docker logs: `docker logs gmail-mcp-server`
   - Verify environment variables
   - Check port availability

2. **Tool Calls Failing**
   - Verify tool name and arguments
   - Check service health status
   - Review error messages

3. **Slow Performance**
   - Check resource usage
   - Review response times
   - Consider scaling options

4. **Connection Issues**
   - Verify network connectivity
   - Check firewall settings
   - Validate service URLs

### Debug Commands

```bash
# Check service status
docker ps | grep mcp

# View service logs
docker logs gmail-mcp-server
docker logs graphiti-mcp-server
docker logs rag-mcp-server
docker logs health-monitor

# Test health endpoints
curl http://localhost:8080/health
curl http://localhost:8082/health
curl http://localhost:8083/health

# Run validation tests
./scripts/run-mcp-validation.sh
```

## Advanced Usage

### Custom Tool Development

To add custom tools to an MCP server:

1. **Define Tool Schema**:
   ```typescript
   const CustomToolSchema = z.object({
     param1: z.string().describe("Description of param1"),
     param2: z.number().optional().describe("Description of param2")
   });
   ```

2. **Implement Tool Handler**:
   ```typescript
   async function handleCustomTool(args: z.infer<typeof CustomToolSchema>) {
     // Tool implementation
     return { result: "success" };
   }
   ```

3. **Register Tool**:
   ```typescript
   server.setRequestHandler(CallToolRequestSchema, async (request) => {
     // Add tool handling logic
   });
   ```

### Session Management

MCP servers support session management for stateful operations:

```bash
# Start a session
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "mcp-session-id: session-123" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}'

# Use session for subsequent calls
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "mcp-session-id: session-123" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {...}}'
```

## Support and Resources

### Documentation
- [API Reference](./api-reference.md) - Complete API documentation
- [Troubleshooting Guide](./troubleshooting.md) - Common issues and solutions
- [Operational Procedures](./operations.md) - Deployment and maintenance

### Tools and Scripts
- `scripts/health-check-all.sh` - Health validation
- `scripts/run-mcp-validation.sh` - Comprehensive testing
- `scripts/validate-mcp-protocol.sh` - Protocol validation

### Monitoring
- Health Dashboard: http://localhost:8083/dashboard
- Health API: http://localhost:8083/api/health
- Service Logs: `docker logs <service-name>`

---

*For more detailed information, see the [API Reference](./api-reference.md) and [Troubleshooting Guide](./troubleshooting.md).*

