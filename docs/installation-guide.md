# PA Ecosystem Detailed Installation Guide

**Comprehensive step-by-step installation procedures for all deployment scenarios**

This guide provides detailed installation procedures for deploying the Personal Assistant ecosystem across different environments and use cases. It complements the quick start guides with comprehensive technical details and troubleshooting information.

## 📋 Table of Contents

1. [Prerequisites and System Requirements](#prerequisites-and-system-requirements)
2. [Installation Methods](#installation-methods)
3. [Environment-Specific Installations](#environment-specific-installations)
4. [Configuration Procedures](#configuration-procedures)
5. [Service-Specific Setup](#service-specific-setup)
6. [Verification and Testing](#verification-and-testing)
7. [Post-Installation Configuration](#post-installation-configuration)
8. [Troubleshooting](#troubleshooting)
9. [Maintenance and Updates](#maintenance-and-updates)

## 🔧 Prerequisites and System Requirements

### Hardware Requirements

#### Minimum Requirements
- **CPU**: 4 cores (2.0 GHz or higher)
- **RAM**: 8GB
- **Storage**: 100GB available space (SSD recommended)
- **Network**: 100 Mbps internet connection

#### Recommended Requirements
- **CPU**: 8+ cores (3.0 GHz or higher)
- **RAM**: 16GB+
- **Storage**: 200GB+ available space (NVMe SSD recommended)
- **Network**: 1 Gbps internet connection

#### Production Requirements
- **CPU**: 16+ cores (3.5 GHz or higher)
- **RAM**: 32GB+
- **Storage**: 500GB+ available space (NVMe SSD with RAID)
- **Network**: 10 Gbps internet connection with redundancy

### Operating System Support

#### Supported Linux Distributions
- **Ubuntu**: 20.04 LTS, 22.04 LTS
- **CentOS**: 8.x, Stream 9
- **Debian**: 11.x (Bullseye)
- **RHEL**: 8.x, 9.x
- **Rocky Linux**: 8.x, 9.x
- **AlmaLinux**: 8.x, 9.x

#### Supported macOS Versions
- **macOS**: 12.0 (Monterey) or later
- **Note**: macOS is supported for development and testing only

#### Unsupported Systems
- Windows (use WSL2 or Docker Desktop)
- FreeBSD
- Solaris
- Older Linux distributions

### Software Dependencies

#### Required Software
- **Docker**: 20.10.0 or later
- **Docker Compose**: 2.0.0 or later
- **Git**: 2.20.0 or later
- **curl**: 7.68.0 or later
- **wget**: 1.20.0 or later

#### Optional Software
- **Node.js**: 18.0.0 or later (for development)
- **Python**: 3.8.0 or later (for development)
- **jq**: 1.6.0 or later (for JSON processing)
- **htop**: 3.0.0 or later (for monitoring)

### Network Requirements

#### Port Requirements
- **8283**: Letta web interface
- **8080**: Open WebUI interface
- **5678**: n8n workflow interface
- **8083**: Health monitor
- **5432**: PostgreSQL database
- **7474**: Neo4j database
- **7687**: Neo4j Bolt protocol
- **8890**: Gmail MCP server
- **1416**: Hayhooks service

#### Firewall Configuration
```bash
# UFW (Ubuntu/Debian)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 8283/tcp  # Letta
sudo ufw allow 8080/tcp  # Open WebUI
sudo ufw allow 5678/tcp  # n8n
sudo ufw allow 8083/tcp  # Health Monitor
sudo ufw enable

# firewalld (CentOS/RHEL)
sudo firewall-cmd --permanent --add-port=8283/tcp
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --permanent --add-port=5678/tcp
sudo firewall-cmd --permanent --add-port=8083/tcp
sudo firewall-cmd --reload
```

### API Key Requirements

#### Required API Keys
- **OpenAI API Key**: [Get from OpenAI Platform](https://platform.openai.com/api-keys)
- **Anthropic API Key**: [Get from Anthropic Console](https://console.anthropic.com/settings/keys)
- **Google Gemini API Key**: [Get from Google AI Studio](https://aistudio.google.com/app/apikey)

#### Optional API Keys
- **Tavily API Key**: [Get from Tavily Dashboard](https://app.tavily.com/home)
- **GitHub API Key**: [Get from GitHub Settings](https://github.com/settings/tokens)
- **Zotero API Key**: [Get from Zotero Settings](https://www.zotero.org/settings/keys)

## 🚀 Installation Methods

### Method 1: Automated Installation (Recommended)

#### Quick Installation
```bash
# Clone repository
git clone https://github.com/your-org/ai-PA.git
cd ai-PA

# Make scripts executable
chmod +x deployment/deploy.sh deployment/scripts/*.sh

# Run automated installation
./deployment/deploy.sh
```

#### Interactive Installation
```bash
# Run with interactive wizard
./deployment/deploy.sh --interactive

# Follow prompts for:
# - System requirements validation
# - Dependency installation
# - Configuration setup
# - Service deployment
```

#### Non-Interactive Installation
```bash
# Run with pre-configured settings
./deployment/deploy.sh --non-interactive

# Requires pre-configured .env file
```

### Method 2: Manual Installation

#### Step 1: System Preparation
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y curl wget git nano htop

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Log out and back in for group changes
```

#### Step 2: Repository Setup
```bash
# Clone repository
git clone https://github.com/your-org/ai-PA.git
cd ai-PA

# Create necessary directories
mkdir -p deployment/logs deployment/config deployment/backups

# Set permissions
chmod +x deployment/deploy.sh deployment/scripts/*.sh
```

#### Step 3: Configuration
```bash
# Select configuration template
./deployment/scripts/select-template.sh

# Edit configuration
nano .env

# Validate configuration
./deployment/scripts/validate-config.sh
```

#### Step 4: Service Deployment
```bash
# Start services
docker-compose up -d

# Check service status
docker-compose ps

# Run health checks
./deployment/scripts/health-check.sh
```

### Method 3: Container-Based Installation

#### Using Docker Compose
```bash
# Clone repository
git clone https://github.com/your-org/ai-PA.git
cd ai-PA

# Configure environment
cp deployment/templates/development.env .env
nano .env

# Start services
docker-compose up -d

# Verify installation
docker-compose ps
```

#### Using Docker Swarm
```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.yml pa-ecosystem

# Check services
docker service ls
```

## 🏗️ Environment-Specific Installations

### Ubuntu 22.04 LTS Installation

#### System Preparation
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install prerequisites
sudo apt install -y apt-transport-https ca-certificates curl gnupg lsb-release software-properties-common

# Add Docker repository
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add user to docker group
sudo usermod -aG docker $USER
```

#### Service Configuration
```bash
# Enable Docker service
sudo systemctl enable docker
sudo systemctl start docker

# Configure Docker daemon
sudo nano /etc/docker/daemon.json
```

Add the following configuration:
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2"
}
```

### CentOS 8 Installation

#### System Preparation
```bash
# Update system
sudo dnf update -y

# Install prerequisites
sudo dnf install -y yum-utils device-mapper-persistent-data lvm2

# Add Docker repository
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# Install Docker
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Start and enable Docker
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group
sudo usermod -aG docker $USER
```

### Debian 11 Installation

#### System Preparation
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install prerequisites
sudo apt install -y apt-transport-https ca-certificates curl gnupg lsb-release

# Add Docker repository
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add user to docker group
sudo usermod -aG docker $USER
```

### macOS Installation

#### Prerequisites
```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Docker Desktop
brew install --cask docker

# Start Docker Desktop
open /Applications/Docker.app
```

#### Configuration
```bash
# Clone repository
git clone https://github.com/your-org/ai-PA.git
cd ai-PA

# Configure for macOS
export DOCKER_HOST=unix:///Users/$USER/.docker/run/docker.sock

# Run installation
./deployment/deploy.sh
```

## ⚙️ Configuration Procedures

### Environment Configuration

#### Template Selection
```bash
# List available templates
ls deployment/templates/

# Select template interactively
./deployment/scripts/select-template.sh

# Or copy template manually
cp deployment/templates/production.env .env
```

#### Configuration Validation
```bash
# Validate configuration
./deployment/scripts/validate-config.sh

# Check specific variables
grep -E "^(OPENAI_API_KEY|POSTGRES_PASSWORD|N8N_ENCRYPTION_KEY)" .env
```

#### Security Configuration
```bash
# Set secure file permissions
chmod 600 .env
chmod 700 deployment/

# Generate secure passwords
openssl rand -base64 32  # For POSTGRES_PASSWORD
openssl rand -base64 32  # For N8N_ENCRYPTION_KEY
```

### Database Configuration

#### PostgreSQL Configuration
```bash
# Check database status
docker-compose exec supabase-db pg_isready -U postgres

# Connect to database
docker-compose exec supabase-db psql -U postgres

# Create additional databases if needed
CREATE DATABASE letta;
CREATE DATABASE n8n;
```

#### Neo4j Configuration
```bash
# Check Neo4j status
docker-compose exec neo4j cypher-shell -u neo4j -p $NEO4J_PASSWORD

# Create indexes
CREATE INDEX ON :Node(property);
CREATE CONSTRAINT ON (n:Node) ASSERT n.id IS UNIQUE;
```

### Network Configuration

#### Docker Network Setup
```bash
# Create custom network
docker network create pa-internal

# Check network configuration
docker network ls
docker network inspect pa-internal
```

#### Port Configuration
```bash
# Check port usage
netstat -tlnp | grep -E "(8283|8080|5678|8083)"

# Configure port forwarding if needed
sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8080
```

## 🔧 Service-Specific Setup

### Letta AI Agent Setup

#### Configuration
```bash
# Check Letta configuration
docker-compose exec letta env | grep LETTA

# Update Letta configuration
nano .env
# Update LETTA_CHAT_MODEL, LETTA_EMBEDDING_MODEL, etc.

# Restart Letta service
docker-compose restart letta
```

#### Memory Configuration
```bash
# Check memory usage
docker stats letta

# Adjust memory limits in docker-compose.yml
services:
  letta:
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G
```

### Open WebUI Setup

#### Model Configuration
```bash
# Check available models
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/models

# Configure models in .env
TASK_MODEL=openai/gpt-4o-mini
TASK_MODEL_EXTERNAL=openai/gpt-4o-mini
RAG_EMBEDDING_MODEL=openai/text-embedding-3-small
```

#### Feature Configuration
```bash
# Enable/disable features
ENABLE_TITLE_GENERATION=true
ENABLE_TAGS_GENERATION=true
ENABLE_WEB_SEARCH=false
AUDIO_STT_ENGINE=openai
```

### n8n Workflow Setup

#### Workflow Configuration
```bash
# Check n8n status
curl -f http://localhost:5678/healthz

# Access n8n interface
open http://localhost:5678

# Configure webhooks
N8N_WEBHOOK_URL=https://your-domain.com
WEBHOOK_URL=https://your-domain.com
```

#### Encryption Setup
```bash
# Generate encryption key
N8N_ENCRYPTION_KEY=$(openssl rand -base64 32)

# Update .env file
echo "N8N_ENCRYPTION_KEY=$N8N_ENCRYPTION_KEY" >> .env
```

### Slack Integration Setup

#### Slack App Configuration
1. Go to [api.slack.com](https://api.slack.com/apps)
2. Create new app
3. Configure OAuth & Permissions
4. Install app to workspace
5. Get bot token, app token, and user token

#### Environment Configuration
```bash
# Add Slack credentials to .env
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_MCP_XOXP_TOKEN=xoxp-your-user-token
LETTA_AGENT_ID=your-agent-id

# Restart services
docker-compose restart slackbot letta
```

### Cloudflare Tunnel Setup

#### Tunnel Configuration
1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Create new tunnel
3. Configure domain mapping
4. Get tunnel token

#### Environment Configuration
```bash
# Add Cloudflare credentials to .env
CLOUDFLARE_TUNNEL_TOKEN=your-tunnel-token
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_ZONE_ID=your-zone-id
CLOUDFLARE_API_TOKEN=your-api-token

# Update webhook URLs
N8N_WEBHOOK_URL=https://n8n.your-domain.com
WEBHOOK_URL=https://n8n.your-domain.com
N8N_HOST=n8n.your-domain.com
N8N_EDITOR_BASE_URL=https://n8n.your-domain.com

# Restart services
docker-compose restart
```

## ✅ Verification and Testing

### System Health Checks

#### Comprehensive Health Check
```bash
# Run full health check
./deployment/scripts/health-check.sh

# Expected output:
# Total checks: 18
# Passed: 16
# Failed: 0
# Warnings: 2
```

#### Individual Service Checks
```bash
# Check Letta
curl -f http://localhost:8283/v1/health/

# Check Open WebUI
curl -f http://localhost:8080/health

# Check n8n
curl -f http://localhost:5678/healthz

# Check Health Monitor
curl -f http://localhost:8083/health
```

### Functional Testing

#### AI Functionality Test
```bash
# Test Letta AI
curl -X POST http://localhost:8283/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello, can you help me test the system?"}]}'

# Test Open WebUI
open http://localhost:8080
# Try: "What can you do?"
```

#### Workflow Testing
```bash
# Test n8n workflows
open http://localhost:5678
# Create a simple workflow
# Test webhook endpoints
```

#### Integration Testing
```bash
# Test Slack integration (if configured)
# Send message to Slack bot
# Verify response

# Test external access (if configured)
curl -f https://your-domain.com/health
```

### Performance Testing

#### Resource Usage
```bash
# Monitor resource usage
docker stats

# Check system resources
htop
df -h
free -h
```

#### Load Testing
```bash
# Test concurrent requests
for i in {1..10}; do
  curl -f http://localhost:8283/v1/health/ &
done
wait
```

## 🔧 Post-Installation Configuration

### User Management

#### Admin User Setup
```bash
# Access Open WebUI
open http://localhost:8080

# Create admin account
# Set up user permissions
# Configure model access
```

#### API Key Management
```bash
# Rotate API keys
# Update .env file
# Restart services
docker-compose restart
```

### Monitoring Setup

#### Health Monitoring
```bash
# Set up monitoring cron job
echo "*/5 * * * * /path/to/ai-PA/deployment/scripts/health-check.sh" | crontab -

# Configure log monitoring
echo "*/1 * * * * docker-compose logs --since=1m >> /var/log/pa-ecosystem.log" | crontab -
```

#### Alerting Configuration
```bash
# Configure email alerts
# Set up Slack notifications
# Configure external monitoring
```

### Backup Configuration

#### Automated Backups
```bash
# Create backup script
cat > backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backups/pa-ecosystem/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup configuration
cp .env "$BACKUP_DIR/"

# Backup database
docker-compose exec supabase-db pg_dump -U postgres postgres > "$BACKUP_DIR/database.sql"

# Backup volumes
docker run --rm -v pa-ecosystem_n8n_data:/data -v "$BACKUP_DIR":/backup alpine tar czf /backup/n8n_data.tar.gz -C /data .
docker run --rm -v pa-ecosystem_letta_data:/data -v "$BACKUP_DIR":/backup alpine tar czf /backup/letta_data.tar.gz -C /data .

echo "Backup completed: $BACKUP_DIR"
EOF

chmod +x backup.sh

# Schedule backups
echo "0 2 * * * /path/to/ai-PA/backup.sh" | crontab -
```

## 🐛 Troubleshooting

### Common Issues

#### Service Won't Start
```bash
# Check service status
docker-compose ps

# Check logs
docker-compose logs [service-name]

# Check resource usage
docker stats

# Restart service
docker-compose restart [service-name]
```

#### Port Conflicts
```bash
# Find conflicting processes
lsof -i :8283
lsof -i :8080
lsof -i :5678

# Kill conflicting processes
sudo kill -9 [PID]

# Or change ports in .env
```

#### Database Issues
```bash
# Check database status
docker-compose exec supabase-db pg_isready -U postgres

# Check database logs
docker-compose logs supabase-db

# Restart database
docker-compose restart supabase-db
```

#### API Key Issues
```bash
# Validate API keys
./deployment/scripts/validate-config.sh

# Test API connectivity
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/models
```

### Diagnostic Commands

#### System Diagnostics
```bash
# System information
uname -a
lsb_release -a
docker --version
docker-compose --version

# Resource usage
htop
df -h
free -h
nproc
```

#### Service Diagnostics
```bash
# Docker status
docker ps -a
docker stats
docker system df

# Service logs
docker-compose logs --tail=100
docker-compose logs -f [service-name]
```

#### Network Diagnostics
```bash
# Port usage
netstat -tlnp | grep -E "(8283|8080|5678|8083)"

# Connectivity tests
curl -f http://localhost:8283/v1/health/
curl -f http://localhost:8080/health
curl -f http://localhost:5678/healthz
```

## 🔄 Maintenance and Updates

### Regular Maintenance

#### Daily Tasks
```bash
# Health check
./deployment/scripts/health-check.sh

# Check logs
docker-compose logs --since=1d
```

#### Weekly Tasks
```bash
# System update
sudo apt update && sudo apt upgrade -y

# Docker cleanup
docker system prune -a

# Log rotation
sudo logrotate /etc/logrotate.d/pa-ecosystem
```

#### Monthly Tasks
```bash
# Full system backup
./backup.sh

# Security updates
sudo apt update && sudo apt upgrade -y

# Performance review
docker stats
htop
df -h
```

### Updates and Upgrades

#### Application Updates
```bash
# Pull latest changes
git pull origin main

# Update services
docker-compose pull
docker-compose up -d

# Verify update
./deployment/scripts/health-check.sh
```

#### System Updates
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Update Docker
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io

# Restart services
docker-compose restart
```

### Monitoring and Alerting

#### Health Monitoring
```bash
# Set up monitoring
echo "*/5 * * * * /path/to/ai-PA/deployment/scripts/health-check.sh" | crontab -

# Configure alerts
# Set up email notifications
# Configure Slack alerts
```

#### Performance Monitoring
```bash
# Monitor resources
watch docker stats

# Monitor logs
tail -f /var/log/pa-ecosystem.log

# Monitor disk usage
watch df -h
```

---

**🎉 Installation Complete!** Your PA ecosystem is now fully installed and configured. Refer to the quick start guides for getting started with the system, or the configuration reference for advanced customization options.
