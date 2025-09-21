# PA Ecosystem System Requirements

## Overview

This document defines the system requirements for deploying the Personal Assistant (PA) Ecosystem. The requirements are based on the current production system architecture and are designed to ensure reliable operation of all services.

## Hardware Requirements

### Minimum Requirements
- **CPU**: 4 cores (2.0 GHz or higher)
- **RAM**: 8 GB
- **Storage**: 100 GB available space
- **Network**: 100 Mbps internet connection

### Recommended Requirements
- **CPU**: 8 cores (2.5 GHz or higher)
- **RAM**: 16 GB
- **Storage**: 200 GB available space (SSD recommended)
- **Network**: 1 Gbps internet connection

### Storage Breakdown
- **Base System**: 20 GB
- **Docker Images**: 15 GB
- **Database Data**: 20 GB (initial, grows over time)
- **Service Data**: 10 GB (n8n workflows, Letta memory, etc.)
- **Logs**: 5 GB (with rotation)
- **Backups**: 30 GB (retention dependent)
- **Buffer**: 20 GB (for growth and temporary files)

## Operating System Requirements

### Supported Operating Systems
- **Ubuntu 20.04 LTS** (Primary support)
- **Ubuntu 22.04 LTS** (Primary support)
- **CentOS 8** (Secondary support)
- **Debian 11** (Secondary support)

### System Dependencies
- **Docker**: Version 20.10.0 or higher
- **Docker Compose**: Version 2.0.0 or higher
- **curl**: For health checks and API calls
- **jq**: For JSON processing (optional but recommended)

## Network Requirements

### Port Requirements
- **80**: HTTP (redirected to HTTPS)
- **443**: HTTPS (external access)
- **8080-8083**: Internal service health checks
- **5432**: PostgreSQL (internal only)
- **7474**: Neo4j (internal only)
- **7687**: Neo4j Bolt (internal only)

### Network Configuration
- **Internet Access**: Required for external API calls and updates
- **DNS Resolution**: Required for service discovery
- **Firewall**: Must allow inbound traffic on ports 80, 443
- **NAT**: Required for external access (if not using Cloudflare tunnels)

## Software Dependencies

### Core Dependencies
- **Docker Engine**: Container runtime
- **Docker Compose**: Multi-container orchestration
- **Git**: Version control (for updates)

### Optional Dependencies
- **jq**: JSON processing for scripts
- **htop**: System monitoring
- **curl**: HTTP client for health checks

## Environment Variables

### Required Environment Variables
- `POSTGRES_PASSWORD`: Database password
- `SUPABASE_ANON_KEY`: Supabase anonymous key
- `SUPABASE_SERVICE_KEY`: Supabase service key
- `N8N_ENCRYPTION_KEY`: n8n encryption key
- `N8N_WEBHOOK_URL`: n8n webhook URL
- `WEBHOOK_URL`: General webhook URL
- `CLOUDFLARE_TUNNEL_TOKEN`: Cloudflare tunnel token
- `ANTHROPIC_API_KEY`: Anthropic API key
- `GEMINI_API_KEY`: Google Gemini API key
- `OPENAI_API_KEY`: OpenAI API key
- `SLACK_BOT_TOKEN`: Slack bot token
- `SLACK_APP_TOKEN`: Slack app token
- `LETTA_AGENT_ID`: Letta agent identifier

### Optional Environment Variables
- `LETTA_DEBUG`: Enable debug mode (default: false)
- `OPENWEBUI_LOG_LEVEL`: Open WebUI log level (default: INFO)
- `ENABLE_TAGS_GENERATION`: Enable tag generation
- `ENABLE_TITLE_GENERATION`: Enable title generation
- `TASK_MODEL`: Task model configuration
- `TASK_MODEL_EXTERNAL`: External task model
- `ENABLE_OLLAMA_API`: Enable Ollama API
- `OLLAMA_BASE_URL`: Ollama base URL
- `RAG_EMBEDDING_ENGINE`: RAG embedding engine
- `RAG_EMBEDDING_MODEL`: RAG embedding model
- `LITELLM_MASTER_KEY`: LiteLLM master key
- `ENABLE_WEB_SEARCH`: Enable web search
- `WEB_SEARCH_ENGINE`: Web search engine
- `TAVILY_API_KEY`: Tavily API key
- `AUDIO_STT_ENGINE`: Audio speech-to-text engine

## Service-Specific Requirements

### Database Services
- **PostgreSQL**: 4 GB RAM, 20 GB storage
- **Neo4j**: 2 GB RAM, 10 GB storage

### AI Services
- **Letta**: 2 GB RAM, 5 GB storage
- **Open WebUI**: 1 GB RAM, 2 GB storage
- **Graphiti MCP**: 1 GB RAM, 2 GB storage
- **RAG MCP**: 1 GB RAM, 2 GB storage

### Automation Services
- **n8n**: 1 GB RAM, 5 GB storage
- **Slackbot**: 512 MB RAM, 1 GB storage

### External Access
- **Cloudflare Tunnel**: 256 MB RAM, minimal storage
- **Health Monitor**: 256 MB RAM, minimal storage

## Security Requirements

### File Permissions
- **Docker socket**: Read/write access for docker group
- **Configuration files**: 600 permissions (owner read/write only)
- **Environment files**: 600 permissions (owner read/write only)
- **Log files**: 644 permissions (owner read/write, group/other read)

### Network Security
- **Internal network**: Isolated Docker network (pa-internal)
- **External access**: Only through designated ports and services
- **API keys**: Stored in environment variables, never in code

### Data Security
- **Database encryption**: At rest and in transit
- **Backup encryption**: Optional but recommended
- **Log rotation**: Prevent log files from consuming excessive space

## Performance Requirements

### Startup Time
- **Full system startup**: ≤ 5 minutes
- **Individual service startup**: ≤ 2 minutes
- **Health check validation**: ≤ 30 seconds

### Resource Usage
- **CPU usage**: ≤ 70% under normal load
- **Memory usage**: ≤ 80% of available RAM
- **Disk I/O**: ≤ 100 MB/s sustained

### Availability
- **Service uptime**: ≥ 99% (excluding planned maintenance)
- **Health check response**: ≤ 5 seconds
- **API response time**: ≤ 2 seconds

## Monitoring Requirements

### Health Checks
- All services must implement health check endpoints
- Health checks must respond within 5 seconds
- Health checks must validate service functionality

### Logging
- All services must use structured JSON logging
- Log files must be rotated (10 MB max, 3 files retained)
- Logs must include service, component, and network labels

### Metrics
- System resource usage (CPU, memory, disk)
- Service response times
- Error rates and counts
- Network connectivity status

## Backup Requirements

### Data Backup
- **Database**: Daily automated backup
- **Configuration**: Daily automated backup
- **Service Data**: Daily automated backup
- **Retention**: 30 days minimum

### Backup Storage
- **Local storage**: Primary backup location
- **External storage**: Optional for disaster recovery
- **Encryption**: Optional but recommended

## Troubleshooting Requirements

### Diagnostic Tools
- System resource monitoring
- Network connectivity testing
- Service health checking
- Log analysis tools

### Common Issues
- Service startup failures
- Network connectivity problems
- Resource exhaustion
- Configuration errors
- API key issues

## Validation Criteria

### Pre-deployment Validation
- System requirements check
- Dependency installation verification
- Network connectivity validation
- Storage space verification
- Permission validation

### Post-deployment Validation
- All services healthy
- Network connectivity functional
- External access working
- API endpoints responding
- Database connectivity verified

## Notes

- Requirements are based on current production system analysis
- Minimum requirements may result in slower performance
- Recommended requirements provide optimal performance
- Storage requirements include growth buffer for data accumulation
- Network requirements assume standard home internet connection
- Security requirements follow Docker and container best practices
