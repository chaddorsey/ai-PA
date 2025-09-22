# PA Ecosystem Network Security Guide

This guide provides comprehensive documentation for the PA Ecosystem's network security implementation, including network segmentation, firewall policies, and security validation procedures.

## Overview

The network security framework provides:
- **Network Segmentation**: Isolated network tiers for different service types
- **Firewall Policies**: Restrictive access controls with allow-list approach
- **Service Isolation**: Prevention of lateral movement in case of compromise
- **Security Monitoring**: Network traffic analysis and anomaly detection
- **Access Control**: Fine-grained control over inter-service communication

## Network Architecture

### Network Tiers

The PA ecosystem implements a multi-tier network architecture with the following security zones:

#### 1. Database Tier (High Security)
- **Subnet**: 172.20.1.0/24
- **Services**: Database services only
- **Access**: Restricted to Supabase internal services and monitoring
- **Security Level**: High

**Services:**
- `supabase-db` - PostgreSQL database

#### 2. Supabase Internal Tier (High Security)
- **Subnet**: 172.20.2.0/24
- **Services**: Internal Supabase services
- **Access**: Database tier and backend tier only
- **Security Level**: High

**Services:**
- `supabase-rest` - REST API service
- `supabase-auth` - Authentication service
- `supabase-realtime` - Real-time service
- `supabase-meta` - Metadata service

#### 3. Backend Tier (Medium Security)
- **Subnet**: 172.20.3.0/24
- **Services**: Application backend services
- **Access**: Frontend tier, Supabase internal, and monitoring
- **Security Level**: Medium

**Services:**
- `n8n` - Workflow automation

#### 4. MCP Services Tier (High Security)
- **Subnet**: 172.20.4.0/24
- **Services**: MCP (Model Context Protocol) servers
- **Access**: Backend tier, AI tier, and monitoring
- **Security Level**: High

**Services:**
- `graphiti-mcp-server` - Graphiti MCP server
- `rag-mcp-server` - RAG MCP server
- `gmail-mcp-server` - Gmail MCP server
- `slack-mcp-server` - Slack MCP server

#### 5. Frontend Tier (Medium Security)
- **Subnet**: 172.20.5.0/24
- **Services**: User-facing services
- **Access**: External tier and backend tier
- **Security Level**: Medium

**Services:**
- `open-webui` - Web interface

#### 6. External Tier (Low Security)
- **Subnet**: 172.20.6.0/24
- **Services**: External-facing services
- **Access**: Frontend tier and external networks
- **Security Level**: Low

**Services:**
- `cloudflare-tunnel` - Cloudflare tunnel service

#### 7. Monitoring Tier (High Security)
- **Subnet**: 172.20.7.0/24
- **Services**: Monitoring and health services
- **Access**: All tiers for monitoring purposes
- **Security Level**: High

**Services:**
- `health-monitor` - Health monitoring service

#### 8. AI Services Tier (High Security)
- **Subnet**: 172.20.8.0/24
- **Services**: AI and LLM services
- **Access**: Backend tier and MCP tier
- **Security Level**: High

**Services:**
- `letta` - AI agent service
- `slackbot` - Slack bot service

## Security Policies

### Network Isolation Rules

#### Allow-List Approach
All network communication follows a deny-by-default policy with explicit allow rules:

1. **Database Tier Access**:
   - ✅ Supabase Internal Tier → Database Tier (port 5432)
   - ✅ Monitoring Tier → Database Tier (port 5432)
   - ❌ All other tiers → Database Tier

2. **Backend Tier Access**:
   - ✅ Frontend Tier → Backend Tier (port 5678)
   - ✅ Supabase Internal Tier → Backend Tier (ports 3000, 9999, 4000, 8080)
   - ✅ Monitoring Tier → Backend Tier (port 8080)
   - ❌ External Tier → Backend Tier

3. **MCP Services Access**:
   - ✅ Backend Tier → MCP Tier (port 8080)
   - ✅ AI Tier → MCP Tier (port 8080)
   - ✅ Monitoring Tier → MCP Tier (port 8080)
   - ❌ External Tier → MCP Tier

4. **Frontend Tier Access**:
   - ✅ External Tier → Frontend Tier (ports 80, 443)
   - ✅ Backend Tier → Frontend Tier
   - ✅ Monitoring Tier → Frontend Tier (port 8080)
   - ❌ Database Tier → Frontend Tier

5. **AI Services Access**:
   - ✅ Backend Tier → AI Tier (port 8283)
   - ✅ MCP Tier → AI Tier (port 8080)
   - ✅ Monitoring Tier → AI Tier (port 8283)
   - ❌ External Tier → AI Tier

### Firewall Configuration

#### Network Security Features
- **Inter-Container Communication (ICC)**: Disabled on all networks
- **IP Masquerading**: Enabled for external connectivity
- **Bridge Isolation**: Each tier uses isolated bridge networks
- **Subnet Isolation**: Each tier has dedicated subnet ranges

#### Traffic Flow Rules
```bash
# Example firewall rules (implemented via Docker networks)
# Database tier - only allow specific access
iptables -A DOCKER-USER -i br-pa-database-tier -o br-pa-supabase-internal -p tcp --dport 5432 -j ACCEPT
iptables -A DOCKER-USER -i br-pa-database-tier -o br-pa-monitoring-tier -p tcp --dport 5432 -j ACCEPT
iptables -A DOCKER-USER -i br-pa-database-tier -j DROP

# MCP tier - restrict to backend and AI access
iptables -A DOCKER-USER -i br-pa-mcp-tier -o br-pa-backend-tier -p tcp --dport 8080 -j ACCEPT
iptables -A DOCKER-USER -i br-pa-mcp-tier -o br-pa-ai-tier -p tcp --dport 8080 -j ACCEPT
iptables -A DOCKER-USER -i br-pa-mcp-tier -o br-pa-monitoring-tier -p tcp --dport 8080 -j ACCEPT
iptables -A DOCKER-USER -i br-pa-mcp-tier -j DROP
```

## Implementation

### Quick Start

#### 1. Deploy Secure Network Configuration
```bash
# Deploy with secure network segmentation
./scripts/network/network-security.sh deploy-secure
```

#### 2. Validate Network Isolation
```bash
# Validate that network isolation is working
./scripts/network/network-security.sh validate-isolation
```

#### 3. Monitor Network Security
```bash
# Monitor network security status
./scripts/network/network-security.sh monitor
```

### Manual Deployment

#### 1. Create Network Segmentation
```bash
# Create isolated networks
./scripts/network/network-security.sh create-segmentation
```

#### 2. Configure Firewall Rules
```bash
# Configure firewall policies
./scripts/network/network-security.sh configure-firewall
```

#### 3. Deploy Services
```bash
# Deploy services with secure configuration
docker-compose -f config/network/docker-compose.secure.yml up -d
```

## Security Validation

### Network Isolation Tests

#### Automated Testing
The network security script includes automated tests to validate isolation:

```bash
# Run isolation tests
./scripts/network/network-security.sh validate-isolation
```

#### Manual Testing
You can manually test network isolation:

```bash
# Test that frontend cannot access database
docker exec open-webui ping supabase-db

# Test that external cannot access MCP services
docker exec cloudflare-tunnel curl gmail-mcp-server:8080/health

# Test that backend can access database
docker exec n8n ping supabase-db
```

### Security Monitoring

#### Network Traffic Analysis
```bash
# Monitor network connections
netstat -tuln | grep -E "(172\.20\.|docker)"

# Check Docker network connectivity
docker network ls
docker network inspect pa-database-tier
```

#### Service Health Checks
```bash
# Check service health across tiers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Networks}}"
```

## Troubleshooting

### Common Issues

#### Services Cannot Communicate
**Problem**: Services in different tiers cannot reach each other.

**Solution**:
1. Check network configuration:
   ```bash
   docker network ls | grep pa-
   ```

2. Verify service placement:
   ```bash
   docker inspect <service-name> | grep NetworkMode
   ```

3. Check firewall rules:
   ```bash
   iptables -L DOCKER-USER
   ```

#### Network Creation Fails
**Problem**: Network creation fails with subnet conflicts.

**Solution**:
1. Check existing networks:
   ```bash
   docker network ls
   ```

2. Remove conflicting networks:
   ```bash
   docker network rm <network-name>
   ```

3. Recreate networks:
   ```bash
   ./scripts/network/network-security.sh create-segmentation
   ```

#### Service Startup Issues
**Problem**: Services fail to start with secure configuration.

**Solution**:
1. Check service logs:
   ```bash
   docker logs <service-name>
   ```

2. Verify environment variables:
   ```bash
   docker exec <service-name> env
   ```

3. Rollback if necessary:
   ```bash
   ./scripts/network/network-security.sh rollback
   ```

### Recovery Procedures

#### Network Recovery
If network configuration is corrupted:

```bash
# Stop all services
docker-compose -f config/network/docker-compose.secure.yml down

# Remove all custom networks
docker network ls | grep pa- | awk '{print $1}' | xargs docker network rm

# Recreate network segmentation
./scripts/network/network-security.sh create-segmentation

# Redeploy services
./scripts/network/network-security.sh deploy-secure
```

#### Service Recovery
If services fail to start:

```bash
# Check service status
docker ps -a

# Restart failed services
docker restart <failed-service>

# Check service health
docker exec <service-name> curl localhost:8080/health
```

## Security Best Practices

### Network Security
1. **Principle of Least Privilege**: Services only have access to required resources
2. **Defense in Depth**: Multiple layers of security controls
3. **Network Segmentation**: Isolate services by function and sensitivity
4. **Traffic Monitoring**: Monitor all network traffic for anomalies
5. **Regular Audits**: Regularly audit network configuration and access

### Access Control
1. **Allow-List Approach**: Deny all traffic by default, allow only necessary
2. **Port Restrictions**: Only open required ports for each service
3. **Protocol Restrictions**: Use secure protocols where possible
4. **Authentication**: Implement authentication for all service access
5. **Authorization**: Implement role-based access control

### Monitoring and Logging
1. **Network Monitoring**: Monitor all network traffic and connections
2. **Security Logging**: Log all security-relevant network events
3. **Anomaly Detection**: Detect unusual network patterns
4. **Incident Response**: Have procedures for security incidents
5. **Regular Reviews**: Regularly review network security configuration

## Advanced Configuration

### Custom Network Policies
You can create custom network policies for specific requirements:

```yaml
# Custom network policy example
networks:
  custom-tier:
    name: pa-custom-tier
    driver: bridge
    driver_opts:
      com.docker.network.bridge.enable_icc: "false"
    ipam:
      config:
        - subnet: 172.20.9.0/24
```

### Integration with External Security Tools
The network security framework can be integrated with external tools:

- **Calico**: For advanced network policies
- **Cilium**: For service mesh and security
- **Istio**: For service mesh security
- **Envoy**: For API gateway security

### Compliance and Standards
The network security implementation follows:

- **NIST Cybersecurity Framework**
- **ISO 27001** security controls
- **SOC 2** security requirements
- **Docker Security Best Practices**
- **Container Security Guidelines**

## Support and Maintenance

### Regular Maintenance
- **Weekly**: Review network connectivity and service health
- **Monthly**: Audit network security configuration
- **Quarterly**: Update security policies and procedures
- **Annually**: Review and update network architecture

### Documentation Updates
- Keep network diagrams current
- Update security procedures as needed
- Document any configuration changes
- Maintain incident response procedures

### Training and Awareness
- Train team members on network security
- Provide security awareness training
- Document troubleshooting procedures
- Maintain security best practices documentation
