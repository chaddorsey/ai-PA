# Cloudflare Tunnel Setup Guide

This guide walks through setting up Cloudflare tunnels for secure external access to the PA ecosystem.

## Prerequisites

- Cloudflare account (free tier available)
- Domain name registered and managed by Cloudflare
- Access to Cloudflare dashboard
- Docker environment with PA ecosystem running

## Step 1: Cloudflare Account Setup

### 1.1 Create Cloudflare Account
1. Go to [cloudflare.com](https://cloudflare.com) and sign up
2. Verify your email address
3. Complete account setup

### 1.2 Add Domain to Cloudflare
1. Log into Cloudflare dashboard
2. Click "Add a Site" or "Add Site"
3. Enter your domain name (e.g., `yourdomain.com`)
4. Choose the free plan (sufficient for tunnels)
5. Cloudflare will scan your existing DNS records
6. Update nameservers at your domain registrar to point to Cloudflare

### 1.3 Verify Domain Configuration
1. Wait for DNS propagation (usually 5-15 minutes)
2. Verify domain is "Active" in Cloudflare dashboard
3. Check that SSL/TLS is set to "Full" or "Full (strict)"

## Step 2: Create Cloudflare Tunnel

### 2.1 Access Zero Trust Dashboard
1. In Cloudflare dashboard, go to "Zero Trust" (or "Cloudflare for Teams")
2. If prompted, choose the free tier
3. Complete the setup wizard

### 2.2 Create Tunnel
1. Go to "Access" → "Tunnels"
2. Click "Create a tunnel"
3. Enter tunnel name: `pa-ecosystem-tunnel`
4. Click "Save tunnel"

### 2.3 Configure Tunnel
1. Click "Next" to configure the tunnel
2. Choose "Cloudflared" as the connector
3. Copy the tunnel token (keep this secure!)

## Step 3: Configure DNS Records

### 3.1 Add DNS Records
In Cloudflare DNS dashboard, add the following CNAME records:

```
Type: CNAME
Name: letta
Content: [tunnel-id].cfargotunnel.com
Proxy: ✅ (orange cloud)

Type: CNAME  
Name: webui
Content: [tunnel-id].cfargotunnel.com
Proxy: ✅ (orange cloud)

Type: CNAME
Name: n8n  
Content: [tunnel-id].cfargotunnel.com
Proxy: ✅ (orange cloud)

Type: CNAME
Name: slackbot
Content: [tunnel-id].cfargotunnel.com
Proxy: ✅ (orange cloud)
```

### 3.2 Configure Tunnel Routes
1. Go back to the tunnel configuration
2. Add public hostnames for each service:

**Letta Service:**
- Subdomain: `letta`
- Domain: `yourdomain.com`
- Service: `http://letta:8283`
- Path: (leave empty)

**Open WebUI Service:**
- Subdomain: `webui`
- Domain: `yourdomain.com`  
- Service: `http://open-webui:8080`
- Path: (leave empty)

**n8n Service:**
- Subdomain: `n8n`
- Domain: `yourdomain.com`
- Service: `http://n8n:5678`
- Path: (leave empty)

**Slackbot Service:**
- Subdomain: `slackbot`
- Domain: `yourdomain.com`
- Service: `http://slackbot:8081`
- Path: (leave empty)

## Step 4: Environment Configuration

### 4.1 Add Environment Variables
Add the following to your `.env` file:

```bash
# Cloudflare Tunnel Configuration
CLOUDFLARE_TUNNEL_TOKEN=your_tunnel_token_here
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_ZONE_ID=your_zone_id
CLOUDFLARE_API_TOKEN=your_api_token
```

### 4.2 Get Required Values
- **Tunnel Token**: From tunnel creation step
- **Account ID**: Found in Cloudflare dashboard right sidebar
- **Zone ID**: Found in domain overview page
- **API Token**: Create in "My Profile" → "API Tokens"

## Step 5: Security Configuration

### 5.1 Configure Access Policies
1. Go to "Access" → "Applications"
2. Create applications for each service:

**Letta Application:**
- Application name: `Letta AI Assistant`
- Subdomain: `letta`
- Domain: `yourdomain.com`
- Policy: Configure as needed (e.g., email-based access)

**Open WebUI Application:**
- Application name: `Open WebUI`
- Subdomain: `webui`
- Domain: `yourdomain.com`
- Policy: Configure as needed

**n8n Application:**
- Application name: `n8n Workflow Automation`
- Subdomain: `n8n`
- Domain: `yourdomain.com`
- Policy: Configure as needed

**Slackbot Application:**
- Application name: `Slackbot Health Monitor`
- Subdomain: `slackbot`
- Domain: `yourdomain.com`
- Policy: Configure as needed

### 5.2 Configure WAF Rules
1. Go to "Security" → "WAF"
2. Create custom rules for additional protection
3. Consider rate limiting rules

## Step 6: SSL/TLS Configuration

### 6.1 SSL Settings
1. Go to "SSL/TLS" → "Overview"
2. Set encryption mode to "Full (strict)"
3. Enable "Always Use HTTPS"
4. Enable "HTTP Strict Transport Security (HSTS)"

### 6.2 Security Headers
1. Go to "Security" → "Settings"
2. Enable "Security Level: Medium"
3. Enable "Browser Integrity Check"
4. Configure additional security headers as needed

## Step 7: Testing Configuration

### 7.1 Test DNS Resolution
```bash
# Test each subdomain resolves
nslookup letta.yourdomain.com
nslookup webui.yourdomain.com
nslookup n8n.yourdomain.com
nslookup slackbot.yourdomain.com
```

### 7.2 Test SSL Certificates
```bash
# Check SSL certificate
openssl s_client -connect letta.yourdomain.com:443 -servername letta.yourdomain.com
```

## Troubleshooting

### Common Issues
1. **DNS not propagating**: Wait 15-30 minutes, check nameservers
2. **SSL certificate issues**: Ensure domain is fully active in Cloudflare
3. **Tunnel connection fails**: Verify tunnel token and network connectivity
4. **Service not accessible**: Check tunnel routes and service availability

### Debug Commands
```bash
# Test tunnel connectivity
cloudflared tunnel info

# Check tunnel status
cloudflared tunnel list

# Test specific service
curl -I https://letta.yourdomain.com
```

## Security Considerations

- Keep tunnel token secure and never commit to version control
- Use strong access policies for production environments
- Regularly rotate API tokens
- Monitor access logs for suspicious activity
- Consider using Cloudflare's free DDoS protection

## Next Steps

After completing this setup:
1. Test all services are accessible externally
2. Configure monitoring and alerting
3. Document access procedures
4. Set up backup access methods
5. Train team on new access methods
