# Quick Start: Minimal Deployment

**Deploy PA ecosystem with minimal resources in 8 minutes**

This guide is optimized for resource-constrained environments, cost-conscious deployments, or simple setups that don't require all features.

## 🎯 Minimal Setup Overview

This setup provides:
- **Essential features only** - Core AI functionality
- **Resource-optimized** - Minimal RAM and CPU usage
- **Cost-effective** - Uses cheapest available models
- **Local access only** - No external access required
- **Simple configuration** - Minimal setup complexity

## ⏱️ Time Estimate: 8 minutes

## 📋 Minimal Requirements

### System Requirements
- **OS**: Ubuntu 20.04/22.04, CentOS 8, Debian 11, or macOS
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 50GB available disk space
- **CPU**: 2+ cores
- **Network**: Internet connection for API access

### Required API Keys
- **OpenAI API Key** - [Get from OpenAI Platform](https://platform.openai.com/api-keys)
- **Optional**: Anthropic and Gemini keys for more model options

## 🚀 Minimal Deployment

### Step 1: Quick Setup (1 minute)
```bash
# Clone and prepare
git clone https://github.com/your-org/ai-PA.git
cd ai-PA
chmod +x deployment/deploy.sh deployment/scripts/*.sh
```

### Step 2: Select Minimal Template (1 minute)
```bash
# Select minimal template
./deployment/scripts/select-template.sh
# Choose option 3: Minimal Template
```

### Step 3: Minimal Configuration (2 minutes)
```bash
# Edit configuration
nano .env

# Only configure these essential values:
OPENAI_API_KEY=sk-your-openai-key-here
POSTGRES_PASSWORD=minimal-password-123
N8N_ENCRYPTION_KEY=minimal-encryption-key-12345678901234567890123456789012

# All other values are pre-configured for minimal usage
```

### Step 4: Deploy (3 minutes)
```bash
# Deploy with minimal configuration
./deployment/deploy.sh --quick --skip-dependencies
```

### Step 5: Verify (1 minute)
```bash
# Quick health check
./deployment/scripts/health-check.sh

# Access interfaces
open http://localhost:8283  # Letta
open http://localhost:8080  # Open WebUI
```

## 🔧 Minimal Features

### Enabled Features
- ✅ **Letta AI Agent** - Core AI functionality
- ✅ **Open WebUI** - Web interface
- ✅ **PostgreSQL Database** - Data storage
- ✅ **Basic n8n** - Simple workflows
- ✅ **Health Monitor** - System monitoring

### Disabled Features (to save resources)
- ❌ **Slack Integration** - Requires additional setup
- ❌ **Gmail Integration** - Requires OAuth setup
- ❌ **Cloudflare Tunnels** - No external access
- ❌ **Advanced n8n Features** - Simplified workflows
- ❌ **Multiple AI Models** - Only OpenAI enabled
- ❌ **Web Search** - Disabled to save API costs

### Resource Usage
- **RAM**: ~2-4GB total
- **CPU**: ~1-2 cores
- **Storage**: ~20-30GB
- **Network**: Minimal (API calls only)

## 💰 Cost Optimization

### API Usage
- **Primary Model**: GPT-3.5-turbo (cheapest OpenAI model)
- **Embedding Model**: text-embedding-3-small (cheapest)
- **No Web Search**: Disabled to avoid additional API costs
- **Minimal Features**: Only essential AI interactions

### Resource Optimization
- **Lightweight Models**: Fastest, cheapest models
- **Minimal Logging**: Reduced log verbosity
- **Disabled Features**: Only essential services running
- **Local Access**: No external access costs

## 🧪 Testing Minimal Setup

### Basic Functionality Test
```bash
# Test Letta AI
open http://localhost:8283
# Try: "Hello, can you help me?"

# Test Open WebUI
open http://localhost:8080
# Try: "What can you do?"

# Test n8n
open http://localhost:5678
# Create a simple workflow
```

### Performance Test
```bash
# Check resource usage
docker stats

# Expected usage:
# - RAM: 2-4GB total
# - CPU: 10-30% per service
# - Storage: 20-30GB
```

## 🔄 Minimal Maintenance

### Daily Tasks
```bash
# Quick health check
./deployment/scripts/health-check.sh

# Check resource usage
docker stats
```

### Weekly Tasks
```bash
# Review logs for issues
docker-compose logs --since=7d

# Check disk space
df -h
```

### Monthly Tasks
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Clean up Docker
docker system prune -a
```

## 🚀 Upgrading from Minimal

### Add More Features
```bash
# Switch to development template
./deployment/scripts/select-template.sh
# Choose option 1: Development Template

# Edit .env to add more API keys
nano .env

# Restart services
docker-compose restart
```

### Add External Access
```bash
# Switch to Cloudflare template
./deployment/scripts/select-template.sh
# Choose option 4: Cloudflare Template

# Configure Cloudflare tunnel
nano .env

# Restart services
docker-compose restart
```

### Add Slack Integration
```bash
# Edit .env to add Slack credentials
nano .env

# Add these variables:
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
LETTA_AGENT_ID=your-agent-id

# Restart services
docker-compose restart
```

## 🐛 Minimal Troubleshooting

### Common Issues

#### "Insufficient resources"
```bash
# Check system resources
free -h
df -h
nproc

# Free up resources
sudo apt autoremove -y
docker system prune -a
```

#### "API key issues"
```bash
# Validate configuration
./deployment/scripts/validate-config.sh

# Test API key
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/models
```

#### "Services won't start"
```bash
# Check logs
docker-compose logs

# Restart services
docker-compose restart

# Full restart
docker-compose down && docker-compose up -d
```

### Performance Issues
```bash
# Check resource usage
docker stats

# Optimize Docker
docker system prune -a

# Restart services
docker-compose restart
```

## 📊 Minimal Monitoring

### Health Check
```bash
# Basic health check
./deployment/scripts/health-check.sh

# Expected output: All essential services healthy
```

### Resource Monitoring
```bash
# Monitor resources
watch docker stats

# Check disk usage
watch df -h

# Check memory usage
watch free -h
```

## 🔗 Related Documentation

- **Main Quick Start**: [quick-start.md](./quick-start.md)
- **Development Setup**: [quick-start-development.md](./quick-start-development.md)
- **Production Setup**: [quick-start-production.md](./quick-start-production.md)
- **Configuration Reference**: [delivery/7/7-6.md](./delivery/7/7-6.md)

## 💡 Tips for Minimal Deployment

### Cost Saving Tips
1. **Use GPT-3.5-turbo** instead of GPT-4 for most tasks
2. **Disable web search** to avoid additional API costs
3. **Use local models** with Ollama if available
4. **Monitor API usage** regularly
5. **Set usage limits** in your OpenAI account

### Performance Tips
1. **Close unused services** when not needed
2. **Use SSD storage** for better performance
3. **Allocate sufficient RAM** (8GB recommended)
4. **Monitor resource usage** regularly
5. **Restart services** if performance degrades

---

**🎉 Minimal Setup Complete!** You now have a lightweight, cost-effective PA ecosystem running with essential features only. Perfect for personal use, testing, or resource-constrained environments.
