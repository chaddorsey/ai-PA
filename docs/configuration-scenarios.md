# Configuration Scenarios Guide

**Pre-configured scenarios for different deployment types and use cases**

This guide provides specific configuration scenarios for different deployment types, helping you choose the right settings for your specific needs.

## 📋 Table of Contents

1. [Development Configuration](#development-configuration)
2. [Production Configuration](#production-configuration)
3. [Minimal Configuration](#minimal-configuration)
4. [High-Performance Configuration](#high-performance-configuration)
5. [Cost-Optimized Configuration](#cost-optimized-configuration)
6. [Security-Focused Configuration](#security-focused-configuration)
7. [External Access Configuration](#external-access-configuration)
8. [Custom Configuration](#custom-configuration)

## 🧪 Development Configuration

**Best for**: Local development, testing, debugging

### Key Characteristics
- Debug logging enabled
- Local access only
- Example API keys (replace with real ones)
- All features enabled for testing
- Resource-optimized for development

### Configuration Settings
```bash
# Debug and Logging
LETTA_DEBUG=true
OPENWEBUI_LOG_LEVEL=DEBUG
HAYHOOKS_LOG_LEVEL=DEBUG

# Features
ENABLE_TITLE_GENERATION=true
ENABLE_TAGS_GENERATION=true
ENABLE_WEB_SEARCH=true
ENABLE_OPENAI_API=true
ENABLE_OLLAMA_API=true

# Models (cost-effective for development)
LETTA_CHAT_MODEL=openai/gpt-4o-mini
LETTA_EMBEDDING_MODEL=openai/text-embedding-3-small
TASK_MODEL=openai/gpt-4o-mini
TASK_MODEL_EXTERNAL=openai/gpt-4o-mini

# Network (local only)
N8N_PROTOCOL=http
N8N_HOST=localhost
N8N_WEBHOOK_URL=http://localhost:5678
WEBHOOK_URL=http://localhost:5678

# External Access (disabled)
CLOUDFLARE_TUNNEL_TOKEN=
CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_ZONE_ID=
CLOUDFLARE_API_TOKEN=

# Optional Integrations (disabled for simplicity)
SLACK_BOT_TOKEN=
SLACK_APP_TOKEN=
SLACK_MCP_XOXP_TOKEN=
LETTA_AGENT_ID=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

### Resource Requirements
- **RAM**: 8GB minimum
- **CPU**: 4 cores
- **Storage**: 100GB
- **Network**: Local only

## 🏭 Production Configuration

**Best for**: Production deployments, live systems, team collaboration

### Key Characteristics
- Security-hardened settings
- Performance-optimized models
- External access ready
- Production-grade logging
- All integrations enabled

### Configuration Settings
```bash
# Debug and Logging
LETTA_DEBUG=false
OPENWEBUI_LOG_LEVEL=INFO
HAYHOOKS_LOG_LEVEL=INFO

# Features
ENABLE_TITLE_GENERATION=true
ENABLE_TAGS_GENERATION=true
ENABLE_WEB_SEARCH=true
ENABLE_OPENAI_API=true
ENABLE_OLLAMA_API=false

# Models (production-grade)
LETTA_CHAT_MODEL=openai/gpt-4o
LETTA_EMBEDDING_MODEL=openai/text-embedding-3-large
TASK_MODEL=openai/gpt-4o-mini
TASK_MODEL_EXTERNAL=openai/gpt-4o-mini

# Network (external access)
N8N_PROTOCOL=https
N8N_HOST=your-domain.com
N8N_WEBHOOK_URL=https://n8n.your-domain.com
WEBHOOK_URL=https://n8n.your-domain.com

# External Access (Cloudflare)
CLOUDFLARE_TUNNEL_TOKEN=your-tunnel-token
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_ZONE_ID=your-zone-id
CLOUDFLARE_API_TOKEN=your-api-token

# Integrations (enabled)
SLACK_BOT_TOKEN=your-slack-bot-token
SLACK_APP_TOKEN=your-slack-app-token
SLACK_MCP_XOXP_TOKEN=your-slack-user-token
LETTA_AGENT_ID=your-agent-id
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Security
POSTGRES_PASSWORD=your-super-secure-password-32-chars-minimum
N8N_ENCRYPTION_KEY=your-32-character-encryption-key-here
LITELLM_MASTER_KEY=your-litellm-master-key
```

### Resource Requirements
- **RAM**: 16GB+ recommended
- **CPU**: 8+ cores
- **Storage**: 200GB+
- **Network**: External access required

## 💡 Minimal Configuration

**Best for**: Resource-constrained environments, cost optimization, basic functionality

### Key Characteristics
- Essential features only
- Lightweight models
- Local access only
- Minimal resource usage
- Cost-optimized

### Configuration Settings
```bash
# Debug and Logging
LETTA_DEBUG=false
OPENWEBUI_LOG_LEVEL=WARNING
HAYHOOKS_LOG_LEVEL=WARNING

# Features (minimal)
ENABLE_TITLE_GENERATION=false
ENABLE_TAGS_GENERATION=false
ENABLE_WEB_SEARCH=false
ENABLE_OPENAI_API=true
ENABLE_OLLAMA_API=false

# Models (lightweight)
LETTA_CHAT_MODEL=openai/gpt-3.5-turbo
LETTA_EMBEDDING_MODEL=openai/text-embedding-3-small
TASK_MODEL=openai/gpt-3.5-turbo
TASK_MODEL_EXTERNAL=openai/gpt-3.5-turbo

# Network (local only)
N8N_PROTOCOL=http
N8N_HOST=localhost
N8N_WEBHOOK_URL=http://localhost:5678
WEBHOOK_URL=http://localhost:5678

# External Access (disabled)
CLOUDFLARE_TUNNEL_TOKEN=
CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_ZONE_ID=
CLOUDFLARE_API_TOKEN=

# Integrations (disabled)
SLACK_BOT_TOKEN=
SLACK_APP_TOKEN=
SLACK_MCP_XOXP_TOKEN=
LETTA_AGENT_ID=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# External APIs (disabled)
TAVILY_API_KEY=
GITHUB_API_KEY=
ZOTERO_LIBRARY_ID=
ZOTERO_API_KEY=
```

### Resource Requirements
- **RAM**: 4GB minimum
- **CPU**: 2 cores
- **Storage**: 50GB
- **Network**: Local only

## ⚡ High-Performance Configuration

**Best for**: High-traffic systems, enterprise deployments, maximum performance

### Key Characteristics
- Premium models for best quality
- Maximum resource allocation
- All features enabled
- Performance monitoring
- Scalable architecture

### Configuration Settings
```bash
# Debug and Logging
LETTA_DEBUG=false
OPENWEBUI_LOG_LEVEL=INFO
HAYHOOKS_LOG_LEVEL=INFO

# Features (all enabled)
ENABLE_TITLE_GENERATION=true
ENABLE_TAGS_GENERATION=true
ENABLE_WEB_SEARCH=true
ENABLE_OPENAI_API=true
ENABLE_OLLAMA_API=true

# Models (premium)
LETTA_CHAT_MODEL=openai/gpt-4o
LETTA_EMBEDDING_MODEL=openai/text-embedding-3-large
TASK_MODEL=openai/gpt-4o
TASK_MODEL_EXTERNAL=openai/gpt-4o

# Network (high-performance)
N8N_PROTOCOL=https
N8N_HOST=your-domain.com
N8N_WEBHOOK_URL=https://n8n.your-domain.com
WEBHOOK_URL=https://n8n.your-domain.com

# External Access (Cloudflare with CDN)
CLOUDFLARE_TUNNEL_TOKEN=your-tunnel-token
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_ZONE_ID=your-zone-id
CLOUDFLARE_API_TOKEN=your-api-token

# All Integrations
SLACK_BOT_TOKEN=your-slack-bot-token
SLACK_APP_TOKEN=your-slack-app-token
SLACK_MCP_XOXP_TOKEN=your-slack-user-token
LETTA_AGENT_ID=your-agent-id
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# External APIs
TAVILY_API_KEY=your-tavily-api-key
GITHUB_API_KEY=your-github-api-key
ZOTERO_LIBRARY_ID=your-zotero-library-id
ZOTERO_API_KEY=your-zotero-api-key

# Performance
OLLAMA_BASE_URL=http://host.docker.internal:11434
HAYHOOKS_SEARCH_SEARXNG_ENABLED=true
```

### Resource Requirements
- **RAM**: 32GB+ recommended
- **CPU**: 16+ cores
- **Storage**: 500GB+ (NVMe SSD)
- **Network**: 10 Gbps with redundancy

## 💰 Cost-Optimized Configuration

**Best for**: Budget-conscious deployments, cost monitoring, efficient resource usage

### Key Characteristics
- Cheapest available models
- Minimal API usage
- Local processing where possible
- Cost monitoring enabled
- Efficient resource allocation

### Configuration Settings
```bash
# Debug and Logging
LETTA_DEBUG=false
OPENWEBUI_LOG_LEVEL=WARNING
HAYHOOKS_LOG_LEVEL=WARNING

# Features (cost-effective)
ENABLE_TITLE_GENERATION=false
ENABLE_TAGS_GENERATION=false
ENABLE_WEB_SEARCH=false
ENABLE_OPENAI_API=true
ENABLE_OLLAMA_API=true

# Models (cheapest)
LETTA_CHAT_MODEL=openai/gpt-3.5-turbo
LETTA_EMBEDDING_MODEL=openai/text-embedding-3-small
TASK_MODEL=openai/gpt-3.5-turbo
TASK_MODEL_EXTERNAL=openai/gpt-3.5-turbo

# Network (local only)
N8N_PROTOCOL=http
N8N_HOST=localhost
N8N_WEBHOOK_URL=http://localhost:5678
WEBHOOK_URL=http://localhost:5678

# External Access (disabled)
CLOUDFLARE_TUNNEL_TOKEN=
CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_ZONE_ID=
CLOUDFLARE_API_TOKEN=

# Integrations (minimal)
SLACK_BOT_TOKEN=
SLACK_APP_TOKEN=
SLACK_MCP_XOXP_TOKEN=
LETTA_AGENT_ID=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# External APIs (disabled)
TAVILY_API_KEY=
GITHUB_API_KEY=
ZOTERO_LIBRARY_ID=
ZOTERO_API_KEY=

# Cost Optimization
OLLAMA_BASE_URL=http://host.docker.internal:11434
HAYHOOKS_SEARCH_SEARXNG_ENABLED=false
```

### Resource Requirements
- **RAM**: 8GB
- **CPU**: 4 cores
- **Storage**: 100GB
- **Network**: Local only

## 🔐 Security-Focused Configuration

**Best for**: High-security environments, compliance requirements, sensitive data

### Key Characteristics
- Maximum security settings
- Encrypted communications
- Audit logging enabled
- Access controls
- Compliance features

### Configuration Settings
```bash
# Debug and Logging (security-focused)
LETTA_DEBUG=false
OPENWEBUI_LOG_LEVEL=INFO
HAYHOOKS_LOG_LEVEL=INFO

# Features (security-optimized)
ENABLE_TITLE_GENERATION=true
ENABLE_TAGS_GENERATION=true
ENABLE_WEB_SEARCH=false
ENABLE_OPENAI_API=true
ENABLE_OLLAMA_API=false

# Models (secure)
LETTA_CHAT_MODEL=openai/gpt-4o
LETTA_EMBEDDING_MODEL=openai/text-embedding-3-large
TASK_MODEL=openai/gpt-4o-mini
TASK_MODEL_EXTERNAL=openai/gpt-4o-mini

# Network (HTTPS only)
N8N_PROTOCOL=https
N8N_HOST=your-secure-domain.com
N8N_WEBHOOK_URL=https://n8n.your-secure-domain.com
WEBHOOK_URL=https://your-secure-domain.com

# External Access (secure)
CLOUDFLARE_TUNNEL_TOKEN=your-tunnel-token
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_ZONE_ID=your-zone-id
CLOUDFLARE_API_TOKEN=your-api-token

# Security Settings
POSTGRES_PASSWORD=your-ultra-secure-password-64-chars-minimum
N8N_ENCRYPTION_KEY=your-64-character-encryption-key-here
LITELLM_MASTER_KEY=your-ultra-secure-litellm-master-key

# Integrations (secure)
SLACK_BOT_TOKEN=your-slack-bot-token
SLACK_APP_TOKEN=your-slack-app-token
SLACK_MCP_XOXP_TOKEN=your-slack-user-token
LETTA_AGENT_ID=your-agent-id

# External APIs (minimal for security)
TAVILY_API_KEY=
GITHUB_API_KEY=
ZOTERO_LIBRARY_ID=
ZOTERO_API_KEY=
```

### Resource Requirements
- **RAM**: 16GB+
- **CPU**: 8+ cores
- **Storage**: 200GB+ (encrypted)
- **Network**: Secure external access

## 🌐 External Access Configuration

**Best for**: Remote access, team collaboration, public-facing deployments

### Key Characteristics
- External access enabled
- Domain-based access
- HTTPS configuration
- Public webhook endpoints
- Team collaboration features

### Configuration Settings
```bash
# Debug and Logging
LETTA_DEBUG=false
OPENWEBUI_LOG_LEVEL=INFO
HAYHOOKS_LOG_LEVEL=INFO

# Features
ENABLE_TITLE_GENERATION=true
ENABLE_TAGS_GENERATION=true
ENABLE_WEB_SEARCH=true
ENABLE_OPENAI_API=true
ENABLE_OLLAMA_API=false

# Models
LETTA_CHAT_MODEL=openai/gpt-4o
LETTA_EMBEDDING_MODEL=openai/text-embedding-3-large
TASK_MODEL=openai/gpt-4o-mini
TASK_MODEL_EXTERNAL=openai/gpt-4o-mini

# Network (external access)
N8N_PROTOCOL=https
N8N_HOST=your-domain.com
N8N_WEBHOOK_URL=https://n8n.your-domain.com
WEBHOOK_URL=https://your-domain.com

# External Access (Cloudflare)
CLOUDFLARE_TUNNEL_TOKEN=your-tunnel-token
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_ZONE_ID=your-zone-id
CLOUDFLARE_API_TOKEN=your-api-token

# Integrations (team collaboration)
SLACK_BOT_TOKEN=your-slack-bot-token
SLACK_APP_TOKEN=your-slack-app-token
SLACK_MCP_XOXP_TOKEN=your-slack-user-token
LETTA_AGENT_ID=your-agent-id
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# External APIs
TAVILY_API_KEY=your-tavily-api-key
GITHUB_API_KEY=your-github-api-key
ZOTERO_LIBRARY_ID=your-zotero-library-id
ZOTERO_API_KEY=your-zotero-api-key
```

### Resource Requirements
- **RAM**: 16GB+
- **CPU**: 8+ cores
- **Storage**: 200GB+
- **Network**: External access with domain

## 🎨 Custom Configuration

**Best for**: Specific requirements, advanced users, custom deployments

### Key Characteristics
- Fully customizable
- All options available
- Advanced features
- Custom integrations
- Flexible architecture

### Configuration Process
1. **Start with Base Template**: Choose closest scenario
2. **Customize Features**: Enable/disable as needed
3. **Adjust Models**: Select appropriate models
4. **Configure Network**: Set up access as required
5. **Add Integrations**: Enable needed integrations
6. **Test Configuration**: Validate all settings

### Customization Areas
- **Model Selection**: Choose based on needs and budget
- **Feature Toggle**: Enable/disable specific features
- **Network Setup**: Configure access and security
- **Integration Selection**: Add required integrations
- **Performance Tuning**: Optimize for your use case

## 🔄 Configuration Switching

### Switching Between Scenarios
```bash
# Backup current configuration
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)

# Switch to new scenario
./deployment/scripts/select-template.sh
# Choose appropriate template

# Or manually update
nano .env
# Update configuration

# Validate configuration
./deployment/scripts/validate-config.sh

# Restart services
docker-compose restart
```

### Gradual Migration
1. **Start with Base**: Begin with closest scenario
2. **Add Features**: Gradually enable features
3. **Test Changes**: Validate each change
4. **Monitor Performance**: Watch resource usage
5. **Optimize**: Fine-tune based on results

## 📊 Configuration Comparison

| Scenario | RAM | CPU | Storage | Features | Cost | Security | External |
|----------|-----|-----|---------|----------|------|----------|----------|
| Development | 8GB | 4 cores | 100GB | All | Low | Basic | No |
| Production | 16GB+ | 8+ cores | 200GB+ | All | High | High | Yes |
| Minimal | 4GB | 2 cores | 50GB | Essential | Low | Basic | No |
| High-Performance | 32GB+ | 16+ cores | 500GB+ | All | Very High | High | Yes |
| Cost-Optimized | 8GB | 4 cores | 100GB | Essential | Very Low | Basic | No |
| Security-Focused | 16GB+ | 8+ cores | 200GB+ | Secure | High | Very High | Yes |
| External Access | 16GB+ | 8+ cores | 200GB+ | All | High | High | Yes |

---

**🎉 Configuration Complete!** Choose the scenario that best fits your needs, or use it as a starting point for custom configuration. Each scenario is optimized for specific use cases and requirements.
