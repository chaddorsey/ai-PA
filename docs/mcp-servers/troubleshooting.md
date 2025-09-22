# MCP Servers Troubleshooting Guide

## Overview

This guide provides comprehensive troubleshooting procedures for MCP servers in the PA ecosystem. It covers common issues, diagnostic procedures, and resolution steps.

## Quick Diagnostic Commands

### System Health Check
```bash
# Check all services
./scripts/health-check-all.sh

# Check individual services
curl http://localhost:8080/health  # Gmail MCP
curl http://localhost:8082/health  # Graphiti MCP
curl http://localhost:8082/health  # RAG MCP
curl http://localhost:8083/health  # Health Monitor

# Check Docker services
docker ps | grep mcp
```

### Log Analysis
```bash
# View recent logs
docker logs --tail 100 gmail-mcp-server
docker logs --tail 100 graphiti-mcp-server
docker logs --tail 100 rag-mcp-server
docker logs --tail 100 health-monitor

# Follow logs in real-time
docker logs -f gmail-mcp-server

# Search for errors
docker logs gmail-mcp-server 2>&1 | grep ERROR
```

## Common Issues and Solutions

### 1. Service Won't Start

#### Symptoms
- Service container exits immediately
- Service not accessible via health endpoint
- Docker logs show startup errors

#### Diagnostic Steps
```bash
# Check container status
docker ps -a | grep mcp-server

# Check container logs
docker logs gmail-mcp-server

# Check resource usage
docker stats gmail-mcp-server

# Check port availability
netstat -tulpn | grep :8080
```

#### Common Causes and Solutions

**Port Already in Use**:
```bash
# Find process using port
lsof -i :8080

# Kill process
kill -9 <PID>

# Or change port in docker-compose.yml
```

**Insufficient Resources**:
```bash
# Check system resources
free -h
df -h

# Increase Docker memory limit
# Edit Docker Desktop settings
```

**Configuration Errors**:
```bash
# Validate docker-compose.yml
docker-compose config

# Check environment variables
docker-compose config | grep -A 10 gmail-mcp-server
```

**Missing Dependencies**:
```bash
# Check if Neo4j is running (for Graphiti)
docker ps | grep neo4j

# Start dependencies first
docker-compose up -d neo4j
docker-compose up -d graphiti-mcp-server
```

### 2. Service Unhealthy

#### Symptoms
- Health endpoint returns non-200 status
- Service responds slowly
- Intermittent failures

#### Diagnostic Steps
```bash
# Check health endpoint
curl -v http://localhost:8080/health

# Check service logs
docker logs gmail-mcp-server | tail -50

# Check resource usage
docker stats gmail-mcp-server

# Test internal connectivity
docker exec gmail-mcp-server curl http://localhost:8080/health
```

#### Common Causes and Solutions

**Database Connection Issues**:
```bash
# Check Neo4j connectivity (Graphiti)
docker exec graphiti-mcp-server ping neo4j

# Check Neo4j status
docker exec neo4j cypher-shell "CALL db.ping()"

# Restart Neo4j
docker-compose restart neo4j
```

**API Authentication Issues**:
```bash
# Check Gmail API credentials
docker exec gmail-mcp-server ls -la /app/config/

# Verify credentials file
docker exec gmail-mcp-server cat /app/config/gcp-oauth.keys.json

# Regenerate credentials if needed
```

**Memory Issues**:
```bash
# Check memory usage
docker stats gmail-mcp-server

# Restart service
docker-compose restart gmail-mcp-server

# Increase memory limit in docker-compose.yml
```

### 3. Tool Execution Failures

#### Symptoms
- MCP tool calls return errors
- Tools not responding
- Invalid tool responses

#### Diagnostic Steps
```bash
# Test tool discovery
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'

# Test specific tool
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "search_emails",
      "arguments": {"query": "test"}
    }
  }'
```

#### Common Causes and Solutions

**Invalid Tool Arguments**:
```bash
# Check tool schema
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'

# Validate arguments match schema
# Check API documentation for correct format
```

**Tool Implementation Errors**:
```bash
# Check service logs for errors
docker logs gmail-mcp-server | grep -i error

# Test with minimal arguments
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "get_labels",
      "arguments": {}
    }
  }'
```

**Rate Limiting**:
```bash
# Check rate limit headers
curl -I http://localhost:8080/mcp

# Wait for rate limit reset
# Implement exponential backoff in client
```

### 4. Letta Integration Issues

#### Symptoms
- Letta can't connect to MCP servers
- Tools not available in Letta
- Connection timeouts

#### Diagnostic Steps
```bash
# Check Letta MCP configuration
cat letta/letta_mcp_config.json

# Test Letta MCP discovery
curl http://localhost:8283/v1/tools/mcp/servers

# Check Letta logs
docker logs letta | grep -i mcp
```

#### Common Causes and Solutions

**Configuration Issues**:
```bash
# Validate JSON configuration
jq . letta/letta_mcp_config.json

# Check service URLs
curl http://gmail-mcp-server:8080/health
curl http://graphiti-mcp-server:8082/health
curl http://rag-mcp-server:8082/health
```

**Network Connectivity**:
```bash
# Test internal network connectivity
docker exec letta ping gmail-mcp-server
docker exec letta ping graphiti-mcp-server
docker exec letta ping rag-mcp-server

# Check Docker network
docker network ls
docker network inspect pa-internal
```

**Service Discovery Issues**:
```bash
# Check if services are registered
curl http://localhost:8283/v1/tools/mcp/servers

# Restart Letta
docker-compose restart letta

# Check Letta MCP configuration
docker exec letta cat /root/.letta/mcp_config.json
```

### 5. Health Monitor Issues

#### Symptoms
- Health monitor not accessible
- Dashboard not loading
- Alerts not working

#### Diagnostic Steps
```bash
# Check health monitor status
curl http://localhost:8083/health

# Check health monitor logs
docker logs health-monitor

# Test API endpoints
curl http://localhost:8083/api/health/overall
curl http://localhost:8083/api/services
```

#### Common Causes and Solutions

**Port Conflicts**:
```bash
# Check port usage
netstat -tulpn | grep :8083

# Change port in docker-compose.yml
# Restart health monitor
```

**Service Dependencies**:
```bash
# Check if MCP servers are running
docker ps | grep mcp-server

# Start MCP servers first
docker-compose up -d gmail-mcp-server graphiti-mcp-server rag-mcp-server
docker-compose up -d health-monitor
```

**WebSocket Issues**:
```bash
# Test WebSocket connection
wscat -c ws://localhost:8083

# Check WebSocket logs
docker logs health-monitor | grep -i websocket
```

## Performance Issues

### 1. Slow Response Times

#### Symptoms
- API calls taking > 5 seconds
- Timeout errors
- High latency

#### Diagnostic Steps
```bash
# Measure response times
time curl http://localhost:8080/health

# Check resource usage
docker stats gmail-mcp-server

# Monitor network latency
ping gmail-mcp-server
```

#### Solutions

**Resource Optimization**:
```bash
# Increase memory limit
# Edit docker-compose.yml
deploy:
  resources:
    limits:
      memory: 2G

# Restart service
docker-compose up -d gmail-mcp-server
```

**Database Optimization**:
```bash
# Check Neo4j performance
docker exec neo4j cypher-shell "CALL db.ping()"

# Optimize Neo4j configuration
# Edit Neo4j environment variables
```

**Network Optimization**:
```bash
# Check network latency
docker exec gmail-mcp-server ping neo4j

# Optimize Docker network
# Use host networking if needed
```

### 2. High Memory Usage

#### Symptoms
- Memory usage > 90%
- Out of memory errors
- Service crashes

#### Diagnostic Steps
```bash
# Check memory usage
docker stats gmail-mcp-server

# Check memory limits
docker inspect gmail-mcp-server | grep -i memory

# Monitor memory over time
watch -n 1 'docker stats --no-stream gmail-mcp-server'
```

#### Solutions

**Memory Leak Fix**:
```bash
# Restart service
docker-compose restart gmail-mcp-server

# Check for memory leaks in logs
docker logs gmail-mcp-server | grep -i memory
```

**Increase Memory Limit**:
```bash
# Edit docker-compose.yml
deploy:
  resources:
    limits:
      memory: 4G

# Restart service
docker-compose up -d gmail-mcp-server
```

**Optimize Application**:
```bash
# Check Node.js memory usage
docker exec gmail-mcp-server node --max-old-space-size=2048

# Optimize application code
# Review memory usage patterns
```

### 3. High CPU Usage

#### Symptoms
- CPU usage > 80%
- Slow response times
- System unresponsive

#### Diagnostic Steps
```bash
# Check CPU usage
docker stats gmail-mcp-server

# Check CPU limits
docker inspect gmail-mcp-server | grep -i cpu

# Monitor CPU over time
top -p $(docker inspect -f '{{.State.Pid}}' gmail-mcp-server)
```

#### Solutions

**CPU Optimization**:
```bash
# Increase CPU limit
deploy:
  resources:
    limits:
      cpus: '2.0'

# Restart service
docker-compose up -d gmail-mcp-server
```

**Code Optimization**:
```bash
# Profile application
docker exec gmail-mcp-server node --prof server.js

# Optimize hot paths
# Review algorithm efficiency
```

## Network Issues

### 1. Connection Refused

#### Symptoms
- "Connection refused" errors
- Service not accessible
- Network timeouts

#### Diagnostic Steps
```bash
# Check if service is listening
netstat -tulpn | grep :8080

# Check Docker port mapping
docker port gmail-mcp-server

# Test local connectivity
curl http://localhost:8080/health
```

#### Solutions

**Port Mapping Issues**:
```bash
# Check docker-compose.yml port mapping
ports:
  - "8080:8080"

# Restart service
docker-compose up -d gmail-mcp-server
```

**Firewall Issues**:
```bash
# Check firewall rules
sudo ufw status

# Allow port
sudo ufw allow 8080

# Restart service
docker-compose restart gmail-mcp-server
```

### 2. DNS Resolution Issues

#### Symptoms
- "Name or service not known" errors
- Service discovery failures
- Internal network issues

#### Diagnostic Steps
```bash
# Test DNS resolution
docker exec gmail-mcp-server nslookup neo4j

# Check Docker network
docker network inspect pa-internal

# Test internal connectivity
docker exec gmail-mcp-server ping neo4j
```

#### Solutions

**Network Configuration**:
```bash
# Recreate Docker network
docker network rm pa-internal
docker-compose up -d

# Check network configuration
docker network ls
```

**Service Discovery**:
```bash
# Check service names in docker-compose.yml
# Ensure consistent naming

# Restart all services
docker-compose down
docker-compose up -d
```

## Database Issues

### 1. Neo4j Connection Issues

#### Symptoms
- Graphiti MCP server can't connect to Neo4j
- Database connection errors
- Timeout errors

#### Diagnostic Steps
```bash
# Check Neo4j status
docker ps | grep neo4j

# Test Neo4j connectivity
docker exec neo4j cypher-shell "CALL db.ping()"

# Check Neo4j logs
docker logs neo4j
```

#### Solutions

**Neo4j Startup Issues**:
```bash
# Start Neo4j first
docker-compose up -d neo4j

# Wait for Neo4j to be ready
sleep 30

# Start Graphiti MCP server
docker-compose up -d graphiti-mcp-server
```

**Connection Configuration**:
```bash
# Check Neo4j URI
docker exec graphiti-mcp-server env | grep NEO4J

# Verify Neo4j credentials
docker exec neo4j cypher-shell -u neo4j -p demodemo
```

### 2. Database Performance Issues

#### Symptoms
- Slow database queries
- High database CPU usage
- Query timeouts

#### Diagnostic Steps
```bash
# Check Neo4j performance
docker exec neo4j cypher-shell "CALL db.ping()"

# Monitor Neo4j resources
docker stats neo4j

# Check Neo4j logs
docker logs neo4j | grep -i slow
```

#### Solutions

**Database Optimization**:
```bash
# Optimize Neo4j configuration
# Edit Neo4j environment variables
NEO4J_dbms_memory_heap_max__size=2G
NEO4J_dbms_memory_pagecache_size=1G

# Restart Neo4j
docker-compose restart neo4j
```

**Query Optimization**:
```bash
# Check slow queries
docker exec neo4j cypher-shell "CALL dbms.listQueries()"

# Optimize indexes
docker exec neo4j cypher-shell "CALL db.index.fulltext.createNodeIndex('memory_content', ['Memory'], ['content'])"
```

## Security Issues

### 1. Authentication Failures

#### Symptoms
- "Authentication failed" errors
- Invalid credentials
- Access denied errors

#### Diagnostic Steps
```bash
# Check Gmail API credentials
docker exec gmail-mcp-server ls -la /app/config/

# Verify credentials file
docker exec gmail-mcp-server cat /app/config/gcp-oauth.keys.json

# Check authentication logs
docker logs gmail-mcp-server | grep -i auth
```

#### Solutions

**Credential Issues**:
```bash
# Regenerate Gmail API credentials
# Update credentials file
docker cp new-credentials.json gmail-mcp-server:/app/config/gcp-oauth.keys.json

# Restart service
docker-compose restart gmail-mcp-server
```

**Permission Issues**:
```bash
# Check file permissions
docker exec gmail-mcp-server ls -la /app/config/

# Fix permissions
docker exec gmail-mcp-server chmod 600 /app/config/gcp-oauth.keys.json
```

### 2. Rate Limiting Issues

#### Symptoms
- "Rate limit exceeded" errors
- API quota exceeded
- Throttling errors

#### Diagnostic Steps
```bash
# Check rate limit headers
curl -I http://localhost:8080/mcp

# Monitor API usage
docker logs gmail-mcp-server | grep -i rate
```

#### Solutions

**Rate Limit Management**:
```bash
# Implement exponential backoff
# Reduce request frequency
# Use batch operations when possible
```

**API Quota Management**:
```bash
# Check API quotas
# Optimize API usage
# Implement caching
```

## Debugging Tools

### 1. Log Analysis

#### Log Levels
```bash
# Set debug logging
export MCP_LOG_LEVEL=DEBUG

# Restart service
docker-compose restart gmail-mcp-server
```

#### Log Filtering
```bash
# Filter by level
docker logs gmail-mcp-server 2>&1 | grep ERROR

# Filter by component
docker logs gmail-mcp-server 2>&1 | grep "Gmail MCP"

# Filter by time
docker logs gmail-mcp-server --since 1h
```

### 2. Network Debugging

#### Network Tools
```bash
# Test connectivity
docker exec gmail-mcp-server ping neo4j

# Check DNS resolution
docker exec gmail-mcp-server nslookup neo4j

# Test port connectivity
docker exec gmail-mcp-server telnet neo4j 7687
```

#### Network Monitoring
```bash
# Monitor network traffic
docker exec gmail-mcp-server netstat -tulpn

# Check network interfaces
docker exec gmail-mcp-server ip addr show
```

### 3. Performance Profiling

#### Resource Monitoring
```bash
# Monitor resources
docker stats gmail-mcp-server

# Monitor over time
watch -n 1 'docker stats --no-stream gmail-mcp-server'
```

#### Application Profiling
```bash
# Node.js profiling
docker exec gmail-mcp-server node --prof server.js

# Generate profile report
docker exec gmail-mcp-server node --prof-process isolate-*.log
```

## Emergency Procedures

### 1. Service Recovery

#### Complete Service Restart
```bash
# Stop all services
docker-compose down

# Start services in order
docker-compose up -d neo4j
sleep 30
docker-compose up -d gmail-mcp-server graphiti-mcp-server rag-mcp-server
docker-compose up -d health-monitor

# Verify recovery
./scripts/health-check-all.sh
```

#### Individual Service Recovery
```bash
# Restart specific service
docker-compose restart gmail-mcp-server

# Verify service health
curl http://localhost:8080/health
```

### 2. Data Recovery

#### Database Recovery
```bash
# Stop services
docker-compose down

# Restore from backup
docker exec -i neo4j neo4j-admin load --database=neo4j --from=/backup/neo4j.dump

# Start services
docker-compose up -d
```

#### Configuration Recovery
```bash
# Restore configuration files
cp backup/letta_mcp_config.json letta/

# Restart services
docker-compose restart letta
```

### 3. Rollback Procedures

#### Service Rollback
```bash
# Stop current version
docker-compose down

# Switch to previous version
git checkout previous-version

# Start previous version
docker-compose up -d
```

#### Configuration Rollback
```bash
# Restore previous configuration
cp backup/docker-compose.yml .

# Restart services
docker-compose up -d
```

## Prevention

### 1. Monitoring Setup

#### Health Monitoring
```bash
# Set up health monitoring
curl http://localhost:8083/dashboard

# Configure alerts
# Set up notification channels
```

#### Performance Monitoring
```bash
# Monitor response times
# Set up performance alerts
# Track resource usage
```

### 2. Regular Maintenance

#### Daily Checks
```bash
# Check service health
./scripts/health-check-all.sh

# Review error logs
docker logs gmail-mcp-server 2>&1 | grep ERROR

# Monitor resource usage
docker stats --no-stream
```

#### Weekly Checks
```bash
# Full system validation
./scripts/run-mcp-validation.sh

# Performance analysis
# Security audit
```

### 3. Backup Procedures

#### Automated Backups
```bash
# Set up daily backups
# Test backup restoration
# Monitor backup success
```

#### Configuration Backups
```bash
# Backup configurations
# Version control changes
# Document changes
```

---

*For more information, see the [Operations Guide](./operations.md) and [API Reference](./api-reference.md).*

