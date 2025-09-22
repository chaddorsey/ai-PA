# MCP Servers API Reference

## Overview

This document provides comprehensive API reference for all MCP servers in the PA ecosystem. All servers follow the Model Context Protocol (MCP) specification and provide standardized JSON-RPC interfaces.

## Common API Patterns

### Base URL Structure
- **Gmail MCP Server**: `http://gmail-mcp-server:8080`
- **Graphiti MCP Server**: `http://graphiti-mcp-server:8082`
- **RAG MCP Server**: `http://rag-mcp-server:8082`
- **Health Monitor**: `http://health-monitor:8083`

### JSON-RPC Format
All MCP servers use JSON-RPC 2.0 format:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "method_name",
  "params": {
    "param1": "value1",
    "param2": "value2"
  }
}
```

### Response Format
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "data": "response_data"
  }
}
```

### Error Format
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32601,
    "message": "Method not found",
    "data": {
      "method": "invalid_method"
    }
  }
}
```

## Gmail MCP Server API

### Base URL
`http://gmail-mcp-server:8080`

### Health Endpoint
**GET** `/health`

Returns server health status.

**Response**:
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

### MCP Endpoint
**POST** `/mcp`

Main MCP protocol endpoint.

### Available Tools

#### 1. search_emails
Search for emails with various criteria.

**Parameters**:
```json
{
  "query": "string (required) - Gmail search query",
  "max_results": "number (optional) - Maximum number of results (default: 10)",
  "label_ids": "array (optional) - Label IDs to search in",
  "include_spam_trash": "boolean (optional) - Include spam/trash (default: false)"
}
```

**Example**:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "search_emails",
    "arguments": {
      "query": "from:example@email.com",
      "max_results": 20,
      "label_ids": ["INBOX", "IMPORTANT"]
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"emails\": [{\"id\": \"email_123\", \"subject\": \"Test Email\", \"from\": \"example@email.com\", \"date\": \"2025-01-20T10:00:00Z\", \"snippet\": \"Email content...\"}], \"total\": 1}"
      }
    ]
  }
}
```

#### 2. send_email
Send an email with optional attachments.

**Parameters**:
```json
{
  "to": "string (required) - Recipient email address",
  "subject": "string (required) - Email subject",
  "body": "string (required) - Email body",
  "cc": "string (optional) - CC recipients",
  "bcc": "string (optional) - BCC recipients",
  "attachments": "array (optional) - Attachment file paths"
}
```

**Example**:
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "send_email",
    "arguments": {
      "to": "recipient@example.com",
      "subject": "Test Email",
      "body": "This is a test email.",
      "cc": "cc@example.com"
    }
  }
}
```

#### 3. get_labels
Retrieve Gmail labels.

**Parameters**:
```json
{
  "user_id": "string (optional) - User ID (default: 'me')"
}
```

#### 4. create_label
Create a new Gmail label.

**Parameters**:
```json
{
  "name": "string (required) - Label name",
  "label_list_visibility": "string (optional) - Label visibility (default: 'labelShow')",
  "message_list_visibility": "string (optional) - Message visibility (default: 'show')"
}
```

#### 5. delete_label
Delete a Gmail label.

**Parameters**:
```json
{
  "label_id": "string (required) - Label ID to delete"
}
```

## Graphiti MCP Server API

### Base URL
`http://graphiti-mcp-server:8082`

### Health Endpoint
**GET** `/health`

Returns server health status.

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-20T21:00:00.000Z",
  "service": "graphiti-tools",
  "version": "1.0.0",
  "uptime": 1800.2,
  "dependencies": {
    "neo4j": "healthy",
    "openai_api": "healthy",
    "external_apis": "healthy"
  },
  "responseTime": 200
}
```

### Available Tools

#### 1. add_memory
Add a new memory to the knowledge graph.

**Parameters**:
```json
{
  "content": "string (required) - Memory content",
  "metadata": "object (optional) - Additional metadata",
  "importance": "number (optional) - Importance score (0-1)",
  "tags": "array (optional) - Memory tags"
}
```

**Example**:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "add_memory",
    "arguments": {
      "content": "User prefers morning meetings",
      "metadata": {
        "category": "preferences",
        "source": "calendar"
      },
      "importance": 0.8,
      "tags": ["preferences", "meetings"]
    }
  }
}
```

#### 2. search_memories
Search for memories by content.

**Parameters**:
```json
{
  "query": "string (required) - Search query",
  "limit": "number (optional) - Maximum results (default: 10)",
  "threshold": "number (optional) - Similarity threshold (0-1, default: 0.7)",
  "tags": "array (optional) - Filter by tags"
}
```

#### 3. get_memory
Retrieve a specific memory by ID.

**Parameters**:
```json
{
  "memory_id": "string (required) - Memory ID"
}
```

#### 4. update_memory
Update an existing memory.

**Parameters**:
```json
{
  "memory_id": "string (required) - Memory ID",
  "content": "string (optional) - New content",
  "metadata": "object (optional) - New metadata",
  "importance": "number (optional) - New importance score"
}
```

#### 5. delete_memory
Delete a memory.

**Parameters**:
```json
{
  "memory_id": "string (required) - Memory ID"
}
```

#### 6. clear_memories
Clear all memories.

**Parameters**:
```json
{
  "confirm": "boolean (required) - Confirmation flag"
}
```

#### 7. get_status
Get server status and statistics.

**Parameters**: None

#### 8. get_health
Get detailed health information.

**Parameters**: None

## RAG MCP Server API

### Base URL
`http://rag-mcp-server:8082`

### Health Endpoint
**GET** `/health`

Returns server health status.

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-20T21:00:00.000Z",
  "service": "rag-tools",
  "version": "1.0.0",
  "uptime": 900.1,
  "dependencies": {
    "vector_database": "healthy",
    "document_store": "healthy",
    "external_apis": "healthy"
  },
  "responseTime": 100
}
```

### Available Tools

#### 1. search_documents
Search for documents using text-based queries.

**Parameters**:
```json
{
  "query": "string (required) - Search query",
  "limit": "number (optional) - Maximum results (default: 10)",
  "collection": "string (optional) - Document collection (default: 'default')"
}
```

**Example**:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "search_documents",
    "arguments": {
      "query": "machine learning algorithms",
      "limit": 5,
      "collection": "research_papers"
    }
  }
}
```

#### 2. retrieve_document
Retrieve a specific document by ID.

**Parameters**:
```json
{
  "document_id": "string (required) - Document ID",
  "collection": "string (optional) - Document collection"
}
```

#### 3. index_document
Index a new document for future retrieval.

**Parameters**:
```json
{
  "content": "string (required) - Document content",
  "metadata": "object (optional) - Document metadata",
  "collection": "string (optional) - Document collection (default: 'default')"
}
```

#### 4. query_vector
Query documents using vector similarity search.

**Parameters**:
```json
{
  "query": "string (required) - Query text",
  "limit": "number (optional) - Maximum results (default: 10)",
  "threshold": "number (optional) - Similarity threshold (0-1, default: 0.7)"
}
```

## Health Monitor API

### Base URL
`http://health-monitor:8083`

### Health Endpoint
**GET** `/health`

Returns health monitor service status.

### API Endpoints

#### 1. Overall Health
**GET** `/api/health/overall`

Returns overall health status of all MCP servers.

**Response**:
```json
{
  "overall": "healthy",
  "services": {
    "gmail-mcp-server": {
      "status": "healthy",
      "timestamp": "2025-01-20T21:00:00.000Z",
      "service": "gmail-mcp-server",
      "version": "1.1.11",
      "uptime": 3600.5,
      "dependencies": {
        "gmail_api": "healthy",
        "external_apis": "healthy"
      },
      "responseTime": 150
    }
  },
  "timestamp": "2025-01-20T21:00:00.000Z",
  "totalServices": 3,
  "healthyServices": 3,
  "unhealthyServices": 0,
  "degradedServices": 0
}
```

#### 2. Service Health
**GET** `/api/health/service/{serviceName}`

Returns health status for a specific service.

**Parameters**:
- `serviceName` (path) - Name of the service

#### 3. Health History
**GET** `/api/health/history/{serviceName}`

Returns health history for a specific service.

**Parameters**:
- `serviceName` (path) - Name of the service

#### 4. Alerts
**GET** `/api/alerts`

Returns all alerts.

**Query Parameters**:
- `service` (optional) - Filter by service name
- `resolved` (optional) - Filter by resolution status

#### 5. Resolve Alert
**POST** `/api/alerts/{alertId}/resolve`

Resolves a specific alert.

**Parameters**:
- `alertId` (path) - ID of the alert to resolve

#### 6. Services
**GET** `/api/services`

Returns configuration of all monitored services.

#### 7. Dashboard
**GET** `/dashboard`

Returns the monitoring dashboard HTML page.

## Error Codes

### JSON-RPC Error Codes
- `-32700` - Parse error
- `-32600` - Invalid Request
- `-32601` - Method not found
- `-32602` - Invalid params
- `-32603` - Internal error

### Custom Error Codes
- `-32000` - Service unavailable
- `-32001` - Authentication failed
- `-32002` - Rate limit exceeded
- `-32003` - Tool execution failed
- `-32004` - Invalid tool arguments

## Rate Limits

### Default Limits
- **Gmail MCP**: 100 requests/minute
- **Graphiti MCP**: 200 requests/minute
- **RAG MCP**: 150 requests/minute
- **Health Monitor**: 500 requests/minute

### Rate Limit Headers
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640995200
```

## Authentication

### API Keys
Some endpoints may require API keys:

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  http://localhost:8080/mcp
```

### Session Management
MCP servers support session-based authentication:

```bash
curl -H "mcp-session-id: session-123" \
  -X POST http://localhost:8080/mcp
```

## WebSocket Support

### Connection
Connect to WebSocket for real-time updates:

```javascript
const ws = new WebSocket('ws://localhost:8083');
ws.onmessage = function(event) {
  const data = JSON.parse(event.data);
  console.log('Health update:', data);
};
```

### Message Format
WebSocket messages follow the same format as REST API responses.

## SDK Examples

### JavaScript/Node.js
```javascript
const axios = require('axios');

async function callMCPTool(serverUrl, toolName, args) {
  try {
    const response = await axios.post(`${serverUrl}/mcp`, {
      jsonrpc: '2.0',
      id: 1,
      method: 'tools/call',
      params: {
        name: toolName,
        arguments: args
      }
    });
    return response.data.result;
  } catch (error) {
    console.error('MCP tool call failed:', error.response.data);
    throw error;
  }
}

// Example usage
const result = await callMCPTool('http://localhost:8080', 'search_emails', {
  query: 'from:example@email.com',
  max_results: 10
});
```

### Python
```python
import requests
import json

def call_mcp_tool(server_url, tool_name, args):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": args
        }
    }
    
    response = requests.post(f"{server_url}/mcp", json=payload)
    response.raise_for_status()
    return response.json()["result"]

# Example usage
result = call_mcp_tool("http://localhost:8080", "search_emails", {
    "query": "from:example@email.com",
    "max_results": 10
})
```

### cURL Examples
```bash
# Search emails
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

# Add memory
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
        "metadata": {"category": "preferences"}
      }
    }
  }'

# Search documents
curl -X POST http://localhost:8082/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "search_documents",
      "arguments": {
        "query": "machine learning",
        "limit": 5
      }
    }
  }'
```

## Testing

### Health Check
```bash
# Check individual service health
curl http://localhost:8080/health
curl http://localhost:8082/health
curl http://localhost:8083/health

# Check overall health
curl http://localhost:8083/api/health/overall
```

### Tool Discovery
```bash
# List available tools
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'
```

### Validation Scripts
```bash
# Run comprehensive validation
./scripts/run-mcp-validation.sh

# Run specific validations
./scripts/validate-mcp-health.sh
./scripts/validate-mcp-protocol.sh
./scripts/validate-letta-mcp-connection.sh
```

---

*For more information, see the [User Guide](./user-guide.md) and [Troubleshooting Guide](./troubleshooting.md).*

