# Configuration Documentation Index

**Complete guide to configuring the PA ecosystem**

This index provides access to all configuration-related documentation, helping you find the right information for your specific configuration needs.

## 📋 Table of Contents

1. [Configuration Reference](#configuration-reference)
2. [Configuration Scenarios](#configuration-scenarios)
3. [Configuration Troubleshooting](#configuration-troubleshooting)
4. [Environment Templates](#environment-templates)
5. [Configuration Tools](#configuration-tools)
6. [Quick Configuration Guide](#quick-configuration-guide)

## 📖 Configuration Reference

### [Main Configuration Reference](./configuration-reference.md)
**Complete reference for all configuration options**

- **Environment Variables**: All environment variables with descriptions
- **Service Configuration**: Service-specific settings and options
- **Network Configuration**: Network and security settings
- **Integration Configuration**: External service integrations
- **Performance Configuration**: Performance tuning options
- **Advanced Configuration**: Advanced customization options

**Best for**: Reference documentation, advanced users, complete configuration details

## 🎯 Configuration Scenarios

### [Configuration Scenarios Guide](./configuration-scenarios.md)
**Pre-configured scenarios for different deployment types**

- **Development Configuration**: Local development and testing
- **Production Configuration**: Production deployments and live systems
- **Minimal Configuration**: Resource-constrained environments
- **High-Performance Configuration**: Maximum performance deployments
- **Cost-Optimized Configuration**: Budget-conscious deployments
- **Security-Focused Configuration**: High-security environments
- **External Access Configuration**: Remote access and team collaboration
- **Custom Configuration**: Fully customizable deployments

**Best for**: Choosing the right configuration for your use case

## 🔧 Configuration Troubleshooting

### [Configuration Troubleshooting Guide](./configuration-troubleshooting.md)
**Common configuration issues and their solutions**

- **Configuration Validation Issues**: Missing variables, invalid formats
- **Environment Variable Issues**: Variable access and value problems
- **Service Configuration Issues**: Service startup and health problems
- **Network Configuration Issues**: Port conflicts, access problems
- **Security Configuration Issues**: Authentication and permission problems
- **Performance Configuration Issues**: Memory usage, response times
- **Integration Configuration Issues**: Slack, Gmail, external APIs
- **Advanced Troubleshooting**: Complex issues and solutions

**Best for**: Diagnosing and resolving configuration problems

## 📁 Environment Templates

### [Environment Templates](../deployment/templates/README.md)
**Pre-configured environment templates for different scenarios**

- **Development Template**: `development.env`
- **Production Template**: `production.env`
- **Minimal Template**: `minimal.env`
- **Cloudflare Template**: `cloudflare.env`
- **Local-Only Template**: `local-only.env`
- **Custom Template**: `custom.env`

**Best for**: Quick setup with pre-configured settings

## 🛠️ Configuration Tools

### Configuration Scripts
- **Template Selection**: `./deployment/scripts/select-template.sh`
- **Configuration Validation**: `./deployment/scripts/validate-config.sh`
- **Health Check**: `./deployment/scripts/health-check.sh`
- **Deployment Script**: `./deployment/deploy.sh`

### Configuration Commands
```bash
# Select configuration template
./deployment/scripts/select-template.sh

# Validate configuration
./deployment/scripts/validate-config.sh

# Check system health
./deployment/scripts/health-check.sh

# Deploy with configuration
./deployment/deploy.sh
```

## 🚀 Quick Configuration Guide

### Step 1: Choose Your Scenario
Select the configuration scenario that best fits your needs:

| Scenario | Use Case | Resource Requirements | Features |
|----------|----------|----------------------|----------|
| [Development](./configuration-scenarios.md#development-configuration) | Local development, testing | 8GB RAM, 4 cores, 100GB | All features, debug enabled |
| [Production](./configuration-scenarios.md#production-configuration) | Live systems, team collaboration | 16GB+ RAM, 8+ cores, 200GB+ | All features, external access |
| [Minimal](./configuration-scenarios.md#minimal-configuration) | Resource-constrained, cost optimization | 4GB RAM, 2 cores, 50GB | Essential features only |
| [High-Performance](./configuration-scenarios.md#high-performance-configuration) | Enterprise, high-traffic | 32GB+ RAM, 16+ cores, 500GB+ | All features, premium models |
| [Cost-Optimized](./configuration-scenarios.md#cost-optimized-configuration) | Budget-conscious | 8GB RAM, 4 cores, 100GB | Essential features, cheap models |
| [Security-Focused](./configuration-scenarios.md#security-focused-configuration) | High-security, compliance | 16GB+ RAM, 8+ cores, 200GB+ | Secure features, encryption |
| [External Access](./configuration-scenarios.md#external-access-configuration) | Remote access, public deployment | 16GB+ RAM, 8+ cores, 200GB+ | All features, external access |

### Step 2: Select Template
```bash
# Run template selection
./deployment/scripts/select-template.sh

# Choose your scenario:
# 1. Development
# 2. Production
# 3. Minimal
# 4. Cloudflare
# 5. Local-Only
# 6. Custom
```

### Step 3: Configure Environment
```bash
# Edit configuration file
nano .env

# Required configuration:
# - Replace all CHANGE_ME_* placeholders
# - Set your API keys
# - Configure passwords (minimum 32 characters)
# - Set webhook URLs if using external access
```

### Step 4: Validate Configuration
```bash
# Validate configuration
./deployment/scripts/validate-config.sh

# Expected output: All validation checks should pass
# Address any warnings or errors before proceeding
```

### Step 5: Deploy Services
```bash
# Deploy with configuration
./deployment/deploy.sh

# Or deploy with specific options:
# ./deployment/deploy.sh --interactive
# ./deployment/deploy.sh --non-interactive
# ./deployment/deploy.sh --quick
```

### Step 6: Verify Configuration
```bash
# Run health check
./deployment/scripts/health-check.sh

# Check individual services
curl -f http://localhost:8283/v1/health/  # Letta
curl -f http://localhost:8080/health       # Open WebUI
curl -f http://localhost:5678/healthz      # n8n
curl -f http://localhost:8083/health       # Health Monitor
```

## 🔍 Configuration Categories

### Essential Configuration
**Required for basic functionality**
- `OPENAI_API_KEY` - OpenAI API access
- `POSTGRES_PASSWORD` - Database password
- `N8N_ENCRYPTION_KEY` - n8n encryption
- `SUPABASE_ANON_KEY` - Supabase access
- `SUPABASE_SERVICE_KEY` - Supabase service access

### AI Model Configuration
**Controls AI model selection and behavior**
- `LETTA_CHAT_MODEL` - Primary chat model
- `LETTA_EMBEDDING_MODEL` - Embedding model
- `TASK_MODEL` - Task processing model
- `RAG_EMBEDDING_MODEL` - RAG embedding model

### Feature Configuration
**Enables/disables specific features**
- `ENABLE_TITLE_GENERATION` - Auto title generation
- `ENABLE_TAGS_GENERATION` - Auto tags generation
- `ENABLE_WEB_SEARCH` - Web search functionality
- `ENABLE_OPENAI_API` - OpenAI integration
- `ENABLE_OLLAMA_API` - Ollama integration

### Network Configuration
**Controls network access and security**
- `N8N_WEBHOOK_URL` - n8n webhook URL
- `WEBHOOK_URL` - General webhook URL
- `N8N_PROTOCOL` - Protocol (http/https)
- `N8N_HOST` - Hostname for access

### External Access Configuration
**Enables external access via tunnels**
- `CLOUDFLARE_TUNNEL_TOKEN` - Cloudflare tunnel
- `CLOUDFLARE_ACCOUNT_ID` - Cloudflare account
- `CLOUDFLARE_ZONE_ID` - Cloudflare zone
- `CLOUDFLARE_API_TOKEN` - Cloudflare API

### Integration Configuration
**External service integrations**
- `SLACK_BOT_TOKEN` - Slack bot integration
- `SLACK_APP_TOKEN` - Slack app integration
- `SLACK_MCP_XOXP_TOKEN` - Slack MCP integration
- `GOOGLE_CLIENT_ID` - Gmail integration
- `GOOGLE_CLIENT_SECRET` - Gmail OAuth

### Performance Configuration
**Performance tuning and optimization**
- `LETTA_DEBUG` - Debug logging
- `OPENWEBUI_LOG_LEVEL` - Open WebUI logging
- `HAYHOOKS_LOG_LEVEL` - Hayhooks logging
- `OLLAMA_BASE_URL` - Ollama service URL

## 📊 Configuration Comparison Matrix

| Feature | Development | Production | Minimal | High-Perf | Cost-Opt | Security | External |
|---------|-------------|------------|---------|-----------|----------|----------|----------|
| Debug Logging | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| All Features | ✅ | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ |
| External Access | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ |
| Premium Models | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ |
| Cost Optimization | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ |
| Security Hardening | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ |
| Resource Usage | Medium | High | Low | Very High | Low | High | High |

## 🆘 Getting Help

### Self-Help Resources
1. **Check Configuration Reference**: [configuration-reference.md](./configuration-reference.md)
2. **Review Configuration Scenarios**: [configuration-scenarios.md](./configuration-scenarios.md)
3. **Troubleshoot Issues**: [configuration-troubleshooting.md](./configuration-troubleshooting.md)
4. **Use Configuration Tools**: Run validation and health checks

### Configuration Tools
```bash
# Validate configuration
./deployment/scripts/validate-config.sh

# Check system health
./deployment/scripts/health-check.sh

# Select configuration template
./deployment/scripts/select-template.sh

# Deploy with configuration
./deployment/deploy.sh
```

### Common Issues
- **Missing Variables**: Add required environment variables
- **Invalid Formats**: Check API key and URL formats
- **Weak Passwords**: Use stronger passwords (32+ characters)
- **Port Conflicts**: Check for conflicting services
- **API Key Issues**: Verify API key validity and permissions

## 📚 Additional Resources

### Installation Documentation
- **Installation Guide**: [installation-guide.md](./installation-guide.md)
- **Quick Start Guide**: [quick-start.md](./quick-start.md)
- **Installation Index**: [installation-index.md](./installation-index.md)

### Deployment Documentation
- **Deployment Script**: [deployment/deploy.sh](../deployment/deploy.sh)
- **Environment Templates**: [deployment/templates/](../deployment/templates/)
- **Validation Scripts**: [deployment/scripts/](../deployment/scripts/)

### Troubleshooting Documentation
- **Main Troubleshooting**: [delivery/7/7-8.md](./delivery/7/7-8.md)
- **Configuration Troubleshooting**: [configuration-troubleshooting.md](./configuration-troubleshooting.md)
- **Health Check Script**: [deployment/scripts/health-check.sh](../deployment/scripts/health-check.sh)

---

**🎉 Configuration Complete!** This index provides comprehensive access to all configuration documentation. Choose the right guide for your needs and configure your PA ecosystem according to your specific requirements.
