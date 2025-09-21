# Cloudflare Tunnel Configuration Details

This document provides detailed configuration information for the PA ecosystem Cloudflare tunnel setup.

## Tunnel Configuration File

### Basic Tunnel Config
```yaml
tunnel: pa-ecosystem-tunnel
credentials-file: /root/.cloudflared/[tunnel-id].json

# Ingress rules for service routing
ingress:
  # Letta AI Assistant
  - hostname: letta.yourdomain.com
    service: http://letta:8283
    originRequest:
      noTLSVerify: true
      connectTimeout: 30s
      tlsTimeout: 10s
      tcpKeepAlive: 30s
      keepAliveConnections: 10
      keepAliveTimeout: 1m30s
      httpHostHeader: letta.yourdomain.com

  # Open WebUI
  - hostname: webui.yourdomain.com
    service: http://open-webui:8080
    originRequest:
      noTLSVerify: true
      connectTimeout: 30s
      tlsTimeout: 10s
      tcpKeepAlive: 30s
      keepAliveConnections: 10
      keepAliveTimeout: 1m30s
      httpHostHeader: webui.yourdomain.com

  # n8n Workflow Automation
  - hostname: n8n.yourdomain.com
    service: http://n8n:5678
    originRequest:
      noTLSVerify: true
      connectTimeout: 30s
      tlsTimeout: 10s
      tcpKeepAlive: 30s
      keepAliveConnections: 10
      keepAliveTimeout: 1m30s
      httpHostHeader: n8n.yourdomain.com

  # Slackbot Health Monitor
  - hostname: slackbot.yourdomain.com
    service: http://slackbot:8081
    originRequest:
      noTLSVerify: true
      connectTimeout: 30s
      tlsTimeout: 10s
      tcpKeepAlive: 30s
      keepAliveConnections: 10
      keepAliveTimeout: 1m30s
      httpHostHeader: slackbot.yourdomain.com

  # Catch-all rule (must be last)
  - service: http_status:404
```

## Docker Compose Integration

### Cloudflare Tunnel Service
```yaml
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
    - slackbot
  healthcheck:
    test: ["CMD", "cloudflared", "tunnel", "info"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 30s
  logging:
    driver: "json-file"
    options:
      max-size: "10m"
      max-file: "3"
  labels:
    - "service=cloudflare-tunnel"
    - "component=external-access"
    - "network=pa-internal"
```

## Environment Variables

### Required Variables
```bash
# Cloudflare Tunnel Configuration
CLOUDFLARE_TUNNEL_TOKEN=your_tunnel_token_here
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_ZONE_ID=your_zone_id
CLOUDFLARE_API_TOKEN=your_api_token

# Optional: Advanced Configuration
CLOUDFLARE_TUNNEL_LOG_LEVEL=info
CLOUDFLARE_TUNNEL_METRICS=localhost:8080
CLOUDFLARE_TUNNEL_PROTOCOL=http2
```

### Variable Descriptions
- **CLOUDFLARE_TUNNEL_TOKEN**: Token from tunnel creation (required)
- **CLOUDFLARE_ACCOUNT_ID**: Your Cloudflare account ID (for API calls)
- **CLOUDFLARE_ZONE_ID**: Your domain's zone ID (for DNS management)
- **CLOUDFLARE_API_TOKEN**: API token with appropriate permissions
- **CLOUDFLARE_TUNNEL_LOG_LEVEL**: Logging level (debug, info, warn, error)
- **CLOUDFLARE_TUNNEL_METRICS**: Metrics endpoint (optional)
- **CLOUDFLARE_TUNNEL_PROTOCOL**: Tunnel protocol (http2, quic)

## Service-Specific Configuration

### Letta Configuration
```yaml
# Letta-specific tunnel settings
letta:
  hostname: letta.yourdomain.com
  service: http://letta:8283
  originRequest:
    noTLSVerify: true
    connectTimeout: 30s
    tlsTimeout: 10s
    httpHostHeader: letta.yourdomain.com
    # Letta-specific headers
    httpHeaders:
      X-Forwarded-Proto: https
      X-Forwarded-For: $remote_addr
```

### Open WebUI Configuration
```yaml
# Open WebUI-specific tunnel settings
webui:
  hostname: webui.yourdomain.com
  service: http://open-webui:8080
  originRequest:
    noTLSVerify: true
    connectTimeout: 30s
    tlsTimeout: 10s
    httpHostHeader: webui.yourdomain.com
    # WebUI-specific headers
    httpHeaders:
      X-Forwarded-Proto: https
      X-Forwarded-For: $remote_addr
```

### n8n Configuration
```yaml
# n8n-specific tunnel settings
n8n:
  hostname: n8n.yourdomain.com
  service: http://n8n:5678
  originRequest:
    noTLSVerify: true
    connectTimeout: 30s
    tlsTimeout: 10s
    httpHostHeader: n8n.yourdomain.com
    # n8n-specific headers
    httpHeaders:
      X-Forwarded-Proto: https
      X-Forwarded-For: $remote_addr
```

### Slackbot Configuration
```yaml
# Slackbot-specific tunnel settings
slackbot:
  hostname: slackbot.yourdomain.com
  service: http://slackbot:8081
  originRequest:
    noTLSVerify: true
    connectTimeout: 30s
    tlsTimeout: 10s
    httpHostHeader: slackbot.yourdomain.com
    # Slackbot-specific headers
    httpHeaders:
      X-Forwarded-Proto: https
      X-Forwarded-For: $remote_addr
```

## Security Configuration

### Access Policies
```yaml
# Example access policy configuration
access_policies:
  letta:
    name: "Letta AI Assistant Access"
    rules:
      - email_domain: "yourcompany.com"
      - country: "US"
      - ip_ranges: ["192.168.1.0/24"]
  
  webui:
    name: "Open WebUI Access"
    rules:
      - email_domain: "yourcompany.com"
      - country: "US"
  
  n8n:
    name: "n8n Workflow Access"
    rules:
      - email_domain: "yourcompany.com"
      - country: "US"
  
  slackbot:
    name: "Slackbot Health Access"
    rules:
      - email_domain: "yourcompany.com"
      - country: "US"
```

### WAF Rules
```yaml
# Web Application Firewall rules
waf_rules:
  - name: "Rate Limiting"
    action: "block"
    expression: "rate(10m) > 100"
  
  - name: "SQL Injection Protection"
    action: "block"
    expression: "http.request.uri.query contains \"'\" or http.request.uri.query contains \"--\""
  
  - name: "XSS Protection"
    action: "block"
    expression: "http.request.uri.query contains \"<script>\" or http.request.uri.query contains \"javascript:\""
```

## Monitoring and Health Checks

### Health Check Configuration
```yaml
# Health check endpoints
health_checks:
  letta:
    url: "https://letta.yourdomain.com/v1/health/"
    expected_status: 200
    timeout: 10s
    interval: 30s
  
  webui:
    url: "https://webui.yourdomain.com/health"
    expected_status: 200
    timeout: 10s
    interval: 30s
  
  n8n:
    url: "https://n8n.yourdomain.com/healthz"
    expected_status: 200
    timeout: 10s
    interval: 30s
  
  slackbot:
    url: "https://slackbot.yourdomain.com/health"
    expected_status: 200
    timeout: 10s
    interval: 30s
```

### Metrics Collection
```yaml
# Metrics configuration
metrics:
  enabled: true
  port: 8080
  path: "/metrics"
  format: "prometheus"
  
  # Custom metrics
  custom_metrics:
    - name: "tunnel_connections"
      type: "gauge"
      description: "Number of active tunnel connections"
    
    - name: "service_health"
      type: "gauge"
      description: "Health status of each service (1=healthy, 0=unhealthy)"
```

## Troubleshooting

### Common Issues and Solutions

#### 1. Tunnel Connection Failed
```bash
# Check tunnel status
cloudflared tunnel info

# Check tunnel logs
docker-compose logs cloudflare-tunnel

# Verify tunnel token
echo $CLOUDFLARE_TUNNEL_TOKEN
```

#### 2. DNS Resolution Issues
```bash
# Check DNS propagation
dig letta.yourdomain.com
nslookup letta.yourdomain.com

# Check Cloudflare DNS
curl -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$CLOUDFLARE_ZONE_ID/dns_records"
```

#### 3. SSL Certificate Issues
```bash
# Check SSL certificate
openssl s_client -connect letta.yourdomain.com:443 -servername letta.yourdomain.com

# Check certificate details
curl -I https://letta.yourdomain.com
```

#### 4. Service Not Accessible
```bash
# Check service health
docker-compose ps
docker-compose logs letta

# Test internal connectivity
docker-compose exec cloudflare-tunnel curl http://letta:8283/v1/health/
```

### Debug Commands
```bash
# Enable debug logging
export CLOUDFLARE_TUNNEL_LOG_LEVEL=debug

# Test tunnel configuration
cloudflared tunnel ingress validate

# Check tunnel metrics
curl http://localhost:8080/metrics
```

## Performance Optimization

### Connection Pooling
```yaml
# Optimize connection settings
originRequest:
  keepAliveConnections: 10
  keepAliveTimeout: 1m30s
  connectTimeout: 30s
  tlsTimeout: 10s
  tcpKeepAlive: 30s
```

### Caching Configuration
```yaml
# Enable caching for static content
caching:
  enabled: true
  ttl: 3600
  static_content:
    - "*.css"
    - "*.js"
    - "*.png"
    - "*.jpg"
    - "*.gif"
```

### Compression
```yaml
# Enable compression
compression:
  enabled: true
  algorithms: ["gzip", "brotli"]
  min_size: 1024
```

## Backup and Recovery

### Configuration Backup
```bash
# Backup tunnel configuration
cp /root/.cloudflared/[tunnel-id].json /backup/
cp /root/.cloudflared/config.yml /backup/

# Backup environment variables
cp .env /backup/
```

### Recovery Procedures
```bash
# Restore tunnel configuration
cp /backup/[tunnel-id].json /root/.cloudflared/
cp /backup/config.yml /root/.cloudflared/

# Restart tunnel service
docker-compose restart cloudflare-tunnel
```

## Security Best Practices

1. **Token Security**: Never commit tunnel tokens to version control
2. **Access Control**: Use strong authentication policies
3. **Monitoring**: Set up alerts for suspicious activity
4. **Updates**: Keep cloudflared updated regularly
5. **Logging**: Enable comprehensive logging and monitoring
6. **Backup**: Regular backup of configuration and credentials
7. **Testing**: Regular testing of failover and recovery procedures
