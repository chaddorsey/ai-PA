# PA Ecosystem Configuration Reference

**Complete reference for all configuration options, environment variables, and settings**

This document provides comprehensive documentation for all configuration options available in the PA ecosystem. It serves as the definitive reference for system administrators, developers, and users who need to customize their deployment.

## 📋 Table of Contents

1. [Environment Variables Overview](#environment-variables-overview)
2. [Database Configuration](#database-configuration)
3. [AI Model Configuration](#ai-model-configuration)
4. [Service Configuration](#service-configuration)
5. [Network Configuration](#network-configuration)
6. [Security Configuration](#security-configuration)
7. [External Integration Configuration](#external-integration-configuration)
8. [Performance Configuration](#performance-configuration)
9. [Logging Configuration](#logging-configuration)
10. [Advanced Configuration](#advanced-configuration)

## 🔧 Environment Variables Overview

### Configuration File Location
- **Primary**: `.env` (project root)
- **Templates**: `deployment/templates/`
- **Validation**: `./deployment/scripts/validate-config.sh`

### Variable Categories
- **Required**: Essential for basic functionality
- **Optional**: Enhance functionality but not required
- **Advanced**: For power users and custom deployments
- **Deprecated**: Legacy options (avoid using)

## 🗄️ Database Configuration

### PostgreSQL Configuration

#### `POSTGRES_PASSWORD`
- **Type**: String
- **Required**: Yes
- **Description**: Password for PostgreSQL database
- **Minimum Length**: 32 characters
- **Security**: Use strong, unique password
- **Example**: `POSTGRES_PASSWORD=your-super-secure-password-32-chars-minimum`

#### `SUPABASE_ANON_KEY`
- **Type**: String
- **Required**: Yes
- **Description**: Supabase anonymous key for client-side access
- **Format**: JWT token
- **Example**: `SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`

#### `SUPABASE_SERVICE_KEY`
- **Type**: String
- **Required**: Yes
- **Description**: Supabase service key for server-side access
- **Format**: JWT token
- **Security**: Keep secret, server-side only
- **Example**: `SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`

#### `DATABASE_URL`
- **Type**: String
- **Required**: No (auto-generated)
- **Description**: Complete database connection URL
- **Format**: `postgresql://user:password@host:port/database`
- **Example**: `DATABASE_URL=postgresql://letta:letta@letta_db:5432/letta`

### Neo4j Configuration

#### `NEO4J_PASSWORD`
- **Type**: String
- **Required**: Yes
- **Description**: Password for Neo4j graph database
- **Minimum Length**: 8 characters
- **Example**: `NEO4J_PASSWORD=your-neo4j-password`

## 🤖 AI Model Configuration

### OpenAI Configuration

#### `OPENAI_API_KEY`
- **Type**: String
- **Required**: Yes
- **Description**: OpenAI API key for GPT models
- **Format**: `sk-...`
- **Security**: Keep secret, required for most AI functionality
- **Example**: `OPENAI_API_KEY=sk-proj-your-openai-api-key-here`

### Anthropic Configuration

#### `ANTHROPIC_API_KEY`
- **Type**: String
- **Required**: Yes
- **Description**: Anthropic API key for Claude models
- **Format**: `sk-ant-...`
- **Security**: Keep secret, required for Claude models
- **Example**: `ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key-here`

### Google Gemini Configuration

#### `GEMINI_API_KEY`
- **Type**: String
- **Required**: Yes
- **Description**: Google Gemini API key for Gemini models
- **Format**: `AIzaSy...`
- **Security**: Keep secret, required for Gemini models
- **Example**: `GEMINI_API_KEY=AIzaSy-your-gemini-api-key-here`

### Letta AI Agent Configuration

#### `LETTA_CHAT_MODEL`
- **Type**: String
- **Required**: Yes
- **Description**: Primary chat model for Letta AI agent
- **Format**: `provider/model-name`
- **Options**:
  - `openai/gpt-4o` - GPT-4 Omni (recommended)
  - `openai/gpt-4o-mini` - GPT-4 Omni Mini (cost-effective)
  - `anthropic/claude-sonnet-4` - Claude Sonnet 4
  - `google_ai/gemini-2.5-flash` - Gemini 2.5 Flash
  - `letta/letta-free` - Free Letta model
- **Example**: `LETTA_CHAT_MODEL=openai/gpt-4o`

#### `LETTA_EMBEDDING_MODEL`
- **Type**: String
- **Required**: Yes
- **Description**: Embedding model for Letta memory system
- **Format**: `provider/model-name`
- **Options**:
  - `openai/text-embedding-3-large` - High quality (recommended)
  - `openai/text-embedding-3-small` - Cost-effective
  - `letta/letta-free` - Free embedding model
- **Example**: `LETTA_EMBEDDING_MODEL=openai/text-embedding-3-large`

#### `LETTA_DEBUG`
- **Type**: Boolean
- **Required**: No
- **Description**: Enable debug logging for Letta
- **Default**: `false`
- **Options**: `true`, `false`
- **Example**: `LETTA_DEBUG=true`

#### `LETTA_PG_URI`
- **Type**: String
- **Required**: No (auto-generated)
- **Description**: PostgreSQL connection URI for Letta
- **Format**: `postgresql://user:password@host:port/database`
- **Example**: `LETTA_PG_URI=postgresql://postgres:password@supabase-db:5432/postgres`

## 🔧 Service Configuration

### n8n Workflow Configuration

#### `N8N_ENCRYPTION_KEY`
- **Type**: String
- **Required**: Yes
- **Description**: Encryption key for n8n data
- **Length**: 32+ characters
- **Security**: Generate with `openssl rand -base64 32`
- **Example**: `N8N_ENCRYPTION_KEY=your-32-character-encryption-key-here`

#### `N8N_WEBHOOK_URL`
- **Type**: String
- **Required**: Yes
- **Description**: Base URL for n8n webhooks
- **Format**: `http://host:port` or `https://domain.com`
- **Example**: `N8N_WEBHOOK_URL=https://n8n.your-domain.com`

#### `N8N_PROTOCOL`
- **Type**: String
- **Required**: No
- **Description**: Protocol for n8n access
- **Options**: `http`, `https`
- **Default**: `http`
- **Example**: `N8N_PROTOCOL=https`

#### `N8N_HOST`
- **Type**: String
- **Required**: No
- **Description**: Hostname for n8n access
- **Example**: `N8N_HOST=n8n.your-domain.com`

#### `N8N_EDITOR_BASE_URL`
- **Type**: String
- **Required**: No
- **Description**: Base URL for n8n editor
- **Example**: `N8N_EDITOR_BASE_URL=https://n8n.your-domain.com`

#### `WEBHOOK_URL`
- **Type**: String
- **Required**: Yes
- **Description**: General webhook URL for the system
- **Format**: `http://host:port` or `https://domain.com`
- **Example**: `WEBHOOK_URL=https://your-domain.com`

### Open WebUI Configuration

#### `OPENWEBUI_LOG_LEVEL`
- **Type**: String
- **Required**: No
- **Description**: Log level for Open WebUI
- **Options**: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- **Default**: `INFO`
- **Example**: `OPENWEBUI_LOG_LEVEL=DEBUG`

#### `ENABLE_OPENAI_API`
- **Type**: Boolean
- **Required**: No
- **Description**: Enable OpenAI API integration
- **Default**: `true`
- **Options**: `true`, `false`
- **Example**: `ENABLE_OPENAI_API=true`

#### `ENABLE_OLLAMA_API`
- **Type**: Boolean
- **Required**: No
- **Description**: Enable Ollama API integration
- **Default**: `false`
- **Options**: `true`, `false`
- **Example**: `ENABLE_OLLAMA_API=false`

#### `ENABLE_TITLE_GENERATION`
- **Type**: Boolean
- **Required**: No
- **Description**: Enable automatic title generation
- **Default**: `true`
- **Options**: `true`, `false`
- **Example**: `ENABLE_TITLE_GENERATION=true`

#### `ENABLE_TAGS_GENERATION`
- **Type**: Boolean
- **Required**: No
- **Description**: Enable automatic tags generation
- **Default**: `true`
- **Options**: `true`, `false`
- **Example**: `ENABLE_TAGS_GENERATION=true`

#### `TASK_MODEL`
- **Type**: String
- **Required**: No
- **Description**: Model for task processing
- **Format**: `provider/model-name`
- **Example**: `TASK_MODEL=openai/gpt-4o-mini`

#### `TASK_MODEL_EXTERNAL`
- **Type**: String
- **Required**: No
- **Description**: External model for task processing
- **Format**: `provider/model-name`
- **Example**: `TASK_MODEL_EXTERNAL=openai/gpt-4o-mini`

#### `RAG_EMBEDDING_ENGINE`
- **Type**: String
- **Required**: No
- **Description**: RAG embedding engine
- **Options**: `openai`, `ollama`, `transformers`
- **Default**: `openai`
- **Example**: `RAG_EMBEDDING_ENGINE=openai`

#### `RAG_EMBEDDING_MODEL`
- **Type**: String
- **Required**: No
- **Description**: RAG embedding model
- **Format**: `provider/model-name`
- **Example**: `RAG_EMBEDDING_MODEL=openai/text-embedding-3-large`

#### `ENABLE_WEB_SEARCH`
- **Type**: Boolean
- **Required**: No
- **Description**: Enable web search functionality
- **Default**: `false`
- **Options**: `true`, `false`
- **Example**: `ENABLE_WEB_SEARCH=true`

#### `WEB_SEARCH_ENGINE`
- **Type**: String
- **Required**: No
- **Description**: Web search engine
- **Options**: `tavily`, `searxng`
- **Default**: `tavily`
- **Example**: `WEB_SEARCH_ENGINE=tavily`

#### `AUDIO_STT_ENGINE`
- **Type**: String
- **Required**: No
- **Description**: Audio speech-to-text engine
- **Options**: `openai`, `whisper`, `deepgram`
- **Example**: `AUDIO_STT_ENGINE=openai`

## 🌐 Network Configuration

### External Access Configuration

#### `CLOUDFLARE_TUNNEL_TOKEN`
- **Type**: String
- **Required**: No
- **Description**: Cloudflare tunnel token for external access
- **Format**: JWT token
- **Example**: `CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoi...`

#### `CLOUDFLARE_ACCOUNT_ID`
- **Type**: String
- **Required**: No
- **Description**: Cloudflare account ID
- **Format**: 32-character hex string
- **Example**: `CLOUDFLARE_ACCOUNT_ID=2b1d33e2a3f153500e339d4ef41aa579`

#### `CLOUDFLARE_ZONE_ID`
- **Type**: String
- **Required**: No
- **Description**: Cloudflare zone ID
- **Format**: 32-character hex string
- **Example**: `CLOUDFLARE_ZONE_ID=b1fc18645deedcc2c35a2802ba240d1c`

#### `CLOUDFLARE_API_TOKEN`
- **Type**: String
- **Required**: No
- **Description**: Cloudflare API token
- **Format**: API token string
- **Example**: `CLOUDFLARE_API_TOKEN=iPKgtLb6hLK_V8QztebwVsb6iGXoVigpEzqzehxZ`

### Ngrok Configuration (Alternative)

#### `NGROK_AUTHTOKEN`
- **Type**: String
- **Required**: No
- **Description**: Ngrok authentication token
- **Format**: Auth token string
- **Example**: `NGROK_AUTHTOKEN=your-ngrok-auth-token`

#### `NGROK_DOMAIN`
- **Type**: String
- **Required**: No
- **Description**: Ngrok reserved domain
- **Format**: `subdomain.ngrok.app`
- **Example**: `NGROK_DOMAIN=your-bot.ngrok.app`

## 🔐 Security Configuration

### API Key Management

#### `LITELLM_MASTER_KEY`
- **Type**: String
- **Required**: No
- **Description**: LiteLLM master key for API access
- **Format**: `sk-...`
- **Security**: Keep secret, used for API authentication
- **Example**: `LITELLM_MASTER_KEY=sk-your-litellm-master-key`

### Password Security

#### Password Requirements
- **Minimum Length**: 32 characters
- **Character Types**: Mixed case, numbers, symbols
- **Uniqueness**: Unique per deployment
- **Rotation**: Regular rotation recommended

#### Password Generation
```bash
# Generate secure password
openssl rand -base64 32

# Generate encryption key
openssl rand -base64 32
```

## 🔗 External Integration Configuration

### Slack Integration

#### `SLACK_BOT_TOKEN`
- **Type**: String
- **Required**: No
- **Description**: Slack bot token for bot functionality
- **Format**: `xoxb-...`
- **Example**: `SLACK_BOT_TOKEN=xoxb-your-slack-bot-token`

#### `SLACK_APP_TOKEN`
- **Type**: String
- **Required**: No
- **Description**: Slack app token for app functionality
- **Format**: `xapp-...`
- **Example**: `SLACK_APP_TOKEN=xapp-your-slack-app-token`

#### `SLACK_MCP_XOXP_TOKEN`
- **Type**: String
- **Required**: No
- **Description**: Slack user token for MCP server
- **Format**: `xoxp-...`
- **Example**: `SLACK_MCP_XOXP_TOKEN=xoxp-your-slack-user-token`

#### `LETTA_AGENT_ID`
- **Type**: String
- **Required**: No
- **Description**: Letta agent ID for Slack integration
- **Format**: UUID string
- **Example**: `LETTA_AGENT_ID=agent-db696f15-ea99-4eb4-b1ab-f004d902d24d`

#### `LETTA_BASE_URL`
- **Type**: String
- **Required**: No
- **Description**: Base URL for Letta service
- **Format**: `http://host:port`
- **Default**: `http://letta:8283`
- **Example**: `LETTA_BASE_URL=http://letta:8283`

### Gmail Integration

#### `GOOGLE_CLIENT_ID`
- **Type**: String
- **Required**: No
- **Description**: Google OAuth client ID
- **Format**: `client-id.apps.googleusercontent.com`
- **Example**: `GOOGLE_CLIENT_ID=958840789786-lti6u43r4nri5g7029rrr90bo24pn0bm.apps.googleusercontent.com`

#### `GOOGLE_CLIENT_SECRET`
- **Type**: String
- **Required**: No
- **Description**: Google OAuth client secret
- **Format**: `GOCSPX-...`
- **Security**: Keep secret
- **Example**: `GOOGLE_CLIENT_SECRET=GOCSPX-your-google-client-secret`

#### `GOOGLE_SCOPES`
- **Type**: String
- **Required**: No
- **Description**: Google API scopes
- **Default**: `https://www.googleapis.com/auth/gmail.readonly`
- **Example**: `GOOGLE_SCOPES=https://www.googleapis.com/auth/gmail.readonly`

#### `GOOGLE_TOKENS_DIR`
- **Type**: String
- **Required**: No
- **Description**: Directory for Google OAuth tokens
- **Default**: `/data/google_tokens`
- **Example**: `GOOGLE_TOKENS_DIR=/data/google_tokens`

#### `GMAIL_MCP_HTTP_PORT`
- **Type**: Integer
- **Required**: No
- **Description**: HTTP port for Gmail MCP server
- **Default**: `8890`
- **Example**: `GMAIL_MCP_HTTP_PORT=8890`

### External API Keys

#### `TAVILY_API_KEY`
- **Type**: String
- **Required**: No
- **Description**: Tavily API key for web search
- **Format**: API key string
- **Example**: `TAVILY_API_KEY=tvly-your-tavily-api-key`

#### `GITHUB_API_KEY`
- **Type**: String
- **Required**: No
- **Description**: GitHub API key for repository access
- **Format**: `github_pat_...` or `ghp_...`
- **Example**: `GITHUB_API_KEY=github_pat_your-github-api-key`

#### `ZOTERO_LIBRARY_ID`
- **Type**: String
- **Required**: No
- **Description**: Zotero library ID for research integration
- **Format**: Numeric string
- **Example**: `ZOTERO_LIBRARY_ID=7428910`

#### `ZOTERO_API_KEY`
- **Type**: String
- **Required**: No
- **Description**: Zotero API key for research integration
- **Format**: API key string
- **Example**: `ZOTERO_API_KEY=dnz1cVrY2djNcMXiYBYxo8OJ`

## ⚡ Performance Configuration

### Ollama Configuration

#### `OLLAMA_BASE_URL`
- **Type**: String
- **Required**: No
- **Description**: Base URL for Ollama service
- **Format**: `http://host:port`
- **Default**: `http://host.docker.internal:11434`
- **Example**: `OLLAMA_BASE_URL=http://host.docker.internal:11434`

### Hayhooks Configuration

#### `HAYHOOKS_LOG_LEVEL`
- **Type**: String
- **Required**: No
- **Description**: Log level for Hayhooks service
- **Options**: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- **Default**: `INFO`
- **Example**: `HAYHOOKS_LOG_LEVEL=DEBUG`

#### `HAYHOOKS_BASE_URL`
- **Type**: String
- **Required**: No
- **Description**: Base URL for Hayhooks service
- **Format**: `http://host:port`
- **Default**: `http://hayhooks:1416`
- **Example**: `HAYHOOKS_BASE_URL=http://hayhooks:1416`

#### `HAYHOOKS_SEARCH_SEARXNG_ENABLED`
- **Type**: Boolean
- **Required**: No
- **Description**: Enable SearXNG search integration
- **Default**: `false`
- **Options**: `true`, `false`
- **Example**: `HAYHOOKS_SEARCH_SEARXNG_ENABLED=false`

## 📝 Logging Configuration

### Service Log Levels

#### Debug Logging
- **Letta**: `LETTA_DEBUG=true`
- **Open WebUI**: `OPENWEBUI_LOG_LEVEL=DEBUG`
- **Hayhooks**: `HAYHOOKS_LOG_LEVEL=DEBUG`

#### Production Logging
- **Letta**: `LETTA_DEBUG=false`
- **Open WebUI**: `OPENWEBUI_LOG_LEVEL=INFO`
- **Hayhooks**: `HAYHOOKS_LOG_LEVEL=INFO`

### Log Management
- **Docker Logs**: `docker-compose logs [service-name]`
- **Log Rotation**: Configured in Docker daemon
- **Log Storage**: `/var/lib/docker/containers/`

## 🔧 Advanced Configuration

### Custom Model Configuration

#### Model Selection Criteria
1. **Performance**: Response time and quality
2. **Cost**: API usage costs
3. **Availability**: Service reliability
4. **Features**: Specific capabilities needed

#### Model Switching
```bash
# Switch chat model
LETTA_CHAT_MODEL=anthropic/claude-sonnet-4

# Switch embedding model
LETTA_EMBEDDING_MODEL=openai/text-embedding-3-small

# Restart services
docker-compose restart letta
```

### Custom Service Configuration

#### Docker Compose Overrides
```yaml
# docker-compose.override.yml
version: '3.8'
services:
  letta:
    environment:
      - LETTA_DEBUG=true
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G
```

#### Custom Environment Files
```bash
# Use custom environment file
docker-compose --env-file custom.env up -d

# Override specific variables
LETTA_CHAT_MODEL=openai/gpt-4o docker-compose up -d
```

## 🔍 Configuration Validation

### Validation Script
```bash
# Validate all configuration
./deployment/scripts/validate-config.sh

# Check specific variables
grep -E "^(OPENAI_API_KEY|POSTGRES_PASSWORD)" .env
```

### Common Validation Issues
1. **Missing Required Variables**: Add missing variables
2. **Invalid Formats**: Check format requirements
3. **Weak Passwords**: Use stronger passwords
4. **Placeholder Values**: Replace CHANGE_ME_* values

## 📚 Configuration Examples

### Development Configuration
```bash
# Development environment
LETTA_DEBUG=true
OPENWEBUI_LOG_LEVEL=DEBUG
HAYHOOKS_LOG_LEVEL=DEBUG
ENABLE_TITLE_GENERATION=true
ENABLE_TAGS_GENERATION=true
```

### Production Configuration
```bash
# Production environment
LETTA_DEBUG=false
OPENWEBUI_LOG_LEVEL=INFO
HAYHOOKS_LOG_LEVEL=INFO
ENABLE_TITLE_GENERATION=true
ENABLE_TAGS_GENERATION=true
N8N_PROTOCOL=https
N8N_HOST=your-domain.com
```

### Minimal Configuration
```bash
# Minimal environment
LETTA_DEBUG=false
OPENWEBUI_LOG_LEVEL=WARNING
HAYHOOKS_LOG_LEVEL=WARNING
ENABLE_TITLE_GENERATION=false
ENABLE_TAGS_GENERATION=false
ENABLE_WEB_SEARCH=false
```

---

**🎉 Configuration Complete!** This reference provides comprehensive documentation for all configuration options in the PA ecosystem. Use this guide to customize your deployment according to your specific needs and requirements.
