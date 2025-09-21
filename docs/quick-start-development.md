# Quick Start: Development Environment

**Deploy PA ecosystem for development and testing in 10 minutes**

This guide is optimized for developers who want to quickly set up a local development environment for testing and development work.

## 🎯 Development Setup Overview

This setup provides:
- **Local access only** (no external access required)
- **Debug logging enabled** for troubleshooting
- **Example API keys** (replace with real ones for testing)
- **All features enabled** for comprehensive testing
- **Resource-optimized** for development machines

## ⏱️ Time Estimate: 10 minutes

## 🚀 Quick Development Deployment

### Step 1: Clone and Prepare (1 minute)
```bash
git clone https://github.com/your-org/ai-PA.git
cd ai-PA
chmod +x deployment/deploy.sh deployment/scripts/*.sh
```

### Step 2: Select Development Template (1 minute)
```bash
./deployment/scripts/select-template.sh
# Choose option 1: Development Template
```

### Step 3: Configure for Development (2 minutes)
```bash
# Edit the .env file
nano .env

# Replace these key values:
# OPENAI_API_KEY=sk-your-real-openai-key-here
# ANTHROPIC_API_KEY=sk-ant-your-real-anthropic-key-here
# GEMINI_API_KEY=AIzaSy-your-real-gemini-key-here
```

### Step 4: Deploy (5 minutes)
```bash
./deployment/deploy.sh --quick
```

### Step 5: Verify (1 minute)
```bash
# Check all services are running
docker-compose ps

# Access the interfaces
open http://localhost:8283  # Letta
open http://localhost:8080  # Open WebUI
open http://localhost:5678  # n8n
```

## 🔧 Development Features

### Debug Mode Enabled
- **Letta Debug**: `LETTA_DEBUG=true`
- **Open WebUI Logs**: `OPENWEBUI_LOG_LEVEL=DEBUG`
- **Hayhooks Logs**: `HAYHOOKS_LOG_LEVEL=DEBUG`

### Local Access URLs
- **Letta Web Interface**: http://localhost:8283
- **Open WebUI**: http://localhost:8080
- **n8n Interface**: http://localhost:5678
- **Health Monitor**: http://localhost:8083

### Development Tools
- **Docker Compose**: Easy service management
- **Health Checks**: Monitor service status
- **Logs**: Accessible via `docker-compose logs`
- **Configuration**: Easy to modify and test

## 🧪 Testing Your Setup

### 1. Test Letta AI Agent
```bash
# Open Letta interface
open http://localhost:8283

# Try these test queries:
# "Hello, can you help me test the system?"
# "What models are available?"
# "Can you search the web for recent AI news?"
```

### 2. Test Open WebUI
```bash
# Open Open WebUI interface
open http://localhost:8080

# Test features:
# - Chat with different AI models
# - Test title generation
# - Test tags generation
# - Try RAG functionality
```

### 3. Test n8n Workflows
```bash
# Open n8n interface
open http://localhost:5678

# Test features:
# - Create a simple workflow
# - Test webhook endpoints
# - Test API integrations
```

## 🔄 Development Workflow

### Making Changes
```bash
# 1. Edit configuration
nano .env

# 2. Restart affected services
docker-compose restart [service-name]

# 3. Check logs
docker-compose logs -f [service-name]

# 4. Test changes
./deployment/scripts/health-check.sh
```

### Adding New Services
```bash
# 1. Add service to docker-compose.yml
# 2. Add environment variables to .env
# 3. Restart services
docker-compose up -d

# 4. Update health checks
./deployment/scripts/health-check.sh
```

### Debugging Issues
```bash
# Check service status
docker-compose ps

# View service logs
docker-compose logs [service-name]

# Check health status
./deployment/scripts/health-check.sh

# Validate configuration
./deployment/scripts/validate-config.sh
```

## 🛠️ Development Tools

### Useful Commands
```bash
# View all logs
docker-compose logs -f

# Restart all services
docker-compose restart

# Stop all services
docker-compose down

# Start specific service
docker-compose up -d [service-name]

# View service logs
docker-compose logs -f [service-name]

# Execute command in container
docker-compose exec [service-name] [command]

# Check resource usage
docker stats
```

### Configuration Management
```bash
# Backup current configuration
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)

# Restore configuration
cp .env.backup.YYYYMMDD_HHMMSS .env

# Validate configuration
./deployment/scripts/validate-config.sh

# Select different template
./deployment/scripts/select-template.sh
```

## 🐛 Common Development Issues

### Port Conflicts
```bash
# Check what's using ports
lsof -i :8283
lsof -i :8080
lsof -i :5678

# Kill conflicting processes
sudo kill -9 [PID]
```

### Docker Issues
```bash
# Restart Docker
sudo systemctl restart docker

# Clean up Docker
docker system prune -a

# Rebuild services
docker-compose up -d --build
```

### API Key Issues
```bash
# Validate API keys
./deployment/scripts/validate-config.sh

# Test API connectivity
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/models
```

### Service Won't Start
```bash
# Check service logs
docker-compose logs [service-name]

# Check service status
docker-compose ps

# Restart specific service
docker-compose restart [service-name]
```

## 📚 Next Steps

### For Development
1. **Set up your IDE** for Docker development
2. **Configure your API keys** for testing
3. **Explore the codebase** in `src/` directories
4. **Test integrations** with external services
5. **Develop new features** and workflows

### For Production
1. **Switch to production template** when ready
2. **Configure external access** if needed
3. **Set up monitoring** and alerting
4. **Implement backup procedures**
5. **Deploy to production server**

## 🔗 Related Documentation

- **Main Quick Start**: [quick-start.md](./quick-start.md)
- **Production Deployment**: [quick-start-production.md](./quick-start-production.md)
- **Configuration Reference**: [delivery/7/7-6.md](./delivery/7/7-6.md)
- **Troubleshooting Guide**: [delivery/7/7-8.md](./delivery/7/7-8.md)

---

**Happy developing!** 🚀 This development environment gives you everything you need to build and test with the PA ecosystem.
