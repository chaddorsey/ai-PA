# MCP Servers Operational Procedures

## Overview

This document provides comprehensive operational procedures for managing MCP servers in the PA ecosystem. It covers deployment, monitoring, maintenance, troubleshooting, and disaster recovery procedures.

## Table of Contents

1. [Deployment Procedures](#deployment-procedures)
2. [Monitoring and Alerting](#monitoring-and-alerting)
3. [Maintenance Procedures](#maintenance-procedures)
4. [Backup and Recovery](#backup-and-recovery)
5. [Scaling and Performance](#scaling-and-performance)
6. [Security Operations](#security-operations)
7. [Incident Response](#incident-response)
8. [Change Management](#change-management)

## Deployment Procedures

### Initial Deployment

#### Prerequisites
- Docker and Docker Compose installed
- Sufficient system resources (CPU, memory, disk)
- Network access to required services
- Environment variables configured

#### Deployment Steps

1. **Clone Repository**:
   ```bash
   git clone <repository-url>
   cd ai-PA
   ```

2. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start Services**:
   ```bash
   docker-compose up -d
   ```

4. **Verify Deployment**:
   ```bash
   ./scripts/health-check-all.sh
   ./scripts/run-mcp-validation.sh
   ```

5. **Access Monitoring Dashboard**:
   ```bash
   open http://localhost:8083/dashboard
   ```

### Service-Specific Deployment

#### Gmail MCP Server
```bash
# Build and start Gmail MCP server
docker-compose up -d gmail-mcp-server

# Verify Gmail MCP server
curl http://localhost:8080/health
```

#### Graphiti MCP Server
```bash
# Build and start Graphiti MCP server
docker-compose up -d graphiti-mcp-server

# Verify Graphiti MCP server
curl http://localhost:8082/health
```

#### RAG MCP Server
```bash
# Build and start RAG MCP server
docker-compose up -d rag-mcp-server

# Verify RAG MCP server
curl http://localhost:8082/health
```

#### Health Monitor
```bash
# Build and start health monitor
docker-compose up -d health-monitor

# Verify health monitor
curl http://localhost:8083/health
```

### Configuration Management

#### Environment Variables
Key environment variables for each service:

**Gmail MCP Server**:
```bash
GMAIL_OAUTH_PATH=/app/config/gcp-oauth.keys.json
GMAIL_CREDENTIALS_PATH=/app/data/credentials.json
MCP_SERVER_NAME=gmail-tools
MCP_SERVER_PORT=8080
```

**Graphiti MCP Server**:
```bash
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=demodemo
OPENAI_API_KEY=your_openai_key
MCP_SERVER_NAME=graphiti-tools
MCP_SERVER_PORT=8082
```

**RAG MCP Server**:
```bash
VECTOR_DB_URL=http://vector-db:8080
DOCUMENT_STORE_URL=http://document-store:8080
EMBEDDING_MODEL=text-embedding-ada-002
MCP_SERVER_NAME=rag-tools
MCP_SERVER_PORT=8082
```

**Health Monitor**:
```bash
PORT=8083
HEALTH_CHECK_INTERVAL=30
NODE_ENV=production
```

## Monitoring and Alerting

### Health Monitoring

#### Real-Time Monitoring
- **Dashboard**: http://localhost:8083/dashboard
- **Health API**: http://localhost:8083/api/health/overall
- **WebSocket**: ws://localhost:8083

#### Key Metrics to Monitor
- Service availability and uptime
- Response times and performance
- Error rates and failure patterns
- Resource usage (CPU, memory, disk)
- Network connectivity and latency

#### Monitoring Commands
```bash
# Check overall health
curl http://localhost:8083/api/health/overall

# Check specific service
curl http://localhost:8083/api/health/service/gmail-mcp-server

# View health history
curl http://localhost:8083/api/health/history/gmail-mcp-server

# Check alerts
curl http://localhost:8083/api/alerts
```

### Alerting System

#### Alert Types
- **Service Down**: MCP server becomes unavailable
- **High Response Time**: Response time exceeds threshold
- **Error Rate Spike**: Error rate increases significantly
- **Resource Exhaustion**: CPU/memory usage too high
- **Dependency Failure**: External service unavailable

#### Alert Configuration
```yaml
# Health monitor configuration
alert_thresholds:
  response_time: 5000  # milliseconds
  error_rate: 0.1     # 10%
  consecutive_failures: 3
  memory_usage: 0.9   # 90%
  cpu_usage: 0.8      # 80%
```

#### Alert Response Procedures
1. **Immediate Response**:
   - Check service status
   - Review recent logs
   - Identify root cause

2. **Escalation**:
   - Notify on-call engineer
   - Create incident ticket
   - Update status page

3. **Resolution**:
   - Implement fix
   - Verify resolution
   - Update documentation

### Log Management

#### Log Locations
- **Docker Logs**: `docker logs <service-name>`
- **Application Logs**: `/var/log/mcp-servers/`
- **Health Monitor Logs**: `docker logs health-monitor`

#### Log Levels
- **DEBUG**: Detailed debugging information
- **INFO**: General information messages
- **WARN**: Warning messages
- **ERROR**: Error messages
- **FATAL**: Fatal error messages

#### Log Rotation
```yaml
# Docker logging configuration
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
    labels: "service,component,network"
```

#### Log Analysis
```bash
# View recent logs
docker logs --tail 100 gmail-mcp-server

# Follow logs in real-time
docker logs -f graphiti-mcp-server

# Search logs for errors
docker logs gmail-mcp-server 2>&1 | grep ERROR

# Export logs for analysis
docker logs gmail-mcp-server > gmail-mcp-logs.txt
```

## Maintenance Procedures

### Regular Maintenance

#### Daily Tasks
- [ ] Check service health status
- [ ] Review error logs
- [ ] Monitor resource usage
- [ ] Verify backup completion

#### Weekly Tasks
- [ ] Review performance metrics
- [ ] Check for security updates
- [ ] Validate backup integrity
- [ ] Update documentation

#### Monthly Tasks
- [ ] Full system health check
- [ ] Security audit
- [ ] Performance optimization review
- [ ] Disaster recovery testing

### Service Updates

#### Rolling Updates
```bash
# Update Gmail MCP server
docker-compose pull gmail-mcp-server
docker-compose up -d gmail-mcp-server

# Verify update
curl http://localhost:8080/health
```

#### Zero-Downtime Updates
```bash
# Start new version alongside old
docker-compose -f docker-compose.yml -f docker-compose.update.yml up -d

# Switch traffic to new version
# (Implementation depends on load balancer)

# Stop old version
docker-compose stop gmail-mcp-server-old
```

### Configuration Updates

#### Environment Variable Updates
```bash
# Update environment variables
docker-compose down
# Edit .env file
docker-compose up -d
```

#### Configuration File Updates
```bash
# Update configuration files
# Edit configuration files
docker-compose restart <service-name>
```

### Database Maintenance

#### Neo4j Maintenance (Graphiti)
```bash
# Connect to Neo4j
docker exec -it neo4j cypher-shell

# Check database size
CALL apoc.meta.stats() YIELD nodeCount, relCount;

# Clean up old data
MATCH (n) WHERE n.created < datetime() - duration('P30D') DELETE n;

# Rebuild indexes
CALL db.index.fulltext.createNodeIndex("memory_content", ["Memory"], ["content"]);
```

#### Data Backup
```bash
# Backup Neo4j database
docker exec neo4j neo4j-admin dump --database=neo4j --to=/backup/neo4j-backup.dump

# Backup Gmail credentials
docker cp gmail-mcp-server:/app/data/credentials.json ./backup/

# Backup RAG documents
docker cp rag-mcp-server:/app/data ./backup/rag-data/
```

## Backup and Recovery

### Backup Procedures

#### Automated Backups
```bash
#!/bin/bash
# backup-mcp-servers.sh

BACKUP_DIR="/backup/mcp-servers/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Backup Neo4j
docker exec neo4j neo4j-admin dump --database=neo4j --to="$BACKUP_DIR/neo4j.dump"

# Backup Gmail data
docker cp gmail-mcp-server:/app/data "$BACKUP_DIR/gmail-data/"

# Backup RAG data
docker cp rag-mcp-server:/app/data "$BACKUP_DIR/rag-data/"

# Backup configurations
cp -r ./gmail-mcp "$BACKUP_DIR/"
cp -r ./graphiti "$BACKUP_DIR/"
cp -r ./rag-mcp "$BACKUP_DIR/"
cp docker-compose.yml "$BACKUP_DIR/"

# Compress backup
tar -czf "$BACKUP_DIR.tar.gz" "$BACKUP_DIR"
rm -rf "$BACKUP_DIR"
```

#### Backup Schedule
```bash
# Add to crontab for daily backups
0 2 * * * /path/to/backup-mcp-servers.sh

# Weekly full backup
0 1 * * 0 /path/to/backup-mcp-servers.sh --full
```

### Recovery Procedures

#### Full System Recovery
```bash
# Stop all services
docker-compose down

# Restore from backup
tar -xzf backup-20250120.tar.gz
cd backup-20250120

# Restore Neo4j
docker exec -i neo4j neo4j-admin load --database=neo4j --from=/backup/neo4j.dump

# Restore data volumes
docker cp gmail-data/ gmail-mcp-server:/app/data/
docker cp rag-data/ rag-mcp-server:/app/data/

# Start services
docker-compose up -d

# Verify recovery
./scripts/health-check-all.sh
```

#### Individual Service Recovery
```bash
# Recover Gmail MCP server
docker-compose up -d gmail-mcp-server
curl http://localhost:8080/health

# Recover Graphiti MCP server
docker-compose up -d graphiti-mcp-server
curl http://localhost:8082/health

# Recover RAG MCP server
docker-compose up -d rag-mcp-server
curl http://localhost:8082/health
```

### Disaster Recovery

#### RTO/RPO Targets
- **Recovery Time Objective (RTO)**: 4 hours
- **Recovery Point Objective (RPO)**: 1 hour
- **Maximum Data Loss**: 1 hour

#### Recovery Steps
1. **Assessment**: Evaluate damage and data loss
2. **Infrastructure**: Restore infrastructure if needed
3. **Data Recovery**: Restore from most recent backup
4. **Service Recovery**: Start services in priority order
5. **Validation**: Verify all services are working
6. **Monitoring**: Ensure monitoring is active

## Scaling and Performance

### Horizontal Scaling

#### Load Balancer Configuration
```yaml
# nginx.conf
upstream gmail_mcp {
    server gmail-mcp-server-1:8080;
    server gmail-mcp-server-2:8080;
    server gmail-mcp-server-3:8080;
}

server {
    listen 80;
    location / {
        proxy_pass http://gmail_mcp;
    }
}
```

#### Service Scaling
```bash
# Scale Gmail MCP server
docker-compose up -d --scale gmail-mcp-server=3

# Scale Graphiti MCP server
docker-compose up -d --scale graphiti-mcp-server=2

# Scale RAG MCP server
docker-compose up -d --scale rag-mcp-server=2
```

### Vertical Scaling

#### Resource Allocation
```yaml
# docker-compose.yml
services:
  gmail-mcp-server:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

#### Performance Tuning
```bash
# Increase Node.js memory limit
NODE_OPTIONS="--max-old-space-size=2048"

# Optimize Neo4j
NEO4J_dbms_memory_heap_initial__size=1G
NEO4J_dbms_memory_heap_max__size=2G
NEO4J_dbms_memory_pagecache_size=1G
```

### Performance Monitoring

#### Key Performance Indicators
- **Response Time**: < 500ms for 95% of requests
- **Throughput**: > 1000 requests/minute
- **Error Rate**: < 1%
- **Availability**: > 99.9%

#### Performance Testing
```bash
# Load testing with Apache Bench
ab -n 1000 -c 10 http://localhost:8080/health

# Load testing with wrk
wrk -t12 -c400 -d30s http://localhost:8080/health

# Custom performance test
./scripts/performance-test.sh
```

## Security Operations

### Security Monitoring

#### Security Metrics
- Failed authentication attempts
- Unusual access patterns
- Suspicious API calls
- Resource usage anomalies

#### Security Logs
```bash
# Monitor authentication failures
docker logs gmail-mcp-server 2>&1 | grep "auth.*failed"

# Monitor API access
docker logs gmail-mcp-server 2>&1 | grep "POST /mcp"

# Monitor error patterns
docker logs gmail-mcp-server 2>&1 | grep "ERROR"
```

### Access Control

#### API Access Control
```yaml
# Rate limiting
rate_limits:
  gmail_mcp: 100/minute
  graphiti_mcp: 200/minute
  rag_mcp: 150/minute
  health_monitor: 500/minute
```

#### Network Security
```yaml
# Firewall rules
- Allow: 8080 (Gmail MCP)
- Allow: 8082 (Graphiti/RAG MCP)
- Allow: 8083 (Health Monitor)
- Deny: All other ports
```

### Vulnerability Management

#### Security Updates
```bash
# Update base images
docker-compose pull

# Update dependencies
docker-compose build --no-cache

# Scan for vulnerabilities
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image gmail-mcp-server:latest
```

#### Security Audits
```bash
# Audit Docker containers
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image --severity HIGH,CRITICAL gmail-mcp-server:latest

# Audit application dependencies
docker exec gmail-mcp-server npm audit
```

## Incident Response

### Incident Classification

#### Severity Levels
- **P1 - Critical**: Service completely down
- **P2 - High**: Service degraded, major impact
- **P3 - Medium**: Service affected, limited impact
- **P4 - Low**: Minor issues, no impact

#### Response Times
- **P1**: 15 minutes
- **P2**: 1 hour
- **P3**: 4 hours
- **P4**: 24 hours

### Incident Response Procedures

#### 1. Detection and Alert
- Monitor alerts and notifications
- Verify incident severity
- Notify on-call engineer

#### 2. Assessment
- Gather information about the incident
- Identify affected services
- Determine root cause

#### 3. Response
- Implement immediate fixes
- Escalate if necessary
- Communicate status updates

#### 4. Resolution
- Verify fix is working
- Monitor for recurrence
- Document incident

#### 5. Post-Incident
- Conduct post-mortem
- Update procedures
- Implement preventive measures

### Common Incidents

#### Service Down
```bash
# Check service status
docker ps | grep mcp-server

# Check logs
docker logs gmail-mcp-server

# Restart service
docker-compose restart gmail-mcp-server

# Verify recovery
curl http://localhost:8080/health
```

#### High Memory Usage
```bash
# Check memory usage
docker stats gmail-mcp-server

# Restart service
docker-compose restart gmail-mcp-server

# Monitor memory usage
docker stats --no-stream gmail-mcp-server
```

#### Database Connection Issues
```bash
# Check Neo4j status
docker exec neo4j cypher-shell "CALL db.ping()"

# Check network connectivity
docker exec graphiti-mcp-server ping neo4j

# Restart database
docker-compose restart neo4j
```

## Change Management

### Change Process

#### 1. Change Request
- Document change details
- Assess impact and risk
- Get approval from stakeholders

#### 2. Change Planning
- Create implementation plan
- Schedule change window
- Prepare rollback plan

#### 3. Change Implementation
- Execute change in test environment
- Validate change works correctly
- Deploy to production

#### 4. Change Validation
- Verify change is working
- Monitor for issues
- Document results

#### 5. Change Closure
- Update documentation
- Conduct lessons learned
- Close change request

### Change Types

#### Standard Changes
- Routine updates
- Configuration changes
- Minor bug fixes

#### Emergency Changes
- Security patches
- Critical bug fixes
- Service restoration

#### Major Changes
- New service deployment
- Architecture changes
- Major feature releases

### Change Documentation

#### Change Request Template
```yaml
Change ID: CHG-2025-001
Title: Update Gmail MCP Server
Description: Update Gmail MCP server to version 1.1.12
Impact: Low
Risk: Low
Implementation Date: 2025-01-21
Rollback Plan: Revert to previous version
```

#### Change Log
```yaml
2025-01-20:
  - Deployed Gmail MCP Server v1.1.11
  - Updated health monitoring configuration
  - Added new email search functionality

2025-01-19:
  - Fixed Graphiti MCP Server memory leak
  - Updated Neo4j configuration
  - Improved error handling
```

---

*For more information, see the [Troubleshooting Guide](./troubleshooting.md) and [Security Guide](./security.md).*
