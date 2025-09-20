# Health Monitoring System for MCP Servers

## Overview

This document describes the comprehensive health monitoring system implemented for all MCP servers in the PA ecosystem. The system provides real-time health status, alerting, and monitoring capabilities to ensure reliable operation of all MCP services.

## Architecture

### Health Monitor Service
- **Service Name**: `health-monitor`
- **Container Name**: `health-monitor`
- **Port**: `8083` (exposed for external access)
- **Dashboard**: `http://localhost:8083/dashboard`
- **API**: `http://localhost:8083/api/health`
- **WebSocket**: `ws://localhost:8083`

### Monitored Services
- **Gmail MCP Server**: `gmail-mcp-server:8080`
- **Graphiti MCP Server**: `graphiti-mcp-server:8082`
- **RAG MCP Server**: `rag-mcp-server:8082`

## Features

### 1. Real-Time Health Monitoring
- Continuous health checks every 30 seconds
- Real-time WebSocket updates to connected clients
- Individual service health status tracking
- Overall system health aggregation

### 2. Health Check Endpoints
- **Individual Service Health**: `/api/health/service/{serviceName}`
- **Overall Health**: `/api/health/overall`
- **Health History**: `/api/health/history/{serviceName}`
- **Service List**: `/api/services`

### 3. Alerting System
- **Failure Detection**: Automatic detection of service failures
- **Recovery Notifications**: Alerts when services recover
- **Performance Degradation**: Warnings for slow response times
- **Alert Management**: API for resolving and managing alerts

### 4. Web Dashboard
- **Real-Time Status**: Live updates of all service statuses
- **Visual Indicators**: Color-coded health status
- **Metrics Display**: Response times, uptime, and error rates
- **Auto-Refresh**: Automatic updates every 30 seconds

## Health Check Implementation

### Standardized Health Response Format
All MCP servers return health information in a standardized JSON format:

```json
{
  "status": "healthy|unhealthy|degraded",
  "timestamp": "2025-01-20T21:00:00.000Z",
  "service": "service-name",
  "version": "1.0.0",
  "uptime": 3600.5,
  "dependencies": {
    "database": "healthy",
    "external_api": "healthy"
  },
  "responseTime": 150,
  "error": "Optional error message"
}
```

### Health Check Configuration
Each MCP server is configured with:
- **URL**: Service endpoint for health checks
- **Port**: Service port
- **Path**: Health check endpoint path (`/health`)
- **Timeout**: Maximum time to wait for response (5 seconds)
- **Retries**: Number of retry attempts (3)
- **Interval**: Check frequency (30 seconds)

## API Endpoints

### Health Endpoints

#### GET /health
Returns the health status of the health monitor service itself.

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-20T21:00:00.000Z",
  "service": "health-monitor",
  "version": "1.0.0",
  "uptime": 3600.5,
  "dependencies": {
    "mcp_servers": 3,
    "websocket_clients": 2
  }
}
```

#### GET /api/health/overall
Returns the overall health status of all MCP servers.

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

#### GET /api/health/service/{serviceName}
Returns the health status of a specific service.

**Parameters**:
- `serviceName`: Name of the service to check

**Response**: Same as individual service health in overall response

#### GET /api/health/history/{serviceName}
Returns the health history for a specific service.

**Parameters**:
- `serviceName`: Name of the service

**Response**:
```json
[
  {
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
]
```

### Alert Endpoints

#### GET /api/alerts
Returns all alerts, optionally filtered by service and resolution status.

**Query Parameters**:
- `service`: Filter by service name
- `resolved`: Filter by resolution status (true/false)

**Response**:
```json
[
  {
    "id": "gmail-mcp-server-1640995200000",
    "service": "gmail-mcp-server",
    "type": "failure",
    "message": "Service gmail-mcp-server has been unhealthy for 3 consecutive checks",
    "timestamp": "2025-01-20T21:00:00.000Z",
    "severity": "high",
    "resolved": false
  }
]
```

#### POST /api/alerts/{alertId}/resolve
Resolves a specific alert.

**Parameters**:
- `alertId`: ID of the alert to resolve

**Response**:
```json
{
  "message": "Alert resolved successfully"
}
```

### Service Endpoints

#### GET /api/services
Returns the configuration of all monitored services.

**Response**:
```json
[
  {
    "service": "gmail-mcp-server",
    "url": "http://gmail-mcp-server:8080",
    "port": 8080,
    "path": "/health",
    "timeout": 5000,
    "retries": 3,
    "interval": 30
  }
]
```

## WebSocket API

### Connection
Connect to `ws://localhost:8083` for real-time updates.

### Message Format
The WebSocket sends health updates in the same format as the overall health API:

```json
{
  "overall": "healthy",
  "services": { ... },
  "timestamp": "2025-01-20T21:00:00.000Z",
  "totalServices": 3,
  "healthyServices": 3,
  "unhealthyServices": 0,
  "degradedServices": 0
}
```

## Health Check Scripts

### Master Health Check Script
The `scripts/health-check-all.sh` script provides comprehensive health checking:

```bash
# Check all services
./scripts/health-check-all.sh

# Check with verbose output
./scripts/health-check-all.sh -v

# Check individual services only
./scripts/health-check-all.sh --individual

# Get overall health from monitor only
./scripts/health-check-all.sh --overall

# Set custom timeout
./scripts/health-check-all.sh -t 15

# Use custom health monitor URL
./scripts/health-check-all.sh -m http://localhost:8083
```

### Script Features
- **Individual Service Checks**: Direct health checks of each MCP server
- **Health Monitor Integration**: Uses health monitor for aggregated status
- **Colored Output**: Visual indicators for health status
- **Verbose Mode**: Detailed output for debugging
- **Configurable Timeouts**: Customizable timeout values
- **Exit Codes**: Proper exit codes for automation

## Monitoring Dashboard

### Access
The monitoring dashboard is available at `http://localhost:8083/dashboard`.

### Features
- **Real-Time Updates**: Live health status updates
- **Visual Indicators**: Color-coded health status
- **Service Cards**: Individual service information
- **Overall Status**: System-wide health summary
- **Metrics Display**: Response times, uptime, and error counts
- **Auto-Refresh**: Automatic updates every 30 seconds

### Dashboard Layout
1. **Header**: Overall system status and metrics
2. **Service Grid**: Individual service health cards
3. **Real-Time Updates**: WebSocket-powered live updates
4. **Refresh Button**: Manual refresh capability

## Alerting System

### Alert Types
1. **Failure Alerts**: Service becomes unhealthy
2. **Recovery Alerts**: Service recovers from failure
3. **Degradation Alerts**: Performance issues detected

### Alert Severity Levels
- **Low**: Minor issues or warnings
- **Medium**: Service degradation or recovery
- **High**: Service failures
- **Critical**: Multiple service failures

### Alert Conditions
- **Consecutive Failures**: 3+ consecutive unhealthy checks
- **Response Time**: Response time > 5000ms
- **Service Recovery**: Service transitions from unhealthy to healthy

## Configuration

### Environment Variables
```yaml
environment:
  - NODE_ENV=production
  - PORT=8083
  - HEALTH_CHECK_INTERVAL=30
```

### Service Dependencies
The health monitor depends on all MCP servers:
```yaml
depends_on:
  - gmail-mcp-server
  - graphiti-mcp-server
  - rag-mcp-server
```

### Port Exposure
The health monitor exposes port 8083 for external access to the dashboard and API.

## Health Check Validation

### Validation Scripts
1. **Individual Service Validation**: `scripts/validate-mcp-health.sh`
2. **Master Health Check**: `scripts/health-check-all.sh`
3. **MCP Protocol Validation**: `scripts/validate-mcp-protocol.sh`
4. **Letta Integration Validation**: `scripts/validate-letta-mcp-connection.sh`

### Validation Framework
The health monitoring system integrates with the existing validation framework:
- **Health Check Validation**: Automated health check testing
- **MCP Protocol Validation**: MCP protocol compliance testing
- **Integration Validation**: End-to-end connectivity testing

## Troubleshooting

### Common Issues

#### Health Monitor Not Starting
```bash
# Check container logs
docker logs health-monitor

# Check health monitor health
curl http://localhost:8083/health

# Check service dependencies
docker ps | grep mcp-server
```

#### Services Not Detected
```bash
# Check service configurations
curl http://localhost:8083/api/services

# Verify service health endpoints
curl http://gmail-mcp-server:8080/health
curl http://graphiti-mcp-server:8082/health
curl http://rag-mcp-server:8082/health
```

#### WebSocket Connection Issues
```bash
# Test WebSocket connection
wscat -c ws://localhost:8083

# Check WebSocket client count
curl http://localhost:8083/health | jq '.dependencies.websocket_clients'
```

### Debug Commands
```bash
# Check all services individually
./scripts/health-check-all.sh --individual -v

# Check overall health
./scripts/health-check-all.sh --overall

# Check specific service
curl -v http://localhost:8083/api/health/service/gmail-mcp-server

# Check alerts
curl http://localhost:8083/api/alerts

# Check health history
curl http://localhost:8083/api/health/history/gmail-mcp-server
```

## Performance Considerations

### Health Check Frequency
- **Default Interval**: 30 seconds
- **Configurable**: Via `HEALTH_CHECK_INTERVAL` environment variable
- **Balanced**: Between responsiveness and resource usage

### Resource Usage
- **Memory**: Minimal memory footprint for health checking
- **CPU**: Low CPU usage for periodic health checks
- **Network**: Minimal network overhead for health checks

### Scalability
- **Service Addition**: Easy to add new services to monitoring
- **Load Handling**: Can handle multiple concurrent health checks
- **WebSocket Scaling**: Supports multiple WebSocket connections

## Security Considerations

### Network Security
- **Internal Network**: Health checks use internal Docker network
- **External Access**: Only health monitor dashboard exposed externally
- **Authentication**: No authentication required for health checks

### Data Security
- **Health Data**: Health status data is not sensitive
- **Alert Data**: Alert information is internal only
- **WebSocket**: WebSocket connections are unencrypted (internal network)

## Future Enhancements

### Advanced Monitoring
- **Metrics Collection**: Prometheus metrics integration
- **Log Aggregation**: Centralized log collection
- **Performance Monitoring**: Detailed performance metrics
- **Capacity Planning**: Resource usage trends

### Alerting Improvements
- **Notification Channels**: Email, Slack, webhook notifications
- **Alert Escalation**: Automatic escalation procedures
- **Alert Suppression**: Maintenance window support
- **Custom Alerts**: User-defined alert conditions

### Dashboard Enhancements
- **Historical Views**: Health trend visualization
- **Custom Dashboards**: User-configurable dashboards
- **Mobile Support**: Mobile-responsive design
- **Dark Mode**: Theme customization

## Integration with PA Ecosystem

### Letta Integration
The health monitoring system provides health status to Letta for:
- **Service Discovery**: Available MCP services
- **Health-Based Routing**: Route requests to healthy services
- **Failure Handling**: Graceful degradation on service failures

### Workflow Integration
- **Health Gates**: Workflow steps that check service health
- **Conditional Execution**: Execute steps based on service health
- **Error Handling**: Automatic retry and fallback mechanisms

### Monitoring Integration
- **Centralized Monitoring**: Single point for all health monitoring
- **Alert Integration**: Unified alerting across all services
- **Dashboard Integration**: Consistent monitoring interface

## Conclusion

The health monitoring system provides comprehensive monitoring and alerting for all MCP servers in the PA ecosystem. It ensures reliable operation through real-time health checks, automated alerting, and a user-friendly dashboard. The system is designed to be scalable, maintainable, and easily extensible for future monitoring needs.

Key benefits:
- **Real-Time Monitoring**: Live health status of all services
- **Automated Alerting**: Proactive failure detection and notification
- **User-Friendly Dashboard**: Visual health monitoring interface
- **Comprehensive API**: Programmatic access to health data
- **Integration Ready**: Easy integration with existing systems
- **Extensible Design**: Support for additional services and features
