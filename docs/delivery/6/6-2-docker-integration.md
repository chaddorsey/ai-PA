# Task 6-2: Docker Compose Integration Guide

This guide shows how to integrate the Cloudflare tunnel service into the Docker Compose setup.

## Docker Compose Service Added

The Cloudflare tunnel service has been added to `docker-compose.yml`:

```yaml
# --- Cloudflare Tunnel Service ---
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

## Environment Variables Required

Add these environment variables to your `.env` file:

```bash
# Cloudflare Tunnel Configuration
CLOUDFLARE_TUNNEL_TOKEN=your-tunnel-token-here
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_ZONE_ID=your-zone-id
CLOUDFLARE_API_TOKEN=your-api-token
```

## Setup Instructions

### Step 1: Create .env File
Create a `.env` file in the project root with the required environment variables.

### Step 2: Add Cloudflare Variables
Add the Cloudflare tunnel configuration variables to your `.env` file:

```bash
# Get these values from Cloudflare dashboard
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoiMTIzNDU2Nzg5MGFiY2RlZiIsInQiOiJhYmNkZWYxMjM0NTY3ODkiLCJzIjoiMTIzNDU2Nzg5MGFiY2RlZiJ9
CLOUDFLARE_ACCOUNT_ID=1234567890abcdef1234567890abcdef
CLOUDFLARE_ZONE_ID=abcdef1234567890abcdef1234567890ab
CLOUDFLARE_API_TOKEN=your-api-token-here
```

### Step 3: Start the Tunnel Service
```bash
# Start the Cloudflare tunnel service
docker-compose up -d cloudflare-tunnel

# Check tunnel status
docker-compose logs cloudflare-tunnel

# Verify tunnel is running
docker-compose ps cloudflare-tunnel
```

### Step 4: Test External Access
```bash
# Test each service
curl -I https://letta.cd-ai-pa.work
curl -I https://webui.cd-ai-pa.work
curl -I https://n8n.cd-ai-pa.work
curl -I https://slackbot.cd-ai-pa.work
```

## Service Dependencies

The tunnel service depends on:
- **letta** - AI assistant (port 8283)
- **open-webui** - Letta web interface (port 8080)
- **n8n** - Workflow automation (port 5678)
- **slackbot** - Slack integration (port 8081)

## Health Checks

The tunnel service includes:
- **Health check**: `cloudflared tunnel info`
- **Interval**: 30 seconds
- **Timeout**: 10 seconds
- **Retries**: 3 attempts
- **Start period**: 30 seconds

## Logging

Tunnel logs are configured with:
- **Driver**: json-file
- **Max size**: 10MB per file
- **Max files**: 3 files
- **Location**: Docker logs

## Troubleshooting

### Tunnel Not Starting
```bash
# Check tunnel logs
docker-compose logs cloudflare-tunnel

# Verify environment variables
docker-compose exec cloudflare-tunnel env | grep CLOUDFLARE

# Test tunnel token
docker-compose exec cloudflare-tunnel cloudflared tunnel info
```

### Service Not Accessible
```bash
# Check if services are running
docker-compose ps

# Test internal connectivity
docker-compose exec cloudflare-tunnel curl http://letta:8283/v1/health/

# Check tunnel routes in Cloudflare dashboard
```

### DNS Issues
```bash
# Check DNS resolution
nslookup letta.cd-ai-pa.work

# Verify SSL certificates
openssl s_client -connect letta.cd-ai-pa.work:443 -servername letta.cd-ai-pa.work
```

## Next Steps

After setting up the environment variables:
1. Start the tunnel service
2. Test external access to all services
3. Configure access policies in Cloudflare
4. Set up monitoring and alerting
5. Document operational procedures

## Security Considerations

- Keep tunnel token secure
- Use strong access policies
- Monitor access logs
- Regular security updates
- Backup configuration
