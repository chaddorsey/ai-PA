# PBI-3: Network Unification - Internal Service Communication

[View in Backlog](../backlog.md#user-content-3)

## Overview

Unify all inter-service communication on a single Docker network (pa-internal) so that services can communicate securely and efficiently without external dependencies, enabling reliable service discovery and eliminating hardcoded IP addresses throughout the system.

## Problem Statement

The current system has fragmented networking:
- Services use external networking with hardcoded IP addresses
- No unified service discovery mechanism
- Mixed internal and external communication patterns
- Potential security vulnerabilities from external service exposure
- Complex firewall and port management requirements

This creates operational challenges:
- Unreliable service communication when containers restart and get new IPs
- Security risks from unnecessary external service exposure
- Complex network troubleshooting across multiple networking patterns
- Difficult service scaling due to hardcoded network assumptions

## User Stories

### Primary User Story
**As a Network Administrator**, I want all inter-service communication on a unified Docker network so that services can communicate securely and efficiently without external dependencies.

### Supporting User Stories
- **As a Security Engineer**, I want internal-only service communication so that services are not unnecessarily exposed to external networks
- **As a DevOps Engineer**, I want reliable service discovery so that container restarts don't break inter-service communication
- **As a System Administrator**, I want simplified network management so that I can troubleshoot connectivity issues easily
- **As a Developer**, I want predictable service endpoints so that application configuration is stable and maintainable

## Technical Approach

### Unified Network Architecture
```yaml
# Single internal network for all services
networks:
  pa-network:
    name: pa-internal
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
    labels:
      - "project=pa-ecosystem"
      - "environment=production"
```

### Service Discovery Pattern
```yaml
# DNS-based service discovery
services:
  letta:
    networks: [pa-network]
    environment:
      - LETTA_PG_HOST=supabase-db      # DNS name, not IP
      - LETTA_PG_PORT=5432
      
  slackbot:
    networks: [pa-network]
    environment:
      - LETTA_BASE_URL=http://letta:8283    # DNS name, not IP
      
  n8n:
    networks: [pa-network]
    environment:
      - DB_POSTGRESDB_HOST=supabase-db      # DNS name, not IP
      
  gmail-mcp-server:
    networks: [pa-network]
    # Accessible via http://gmail-mcp-server:8080
    
  graphiti-mcp-server:
    networks: [pa-network]
    # Accessible via http://graphiti-mcp-server:8081
```

### External Access Pattern
```yaml
# Controlled external access via designated services
services:
  cloudflared:
    networks: [pa-network]
    ports:
      - "8080:8080"  # Only tunnel endpoint exposed
    environment:
      - TUNNEL_ORIGIN_CERT=${CLOUDFLARE_CERT}
      
  # Internal services - no external ports
  letta:
    networks: [pa-network]
    # No ports: [] - internal only
    
  supabase-db:
    networks: [pa-network]
    # No ports: [] - internal only (commented out in current config)
```

### Network Security Configuration
```yaml
# Network isolation and security
networks:
  pa-network:
    driver: bridge
    driver_opts:
      com.docker.network.bridge.enable_icc: "true"
      com.docker.network.bridge.enable_ip_masquerade: "true"
      com.docker.network.driver.mtu: "1500"
    ipam:
      driver: default
      config:
        - subnet: 172.20.0.0/16
          gateway: 172.20.0.1
```

### Migration Strategy

#### 1. Network Creation and Validation
- Create unified pa-internal network with proper subnet allocation
- Validate network isolation and internal connectivity
- Test DNS resolution between services

#### 2. Service-by-Service Migration
- **Phase 1**: Core services (database, Letta, n8n)
- **Phase 2**: MCP servers (Gmail, Graphiti, future RAG)
- **Phase 3**: Application services (Slackbot, Open WebUI)
- **Phase 4**: Infrastructure services (Cloudflare, monitoring)

#### 3. Configuration Updates
- Replace all hardcoded IP addresses with DNS names
- Update environment variables for internal service URLs
- Remove unnecessary external port exposures
- Validate service-to-service communication

#### 4. External Access Reconfiguration
- Ensure only necessary services expose external ports
- Configure Cloudflare tunnel for external access
- Validate security boundaries and access controls

### Health Check Integration
```yaml
# Network-aware health checks
services:
  letta:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8283/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    depends_on:
      supabase-db:
        condition: service_healthy
```

## UX/UI Considerations

### Administrative Experience
- **Simplified Networking**: Single network to monitor and manage
- **Predictable Endpoints**: Service URLs remain consistent across restarts
- **Clear Security Boundaries**: Easy to understand which services are externally accessible
- **Unified Monitoring**: Network traffic monitoring through single network interface

### Developer Experience
- **Reliable Service Discovery**: Services findable via predictable DNS names
- **Consistent Configuration**: Same patterns across all service configurations
- **Easy Debugging**: Network issues isolated to single network namespace
- **Simplified Testing**: Local development mirrors production networking

## Acceptance Criteria

### Functional Requirements
- [ ] All services connected to pa-internal network with DNS-based service discovery
- [ ] No hardcoded IP addresses in service configurations
- [ ] Service discovery works via DNS names (e.g., http://letta:8283)
- [ ] External access only via designated endpoints (Cloudflare tunnel)
- [ ] Network isolation prevents external access to internal services
- [ ] All current service communication functionality preserved

### Non-Functional Requirements
- [ ] Service-to-service communication latency equivalent to current setup
- [ ] Network startup time under 30 seconds
- [ ] DNS resolution time under 100ms for service discovery
- [ ] Network isolation validated - no unintended external access
- [ ] Network monitoring and logging integrated with existing observability

### Security Requirements
- [ ] Internal services not accessible from external networks
- [ ] Network traffic encrypted where appropriate (TLS for external connections)
- [ ] Service-to-service authentication maintained
- [ ] Network segmentation prevents unauthorized inter-service access
- [ ] External access audit trail maintained

## Dependencies

### Technical Dependencies
- Docker Engine with advanced networking support
- Docker Compose v2 with network configuration capabilities
- DNS resolution within Docker networks
- Service configuration management for environment variables

### Process Dependencies
- **Upstream**:
  - PBI-2 (Docker Compose Unification) - required for unified service deployment
- **Downstream**:
  - PBI-4 (MCP Standardization) - depends on internal network communication
  - PBI-5 (Slackbot Integration) - depends on internal service discovery
  - PBI-6 (Cloudflare Integration) - depends on network security boundaries

### Configuration Dependencies
- Update all service environment variables for internal communication
- Cloudflare tunnel configuration for external access
- Service health check updates for internal endpoints
- Monitoring configuration updates for network visibility

## Open Questions

1. **Network Subnet**: Is the chosen subnet (172.20.0.0/16) appropriate and conflict-free?
2. **DNS Caching**: Should DNS caching be configured for improved service discovery performance?
3. **Network Monitoring**: What level of network traffic monitoring should be implemented?
4. **Service Mesh**: Should a service mesh be considered for advanced networking features?
5. **Load Balancing**: Are load balancing capabilities needed for any services?
6. **Network Policies**: Should additional network policies be implemented for security?

## Related Tasks

Tasks for this PBI will be defined in [tasks.md](./tasks.md) following the implementation approach:

1. **Network Architecture Design**
2. **Unified Network Creation**
3. **Service Configuration Analysis**
4. **DNS-Based Service Discovery Implementation**
5. **Security Boundary Configuration**
6. **Service Migration to Internal Network**
7. **External Access Reconfiguration**
8. **Network Validation and Testing**
9. **Monitoring and Documentation**

---

**Back to**: [Project Backlog](../backlog.md)
