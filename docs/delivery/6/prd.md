# PBI-6: Cloudflare Tunnel Integration - Secure External Access

[View in Backlog](../backlog.md#user-content-6)

## Overview

Integrate Cloudflare tunnels into the Docker setup to provide secure external access to the PA ecosystem services, enabling remote management and access while maintaining security best practices.

## Problem Statement

The current PA ecosystem lacks secure external access capabilities:
- No way to access services remotely without exposing ports directly to the internet
- Manual port forwarding creates security risks and management complexity
- No centralized external access management
- Difficult to provide secure access to specific services for different users
- No failover or reconnection handling for external access

This creates:
- Security vulnerabilities from direct port exposure
- Complex network configuration management
- No centralized access control
- Difficult remote troubleshooting and management
- Risk of service unavailability during network changes

## User Stories

### Primary User Story
**As an Operations Engineer**, I want external access via Cloudflare tunnels integrated into the Docker setup so that remote access is secure and properly managed.

### Supporting User Stories
- **As a System Administrator**, I want secure remote access to the PA ecosystem so that I can manage it from anywhere
- **As a Developer**, I want easy access to development services so that I can work remotely
- **As a Security Engineer**, I want centralized access control so that external access is properly secured
- **As a Home Server Owner**, I want reliable external access so that the system is accessible when needed

## Technical Approach

### Cloudflare Tunnel Architecture
```yaml
# Cloudflare tunnel service in docker-compose.yml
services:
  cloudflare-tunnel:
    image: cloudflare/cloudflared:latest
    container_name: cloudflare-tunnel
    restart: unless-stopped
    networks: [pa-network]
    environment:
      - TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN}
    command: tunnel --no-autoupdate run --token ${CLOUDFLARE_TUNNEL_TOKEN}
    depends_on:
      - letta
      - open-webui
      - n8n
    healthcheck:
      test: ["CMD", "cloudflared", "tunnel", "info"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
```

### Service Access Configuration
```yaml
# Tunnel configuration for different services
tunnel_config:
  services:
    letta:
      hostname: letta.yourdomain.com
      service: http://letta:8283
      originRequest:
        noTLSVerify: true
    webui:
      hostname: webui.yourdomain.com
      service: http://open-webui:8080
      originRequest:
        noTLSVerify: true
    n8n:
      hostname: n8n.yourdomain.com
      service: http://n8n:5678
      originRequest:
        noTLSVerify: true
    slackbot:
      hostname: slackbot.yourdomain.com
      service: http://slackbot:8081
      originRequest:
        noTLSVerify: true
```

### Security Configuration
- **Zero Trust Access**: Configure Cloudflare Zero Trust for additional security
- **Access Policies**: Implement role-based access control
- **WAF Rules**: Configure Web Application Firewall rules
- **DDoS Protection**: Leverage Cloudflare's DDoS protection
- **SSL/TLS**: Automatic SSL certificate management

### Environment Configuration
```bash
# Required environment variables
CLOUDFLARE_TUNNEL_TOKEN=your_tunnel_token_here
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_ZONE_ID=your_zone_id
CLOUDFLARE_API_TOKEN=your_api_token
```

## UX/UI Considerations

### Access Management
- **Centralized Dashboard**: Single point to manage all external access
- **Service Discovery**: Easy identification of available services
- **Status Monitoring**: Real-time status of tunnel connections
- **Access Logs**: Comprehensive logging of external access attempts

### User Experience
- **Seamless Access**: Transparent access to services without complex configuration
- **Mobile Friendly**: Responsive design for mobile access
- **Fast Connection**: Optimized routing through Cloudflare's global network
- **Reliable Uptime**: High availability with automatic failover

## Acceptance Criteria

### Functional Requirements
- [x] Cloudflare tunnel container deployed and running
- [x] All critical services accessible via secure external URLs
- [x] Tunnel configuration managed via environment variables
- [x] Automatic reconnection on tunnel failure
- [x] Health checks validate tunnel connectivity
- [x] SSL certificates automatically managed by Cloudflare

### Non-Functional Requirements
- [x] Tunnel connection established within 60 seconds of startup
- [x] External access latency < 200ms for all services
- [x] 99.9% uptime for tunnel connections
- [x] Automatic failover and reconnection within 30 seconds
- [x] Zero hardcoded credentials in configuration

### Security Requirements
- [x] All external access encrypted via TLS 1.3
- [x] No direct port exposure to internet
- [ ] Access control policies implemented
- [x] Audit logging for all external access
- [x] DDoS protection enabled

## Dependencies

### Technical Dependencies
- Cloudflare account with tunnel capability
- Domain name configured in Cloudflare
- Docker Compose infrastructure (PBI-2)
- Unified network configuration (PBI-3)
- All target services operational

### Process Dependencies
- **Upstream**:
  - PBI-2 (Docker Compose Unification) - required for service integration
  - PBI-3 (Network Unification) - required for internal communication
- **Downstream**:
  - PBI-7 (Deployment Kit) - tunnel configuration included in deployment
  - PBI-9 (Security Management) - tunnel security policies

## Open Questions

1. **Domain Strategy**: Should we use subdomains or paths for different services?
2. **Access Control**: What level of authentication/authorization is needed?
3. **Monitoring**: How should we monitor tunnel health and performance?
4. **Backup Access**: What happens if Cloudflare is unavailable?
5. **Cost Management**: How to optimize Cloudflare usage and costs?

## Related Tasks

Tasks for this PBI will be defined in [tasks.md](./tasks.md) following the implementation approach:

1. **Cloudflare Account Setup and Configuration**
2. **Tunnel Service Integration**
3. **Service Access Configuration**
4. **Security and Access Control Setup**
5. **Health Monitoring and Failover**
6. **Documentation and Operational Procedures**

---

**Back to**: [Project Backlog](../backlog.md)
