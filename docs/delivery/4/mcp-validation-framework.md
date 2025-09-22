# MCP Server Validation Framework

## Overview

This document outlines a comprehensive validation framework to ensure MCP servers remain operational during and after the standardization process. The framework includes pre-migration, migration, and post-migration validation steps.

## Validation Phases

### Phase 1: Pre-Migration Validation

#### 1.1 Baseline Functionality Testing
```bash
# Test current Gmail MCP functionality
curl -X POST http://gmail-mcp-server:7331/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'

# Test current Graphiti MCP functionality  
curl -X POST http://graphiti-mcp-server:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'

# Test current Slack MCP functionality
curl -X POST http://slack-mcp-server:3001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'
```

#### 1.2 Letta Integration Testing
```bash
# Test Letta can connect to current MCP servers
curl http://letta:8283/v1/tools/mcp/servers

# Test specific MCP tool functionality through Letta
curl -X POST http://letta:8283/v1/tools/mcp/test \
  -H "Content-Type: application/json" \
  -d '{"server_name": "gmail-tools", "tool_name": "send_email"}'
```

#### 1.3 OAuth and Authentication Testing
```bash
# Test Gmail OAuth flow
# (Manual testing required for OAuth flows)

# Test Graphiti Neo4j connection
curl -X POST http://graphiti-mcp-server:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "add_memory", "params": {"name": "test", "episode_body": "validation test"}}'
```

### Phase 2: Migration Validation

#### 2.1 Service-by-Service Validation
Each MCP server is validated individually during migration:

**Gmail MCP Server Migration**:
1. Update docker-compose.yml
2. Test service startup: `docker-compose up gmail-mcp-server`
3. Test health check: `curl http://gmail-mcp-server:8080/health`
4. Test MCP endpoint: `curl -X POST http://gmail-mcp-server:8080/mcp`
5. Test OAuth functionality
6. Test Letta connectivity

**Graphiti MCP Server Migration**:
1. Update docker-compose.yml
2. Test service startup: `docker-compose up graphiti-mcp-server`
3. Test health check: `curl http://graphiti-mcp-server:8082/health`
4. Test MCP endpoint: `curl -X POST http://graphiti-mcp-server:8082/mcp`
5. Test Neo4j connectivity
6. Test knowledge graph operations

#### 2.2 Incremental Testing
- Apply changes one service at a time
- Test after each change
- Rollback immediately if issues occur
- Document any problems and solutions

### Phase 3: Post-Migration Validation

#### 3.1 Comprehensive System Testing

**Health Check Validation**:
```bash
#!/bin/bash
# validate-mcp-health.sh

echo "Validating MCP server health checks..."

# Test all MCP server health endpoints
curl -f http://gmail-mcp-server:8080/health || echo "Gmail MCP health check failed"
curl -f http://slack-mcp-server:8081/health || echo "Slack MCP health check failed"
curl -f http://graphiti-mcp-server:8082/health || echo "Graphiti MCP health check failed"
curl -f http://rag-mcp-server:8083/health || echo "RAG MCP health check failed"

echo "Health check validation complete"
```

**MCP Protocol Validation**:
```bash
#!/bin/bash
# validate-mcp-protocol.sh

echo "Validating MCP protocol functionality..."

# Test MCP server initialization
test_mcp_server() {
    local server_name=$1
    local server_url=$2
    
    echo "Testing $server_name at $server_url"
    
    response=$(curl -s -X POST "$server_url/mcp" \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}')
    
    if echo "$response" | grep -q "result"; then
        echo "✅ $server_name: MCP protocol working"
    else
        echo "❌ $server_name: MCP protocol failed"
        echo "Response: $response"
    fi
}

test_mcp_server "Gmail MCP" "http://gmail-mcp-server:8080"
test_mcp_server "Slack MCP" "http://slack-mcp-server:8081"
test_mcp_server "Graphiti MCP" "http://graphiti-mcp-server:8082"
test_mcp_server "RAG MCP" "http://rag-mcp-server:8083"
```

**Tool Functionality Validation**:
```bash
#!/bin/bash
# validate-mcp-tools.sh

echo "Validating MCP tool functionality..."

# Test Gmail tools
echo "Testing Gmail tools..."
curl -s -X POST http://gmail-mcp-server:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}' | jq '.result.tools[].name'

# Test Graphiti tools
echo "Testing Graphiti tools..."
curl -s -X POST http://graphiti-mcp-server:8082/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}' | jq '.result.tools[].name'

# Test Slack tools
echo "Testing Slack tools..."
curl -s -X POST http://slack-mcp-server:8081/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}' | jq '.result.tools[].name'
```

#### 3.2 Letta Integration Validation

**Letta MCP Server Discovery**:
```bash
#!/bin/bash
# validate-letta-mcp-connection.sh

echo "Validating Letta MCP server connections..."

# Test Letta can discover all MCP servers
servers=$(curl -s http://letta:8283/v1/tools/mcp/servers | jq -r '.[].server_name')

echo "Discovered MCP servers:"
echo "$servers"

# Validate expected servers are present
expected_servers=("gmail-tools" "slack-tools" "graphiti-tools" "rag-tools")

for expected in "${expected_servers[@]}"; do
    if echo "$servers" | grep -q "$expected"; then
        echo "✅ $expected: Connected to Letta"
    else
        echo "❌ $expected: Not connected to Letta"
    fi
done
```

**End-to-End Tool Testing**:
```bash
#!/bin/bash
# validate-letta-tools.sh

echo "Validating Letta tool functionality..."

# Test Gmail tools through Letta
echo "Testing Gmail tools through Letta..."
curl -s -X POST http://letta:8283/v1/tools/mcp/servers/gmail-tools/test

# Test Graphiti tools through Letta
echo "Testing Graphiti tools through Letta..."
curl -s -X POST http://letta:8283/v1/tools/mcp/servers/graphiti-tools/test

# Test Slack tools through Letta
echo "Testing Slack tools through Letta..."
curl -s -X POST http://letta:8283/v1/tools/mcp/servers/slack-tools/test
```

### Phase 4: Continuous Monitoring

#### 4.1 Automated Health Monitoring
```yaml
# docker-compose.yml monitoring configuration
services:
  mcp-monitor:
    image: curlimages/curl:latest
    command: |
      sh -c "
        while true; do
          echo 'Checking MCP server health...'
          curl -f http://gmail-mcp-server:8080/health || echo 'Gmail MCP unhealthy'
          curl -f http://slack-mcp-server:8081/health || echo 'Slack MCP unhealthy'
          curl -f http://graphiti-mcp-server:8082/health || echo 'Graphiti MCP unhealthy'
          curl -f http://rag-mcp-server:8083/health || echo 'RAG MCP unhealthy'
          sleep 60
        done
      "
    networks: [pa-network]
    depends_on:
      - gmail-mcp-server
      - slack-mcp-server
      - graphiti-mcp-server
      - rag-mcp-server
```

#### 4.2 Log Monitoring
```bash
#!/bin/bash
# monitor-mcp-logs.sh

echo "Monitoring MCP server logs for errors..."

# Monitor logs for errors
docker-compose logs -f gmail-mcp-server | grep -i error &
docker-compose logs -f slack-mcp-server | grep -i error &
docker-compose logs -f graphiti-mcp-server | grep -i error &
docker-compose logs -f rag-mcp-server | grep -i error &
```

## Validation Checklist

### Pre-Migration Checklist
- [ ] All current MCP servers are operational
- [ ] Letta can connect to all MCP servers
- [ ] All MCP tools are functional
- [ ] OAuth flows are working
- [ ] Database connections are stable
- [ ] Backup of current configuration created

### During Migration Checklist
- [ ] Service starts with new configuration
- [ ] Health check endpoint responds correctly
- [ ] MCP protocol endpoints are accessible
- [ ] OAuth/authentication still works
- [ ] Database connections are maintained
- [ ] Letta can connect to updated server
- [ ] No errors in logs

### Post-Migration Checklist
- [ ] All MCP servers operational
- [ ] All health checks passing
- [ ] All MCP tools functional
- [ ] Letta integration working
- [ ] Logging is structured and working
- [ ] Monitoring is operational
- [ ] Performance is acceptable
- [ ] No regressions detected

## Rollback Procedures

### Immediate Rollback
```bash
# Stop all services
docker-compose down

# Restore backup configuration
cp docker-compose.yml.backup docker-compose.yml

# Start services with old configuration
docker-compose up -d

# Verify functionality
./validate-mcp-health.sh
```

### Gradual Rollback
```bash
# Rollback one service at a time
# Example: Rollback Gmail MCP server
docker-compose stop gmail-mcp-server
# Edit docker-compose.yml to revert Gmail MCP changes
docker-compose up gmail-mcp-server
# Test functionality
curl http://gmail-mcp-server:7331/health
```

## Performance Validation

### Response Time Testing
```bash
#!/bin/bash
# test-mcp-performance.sh

echo "Testing MCP server performance..."

# Test response times
test_response_time() {
    local server_name=$1
    local server_url=$2
    
    echo "Testing $server_name response time..."
    
    start_time=$(date +%s%N)
    curl -s -X POST "$server_url/mcp" \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}' > /dev/null
    end_time=$(date +%s%N)
    
    response_time=$(( (end_time - start_time) / 1000000 ))
    echo "$server_name response time: ${response_time}ms"
}

test_response_time "Gmail MCP" "http://gmail-mcp-server:8080"
test_response_time "Slack MCP" "http://slack-mcp-server:8081"
test_response_time "Graphiti MCP" "http://graphiti-mcp-server:8082"
test_response_time "RAG MCP" "http://rag-mcp-server:8083"
```

## Success Criteria

### Functional Success
- All MCP servers start successfully
- All health checks pass
- All MCP tools are discoverable and functional
- Letta can connect to all MCP servers
- OAuth and authentication flows work
- Database connections are stable

### Performance Success
- Health checks respond within 5 seconds
- MCP tool responses complete within 30 seconds
- No significant performance degradation
- Memory usage is within acceptable limits

### Operational Success
- Structured logging is working
- Monitoring and alerting are operational
- Service discovery works correctly
- Error handling is robust
- Rollback procedures are tested and working

## Validation Tools

### Automated Validation Script
```bash
#!/bin/bash
# run-mcp-validation.sh

echo "Starting comprehensive MCP validation..."

# Run all validation scripts
./validate-mcp-health.sh
./validate-mcp-protocol.sh
./validate-mcp-tools.sh
./validate-letta-mcp-connection.sh
./validate-letta-tools.sh
./test-mcp-performance.sh

echo "MCP validation complete"
```

This validation framework ensures that MCP servers remain operational throughout the standardization process and provides comprehensive testing to catch any issues early.

