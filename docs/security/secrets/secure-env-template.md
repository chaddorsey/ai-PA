# Secure Environment Template

This document provides a secure environment template that follows security best practices for credential management in the PA ecosystem.

## Usage

1. Copy this template to your project root as `.env`
2. Use the secrets management framework to populate actual values
3. Never commit the actual `.env` file with real credentials

## Template Content

```bash
# PA Ecosystem Secure Environment Template
# This template follows security best practices for credential management
# Generated: 2025-01-21
# 
# SECURITY NOTICE:
# - All sensitive values should be managed via secrets-manager.sh
# - Never commit actual credentials to version control
# - Use strong, unique passwords for all services
# - Rotate credentials regularly (every 90 days)
# - Use environment-specific values for dev/staging/production

# =============================================================================
# SECRETS MANAGEMENT CONFIGURATION
# =============================================================================
# These variables control the secrets management framework
SECRETS_MANAGER_ENABLED=true
SECRETS_MANAGER_KEY_FILE=/app/config/secrets/master.key
SECRETS_ROTATION_DAYS=90
SECRETS_AUDIT_ENABLED=true

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================
# PostgreSQL Database Settings
# SECURITY: Use strong passwords (minimum 32 characters)
# Generated via: secrets-manager.sh store postgres-password "$(openssl rand -base64 32)"
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-}

# Supabase Configuration
# SECURITY: Use real JWT tokens from Supabase dashboard
# Generated via: secrets-manager.sh store supabase-anon-key "your-anon-key"
SUPABASE_ANON_KEY=${SUPABASE_ANON_KEY:-}
# Generated via: secrets-manager.sh store supabase-service-key "your-service-key"
SUPABASE_SERVICE_KEY=${SUPABASE_SERVICE_KEY:-}

# =============================================================================
# N8N WORKFLOW AUTOMATION
# =============================================================================
# N8N Configuration
# SECURITY: Use strong encryption keys (minimum 32 characters)
# Generated via: secrets-manager.sh store n8n-encryption-key "$(openssl rand -base64 32)"
N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY:-}

# N8N Network Configuration
N8N_WEBHOOK_URL=${N8N_WEBHOOK_URL:-http://localhost:5678}
WEBHOOK_URL=${WEBHOOK_URL:-http://localhost:5678}
N8N_PROTOCOL=${N8N_PROTOCOL:-http}
N8N_HOST=${N8N_HOST:-localhost}
N8N_EDITOR_BASE_URL=${N8N_EDITOR_BASE_URL:-http://localhost:5678}

# =============================================================================
# AI MODEL API KEYS
# =============================================================================
# OpenAI Configuration
# SECURITY: Store real API keys via secrets manager
# Generated via: secrets-manager.sh store openai-api-key "sk-your-actual-key"
OPENAI_API_KEY=${OPENAI_API_KEY:-}

# Anthropic Configuration
# Generated via: secrets-manager.sh store anthropic-api-key "sk-ant-your-actual-key"
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}

# Google Gemini Configuration
# Generated via: secrets-manager.sh store gemini-api-key "AIza-your-actual-key"
GEMINI_API_KEY=${GEMINI_API_KEY:-}

# =============================================================================
# SLACK INTEGRATION
# =============================================================================
# Slack Bot Configuration
# SECURITY: Use real tokens from Slack app configuration
# Generated via: secrets-manager.sh store slack-bot-token "xoxb-your-bot-token"
SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN:-}

# Slack App Configuration
# Generated via: secrets-manager.sh store slack-app-token "xapp-your-app-token"
SLACK_APP_TOKEN=${SLACK_APP_TOKEN:-}

# Slack MCP Token
# Generated via: secrets-manager.sh store slack-mcp-token "xoxp-your-user-token"
SLACK_MCP_XOXP_TOKEN=${SLACK_MCP_XOXP_TOKEN:-}

# Letta Agent Configuration
# Generated via: secrets-manager.sh store letta-agent-id "your-agent-id"
LETTA_AGENT_ID=${LETTA_AGENT_ID:-}
LETTA_BASE_URL=${LETTA_BASE_URL:-http://letta:8283}

# =============================================================================
# CLOUDFLARE TUNNEL CONFIGURATION
# =============================================================================
# Cloudflare Tunnel Token
# SECURITY: Use real tunnel token from Cloudflare dashboard
# Generated via: secrets-manager.sh store cloudflare-tunnel-token "your-tunnel-token"
CLOUDFLARE_TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN:-}

# =============================================================================
# SECURITY CONFIGURATION
# =============================================================================
# LiteLLM Master Key for API security
# Generated via: secrets-manager.sh store litellm-master-key "$(openssl rand -base64 32)"
LITELLM_MASTER_KEY=${LITELLM_MASTER_KEY:-}

# JWT Secret for session management
# Generated via: secrets-manager.sh store jwt-secret "$(openssl rand -base64 32)"
JWT_SECRET=${JWT_SECRET:-}

# Encryption key for sensitive data
# Generated via: secrets-manager.sh store data-encryption-key "$(openssl rand -base64 32)"
DATA_ENCRYPTION_KEY=${DATA_ENCRYPTION_KEY:-}

# =============================================================================
# EXTERNAL SERVICE INTEGRATIONS
# =============================================================================
# Web Search Configuration
ENABLE_WEB_SEARCH=${ENABLE_WEB_SEARCH:-false}
WEB_SEARCH_ENGINE=${WEB_SEARCH_ENGINE:-tavily}
# Generated via: secrets-manager.sh store tavily-api-key "your-tavily-key"
TAVILY_API_KEY=${TAVILY_API_KEY:-}

# Email Service Configuration (if using external email)
# Generated via: secrets-manager.sh store smtp-password "your-smtp-password"
SMTP_PASSWORD=${SMTP_PASSWORD:-}

# =============================================================================
# DEVELOPMENT AND DEBUGGING
# =============================================================================
# Debug Configuration
LETTA_DEBUG=${LETTA_DEBUG:-false}
OPENWEBUI_LOG_LEVEL=${OPENWEBUI_LOG_LEVEL:-INFO}

# Feature Flags
ENABLE_TAGS_GENERATION=${ENABLE_TAGS_GENERATION:-true}
ENABLE_TITLE_GENERATION=${ENABLE_TITLE_GENERATION:-true}

# Model Configuration
TASK_MODEL=${TASK_MODEL:-gpt-4}
TASK_MODEL_EXTERNAL=${TASK_MODEL_EXTERNAL:-gpt-4}

# =============================================================================
# OPTIONAL SERVICES
# =============================================================================
# Ollama Configuration (if using local models)
ENABLE_OLLAMA_API=${ENABLE_OLLAMA_API:-false}
OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://localhost:11434}

# RAG Configuration
RAG_EMBEDDING_ENGINE=${RAG_EMBEDDING_ENGINE:-openai}
RAG_EMBEDDING_MODEL=${RAG_EMBEDDING_MODEL:-text-embedding-ada-002}

# Audio STT Configuration
AUDIO_STT_ENGINE=${AUDIO_STT_ENGINE:-openai}

# =============================================================================
# SECURITY VALIDATION
# =============================================================================
# These variables are set by the security validation script
SECURITY_VALIDATION_PASSED=${SECURITY_VALIDATION_PASSED:-false}
SECURITY_LAST_AUDIT=${SECURITY_LAST_AUDIT:-}
SECURITY_NEXT_ROTATION=${SECURITY_NEXT_ROTATION:-}

# =============================================================================
# ENVIRONMENT SPECIFIC OVERRIDES
# =============================================================================
# Development Environment
if [ "${NODE_ENV:-}" = "development" ]; then
    LETTA_DEBUG=true
    OPENWEBUI_LOG_LEVEL=DEBUG
fi

# Production Environment
if [ "${NODE_ENV:-}" = "production" ]; then
    LETTA_DEBUG=false
    OPENWEBUI_LOG_LEVEL=WARN
    # Ensure all security features are enabled in production
    SECRETS_MANAGER_ENABLED=true
    SECRETS_AUDIT_ENABLED=true
fi
```

## Security Best Practices

### 1. Credential Storage
- Use `secrets-manager.sh` to store all sensitive values
- Never hardcode credentials in configuration files
- Reference stored secrets via environment variables

### 2. Password Requirements
- Minimum 32 characters for database passwords
- Use cryptographically secure random generators
- Rotate passwords every 90 days

### 3. API Key Security
- Store API keys via secrets manager
- Use environment-specific keys for dev/staging/prod
- Monitor API key usage and rotate regularly

### 4. Network Security
- Use HTTPS for all external communications
- Implement network segmentation
- Use firewall rules to restrict access

### 5. Audit and Monitoring
- Enable security auditing
- Monitor credential access and usage
- Set up alerts for security violations

## Implementation Steps

1. **Initialize Secrets Management**:
   ```bash
   ./scripts/secrets/secrets-manager.sh initialize
   ```

2. **Store Credentials**:
   ```bash
   ./scripts/secrets/secrets-manager.sh store postgres-password "$(openssl rand -base64 32)"
   ./scripts/secrets/secrets-manager.sh store openai-api-key "sk-your-actual-key"
   ```

3. **Generate Environment File**:
   ```bash
   ./scripts/secrets/secrets-manager.sh generate-env .env
   ```

4. **Run Security Audit**:
   ```bash
   ./scripts/audit/credential-audit.sh
   ```

## File Permissions

Set appropriate permissions for sensitive files:
```bash
chmod 600 .env                    # Environment file
chmod 700 config/secrets/         # Secrets directory
chmod 600 config/secrets/*.key    # Key files
```
