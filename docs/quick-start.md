# PA Ecosystem Quick Start Guide

**Deploy your Personal Assistant ecosystem in 15 minutes or less!**

This guide will walk you through deploying the complete PA ecosystem on your home server or local machine. The deployment includes all services, databases, and configurations needed for a fully functional AI personal assistant.

## 🚀 Quick Start Overview

The PA ecosystem consists of:
- **Letta AI Agent** - Core AI assistant with memory and tool integration
- **Open WebUI** - Web interface for interacting with AI models
- **n8n** - Workflow automation and integration platform
- **Slackbot** - Slack integration for team collaboration
- **Health Monitor** - System health monitoring and alerts
- **MCP Servers** - Model Context Protocol servers for various integrations

## ⏱️ Time Estimate

- **Total Time**: 15 minutes
- **Prerequisites**: 5 minutes
- **Deployment**: 10 minutes

## 📋 Prerequisites

Before starting, ensure you have:

### System Requirements
- **OS**: Ubuntu 20.04/22.04, CentOS 8, Debian 11, or macOS (for testing)
- **RAM**: Minimum 8GB, Recommended 16GB+
- **Storage**: 100GB+ available disk space
- **CPU**: 4+ cores recommended
- **Network**: Internet connection for API access

### Required Accounts & API Keys
- **OpenAI API Key** - [Get from OpenAI Platform](https://platform.openai.com/api-keys)
- **Anthropic API Key** - [Get from Anthropic Console](https://console.anthropic.com/settings/keys)
- **Google Gemini API Key** - [Get from Google AI Studio](https://aistudio.google.com/app/apikey)

### Optional Integrations
- **Slack Workspace** - For team collaboration
- **Cloudflare Account** - For external access
- **Gmail Account** - For email integration

## 🛠️ Step 1: Download and Prepare (2 minutes)

### 1.1 Clone the Repository
```bash
git clone https://github.com/your-org/ai-PA.git
cd ai-PA
```

### 1.2 Make Scripts Executable
```bash
chmod +x deployment/deploy.sh
chmod +x deployment/scripts/*.sh
```

### 1.3 Verify System Requirements
```bash
./deployment/scripts/validate-requirements.sh
```

**Expected Output**: All checks should pass. If any fail, address them before proceeding.

## ⚙️ Step 2: Configure Environment (3 minutes)

### 2.1 Select Configuration Template
```bash
./deployment/scripts/select-template.sh
```

**Choose based on your needs:**
- **Development** - Local testing with example keys
- **Production** - Full deployment with real API keys
- **Minimal** - Resource-constrained environments
- **Cloudflare** - External access via Cloudflare tunnels
- **Local-Only** - Full features locally without external access
- **Custom** - Maximum customization

### 2.2 Edit Configuration
```bash
nano .env
```

**Required Changes:**
- Replace `CHANGE_ME_*` placeholders with real values
- Set your API keys
- Configure passwords (minimum 32 characters)

### 2.3 Validate Configuration
```bash
./deployment/scripts/validate-config.sh
```

**Expected Output**: All validation checks should pass.

## 🚀 Step 3: Deploy Services (5 minutes)

### 3.1 Run Deployment Script
```bash
./deployment/deploy.sh
```

**The script will:**
1. ✅ Validate system requirements
2. ✅ Install dependencies (Docker, Docker Compose)
3. ✅ Run interactive configuration wizard
4. ✅ Deploy all services with Docker Compose
5. ✅ Run health checks
6. ✅ Display access URLs and summary

### 3.2 Monitor Deployment
Watch for these success messages:
- `[SUCCESS] System requirements validation passed`
- `[SUCCESS] Dependencies installation completed`
- `[SUCCESS] Configuration completed`
- `[SUCCESS] Services deployed successfully`
- `[SUCCESS] All health checks passed`

## ✅ Step 4: Verify Deployment (2 minutes)

### 4.1 Check Service Status
```bash
./deployment/scripts/health-check.sh
```

### 4.2 Access Web Interfaces
- **Letta Web Interface**: http://localhost:8283
- **Open WebUI**: http://localhost:8080
- **n8n Interface**: http://localhost:5678
- **Health Monitor**: http://localhost:8083

### 4.3 Test Basic Functionality
1. Open Letta Web Interface
2. Try a simple query: "Hello, can you help me?"
3. Verify the AI responds appropriately

## 🎉 Step 5: Next Steps (3 minutes)

### 5.1 Configure Slack Integration (Optional)
1. Create a Slack app at [api.slack.com](https://api.slack.com/apps)
2. Get bot token, app token, and user token
3. Update `.env` file with Slack credentials
4. Restart services: `docker-compose restart`

### 5.2 Set Up External Access (Optional)
For external access via Cloudflare:
1. Set up Cloudflare tunnel
2. Update `.env` with Cloudflare credentials
3. Configure domain mapping
4. Restart services: `docker-compose restart`

### 5.3 Explore Features
- **Letta**: AI conversations with memory
- **Open WebUI**: Multiple AI model access
- **n8n**: Workflow automation
- **Health Monitor**: System monitoring

## 🔧 Troubleshooting

### Common Issues

#### "System requirements validation failed"
```bash
# Check system resources
./deployment/scripts/validate-requirements.sh -v

# Common fixes:
# - Increase disk space (minimum 100GB)
# - Add more RAM (minimum 8GB)
# - Install Docker and Docker Compose
```

#### "Configuration validation failed"
```bash
# Check configuration
./deployment/scripts/validate-config.sh

# Common fixes:
# - Replace all CHANGE_ME_* placeholders
# - Use strong passwords (32+ characters)
# - Verify API key formats
```

#### "Services deployment failed"
```bash
# Check Docker status
docker ps -a
docker-compose logs

# Common fixes:
# - Restart Docker service
# - Check port availability
# - Verify .env configuration
```

#### "Health checks failed"
```bash
# Check service health
./deployment/scripts/health-check.sh

# Common fixes:
# - Wait for services to fully start (2-3 minutes)
# - Check service logs
# - Verify API keys are valid
```

### Getting Help

1. **Check Logs**: `docker-compose logs [service-name]`
2. **Health Check**: `./deployment/scripts/health-check.sh`
3. **Rollback**: `./deployment/scripts/rollback.sh`
4. **Documentation**: See `docs/delivery/7/` for detailed guides

## 📚 Additional Resources

- **Detailed Installation Guide**: [docs/delivery/7/7-5.md](./delivery/7/7-5.md)
- **Configuration Reference**: [docs/delivery/7/7-6.md](./delivery/7/7-6.md)
- **Troubleshooting Guide**: [docs/delivery/7/7-8.md](./delivery/7/7-8.md)
- **Template Guide**: [deployment/templates/README.md](../deployment/templates/README.md)

## 🎯 Success Criteria

Your deployment is successful when:
- ✅ All services are running (`docker-compose ps`)
- ✅ Health checks pass (`./deployment/scripts/health-check.sh`)
- ✅ Web interfaces are accessible
- ✅ AI responds to queries in Letta
- ✅ No error messages in logs

## 🔄 Maintenance

### Regular Tasks
- **Daily**: Check health monitor dashboard
- **Weekly**: Review service logs
- **Monthly**: Update API keys if needed
- **As needed**: Backup configuration

### Updates
```bash
# Pull latest changes
git pull origin main

# Redeploy with updates
./deployment/deploy.sh --force
```

---

**🎉 Congratulations!** You now have a fully functional Personal Assistant ecosystem running on your system. The AI can help with tasks, answer questions, and integrate with your existing tools and workflows.

**Need help?** Check the troubleshooting section above or refer to the detailed documentation in the `docs/` directory.
