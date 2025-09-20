# MCP Servers Documentation

This directory contains comprehensive documentation for all MCP (Model Context Protocol) servers in the PA (Personal Assistant) ecosystem.

## Overview

The PA ecosystem includes several MCP servers that provide specialized functionality through a standardized protocol. All servers follow consistent patterns for configuration, health monitoring, and integration.

## Documentation Structure

### Core Documentation
- **[User Guide](./user-guide.md)** - Complete user guide for MCP servers
- **[API Reference](./api-reference.md)** - Comprehensive API documentation
- **[Troubleshooting Guide](./troubleshooting.md)** - Common issues and solutions
- **[Operational Procedures](./operations.md)** - Deployment, monitoring, and maintenance
- **[Security Guide](./security.md)** - Security best practices and procedures
- **[Deployment Guide](./deployment.md)** - Installation and configuration

### Service-Specific Documentation
- **[Gmail MCP Server](./gmail-mcp-server.md)** - Gmail integration tools
- **[Graphiti MCP Server](./graphiti-mcp-server.md)** - Knowledge graph and memory tools
- **[RAG MCP Server](./rag-mcp-server.md)** - Retrieval-augmented generation tools
- **[Health Monitor](./health-monitor.md)** - Health monitoring and alerting system

### Integration Documentation
- **[Letta Integration](./letta-integration.md)** - Letta MCP server integration
- **[Workflow Examples](./workflow-examples.md)** - Common workflow patterns
- **[Development Guide](./development.md)** - Development and contribution guidelines

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Node.js 20+ (for development)
- Basic understanding of MCP protocol

### Getting Started
1. **Deploy Services**: Follow the [Deployment Guide](./deployment.md)
2. **Configure Letta**: See [Letta Integration](./letta-integration.md)
3. **Monitor Health**: Use the [Health Monitor](./health-monitor.md)
4. **Start Using Tools**: Check the [User Guide](./user-guide.md)

### Quick Commands
```bash
# Start all MCP servers
docker-compose up -d

# Check health status
./scripts/health-check-all.sh

# Run validation tests
./scripts/run-mcp-validation.sh

# View monitoring dashboard
open http://localhost:8083/dashboard
```

## Architecture

### MCP Servers
- **Gmail MCP Server** (Port 8080) - Email management tools
- **Graphiti MCP Server** (Port 8082) - Knowledge graph and memory tools
- **RAG MCP Server** (Port 8082) - Document retrieval and search tools
- **Health Monitor** (Port 8083) - Health monitoring and alerting

### Integration Points
- **Letta Integration** - Primary MCP client
- **Health Monitoring** - Centralized health management
- **Docker Network** - Internal service communication

## Key Features

### Standardized Configuration
- Consistent environment variables
- Standardized health check endpoints
- Unified logging and monitoring
- Common security patterns

### Health Monitoring
- Real-time health status
- Automated alerting
- Performance metrics
- Web dashboard

### Tool Integration
- 17+ available tools across all servers
- Consistent tool interface
- Error handling and recovery
- Session management

## Support

### Getting Help
1. **Check Documentation**: Start with the [User Guide](./user-guide.md)
2. **Troubleshooting**: See the [Troubleshooting Guide](./troubleshooting.md)
3. **API Reference**: Consult the [API Reference](./api-reference.md)
4. **Health Status**: Check the [Health Monitor](./health-monitor.md)

### Common Issues
- **Service Not Starting**: Check [Deployment Guide](./deployment.md)
- **Connection Issues**: See [Troubleshooting Guide](./troubleshooting.md)
- **Tool Errors**: Check [API Reference](./api-reference.md)
- **Performance Issues**: See [Operations Guide](./operations.md)

## Contributing

### Development
- See [Development Guide](./development.md) for setup
- Follow [Contributing Guidelines](./contributing.md)
- Run tests before submitting changes

### Documentation
- Keep documentation up-to-date
- Add examples and use cases
- Test all procedures and examples

## Version Information

- **MCP Protocol Version**: 1.0.0
- **Gmail MCP Server**: 1.1.11
- **Graphiti MCP Server**: 1.0.0
- **RAG MCP Server**: 1.0.0
- **Health Monitor**: 1.0.0

## License

This documentation is part of the PA ecosystem and follows the same license terms.

---

*Last updated: 2025-01-20*
*For the latest updates, check the [changelog](./changelog.md)*
