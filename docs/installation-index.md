# Installation Guides Index

**Choose the right installation guide for your operating system and deployment scenario**

This index helps you find the most appropriate installation guide based on your specific operating system and deployment requirements.

## 🎯 Choose Your Installation Guide

### 🐧 [Ubuntu Installation Guide](./installation-ubuntu.md)
**For**: Ubuntu 20.04 LTS and 22.04 LTS
**Features**: UFW firewall, systemd services, optimized for Ubuntu
**Best for**: Most Linux users, production deployments

### 🔴 [CentOS/RHEL Installation Guide](./installation-centos.md)
**For**: CentOS 8, RHEL 8, Rocky Linux 8, AlmaLinux 8
**Features**: firewalld, SELinux, systemd services, optimized for Red Hat-based systems
**Best for**: Enterprise environments, Red Hat-based distributions

### 🍎 [macOS Installation Guide](./installation-macos.md)
**For**: macOS 12.0 (Monterey) and later
**Features**: Docker Desktop, Homebrew, LaunchAgent services
**Best for**: Development and testing only

### 📖 [Main Installation Guide](./installation-guide.md)
**For**: All operating systems, comprehensive procedures
**Features**: Complete installation procedures, troubleshooting, maintenance
**Best for**: Reference documentation, advanced users

## 📊 Quick Comparison

| Guide | OS Support | Firewall | Service Manager | Best For |
|-------|------------|----------|-----------------|----------|
| [Ubuntu](./installation-ubuntu.md) | Ubuntu 20.04/22.04 | UFW | systemd | General Linux users |
| [CentOS/RHEL](./installation-centos.md) | CentOS 8, RHEL 8, Rocky 8, Alma 8 | firewalld | systemd | Enterprise environments |
| [macOS](./installation-macos.md) | macOS 12.0+ | Built-in | LaunchAgent | Development/testing |
| [Main](./installation-guide.md) | All supported | Multiple | Multiple | Reference documentation |

## 🚀 Quick Start Process

### 1. Choose Your Guide
Select the appropriate guide based on your operating system:
- **Ubuntu** → [Ubuntu Installation Guide](./installation-ubuntu.md)
- **CentOS/RHEL** → [CentOS/RHEL Installation Guide](./installation-centos.md)
- **macOS** → [macOS Installation Guide](./installation-macos.md)
- **Other/Reference** → [Main Installation Guide](./installation-guide.md)

### 2. Prepare Your System
```bash
# Clone repository
git clone https://github.com/your-org/ai-PA.git
cd ai-PA

# Make scripts executable
chmod +x deployment/deploy.sh deployment/scripts/*.sh

# Validate system requirements
./deployment/scripts/validate-requirements.sh
```

### 3. Follow Your Chosen Guide
Each guide provides step-by-step instructions for your specific operating system.

### 4. Verify Installation
```bash
# Health check
./deployment/scripts/health-check.sh

# Access interfaces
open http://localhost:8283  # Letta
open http://localhost:8080  # Open WebUI
open http://localhost:5678  # n8n
```

## 🔧 Prerequisites Checklist

Before starting any installation, ensure you have:

### System Requirements
- [ ] **Supported OS**: Ubuntu 20.04/22.04, CentOS 8, RHEL 8, Rocky 8, Alma 8, or macOS 12.0+
- [ ] **RAM**: 8GB minimum (16GB+ recommended)
- [ ] **Storage**: 100GB+ available space
- [ ] **CPU**: 4+ cores recommended
- [ ] **Network**: Internet connection

### Required Software
- [ ] **Docker**: 20.10.0 or later
- [ ] **Docker Compose**: 2.0.0 or later
- [ ] **Git**: 2.20.0 or later
- [ ] **curl**: 7.68.0 or later

### Required Accounts
- [ ] **OpenAI Account** - [Get API Key](https://platform.openai.com/api-keys)
- [ ] **Anthropic Account** - [Get API Key](https://console.anthropic.com/settings/keys)
- [ ] **Google AI Account** - [Get API Key](https://aistudio.google.com/app/apikey)

## 📚 Installation Methods

### Method 1: Automated Installation (Recommended)
```bash
# Quick installation
./deployment/deploy.sh

# Interactive installation
./deployment/deploy.sh --interactive

# Non-interactive installation
./deployment/deploy.sh --non-interactive
```

### Method 2: Manual Installation
Follow the step-by-step procedures in your chosen installation guide.

### Method 3: Container-Based Installation
```bash
# Using Docker Compose
docker-compose up -d

# Using Docker Swarm
docker swarm init
docker stack deploy -c docker-compose.yml pa-ecosystem
```

## 🔍 Verification Steps

### System Health Check
```bash
# Comprehensive health check
./deployment/scripts/health-check.sh

# Expected output:
# Total checks: 18
# Passed: 16
# Failed: 0
# Warnings: 2
```

### Service Verification
```bash
# Check individual services
curl -f http://localhost:8283/v1/health/  # Letta
curl -f http://localhost:8080/health       # Open WebUI
curl -f http://localhost:5678/healthz      # n8n
curl -f http://localhost:8083/health       # Health Monitor
```

### Functional Testing
```bash
# Test AI functionality
open http://localhost:8283
# Try: "Hello, can you help me test the system?"

# Test web interfaces
open http://localhost:8080  # Open WebUI
open http://localhost:5678  # n8n
```

## 🆘 Troubleshooting

### Common Issues

#### System Requirements Issues
```bash
# Check system requirements
./deployment/scripts/validate-requirements.sh

# Common fixes:
# - Increase disk space (minimum 100GB)
# - Add more RAM (minimum 8GB)
# - Install Docker and Docker Compose
```

#### Configuration Issues
```bash
# Validate configuration
./deployment/scripts/validate-config.sh

# Common fixes:
# - Replace all CHANGE_ME_* placeholders
# - Use strong passwords (32+ characters)
# - Verify API key formats
```

#### Service Issues
```bash
# Check service status
docker-compose ps

# Check logs
docker-compose logs [service-name]

# Restart services
docker-compose restart
```

### Getting Help

#### Self-Help Resources
1. **Check the troubleshooting guide**: [delivery/7/7-8.md](./delivery/7/7-8.md)
2. **Run diagnostics**: `./deployment/scripts/health-check.sh`
3. **Validate configuration**: `./deployment/scripts/validate-config.sh`
4. **Check logs**: `docker-compose logs [service-name]`

#### Documentation
- **Quick Start Guides**: [quick-start.md](./quick-start.md)
- **Configuration Reference**: [delivery/7/7-6.md](./delivery/7/7-6.md)
- **Troubleshooting Guide**: [delivery/7/7-8.md](./delivery/7/7-8.md)

## 🔄 Maintenance

### Regular Tasks
```bash
# Daily
./deployment/scripts/health-check.sh

# Weekly
docker-compose logs --since=7d
docker system prune

# Monthly
sudo apt update && sudo apt upgrade -y  # Ubuntu
sudo dnf update -y                      # CentOS/RHEL
brew update && brew upgrade             # macOS
```

### Updates
```bash
# Pull latest changes
git pull origin main

# Update services
docker-compose pull
docker-compose up -d

# Verify update
./deployment/scripts/health-check.sh
```

## 📖 Additional Resources

### Quick Start Guides
- **Main Quick Start**: [quick-start.md](./quick-start.md)
- **Development Setup**: [quick-start-development.md](./quick-start-development.md)
- **Production Setup**: [quick-start-production.md](./quick-start-production.md)
- **Minimal Setup**: [quick-start-minimal.md](./quick-start-minimal.md)

### Configuration
- **Environment Templates**: [deployment/templates/README.md](../deployment/templates/README.md)
- **Configuration Reference**: [delivery/7/7-6.md](./delivery/7/7-6.md)
- **Template Selection**: `./deployment/scripts/select-template.sh`

### Scripts
- **Deployment Script**: `./deployment/deploy.sh`
- **Health Check**: `./deployment/scripts/health-check.sh`
- **Configuration Validation**: `./deployment/scripts/validate-config.sh`
- **Rollback**: `./deployment/scripts/rollback.sh`

---

**Ready to install?** Choose your operating system above and follow the appropriate installation guide. Each guide is optimized for your specific environment and provides detailed step-by-step procedures.
