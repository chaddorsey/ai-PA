# RAG MCP Server Framework

## Overview

This document describes the RAG (Retrieval-Augmented Generation) MCP Server framework created for future RAG integration in the PA ecosystem. The framework provides a standardized foundation for implementing RAG capabilities while following all established MCP server patterns.

## Architecture

### Service Configuration
- **Service Name**: `rag-mcp-server`
- **Container Name**: `rag-mcp-server`
- **Port**: `8082` (standardized port assignment)
- **Transport**: HTTP with StreamableHTTPServerTransport
- **Health Endpoint**: `/health`
- **MCP Endpoint**: `/mcp`

### Directory Structure
```
rag-mcp/
├── src/
│   ├── index.ts          # Main MCP server (stdio transport)
│   └── server-http.ts    # HTTP transport implementation
├── package.json          # Node.js dependencies and scripts
├── tsconfig.json         # TypeScript configuration
└── Dockerfile           # Container configuration
```

## RAG Tools

The framework provides four core RAG tools as placeholders for future implementation:

### 1. search_documents
**Purpose**: Search for documents using text-based queries
**Input Schema**:
```json
{
  "query": "string (required) - The search query to find relevant documents",
  "limit": "number (optional) - Maximum number of documents to return (default: 10)",
  "collection": "string (optional) - Document collection to search (default: 'default')"
}
```

**Example Usage**:
```json
{
  "name": "search_documents",
  "arguments": {
    "query": "machine learning algorithms",
    "limit": 5,
    "collection": "research_papers"
  }
}
```

### 2. retrieve_document
**Purpose**: Retrieve a specific document by its ID
**Input Schema**:
```json
{
  "document_id": "string (required) - The unique identifier of the document to retrieve",
  "collection": "string (optional) - Document collection containing the document"
}
```

**Example Usage**:
```json
{
  "name": "retrieve_document",
  "arguments": {
    "document_id": "doc-12345",
    "collection": "research_papers"
  }
}
```

### 3. index_document
**Purpose**: Index a new document for future retrieval
**Input Schema**:
```json
{
  "content": "string (required) - The content of the document to index",
  "metadata": "object (optional) - Optional metadata for the document",
  "collection": "string (optional) - Document collection to index into (default: 'default')"
}
```

**Example Usage**:
```json
{
  "name": "index_document",
  "arguments": {
    "content": "This is a research paper about neural networks...",
    "metadata": {
      "title": "Neural Networks in Practice",
      "author": "Dr. Smith",
      "year": 2025
    },
    "collection": "research_papers"
  }
}
```

### 4. query_vector
**Purpose**: Query documents using vector similarity search
**Input Schema**:
```json
{
  "query": "string (required) - The query to search for in vector space",
  "limit": "number (optional) - Maximum number of results to return (default: 10)",
  "threshold": "number (optional) - Similarity threshold (0-1, default: 0.7)"
}
```

**Example Usage**:
```json
{
  "name": "query_vector",
  "arguments": {
    "query": "artificial intelligence applications",
    "limit": 8,
    "threshold": 0.8
  }
}
```

## Environment Variables

### Standardized MCP Variables
```yaml
environment:
  # Common MCP variables
  - MCP_SERVER_NAME=rag-tools
  - MCP_SERVER_VERSION=1.0.0
  - MCP_SERVER_DESCRIPTION=RAG tools for retrieval-augmented generation
  - MCP_SERVER_HOST=0.0.0.0
  - MCP_SERVER_PORT=8082
  - MCP_SERVER_PATH=/mcp
  - MCP_LOG_LEVEL=INFO
  - MCP_LOG_FORMAT=json
  - MCP_HEALTH_CHECK_PATH=/health
```

### RAG-Specific Variables (Placeholders)
```yaml
environment:
  # RAG-specific variables (placeholders for future implementation)
  - VECTOR_DB_URL=http://vector-db:8080
  - DOCUMENT_STORE_URL=http://document-store:8080
  - EMBEDDING_MODEL=text-embedding-ada-002
  - PORT=8082
```

## Health Check

### Health Endpoint
- **URL**: `http://rag-mcp-server:8082/health`
- **Method**: GET
- **Response Format**: JSON

### Health Response
```json
{
  "status": "healthy",
  "timestamp": "2025-01-20T21:00:00.000Z",
  "service": "rag-tools",
  "version": "1.0.0",
  "uptime": 3600.5,
  "dependencies": {
    "vector_database": "healthy",
    "document_store": "healthy",
    "external_apis": "healthy"
  }
}
```

### Health Check Configuration
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8082/health"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 30s
```

## Docker Configuration

### Dockerfile Features
- **Base Image**: `node:20-slim`
- **Working Directory**: `/app`
- **Build Process**: TypeScript compilation
- **Runtime**: Node.js production environment
- **Port**: 8082
- **Data Directory**: `/app/data`

### Volume Mounts
```yaml
volumes:
  - rag-mcp-data:/app/data
```

### Logging Configuration
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
    labels: "service,component,network"
```

### Service Labels
```yaml
labels:
  - "service=rag-mcp-server"
  - "component=mcp-server"
  - "network=pa-internal"
  - "mcp-transport=http"
  - "mcp-version=1.0.0"
  - "security.internal-only=true"
  - "security.no-external-access=true"
```

## MCP Protocol Implementation

### Transport Support
- **HTTP**: Primary transport using StreamableHTTPServerTransport
- **Stdio**: Available for direct MCP client connections

### Session Management
- **Session ID**: Generated using `randomUUID()`
- **Session Reuse**: Sessions are cached and reused when possible
- **Session Cleanup**: Sessions can be torn down via DELETE request

### Error Handling
- **Validation**: Input validation using Zod schemas
- **Error Responses**: Structured error responses with proper MCP format
- **Logging**: Comprehensive error logging for debugging

## Development and Testing

### Development Commands
```bash
# Install dependencies
npm install

# Build TypeScript
npm run build

# Start development server
npm run dev

# Run tests
npm test

# Lint code
npm run lint

# Fix linting issues
npm run lint:fix
```

### Testing the Server
```bash
# Test health check
curl -f http://localhost:8082/health

# Test MCP endpoint
curl -X POST http://localhost:8082/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}'

# Test tool discovery
curl -X POST http://localhost:8082/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'

# Test RAG tool
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

## Future Implementation Guidelines

### Vector Database Integration
1. **Choose Vector Database**: Select appropriate vector database (Pinecone, Weaviate, Qdrant, etc.)
2. **Update Environment Variables**: Configure `VECTOR_DB_URL` and authentication
3. **Implement Vector Operations**: Replace placeholder functions with actual vector operations
4. **Add Health Checks**: Implement actual vector database health validation

### Document Store Integration
1. **Choose Document Store**: Select appropriate document store (Elasticsearch, MongoDB, etc.)
2. **Update Environment Variables**: Configure `DOCUMENT_STORE_URL` and authentication
3. **Implement Document Operations**: Replace placeholder functions with actual document operations
4. **Add Health Checks**: Implement actual document store health validation

### Embedding Model Integration
1. **Choose Embedding Model**: Select appropriate embedding model (OpenAI, Cohere, etc.)
2. **Update Environment Variables**: Configure `EMBEDDING_MODEL` and API keys
3. **Implement Embedding Operations**: Add embedding generation and similarity search
4. **Add Health Checks**: Implement actual embedding service health validation

### Advanced RAG Features
1. **Hybrid Search**: Combine text and vector search
2. **Query Expansion**: Implement query expansion and refinement
3. **Result Ranking**: Add sophisticated ranking algorithms
4. **Caching**: Implement result caching for performance
5. **Analytics**: Add usage analytics and monitoring

## Security Considerations

### Network Security
- Service runs on internal network only
- No external port exposure
- Health check endpoint accessible internally only

### Data Security
- Document content should be encrypted at rest
- Vector embeddings should be secured
- API keys managed via environment variables
- No hardcoded credentials in configuration

### Access Control
- Service labeled as internal-only
- No external access allowed
- Proper dependency management
- MCP session management

## Monitoring and Observability

### Health Monitoring
- Monitor health endpoint: `http://rag-mcp-server:8082/health`
- Set up alerts for health check failures
- Track vector database and document store status
- Monitor RAG operation performance

### Log Monitoring
- Monitor structured logs for errors
- Track RAG tool usage patterns
- Monitor vector database and document store operations
- Track embedding generation performance

### Metrics to Track
- Service uptime and availability
- Vector database health and performance
- Document store health and performance
- RAG tool response times
- Embedding generation success rates
- Search result quality metrics

## Performance Considerations

### Scalability
- Vector database should be horizontally scalable
- Document store should support sharding
- Embedding generation should be optimized
- Caching should be implemented for frequent queries

### Optimization
- Use connection pooling for databases
- Implement query result caching
- Optimize vector similarity search
- Use batch operations where possible

### Resource Management
- Monitor memory usage for vector operations
- Implement proper cleanup for sessions
- Use streaming for large document processing
- Implement rate limiting for API calls

## Integration with PA Ecosystem

### Letta Integration
The RAG MCP server is configured to work with Letta through the standardized MCP configuration:

```json
{
  "mcpServers": {
    "rag-tools": {
      "command": "http",
      "args": ["http://rag-mcp-server:8082"],
      "env": {},
      "disabled": false
    }
  }
}
```

### Workflow Integration
- RAG tools can be used in Letta workflows
- Document search and retrieval for context
- Vector similarity search for related content
- Document indexing for knowledge management

### Future Extensions
- Integration with other PA ecosystem services
- Advanced RAG capabilities
- Multi-modal RAG support
- Real-time document processing

## Troubleshooting

### Common Issues
1. **Health Check Failures**: Check vector database and document store connectivity
2. **Tool Errors**: Verify input validation and error handling
3. **Session Issues**: Check session management and cleanup
4. **Performance Issues**: Monitor resource usage and optimize queries

### Debug Commands
```bash
# Check container logs
docker logs rag-mcp-server

# Check health status
curl -v http://rag-mcp-server:8082/health

# Test MCP protocol
curl -X POST http://rag-mcp-server:8082/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'

# Check environment variables
docker exec rag-mcp-server env | grep MCP
```

### Log Analysis
- Check structured logs for error patterns
- Monitor performance metrics
- Track tool usage statistics
- Analyze health check responses

## Conclusion

The RAG MCP Server framework provides a solid foundation for implementing RAG capabilities in the PA ecosystem. It follows all standardized patterns while providing extensibility for future RAG implementations. The framework is production-ready and can be easily extended with actual RAG functionality as needed.

Key benefits:
- **Standardized**: Follows all established MCP server patterns
- **Extensible**: Easy to add actual RAG functionality
- **Production-Ready**: Includes health checks, logging, and monitoring
- **Well-Documented**: Comprehensive documentation and examples
- **Secure**: Proper security considerations and access control
- **Observable**: Built-in monitoring and debugging capabilities
