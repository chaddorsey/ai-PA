# Configuration Troubleshooting Guide

**Common configuration issues and their solutions**

This guide helps you diagnose and resolve common configuration issues in the PA ecosystem.

## 📋 Table of Contents

1. [Configuration Validation Issues](#configuration-validation-issues)
2. [Environment Variable Issues](#environment-variable-issues)
3. [Service Configuration Issues](#service-configuration-issues)
4. [Network Configuration Issues](#network-configuration-issues)
5. [Security Configuration Issues](#security-configuration-issues)
6. [Performance Configuration Issues](#performance-configuration-issues)
7. [Integration Configuration Issues](#integration-configuration-issues)
8. [Advanced Troubleshooting](#advanced-troubleshooting)

## 🔍 Configuration Validation Issues

### "Required variable not set"

#### Symptoms
- Configuration validation fails
- Services won't start
- Error messages about missing variables

#### Diagnosis
```bash
# Check validation output
./deployment/scripts/validate-config.sh

# Check specific variables
grep -E "^(OPENAI_API_KEY|POSTGRES_PASSWORD|N8N_ENCRYPTION_KEY)" .env
```

#### Solutions
```bash
# Add missing variables
nano .env

# Required variables:
OPENAI_API_KEY=sk-your-openai-api-key
POSTGRES_PASSWORD=your-secure-password-32-chars-minimum
SUPABASE_ANON_KEY=your-supabase-anon-key
SUPABASE_SERVICE_KEY=your-supabase-service-key
N8N_ENCRYPTION_KEY=your-32-character-encryption-key

# Validate again
./deployment/scripts/validate-config.sh
```

### "API key format invalid"

#### Symptoms
- API key validation fails
- Services can't authenticate
- Error messages about invalid key format

#### Diagnosis
```bash
# Check API key formats
echo "OpenAI: $OPENAI_API_KEY" | head -c 20
echo "Anthropic: $ANTHROPIC_API_KEY" | head -c 20
echo "Gemini: $GEMINI_API_KEY" | head -c 20
```

#### Solutions
```bash
# Fix OpenAI API key format
# Should start with 'sk-'
OPENAI_API_KEY=sk-proj-your-openai-api-key

# Fix Anthropic API key format
# Should start with 'sk-ant-'
ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key

# Fix Gemini API key format
# Should start with 'AIzaSy'
GEMINI_API_KEY=AIzaSy-your-gemini-api-key

# Validate configuration
./deployment/scripts/validate-config.sh
```

### "Password too short"

#### Symptoms
- Password validation fails
- Security warnings
- Database connection issues

#### Diagnosis
```bash
# Check password length
echo $POSTGRES_PASSWORD | wc -c
echo $N8N_ENCRYPTION_KEY | wc -c
```

#### Solutions
```bash
# Generate secure passwords
POSTGRES_PASSWORD=$(openssl rand -base64 32)
N8N_ENCRYPTION_KEY=$(openssl rand -base64 32)

# Update .env file
nano .env

# Validate configuration
./deployment/scripts/validate-config.sh
```

## 🔧 Environment Variable Issues

### "Variable not found"

#### Symptoms
- Services can't access environment variables
- Configuration errors
- Service startup failures

#### Diagnosis
```bash
# Check if .env file exists
ls -la .env

# Check file permissions
ls -la .env

# Check if variables are loaded
source .env
echo $OPENAI_API_KEY
```

#### Solutions
```bash
# Fix file permissions
chmod 600 .env

# Reload environment variables
source .env

# Restart services
docker-compose restart
```

### "Invalid variable value"

#### Symptoms
- Services behave unexpectedly
- Configuration errors
- Service crashes

#### Diagnosis
```bash
# Check variable values
grep -E "^(LETTA_CHAT_MODEL|TASK_MODEL)" .env

# Check service logs
docker-compose logs letta
```

#### Solutions
```bash
# Fix model names
LETTA_CHAT_MODEL=openai/gpt-4o-mini
TASK_MODEL=openai/gpt-4o-mini

# Fix boolean values
ENABLE_TITLE_GENERATION=true
ENABLE_TAGS_GENERATION=true

# Fix URL formats
N8N_WEBHOOK_URL=https://n8n.your-domain.com
WEBHOOK_URL=https://your-domain.com

# Restart services
docker-compose restart
```

## 🔧 Service Configuration Issues

### "Service won't start"

#### Symptoms
- Docker containers exit immediately
- Service status shows "Exited"
- Error messages in logs

#### Diagnosis
```bash
# Check service status
docker-compose ps

# Check service logs
docker-compose logs [service-name]

# Check resource usage
docker stats
```

#### Solutions
```bash
# Check configuration
./deployment/scripts/validate-config.sh

# Fix common issues:
# 1. Missing required variables
# 2. Invalid configuration values
# 3. Resource constraints
# 4. Port conflicts

# Restart service
docker-compose restart [service-name]
```

### "Service unhealthy"

#### Symptoms
- Health checks fail
- Services respond slowly
- Error messages in health check

#### Diagnosis
```bash
# Run health check
./deployment/scripts/health-check.sh

# Check individual services
curl -f http://localhost:8283/v1/health/
curl -f http://localhost:8080/health
curl -f http://localhost:5678/healthz
```

#### Solutions
```bash
# Check service logs
docker-compose logs [service-name]

# Common fixes:
# 1. Wait for services to fully start (2-3 minutes)
# 2. Check API key validity
# 3. Verify network connectivity
# 4. Check resource availability

# Restart services
docker-compose restart
```

## 🌐 Network Configuration Issues

### "Port already in use"

#### Symptoms
- Services can't bind to ports
- Port conflict errors
- Services won't start

#### Diagnosis
```bash
# Check port usage
lsof -i :8283
lsof -i :8080
lsof -i :5678
lsof -i :8083

# Check Docker port mapping
docker-compose ps
```

#### Solutions
```bash
# Kill conflicting processes
sudo kill -9 [PID]

# Or change ports in .env
# Update service URLs accordingly
N8N_WEBHOOK_URL=http://localhost:5679
WEBHOOK_URL=http://localhost:5679

# Restart services
docker-compose restart
```

### "Can't access web interfaces"

#### Symptoms
- Web interfaces not accessible
- Connection refused errors
- Timeout errors

#### Diagnosis
```bash
# Check if services are running
docker-compose ps

# Check port accessibility
netstat -tlnp | grep -E "(8283|8080|5678|8083)"

# Test local access
curl -f http://localhost:8283/v1/health/
```

#### Solutions
```bash
# Check firewall settings
sudo ufw status
sudo firewall-cmd --list-all

# Allow ports through firewall
sudo ufw allow 8283/tcp
sudo ufw allow 8080/tcp
sudo ufw allow 5678/tcp
sudo ufw allow 8083/tcp

# Check Docker network
docker network ls
docker network inspect pa-ecosystem_default
```

### "External access not working"

#### Symptoms
- External URLs not accessible
- Cloudflare tunnel errors
- Domain resolution issues

#### Diagnosis
```bash
# Check Cloudflare tunnel status
docker-compose logs cloudflare-tunnel

# Test external URLs
curl -f https://your-domain.com/health

# Check DNS resolution
nslookup your-domain.com
```

#### Solutions
```bash
# Check Cloudflare configuration
CLOUDFLARE_TUNNEL_TOKEN=your-tunnel-token
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_ZONE_ID=your-zone-id
CLOUDFLARE_API_TOKEN=your-api-token

# Update webhook URLs
N8N_WEBHOOK_URL=https://n8n.your-domain.com
WEBHOOK_URL=https://your-domain.com

# Restart services
docker-compose restart
```

## 🔐 Security Configuration Issues

### "Authentication failed"

#### Symptoms
- API authentication errors
- Service authentication failures
- Access denied errors

#### Diagnosis
```bash
# Test API keys
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/models

curl -H "Authorization: Bearer $ANTHROPIC_API_KEY" \
     https://api.anthropic.com/v1/messages

curl -H "Authorization: Bearer $GEMINI_API_KEY" \
     https://generativelanguage.googleapis.com/v1/models
```

#### Solutions
```bash
# Verify API key validity
# Check API key format
# Ensure API keys have proper permissions
# Check API usage limits

# Update API keys if needed
OPENAI_API_KEY=sk-your-valid-openai-api-key
ANTHROPIC_API_KEY=sk-ant-your-valid-anthropic-api-key
GEMINI_API_KEY=AIzaSy-your-valid-gemini-api-key

# Restart services
docker-compose restart
```

### "Permission denied"

#### Symptoms
- File permission errors
- Access denied errors
- Service startup failures

#### Diagnosis
```bash
# Check file permissions
ls -la .env
ls -la deployment/

# Check Docker permissions
docker ps
```

#### Solutions
```bash
# Fix file permissions
chmod 600 .env
chmod 700 deployment/
chmod +x deployment/scripts/*.sh

# Fix Docker permissions
sudo usermod -aG docker $USER
newgrp docker

# Restart services
docker-compose restart
```

## ⚡ Performance Configuration Issues

### "High memory usage"

#### Symptoms
- System running slowly
- Out of memory errors
- Service crashes

#### Diagnosis
```bash
# Check memory usage
free -h
docker stats

# Check service memory limits
docker-compose config
```

#### Solutions
```bash
# Optimize memory usage
# 1. Reduce model complexity
LETTA_CHAT_MODEL=openai/gpt-3.5-turbo
LETTA_EMBEDDING_MODEL=openai/text-embedding-3-small

# 2. Disable unnecessary features
ENABLE_TITLE_GENERATION=false
ENABLE_TAGS_GENERATION=false
ENABLE_WEB_SEARCH=false

# 3. Increase system memory
# 4. Optimize Docker memory limits

# Restart services
docker-compose restart
```

### "Slow response times"

#### Symptoms
- Services respond slowly
- High latency
- Timeout errors

#### Diagnosis
```bash
# Check system resources
htop
df -h
iostat

# Check service logs
docker-compose logs [service-name]
```

#### Solutions
```bash
# Optimize performance
# 1. Use faster models
LETTA_CHAT_MODEL=openai/gpt-4o-mini
TASK_MODEL=openai/gpt-4o-mini

# 2. Enable caching
# 3. Optimize database queries
# 4. Use SSD storage
# 5. Increase CPU cores

# Restart services
docker-compose restart
```

## 🔗 Integration Configuration Issues

### "Slack integration not working"

#### Symptoms
- Slack bot not responding
- Slack authentication errors
- Integration failures

#### Diagnosis
```bash
# Check Slack configuration
grep -E "^(SLACK_BOT_TOKEN|SLACK_APP_TOKEN|LETTA_AGENT_ID)" .env

# Check Slack service logs
docker-compose logs slackbot
```

#### Solutions
```bash
# Verify Slack credentials
SLACK_BOT_TOKEN=xoxb-your-valid-bot-token
SLACK_APP_TOKEN=xapp-your-valid-app-token
SLACK_MCP_XOXP_TOKEN=xoxp-your-valid-user-token
LETTA_AGENT_ID=your-valid-agent-id

# Check Slack app configuration
# 1. Verify bot permissions
# 2. Check OAuth scopes
# 3. Verify webhook URLs
# 4. Check app installation

# Restart services
docker-compose restart slackbot letta
```

### "Gmail integration not working"

#### Symptoms
- Gmail MCP server errors
- OAuth authentication failures
- Email access issues

#### Diagnosis
```bash
# Check Gmail configuration
grep -E "^(GOOGLE_CLIENT_ID|GOOGLE_CLIENT_SECRET)" .env

# Check Gmail MCP logs
docker-compose logs gmail-mcp-server
```

#### Solutions
```bash
# Verify Google OAuth credentials
GOOGLE_CLIENT_ID=your-valid-client-id
GOOGLE_CLIENT_SECRET=your-valid-client-secret
GOOGLE_SCOPES=https://www.googleapis.com/auth/gmail.readonly

# Check Google OAuth configuration
# 1. Verify OAuth consent screen
# 2. Check redirect URIs
# 3. Verify API scopes
# 4. Check token storage

# Restart services
docker-compose restart gmail-mcp-server
```

## 🔧 Advanced Troubleshooting

### Configuration Reset

#### Complete Reset
```bash
# Backup current configuration
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)

# Reset to template
./deployment/scripts/select-template.sh

# Or restore from backup
cp .env.backup.YYYYMMDD_HHMMSS .env

# Validate and restart
./deployment/scripts/validate-config.sh
docker-compose restart
```

#### Partial Reset
```bash
# Reset specific service
docker-compose stop [service-name]
docker-compose rm [service-name]
docker-compose up -d [service-name]

# Reset specific configuration
# Edit .env file
nano .env

# Restart affected services
docker-compose restart
```

### Configuration Validation

#### Manual Validation
```bash
# Check all required variables
grep -E "^(OPENAI_API_KEY|POSTGRES_PASSWORD|N8N_ENCRYPTION_KEY)" .env

# Check API key formats
echo $OPENAI_API_KEY | grep -E "^sk-"
echo $ANTHROPIC_API_KEY | grep -E "^sk-ant-"
echo $GEMINI_API_KEY | grep -E "^AIzaSy"

# Check password strength
echo $POSTGRES_PASSWORD | wc -c
echo $N8N_ENCRYPTION_KEY | wc -c

# Check URL formats
echo $N8N_WEBHOOK_URL | grep -E "^https?://"
echo $WEBHOOK_URL | grep -E "^https?://"
```

#### Automated Validation
```bash
# Run full validation
./deployment/scripts/validate-config.sh

# Check specific categories
grep -E "^(OPENAI|ANTHROPIC|GEMINI)_API_KEY" .env
grep -E "^(POSTGRES|NEO4J)_PASSWORD" .env
grep -E "^(N8N|WEBHOOK)_URL" .env
```

### Configuration Testing

#### Service Testing
```bash
# Test individual services
curl -f http://localhost:8283/v1/health/
curl -f http://localhost:8080/health
curl -f http://localhost:5678/healthz
curl -f http://localhost:8083/health

# Test API connectivity
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/models
```

#### Integration Testing
```bash
# Test Slack integration
# Send message to Slack bot
# Verify response

# Test Gmail integration
# Check Gmail MCP server status
# Verify email access

# Test external access
curl -f https://your-domain.com/health
```

## 📚 Additional Resources

### Configuration Documentation
- **Main Configuration Reference**: [configuration-reference.md](./configuration-reference.md)
- **Configuration Scenarios**: [configuration-scenarios.md](./configuration-scenarios.md)
- **Environment Templates**: [deployment/templates/README.md](../deployment/templates/README.md)

### Troubleshooting Tools
- **Health Check**: `./deployment/scripts/health-check.sh`
- **Configuration Validation**: `./deployment/scripts/validate-config.sh`
- **Service Logs**: `docker-compose logs [service-name]`

### Getting Help
- **Check Logs**: `docker-compose logs -f`
- **Run Diagnostics**: `./deployment/scripts/health-check.sh`
- **Validate Configuration**: `./deployment/scripts/validate-config.sh`
- **Review Documentation**: Check relevant guides

---

**🆘 Still having issues?** If you can't resolve the configuration issue using this guide, check the main troubleshooting guide or reach out to the community for support.
